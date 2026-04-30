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


class TestFilterEnvironmentRemark(unittest.TestCase):
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

    def test_filter_environment_remark(self) -> None:
        data = self.config["test_data"]["environment_filter_remark"]
        remark_keyword = str(data.get("remark_keyword", "备注UI自动化")).strip()
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)

        try:
            environment_page.open_list()
            environment_page.clear_search()
            environment_page.filter_by_remark_keyword(remark_keyword)

            remark_values = environment_page.environment_remark_values_in_current_list()
            assert_true(remark_values, f"environment remark filter returned no rows: {remark_keyword}")
            for actual_remark in remark_values:
                assert_true(
                    remark_keyword in actual_remark,
                    "environment remark filter result mismatch: "
                    f"expected_contains={remark_keyword}, actual={actual_remark}",
                )
        finally:
            try:
                environment_page.clear_search()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
