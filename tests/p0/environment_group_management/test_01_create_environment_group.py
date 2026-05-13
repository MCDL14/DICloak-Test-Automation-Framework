from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_group_page import EnvironmentGroupPage
from pages.login_page import LoginPage


CASE_MODULE = "环境分组管理"


class TestCreateEnvironmentGroup(unittest.TestCase):
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

    def test_create_and_delete_environment_group(self) -> None:
        group_name = "自动化-创建环境分组"
        group_page = EnvironmentGroupPage(cdp_driver=self.cdp, config=self.config)
        group_created = False

        try:
            group_page.open_list()
            group_page.delete_group_if_exists(group_name)
            group_page.wait_group_absent(group_name)

            group_page.create_group(group_name)
            group_created = True
            assert_true(group_page.group_visible(group_name), f"environment group was not created: {group_name}")

            group_page.delete_group(group_name)
            group_created = False
            assert_true(not group_page.group_visible(group_name), f"environment group was not deleted: {group_name}")
        finally:
            try:
                if group_created:
                    group_page.delete_group_if_exists(group_name)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
