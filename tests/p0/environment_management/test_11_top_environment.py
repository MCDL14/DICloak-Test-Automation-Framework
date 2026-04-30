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


class TestTopEnvironment(unittest.TestCase):
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

    def test_top_and_cancel_top_environment(self) -> None:
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        target_serial = ""
        top_applied = False

        try:
            environment_page.open_list()
            environment_page.clear_search()

            target_serial = environment_page.environment_serial_at_position(3)
            assert_true(bool(target_serial), "third environment serial is empty")

            environment_page.top_environment_by_serial(target_serial)
            top_applied = True
            environment_page.wait_first_environment_serial(target_serial)
            assert_equal(
                environment_page.first_environment_serial(),
                target_serial,
                f"environment was not moved to top after top action: serial={target_serial}",
            )

            environment_page.cancel_top_environment_by_serial(target_serial)
            top_applied = False
            environment_page.wait_first_environment_serial_not(target_serial)
            assert_true(
                environment_page.first_environment_serial() != target_serial,
                f"environment was still first after cancel top action: serial={target_serial}",
            )
        finally:
            try:
                if top_applied and target_serial:
                    environment_page.cancel_top_environment_by_serial(target_serial)
                    environment_page.wait_first_environment_serial_not(target_serial)
            except Exception:
                pass
            try:
                environment_page.clear_search()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
