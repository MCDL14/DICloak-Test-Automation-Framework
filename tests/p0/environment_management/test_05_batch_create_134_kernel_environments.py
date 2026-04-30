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


class TestBatchCreate134KernelEnvironments(unittest.TestCase):
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

    def test_batch_create_open_verify_close_delete_134_kernel_environments(self) -> None:
        data = self.config["test_data"]["environment_batch_create_134_kernel"]
        name_prefix = str(data.get("environment_name_prefix", "自动化-批量创建134内核环境"))
        create_count = int(data.get("create_count", 3))
        kernel_label = str(data.get("kernel_label", "ChromeBrowser 134"))
        expected_kernel_prefix = str(data.get("expected_kernel_prefix", "134"))
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        created_names: list[str] = []
        kernel_pids: list[int] = []
        environments_opened = False

        try:
            environment_page.open_list()
            environment_page.search_environment_without_assert(name_prefix)
            existing_names = environment_page.environment_names_by_prefix_in_current_list(name_prefix)
            self._close_environments_if_open(
                environment_page,
                existing_names,
                timeout_seconds=environment_close_timeout,
                kernel_pids=[],
                kernel_process_timeout=kernel_process_timeout,
            )
            environment_page.delete_environments_by_prefix_from_current_list(name_prefix)
            environment_page.wait_no_environment_by_prefix_in_current_list(name_prefix)

            environment_page.batch_create_environments_with_kernel(name_prefix, create_count, kernel_label)
            environment_page.search_environment_without_assert(name_prefix)
            created_names = environment_page.wait_environment_count_by_prefix_in_current_list(
                name_prefix,
                create_count,
            )
            assert_equal(
                len(created_names),
                create_count,
                f"batch created 134 kernel environment count is incorrect: names={created_names}",
            )

            environment_page.select_environments(created_names)
            kernel_pids = environment_page.open_selected_environments_and_capture_pids(
                expected_count=create_count,
                timeout_seconds=environment_open_timeout,
            )
            assert_equal(
                len(kernel_pids),
                create_count,
                f"open_env pid count is incorrect: pids={kernel_pids}",
            )
            for pid in kernel_pids:
                assert_true(
                    wait_for_pid_running(pid, timeout_seconds=kernel_process_timeout),
                    f"kernel process did not start: pid={pid}",
                )
            environment_page.wait_environments_action_text(
                created_names,
                "关闭",
                timeout_seconds=environment_open_timeout,
            )
            environments_opened = True
            for name in created_names:
                assert_equal(
                    environment_page.environment_action_text(name),
                    "关闭",
                    f"environment was not opened successfully: {name}",
                )

            for name, pid in zip(created_names, kernel_pids):
                kernel_runtime = resolve_kernel_runtime(
                    name,
                    pid,
                    timeout_seconds=kernel_cdp_timeout,
                    probe_timeout_seconds=kernel_cdp_probe_timeout,
                    http_timeout_seconds=http_probe_timeout,
                )
                kernel_version = kernel_version_from_cdp(kernel_runtime.cdp_port, timeout_seconds=http_probe_timeout)
                if not kernel_version:
                    kernel_version = kernel_version_from_command_line(kernel_runtime.command_line)
                assert_true(
                    kernel_version.startswith(expected_kernel_prefix),
                    f"kernel version should start with {expected_kernel_prefix}: name={name}, actual={kernel_version}",
                )

            environment_page.select_environments(created_names)
            environment_page.click_batch_action("关闭环境")
            environment_page.confirm_secondary_dialog_if_present()
            for pid in kernel_pids:
                assert_true(
                    wait_for_pid_stopped(pid, timeout_seconds=kernel_process_timeout),
                    f"kernel process did not stop: pid={pid}",
                )
            environment_page.wait_environments_action_text(
                created_names,
                "打开",
                timeout_seconds=environment_close_timeout,
            )
            environments_opened = False
            for name in created_names:
                assert_equal(
                    environment_page.environment_action_text(name),
                    "打开",
                    f"environment was not closed successfully: {name}",
                )

            environment_page.delete_environments_by_prefix_from_current_list(name_prefix)
            environment_page.search_environment_without_assert(name_prefix)
            assert_true(
                not environment_page.environment_names_by_prefix_in_current_list(name_prefix),
                f"batch created 134 kernel environments were not deleted: prefix={name_prefix}",
            )
            created_names = []
        finally:
            try:
                if environments_opened and created_names:
                    self._close_environments_if_open(
                        environment_page,
                        created_names,
                        timeout_seconds=environment_close_timeout,
                        kernel_pids=kernel_pids,
                        kernel_process_timeout=kernel_process_timeout,
                    )
            except Exception:
                pass
            try:
                if created_names:
                    environment_page.clear_selected_environments()
                    environment_page.search_environment_without_assert(name_prefix)
                    environment_page.delete_environments_by_prefix_from_current_list(name_prefix)
            except Exception:
                pass
            try:
                environment_page.clear_selected_environments()
            except Exception:
                pass
            try:
                environment_page.clear_search()
            except Exception:
                pass

    def _close_environments_if_open(
        self,
        environment_page: EnvironmentPage,
        names: list[str],
        timeout_seconds: int,
        kernel_pids: list[int],
        kernel_process_timeout: int,
    ) -> None:
        open_names = [
            name
            for name in names
            if environment_page.environment_visible_in_current_list(name)
            and environment_page.environment_action_text(name) == "关闭"
        ]
        if not open_names:
            return
        environment_page.select_environments(open_names)
        environment_page.click_batch_action("关闭环境")
        environment_page.confirm_secondary_dialog_if_present()
        for pid in kernel_pids:
            wait_for_pid_stopped(pid, timeout_seconds=kernel_process_timeout)
        environment_page.wait_environments_action_text(
            open_names,
            "打开",
            timeout_seconds=timeout_seconds,
        )
        environment_page.clear_selected_environments()


if __name__ == "__main__":
    unittest.main()
