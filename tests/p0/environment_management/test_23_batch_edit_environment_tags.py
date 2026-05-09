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


class TestBatchEditEnvironmentTags(unittest.TestCase):
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

    def test_batch_edit_environment_tags(self) -> None:
        data = self.config["test_data"]["environment_batch_edit_tags"]
        target_count = int(data.get("target_count", 3))
        append_tag_name = str(data.get("append_tag_name", "标签7")).strip()
        overwrite_tag_names = self._as_string_list(data.get("overwrite_tag_names", ["标签5", "标签1"]))
        final_tag_name = str(data.get("final_tag_name", "标签1")).strip()
        assert_true(target_count > 0, f"batch edit tag target count must be positive: {target_count}")
        assert_true(bool(append_tag_name), "batch edit append tag name is empty")
        assert_true(bool(overwrite_tag_names), "batch edit overwrite tag names are empty")
        assert_true(bool(final_tag_name), "batch edit final tag name is empty")

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)

        try:
            environment_page.open_list()
            target_serials = environment_page.environment_serials_at_positions(target_count)
            assert_equal(
                len(target_serials),
                target_count,
                f"target environment count is incorrect: serials={target_serials}",
            )

            original_tags_by_serial = {
                serial: environment_page.environment_tag_values_by_serial(serial)
                for serial in target_serials
            }

            environment_page.select_environments_by_serials(target_serials)
            selected_append_tags = environment_page.batch_set_environment_tags("追加标签", [append_tag_name])
            assert_true(
                append_tag_name in selected_append_tags,
                f"append tag was not selected in batch dialog: selected={selected_append_tags}",
            )

            for serial in target_serials:
                expected_tags = self._unique_non_empty(original_tags_by_serial[serial] + [append_tag_name])
                actual_tags = self._wait_environment_tags_contain(environment_page, serial, expected_tags)
                for original_tag in original_tags_by_serial[serial]:
                    assert_true(
                        original_tag in actual_tags,
                        "original environment tag was unexpectedly changed during append: "
                        f"serial={serial}, original={original_tags_by_serial[serial]}, actual={actual_tags}",
                    )
                assert_true(
                    append_tag_name in actual_tags,
                    "environment tag was not appended successfully: "
                    f"serial={serial}, expected={expected_tags}, actual={actual_tags}",
                )

            environment_page.select_environments_by_serials(target_serials)
            selected_overwrite_tags = environment_page.batch_set_environment_tags("覆盖标签", overwrite_tag_names)
            assert_true(
                set(overwrite_tag_names).issubset(set(selected_overwrite_tags)),
                f"overwrite tags were not selected in batch dialog: selected={selected_overwrite_tags}",
            )

            expected_overwrite_set = set(overwrite_tag_names)
            for serial in target_serials:
                actual_tags = self._wait_environment_tags_equal(environment_page, serial, expected_overwrite_set)
                assert_equal(
                    set(actual_tags),
                    expected_overwrite_set,
                    "environment tag was not overwritten successfully: "
                    f"serial={serial}, expected={sorted(expected_overwrite_set)}, actual={actual_tags}",
                )

            environment_page.select_environments_by_serials(target_serials)
            environment_page.batch_set_environment_tags("清空标签", [])
            for serial in target_serials:
                actual_tags = self._wait_environment_tags_equal(environment_page, serial, set())
                assert_equal(
                    actual_tags,
                    [],
                    "environment tag was not cleared successfully: "
                    f"serial={serial}, actual={actual_tags}",
                )

            environment_page.select_environments_by_serials(target_serials)
            selected_final_tags = environment_page.batch_set_environment_tags("覆盖标签", [final_tag_name])
            assert_true(
                final_tag_name in selected_final_tags,
                f"final tag was not selected in batch dialog: selected={selected_final_tags}",
            )

            expected_final_set = {final_tag_name}
            for serial in target_serials:
                actual_tags = self._wait_environment_tags_equal(environment_page, serial, expected_final_set)
                assert_equal(
                    set(actual_tags),
                    expected_final_set,
                    "environment tag was not restored to final expected value: "
                    f"serial={serial}, expected={sorted(expected_final_set)}, actual={actual_tags}",
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

    def _wait_environment_tags_contain(
        self,
        environment_page: EnvironmentPage,
        serial: str,
        expected_tags: list[str],
    ) -> list[str]:
        deadline = time.time() + timeout_seconds(self.config, "search_result_seconds", 10)
        actual_tags: list[str] = []
        expected_set = set(self._unique_non_empty(expected_tags))
        while time.time() < deadline:
            actual_tags = self._unique_non_empty(environment_page.environment_tag_values_by_serial(serial))
            if expected_set.issubset(set(actual_tags)):
                return actual_tags
            time.sleep(0.5)
        return actual_tags

    def _wait_environment_tags_equal(
        self,
        environment_page: EnvironmentPage,
        serial: str,
        expected_tags: set[str],
    ) -> list[str]:
        deadline = time.time() + timeout_seconds(self.config, "search_result_seconds", 10)
        actual_tags: list[str] = []
        while time.time() < deadline:
            actual_tags = self._unique_non_empty(environment_page.environment_tag_values_by_serial(serial))
            if set(actual_tags) == expected_tags:
                return actual_tags
            time.sleep(0.5)
        return actual_tags

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
