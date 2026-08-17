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
ENVIRONMENT_NAME = "全局设置-单向同步-禁止当前账号同步"
EXPECTED_SYNC_ITEMS = ["Cookie", "Local Storage", "IndexedDB"]
EXPECTED_WHITELIST_GROUPS = ["超管组"]
LOGGED_IN_STATUS = "已登录"
LOGGED_OUT_STATUS = "未登录"
ONE_WAY_SYNC_DATA_KEY = "environment_one_way_sync"
SITE_DEFINITIONS = (
    {
        "site_id": "cookie",
        "label": "Cookie",
        "expected_account": "MCDL004",
    },
    {
        "site_id": "localstorage",
        "label": "Local Storage",
        "expected_account": "MCDL005",
    },
    {
        "site_id": "indexeddb",
        "label": "IndexedDB",
        "expected_account": "MCDL006",
    },
)


class TestGlobalSettingsOneWaySyncForbidCurrentAccount(unittest.TestCase):
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

    def test_global_settings_one_way_sync_forbids_current_account_data_upload(self) -> None:
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)

        credentials_by_site = self._credentials_by_site()

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        personal_settings_page = PersonalSettingsPage(cdp_driver=self.cdp, config=self.config)
        try:
            global_settings_page.open(force_reentry=True)
            configured_state = global_settings_page.configure_data_sync_one_way(
                EXPECTED_SYNC_ITEMS,
                EXPECTED_WHITELIST_GROUPS,
            )
            self._assert_global_one_way_configured(configured_state)

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

            environment_page.create_environment(ENVIRONMENT_NAME)
            environment_page.wait_environment_visible_in_current_list(ENVIRONMENT_NAME)
            assert_equal(
                environment_page.environment_action_text(ENVIRONMENT_NAME),
                "打开",
                f"新建默认配置环境未处于可打开状态: {ENVIRONMENT_NAME}",
            )

            first_statuses = self._open_visit_sites_and_close(
                environment_page,
                environment_open_timeout=environment_open_timeout,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_cdp_timeout=kernel_cdp_timeout,
                kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                http_probe_timeout=http_probe_timeout,
                stage="首次打开并登录",
                credentials_by_site=credentials_by_site,
                wait_after_login_seconds=2,
            )
            self._assert_sites_logged_in(first_statuses, stage="首次打开登录后")

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

            second_statuses = self._open_visit_sites_and_close(
                environment_page,
                environment_open_timeout=environment_open_timeout,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_cdp_timeout=kernel_cdp_timeout,
                kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                http_probe_timeout=http_probe_timeout,
                stage="删除本地缓存后再次打开",
            )
            self._assert_sites_logged_out(second_statuses, stage="删除本地缓存后再次打开")

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
            global_settings_page.open(force_reentry=True)
            final_global_state = global_settings_page.disable_data_sync_one_way()
            assert_true(
                not bool(final_global_state.get("one_way_enabled")),
                f"全局设置单向同步开关未关闭: actual={final_global_state}",
            )

    def _credentials_by_site(self) -> dict[str, tuple[str, str]]:
        test_data = self.config.get("test_data", {})
        assert_true(isinstance(test_data, dict), "测试数据配置格式错误: test_data 不是字典")
        combined = test_data.get(ONE_WAY_SYNC_DATA_KEY)
        if not isinstance(combined, dict):
            combined = {}
        credentials_by_site: dict[str, tuple[str, str]] = {}
        for site in SITE_DEFINITIONS:
            site_id = site["site_id"]
            value = combined.get(site_id)
            if not isinstance(value, dict):
                value = {}
            username = str(value.get("username", "")).strip()
            password = str(value.get("password", ""))
            assert_equal(
                username,
                site["expected_account"],
                f"单向同步共享配置 {site['label']} 账号配置错误",
            )
            assert_true(
                bool(password) and not password.startswith("请在"),
                f"请在 config/test_data.yaml 中配置 {ONE_WAY_SYNC_DATA_KEY}.{site_id} 登录密码",
            )
            credentials_by_site[site_id] = (username, password)
        return credentials_by_site

    def _assert_global_one_way_configured(self, state: dict[str, object]) -> None:
        assert_true(bool(state.get("cookie")), "全局设置数据同步 Cookie 未保持勾选")
        assert_true(bool(state.get("local_storage")), "全局设置数据同步 Local Storage 未保持勾选")
        assert_true(bool(state.get("indexeddb")), "全局设置数据同步 IndexedDB 未保持勾选")
        assert_true(bool(state.get("one_way_enabled")), "全局设置单向同步开关未保持开启")
        actual_whitelist = sorted(str(item) for item in state.get("whitelist_groups", []))
        assert_equal(
            actual_whitelist,
            sorted(EXPECTED_WHITELIST_GROUPS),
            f"全局设置单向同步白名单不正确: actual={actual_whitelist}",
        )

    def _assert_sites_logged_in(self, statuses: dict[str, tuple[str, str]], *, stage: str) -> None:
        for site in SITE_DEFINITIONS:
            label = site["label"]
            status, account = statuses[site["site_id"]]
            assert_equal(
                status,
                LOGGED_IN_STATUS,
                f"{stage} {label} 模拟站状态错误: actual_status={status}, actual_account={account}",
            )
            assert_equal(
                account,
                site["expected_account"],
                f"{stage} {label} 模拟站账号错误: actual={account}",
            )

    def _assert_sites_logged_out(self, statuses: dict[str, tuple[str, str]], *, stage: str) -> None:
        for site in SITE_DEFINITIONS:
            label = site["label"]
            status, account = statuses[site["site_id"]]
            assert_equal(
                status,
                LOGGED_OUT_STATUS,
                f"{stage} {label} 模拟站应为未登录: actual_status={status}, actual_account={account}",
            )

    def _open_visit_sites_and_close(
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
        credentials_by_site: dict[str, tuple[str, str]] | None = None,
        wait_after_login_seconds: int = 0,
    ) -> dict[str, tuple[str, str]]:
        kernel_pid = 0
        statuses: dict[str, tuple[str, str]] = {}
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
                for site in SITE_DEFINITIONS:
                    site_id = site["site_id"]
                    local_auth_page.open(site_id)
                    if credentials_by_site:
                        username, password = credentials_by_site[site_id]
                        local_auth_page.login(
                            username,
                            password,
                            run_id=f"global-one-way-sync-forbid-{site_id}",
                        )
                        time.sleep(wait_after_login_seconds)
                    status = local_auth_page.auth_status
                    account = local_auth_page.current_account
                    statuses[site_id] = (status, account)
                    self.logger.info(
                        "Global one-way sync login status captured: "
                        "stage=%s environment=%s site=%s status=%s account=%s",
                        stage,
                        ENVIRONMENT_NAME,
                        site_id,
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
        return statuses

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
