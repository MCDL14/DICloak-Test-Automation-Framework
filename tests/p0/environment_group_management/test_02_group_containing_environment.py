from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_group_page import EnvironmentGroupPage
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境分组管理"


class TestGroupContainingEnvironment(unittest.TestCase):
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

    def test_delete_group_with_contained_environment(self) -> None:
        group_name = "自动化-包含环境的分组"
        group_page = EnvironmentGroupPage(cdp_driver=self.cdp, config=self.config)
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        group_created = False
        environment_name = ""
        environment_created = False

        try:
            group_page.open_list()
            if group_page.group_visible(group_name):
                group_page.delete_group(group_name, delete_environments=True)

            group_page.create_group(group_name)
            group_created = True
            assert_true(group_page.group_visible(group_name), f"environment group was not created: {group_name}")

            environment_page.open_list()
            environment_name, selected_groups = environment_page.create_environment_with_exact_groups_from_default_name(
                [group_name]
            )
            environment_created = True
            assert_true(
                set(selected_groups) == {group_name},
                "target group was not the only selected group before creating environment: "
                f"group={group_name}, selected={selected_groups}",
            )

            environment_page.search_environment_without_assert(environment_name)
            environment_page.wait_environment_visible_in_current_list(environment_name)
            actual_group_text = environment_page.environment_group_full_text_by_name_in_current_list(environment_name)
            assert_true(
                group_name in actual_group_text,
                "created environment group did not match expected group: "
                f"name={environment_name}, expected={group_name}, actual={actual_group_text}",
            )

            group_page.open_list()
            group_page.filter_by_containing_environment(environment_name)
            filtered_rows = group_page.group_rows_in_current_list()
            assert_true(
                filtered_rows,
                f"containing-environment filter returned no rows: environment={environment_name}",
            )
            assert_true(
                all(environment_name in row["text"] for row in filtered_rows),
                "containing-environment filter returned rows not containing target environment: "
                f"environment={environment_name}, rows={filtered_rows}",
            )
            assert_true(
                any(group_name in row["text"] for row in filtered_rows),
                "containing-environment filter did not return target group: "
                f"group={group_name}, environment={environment_name}, rows={filtered_rows}",
            )
            group_page.clear_filters()
            assert_true(group_page.group_visible(group_name), f"environment group was not visible after clearing filter: {group_name}")

            group_page.delete_group(group_name, delete_environments=True)
            group_created = False
            environment_created = False
            assert_true(not group_page.group_visible(group_name), f"environment group was not deleted: {group_name}")

            environment_page.open_list()
            environment_page.search_environment_without_assert(environment_name)
            assert_true(
                not environment_page.environment_visible_in_current_list(environment_name),
                f"environment under deleted group still exists: {environment_name}",
            )

            environment_page.clear_search()
            group_page.open_list()
        finally:
            try:
                if environment_created and environment_name:
                    environment_page.open_list()
                    environment_page.search_environment_without_assert(environment_name)
                    if environment_page.environment_visible_in_current_list(environment_name):
                        environment_page.delete_environment_from_current_list(environment_name)
            except Exception:
                pass
            try:
                if group_created:
                    group_page.open_list()
                    group_page.delete_group_if_exists(group_name, delete_environments=True)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
