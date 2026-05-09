from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestFilterEnvironmentTag(unittest.TestCase):
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

    def test_filter_environment_tag(self) -> None:
        data = self.config["test_data"]["environment_filter_tag"]
        tag_name = str(data.get("tag_name", "标签2")).strip()
        assert_true(bool(tag_name), "environment tag filter name is empty")

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)

        try:
            environment_page.open_list()
            environment_page.clear_search()
            environment_page.filter_by_tag(tag_name)

            tag_values_by_serial = environment_page.environment_tag_values_in_current_list()
            assert_true(tag_values_by_serial, f"environment tag filter returned no rows: {tag_name}")
            for serial, actual_tags in tag_values_by_serial.items():
                assert_true(
                    tag_name in actual_tags,
                    "environment tag filter result mismatch: "
                    f"serial={serial}, expected_contains={tag_name}, actual={actual_tags}",
                )
        finally:
            try:
                environment_page.clear_search()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
