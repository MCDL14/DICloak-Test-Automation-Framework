from __future__ import annotations

import copy
import os
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

import streamlit_runner
from core.app_packages import APP_PROFILE_ENV, runtime_app_profile
from core.remote_runner import (
    RemoteHost,
    RemoteRunRequest,
    _stage_remote_app_profile,
    build_remote_command,
    build_remote_health_check_command,
    collect_remote_artifacts,
    run_remote_health_check,
    run_remote_tests,
)
from core.remote_sync import _remote_setup_script, create_local_sync_bundle


def _profile() -> dict:
    return runtime_app_profile({
        "windows_exe_path": "C:/Disposable Test APP/DICloak.exe",
        "macos_app_name": "DICloak2",
        "api_base_url": "http://gin-server-test.dicloak.com",
        "cdp_port": 9223,
    })


def _host() -> RemoteHost:
    return RemoteHost(
        name="test-mac", host="example.invalid", username="test-user",
        project_dir="/Users/test-user/project", config="config/config.macos.yaml",
    )


class TestPackageLocalExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="test-package-execution-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config_path = self.root / "config.yaml"
        self.path_patch = mock.patch("streamlit_runner.CONFIG_PATH", self.config_path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def _run(self, *, app_profile=None, stop_event=None, attach=True):
        return streamlit_runner._run_selected_tests_unlocked(
            ["tests.p0.example.TestExample.test_one"], queue.Queue(),
            attach_existing_app=attach,
            account_profile={"group_name": "独立测试组", "password": "disposable-test-only"},
            stop_event=stop_event or threading.Event(), app_profile=app_profile,
        )

    def test_local_app_and_account_profiles_are_separate_and_short_lived(self) -> None:
        captured = []

        def run_child(command, *_args, **_kwargs):
            package_path = Path(command[command.index("--app-profile") + 1])
            account_path = Path(command[command.index("--account-profile") + 1])
            self.assertNotEqual(package_path, account_path)
            self.assertTrue(package_path.name.startswith(".ui_app_profile_"))
            self.assertEqual(yaml.safe_load(package_path.read_text(encoding="utf-8")), _profile())
            self.assertNotIn("password", package_path.read_text(encoding="utf-8"))
            self.assertNotIn("disposable-test-only", " ".join(command))
            captured.extend((package_path, account_path))
            return 0

        with mock.patch("streamlit_runner._run_streaming_subprocess", side_effect=run_child):
            self.assertEqual(self._run(app_profile=_profile()), 0)
        self.assertTrue(captured)
        self.assertTrue(all(not path.exists() for path in captured))

    def test_production_command_does_not_add_package_profile(self) -> None:
        with mock.patch("streamlit_runner._run_streaming_subprocess", return_value=0) as child:
            self._run()
        self.assertNotIn("--app-profile", child.call_args.args[0])
        self.assertEqual(list(self.root.glob(".ui_app_profile_*.yaml")), [])

    def test_real_child_output_preserves_chinese_startup_errors(self) -> None:
        messages = queue.Queue()
        with mock.patch.dict(os.environ, {"PYTHONIOENCODING": "ascii"}):
            result = streamlit_runner._run_streaming_subprocess(
                [sys.executable, "-u", "-c", "print('[ERROR] 配置加载失败：测试 APP 路径无效')"],
                messages, threading.Event(), cwd=self.root,
            )
        self.assertEqual(result, 0)
        self.assertEqual(messages.get_nowait(), "[ERROR] 配置加载失败：测试 APP 路径无效")
        self.assertTrue(messages.empty())

    def test_package_profile_is_removed_when_child_raises(self) -> None:
        with mock.patch("streamlit_runner._run_streaming_subprocess", side_effect=OSError("synthetic")):
            with self.assertRaises(OSError):
                self._run(app_profile=_profile())
        self.assertEqual(list(self.root.glob(".ui_*_profile_*.yaml")), [])

    def test_cancel_cleanup_receives_same_frozen_test_package(self) -> None:
        stopped = threading.Event()

        def stop_child(*_args, **_kwargs):
            stopped.set()
            return 130

        with (
            mock.patch("streamlit_runner._run_streaming_subprocess", side_effect=stop_child),
            mock.patch("streamlit_runner._close_managed_app_after_cancel") as close,
        ):
            self.assertEqual(self._run(app_profile=_profile(), stop_event=stopped, attach=False), 130)
        self.assertEqual(close.call_args.kwargs["app_profile"], _profile())

    def test_cancel_cleanup_applies_profile_before_constructing_app_manager(self) -> None:
        original, effective = {"base": "production"}, {"resolved": "test-only"}
        with (
            mock.patch("streamlit_runner._build_config", return_value=original),
            mock.patch("streamlit_runner.apply_runtime_app_profile", return_value=effective) as apply,
            mock.patch("streamlit_runner.AppManager") as manager,
        ):
            streamlit_runner._close_managed_app_after_cancel(queue.Queue(), app_profile=_profile())
        apply.assert_called_once_with(original, _profile())
        self.assertIs(manager.call_args.args[0], effective)
        manager.return_value.close.assert_called_once_with()

    def test_local_profile_write_failure_removes_partial_file(self) -> None:
        with mock.patch("streamlit_runner.yaml.safe_dump", side_effect=OSError("synthetic")):
            with self.assertRaises(OSError):
                streamlit_runner._write_local_app_profile(_profile())
        self.assertEqual(list(self.root.glob(".ui_app_profile_*.yaml")), [])


class TestPackageRemoteExecutionTests(unittest.TestCase):
    def test_precheck_command_includes_package_profile_not_account_secrets(self) -> None:
        command = build_remote_command(_host(), RemoteRunRequest(
            scope="precheck", account_profile_path="/private/account.yaml",
            app_profile_path="/private/test app.yaml",
        ))
        self.assertIn("--precheck", command)
        self.assertIn("--app-profile '/private/test app.yaml'", command)
        self.assertNotIn("--account-profile", command)

    def test_remote_stages_both_profiles_and_cleans_up_after_failure(self) -> None:
        captured = []
        request = RemoteRunRequest(
            scope="cases", values=("test.example",),
            account_profile={"group_name": "test-only"}, app_profile=_profile(),
        )
        with (
            mock.patch("core.remote_runner._stage_remote_account_profile", return_value="/private/account.yaml"),
            mock.patch("core.remote_runner._stage_remote_app_profile", return_value="/private/package.yaml"),
            mock.patch("core.remote_runner._remove_remote_account_profile") as remove_account,
            mock.patch("core.remote_runner._remove_remote_app_profile") as remove_package,
            mock.patch("core.remote_runner._exec_ssh_command",
                       side_effect=lambda _host, command, *_args, **_kwargs: captured.append(command) or 3),
        ):
            result = run_remote_tests(_host(), request, queue.Queue())
        self.assertEqual(result.exit_code, 3)
        self.assertIn("--app-profile /private/package.yaml", captured[0])
        self.assertIn("--account-profile /private/account.yaml", captured[0])
        remove_account.assert_called_once()
        remove_package.assert_called_once()

    def test_account_profile_is_cleaned_if_package_staging_fails(self) -> None:
        request = RemoteRunRequest(scope="precheck", account_profile={"group_name": "test"}, app_profile=_profile())
        with (
            mock.patch("core.remote_runner._stage_remote_account_profile", return_value="/private/account.yaml"),
            mock.patch("core.remote_runner._stage_remote_app_profile", side_effect=RuntimeError("synthetic")),
            mock.patch("core.remote_runner._remove_remote_account_profile") as remove,
            mock.patch("core.remote_runner._exec_ssh_command") as execute,
        ):
            with self.assertRaises(RuntimeError):
                run_remote_tests(_host(), request, queue.Queue())
        remove.assert_called_once()
        execute.assert_not_called()

    def test_remote_profile_is_private_before_payload_write(self) -> None:
        events = []
        client = mock.MagicMock()
        sftp = client.open_sftp.return_value
        sftp.chmod.side_effect = lambda *_args: events.append("chmod")
        remote_file = sftp.open.return_value.__enter__.return_value
        remote_file.write.side_effect = lambda *_args: events.append("write")
        with mock.patch("core.remote_runner._connect_ssh_client", return_value=client):
            path = _stage_remote_app_profile(_host(), _profile())
        self.assertIn(".ui_app_profile_", path)
        self.assertEqual(events, ["chmod", "write"])
        self.assertEqual(sftp.open.call_args.args[1], "wx")
        sftp.chmod.assert_called_once_with(path, 0o600)
        self.assertEqual(yaml.safe_load(remote_file.write.call_args.args[0]), _profile())
        client.close.assert_called_once_with()

    def test_health_check_uses_test_profile_and_removes_it(self) -> None:
        with (
            mock.patch("core.remote_runner._stage_remote_app_profile", return_value="/private/package.yaml"),
            mock.patch("core.remote_runner._remove_remote_app_profile") as remove,
            mock.patch("core.remote_runner._exec_ssh_command", return_value=0) as execute,
        ):
            result = run_remote_health_check(_host(), queue.Queue(), app_profile=_profile())
        self.assertEqual(result.exit_code, 0)
        command = execute.call_args.args[1]
        self.assertIn(APP_PROFILE_ENV, command)
        self.assertIn("/private/package.yaml", command)
        remove.assert_called_once()

    def test_production_health_check_command_has_no_package_override(self) -> None:
        command = build_remote_health_check_command(_host())
        self.assertIn("os.environ.pop(", command)
        self.assertIn(APP_PROFILE_ENV, command)
        self.assertIn("DICLOAK_ACCOUNT_PROFILE_FILE", command)
        self.assertNotIn("os.environ[", command)

    def test_remote_command_clears_inherited_profiles_before_explicit_cli_selection(self) -> None:
        command = build_remote_command(_host(), RemoteRunRequest(scope="precheck"))
        self.assertIn("env -u DICLOAK_APP_PROFILE_FILE -u DICLOAK_ACCOUNT_PROFILE_FILE", command)
        self.assertNotIn("--app-profile", command)

    def test_test_artifacts_are_saved_under_separate_package_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="test-package-artifacts-") as directory:
            with (
                mock.patch("core.remote_runner._connect_ssh_client", return_value=mock.MagicMock()),
                mock.patch("core.remote_runner._copy_recent_remote_tree", return_value=0),
            ):
                result = collect_remote_artifacts(
                    _host(), 1.0, queue.Queue(), local_root=directory, package_kind="test",
                )
            self.assertEqual(result.local_dir.parent.name, "test-app")


