from __future__ import annotations

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


class TestBatchCreateProxy(unittest.TestCase):
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

    def test_batch_create_proxy_validate_detect_and_delete(self) -> None:
        proxy_page = ProxyPage(cdp_driver=self.cdp, config=self.config)
        failures: list[str] = []
        original_system_proxy_settings = None
        created_proxy_ids: set[str] = set()
        prerequisite_proxy_ids: set[str] = set()
        existing_ids_by_target: dict[tuple[str, str], set[str]] = {}

        single_line = "HTTP://192.168.20.33:7897:test:M12345678{批量创建代理}"
        invalid_batch_text = "\n".join(
            [
                "HTTP://192.168.20.33:7897:test:M12345678}",
                "192.168.0.1:8000{备注}",
                "127.0.0.1:7890{}错误",
                "192.168.0.1:8000:Username:Password{备注}",
                "socks5://Username:Password@192.168.0.1:8000{备注}",
            ]
        )
        valid_batch_text = "\n".join(
            [
                "HTTP://192.168.20.33:7897:test:M12345678}",
                "192.168.0.1:8000{备注}",
                "127.0.0.1:7897{}",
                "192.168.0.1:8000:Username:Password{备注}",
                "socks5://Username:Password@192.168.0.1:8000{备注}",
            ]
        )
        expected_single_row = {
            "type": "HTTP",
            "host": "192.168.20.33",
            "port": "7897",
            "account": "test",
            "password": "M12345678",
            "remark": "批量创建代理",
        }
        expected_created_rows = [
            {
                "type": "HTTP",
                "host": "192.168.20.33",
                "port": "7897",
                "account": "test",
                "password": "M12345678}",
                "remark": "--",
            },
            {
                "type": "SOCKS5",
                "host": "192.168.0.1",
                "port": "8000",
                "account": "--",
                "password": "--",
                "remark": "备注",
            },
            {
                "type": "SOCKS5",
                "host": "192.168.0.1",
                "port": "8000",
                "account": "Username",
                "password": "Password",
                "remark": "备注",
            },
        ]
        expected_duplicate_rows = [
            {"type": "SOCKS5", "host": "127.0.0.1", "port": "7897"},
        ]

        try:
            proxy_page.open_list()
            for target in expected_duplicate_rows:
                prerequisite_proxy_id = self._ensure_duplicate_prerequisite(proxy_page, target)
                if prerequisite_proxy_id:
                    prerequisite_proxy_ids.add(prerequisite_proxy_id)

            for target in expected_created_rows:
                key = (target["host"], target["port"])
                existing_ids_by_target[key] = proxy_page.proxy_ids_by_host_port(*key)
            for target in expected_duplicate_rows:
                key = (target["host"], target["port"])
                existing_ids_by_target[key] = proxy_page.proxy_ids_by_host_port(*key)

            proxy_page.open_batch_create_page()
            proxy_page.fill_batch_proxy_text(single_line)
            single_rows = proxy_page.wait_batch_preview_rows(1)
            self._soft_check_batch_row(failures, single_rows[0], expected_single_row, "单条预览")

            original_system_proxy_settings = self._enable_system_proxy_if_supported()
            try:
                proxy_page.detect_batch_proxies()
                detected_rows = proxy_page.wait_batch_detection_finished()
                outbound_ip = detected_rows[0].get("outbound_ip", "") if detected_rows else ""
                self._soft_check(
                    failures,
                    self._has_actual_outbound_ip(outbound_ip),
                    f"批量创建单条检测未出现实际出口 IP: outbound_ip={outbound_ip!r}, rows={detected_rows}",
                )
            finally:
                if original_system_proxy_settings is not None:
                    self._restore_system_proxy(original_system_proxy_settings)
                    original_system_proxy_settings = None

            proxy_page.fill_batch_proxy_text(invalid_batch_text)
            validation_text = proxy_page.wait_batch_validation_error_contains("第3行格式有误")
            self._soft_check(
                failures,
                "第3行格式有误" in validation_text,
                f"批量创建格式错误提示不正确: actual={validation_text!r}",
            )

            proxy_page.fill_batch_proxy_text(valid_batch_text)
            proxy_page.wait_batch_preview_rows(5)
            result = proxy_page.confirm_batch_create()
            self._soft_check(
                failures,
                result.get("success") == 3,
                f"批量创建成功数量不正确: expected=3, actual={result}",
            )
            self._soft_check(
                failures,
                result.get("duplicate") == 2,
                f"批量创建重复数量不正确: expected=2, actual={result}",
            )
            proxy_page.confirm_batch_result_dialog()

            seen_ids_by_target: dict[tuple[str, str], set[str]] = {}
            for expected in expected_created_rows:
                key = (expected["host"], expected["port"])
                excluded_ids = set(existing_ids_by_target.get(key, set()))
                excluded_ids.update(seen_ids_by_target.get(key, set()))
                row_id = proxy_page.wait_new_proxy_visible_by_type(
                    expected["type"],
                    expected["host"],
                    expected["port"],
                    excluded_ids,
                )
                created_proxy_ids.add(row_id)
                seen_ids_by_target.setdefault(key, set()).add(row_id)
                row = proxy_page.proxy_row_by_id(row_id)
                self._soft_check_created_row(failures, row, expected, row_id)

            for expected in expected_duplicate_rows:
                current_ids = proxy_page.proxy_ids_by_type_host_port(expected["type"], expected["host"], expected["port"])
                before_ids = existing_ids_by_target.get((expected["host"], expected["port"]), set())
                self._soft_check(
                    failures,
                    current_ids == before_ids,
                    f"批量创建重复代理出现新增记录: expected_no_new={expected}, before={before_ids}, current={current_ids}",
                )

            self.logger.info("Proxy batch cleanup bulk delete ids=%s", sorted(created_proxy_ids))
            proxy_page.bulk_delete_selected_proxies(created_proxy_ids)
            for proxy_id in list(created_proxy_ids):
                self._soft_check(
                    failures,
                    not proxy_page.proxy_exists_by_id(proxy_id),
                    f"批量删除代理后记录仍存在: id={proxy_id}",
                )
                created_proxy_ids.discard(proxy_id)
        finally:
            try:
                if original_system_proxy_settings is not None:
                    self._restore_system_proxy(original_system_proxy_settings)
            except Exception as exc:
                failures.append(f"系统代理恢复失败: {exc}")
            try:
                proxy_page.return_from_batch_create()
            except Exception:
                pass
            for proxy_id in list(created_proxy_ids):
                try:
                    proxy_page.delete_proxy_by_id(proxy_id)
                    created_proxy_ids.discard(proxy_id)
                except Exception as exc:
                    failures.append(f"批量创建代理清理失败 id={proxy_id}: {exc}")
            for target in expected_created_rows:
                try:
                    proxy_page.delete_newest_proxy_by_host_port_excluding(
                        target["host"],
                        target["port"],
                        existing_ids_by_target.get((target["host"], target["port"]), set()),
                    )
                except Exception as exc:
                    failures.append(f"批量创建代理兜底清理失败 {target['host']}:{target['port']}: {exc}")
            for proxy_id in list(prerequisite_proxy_ids):
                try:
                    proxy_page.delete_proxy_by_id(proxy_id)
                    prerequisite_proxy_ids.discard(proxy_id)
                except Exception as exc:
                    failures.append(f"批量创建代理前置重复数据清理失败 id={proxy_id}: {exc}")

        assert_true(not failures, "; ".join(failures))

    def _soft_check(self, failures: list[str], condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)
            self.logger.warning(message)

    def _soft_check_batch_row(
        self,
        failures: list[str],
        row: dict[str, str],
        expected: dict[str, str],
        prefix: str,
    ) -> None:
        for field, expected_value in expected.items():
            actual_value = row.get(field, "")
            self._soft_check(
                failures,
                actual_value == expected_value,
                f"{prefix}{field}不正确: expected={expected_value!r}, actual={actual_value!r}, row={row}",
            )

    def _soft_check_created_row(
        self,
        failures: list[str],
        row: dict[str, str],
        expected: dict[str, str],
        row_id: str,
    ) -> None:
        self._soft_check(
            failures,
            bool(row),
            f"批量创建代理未在列表中找到: id={row_id}, expected={expected}",
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
                f"批量创建代理列表{field}不正确: expected={expected_value!r}, actual={actual_value!r}, row={row}",
            )
        for field in ("remark",):
            expected_value = expected[field]
            if expected_value == "--":
                continue
            actual_value = row.get(field, "")
            self._soft_check(
                failures,
                actual_value == expected_value or expected_value in text,
                f"批量创建代理列表{field}不正确: expected={expected_value!r}, actual={actual_value!r}, row={row}",
            )

    def _has_actual_outbound_ip(self, value: str) -> bool:
        clean_value = str(value or "").strip().replace("\n", " ")
        if not clean_value or clean_value in {"--", "-- --"}:
            return False
        return any(char.isdigit() for char in clean_value)

    def _ensure_duplicate_prerequisite(self, proxy_page: ProxyPage, target: dict[str, str]) -> str:
        existing_ids = proxy_page.proxy_ids_by_type_host_port(target["type"], target["host"], target["port"])
        if existing_ids:
            return ""
        proxy_page.open_create_dialog()
        proxy_page.ensure_create_dialog_proxy_type(target["type"])
        proxy_page.fill_create_dialog(target["host"], target["port"], "", "")
        proxy_page.confirm_create_dialog()
        proxy_id = proxy_page.wait_new_proxy_visible_by_type(target["type"], target["host"], target["port"], existing_ids)
        self.logger.info("Proxy batch prerequisite duplicate created id=%s target=%s", proxy_id, target)
        return proxy_id

    def _enable_system_proxy_if_supported(self) -> dict[str, tuple[bool, object, int | None]] | None:
        if not system_proxy_supported():
            self.logger.info("System proxy is unsupported on this platform; skip system proxy enable for batch proxy detection")
            return None
        proxy_server = proxy_server_from_config(self.config)
        original_settings = read_system_proxy_settings()
        self.logger.info(
            "System proxy enable for batch proxy detection proxy_server=%s original_enable=%s original_server=%s",
            proxy_server,
            original_settings.get("ProxyEnable", (False, None, None))[1],
            original_settings.get("ProxyServer", (False, None, None))[1],
        )
        enable_system_proxy(proxy_server)
        return original_settings

    def _restore_system_proxy(self, original_settings: dict[str, tuple[bool, object, int | None]]) -> None:
        current_settings = read_system_proxy_settings()
        self.logger.info(
            "System proxy restore after batch proxy detection current_enable=%s current_server=%s original_enable=%s original_server=%s",
            current_settings.get("ProxyEnable", (False, None, None))[1],
            current_settings.get("ProxyServer", (False, None, None))[1],
            original_settings.get("ProxyEnable", (False, None, None))[1],
            original_settings.get("ProxyServer", (False, None, None))[1],
        )
        restore_system_proxy_settings(original_settings)


if __name__ == "__main__":
    unittest.main()
