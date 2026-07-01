from __future__ import annotations

import os
import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from core.system_proxy import (
    enable_system_proxy,
    proxy_server_from_config,
    read_system_proxy_settings,
    restore_system_proxy_settings,
    system_proxy_supported,
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
        original_system_proxy_settings = None
        created_proxy_serial = ""
        failures: list[str] = []

        try:
            original_system_proxy_settings = self._enable_system_proxy_if_supported()
            proxy_page.open_list()
            existing_serials = proxy_page.proxy_serials_by_type_host_port(protocol, host, port)

            proxy_page.open_create_dialog()
            proxy_page.ensure_create_dialog_proxy_type(protocol)
            proxy_page.fill_create_dialog(host, port, account, password)

            dialog_result = proxy_page.detect_proxy_in_create_dialog()
            if dialog_result == ProxyPage.FAILURE_TEXT:
                failures.append("创建弹窗检测代理结果为连接失败")
            created_proxy_serial = proxy_page.confirm_create_dialog_and_wait_new_proxy(
                protocol,
                host,
                port,
                existing_serials,
            )

            if created_proxy_serial:
                created_row = proxy_page.proxy_row_by_serial(created_proxy_serial)
                self.logger.info(
                    "Proxy custom created serial=%s type=%s host=%s port=%s",
                    created_proxy_serial,
                    created_row.get("type"),
                    host,
                    port,
                )
                assert_true(
                    created_row.get("type") == protocol,
                    f"created custom proxy type mismatch: expected={protocol}, row={created_row}",
                )

                self.logger.info("Proxy custom row detect start serial=%s", created_proxy_serial)
                row_result = proxy_page.detect_proxy_in_row(created_proxy_serial)
                self.logger.info("Proxy custom row detect result serial=%s result=%s", created_proxy_serial, row_result)
                if row_result == ProxyPage.FAILURE_TEXT:
                    failures.append("代理列表行内检测结果为连接失败")

                deleted_proxy_serial = created_proxy_serial
                self.logger.info("Proxy custom delete start serial=%s", deleted_proxy_serial)
                proxy_page.delete_proxy_by_serial(created_proxy_serial)
                created_proxy_serial = ""
                self.logger.info("Proxy custom delete finished serial=%s", deleted_proxy_serial)
                assert_true(
                    not proxy_page.proxy_exists_by_type_host_port_serial(protocol, host, port, deleted_proxy_serial),
                    "代理删除后仍存在于列表",
                )
        finally:
            try:
                if "existing_serials" in locals():
                    if created_proxy_serial:
                        self.logger.info("Proxy custom cleanup delete remaining serial=%s", created_proxy_serial)
                        proxy_page.delete_proxy_by_serial(created_proxy_serial)
            except Exception as exc:
                failures.append(f"代理清理失败: {exc}")
            try:
                if original_system_proxy_settings is not None:
                    self._restore_system_proxy(original_system_proxy_settings)
            except Exception as exc:
                failures.append(f"系统代理恢复失败: {exc}")

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

    def _enable_system_proxy_if_supported(self) -> dict[str, tuple[bool, object, int | None]] | None:
        if not system_proxy_supported():
            self.logger.info("System proxy is unsupported on this platform; continue proxy management case without it")
            return None
        proxy_server = proxy_server_from_config(self.config)
        original_settings = read_system_proxy_settings()
        self.logger.info(
            "System proxy enable proxy_server=%s original_enable=%s original_server=%s",
            proxy_server,
            original_settings.get("ProxyEnable", (False, None, None))[1],
            original_settings.get("ProxyServer", (False, None, None))[1],
        )
        enable_system_proxy(proxy_server)
        return original_settings

    def _restore_system_proxy(self, original_settings: dict[str, tuple[bool, object, int | None]]) -> None:
        current_settings = read_system_proxy_settings()
        self.logger.info(
            "System proxy restore current_enable=%s current_server=%s original_enable=%s original_server=%s",
            current_settings.get("ProxyEnable", (False, None, None))[1],
            current_settings.get("ProxyServer", (False, None, None))[1],
            original_settings.get("ProxyEnable", (False, None, None))[1],
            original_settings.get("ProxyServer", (False, None, None))[1],
        )
        restore_system_proxy_settings(original_settings)


if __name__ == "__main__":
    unittest.main()
