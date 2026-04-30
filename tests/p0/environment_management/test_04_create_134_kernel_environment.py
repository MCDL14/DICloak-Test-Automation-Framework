from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.kernel_process import kernel_version_from_cdp, kernel_version_from_command_line, resolve_kernel_runtime
from core.logger import setup_logger
from core.process import wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestCreate134KernelEnvironment(unittest.TestCase):
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

    def test_create_open_verify_close_delete_134_kernel_environment(self) -> None:
        data = self.config["test_data"]["environment_create_134_kernel"]
        environment_name = str(data.get("environment_name", "自动化-创建134内核环境"))
        kernel_label = str(data.get("kernel_label", "ChromeBrowser 134"))
        expected_kernel_prefix = str(data.get("expected_kernel_prefix", "134"))
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        environment_created = False
        environment_opened = False
        kernel_pid = 0

        try:
            environment_page.open_list()
            environment_page.search_environment_without_assert(environment_name)
            if environment_page.environment_visible_in_current_list(environment_name):
                self._close_environment_if_open(
                    environment_page,
                    environment_name,
                    timeout_seconds=environment_close_timeout,
                )
                environment_page.delete_environment_from_current_list(environment_name)
                assert_true(
                    not environment_page.environment_visible_in_current_list(environment_name),
                    f"existing test environment was not cleaned before create: {environment_name}",
                )

            environment_page.create_environment_with_kernel(environment_name, kernel_label)
            environment_created = True
            environment_page.wait_environment_visible_in_current_list(environment_name)

            assert_equal(
                environment_page.environment_action_text(environment_name),
                "打开",
                f"created 134 kernel environment is not ready to open: {environment_name}",
            )
            kernel_pid = environment_page.open_environment_and_capture_pid(environment_name)
            assert_true(
                wait_for_pid_running(kernel_pid, timeout_seconds=kernel_process_timeout),
                f"kernel process did not start: pid={kernel_pid}",
            )
            environment_page.wait_environment_action_text(
                environment_name,
                "关闭",
                timeout_seconds=environment_open_timeout,
            )
            environment_opened = True

            kernel_runtime = resolve_kernel_runtime(
                environment_name,
                kernel_pid,
                timeout_seconds=kernel_cdp_timeout,
                probe_timeout_seconds=kernel_cdp_probe_timeout,
                http_timeout_seconds=http_probe_timeout,
            )
            kernel_version = kernel_version_from_cdp(kernel_runtime.cdp_port, timeout_seconds=http_probe_timeout)
            if not kernel_version:
                kernel_version = kernel_version_from_command_line(kernel_runtime.command_line)
            assert_true(
                kernel_version.startswith(expected_kernel_prefix),
                f"kernel version should start with {expected_kernel_prefix}, actual={kernel_version}",
            )

            environment_page.click_environment_action(environment_name, "关闭")
            environment_opened = False
            assert_true(
                wait_for_pid_stopped(kernel_pid, timeout_seconds=kernel_process_timeout),
                f"kernel process did not stop: pid={kernel_pid}",
            )
            environment_page.wait_environment_action_text(
                environment_name,
                "打开",
                timeout_seconds=environment_close_timeout,
            )

            environment_page.delete_environment_from_current_list(environment_name)
            environment_created = False
            environment_page.search_environment_without_assert(environment_name)
            assert_true(
                not environment_page.environment_visible_in_current_list(environment_name),
                f"environment was not deleted: {environment_name}",
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
                if environment_created:
                    environment_page.search_environment_without_assert(environment_name)
                    if environment_page.environment_visible_in_current_list(environment_name):
                        self._close_environment_if_open(
                            environment_page,
                            environment_name,
                            timeout_seconds=environment_close_timeout,
                        )
                        environment_page.delete_environment_from_current_list(environment_name)
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
