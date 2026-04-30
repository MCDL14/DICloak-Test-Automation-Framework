from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.logger import setup_logger
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestQuickEditEnvironmentName(unittest.TestCase):
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

    def test_quick_edit_environment_name_and_restore(self) -> None:
        data = self.config["test_data"]["environment_quick_edit_name"]
        temporary_name = str(data.get("temporary_name", "自动化-列表快捷修改环境名称"))
        search_timeout = timeout_seconds(self.config, "search_result_seconds", 10)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        original_serial = ""
        original_name = ""
        name_changed = False

        try:
            environment_page.open_list()
            environment_page.clear_search()
            original_serial, original_name = environment_page.first_environment_serial_and_name()
            assert_true(bool(original_serial), f"first environment serial is empty: name={original_name}")
            assert_true(bool(original_name), f"first environment name is empty: serial={original_serial}")

            environment_page.quick_edit_environment_name_by_serial(original_serial, temporary_name)
            name_changed = True
            environment_page.wait_environment_name_by_serial(
                original_serial,
                temporary_name,
                timeout_seconds=search_timeout,
            )
            assert_equal(
                environment_page.environment_name_by_serial(original_serial),
                temporary_name,
                f"environment name was not changed by quick edit: serial={original_serial}",
            )

            environment_page.quick_edit_environment_name_by_serial(original_serial, original_name)
            name_changed = False
            environment_page.wait_environment_name_by_serial(
                original_serial,
                original_name,
                timeout_seconds=search_timeout,
            )
            assert_equal(
                environment_page.environment_name_by_serial(original_serial),
                original_name,
                f"environment name was not restored by quick edit: serial={original_serial}",
            )
        finally:
            if name_changed and original_serial and original_name:
                try:
                    environment_page.quick_edit_environment_name_by_serial(original_serial, original_name)
                    environment_page.wait_environment_name_by_serial(
                        original_serial,
                        original_name,
                        timeout_seconds=search_timeout,
                    )
                except Exception:
                    pass
            try:
                environment_page.clear_search()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
