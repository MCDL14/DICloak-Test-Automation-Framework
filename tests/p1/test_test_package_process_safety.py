from __future__ import annotations

import copy
import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import psutil

from core.app import (
    AppManager,
    AppStartupError,
    _listener_pids,
    assert_test_app_cdp_target,
    wait_for_test_app_cdp_target,
)
from core.precheck import EnvironmentPrechecker, PrecheckResult
from core.cdp_driver import CDPConnectionError, CDPDriver
from core.runner import AutomationRunner, ExitCode


class _Process:
    def __init__(self, pid: int, exe: Path | None, *, name: str = "DICloak.exe", status: str = "running"):
        self.pid = pid
        self.path = exe
        self.info = {"pid": pid, "exe": str(exe) if exe else None, "name": name, "status": status}
        self.actions: list[str] = []
        self.descendants: list[_Process] = []

    def exe(self):
        if self.path is None:
            raise psutil.AccessDenied(self.pid)
        return str(self.path)

    def children(self, *, recursive: bool):
        return self.descendants

    def terminate(self):
        self.actions.append("terminate")

    def kill(self):
        self.actions.append("kill")


def _connection(port: int, *, pid: int | None = 123, status: str = "LISTEN"):
    return SimpleNamespace(laddr=("127.0.0.1", port), pid=pid, status=status)


