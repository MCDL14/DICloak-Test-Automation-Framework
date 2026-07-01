from __future__ import annotations

import os
import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from core.system_proxy import (
    disable_system_proxy,
    enable_system_proxy,
    proxy_server_from_config,
    read_system_proxy_settings,
    restore_system_proxy_settings,
    system_proxy_supported,
)
from pages.login_page import LoginPage
from pages.proxy_page import ProxyPage


CASE_MODULE = "代理管理"


class TestCreateNodeMavenProxy(unittest.TestCase):
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

    def test_create_nodemaven_proxy_detect_and_delete(self) -> None:
        proxy_page = ProxyPage(cdp_driver=self.cdp, config=self.config)
        proxy_data = self._proxy_data()
        proxy_type = proxy_data["type"]
        host = proxy_data["host"]
        port = proxy_data["port"]
        account = proxy_data["account"]
        password = proxy_data["password"]
        country = proxy_data["country"]
        expected_dialog_country = proxy_data["expected_dialog_country"]
        expected_row_country = proxy_data["expected_row_country"]
        remark = proxy_data["remark"]
        created_proxy_serial = ""
        failures: list[str] = []
        original_system_proxy_settings = None
        existing_serials: set[str] = set()

        try:
            proxy_page.open_list()
            existing_serials = proxy_page.proxy_serials_by_type_host_port(proxy_type, host, port)

            proxy_page.open_create_dialog()
            proxy_page.ensure_create_dialog_proxy_type(proxy_type)
            proxy_page.fill_create_dialog(host, port, account, password)
            proxy_page.select_create_dialog_country(country)
            proxy_page.fill_create_dialog_remark(remark)

            original_system_proxy_settings = self._enable_system_proxy_if_supported()
            dialog_result = proxy_page.detect_proxy_in_create_dialog()
            dialog_text = proxy_page.create_dialog_text()
            self.logger.info("NodeMaven create dialog detect result=%s text=%s", dialog_result, dialog_text)
            if dialog_result == ProxyPage.FAILURE_TEXT:
                failures.append("创建 NodeMaven 代理弹窗检测结果为连接失败")
            elif not self._is_success_result(dialog_result):
                failures.append(f"创建 NodeMaven 代理弹窗检测结果不明确: {dialog_result!r}")
            if self._is_success_result(dialog_result):
                self._soft_check(
                    failures,
                    expected_dialog_country in dialog_text,
                    f"NodeMaven 弹窗检测成功后国家/地区不正确: expected={expected_dialog_country!r}, text={dialog_text!r}",
                )

            if proxy_page.try_confirm_create_dialog(timeout_seconds=8):
                created_proxy_serial = proxy_page.wait_new_proxy_visible_by_type(proxy_type, host, port, existing_serials)
            else:
                proxy_page.cancel_create_dialog()

            self._soft_check(failures, bool(created_proxy_serial), "NodeMaven 代理未创建成功，无法继续列表校验和行内检测")
            if created_proxy_serial:
                row = proxy_page.proxy_row_by_serial(created_proxy_serial)
                self._soft_check_created_row(
                    failures,
                    row,
                    {
                        "type": proxy_type.upper(),
                        "host": host,
                        "port": port,
                        "remark": remark,
                    },
                    created_proxy_serial,
                )

                self.logger.info("NodeMaven row detect start serial=%s", created_proxy_serial)
                row_result = proxy_page.detect_proxy_in_row(created_proxy_serial)
                row_text = proxy_page.row_text_by_serial(created_proxy_serial)
                self.logger.info("NodeMaven row detect result serial=%s result=%s text=%s", created_proxy_serial, row_result, row_text)
                if row_result == ProxyPage.FAILURE_TEXT:
                    failures.append("NodeMaven 代理列表行内检测结果为连接失败")
                elif not self._is_success_result(row_result):
                    failures.append(f"NodeMaven 代理列表行内检测结果不明确: {row_result!r}")
                if self._is_success_result(row_result):
                    self._soft_check(
                        failures,
                        expected_row_country in row_text,
                        f"NodeMaven 行内检测成功后出口 IP 列国家/地区不正确: expected={expected_row_country!r}, text={row_text!r}",
                    )

                if original_system_proxy_settings is not None:
                    self._disable_system_proxy_before_delete()

                deleted_proxy_serial = created_proxy_serial
                self.logger.info("NodeMaven delete start serial=%s", deleted_proxy_serial)
                proxy_page.delete_proxy_by_serial(created_proxy_serial)
                created_proxy_serial = ""
                self.logger.info("NodeMaven delete finished serial=%s", deleted_proxy_serial)
                self._soft_check(
                    failures,
                    not proxy_page.proxy_exists_by_serial(deleted_proxy_serial),
                    f"NodeMaven 代理删除后仍存在: serial={deleted_proxy_serial}",
                )
        finally:
            try:
                if original_system_proxy_settings is not None and created_proxy_serial:
                    self._disable_system_proxy_before_delete()
                if created_proxy_serial:
                    self.logger.info("NodeMaven cleanup delete remaining serial=%s", created_proxy_serial)
                    proxy_page.delete_proxy_by_serial(created_proxy_serial)
                    created_proxy_serial = ""
            except Exception as exc:
                failures.append(f"NodeMaven 代理清理失败 serial={created_proxy_serial}: {exc}")
            try:
                if original_system_proxy_settings is not None:
                    self._disable_system_proxy_before_delete()
                proxy_page.delete_newest_proxy_by_host_port_excluding(host, port, existing_serials, proxy_type)
            except Exception as exc:
                failures.append(f"NodeMaven 代理兜底清理失败 {host}:{port}: {exc}")
            try:
                if original_system_proxy_settings is not None:
                    self._restore_system_proxy(original_system_proxy_settings)
            except Exception as exc:
                failures.append(f"系统代理恢复失败: {exc}")

        assert_true(not failures, "; ".join(failures))

    def _soft_check(self, failures: list[str], condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)
            self.logger.warning(message)

    def _soft_check_created_row(
        self,
        failures: list[str],
        row: dict[str, str],
        expected: dict[str, str],
        row_serial: str,
    ) -> None:
        self._soft_check(
            failures,
            bool(row),
            f"NodeMaven 代理未在列表中找到: serial={row_serial}, expected={expected}",
        )
        if not row:
            return
        text = row.get("text", "")
        for field in ("type", "host", "port"):
            expected_value = expected[field]
            actual_value = row.get(field, "")
            self._soft_check(
                failures,
                actual_value == expected_value,
                f"NodeMaven 代理列表{field}不正确: expected={expected_value!r}, actual={actual_value!r}, row={row}",
            )
        self._soft_check(
            failures,
            expected["remark"] in text or row.get("remark") == expected["remark"],
            f"NodeMaven 代理列表备注不正确: expected={expected['remark']!r}, row={row}",
        )

    def _is_success_result(self, result: str) -> bool:
        return any(success_text in str(result or "") for success_text in ProxyPage.SUCCESS_TEXTS)

    def _proxy_data(self) -> dict[str, str]:
        data = self.config.get("test_data", {}).get("proxy_nodemaven", {})
        proxy_type = str(data.get("type") or "NodeMaven").strip()
        host = str(data.get("host") or "gate.nodemaven.com").strip()
        port = str(data.get("port") or "8080").strip()
        account = str(os.environ.get("DICLOAK_PROXY_NODEMAVEN_ACCOUNT") or data.get("account") or "").strip()
        password = str(os.environ.get("DICLOAK_PROXY_NODEMAVEN_PASSWORD") or data.get("password") or "").strip()
        assert_true(
            bool(account),
            "proxy NodeMaven account is empty; set test_data.proxy_nodemaven.account or DICLOAK_PROXY_NODEMAVEN_ACCOUNT",
        )
        assert_true(
            bool(password),
            "proxy NodeMaven password is empty; set test_data.proxy_nodemaven.password or DICLOAK_PROXY_NODEMAVEN_PASSWORD",
        )
        return {
            "type": proxy_type,
            "host": host,
            "port": port,
            "account": account,
            "password": password,
            "country": str(data.get("country") or "美国").strip(),
            "expected_dialog_country": str(data.get("expected_dialog_country") or "United States(US)").strip(),
            "expected_row_country": str(data.get("expected_row_country") or "US-United States").strip(),
            "remark": str(data.get("remark") or "自动化-创建动态代理NodeMaven").strip(),
        }

    def _enable_system_proxy_if_supported(self) -> dict[str, tuple[bool, object, int | None]] | None:
        if not system_proxy_supported():
            self.logger.info("System proxy is unsupported on this platform; skip system proxy enable for NodeMaven detection")
            return None
        proxy_server = proxy_server_from_config(self.config)
        original_settings = read_system_proxy_settings()
        self.logger.info(
            "System proxy enable for NodeMaven detection proxy_server=%s original_enable=%s original_server=%s",
            proxy_server,
            original_settings.get("ProxyEnable", (False, None, None))[1],
            original_settings.get("ProxyServer", (False, None, None))[1],
        )
        enable_system_proxy(proxy_server)
        return original_settings

    def _restore_system_proxy(self, original_settings: dict[str, tuple[bool, object, int | None]]) -> None:
        current_settings = read_system_proxy_settings()
        self.logger.info(
            "System proxy restore after NodeMaven detection current_enable=%s current_server=%s original_enable=%s original_server=%s",
            current_settings.get("ProxyEnable", (False, None, None))[1],
            current_settings.get("ProxyServer", (False, None, None))[1],
            original_settings.get("ProxyEnable", (False, None, None))[1],
            original_settings.get("ProxyServer", (False, None, None))[1],
        )
        restore_system_proxy_settings(original_settings)

    def _disable_system_proxy_before_delete(self) -> None:
        current_settings = read_system_proxy_settings()
        self.logger.info(
            "System proxy disable before NodeMaven delete current_enable=%s current_server=%s",
            current_settings.get("ProxyEnable", (False, None, None))[1],
            current_settings.get("ProxyServer", (False, None, None))[1],
        )
        disable_system_proxy()


if __name__ == "__main__":
    unittest.main()