class TestPackageRunnerPropagationTests(unittest.TestCase):
    def test_dual_execution_passes_frozen_profiles_to_each_machine(self) -> None:
        local_profile, remote_profile = _profile(), copy.deepcopy(_profile())
        remote_profile["settings"]["macos_app_name"] = "DICloak"
        with (
            mock.patch("streamlit_runner._run_selected_tests_unlocked", return_value=0) as local,
            mock.patch("streamlit_runner._run_remote_cli_unlocked", return_value=0) as remote,
        ):
            streamlit_runner.run_local_and_remote(
                ["test.local"], queue.Queue(), remote_test_ids=["test.remote"],
                local_attach_existing_app=False, local_account_profile={"group_name": "group-1"},
                remote_host_name="test-mac", remote_attach_existing_app=False,
                remote_collect_artifacts=False, remote_sync_before_run=False,
                remote_ssh_host="example.invalid", remote_ssh_port=22,
                remote_ssh_username="test-user", remote_ssh_password="",
                remote_account_profile={"group_name": "group-2"},
                local_app_profile=local_profile, remote_app_profile=remote_profile,
            )
        self.assertEqual(local.call_args.kwargs["app_profile"], local_profile)
        self.assertEqual(remote.call_args.kwargs["app_profile"], remote_profile)
        self.assertEqual(remote.call_args.kwargs["case_ids"], ["test.remote"])
        self.assertIs(local.call_args.kwargs["stop_event"], remote.call_args.kwargs["stop_event"])

    def test_remote_ui_execution_carries_profile_and_labels_artifacts(self) -> None:
        result = SimpleNamespace(host_name="test-mac", exit_code=0, started_at=1.0, finished_at=2.0)
        with (
            mock.patch("streamlit_runner._remote_host_by_name", return_value=_host()),
            mock.patch("streamlit_runner.run_remote_tests", return_value=result) as run,
            mock.patch("streamlit_runner.collect_remote_artifacts") as artifacts,
        ):
            streamlit_runner._run_remote_cli_unlocked(
                "test-mac", "precheck", "", queue.Queue(), attach_existing_app=False,
                collect_artifacts=True, sync_before_run=False, ssh_host="", ssh_port=None,
                ssh_username="", ssh_password="", case_ids=None, account_profile=None,
                stop_event=threading.Event(), app_profile=_profile(),
            )
        self.assertEqual(run.call_args.args[1].app_profile, _profile())
        self.assertEqual(artifacts.call_args.kwargs["package_kind"], "test")

    def test_remote_preview_discloses_test_profile_flag_without_creating_file(self) -> None:
        with mock.patch("streamlit_runner._remote_host_by_name", return_value=_host()):
            command = streamlit_runner.preview_remote_command("test-mac", "precheck", "", app_profile=_profile())
        self.assertIn("--app-profile", command)
        self.assertIn("<run-id>", command)


