from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from core.test_names import test_name
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestCreateTag(unittest.TestCase):
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

    def test_create_and_delete_tag(self) -> None:
        tag_name = test_name(self.config, "create-tag", kind="tag").strip()
        assert_true(bool(tag_name), "create tag test has no tag name configured")

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        tag_created = False

        try:
            environment_page.open_list()
            environment_page.clear_search()
            environment_page.open_tag_management()
            if environment_page.tag_exists_in_management(tag_name):
                environment_page.delete_tag(tag_name)

            environment_page.create_tag(tag_name)
            tag_created = True
            environment_page.wait_tag_visible(tag_name)

            environment_page.delete_tag(tag_name)
            tag_created = False
            environment_page.wait_tag_absent(tag_name)
        finally:
            try:
                if tag_created:
                    environment_page.delete_tag(tag_name)
            except Exception:
                pass
            try:
                environment_page.close_tag_management()
            except Exception:
                pass
            try:
                environment_page.clear_selected_environments()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
