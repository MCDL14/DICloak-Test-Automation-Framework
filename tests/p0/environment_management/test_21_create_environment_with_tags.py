from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from core.test_names import cleanup_prefix, test_name
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestCreateEnvironmentWithTags(unittest.TestCase):
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

    def test_create_environment_with_tags(self) -> None:
        data = self.config["test_data"]["environment_create_with_tags"]
        environment_name = test_name(self.config, "create-with-tags").strip()
        environment_cleanup_prefix = cleanup_prefix(self.config, "create-with-tags")
        tag_names = self._as_string_list(data.get("tag_names", ["标签1", "标签2"]))
        assert_true(bool(environment_name), "create environment with tags test has no environment name configured")
        assert_true(bool(tag_names), "create environment with tags test has no tag names configured")

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        created = False

        try:
            environment_page.open_list()
            environment_page.search_environment_without_assert(environment_cleanup_prefix)
            environment_page.delete_environments_by_prefix_from_current_list(environment_cleanup_prefix)
            environment_page.wait_no_environment_by_prefix_in_current_list(environment_cleanup_prefix)
            environment_page.clear_search()

            selected_tags = environment_page.create_environment_with_tags(environment_name, tag_names)
            assert_true(
                set(tag_names).issubset(set(selected_tags)),
                f"configured tags were not selected before submit: expected={tag_names}, selected={selected_tags}",
            )
            created = True

            environment_page.search_environment_without_assert(environment_name)
            environment_page.wait_environment_visible_in_current_list(environment_name)
            row_cells = environment_page.wait_environment_row_cells_contain(environment_name, tag_names)
            row_text = "\n".join(row_cells)
            for tag_name in tag_names:
                assert_true(
                    tag_name in row_text,
                    f"created environment tag was not visible in row: tag={tag_name}, cells={row_cells}",
                )

            environment_page.delete_environment_from_current_list(environment_name)
            created = False
            environment_page.search_environment_without_assert(environment_name)
            assert_true(
                not environment_page.environment_visible_in_current_list(environment_name),
                f"environment with tags was not deleted: {environment_name}",
            )
        finally:
            try:
                if created:
                    environment_page.search_environment_without_assert(environment_name)
                    if environment_page.environment_visible_in_current_list(environment_name):
                        environment_page.delete_environment_from_current_list(environment_name)
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

    def _as_string_list(self, value) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []


if __name__ == "__main__":
    unittest.main()