class TestTestPackageProcessSafety(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="dicloak-package-process-test-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.test_exe = self.root / "test-package" / "DICloak.exe"
        self.prod_exe = self.root / "production" / "DICloak.exe"
        self.test_exe.parent.mkdir()
        self.test_exe.touch()
        self.prod_exe.parent.mkdir()
        self.prod_exe.touch()
        self.config = {
            "_app_package_kind": "test",
            "app": {
                "exe_path": str(self.test_exe), "work_dir": str(self.test_exe.parent),
                "process_name": "DICloak.exe", "isolation": "executable_path",
                "startup_args": [], "cdp_auth": {"enabled": False},
            },
            "cdp": {"host": "127.0.0.1", "port": 9223, "connect_timeout": 1},
            "run": {"precheck_before_run": False},
            "feishu": {"enabled": False},
        }
        self.logger = mock.MagicMock(spec=logging.Logger)

    def test_production_process_detection_preserves_name_based_behavior(self):
        config = copy.deepcopy(self.config)
        config.pop("_app_package_kind")
        config["app"].pop("isolation")
        with mock.patch("core.app.is_process_running", return_value=True) as detection:
            self.assertTrue(AppManager(config, self.logger).is_running())
        detection.assert_called_once_with("DICloak.exe")

    def test_same_name_production_process_does_not_count_as_test_package(self):
        production = _Process(11, self.prod_exe)
        with mock.patch("core.app.psutil.process_iter", return_value=[production]):
            self.assertFalse(AppManager(self.config, self.logger).is_running())

    def test_exact_executable_matches_and_zombie_is_not_running(self):
        test = _Process(12, self.test_exe)
        zombie = _Process(13, self.test_exe, status=psutil.STATUS_ZOMBIE)
        with mock.patch("core.app.psutil.process_iter", return_value=[test]):
            self.assertTrue(AppManager(self.config, self.logger).is_running())
        with mock.patch("core.app.psutil.process_iter", return_value=[zombie]):
            self.assertFalse(AppManager(self.config, self.logger).is_running())

    def test_close_uses_exact_target_pid_and_children_never_taskkill_image_name(self):
        production = _Process(11, self.prod_exe)
        test = _Process(12, self.test_exe)
        child = _Process(13, self.test_exe)
        test.descendants = [child]
        with (
            mock.patch("core.app.psutil.process_iter", return_value=[production, test]),
            mock.patch("core.app.psutil.wait_procs", return_value=([test, child], [])),
            mock.patch("core.app.subprocess.run") as command,
        ):
            AppManager(self.config, self.logger).close()
        self.assertEqual(production.actions, [])
        self.assertEqual(test.actions, ["terminate"])
        self.assertEqual(child.actions, ["terminate"])
        command.assert_not_called()

    def test_unknown_same_named_process_is_not_terminated_or_name_fallback(self):
        unknown = _Process(11, None)
        with (
            mock.patch("core.app.psutil.process_iter", return_value=[unknown]),
            mock.patch("core.app.subprocess.run") as command,
        ):
            with self.assertRaisesRegex(AppStartupError, "无法确认同名"):
                AppManager(self.config, self.logger).close()
        self.assertEqual(unknown.actions, [])
        command.assert_not_called()

    def test_close_rechecks_process_executable_before_signalling(self):
        replaced = _Process(12, self.prod_exe)
        with mock.patch("core.app._matching_test_processes", return_value=[replaced]):
            AppManager(self.config, self.logger).close()
        self.assertEqual(replaced.actions, [])

    def test_free_local_port_is_safe_without_process_enumeration(self):
        with (
            mock.patch("core.app._test_cdp_port_listening", return_value=False),
            mock.patch("core.app._listener_pids") as owners,
        ):
            assert_test_app_cdp_target(self.config)
        owners.assert_not_called()

    def test_listener_of_exact_test_executable_can_be_reused(self):
        with (
            mock.patch("core.app._listener_pids", return_value={12}),
            mock.patch("core.app.psutil.Process", return_value=_Process(12, self.test_exe)),
        ):
            assert_test_app_cdp_target(self.config, listening=True)

    def test_production_or_other_listener_is_rejected(self):
        with (
            mock.patch("core.app._listener_pids", return_value={11}),
            mock.patch("core.app.psutil.Process", return_value=_Process(11, self.prod_exe)),
        ):
            with self.assertRaisesRegex(AppStartupError, "其他程序或生产"):
                assert_test_app_cdp_target(self.config, listening=True)

    def test_unknown_listener_owner_is_rejected(self):
        with mock.patch("core.app._listener_pids", return_value=None):
            with self.assertRaisesRegex(AppStartupError, "无法确认监听进程"):
                assert_test_app_cdp_target(self.config, listening=True)

    def test_access_denied_listener_executable_is_rejected(self):
        with (
            mock.patch("core.app._listener_pids", return_value={12}),
            mock.patch("core.app.psutil.Process", side_effect=psutil.AccessDenied(12)),
        ):
            with self.assertRaisesRegex(AppStartupError, "无法读取"):
                assert_test_app_cdp_target(self.config, listening=True)

    def test_every_listener_owner_must_match_not_only_the_first(self):
        processes = {12: _Process(12, self.test_exe), 13: _Process(13, self.prod_exe)}
        with (
            mock.patch("core.app._listener_pids", return_value={12, 13}),
            mock.patch("core.app.psutil.Process", side_effect=processes.__getitem__),
        ):
            with self.assertRaises(AppStartupError):
                assert_test_app_cdp_target(self.config, listening=True)

    def test_nonlocal_host_and_empty_or_relative_path_fail_closed(self):
        for update in ({"host": "192.0.2.12"}, {"port": 0}, {"port": True}):
            with self.subTest(update=update):
                cfg = copy.deepcopy(self.config)
                cfg["cdp"].update(update)
                with self.assertRaises(AppStartupError):
                    assert_test_app_cdp_target(cfg, listening=False)
        for path in ("", "relative/DICloak.exe"):
            cfg = copy.deepcopy(self.config)
            cfg["app"]["exe_path"] = path
            with self.assertRaises(AppStartupError):
                assert_test_app_cdp_target(cfg, listening=False)

    def test_attach_requires_actual_listener(self):
        with mock.patch("core.app._test_cdp_port_listening", return_value=False):
            with self.assertRaisesRegex(AppStartupError, "端口未监听"):
                assert_test_app_cdp_target(self.config, require_listening=True)

    def test_listener_pid_table_is_read_only_and_unknown_pid_is_rejected(self):
        with mock.patch("core.app.psutil.net_connections", return_value=[_connection(9223, pid=12), _connection(9222, pid=11)]):
            self.assertEqual(_listener_pids(9223), {12})
        with mock.patch("core.app.psutil.net_connections", return_value=[_connection(9223, pid=None)]):
            self.assertIsNone(_listener_pids(9223))

    def test_per_process_connection_fallback_supports_macos_without_global_table_access(self):
        process = _Process(12, self.test_exe)
        process.net_connections = mock.Mock(return_value=[_connection(9223)])
        with (
            mock.patch("core.app.psutil.net_connections", side_effect=psutil.AccessDenied()),
            mock.patch("core.app.psutil.process_iter", return_value=[process]),
        ):
            self.assertEqual(_listener_pids(9223), {12})
        process.net_connections.assert_called_once_with(kind="tcp")

    def test_inaccessible_connection_fallback_stays_unknown(self):
        process = _Process(12, self.test_exe)
        process.net_connections = mock.Mock(side_effect=psutil.AccessDenied())
        with (
            mock.patch("core.app.psutil.net_connections", side_effect=psutil.AccessDenied()),
            mock.patch("core.app.psutil.process_iter", return_value=[process]),
            mock.patch("core.app.shutil.which", return_value=None),
        ):
            self.assertIsNone(_listener_pids(9223))

    def test_launch_guard_runs_before_signing_or_closing_existing_processes(self):
        manager = AppManager(self.config, self.logger)
        with (
            mock.patch("core.app.assert_test_app_cdp_target", side_effect=AppStartupError("foreign listener")),
            mock.patch("core.app.generate_app_cdp_token") as sign,
            mock.patch.object(manager, "close_existing_if_needed") as close,
            mock.patch("core.app.subprocess.Popen") as start,
        ):
            with self.assertRaises(AppStartupError):
                manager.launch_fresh(force_close_existing=True)
        sign.assert_not_called()
        close.assert_not_called()
        start.assert_not_called()

    def test_prepared_launch_rechecks_listener_before_popen(self):
        with (
            mock.patch("core.app.assert_test_app_cdp_target", side_effect=AppStartupError("foreign listener")),
            mock.patch("core.app.subprocess.Popen") as start,
        ):
            with self.assertRaises(AppStartupError):
                AppManager(self.config, self.logger)._start_prepared(self.test_exe.parent, [str(self.test_exe)])
        start.assert_not_called()

    def test_managed_test_launch_requires_enabled_credential_signing(self):
        self.config["app"]["startup_args"] = ["--remote-debugging-port=9222"]
        manager = AppManager(self.config, self.logger)
        with (
            mock.patch("core.app.assert_test_app_cdp_target"),
            mock.patch("core.app.generate_app_cdp_token") as sign,
            mock.patch.object(manager, "close_existing_if_needed") as close,
            mock.patch("core.app.subprocess.Popen") as start,
        ):
            with self.assertRaisesRegex(AppStartupError, "必须开启 CDP 凭证"):
                manager.launch_fresh()
        sign.assert_not_called()
        close.assert_not_called()
        start.assert_not_called()

    def test_managed_test_precheck_rejects_disabled_signing_before_script_validation(self):
        result = PrecheckResult()
        with (
            mock.patch("core.precheck.assert_test_app_cdp_target"),
            mock.patch("core.precheck.validate_cdp_auth_setup") as credentials,
        ):
            EnvironmentPrechecker(self.config, self.logger)._check_app(result)
        self.assertFalse(result.passed)
        self.assertIn("必须开启 CDP 凭证", result.failed_items[0].message)
        credentials.assert_not_called()

    def test_precheck_attach_checks_test_path_and_identity_but_does_not_sign(self):
        result = PrecheckResult()
        with (
            mock.patch("core.precheck.assert_test_app_cdp_target") as check,
            mock.patch("core.precheck.validate_cdp_auth_setup") as credentials,
        ):
            EnvironmentPrechecker(self.config, self.logger)._check_app(result, attach_existing_app=True)
        self.assertTrue(result.passed)
        self.assertIn("APP exe_path exists", [item.name for item in result.items])
        check.assert_called_once_with(self.config, require_listening=True)
        credentials.assert_not_called()

    def test_precheck_rejects_wrong_test_listener_even_with_attach(self):
        result = PrecheckResult()
        with mock.patch("core.precheck.assert_test_app_cdp_target", side_effect=AppStartupError("wrong target")):
            EnvironmentPrechecker(self.config, self.logger)._check_app(result, attach_existing_app=True)
        self.assertFalse(result.passed)
        self.assertEqual(result.failed_items[0].name, "Test APP CDP target identity")

    def test_runner_rejects_target_guard_failure_without_starting_app_or_connecting(self):
        for attach in (True, False):
            with (
                self.subTest(attach=attach),
                mock.patch("core.runner.assert_test_app_cdp_target", side_effect=AppStartupError("wrong target")),
                mock.patch("core.runner.is_cdp_port_open", return_value=True),
                mock.patch("core.runner.AppManager") as app,
                mock.patch("core.runner.CDPDriver") as driver,
            ):
                result = AutomationRunner(self.config, self.logger).run(attach_existing_app=attach)
                self.assertEqual(result, ExitCode.APP_OR_CDP_ERROR)
                app.assert_not_called()
                driver.assert_not_called()

    def test_precheck_only_reports_guard_failure_as_precheck_error(self):
        with mock.patch("core.runner.assert_test_app_cdp_target", side_effect=AppStartupError("wrong target")):
            result = AutomationRunner(self.config, self.logger).run_precheck_only()
        self.assertEqual(result, ExitCode.CONFIG_OR_PRECHECK_ERROR)

    def test_wait_for_listener_confirms_identity_before_returning(self):
        with (
            mock.patch("core.app._test_cdp_port_listening", side_effect=[False, True]),
            mock.patch("core.app.assert_test_app_cdp_target") as guard,
            mock.patch("core.app.time.sleep"),
        ):
            wait_for_test_app_cdp_target(self.config)
        self.assertEqual([call.kwargs["listening"] for call in guard.call_args_list], [False, True])

    def test_wait_timeout_does_not_connect_to_an_unconfirmed_port(self):
        self.config["cdp"]["connect_timeout"] = 0
        with mock.patch("core.app._test_cdp_port_listening", return_value=False):
            with self.assertRaisesRegex(AppStartupError, "独立 CDP 端口超时"):
                wait_for_test_app_cdp_target(self.config)

    def test_public_and_direct_cdp_connect_reject_wrong_target_before_transport(self):
        for method_name in ("connect", "connect_playwright", "connect_websocket", "list_targets"):
            with self.subTest(method=method_name):
                driver = CDPDriver(self.config, self.logger)
                with (
                    mock.patch("core.app.assert_test_app_cdp_target", side_effect=AppStartupError("wrong listener")) as guard,
                    mock.patch("core.cdp_driver.urllib.request.urlopen") as http,
                    mock.patch("core.cdp_driver.CDPDriver._disconnect_unverified_target") as disconnect,
                ):
                    with self.assertRaisesRegex(CDPConnectionError, "wrong listener"):
                        getattr(driver, method_name)()
                guard.assert_called_once_with(self.config, require_listening=True)
                http.assert_not_called()
                disconnect.assert_called_once()

    def _fake_playwright(self):
        page = mock.MagicMock()
        context = SimpleNamespace(pages=[page])
        browser = mock.MagicMock()
        browser.contexts = [context]
        playwright = mock.MagicMock()
        playwright.chromium.connect_over_cdp.return_value = browser
        sync_api = types.ModuleType("playwright.sync_api")
        sync_api.sync_playwright = mock.Mock(return_value=SimpleNamespace(start=lambda: playwright))
        module = types.ModuleType("playwright")
        module.sync_api = sync_api
        return {"playwright": module, "playwright.sync_api": sync_api}, playwright, browser, page

    def test_direct_playwright_connect_checks_identity_before_and_after_attach(self):
        modules, playwright, browser, page = self._fake_playwright()
        driver = CDPDriver(self.config, self.logger)
        with (
            mock.patch.dict(sys.modules, modules),
            mock.patch("core.app.assert_test_app_cdp_target") as guard,
            mock.patch.object(driver, "_select_default_page", return_value=page),
        ):
            driver.connect_playwright()
        self.assertGreaterEqual(guard.call_count, 3)
        playwright.chromium.connect_over_cdp.assert_called_once()
        self.assertIs(driver.page, page)
        browser.new_context.assert_not_called()

    def test_identity_change_during_playwright_attach_disconnects_without_closing_unknown_browser(self):
        modules, playwright, browser, _page = self._fake_playwright()
        driver = CDPDriver(self.config, self.logger)
        with (
            mock.patch.dict(sys.modules, modules),
            mock.patch("core.app.assert_test_app_cdp_target", side_effect=[None, None, AppStartupError("identity changed")]),
        ):
            with self.assertRaisesRegex(CDPConnectionError, "identity changed"):
                driver.connect_playwright()
        self.assertIsNone(driver.browser)
        self.assertIsNone(driver.page)
        playwright.stop.assert_called_once()
        browser.close.assert_not_called()
        browser.new_context.assert_not_called()

    def test_direct_websocket_connect_checks_identity_and_only_disconnects_if_it_changes(self):
        websocket = types.ModuleType("websocket")
        connection = mock.Mock()
        websocket.create_connection = mock.Mock(return_value=connection)
        driver = CDPDriver(self.config, self.logger)
        target = SimpleNamespace(websocket_url="ws://127.0.0.1:9223/devtools/page/test-only")
        with (
            mock.patch.dict(sys.modules, {"websocket": websocket}),
            mock.patch.object(driver, "list_targets", return_value=[target]),
            mock.patch("core.app.assert_test_app_cdp_target", side_effect=[None, None, AppStartupError("identity changed")]),
        ):
            with self.assertRaisesRegex(CDPConnectionError, "identity changed"):
                driver.connect_websocket()
        connection.close.assert_called_once()
        self.assertIsNone(driver.websocket)

    def test_production_cdp_connection_does_not_probe_process_identity(self):
        config = copy.deepcopy(self.config)
        config.pop("_app_package_kind")
        config["app"].pop("isolation")
        driver = CDPDriver(config, self.logger)
        with (
            mock.patch.object(driver, "connect_playwright") as connect,
            mock.patch("core.app.assert_test_app_cdp_target") as guard,
        ):
            driver.connect()
        connect.assert_called_once()
        guard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
