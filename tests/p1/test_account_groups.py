from __future__ import annotations

import os
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

import core.remote_runner as remote_runner
import streamlit_runner
from core.account_groups import (
    ACCOUNT_PROFILE_ENV,
    account_group_test_suffix,
    account_group_missing_fields,
    apply_runtime_account_profile,
    concurrent_account_group_conflicts,
    load_account_groups,
    runtime_account_profile,
    save_account_groups,
)
from core.config import DEFAULT_CONFIG, load_config
from core.remote_runner import (
    RemoteHost,
    RemoteRunRequest,
    build_remote_command,
    run_remote_tests,
)
from run import parse_args


def _sample_group(name: str, suffix: str) -> dict:
    return {
        "name": name,
        "automation_account": {
            "username": f"external-{suffix}@example.com",
            "password": f"external-password-{suffix}",
            "team_name": f"team-{suffix}",
            "member_id": f"external-id-{suffix}",
        },
        "case_external_member": {
            "name": f"case-external-member-{suffix}",
            "email": f"case-external-{suffix}@example.com",
        },
        "internal_member": {
            "username": f"INTERNAL{suffix}",
            "password": f"internal-password-{suffix}",
            "member_id": f"internal-id-{suffix}",
        },
        "member_api_token": f"api-token-{suffix}",
    }