class TestPackageSyncProtectionTests(unittest.TestCase):
    def test_test_configuration_and_runtime_profiles_never_enter_code_bundle(self) -> None:
        import tarfile

        with tempfile.TemporaryDirectory(prefix="test-package-bundle-") as directory:
            root = Path(directory)
            config = root / "config"
            config.mkdir()
            (root / "run.py").write_text("pass\n", encoding="utf-8")
            for name in ("account_groups.test.yaml", "test_app_package.yaml", ".ui_app_profile_test.yaml"):
                (config / name).write_text("test_only: disposable\n", encoding="utf-8")
            (config / "remote_sync.yaml").write_text(
                yaml.safe_dump({"include": ["**", "run.py"], "exclude": []}), encoding="utf-8",
            )
            bundle = create_local_sync_bundle(root)
            try:
                with tarfile.open(bundle.archive_path) as archive:
                    names = archive.getnames()
                self.assertTrue(all("test_app_package.yaml" not in name for name in names))
                self.assertTrue(all("account_groups.test.yaml" not in name for name in names))
                self.assertTrue(all(".ui_app_profile_" not in name for name in names))
            finally:
                bundle.archive_path.unlink(missing_ok=True)

    def test_release_preservation_does_not_copy_test_accounts_or_local_settings(self) -> None:
        script = _remote_setup_script(
            host=_host(), remote_archive="/tmp/disposable.tar.gz", release_root="/srv/releases",
            release_dir="/srv/releases/test", release_name="test", keep_releases=5, compile_check=False,
        )
        self.assertIn("|account_groups.test.yaml|test_app_package.yaml|", script)
        self.assertIn(".ui_app_profile_*.yaml) continue", script)


if __name__ == "__main__":
    unittest.main()
