from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from core.assertions import assert_true
from core.app_config import resolve_app_config
from core.cdp_driver import CDPDriver
from core.config import load_config, require_value, timeout_seconds
from core.logger import setup_logger
from core.platform.detect import is_windows
from core.process import (
    is_process_running,
    main_process_ids,
    wait_for_pid_running,
    wait_for_pid_stopped,
    wait_for_process_running,
    wait_for_process_stopped,
)
from pages.environment_page import EnvironmentPage
from pages.global_settings_page import GlobalSettingsPage
from pages.login_page import LoginPage


CASE_MODULE = "全局设置"


@unittest.skipUnless(is_windows(), "packet capture blocking validation depends on Windows executable tools")
class TestDisablePacketCaptureSoftware(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(Path("config/config.yaml"))
        cls.logger = setup_logger(cls.config)
        cls.cdp = CDPDriver(cls.config, cls.logger)
        cls.cdp.connect()
        LoginPage(cdp_driver=cls.cdp, config=cls.config).ensure_logged_in_as_config_account()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cdp.close()

    def test_disable_packet_capture_software(self) -> None:
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        packet_process_timeout = timeout_seconds(self.config, "process_check_timeout", 30)

        packet_process_name = str(require_value(self.config, "test_data.packet_capture.process_name")).strip()
        packet_startup_path = self._resolve_project_path(
            str(require_value(self.config, "test_data.packet_capture.startup_path")).strip()
        )
        browser_process_name = resolve_app_config(self.config).browser_process_name.strip()

        assert_true(packet_startup_path.is_file(), f"packet capture startup path does not exist: {packet_startup_path}")
        assert_true(
            not is_process_running(packet_process_name),
            "packet capture process is already running before test; "
            f"please close it first to avoid unsafe cleanup: {packet_process_name}",
        )

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        environment_name = ""
        kernel_pid = 0
        environment_opened = False
        packet_process_started = False
        packet_process_ids: set[int] = set()
        cleanup_error: Exception | None = None

        try:
            global_settings_page.open()
            global_settings_page.configure_packet_capture_blocking(packet_process_name)

            packet_process_ids_before = set(main_process_ids(packet_process_name))
            subprocess.Popen([str(packet_startup_path)], cwd=str(packet_startup_path.parent))
            packet_process_started = True
            assert_true(
                wait_for_process_running(packet_process_name, timeout_seconds=packet_process_timeout),
                f"packet capture process did not start: {packet_process_name}, path={packet_startup_path}",
            )
            packet_process_ids = set(main_process_ids(packet_process_name)) - packet_process_ids_before

            environment_page.open_list()
            environment_name = environment_page.first_environment_name()
            assert_true(bool(environment_name), "first environment was not found")

            self._close_environment_if_open(
                environment_page,
                environment_name,
                timeout_seconds=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
            )

            kernel_pids_before_blocked_open = set(main_process_ids(browser_process_name))
            environment_page.click_environment_action(environment_name, "打开")
            environment_page.wait_for_forbidden_open_environment_dialog()
            kernel_pids_after_blocked_open = set(main_process_ids(browser_process_name))
            unexpected_kernel_pids = kernel_pids_after_blocked_open - kernel_pids_before_blocked_open
            assert_true(
                not unexpected_kernel_pids,
                "kernel process should not start when packet capture process is running: "
                f"new_pids={sorted(unexpected_kernel_pids)}, process={browser_process_name}",
            )
            assert_true(
                environment_page.environment_action_text(environment_name) == "打开",
                f"environment should remain closed after packet capture block: {environment_name}",
            )
            environment_page.close_forbidden_open_environment_dialog()

            self._terminate_packet_capture_process(
                packet_process_name,
                pids=packet_process_ids,
                timeout_seconds=packet_process_timeout,
            )
            packet_process_started = False

            kernel_pid = environment_page.open_environment_and_capture_pid(environment_name)
            environment_opened = True
            environment_page.wait_no_forbidden_open_environment_dialog(timeout_seconds=3)
            assert_true(
                wait_for_pid_running(kernel_pid, timeout_seconds=kernel_process_timeout),
                f"kernel process did not start after packet capture process closed: pid={kernel_pid}",
            )
            environment_page.wait_environment_action_text(
                environment_name,
                "关闭",
                timeout_seconds=environment_open_timeout,
            )

            self._close_environment_if_open(
                environment_page,
                environment_name,
                timeout_seconds=environment_close_timeout,
                kernel_pid=kernel_pid,
                kernel_process_timeout=kernel_process_timeout,
            )
            environment_opened = False
            kernel_pid = 0
            assert_true(
                environment_page.environment_action_text(environment_name) == "打开",
                f"environment action text was not restored to open: {environment_name}",
            )
        finally:
            try:
                if environment_opened and environment_name:
                    self._close_environment_if_open(
                        environment_page,
                        environment_name,
                        timeout_seconds=environment_close_timeout,
                        kernel_pid=kernel_pid,
                        kernel_process_timeout=kernel_process_timeout,
                    )
            except Exception:
                pass
            try:
                if packet_process_started:
                    self._terminate_packet_capture_process(
                        packet_process_name,
                        pids=packet_process_ids,
                        timeout_seconds=packet_process_timeout,
                    )
            except Exception as exc:
                cleanup_error = cleanup_error or exc
            try:
                global_settings_page.open()
                global_settings_page.disable_packet_capture_blocking()
                global_settings_page.open()
                global_settings_page._wait_global_setting_states_stable()
                assert_true(
                    not global_settings_page.packet_capture_blocking_enabled(),
                    "禁用抓包软件功能开关在用例清理后仍未关闭",
                )
            except Exception as exc:
                cleanup_error = cleanup_error or exc
            try:
                environment_page.open_list()
            except Exception:
                pass
            if cleanup_error:
                raise cleanup_error

    def _resolve_project_path(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path
        return Path(str(self.config.get("_project_root", Path.cwd()))).joinpath(path).resolve()

    def _terminate_packet_capture_process(
        self,
        process_name: str,
        pids: set[int],
        timeout_seconds: int,
    ) -> None:
        target_pids = set(pids) or set(main_process_ids(process_name))
        for pid in sorted(target_pids):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                text=True,
                encoding="mbcs",
                errors="ignore",
                timeout=10,
                check=False,
            )
        if not wait_for_process_stopped(process_name, timeout_seconds=timeout_seconds):
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", process_name],
                capture_output=True,
                text=True,
                encoding="mbcs",
                errors="ignore",
                timeout=10,
                check=False,
            )
        assert_true(
            wait_for_process_stopped(process_name, timeout_seconds=timeout_seconds),
            f"packet capture process did not stop: {process_name}",
        )

    def _close_environment_if_open(
        self,
        environment_page: EnvironmentPage,
        environment_name: str,
        timeout_seconds: int,
        kernel_pid: int = 0,
        kernel_process_timeout: int = 90,
    ) -> None:
        if not environment_name:
            return
        if not environment_page.environment_visible_in_current_list(environment_name):
            return
        if environment_page.environment_action_text(environment_name) != "关闭":
            return
        environment_page.click_environment_action(environment_name, "关闭")
        if kernel_pid:
            wait_for_pid_stopped(kernel_pid, timeout_seconds=kernel_process_timeout)
        environment_page.wait_environment_action_text(
            environment_name,
            "打开",
            timeout_seconds=timeout_seconds,
        )


if __name__ == "__main__":
    unittest.main()
