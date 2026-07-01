from __future__ import annotations

import os
import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.login_page import LoginPage
from pages.proxy_page import ProxyPage


CASE_MODULE = "代理管理"


class TestBatchCreateAndBulkDetectProxy(unittest.TestCase):
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

    def test_batch_create_proxy_then_bulk_detect_and_delete(self) -> None:
        proxy_page = ProxyPage(cdp_driver=self.cdp, config=self.config)
        proxy_data = self._proxy_data()
        expected_rows = proxy_data["expected_rows"]
        created_proxy_serials: set[str] = set()
        existing_serials_by_target: dict[tuple[str, str, str], set[str]] = {}
        failures: list[str] = []

        try:
            proxy_page.open_list()
            for expected in expected_rows:
                key = (expected["type"], expected["host"], expected["port"])
                existing_serials_by_target[key] = proxy_page.proxy_serials_by_type_host_port(*key)

            proxy_page.open_batch_create_page()
            proxy_page.fill_batch_proxy_text(proxy_data["batch_text"])
            preview_rows = proxy_page.wait_batch_preview_rows(3)
            for index, expected in enumerate(expected_rows):
                preview = preview_rows[index] if index < len(preview_rows) else {}
                self._soft_check_batch_preview_row(failures, preview, expected, f"批量创建预览第{index + 1}行")

            result = proxy_page.confirm_batch_create()
            self._soft_check(
                failures,
                result.get("success") == 3,
                f"批量创建成功数量不正确: expected=3, actual={result}",
            )
            self._soft_check(
                failures,
                result.get("duplicate") == 0,
                f"批量创建重复数量不正确: expected=0, actual={result}",
            )
            proxy_page.confirm_batch_result_dialog()

            seen_serials_by_target: dict[tuple[str, str, str], set[str]] = {}
            for expected in expected_rows:
                key = (expected["type"], expected["host"], expected["port"])
                excluded_serials = set(existing_serials_by_target.get(key, set()))
                excluded_serials.update(seen_serials_by_target.get(key, set()))
                row_serial = proxy_page.wait_new_proxy_visible_by_type(
                    expected["type"],
                    expected["host"],
                    expected["port"],
                    excluded_serials,
                )
                created_proxy_serials.add(row_serial)
                seen_serials_by_target.setdefault(key, set()).add(row_serial)
                row = proxy_page.proxy_row_by_serial(row_serial)
                self._soft_check_created_row(failures, row, expected, row_serial)

            before_results = proxy_page.start_bulk_detect_selected_proxies(created_proxy_serials)
            for proxy_serial in sorted(created_proxy_serials):
                try:
                    result_text = proxy_page.wait_proxy_row_detection_finished(proxy_serial, before_results.get(proxy_serial, ""))
                    row_text = proxy_page.row_text_by_serial(proxy_serial)
                    self.logger.info("Proxy bulk detect row result serial=%s result=%s text=%s", proxy_serial, result_text, row_text)
                    self._soft_check(
                        failures,
                        self._is_success_result(result_text),
                        f"批量检测代理未连接成功: serial={proxy_serial}, result={result_text!r}, row_text={row_text!r}",
                    )
                except Exception as exc:
                    failures.append(f"批量检测代理等待失败: serial={proxy_serial}, error={exc}")
                    self.logger.warning("Proxy bulk detect wait failed serial=%s error=%s", proxy_serial, exc)

            self.logger.info("Proxy batch detect cleanup bulk delete serials=%s", sorted(created_proxy_serials))
            proxy_page.bulk_delete_selected_proxies(created_proxy_serials)
            for proxy_serial in list(created_proxy_serials):
                self._soft_check(
                    failures,
                    not proxy_page.proxy_exists_by_serial(proxy_serial),
                    f"批量检测用例删除后代理仍存在: serial={proxy_serial}",
                )
                created_proxy_serials.discard(proxy_serial)
        finally:
            try:
                proxy_page.return_from_batch_create()
            except Exception:
                pass
            for proxy_serial in list(created_proxy_serials):
                try:
                    proxy_page.delete_proxy_by_serial(proxy_serial)
                    created_proxy_serials.discard(proxy_serial)
                except Exception as exc:
                    failures.append(f"批量检测用例清理失败 serial={proxy_serial}: {exc}")
            for expected in expected_rows:
                key = (expected["type"], expected["host"], expected["port"])
                try:
                    proxy_page.delete_newest_proxy_by_host_port_excluding(
                        expected["host"],
                        expected["port"],
                        existing_serials_by_target.get(key, set()),
                        expected["type"],
                    )
                except Exception as exc:
                    failures.append(f"批量检测用例兜底清理失败 {expected['host']}:{expected['port']}: {exc}")

        assert_true(not failures, "; ".join(failures))

    def _proxy_data(self) -> dict[str, object]:
        data = self.config.get("test_data", {}).get("proxy_nodemaven", {})
        nodemaven_account = str(os.environ.get("DICLOAK_PROXY_NODEMAVEN_ACCOUNT") or data.get("account") or "").strip()
        nodemaven_password = str(os.environ.get("DICLOAK_PROXY_NODEMAVEN_PASSWORD") or data.get("password") or "").strip()
        assert_true(
            bool(nodemaven_account),
            "proxy NodeMaven account is empty; set test_data.proxy_nodemaven.account or DICLOAK_PROXY_NODEMAVEN_ACCOUNT",
        )
        assert_true(
            bool(nodemaven_password),
            "proxy NodeMaven password is empty; set test_data.proxy_nodemaven.password or DICLOAK_PROXY_NODEMAVEN_PASSWORD",
        )
        remark = "批量检测代理"
        expected_rows = [
            {
                "type": "HTTP",
                "host": "192.168.20.33",
                "port": "7897",
                "account": "--",
                "password": "--",
                "remark": remark,
            },
            {
                "type": "HTTP",
                "host": "127.0.0.1",
                "port": "7897",
                "account": "--",
                "password": "--",
                "remark": remark,
            },
            {
                "type": "HTTP",
                "host": "gate.nodemaven.com",
                "port": "8080",
                "account": nodemaven_account,
                "password": nodemaven_password,
                "remark": remark,
            },
        ]
        batch_text = "\n".join(
            [
                "HTTP://192.168.20.33:7897{批量检测代理}",
                "HTTP://127.0.0.1:7897{批量检测代理}",
                f"HTTP://gate.nodemaven.com:8080:{nodemaven_account}:{nodemaven_password}{{批量检测代理}}",
            ]
        )
        return {"batch_text": batch_text, "expected_rows": expected_rows}

    def _soft_check(self, failures: list[str], condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)
            self.logger.warning(message)

    def _soft_check_batch_preview_row(
        self,
        failures: list[str],
        row: dict[str, str],
        expected: dict[str, str],
        prefix: str,
    ) -> None:
        for field in ("type", "host", "port", "account", "password", "remark"):
            expected_value = expected[field]
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
        row_serial: str,
    ) -> None:
        self._soft_check(
            failures,
            bool(row),
            f"批量检测代理未在列表中找到: serial={row_serial}, expected={expected}",
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
                f"批量检测代理列表{field}不正确: expected={expected_value!r}, actual={actual_value!r}, row={row}",
            )
        expected_remark = expected["remark"]
        self._soft_check(
            failures,
            row.get("remark") == expected_remark or expected_remark in text,
            f"批量检测代理列表remark不正确: expected={expected_remark!r}, row={row}",
        )

    def _is_success_result(self, result: str) -> bool:
        return any(success_text in str(result or "") for success_text in ProxyPage.SUCCESS_TEXTS)


if __name__ == "__main__":
    unittest.main()
