from __future__ import annotations

import time
import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.logger import setup_logger
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestBatchEditEnvironmentMultiGroup(unittest.TestCase):
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

    def test_batch_edit_environment_multi_group(self) -> None:
        data = self.config["test_data"]["environment_batch_edit_multi_group"]
        target_count = int(data.get("target_count", 3))
        append_group_name = str(data.get("append_group_name", "分组二")).strip()
        overwrite_group_names = self._as_string_list(data.get("overwrite_group_names", ["分组三", "分组二"]))
        reset_group_name = str(data.get("reset_group_name", "未分组")).strip()
        assert_true(target_count > 0, f"batch edit target count must be positive: {target_count}")
        assert_true(bool(append_group_name), "batch edit append group name is empty")
        assert_true(bool(overwrite_group_names), "batch edit overwrite group names are empty")
        assert_true(bool(reset_group_name), "batch edit reset group name is empty")

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)

        try:
            environment_page.open_list()
            target_serials = environment_page.environment_serials_at_positions(target_count)
            assert_equal(
                len(target_serials),
                target_count,
                f"target environment count is incorrect: serials={target_serials}",
            )

            original_groups_by_serial = {
                serial: self._real_groups(environment_page.environment_group_values_by_serial(serial))
                for serial in target_serials
            }

            environment_page.select_environments_by_serials(target_serials)
            selected_append_groups = environment_page.batch_set_environment_groups("追加", [append_group_name])
            assert_true(
                append_group_name in selected_append_groups,
                f"append group was not selected in batch dialog: selected={selected_append_groups}",
            )

            for serial in target_serials:
                expected_groups = self._unique_non_empty(original_groups_by_serial[serial] + [append_group_name])
                actual_groups = self._wait_environment_groups_contain(environment_page, serial, expected_groups)
                for expected_group in expected_groups:
                    assert_true(
                        expected_group in actual_groups,
                        "environment group was not appended successfully: "
                        f"serial={serial}, expected={expected_groups}, actual={actual_groups}",
                    )

            environment_page.select_environments_by_serials(target_serials)
            selected_overwrite_groups = environment_page.batch_set_environment_groups("覆盖", overwrite_group_names)
            assert_true(
                set(overwrite_group_names).issubset(set(selected_overwrite_groups)),
                f"overwrite groups were not selected in batch dialog: selected={selected_overwrite_groups}",
            )

            expected_overwrite_set = set(overwrite_group_names)
            for serial in target_serials:
                actual_groups = self._wait_environment_groups_equal(environment_page, serial, expected_overwrite_set)
                assert_equal(
                    set(actual_groups),
                    expected_overwrite_set,
                    "environment group was not overwritten successfully: "
                    f"serial={serial}, expected={sorted(expected_overwrite_set)}, actual={actual_groups}",
                )

            environment_page.select_environments_by_serials(target_serials)
            selected_reset_groups = environment_page.batch_set_environment_groups("覆盖", [reset_group_name])
            assert_true(
                reset_group_name in selected_reset_groups,
                f"reset group was not selected in batch dialog: selected={selected_reset_groups}",
            )

            expected_reset_set = {reset_group_name}
            for serial in target_serials:
                actual_groups = self._wait_environment_groups_raw_equal(
                    environment_page,
                    serial,
                    expected_reset_set,
                )
                assert_equal(
                    set(actual_groups),
                    expected_reset_set,
                    "environment group was not reset successfully: "
                    f"serial={serial}, expected={sorted(expected_reset_set)}, actual={actual_groups}",
                )
        finally:
            try:
                environment_page.clear_selected_environments()
            except Exception:
                pass
            try:
                environment_page.clear_search()
            except Exception:
                pass

    def _wait_environment_groups_contain(
        self,
        environment_page: EnvironmentPage,
        serial: str,
        expected_groups: list[str],
    ) -> list[str]:
        deadline = time.time() + timeout_seconds(self.config, "search_result_seconds", 10)
        actual_groups: list[str] = []
        expected_set = set(self._real_groups(expected_groups))
        while time.time() < deadline:
            actual_groups = self._real_groups(environment_page.environment_group_values_by_serial(serial))
            if expected_set.issubset(set(actual_groups)):
                return actual_groups
            time.sleep(0.5)
        return actual_groups

    def _wait_environment_groups_equal(
        self,
        environment_page: EnvironmentPage,
        serial: str,
        expected_groups: set[str],
    ) -> list[str]:
        deadline = time.time() + timeout_seconds(self.config, "search_result_seconds", 10)
        actual_groups: list[str] = []
        while time.time() < deadline:
            actual_groups = self._real_groups(environment_page.environment_group_values_by_serial(serial))
            if set(actual_groups) == expected_groups:
                return actual_groups
            time.sleep(0.5)
        return actual_groups

    def _wait_environment_groups_raw_equal(
        self,
        environment_page: EnvironmentPage,
        serial: str,
        expected_groups: set[str],
    ) -> list[str]:
        deadline = time.time() + timeout_seconds(self.config, "search_result_seconds", 10)
        actual_groups: list[str] = []
        while time.time() < deadline:
            actual_groups = self._unique_non_empty(environment_page.environment_group_values_by_serial(serial))
            if set(actual_groups) == expected_groups:
                return actual_groups
            time.sleep(0.5)
        return actual_groups

    def _real_groups(self, values: list[str]) -> list[str]:
        return [value for value in self._unique_non_empty(values) if value != "未分组"]

    def _as_string_list(self, value) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []

    def _unique_non_empty(self, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value).strip()
            if text and text not in result:
                result.append(text)
        return result


if __name__ == "__main__":
    unittest.main()
