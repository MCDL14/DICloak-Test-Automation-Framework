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

LOCKED_PAGE_SIZE = "20 条/页"
RESTORED_PAGE_SIZE = "10条/页"


class TestEnvironmentListPaginationSetting(unittest.TestCase):
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

    def test_environment_list_pagination_setting(self) -> None:
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        pagination_setting_saved = False
        global_settings_dirty = False
        cleanup_error: Exception | None = None

        try:
            global_settings_page.open()
            global_settings_dirty = True
            global_settings_page.configure_environment_list_pagination_setting(LOCKED_PAGE_SIZE)
            global_settings_dirty = False
            pagination_setting_saved = True

            self.cdp.reload()
            environment_page.open_list()
            environment_page.wait_pagination_size_selector_hidden()
            environment_page.wait_current_page_row_count_between(min_exclusive=10, max_inclusive=20)

            global_settings_page.open()
            global_settings_dirty = True
            global_settings_page.disable_environment_list_pagination_setting()
            global_settings_dirty = False
            pagination_setting_saved = False

            self.cdp.reload()
            environment_page.open_list()
            environment_page.wait_pagination_size_selector_visible()
            environment_page.set_pagination_size(RESTORED_PAGE_SIZE)
            row_count = environment_page.wait_current_page_row_count(10)
            assert_true(row_count == 10, f"current page environment row count should be 10 after restore: {row_count}")
        finally:
            try:
                if pagination_setting_saved:
                    global_settings_page.open()
                    global_settings_page.disable_environment_list_pagination_setting()
                    global_settings_page.open()
                    global_settings_page._wait_global_setting_states_stable()
                    assert_true(
                        not global_settings_page.environment_list_pagination_setting_enabled(),
                        "环境列表分页设置功能开关在用例清理后仍未关闭",
                    )
                elif global_settings_dirty:
                    self.cdp.reload()
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
