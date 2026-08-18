from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_page import EnvironmentPage
from pages.global_settings_page import GlobalSettingsPage
from pages.login_page import LoginPage


CASE_MODULE = "全局设置"

LIMITED_SETTING_FIELDS = ["环境序号", "环境名称"]
LIMITED_EXPECTED_HEADERS = ["环境序号", "环境名称", "环境状态"]


class TestEnvironmentFieldDisplayLimit(unittest.TestCase):
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

    def test_environment_field_display_limit(self) -> None:
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        cleanup_error: Exception | None = None
        global_settings_snapshot: dict[str, object] | None = None

        try:
            global_settings_page.open()
            global_settings_snapshot = global_settings_page.capture_global_settings_snapshot()
            global_settings_page.disable_environment_field_display_limit()

            environment_page.open_list()
            original_headers = environment_page.environment_business_header_texts()
            assert_true(bool(original_headers), f"environment headers were not found: {original_headers}")
            assert_true(
                environment_page.column_settings_button_visible(),
                "custom list field button should be visible before environment field display limit is enabled",
            )

            global_settings_page.open()
            global_settings_page.configure_environment_field_display_limit(LIMITED_SETTING_FIELDS)

            environment_page.open_list()
            environment_page.wait_column_settings_button_hidden()
            environment_page.wait_business_headers_equal(LIMITED_EXPECTED_HEADERS)

            global_settings_page.open()
            global_settings_page.disable_environment_field_display_limit()

            environment_page.open_list()
            environment_page.wait_column_settings_button_visible()
            environment_page.verify_column_settings_button_clickable()
            environment_page.wait_business_headers_include(LIMITED_EXPECTED_HEADERS)
        finally:
            try:
                if global_settings_snapshot is not None:
                    global_settings_page.open(force_reentry=True)
                    global_settings_page.restore_global_settings_snapshot(global_settings_snapshot)
            except Exception as exc:
                cleanup_error = cleanup_error or exc
            try:
                environment_page.open_list()
            except Exception:
                pass
            if cleanup_error:
                raise cleanup_error


if __name__ == "__main__":
    unittest.main()
