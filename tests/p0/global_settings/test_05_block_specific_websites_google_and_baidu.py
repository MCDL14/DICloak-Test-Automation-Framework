from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.kernel_cdp import verify_kernel_website_blocklist_rules
from core.kernel_process import resolve_kernel_runtime
from core.local_http import LocalHttpProbe
from core.logger import setup_logger
from core.process import wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.global_settings_page import GlobalSettingsPage
from pages.login_page import LoginPage


CASE_MODULE = "全局设置"

ENVIRONMENT_SEARCH_KEYWORD = "142"
BLOCKED_URLS = [
    "https://baidu.com",
    "https://chromewebstore.google.com",
]
EXPECTED_BLOCK_TEXT = "ERR_BLOCKED_BY_CLIENT"


class TestBlockSpecificWebsitesGoogleAndBaidu(unittest.TestCase):
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

    def test_block_specific_websites_google_shortcut_and_baidu(self) -> None:
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
        cleanup_error: Exception | None = None

        try:
            with LocalHttpProbe() as allowed_probe:
                global_settings_page.open()
                global_settings_page.validate_website_restriction_controls_without_saving(
                    test_url="https://baidu.com",
                    shortcut_name="谷歌应用商店",
                )
                global_settings_page.configure_website_restriction_blocklist(
                    urls=["https://baidu.com"],
                    shortcut_name="谷歌应用商店",
                )

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
                result = verify_kernel_website_blocklist_rules(
                    kernel_runtime.cdp_port,
                    blocked_urls=BLOCKED_URLS,
                    allowed_url=allowed_probe.url,
                    expected_block_text=EXPECTED_BLOCK_TEXT,
                    timeout_seconds=60,
                    http_timeout_seconds=http_probe_timeout,
                )
                for check in result.checks[: len(BLOCKED_URLS)]:
                    assert_true(
                        check.blocked,
                        "url was not blocked as expected: "
                        f"requested_url={check.requested_url}, target_url={check.target_url}, "
                        f"title={check.title}, error={check.error_text}, evidence={check.evidence[:1000]}",
                    )
                allowed_check = result.checks[-1]
                assert_true(
                    allowed_check.loaded and not allowed_check.blocked,
                    "allowed url was not loaded as expected under blocklist: "
                    f"requested_url={allowed_check.requested_url}, target_url={allowed_check.target_url}, "
                    f"title={allowed_check.title}, error={allowed_check.error_text}, "
                    f"evidence={allowed_check.evidence[:1000]}",
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
                global_settings_page.disable_website_restriction()
                global_settings_page.open()
                global_settings_page._wait_global_setting_states_stable()
                assert_true(
                    not global_settings_page.website_restriction_enabled(),
                    "访问网站限制功能开关在用例清理后仍未关闭",
                )
            except Exception as exc:
                cleanup_error = exc
            try:
                environment_page.open_list()
            except Exception:
                pass
            if cleanup_error:
                raise cleanup_error

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
