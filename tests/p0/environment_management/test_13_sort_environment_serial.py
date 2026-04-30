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


class TestSortEnvironmentSerial(unittest.TestCase):
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

    def test_sort_environment_serial_ascending_and_descending(self) -> None:
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)

        try:
            environment_page.open_list()
            environment_page.clear_search()

            environment_page.clear_environment_serial_sort_if_active()
            assert_equal(
                environment_page.environment_serial_sort_state(),
                "none",
                "environment serial sort state was not cleared before sort test",
            )

            environment_page.click_environment_serial_sort("ascending")
            environment_page.wait_environment_serial_sort_state("ascending")
            ascending_serials = environment_page.wait_environment_serials_sorted("ascending")
            assert_true(
                len(ascending_serials) >= 2,
                f"not enough rows to verify ascending serial sort: {ascending_serials}",
            )
            assert_true(
                ascending_serials == sorted(ascending_serials),
                f"environment serials were not ascending: {ascending_serials}",
            )

            environment_page.click_environment_serial_sort("descending")
            environment_page.wait_environment_serial_sort_state("descending")
            descending_serials = environment_page.wait_environment_serials_sorted("descending")
            assert_true(
                len(descending_serials) >= 2,
                f"not enough rows to verify descending serial sort: {descending_serials}",
            )
            assert_true(
                descending_serials == sorted(descending_serials, reverse=True),
                f"environment serials were not descending: {descending_serials}",
            )
        finally:
            try:
                if environment_page.environment_serial_sort_state() != "descending":
                    environment_page.click_environment_serial_sort("descending")
                    environment_page.wait_environment_serial_sort_state("descending")
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
