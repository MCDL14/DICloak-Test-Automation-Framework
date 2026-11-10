from __future__ import annotations

import copy
import io
import os
import queue
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import streamlit as st
from streamlit.testing.v1 import AppTest

from core.account_groups import (
    ACCOUNT_PROFILE_ENV,
    apply_runtime_account_profile,
    default_account_groups,
    load_account_groups,
    load_runtime_account_profile,
    runtime_account_profile,
    save_account_groups,
)
from core.app_packages import APP_PROFILE_ENV, default_test_package_settings
from core.config import DEFAULT_CONFIG


ROOT = Path(__file__).resolve().parents[2]
CASE_ID = "tests.p0.fake.TestFake.test_example"
CASE = {"id": CASE_ID, "module": "环境管理", "class_name": "TestFake",
        "method_name": "test_example", "display_name": "隔离测试用例"}


def _group(name: str, suffix: str) -> dict:
    return {
        "name": name,
        "automation_account": {"username": f"test-{suffix}@example.invalid", "password": f"fake-password-{suffix}",
                               "team_name": f"team-{suffix}", "member_id": f"id-{suffix}"},
        "case_external_member": {"name": f"member-{suffix}", "email": f"member-{suffix}@example.invalid"},
        "internal_member": {"username": f"internal-{suffix}", "password": f"fake-internal-{suffix}", "member_id": f"internal-id-{suffix}"},
        "member_api_token": f"fake-token-{suffix}", "http_api_key": f"fake-http-key-{suffix}",
    }


class TestPackageAccountIsolationTests(unittest.TestCase):
    def test_ui_base_config_and_cancel_ignore_inherited_expired_profiles(self) -> None:
        import yaml
        import streamlit_runner
        from core.config import ConfigError, load_config
        from core.app_packages import APP_PROFILE_ENV
        from core.account_groups import ACCOUNT_PROFILE_ENV

        with tempfile.TemporaryDirectory(prefix="test-package-base-") as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(yaml.safe_dump(DEFAULT_CONFIG), encoding="utf-8")
            with (
                mock.patch.dict(os.environ, {
                    APP_PROFILE_ENV: str(Path(directory) / "expired-app.yaml"),
                    ACCOUNT_PROFILE_ENV: str(Path(directory) / "expired-account.yaml"),
                }),
                mock.patch("streamlit_runner.CONFIG_PATH", path),
                mock.patch("streamlit_runner.AppManager") as manager,
            ):
                with self.assertRaises(ConfigError):
                    load_config(path)
                clean = load_config(path, ignore_runtime_profiles=True)
                self.assertNotIn("_app_package_kind", clean)
                streamlit_runner._close_managed_app_after_cancel(queue.Queue())
                effective = manager.call_args.args[0]
                self.assertNotIn("_app_package_kind", effective)
                manager.return_value.close.assert_called_once()
                self.assertTrue(os.environ[APP_PROFILE_ENV].endswith("expired-app.yaml"))

    def test_ui_child_environment_does_not_inherit_stale_package_or_account_profile(self) -> None:
        import streamlit_runner

        class ImmediateReader:
            def __init__(self, *, target, **_kwargs):
                self.target = target

            def start(self):
                self.target()

            def join(self, **_kwargs):
                return None

        process = mock.MagicMock()
        process.stdout = io.StringIO("")
        process.poll.return_value = 0
        process.returncode = 0
        stopped = threading.Event()
        with (
            mock.patch.dict(os.environ, {APP_PROFILE_ENV: "C:/stale-app.yaml", ACCOUNT_PROFILE_ENV: "C:/stale-account.yaml"}),
            mock.patch("streamlit_runner.subprocess.Popen", return_value=process) as popen,
            mock.patch("streamlit_runner.threading.Thread", ImmediateReader),
            mock.patch("streamlit_runner._set_cancel_callback"),
        ):
            result = streamlit_runner._run_streaming_subprocess(["python", "run.py"], queue.Queue(), stopped, cwd=ROOT)
            child_environment = popen.call_args.kwargs["env"]
            self.assertNotIn(APP_PROFILE_ENV, child_environment)
            self.assertNotIn(ACCOUNT_PROFILE_ENV, child_environment)
            self.assertEqual(child_environment["PYTHONIOENCODING"], "utf-8")
            self.assertEqual(os.environ[APP_PROFILE_ENV], "C:/stale-app.yaml")
            self.assertEqual(os.environ[ACCOUNT_PROFILE_ENV], "C:/stale-account.yaml")
        self.assertEqual(result, 0)

    def test_missing_test_group_file_never_migrates_production_defaults(self) -> None:
        base = copy.deepcopy(DEFAULT_CONFIG)
        base["account"].update(username="production-only", password="production-only-password", http_api_key="production-only-key")
        with tempfile.TemporaryDirectory(prefix="test-package-account-") as directory:
            groups = load_account_groups(Path(directory) / "missing.yaml", base_config=base, package_kind="test")
        for group in groups.values():
            self.assertTrue(all(value == "" for value in group["automation_account"].values()))
            self.assertEqual(group["case_external_member"], {"name": "", "email": ""})
            self.assertTrue(all(value == "" for value in group["internal_member"].values()))
            self.assertEqual(group["member_api_token"], "")
            self.assertEqual(group["http_api_key"], "")

    def test_test_account_file_and_runtime_marker_are_independent(self) -> None:
        import yaml

        production = {"group_1": _group("生产组1", "prod1"), "group_2": _group("生产组2", "prod2")}
        testing = {"group_1": _group("测试组1", "test1"), "group_2": _group("测试组2", "test2")}
        with tempfile.TemporaryDirectory(prefix="test-package-account-") as directory:
            production_path = Path(directory) / "account_groups.yaml"
            test_path = Path(directory) / "account_groups.test.yaml"
            save_account_groups(production_path, production)
            original = production_path.read_bytes()
            save_account_groups(test_path, testing, package_kind="test")
            loaded = load_account_groups(test_path, package_kind="test")
            profile = runtime_account_profile(loaded["group_1"], package_kind="test")
            profile_path = Path(directory) / "runtime.yaml"
            profile_path.write_text(yaml.safe_dump(profile), encoding="utf-8")
            round_trip = load_runtime_account_profile(profile_path)
            applied = apply_runtime_account_profile(DEFAULT_CONFIG, round_trip)
            self.assertEqual(production_path.read_bytes(), original)
        self.assertEqual(profile["package_kind"], "test")
        self.assertEqual(round_trip["package_kind"], "test")
        self.assertEqual(applied["_account_package_kind"], "test")
        self.assertEqual(applied["account"]["username"], testing["group_1"]["automation_account"]["username"])


