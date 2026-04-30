from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.kernel_process import (
    close_kernel_target_by_url,
    resolve_kernel_runtime,
    wait_kernel_target_url,
)
from core.logger import setup_logger
from core.process import wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestEditFixedOpenUrl(unittest.TestCase):
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

    def test_edit_fixed_open_url_and_clear(self) -> None:
        data = self.config["test_data"]["environment_edit_fixed_open_url"]
        environment_name = str(data.get("environment_name", "自动化编辑打开网址"))
        fixed_url = str(data.get("fixed_url", "https://bilibili.com"))
        url_keyword = str(data.get("url_keyword", "bilibili.com"))

        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        fixed_url_set = False
        environment_opened = False
        kernel_pid = 0

        try:
            environment_page.open_list()
            environment_page.search_environment(environment_name)
            assert_true(
                environment_page.environment_visible_in_current_list(environment_name),
                f"preset environment was not found: {environment_name}",
            )
            self._close_environment_if_open(
                environment_page,
                environment_name,
                timeout_seconds=environment_close_timeout,
            )

            environment_page.edit_environment_fixed_open_url(environment_name, fixed_url)
            fixed_url_set = True

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
            assert_true(
                wait_kernel_target_url(
                    kernel_runtime.cdp_port,
                    url_keyword,
                    expected_present=True,
                    timeout_seconds=30,
                    http_timeout_seconds=http_probe_timeout,
                ),
                f"fixed URL tab did not open automatically: keyword={url_keyword}",
            )
            assert_true(
                close_kernel_target_by_url(
                    kernel_runtime.cdp_port,
                    url_keyword,
                    timeout_seconds=http_probe_timeout,
                ),
                f"fixed URL tab was not closed: keyword={url_keyword}",
            )
            assert_true(
                wait_kernel_target_url(
                    kernel_runtime.cdp_port,
                    url_keyword,
                    expected_present=False,
                    timeout_seconds=15,
                    http_timeout_seconds=http_probe_timeout,
                ),
                f"fixed URL tab still exists after close: keyword={url_keyword}",
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

            environment_page.edit_environment_fixed_open_url(environment_name, "")
            fixed_url_set = False

            kernel_pid = environment_page.open_environment_and_capture_pid(environment_name)
            environment_opened = True
            assert_true(
                wait_for_pid_running(kernel_pid, timeout_seconds=kernel_process_timeout),
                f"kernel process did not start after clearing fixed URL: pid={kernel_pid}",
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
            assert_true(
                wait_kernel_target_url(
                    kernel_runtime.cdp_port,
                    url_keyword,
                    expected_present=False,
                    timeout_seconds=12,
                    http_timeout_seconds=http_probe_timeout,
                    stable_absence_seconds=5,
                ),
                f"fixed URL tab should not open after clearing config: keyword={url_keyword}",
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
            assert_equal(
                environment_page.environment_action_text(environment_name),
                "打开",
                f"environment action text was not restored to open: {environment_name}",
            )
        finally:
            try:
                if environment_opened:
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
                if fixed_url_set:
                    environment_page.edit_environment_fixed_open_url(environment_name, "")
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
