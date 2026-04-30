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


class TestFilterEnvironmentGroup(unittest.TestCase):
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

    def test_filter_environment_group(self) -> None:
        data = self.config["test_data"]["environment_filter_group"]
        group_name = str(data.get("group_name", "自动化分组"))
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)

        try:
            environment_page.open_list()
            environment_page.clear_search()
            environment_page.filter_by_environment_group(group_name)

            group_values = environment_page.environment_group_values_in_current_list()
            assert_true(group_values, f"environment group filter returned no rows: {group_name}")
            for actual_group in group_values:
                assert_equal(
                    actual_group,
                    group_name,
                    f"environment group filter result mismatch: expected={group_name}, actual={actual_group}",
                )
        finally:
            try:
                environment_page.clear_search()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
