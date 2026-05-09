from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.kernel_cdp import open_kernel_url_and_read_page, verify_bilibili_password_eye_blocked
from core.kernel_process import resolve_kernel_runtime
from core.logger import setup_logger
from core.process import wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.global_settings_page import GlobalSettingsPage
from pages.login_page import LoginPage


CASE_MODULE = "全局设置"

ENVIRONMENT_SEARCH_KEYWORD = "142"
BLOCKED_URL = "chrome://password-manager/"
EXPECTED_BLOCK_TEXT = "ERR_BLOCKED_BY_CLIENT"
BILIBILI_URL = "https://www.bilibili.com"
BILIBILI_PASSWORD = "12345678"


class TestDisableViewPassword(unittest.TestCase):
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

    def test_disable_view_password_blocks_password_manager(self) -> None:
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        environment_name = ""
        kernel_pid = 0
        environment_opened = False

        try:
            global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
            global_settings_page.open()
            global_settings_page.ensure_disable_view_password_enabled()

            environment_page.open_list()
            environment_page.search_environment(ENVIRONMENT_SEARCH_KEYWORD)
            environment_name = environment_page.first_environment_name()
            assert_true(
                bool(environment_name),
                f"environment was not found by keyword: {ENVIRONMENT_SEARCH_KEYWORD}",
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
            blocked_page = open_kernel_url_and_read_page(
                kernel_runtime.cdp_port,
                BLOCKED_URL,
                timeout_seconds=20,
                http_timeout_seconds=http_probe_timeout,
            )
            evidence = "\n".join(
                [
                    blocked_page.error_text,
                    blocked_page.title,
                    blocked_page.target_url,
                    blocked_page.text,
                ]
            )
            assert_true(
                EXPECTED_BLOCK_TEXT in evidence,
                "password manager page was not blocked as expected: "
                f"url={BLOCKED_URL}, target_url={blocked_page.target_url}, "
                f"title={blocked_page.title}, error={blocked_page.error_text}",
            )

            password_eye = verify_bilibili_password_eye_blocked(
                kernel_runtime.cdp_port,
                password=BILIBILI_PASSWORD,
                url=BILIBILI_URL,
                timeout_seconds=45,
                http_timeout_seconds=http_probe_timeout,
            )
            assert_true(
                password_eye.password_value == BILIBILI_PASSWORD,
                f"bilibili password input was not filled correctly: {password_eye.evidence}",
            )
            assert_true(
                bool(password_eye.eye_click_target),
                f"bilibili password eye button was not clicked: {password_eye.evidence}",
            )
            assert_true(
                not password_eye.password_visible,
                "bilibili password became visible after clicking eye button: "
                f"type={password_eye.password_input_type}, "
                f"text_security={password_eye.password_text_security}, "
                f"target_url={password_eye.target_url}, evidence={password_eye.evidence}",
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