class _CapturedExecutionThread:
    records: list = []

    def __init__(self, *, target, args=(), kwargs=None, **_options):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.started = False
        self.records.append(self)

    def start(self):
        self.started = True
        # Do not call the executor. Only simulate its completion protocol.
        messages = next(arg for arg in self.args if isinstance(arg, queue.Queue))
        messages.put(f"CASE START #1 {CASE_ID}")
        messages.put(f"CASE PASS #1 {CASE_ID} elapsed=0.01s")
        messages.put("Final test summary: total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0")
        messages.put(None)

    def is_alive(self):
        return False

    def join(self, *_args, **_kwargs):
        return None


class TestPackageUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)
        self.production = {"group_1": _group("生产组1", "prod1"), "group_2": _group("生产组2", "prod2")}
        self.testing = default_account_groups(package_kind="test")
        self.settings = default_test_package_settings()
        self.saved_accounts = []
        self.saved_settings = []
        self.progress_event = None
        _CapturedExecutionThread.records = []

        def load_groups(_path, *, base_config=None, package_kind="production"):
            return copy.deepcopy(self.testing if package_kind == "test" else self.production)

        def save_groups(path, groups, *, package_kind="production"):
            self.saved_accounts.append((Path(path), copy.deepcopy(groups), package_kind))
            if package_kind == "test":
                self.testing = copy.deepcopy(groups)
            else:
                self.production = copy.deepcopy(groups)

        def save_settings(path, settings):
            self.saved_settings.append((Path(path), copy.deepcopy(settings)))
            self.settings = copy.deepcopy(settings)

        self.stack.enter_context(mock.patch("core.config.load_config", side_effect=lambda *_args, **_kwargs: copy.deepcopy(DEFAULT_CONFIG)))
        self.stack.enter_context(mock.patch("core.account_groups.load_account_groups", side_effect=load_groups))
        self.stack.enter_context(mock.patch("core.account_groups.save_account_groups", side_effect=save_groups))
        self.stack.enter_context(mock.patch("core.app_packages.load_test_package_settings", side_effect=lambda *_args, **_kwargs: copy.deepcopy(self.settings)))
        self.stack.enter_context(mock.patch("core.app_packages.save_test_package_settings", side_effect=save_settings))
        self.stack.enter_context(mock.patch("streamlit_runner.discover_cases", return_value=[copy.deepcopy(CASE)]))
        hosts = [
            {"name": "fake-linux", "platform": "linux", "host": "linux.invalid", "port": "22", "username": "tester"},
            {"name": "fake-mac", "platform": "macos", "host": "mac.invalid", "port": "22", "username": "tester",
             "project_dir": "/Users/tester/project", "python": "python3", "config": "config/config.macos.yaml",
             "auth": "SSH key", "sync_enabled": "是", "venv_activate": ".venv/bin/activate"},
        ]
        self.stack.enter_context(mock.patch("streamlit_runner.discover_remote_hosts", return_value=hosts))
        self.stack.enter_context(mock.patch("streamlit_runner.load_remote_connection_cache", return_value={}))
        self.stack.enter_context(mock.patch("streamlit_runner.save_remote_connection_cache"))
        self.stack.enter_context(mock.patch("streamlit_runner.ui_task_status", return_value={"locked": False, "active": False, "thread_alive": False}))
        self.stack.enter_context(mock.patch("streamlit_runner.reset_stale_ui_task_lock"))
        self.stack.enter_context(mock.patch("streamlit_runner.remote_capability_matrix", return_value=[]))
        self.stack.enter_context(mock.patch("streamlit_runner.preview_remote_command", return_value="python3 run.py --precheck", autospec=True))
        self.stack.enter_context(mock.patch("ui.components.case_selector.render_case_selector", return_value=None))
        self.stack.enter_context(mock.patch("ui.components.case_progress.render_case_progress", side_effect=lambda **_kwargs: self.progress_event))

        original_exists = Path.exists

        def harmless_exists(path):
            if path.name in {"account_groups.yaml", "account_groups.test.yaml", "test_app_package.yaml"}:
                return True
            return original_exists(path)

        self.stack.enter_context(mock.patch.object(Path, "exists", harmless_exists))
        original_thread = threading.Thread
        executor_names = {"run_selected_tests", "run_remote_cli", "run_local_and_remote", "check_remote_host", "check_remote_code", "sync_remote_code"}

        class SelectiveThread(original_thread):
            def __new__(cls, *args, **kwargs):
                if getattr(kwargs.get("target"), "__name__", "") in executor_names:
                    return _CapturedExecutionThread(*args, **kwargs)
                return original_thread.__new__(cls)

        self.stack.enter_context(mock.patch("threading.Thread", SelectiveThread))

    def _page(self, name: str):
        app = AppTest.from_file(str(ROOT / "ui" / "pages" / name)).run(timeout=20)
        self._no_errors(app)
        return app

    def _no_errors(self, app):
        self.assertEqual([str(error.value) for error in app.exception], [])

    def _radio(self, app, label):
        return next(element for element in app.radio if element.label == label)

    def _button(self, app, label):
        return next(element for element in app.button if element.label == label)

    def _test_execution(self, *, valid_accounts=True, windows_path="C:/Disposable Test APP/DICloak.exe"):
        if valid_accounts:
            self.testing = {"group_1": _group("测试组1", "test1"), "group_2": _group("测试组2", "test2")}
        self.settings["windows_exe_path"] = windows_path
        app = self._page("01_执行用例.py")
        self._radio(app, "执行位置").set_value("测试 APP 包").run(timeout=20)
        self._no_errors(app)
        return app

    def _run_button(self, app):
        return next(element for element in app.button if element.label.startswith("[测试包]"))

    def test_account_scope_switch_has_empty_test_credentials_and_package_defaults(self) -> None:
        app = self._page("03_账号组.py")
        self.assertEqual(app.text_input(key="group_1_external_username").value, self.production["group_1"]["automation_account"]["username"])
        app.radio(key="account_package_scope").set_value("测试 APP 包").run(timeout=20)
        self._no_errors(app)
        self.assertEqual(app.text_input(key="test_package_group_1_external_username").value, "")
        self.assertEqual(app.text_input(key="test_package_group_1_external_password").value, "")
        self.assertEqual(app.text_input(key="test_package_group_1_case_external_name").value, "")
        self.assertEqual(app.text_input(key="test_package_windows_exe_path").value, "")
        self.assertEqual(app.text_input(key="test_package_api_base_url").value, "http://gin-server-test.dicloak.com")
        self.assertEqual(app.selectbox(key="test_package_macos_app_name").options, ["DICloak", "DICloak2"])
        self.assertEqual(app.number_input(key="test_package_cdp_port").value, 9223)

    def test_test_package_settings_save_does_not_save_accounts_or_production(self) -> None:
        app = self._page("03_账号组.py")
        app.radio(key="account_package_scope").set_value("测试 APP 包").run(timeout=20)
        app.text_input(key="test_package_windows_exe_path").input("C:/Disposable/DICloak.exe")
        app.text_input(key="test_package_api_base_url").input("http://alternate-test.example.invalid")
        app.selectbox(key="test_package_macos_app_name").select("DICloak")
        app.number_input(key="test_package_cdp_port").set_value(9333)
        self._button(app, "保存测试包运行配置").click().run(timeout=20)
        self._no_errors(app)
        path, settings = self.saved_settings[-1]
        self.assertEqual(path.name, "test_app_package.yaml")
        self.assertEqual(settings, {"windows_exe_path": "C:/Disposable/DICloak.exe", "api_base_url": "http://alternate-test.example.invalid", "macos_app_name": "DICloak", "cdp_port": 9333})
        self.assertEqual(self.saved_accounts, [])

    def test_test_account_save_target_and_return_to_production_are_isolated(self) -> None:
        original_production = copy.deepcopy(self.production)
        app = self._page("03_账号组.py")
        app.radio(key="account_package_scope").set_value("测试 APP 包").run(timeout=20)
        app.text_input(key="test_package_group_1_external_username").input("new-test@example.invalid")
        app.text_input(key="test_package_group_1_external_password").input("new-fake-password")
        app.text_input(key="test_package_group_1_http_api_key").input("new-fake-http-key")
        self._button(app, "保存两个账号组").click().run(timeout=20)
        self._no_errors(app)
        path, groups, kind = self.saved_accounts[-1]
        self.assertEqual(path.name, "account_groups.test.yaml")
        self.assertEqual(kind, "test")
        self.assertEqual(groups["group_1"]["automation_account"]["username"], "new-test@example.invalid")
        self.assertEqual(self.production, original_production)
        app.radio(key="account_package_scope").set_value("生产 APP 包").run(timeout=20)
        self._no_errors(app)
        self.assertEqual(app.text_input(key="group_1_external_username").value, original_production["group_1"]["automation_account"]["username"])
        self.assertEqual(app.text_input(key="group_1_http_api_key").value, original_production["group_1"]["http_api_key"])

    def test_windows_test_execution_disabled_without_explicit_path(self) -> None:
        app = self._test_execution(windows_path="")
        self.assertTrue(self._run_button(app).disabled)
        self.assertTrue(any("Windows 测试 APP 可执行文件路径" in str(error.value) for error in app.error))
        self.assertEqual(_CapturedExecutionThread.records, [])

    def test_test_execution_has_no_redundant_details_or_second_confirmation(self) -> None:
        app = self._test_execution()
        self.assertFalse(self._run_button(app).disabled)
        self.assertNotIn("我确认所选路径安装的是测试 APP 包", [element.label for element in app.checkbox])
        captions = [str(element.value) for element in app.caption]
        for prefix in ("Windows：", "Mac：", "测试 API：", "请求地址只控制框架业务 API"):
            self.assertFalse(any(text.startswith(prefix) for text in captions), prefix)
        self.assertTrue(any("当前仅执行测试 APP 包" in str(element.value) for element in app.warning))
        self.assertIsNotNone(self._button(app, "配置测试包及两组账号"))
        app.radio(key="test_package_execution_target").set_value("双端同步").run(timeout=20)
        self._no_errors(app)
        self.assertNotIn("我确认所选路径安装的是测试 APP 包", [element.label for element in app.checkbox])
        self.assertFalse(self._run_button(app).disabled)

    def test_windows_test_execution_disabled_with_empty_test_accounts(self) -> None:
        app = self._test_execution(valid_accounts=False)
        self.assertTrue(self._run_button(app).disabled)
        self.assertTrue(any("主账号" in str(error.value) for error in app.error))
        self.assertEqual(_CapturedExecutionThread.records, [])

    def test_all_test_targets_render_machine_specific_controls_and_mac_only_nodes(self) -> None:
        app = self._test_execution()
        self.assertEqual(app.radio(key="test_package_execution_target").options, ["Windows 本机", "Mac 远程", "双端同步"])
        self.assertFalse(self._run_button(app).disabled)
        app.radio(key="test_package_execution_target").set_value("Mac 远程").run(timeout=20)
        self._no_errors(app)
        node = next(element for element in app.selectbox if element.label == "远程节点")
        self.assertEqual(node.options, ["fake-mac (macos)"])
        self.assertIn("预检", self._run_button(app).label)
        app.radio(key="test_package_execution_target").set_value("双端同步").run(timeout=20)
        self._no_errors(app)
        self.assertEqual(app.selectbox(key="test_package_dual_local_group").label, "Windows 本机账号组")
        self.assertEqual(app.selectbox(key="test_package_dual_remote_group").label, "macOS 远程账号组")
        self.assertFalse(self._run_button(app).disabled)

    def test_windows_execution_captures_test_profile_without_starting_executor(self) -> None:
        app = self._test_execution()
        self._run_button(app).click().run(timeout=20)
        self._no_errors(app)
        thread = _CapturedExecutionThread.records[-1]
        self.assertEqual(thread.target.__name__, "run_selected_tests")
        self.assertEqual(thread.kwargs["app_profile"]["package_kind"], "test")
        self.assertEqual(thread.kwargs["app_profile"]["settings"], self.settings)
        self.assertEqual(thread.kwargs["account_profile"]["package_kind"], "test")
        self.assertEqual(app.session_state["execute_cases_last_result"]["execution_context"]["package_kind"], "test")

    def test_mac_execution_needs_no_second_confirmation_after_connection_target_changes(self) -> None:
        app = self._test_execution()
        app.radio(key="test_package_execution_target").set_value("Mac 远程").run(timeout=20)
        self._button(app, "执行用例").click().run(timeout=20)
        self._no_errors(app)
        self.assertFalse(self._run_button(app).disabled)
        self._button(app, "编辑连接").click().run(timeout=20)
        app.text_input(key="remote_connection_host_fake-mac_input").input("replacement-mac.invalid").run(timeout=20)
        self._no_errors(app)
        self.assertNotIn("我确认所选路径安装的是测试 APP 包", [element.label for element in app.checkbox])
        self.assertFalse(self._run_button(app).disabled)
        self._run_button(app).click().run(timeout=20)
        self._no_errors(app)
        thread = _CapturedExecutionThread.records[-1]
        self.assertEqual(thread.target.__name__, "run_remote_cli")
        self.assertEqual(thread.kwargs["ssh_host"], "replacement-mac.invalid")
        self.assertEqual(thread.kwargs["app_profile"]["package_kind"], "test")

    def test_dual_execution_freezes_both_profiles_and_distinct_test_groups(self) -> None:
        app = self._test_execution()
        app.radio(key="test_package_execution_target").set_value("双端同步").run(timeout=20)
        self._run_button(app).click().run(timeout=20)
        self._no_errors(app)
        thread = _CapturedExecutionThread.records[-1]
        self.assertEqual(thread.target.__name__, "run_local_and_remote")
        self.assertEqual(thread.kwargs["local_app_profile"]["settings"], self.settings)
        self.assertEqual(thread.kwargs["remote_app_profile"]["settings"], self.settings)
        self.assertNotEqual(thread.kwargs["local_account_profile"]["automation_account"]["team_name"], thread.kwargs["remote_account_profile"]["automation_account"]["team_name"])

    def test_mac_precheck_runs_without_windows_path_and_carries_test_profile(self) -> None:
        app = self._test_execution(valid_accounts=False, windows_path="")
        app.radio(key="test_package_execution_target").set_value("Mac 远程").run(timeout=20)
        self._no_errors(app)
        self.assertFalse(self._run_button(app).disabled)
        self._run_button(app).click().run(timeout=20)
        self._no_errors(app)
        thread = _CapturedExecutionThread.records[-1]
        self.assertEqual(thread.target.__name__, "run_remote_cli")
        self.assertEqual(thread.args[1], "precheck")
        self.assertIsNone(thread.kwargs["account_profile"])
        self.assertEqual(thread.kwargs["app_profile"]["settings"]["macos_app_name"], "DICloak2")

    def test_retry_after_switching_to_production_uses_original_test_snapshot(self) -> None:
        app = self._test_execution()
        self._run_button(app).click().run(timeout=20)
        self._no_errors(app)
        first_profile = copy.deepcopy(_CapturedExecutionThread.records[-1].kwargs["app_profile"])
        result = copy.deepcopy(app.session_state["execute_cases_last_result"])
        result["snapshot"]["rows"] = [{"状态码": "failed", "执行端": "本机", "原始用例": CASE_ID}]
        app.session_state["execute_cases_last_result"] = result
        self.settings["windows_exe_path"] = "C:/Changed Later/DICloak.exe"
        self.progress_event = {"event_id": "fake-test-retry", "scope": "case", "platform": "本机", "case_id": CASE_ID}
        self._radio(app, "执行位置").set_value("本机").run(timeout=20)
        self._no_errors(app)
        self.assertEqual(len(_CapturedExecutionThread.records), 2)
        retried = _CapturedExecutionThread.records[-1]
        self.assertEqual(retried.kwargs["app_profile"], first_profile)
        self.assertEqual(retried.kwargs["account_profile"]["package_kind"], "test")


if __name__ == "__main__":
    unittest.main()
