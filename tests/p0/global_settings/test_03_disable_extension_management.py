from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.kernel_cdp import verify_extension_management_and_install_blocked
from core.kernel_process import resolve_kernel_runtime
from core.logger import setup_logger
from core.process import wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.global_settings_page import GlobalSettingsPage
from pages.login_page import LoginPage


CASE_MODULE = "全局设置"

ENVIRONMENT_SEARCH_KEYWORD = "142"
EXTENSIONS_URL = "chrome://extensions/"
WEBSTORE_URL = (
    "https://chromewebstore.google.com/detail/ultimate-car-driving-game/"
    "aomkpefnllinimbhddlfhelelngakbbn?utm_source=ext_app_menu"
)
EXPECTED_INSTALL_ERROR = "下载时出错: Invalid manifest"


class TestDisableExtensionManagement(unittest.TestCase):
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

    def test_disable_extension_management_and_install(self) -> None:
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        environment_name = ""
        kernel_pid = 0
        environment_opened = False

        try:
            global_settings_page.open()
            global_settings_page.ensure_disable_extension_management_enabled()

            environment_page.open_list()
            environment_page.search_environment(ENVIRONMENT_SEARCH_KEYWORD)
            environment_name = environment_page.environment_name_at_position(2)
            assert_true(
                bool(environment_name),
                f"second environment was not found by keyword: {ENVIRONMENT_SEARCH_KEYWORD}",
            )

            self._close_environment_if_open(
                environment_page,
                environment_name,
                timeout_seconds=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
            )

            kernel_pid = environment_page.open_environment_and_capture_pid(environment_name)
            environment_opened = True
            assert_true(
                wait_for_pid_running(kernel_pid, timeout_seconds=kernel_process_timeout),
                f"kernel process did not start: pid={kernel_pid}",
            )
            environment_page.wait_environment_action_text(
                environment_name,
                "关闭",
                timeout_seconds=environment_open_timeout,
            )

            kernel_runtime = resolve_kernel_runtime(
                environment_name,
                kernel_pid,
                timeout_seconds=kernel_cdp_timeout,
                probe_timeout_seconds=kernel_cdp_probe_timeout,
                http_timeout_seconds=http_probe_timeout,
            )
            result = verify_extension_management_and_install_blocked(
                kernel_runtime.cdp_port,
                extensions_url=EXTENSIONS_URL,
                webstore_url=WEBSTORE_URL,
                expected_install_error=EXPECTED_INSTALL_ERROR,
                timeout_seconds=75,
                http_timeout_seconds=http_probe_timeout,
            )
            assert_true(
                result.extensions_blocked,
                "chrome extensions page was not blocked as expected: "
                f"url={result.extensions_target_url}, evidence={result.extensions_evidence}",
            )
            assert_true(
                result.install_button_clicked,
                f"chrome web store add button was not clicked: {result.evidence}",
            )
            assert_true(
                result.install_error_visible or result.webstore_switch_chrome_prompt_visible,
                "chrome web store install was not blocked or prevented after maximizing kernel window: "
                f"expected_error={EXPECTED_INSTALL_ERROR}, target_url={result.webstore_target_url}, "
                f"kernel_window_maximized={result.kernel_window_maximized}, "
                f"status_before={result.extension_status_before_click}, "
                f"status_after={result.extension_status_after_click}, "
                f"switch_chrome_prompt_visible={result.webstore_switch_chrome_prompt_visible}, "
                f"evidence={result.evidence}",
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
                environment_page.clear_search()
            except Exception:
                pass
            try:
                global_settings_page.open()
                global_settings_page.ensure_disable_extension_management_disabled()
            except Exception:
                pass
            try:
                environment_page.open_list()
            except Exception:
                pass

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
