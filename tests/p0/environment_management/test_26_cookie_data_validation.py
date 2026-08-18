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
from core.logger import setup_logger
from core.process import wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.global_settings_page import GlobalSettingsPage
from pages.local_auth_lab_page import LocalAuthLabPage
from pages.login_page import LoginPage
from pages.personal_settings_page import PersonalSettingsPage


CASE_MODULE = "环境管理"
ENVIRONMENT_NAME = "Cookie数据校验"
EXPECTED_LOGIN_STATUS = "已登录"


class TestCookieDataValidation(unittest.TestCase):
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

    def test_cookie_data_survives_close_reopen_and_local_cache_deletion(self) -> None:
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        personal_settings_page = PersonalSettingsPage(cdp_driver=self.cdp, config=self.config)
        cookie_sync_changed = False
        global_settings_snapshot: dict[str, object] | None = None
        cleanup_error: Exception | None = None

        try:
            environment_page.open_list()
            global_settings_page.open()
            global_settings_snapshot = global_settings_page.capture_global_settings_snapshot()
            self.logger.info(
                "Global settings page loaded with at least %s checked checkboxes before Cookie read",
                global_settings_page.MINIMUM_CHECKED_CHECKBOXES,
            )
            cookie_sync_changed = global_settings_page.ensure_cookie_data_sync_enabled()
            assert_true(
                global_settings_page.cookie_data_sync_enabled(),
                "数据设置 → 数据同步中的 Cookie 未保持勾选状态",
            )
            self.logger.info("Cookie data sync is enabled: changed=%s", cookie_sync_changed)

            environment_page.open_list()
            environment_page.search_environment(ENVIRONMENT_NAME)
            assert_true(
                environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME),
                f"preset environment was not found: {ENVIRONMENT_NAME}",
            )
            self._close_environment_if_open(
                environment_page,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
            )

            first_status = self._open_read_cookie_status_and_close(
                environment_page,
                environment_open_timeout=environment_open_timeout,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_cdp_timeout=kernel_cdp_timeout,
                kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                http_probe_timeout=http_probe_timeout,
                stage="首次打开",
            )
            assert_equal(
                first_status,
                EXPECTED_LOGIN_STATUS,
                f"首次打开环境后 Cookie 模拟站登录状态错误: actual={first_status}",
            )

            # 该 3 秒是用例明确要求的云端同步等待窗口，不作为页面加载同步手段。
            time.sleep(3)

            second_status = self._open_read_cookie_status_and_close(
                environment_page,
                environment_open_timeout=environment_open_timeout,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_cdp_timeout=kernel_cdp_timeout,
                kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                http_probe_timeout=http_probe_timeout,
                stage="等待后再次打开",
            )
            assert_equal(
                second_status,
                EXPECTED_LOGIN_STATUS,
                f"再次打开环境后 Cookie 模拟站登录状态错误: actual={second_status}",
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
                f"cache deletion后未找到预置环境: {ENVIRONMENT_NAME}",
            )
            third_status = self._open_read_cookie_status_and_close(
                environment_page,
                environment_open_timeout=environment_open_timeout,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_cdp_timeout=kernel_cdp_timeout,
                kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                http_probe_timeout=http_probe_timeout,
                stage="删除本地缓存后打开",
            )
            assert_equal(
                third_status,
                EXPECTED_LOGIN_STATUS,
                f"删除本地缓存并恢复后 Cookie 模拟站登录状态错误: actual={third_status}",
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
            except Exception:
                pass
            try:
                environment_page.clear_search()
            except Exception:
                pass
            try:
                if global_settings_snapshot is not None:
                    global_settings_page.open(force_reentry=True)
                    global_settings_page.restore_global_settings_snapshot(global_settings_snapshot)
            except Exception as exc:
                cleanup_error = exc
            if cleanup_error:
                raise cleanup_error

    def _open_read_cookie_status_and_close(
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
    ) -> str:
        kernel_pid = 0
        status = ""
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
                local_auth_page.open("cookie")
                status = local_auth_page.auth_status
                self.logger.info(
                    "Cookie login status captured: stage=%s environment=%s status=%s account=%s",
                    stage,
                    ENVIRONMENT_NAME,
                    status,
                    local_auth_page.current_account,
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
        return status

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
