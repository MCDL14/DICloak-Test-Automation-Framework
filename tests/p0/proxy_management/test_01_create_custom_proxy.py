from __future__ import annotations

import os
import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from core.windows_proxy import (
    disable_windows_system_proxy,
    enable_windows_system_proxy,
    proxy_server_from_config,
    read_windows_system_proxy_settings,
)
from pages.login_page import LoginPage
from pages.proxy_page import ProxyPage


CASE_MODULE = "代理管理"


class TestCreateCustomProxy(unittest.TestCase):
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

    def test_create_custom_proxy_detect_and_delete(self) -> None:
        proxy_page = ProxyPage(cdp_driver=self.cdp, config=self.config)
        proxy_data = self._proxy_data()
        host = proxy_data["host"]
        port = proxy_data["port"]
        account = proxy_data["account"]
        password = proxy_data["password"]
        protocol = "HTTP"
        system_proxy_server = proxy_server_from_config(self.config)
        created_proxy_id = ""
        failures: list[str] = []

        try:
            self._enable_windows_system_proxy(system_proxy_server)
            proxy_page.open_list()
            existing_ids = proxy_page.proxy_ids_by_type_host_port(protocol, host, port)

            proxy_page.open_create_dialog()
            proxy_page.ensure_create_dialog_proxy_type(protocol)
            proxy_page.fill_create_dialog(host, port, account, password)

            dialog_result = proxy_page.detect_proxy_in_create_dialog()
            if dialog_result == ProxyPage.FAILURE_TEXT:
                failures.append("创建弹窗检测代理结果为连接失败")

            if dialog_result == ProxyPage.FAILURE_TEXT:
                if proxy_page.try_confirm_create_dialog(timeout_seconds=5):
                    created_proxy_id = proxy_page.wait_new_proxy_visible_by_type(protocol, host, port, existing_ids)
                else:
                    proxy_page.cancel_create_dialog()
            else:
                proxy_page.confirm_create_dialog()
                created_proxy_id = proxy_page.wait_new_proxy_visible_by_type(protocol, host, port, existing_ids)

            if created_proxy_id:
                created_row = proxy_page.proxy_row_by_id(created_proxy_id)
                self.logger.info(
                    "Proxy custom created id=%s type=%s host=%s port=%s",
                    created_proxy_id,
                    created_row.get("type"),
                    host,
                    port,
                )
                assert_true(
                    created_row.get("type") == protocol,
                    f"created custom proxy type mismatch: expected={protocol}, row={created_row}",
                )

                self.logger.info("Proxy custom row detect start id=%s", created_proxy_id)
                row_result = proxy_page.detect_proxy_in_row(created_proxy_id)
                self.logger.info("Proxy custom row detect result id=%s result=%s", created_proxy_id, row_result)
                if row_result == ProxyPage.FAILURE_TEXT:
                    failures.append("代理列表行内检测结果为连接失败")

                deleted_proxy_id = created_proxy_id
                self.logger.info("Proxy custom delete start id=%s", deleted_proxy_id)
                proxy_page.delete_proxy_by_id(created_proxy_id)
                created_proxy_id = ""
                self.logger.info("Proxy custom delete finished id=%s", deleted_proxy_id)
                assert_true(
                    not proxy_page.proxy_exists_by_type_host_port_id(protocol, host, port, deleted_proxy_id),
                    "代理删除后仍存在于列表",
                )
        finally:
            try:
                if "existing_ids" in locals():
                    if created_proxy_id:
                        self.logger.info("Proxy custom cleanup delete remaining id=%s", created_proxy_id)
                        proxy_page.delete_proxy_by_id(created_proxy_id)
            except Exception as exc:
                failures.append(f"代理清理失败: {exc}")
            try:
                self._disable_windows_system_proxy()
            except Exception as exc:
                failures.append(f"Windows 系统代理关闭失败: {exc}")

        assert_true(not failures, "; ".join(failures))

    def _proxy_data(self) -> dict[str, str]:
        data = self.config.get("test_data", {}).get("proxy_custom", {})
        host = str(data.get("host") or "accel.ipflygates.com").strip()
        port = str(data.get("port") or "5001").strip()
        account = str(os.environ.get("DICLOAK_PROXY_CUSTOM_ACCOUNT") or data.get("account") or "").strip()
        password = str(os.environ.get("DICLOAK_PROXY_CUSTOM_PASSWORD") or data.get("password") or "").strip()
        assert_true(bool(account), "proxy custom account is empty; set test_data.proxy_custom.account or DICLOAK_PROXY_CUSTOM_ACCOUNT")
        assert_true(bool(password), "proxy custom password is empty; set test_data.proxy_custom.password or DICLOAK_PROXY_CUSTOM_PASSWORD")
        return {
            "host": host,
            "port": port,
            "account": account,
            "password": password,
        }

    def _enable_windows_system_proxy(self, proxy_server: str) -> None:
        original_settings = read_windows_system_proxy_settings()
        self.logger.info(
            "Windows system proxy enable proxy_server=%s original_enable=%s original_server=%s",
            proxy_server,
            original_settings.get("ProxyEnable", (False, None, None))[1],
            original_settings.get("ProxyServer", (False, None, None))[1],
        )
        enable_windows_system_proxy(proxy_server)

    def _disable_windows_system_proxy(self) -> None:
        current_settings = read_windows_system_proxy_settings()
        self.logger.info(
            "Windows system proxy disable current_enable=%s current_server=%s",
            current_settings.get("ProxyEnable", (False, None, None))[1],
            current_settings.get("ProxyServer", (False, None, None))[1],
        )
        disable_windows_system_proxy()


if __name__ == "__main__":
    unittest.main()
