from __future__ import annotations

import copy
import time
import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.kernel_cdp_session import KernelCDPSession
from core.kernel_process import resolve_kernel_runtime
from core.local_auth_lab.client import LocalAuthLabClient
from core.local_auth_lab.credentials import local_auth_lab_login_credentials_by_site
from core.local_auth_lab.settings import LocalAuthLabSettings
from core.logger import setup_logger
from core.process import wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.global_settings_page import GlobalSettingsPage
from pages.local_auth_lab_page import LocalAuthLabPage
from pages.login_page import LoginPage


CASE_MODULE = "全局设置"
ENVIRONMENT_NAME = "自动化-全局设置-清除本地全部缓存-每次都清除-不同步云端数据"
LOGGED_IN_STATUS = "已登录"
LOGGED_OUT_STATUS = "未登录"
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


class TestGlobalSettingsClearAllCacheEveryOpenNoCloudSync(unittest.TestCase):
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

    def test_clear_all_cache_every_open_without_cloud_sync_clears_site_login_state(self) -> None:
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)

        credentials_by_site = self._credentials_by_site()
        self._ensure_lab_users(credentials_by_site)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        global_settings_snapshot: dict[str, object] | None = None
        global_clear_cache_reset = False
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
                wait_after_visit_seconds=2,
                run_id_prefix="global-clear-all-cache-no-cloud-sync-first",
            )
            self._assert_sites_logged_in(first_statuses, stage="首次打开登录后")

            global_settings_page.open(force_reentry=True)
            global_settings_snapshot = global_settings_page.capture_global_settings_snapshot()
            global_settings_page.configure_clear_all_local_cache_every_open_no_cloud_sync_data()

            environment_page.open_list()
            environment_page.search_environment(ENVIRONMENT_NAME)
            assert_true(
                environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME),
                f"配置全局清除本地缓存策略后未找到新建环境: {ENVIRONMENT_NAME}",
            )
            assert_equal(
                environment_page.environment_action_text(ENVIRONMENT_NAME),
                "打开",
                f"配置全局清除本地缓存策略后环境未处于可打开状态: {ENVIRONMENT_NAME}",
            )

            second_statuses = self._open_visit_sites_and_close(
                environment_page,
                environment_open_timeout=environment_open_timeout,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_cdp_timeout=kernel_cdp_timeout,
                kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                http_probe_timeout=http_probe_timeout,
                stage="启用全局清除本地缓存且不同步云端后再次打开",
                wait_after_visit_seconds=2,
            )
            self._assert_sites_logged_out(
                second_statuses,
                stage="启用全局清除本地缓存且不同步云端后再次打开",
            )

            environment_page.delete_environment_from_current_list(ENVIRONMENT_NAME)
            environment_page.search_environment_without_assert(ENVIRONMENT_NAME)
            assert_true(
                not environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME),
                f"新建环境删除后仍然存在: {ENVIRONMENT_NAME}",
            )

            global_settings_page.open(force_reentry=True)
            global_settings_page.restore_global_settings_snapshot(
                self._snapshot_with_clear_local_cache_no_clear(global_settings_snapshot)
            )
            global_clear_cache_reset = True
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
            if not global_clear_cache_reset:
                try:
                    global_settings_page.open(force_reentry=True)
                    if global_settings_snapshot is not None:
                        global_settings_page.restore_global_settings_snapshot(
                            self._snapshot_with_clear_local_cache_no_clear(global_settings_snapshot)
                        )
                    else:
                        global_settings_page.configure_clear_local_cache_no_clear()
                except Exception:
                    self.logger.exception("failed to restore global clear-local-cache setting to no-clear")

    def _credentials_by_site(self) -> dict[str, tuple[str, str]]:
        return local_auth_lab_login_credentials_by_site(
            self.config,
            (str(site["site_id"]) for site in SITE_DEFINITIONS),
        )

    def _ensure_lab_users(self, credentials_by_site: dict[str, tuple[str, str]]) -> None:
        settings = LocalAuthLabSettings.from_config(self.config).ensure_persistent_credentials()
        client = LocalAuthLabClient(settings)
        for site in SITE_DEFINITIONS:
            site_id = str(site["site_id"])
            username, password = credentials_by_site[site_id]
            client.ensure_user(site_id, username, password)

    def _snapshot_with_clear_local_cache_no_clear(self, snapshot: dict[str, object]) -> dict[str, object]:
        target = copy.deepcopy(snapshot)
        target["clear_local_cache"] = {
            "clear_method": GlobalSettingsPage.CLEAR_LOCAL_CACHE_NO_CLEAR_TEXT,
        }
        return target

    def _assert_sites_logged_in(self, statuses: dict[str, tuple[str, str]], *, stage: str) -> None:
        for site in SITE_DEFINITIONS:
            label = str(site["label"])
            site_id = str(site["site_id"])
            status, account = statuses[site_id]
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
            label = str(site["label"])
            site_id = str(site["site_id"])
            status, account = statuses[site_id]
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
        wait_after_visit_seconds: int = 0,
        run_id_prefix: str = "",
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
                    site_id = str(site["site_id"])
                    local_auth_page.open(site_id)
                    if credentials_by_site and local_auth_page.auth_status == LOGGED_IN_STATUS:
                        current_account = local_auth_page.current_account
                        if current_account != site["expected_account"]:
                            local_auth_page.logout()
                    if credentials_by_site and local_auth_page.auth_status != LOGGED_IN_STATUS:
                        username, password = credentials_by_site[site_id]
                        local_auth_page.login(
                            username,
                            password,
                            run_id=f"{run_id_prefix}-{site_id}",
                        )
                    time.sleep(wait_after_visit_seconds)
                    status = local_auth_page.auth_status
                    account = local_auth_page.current_account
                    statuses[site_id] = (status, account)
                    self.logger.info(
                        "Global clear-all-cache no-cloud-sync login status captured: "
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
