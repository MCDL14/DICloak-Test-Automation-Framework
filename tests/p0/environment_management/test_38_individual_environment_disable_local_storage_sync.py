from __future__ import annotations

import time
import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.environment_cache import (
    delete_numeric_environment_cache_dirs,
    numeric_environment_cache_dirs,
)
from core.kernel_cdp_session import KernelCDPSession
from core.kernel_process import resolve_kernel_runtime
from core.local_auth_lab.client import LocalAuthLabClient
from core.local_auth_lab.credentials import local_auth_lab_login_credentials
from core.local_auth_lab.settings import LocalAuthLabSettings
from core.logger import setup_logger
from core.process import wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.local_auth_lab_page import LocalAuthLabPage
from pages.login_page import LoginPage
from pages.personal_settings_page import PersonalSettingsPage


CASE_MODULE = "环境管理"
ENVIRONMENT_NAME = "自动化-环境单独设置-不勾选Local Storage同步"
EXPECTED_ACCOUNT = "MCDL005"
DISABLED_SYNC_ITEMS = ["Local Storage"]
LOGGED_IN_STATUS = "已登录"
LOGGED_OUT_STATUS = "未登录"


class TestIndividualEnvironmentDisableLocalStorageSync(unittest.TestCase):
    REQUIRED_RUNTIME_SERVICES = {"local_auth_lab"}

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

    def test_local_storage_not_restored_after_cache_deletion_when_individual_local_storage_sync_disabled(
        self,
    ) -> None:
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)

        username, password = local_auth_lab_login_credentials(self.config, "localstorage")
        self._ensure_local_storage_lab_user(username, password)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        personal_settings_page = PersonalSettingsPage(cdp_driver=self.cdp, config=self.config)
        try:
            environment_page.open_list()
            environment_page.search_environment_without_assert(ENVIRONMENT_NAME)
            if environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME):
                self._close_environment_if_open(
                    environment_page,
                    environment_close_timeout=environment_close_timeout,
                    kernel_process_timeout=kernel_process_timeout,
                )
                environment_page.delete_environment_from_current_list(ENVIRONMENT_NAME)
                environment_page.wait_environment_absent_in_current_list(ENVIRONMENT_NAME)

            selected_sync_items = environment_page.create_environment_with_custom_data_sync_disabled(
                ENVIRONMENT_NAME,
                DISABLED_SYNC_ITEMS,
            )
            assert_true(
                "Local Storage" not in selected_sync_items,
                f"创建环境时 Local Storage 数据同步未保持取消勾选: actual={selected_sync_items}",
            )
            environment_page.wait_environment_visible_in_current_list(ENVIRONMENT_NAME)
            assert_equal(
                environment_page.environment_action_text(ENVIRONMENT_NAME),
                "打开",
                f"新建环境未处于可打开状态: {ENVIRONMENT_NAME}",
            )

            first_status, first_account = self._open_read_local_storage_status_and_close(
                environment_page,
                environment_open_timeout=environment_open_timeout,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_cdp_timeout=kernel_cdp_timeout,
                kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                http_probe_timeout=http_probe_timeout,
                stage="首次打开并登录",
                login_username=username,
                login_password=password,
                wait_after_login_seconds=2,
            )
            assert_equal(
                first_status,
                LOGGED_IN_STATUS,
                f"首次打开登录后 Local Storage 模拟站状态错误: actual={first_status}, account={first_account}",
            )
            assert_equal(
                first_account,
                EXPECTED_ACCOUNT,
                f"首次打开登录后 Local Storage 模拟站账号错误: actual={first_account}",
            )

            second_status, second_account = self._open_read_local_storage_status_and_close(
                environment_page,
                environment_open_timeout=environment_open_timeout,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_cdp_timeout=kernel_cdp_timeout,
                kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                http_probe_timeout=http_probe_timeout,
                stage="未删除本地缓存再次打开",
            )
            assert_equal(
                second_status,
                LOGGED_IN_STATUS,
                f"未删除本地缓存再次打开后 Local Storage 模拟站状态错误: actual={second_status}, account={second_account}",
            )
            assert_equal(
                second_account,
                EXPECTED_ACCOUNT,
                f"未删除本地缓存再次打开后 Local Storage 模拟站账号错误: actual={second_account}",
            )

            personal_settings_page.open_from_avatar()
            personal_settings_page.open_basic_settings()
            cache_dir = personal_settings_page.environment_cache_dir()
            cache_targets = numeric_environment_cache_dirs(cache_dir)
            assert_true(
                bool(cache_targets),
                f"环境缓存目录中未找到 19 位纯数字文件夹: cache_dir={cache_dir}",
            )
            target_names = tuple(path.name for path in cache_targets)
            self.logger.info(
                "Validated environment cache deletion targets: root=%s targets=%s",
                cache_dir,
                target_names,
            )
            deleted_names = delete_numeric_environment_cache_dirs(cache_dir)
            assert_equal(
                deleted_names,
                target_names,
                f"19 位环境缓存目录删除结果与预检目标不一致: expected={target_names}, actual={deleted_names}",
            )
            assert_equal(
                numeric_environment_cache_dirs(cache_dir),
                (),
                f"19 位环境缓存目录删除后仍有残留: cache_dir={cache_dir}",
            )

            environment_page.open_list()
            environment_page.search_environment(ENVIRONMENT_NAME)
            assert_true(
                environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME),
                f"删除本地缓存后未找到新建环境: {ENVIRONMENT_NAME}",
            )
            third_status, third_account = self._open_read_local_storage_status_and_close(
                environment_page,
                environment_open_timeout=environment_open_timeout,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_cdp_timeout=kernel_cdp_timeout,
                kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                http_probe_timeout=http_probe_timeout,
                stage="删除本地缓存后再次打开",
            )
            assert_equal(
                third_status,
                LOGGED_OUT_STATUS,
                f"删除本地缓存后 Local Storage 模拟站应为未登录: actual={third_status}, account={third_account}",
            )

            environment_page.delete_environment_from_current_list(ENVIRONMENT_NAME)
            environment_page.search_environment_without_assert(ENVIRONMENT_NAME)
            assert_true(
                not environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME),
                f"新建环境删除后仍然存在: {ENVIRONMENT_NAME}",
            )
        finally:
            try:
                environment_page.open_list()
                environment_page.search_environment_without_assert(ENVIRONMENT_NAME)
                self._close_environment_if_open(
                    environment_page,
                    environment_close_timeout=environment_close_timeout,
                    kernel_process_timeout=kernel_process_timeout,
                )
                if environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME):
                    environment_page.delete_environment_from_current_list(ENVIRONMENT_NAME)
                    environment_page.wait_environment_absent_in_current_list(ENVIRONMENT_NAME)
            except Exception:
                pass
            try:
                environment_page.clear_search()
            except Exception:
                pass

    def _ensure_local_storage_lab_user(self, username: str, password: str) -> None:
        settings = LocalAuthLabSettings.from_config(self.config).ensure_persistent_credentials()
        LocalAuthLabClient(settings).ensure_user("localstorage", username, password)

    def _open_read_local_storage_status_and_close(
        self,
        environment_page: EnvironmentPage,
        *,
        environment_open_timeout: int,
        environment_close_timeout: int,
        kernel_process_timeout: int,
        kernel_cdp_timeout: int,
        kernel_cdp_probe_timeout: int,
        http_probe_timeout: int,
        stage: str,
        login_username: str = "",
        login_password: str = "",
        wait_after_login_seconds: int = 0,
    ) -> tuple[str, str]:
        kernel_pid = 0
        status = ""
        account = ""
        try:
            kernel_pid = environment_page.open_environment_and_capture_pid(ENVIRONMENT_NAME)
            assert_true(
                wait_for_pid_running(kernel_pid, timeout_seconds=kernel_process_timeout),
                f"{stage}时浏览器内核进程未启动: pid={kernel_pid}",
            )
            environment_page.wait_environment_action_text(
                ENVIRONMENT_NAME,
                "关闭",
                timeout_seconds=environment_open_timeout,
            )
            kernel_runtime = resolve_kernel_runtime(
                ENVIRONMENT_NAME,
                kernel_pid,
                timeout_seconds=kernel_cdp_timeout,
                probe_timeout_seconds=kernel_cdp_probe_timeout,
                http_timeout_seconds=http_probe_timeout,
            )
            with KernelCDPSession(
                kernel_runtime.cdp_port,
                timeout_seconds=max(kernel_cdp_timeout, 20),
            ) as kernel_session:
                local_auth_page = LocalAuthLabPage(kernel_session, self.config)
                local_auth_page.open("localstorage")
                if login_username:
                    local_auth_page.login(
                        login_username,
                        login_password,
                        run_id="individual-environment-local-storage-sync-disabled",
                    )
                    time.sleep(wait_after_login_seconds)
                status = local_auth_page.auth_status
                account = local_auth_page.current_account
                self.logger.info(
                    "Local Storage login status captured: stage=%s environment=%s status=%s account=%s",
                    stage,
                    ENVIRONMENT_NAME,
                    status,
                    account,
                )
        finally:
            self._close_environment_if_open(
                environment_page,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_pid=kernel_pid,
            )

        assert_equal(
            environment_page.environment_action_text(ENVIRONMENT_NAME),
            "打开",
            f"{stage}并关闭环境后操作按钮未恢复为打开: {ENVIRONMENT_NAME}",
        )
        return status, account

    def _close_environment_if_open(
        self,
        environment_page: EnvironmentPage,
        *,
        environment_close_timeout: int,
        kernel_process_timeout: int,
        kernel_pid: int = 0,
    ) -> None:
        if not environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME):
            return
        if environment_page.environment_action_text(ENVIRONMENT_NAME) != "关闭":
            return
        environment_page.click_environment_action(ENVIRONMENT_NAME, "关闭")
        if kernel_pid:
            assert_true(
                wait_for_pid_stopped(kernel_pid, timeout_seconds=kernel_process_timeout),
                f"浏览器内核进程未停止: pid={kernel_pid}",
            )
        environment_page.wait_environment_action_text(
            ENVIRONMENT_NAME,
            "打开",
            timeout_seconds=environment_close_timeout,
        )


if __name__ == "__main__":
    unittest.main()
