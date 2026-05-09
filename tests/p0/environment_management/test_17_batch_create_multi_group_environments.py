from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from core.test_names import cleanup_prefix, test_prefix
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestBatchCreateMultiGroupEnvironments(unittest.TestCase):
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

    def test_batch_create_multi_group_environments(self) -> None:
        data = self.config["test_data"]["environment_batch_create_multi_group"]
        name_prefix = test_prefix(self.config, "batch-create-multi-group")
        name_cleanup_prefix = cleanup_prefix(self.config, "batch-create-multi-group")
        create_count = int(data.get("create_count", 3))
        group_names = self._as_string_list(data.get("group_names", ["分组三", "分组二"]))
        assert_true(group_names, "batch multi group environment test has no group names configured")

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        created_names: list[str] = []

        try:
            environment_page.open_list()
            environment_page.search_environment_without_assert(name_cleanup_prefix)
            environment_page.delete_environments_by_prefix_from_current_list(name_cleanup_prefix)
            environment_page.wait_no_environment_by_prefix_in_current_list(name_cleanup_prefix)

            initial_groups, expected_groups = environment_page.batch_create_environments_with_groups(
                name_prefix,
                create_count,
                group_names,
            )
            assert_true(
                set(group_names).issubset(set(expected_groups)),
                f"configured groups were not selected before submit: initial={initial_groups}, expected={expected_groups}",
            )

            environment_page.search_environment_without_assert(name_prefix)
            created_names = environment_page.wait_environment_count_by_prefix_in_current_list(
                name_prefix,
                create_count,
            )
            assert_equal(
                len(created_names),
                create_count,
                f"batch created multi group environment count is incorrect: names={created_names}",
            )

            for environment_name in created_names:
                actual_group_text = environment_page.environment_group_full_text_by_name_in_current_list(environment_name)
                for expected_group in expected_groups:
                    assert_true(
                        expected_group in actual_group_text,
                        "batch created environment group popover did not contain expected group: "
                        f"name={environment_name}, expected={expected_groups}, missing={expected_group}, "
                        f"actual={actual_group_text}",
                    )

            environment_page.delete_environments_by_prefix_from_current_list(name_prefix)
            environment_page.search_environment_without_assert(name_prefix)
            assert_true(
                not environment_page.environment_names_by_prefix_in_current_list(name_prefix),
                f"batch created multi group environments were not deleted: prefix={name_prefix}",
            )
            created_names = []
        finally:
            try:
                if created_names:
                    environment_page.clear_selected_environments()
                    environment_page.search_environment_without_assert(name_prefix)
                    environment_page.delete_environments_by_prefix_from_current_list(name_prefix)
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
