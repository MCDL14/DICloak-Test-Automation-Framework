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
BATCH_CREATE_WITH_TAGS_PREFIX = "自动化-批量创建带有标签的环境"


class TestBatchCreateEnvironmentsWithTags(unittest.TestCase):
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

    def test_batch_create_environments_with_tags(self) -> None:
        data = self.config["test_data"]["environment_batch_create_with_tags"]
        create_count = int(data.get("create_count", 3))
        tag_names = self._as_string_list(data.get("tag_names", ["标签1", "标签2"]))
        assert_true(create_count > 0, f"batch create with tags count must be positive: {create_count}")
        assert_true(bool(tag_names), "batch create with tags test has no tag names configured")

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        created_names: list[str] = []

        try:
            environment_page.open_list()
            environment_page.search_environment_without_assert(BATCH_CREATE_WITH_TAGS_PREFIX)
            environment_page.delete_environments_by_prefix_from_current_list(BATCH_CREATE_WITH_TAGS_PREFIX)
            environment_page.wait_no_environment_by_prefix_in_current_list(BATCH_CREATE_WITH_TAGS_PREFIX)

            selected_tags = environment_page.batch_create_environments_with_tags(
                BATCH_CREATE_WITH_TAGS_PREFIX,
                create_count,
                tag_names,
            )
            assert_true(
                set(tag_names).issubset(set(selected_tags)),
                f"configured tags were not selected before submit: expected={tag_names}, selected={selected_tags}",
            )

            environment_page.search_environment_without_assert(BATCH_CREATE_WITH_TAGS_PREFIX)
            created_names = environment_page.wait_environment_count_by_prefix_in_current_list(
                BATCH_CREATE_WITH_TAGS_PREFIX,
                create_count,
            )
            assert_equal(
                len(created_names),
                create_count,
                f"batch created environment count is incorrect: names={created_names}",
            )
            for environment_name in created_names:
                assert_true(
                    environment_name.startswith(BATCH_CREATE_WITH_TAGS_PREFIX),
                    f"created environment name did not start with expected prefix: {environment_name}",
                )
                row_cells = environment_page.wait_environment_row_cells_contain(environment_name, tag_names)
                row_text = "\n".join(row_cells)
                for tag_name in tag_names:
                    assert_true(
                        tag_name in row_text,
                        f"batch created environment tag was not visible in row: "
                        f"name={environment_name}, tag={tag_name}, cells={row_cells}",
                    )

            environment_page.delete_environments_by_prefix_from_current_list(BATCH_CREATE_WITH_TAGS_PREFIX)
            environment_page.search_environment_without_assert(BATCH_CREATE_WITH_TAGS_PREFIX)
            assert_true(
                not environment_page.environment_names_by_prefix_in_current_list(BATCH_CREATE_WITH_TAGS_PREFIX),
                f"batch created environments with tags were not deleted: prefix={BATCH_CREATE_WITH_TAGS_PREFIX}",
            )
            created_names = []
        finally:
            try:
                if created_names:
                    environment_page.clear_selected_environments()
                    environment_page.search_environment_without_assert(BATCH_CREATE_WITH_TAGS_PREFIX)
                    environment_page.delete_environments_by_prefix_from_current_list(BATCH_CREATE_WITH_TAGS_PREFIX)
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
