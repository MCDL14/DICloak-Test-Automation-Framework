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

SORT_FIELD = "环境序号"


class TestEnvironmentListSortLimit(unittest.TestCase):
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

    def test_environment_list_sort_limit(self) -> None:
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        sort_limit_saved = False
        global_settings_dirty = False
        cleanup_error: Exception | None = None

        try:
            global_settings_page.open()
            global_settings_dirty = True
            global_settings_page.configure_environment_list_sort(SORT_FIELD, "升序")
            global_settings_dirty = False
            sort_limit_saved = True

            self.cdp.reload()
            environment_page.open_list()
            hidden_states = environment_page.wait_all_header_sort_buttons_hidden()
            assert_true(
                hidden_states and not any(hidden_states.values()),
                f"header sort buttons should be hidden when environment list sort limit is enabled: {hidden_states}",
            )
            ascending_serials = environment_page.wait_environment_serials_sorted("ascending")
            assert_true(
                ascending_serials == sorted(ascending_serials),
                f"environment serials were not ascending under global sort limit: {ascending_serials}",
            )

            global_settings_page.open()
            global_settings_dirty = True
            global_settings_page.configure_environment_list_sort(SORT_FIELD, "降序")
            global_settings_dirty = False

            self.cdp.reload()
            environment_page.open_list()
            hidden_states = environment_page.wait_all_header_sort_buttons_hidden()
            assert_true(
                hidden_states and not any(hidden_states.values()),
                f"header sort buttons should stay hidden after changing sort direction: {hidden_states}",
            )
            descending_serials = environment_page.wait_environment_serials_sorted("descending")
            assert_true(
                descending_serials == sorted(descending_serials, reverse=True),
                f"environment serials were not descending under global sort limit: {descending_serials}",
            )

            global_settings_page.open()
            global_settings_dirty = True
            global_settings_page.disable_environment_list_sort()
            global_settings_dirty = False
            sort_limit_saved = False

            self.cdp.reload()
            environment_page.open_list()
            visible_states = environment_page.wait_header_sort_buttons_visible()
            assert_true(
                visible_states.get(SORT_FIELD, False),
                f"environment serial sort button should be visible after sort limit is disabled: {visible_states}",
            )
            if environment_page.environment_serial_sort_state() != "descending":
                environment_page.click_environment_serial_sort("descending")
            environment_page.wait_environment_serial_sort_state("descending")
            final_serials = environment_page.wait_environment_serials_sorted("descending")
            assert_true(
                final_serials == sorted(final_serials, reverse=True),
                f"environment serials were not descending after manual sort restore: {final_serials}",
            )
        finally:
            try:
                if sort_limit_saved:
                    global_settings_page.open()
                    global_settings_page.disable_environment_list_sort()
                    self.cdp.reload()
                    global_settings_page.open()
                    global_settings_page._wait_global_setting_states_stable()
                    assert_true(
                        not global_settings_page.environment_list_sort_enabled(),
                        "环境列表排序功能开关在用例清理后仍未关闭",
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