class AccountGroupTests(unittest.TestCase):
    def tearDown(self) -> None:
        if streamlit_runner.ui_task_status().get("locked"):
            streamlit_runner._release_run_lock()

    def test_two_groups_round_trip_with_passwords(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "account_groups.yaml"
            groups = {
                "group_1": _sample_group("Windows", "1"),
                "group_2": _sample_group("macOS", "2"),
            }

            save_account_groups(path, groups)
            loaded = load_account_groups(path)

            self.assertEqual(loaded, groups)
            self.assertEqual(
                loaded["group_1"]["automation_account"]["password"],
                "external-password-1",
            )
            self.assertEqual(
                loaded["group_2"]["internal_member"]["password"],
                "internal-password-2",
            )
            self.assertEqual(
                loaded["group_2"]["case_external_member"]["name"],
                "case-external-member-2",
            )

    def test_runtime_profile_overrides_login_and_member_api_data(self) -> None:
        profile = runtime_account_profile(_sample_group("macOS", "2"))

        merged = apply_runtime_account_profile(DEFAULT_CONFIG, profile)

        self.assertEqual(merged["account"]["username"], "external-2@example.com")
        self.assertEqual(merged["account"]["team_name"], "team-2")
        api_data = merged["test_data"]["api_member_edit"]
        self.assertEqual(api_data["external_member_id"], "external-id-2")
        self.assertEqual(api_data["internal_member"]["member_id"], "internal-id-2")
        self.assertEqual(api_data["token"], "api-token-2")
        self.assertEqual(
            merged["test_data"]["case_external_member"],
            {
                "name": "case-external-member-2",
                "email": "case-external-2@example.com",
            },
        )

    def test_load_config_applies_profile_to_every_reload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            profile_path = Path(temp_dir) / "profile.yaml"
            config_path.write_text(
                yaml.safe_dump(DEFAULT_CONFIG, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            profile_path.write_text(
                yaml.safe_dump(runtime_account_profile(_sample_group("Windows", "1")), allow_unicode=True),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {ACCOUNT_PROFILE_ENV: str(profile_path)}, clear=False):
                first = load_config(config_path)
                second = load_config(config_path)

            self.assertEqual(first["account"]["username"], "external-1@example.com")
            self.assertEqual(second["test_data"]["api_member_edit"]["internal_member"]["username"], "INTERNAL1")
            self.assertEqual(first["_account_group_name"], "Windows")

    def test_required_fields_expand_for_member_api_cases(self) -> None:
        incomplete = _sample_group("Incomplete", "1")
        incomplete["internal_member"]["member_id"] = ""
        incomplete["member_api_token"] = ""

        missing = account_group_missing_fields(
            incomplete,
            require_internal=True,
            require_member_ids=True,
            require_member_api=True,
        )

        self.assertIn("内部成员 ID", missing)
        self.assertIn("成员 Open API token", missing)

    def test_required_fields_include_case_external_member_only_when_needed(self) -> None:
        incomplete = _sample_group("Incomplete", "1")
        incomplete["case_external_member"]["name"] = ""
        incomplete["case_external_member"]["email"] = ""

        missing = account_group_missing_fields(incomplete, require_case_external=True)

        self.assertIn("用例外部成员名称", missing)
        self.assertIn("用例外部成员邮箱", missing)

    def test_internal_ui_account_does_not_require_member_id(self) -> None:
        incomplete = _sample_group("Internal UI", "1")
        incomplete["internal_member"]["member_id"] = ""

        missing = account_group_missing_fields(incomplete, require_internal=True)

        self.assertNotIn("内部成员 ID", missing)

    def test_legacy_external_and_internal_keys_are_migrated(self) -> None:
        legacy = {
            "name": "Legacy",
            "external": {
                "username": "legacy-main@example.com",
                "password": "main-password",
                "team_name": "legacy-team",
                "member_id": "legacy-main-id",
            },
            "internal": {
                "username": "LEGACY001",
                "password": "internal-password",
                "member_id": "legacy-internal-id",
            },
        }

        profile = runtime_account_profile(legacy)

        self.assertEqual(
            profile["automation_account"]["username"],
            "legacy-main@example.com",
        )
        self.assertEqual(profile["internal_member"]["username"], "LEGACY001")
        self.assertEqual(
            profile["case_external_member"],
            {
                "name": "外部成员1",
                "email": "oytrhsjwe@tempmail.cn",
            },
        )

    def test_concurrent_groups_reject_same_accounts_or_team(self) -> None:
        local = _sample_group("Windows", "1")
        remote = _sample_group("macOS", "2")
        remote["automation_account"]["team_name"] = local["automation_account"]["team_name"].upper()
        remote["internal_member"]["username"] = local["internal_member"]["username"].lower()

        conflicts = concurrent_account_group_conflicts(local, remote)

        self.assertIn("自动化团队不能相同", conflicts)
        self.assertIn("内部账号不能相同", conflicts)
        self.assertNotIn("自动化主账号不能相同", conflicts)

    def test_account_group_test_suffix_is_stable_and_group_specific(self) -> None:
        first_config = apply_runtime_account_profile(
            DEFAULT_CONFIG,
            runtime_account_profile(_sample_group("Windows", "1")),
        )
        second_config = apply_runtime_account_profile(
            DEFAULT_CONFIG,
            runtime_account_profile(_sample_group("macOS", "2")),
        )

        first_suffix = account_group_test_suffix(first_config)

        self.assertEqual(first_suffix, account_group_test_suffix(first_config))
        self.assertRegex(first_suffix, r"^\d{6}$")
        self.assertNotEqual(first_suffix, account_group_test_suffix(second_config))

    def test_cli_accepts_runtime_account_profile(self) -> None:
        args = parse_args(["--account-profile", "config/runtime.yaml"])

        self.assertEqual(args.account_profile, "config/runtime.yaml")

    def test_remote_command_contains_only_profile_path(self) -> None:
        host = RemoteHost(
            name="macos-arm64",
            host="127.0.0.1",
            username="tester",
            project_dir="/tmp/dicloak",
        )
        request = RemoteRunRequest(
            scope="case",
            value="tests.p0.sample.TestSample.test_one",
            account_profile_path="/tmp/dicloak/config/.ui_account_profile.yaml",
        )

        command = build_remote_command(host, request)

        self.assertIn("--account-profile /tmp/dicloak/config/.ui_account_profile.yaml", command)
        self.assertNotIn("password", command)
        self.assertNotIn("api-token", command)

    def test_remote_profile_is_staged_and_removed(self) -> None:
        host = RemoteHost(
            name="macos-account-profile-test",
            host="127.0.0.1",
            username="tester",
            project_dir="/tmp/dicloak",
        )
        profile = runtime_account_profile(_sample_group("macOS", "2"))
        request = RemoteRunRequest(
            scope="case",
            value="tests.p0.sample.TestSample.test_one",
            account_profile=profile,
        )
        log_queue: queue.Queue = queue.Queue()

        with (
            patch("core.remote_runner._stage_remote_account_profile", return_value="/tmp/profile.yaml") as stage,
            patch("core.remote_runner._exec_ssh_command", return_value=0),
            patch("core.remote_runner._remove_remote_account_profile") as remove,
        ):
            result = run_remote_tests(host, request, log_queue)

        self.assertEqual(result.exit_code, 0)
        stage.assert_called_once_with(host, profile)
        remove.assert_called_once_with(host, "/tmp/profile.yaml", log_queue)
        self.assertIn("--account-profile /tmp/profile.yaml", result.command)
        self.assertNotIn("external-password-2", result.command)
        self.assertNotIn("api-token-2", result.command)

    def test_remote_profile_permission_failure_removes_partial_file(self) -> None:
        host = RemoteHost(
            name="macos-partial-profile-test",
            host="127.0.0.1",
            username="tester",
            project_dir="/tmp/dicloak",
        )
        client = MagicMock()
        sftp = MagicMock()
        client.open_sftp.return_value = sftp
        sftp.chmod.side_effect = OSError("chmod failed")

        with patch("core.remote_runner._connect_ssh_client", return_value=client):
            with self.assertRaises(remote_runner.RemoteRunError):
                remote_runner._stage_remote_account_profile(
                    host,
                    runtime_account_profile(_sample_group("macOS", "2")),
                )

        sftp.remove.assert_called_once()
        sftp.close.assert_called_once()
        client.close.assert_called_once()

    def test_local_profile_file_exists_only_during_subprocess(self) -> None:
        log_queue: queue.Queue = queue.Queue()
        stop_event = threading.Event()
        profile = runtime_account_profile(_sample_group("Windows", "1"))
        captured_path: list[Path] = []

        def fake_subprocess(command, *_args, **_kwargs) -> int:
            profile_arg = command[command.index("--account-profile") + 1]
            path = Path(profile_arg)
            self.assertTrue(path.exists())
            captured_path.append(path)
            return 0

        with patch("streamlit_runner._run_streaming_subprocess", side_effect=fake_subprocess):
            exit_code = streamlit_runner._run_selected_tests_unlocked(
                ["tests.p0.sample.TestSample.test_one"],
                log_queue,
                attach_existing_app=True,
                account_profile=profile,
                stop_event=stop_event,
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(captured_path)
        self.assertFalse(captured_path[0].exists())

    def test_local_profile_write_failure_removes_partial_file(self) -> None:
        profile = runtime_account_profile(_sample_group("Windows", "1"))
        with (
            patch("streamlit_runner.uuid.uuid4") as uuid4,
            patch("streamlit_runner.yaml.safe_dump", side_effect=OSError("write failed")),
        ):
            uuid4.return_value.hex = "partial"
            expected_path = streamlit_runner.CONFIG_PATH.parent / ".ui_account_profile_partial.yaml"
            with self.assertRaises(OSError):
                streamlit_runner._write_local_account_profile(profile)

        self.assertFalse(expected_path.exists())

    def test_combined_runner_starts_local_and_remote_concurrently(self) -> None:
        log_queue: queue.Queue = queue.Queue()
        barrier = threading.Barrier(2, timeout=3)
        started: list[str] = []

        def local_side_effect(*_args, **_kwargs) -> int:
            started.append("local")
            barrier.wait()
            return 0

        def remote_side_effect(*_args, **_kwargs) -> int:
            started.append("remote")
            barrier.wait()
            return 0

        with (
            patch("streamlit_runner._run_selected_tests_unlocked", side_effect=local_side_effect),
            patch("streamlit_runner._run_remote_cli_unlocked", side_effect=remote_side_effect),
        ):
            streamlit_runner.run_local_and_remote(
                ["tests.p0.sample.TestSample.test_one"],
                log_queue,
                local_attach_existing_app=True,
                local_account_profile=runtime_account_profile(_sample_group("Windows", "1")),
                remote_host_name="macos-arm64",
                remote_attach_existing_app=False,
                remote_collect_artifacts=False,
                remote_sync_before_run=False,
                remote_ssh_host="127.0.0.1",
                remote_ssh_port=22,
                remote_ssh_username="tester",
                remote_ssh_password="",
                remote_account_profile=runtime_account_profile(_sample_group("macOS", "2")),
            )

        self.assertCountEqual(started, ["local", "remote"])
        self.assertFalse(streamlit_runner.ui_task_status()["locked"])


if __name__ == "__main__":
    unittest.main()
