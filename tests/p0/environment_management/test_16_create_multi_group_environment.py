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


class TestCreateMultiGroupEnvironment(unittest.TestCase):
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

    def test_create_multi_group_environment(self) -> None:
        data = self.config["test_data"]["environment_create_multi_group"]
        environment_name = test_name(self.config, "create-multi-group")
        environment_cleanup_prefix = cleanup_prefix(self.config, "create-multi-group")
        group_names = self._as_string_list(data.get("group_names", ["分组三", "分组二"]))
        assert_true(group_names, "multi group environment test has no group names configured")

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        environment_created = False

        try:
            environment_page.open_list()
            environment_page.search_environment_without_assert(environment_cleanup_prefix)
            environment_page.delete_environments_by_prefix_from_current_list(environment_cleanup_prefix)
            environment_page.wait_no_environment_by_prefix_in_current_list(environment_cleanup_prefix)

            initial_groups, expected_groups = environment_page.create_environment_with_groups(
                environment_name,
                group_names,
            )
            environment_created = True
            assert_true(
                set(group_names).issubset(set(expected_groups)),
                f"configured groups were not selected before submit: initial={initial_groups}, expected={expected_groups}",
            )

            environment_page.search_environment_without_assert(environment_name)
            environment_page.wait_environment_visible_in_current_list(environment_name)
            actual_group_text = environment_page.environment_group_full_text_by_name_in_current_list(environment_name)
            for expected_group in expected_groups:
                assert_true(
                    expected_group in actual_group_text,
                    "created environment group popover did not contain expected group: "
                    f"name={environment_name}, expected={expected_groups}, missing={expected_group}, "
                    f"actual={actual_group_text}",
                )

            environment_page.delete_environment_from_current_list(environment_name)
            environment_created = False
            environment_page.search_environment_without_assert(environment_name)
            assert_true(
                not environment_page.environment_visible_in_current_list(environment_name),
                f"multi group environment was not deleted: {environment_name}",
            )
        finally:
            try:
                if environment_created:
                    environment_page.search_environment_without_assert(environment_name)
                    if environment_page.environment_visible_in_current_list(environment_name):
                        environment_page.delete_environment_from_current_list(environment_name)
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
