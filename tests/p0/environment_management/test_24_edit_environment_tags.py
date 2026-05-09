from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestEditEnvironmentTags(unittest.TestCase):
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

    def test_edit_environment_tags(self) -> None:
        data = self.config["test_data"]["environment_edit_tags"]
        target_tag_name = str(data.get("target_tag_name", "标签9")).strip()
        assert_true(bool(target_tag_name), "edit environment tag name is empty")

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        target_serial = ""
        original_tags: list[str] = []
        edited_tags: list[str] = []
        original_tags_captured = False
        restored = False

        try:
            environment_page.open_list()
            target_serial, _ = environment_page.first_environment_serial_and_name()
            assert_true(bool(target_serial), "first environment serial is empty")
            original_tags = self._unique_non_empty(environment_page.environment_tag_values_by_serial(target_serial))
            original_tags_captured = True

            desired_tags = self._unique_non_empty(original_tags + [target_tag_name])
            environment_page.edit_environment_tags_by_serial(target_serial, desired_tags)
            edited_tags = desired_tags

            actual_tags = self._wait_environment_tags_equal(environment_page, target_serial, set(desired_tags))
            assert_equal(
                set(actual_tags),
                set(desired_tags),
                f"environment tag was not edited successfully: serial={target_serial}, expected={desired_tags}, actual={actual_tags}",
            )

            environment_page.edit_environment_tags_by_serial(target_serial, original_tags)

            actual_restored_tags = self._wait_environment_tags_equal(environment_page, target_serial, set(original_tags))
            assert_equal(
                set(actual_restored_tags),
                set(original_tags),
                f"environment tag was not restored successfully: serial={target_serial}, expected={original_tags}, actual={actual_restored_tags}",
            )
            restored = True
        finally:
            try:
                if target_serial and original_tags_captured and not restored:
                    current_tags = self._unique_non_empty(environment_page.environment_tag_values_by_serial(target_serial))
                    if set(current_tags) != set(original_tags):
                        environment_page.edit_environment_tags_by_serial(target_serial, original_tags)
                elif target_serial and edited_tags and not restored:
                    environment_page.edit_environment_tags_by_serial(target_serial, original_tags)
            except Exception:
                pass
            try:
                environment_page.clear_selected_environments()
            except Exception:
                pass
            try:
                environment_page.clear_search()
            except Exception:
                pass

    def _wait_environment_tags_equal(
        self,
        environment_page: EnvironmentPage,
        serial: str,
        expected_tags: set[str],
    ) -> list[str]:
        from core.config import timeout_seconds
        import time

        deadline = time.time() + timeout_seconds(self.config, "search_result_seconds", 10)
        actual_tags: list[str] = []
        while time.time() < deadline:
            actual_tags = self._unique_non_empty(environment_page.environment_tag_values_by_serial(serial))
            if set(actual_tags) == expected_tags:
                return actual_tags
            time.sleep(0.5)
        return actual_tags

    def _unique_non_empty(self, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value).strip()
            if text and text not in result:
                result.append(text)
        return result


if __name__ == "__main__":
    unittest.main()
