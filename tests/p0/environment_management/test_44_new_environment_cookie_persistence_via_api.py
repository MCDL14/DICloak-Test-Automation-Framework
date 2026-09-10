from __future__ import annotations

import time
import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.environment_create_api import EnvironmentCreateApiClient
from core.environment_cache import (
    delete_numeric_environment_cache_dirs,
    numeric_environment_cache_dirs,
)
from core.kernel_cdp_session import KernelCDPSession
from core.kernel_process import resolve_kernel_runtime
from core.local_auth_lab.credentials import local_auth_lab_login_credentials
from core.logger import setup_logger
from core.process import wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.global_settings_page import GlobalSettingsPage
from pages.local_auth_lab_page import LocalAuthLabPage
from pages.login_page import LoginPage
from pages.personal_settings_page import PersonalSettingsPage


CASE_MODULE = "环境管理"
ENVIRONMENT_NAME = "自动化-接口新环境Cookie持续保持"
EXPECTED_LOGIN_STATUS = "已登录"
EXPECTED_ACCOUNT = "MCDL004"
API_STATE_TIMEOUT_SECONDS = 30
API_STATE_POLL_SECONDS = 1


class TestNewEnvironmentCookiePersistenceViaApi(unittest.TestCase):
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

    def test_api_created_environment_cookie_survives_close_reopen_and_local_cache_deletion(self) -> None:
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)

        username, password = local_auth_lab_login_credentials(self.config, "cookie")

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page.prepare_api_recovery(
            affected_blocks={"data_sync_config"},
            bitmask_blocks={"data_sync_config"},
        )
        personal_settings_page = PersonalSettingsPage(cdp_driver=self.cdp, config=self.config)
        environment_api: EnvironmentCreateApiClient | None = None
        cookie_sync_changed = False
        environment_id = ""
        cleanup_error: Exception | None = None
        try:
            environment_page.open_list()
            global_settings_page.open()
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

            device_id = self._open_environment_list_and_capture_device_id(
                environment_page,
            )
            environment_api = EnvironmentCreateApiClient(
                self.cdp,
                device_id=device_id,
            )
            stale_environment_ids = self._environment_ids_from_api(environment_api)
            if stale_environment_ids:
                environment_api.delete_environments(stale_environment_ids)
                self._wait_environment_api_state(
                    environment_api,
                    expected_present=False,
                )
            environment_page.clear_search()

            environment_api.create_environment(
                name=ENVIRONMENT_NAME,
                browser_version_id="142",
            )
            environment_id = environment_api.last_created_environment_id
            assert_true(bool(environment_id), "创建环境接口未保存响应 data.id")
            self._wait_environment_api_state(
                environment_api,
                expected_present=True,
                environment_id=environment_id,
            )

            environment_page.search_environment(ENVIRONMENT_NAME)
            environment_page.wait_environment_visible_in_current_list(ENVIRONMENT_NAME)
            assert_equal(
                environment_page.environment_action_text(ENVIRONMENT_NAME),
                "打开",
                f"新建环境未处于可打开状态: {ENVIRONMENT_NAME}",
            )

            first_status, first_account = self._open_read_cookie_status_and_close(
                environment_page,
                environment_open_timeout=environment_open_timeout,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_cdp_timeout=kernel_cdp_timeout,
                kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                http_probe_timeout=http_probe_timeout,
                stage="新建环境首次登录",
                login_username=username,
                login_password=password,
                wait_after_login_seconds=2,
            )
            assert_equal(
                first_status,
                EXPECTED_LOGIN_STATUS,
                f"新建环境首次登录后的 Cookie 模拟站状态错误: actual={first_status}",
            )
            assert_equal(
                first_account,
                EXPECTED_ACCOUNT,
                f"新建环境首次登录后的账号错误: actual={first_account}",
            )

            # 该 3 秒是用例明确要求的云端同步等待窗口，不作为页面加载同步手段。
            time.sleep(3)

            second_status, second_account = self._open_read_cookie_status_and_close(
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
                f"再次打开新环境后的 Cookie 模拟站状态错误: actual={second_status}",
            )
            assert_equal(
                second_account,
                EXPECTED_ACCOUNT,
                f"再次打开新环境后的账号错误: actual={second_account}",
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
            third_status, third_account = self._open_read_cookie_status_and_close(
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
                f"删除本地缓存并恢复后 Cookie 模拟站状态错误: actual={third_status}",
            )
            assert_equal(
                third_account,
                EXPECTED_ACCOUNT,
                f"删除本地缓存并恢复后的账号错误: actual={third_account}",
            )

            environment_api.delete_environments(environment_id)
            self._wait_environment_api_state(
                environment_api,
                expected_present=False,
            )
            environment_id = ""
            environment_page.clear_search()
        finally:
            if environment_id:
                try:
                    environment_page.open_list()
                    environment_page.search_environment_without_assert(ENVIRONMENT_NAME)
                    self._close_environment_if_open(
                        environment_page,
                        environment_close_timeout=environment_close_timeout,
                        kernel_process_timeout=kernel_process_timeout,
                    )
                except Exception as exc:
                    self.logger.warning(
                        "Failed to close API-created environment during cleanup: %s",
                        exc,
                    )
            try:
                cleanup_ids = (
                    self._environment_ids_from_api(environment_api)
                    if environment_api is not None
                    else []
                )
                if environment_id and environment_id not in cleanup_ids:
                    cleanup_ids.append(environment_id)
                if cleanup_ids and environment_api is not None:
                    environment_api.delete_environments(cleanup_ids)
                    self._wait_environment_api_state(
                        environment_api,
                        expected_present=False,
                    )
            except Exception as exc:
                self.logger.warning("Failed to delete API-created environment during cleanup: %s", exc)
            try:
                environment_page.clear_search()
            except Exception:
                pass
            try:
                global_settings_page.restore_api_recovery_if_needed()
            except Exception as exc:
                cleanup_error = exc
            if cleanup_error:
                raise cleanup_error

    def _open_environment_list_and_capture_device_id(
        self,
        environment_page: EnvironmentPage,
    ) -> str:
        page = self.cdp._page()

        def is_environment_list_request(request) -> bool:
            return (
                "/gin/v1/env/list" in request.url
                and request.method.upper() == "POST"
            )

        with page.expect_request(is_environment_list_request, timeout=30_000) as request_info:
            environment_page.open_list()
        device_id = str(request_info.value.headers.get("x-device-id") or "").strip()
        assert_true(bool(device_id), "APP 环境列表请求未携带 x-device-id")
        return device_id

    def _environment_ids_from_api(
        self,
        environment_api: EnvironmentCreateApiClient,
    ) -> list[str]:
        return environment_api.environment_ids_by_name(ENVIRONMENT_NAME)

    def _wait_environment_api_state(
        self,
        environment_api: EnvironmentCreateApiClient,
        *,
        expected_present: bool,
        environment_id: str = "",
    ) -> None:
        deadline = time.time() + API_STATE_TIMEOUT_SECONDS
        last_environment_ids: list[str] = []
        while time.time() < deadline:
            last_environment_ids = self._environment_ids_from_api(environment_api)
            if expected_present:
                if environment_id in last_environment_ids:
                    return
            elif not last_environment_ids:
                return
            time.sleep(API_STATE_POLL_SECONDS)
        expected_text = "存在" if expected_present else "不存在"
        raise AssertionError(
            "环境列表接口状态确认超时: "
            f"expected={expected_text}, name={ENVIRONMENT_NAME}, "
            f"environment_id={environment_id}, actual_ids={last_environment_ids}"
        )

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
                local_auth_page.open("cookie")
                if login_username:
                    local_auth_page.login(
                        login_username,
                        login_password,
                        run_id="api-created-environment-cookie-persistence",
                    )
                    time.sleep(wait_after_login_seconds)
                status = local_auth_page.auth_status
                account = local_auth_page.current_account
                self.logger.info(
                    "Cookie login status captured: stage=%s environment=%s status=%s account=%s",
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
