from __future__ import annotations

import time
import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "成员管理"

NO_EDIT_USERNAME = "MCDL007"
NO_EDIT_PASSWORD = "M12345678"


class TestNoEditPermissionMember(unittest.TestCase):
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

    def test_no_edit_permission_member_ui(self) -> None:
        login_page = LoginPage(cdp_driver=self.cdp, config=self.config)
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        should_restore_config_account = False

        try:
            login_page.logout()
            time.sleep(1)

            login_page.login(username=NO_EDIT_USERNAME, password=NO_EDIT_PASSWORD)
            should_restore_config_account = True
            time.sleep(3)

            assert_true(login_page.is_logged_in(), f"{NO_EDIT_USERNAME} login failed")
            assert_true(
                bool(login_page.current_account()),
                f"{NO_EDIT_USERNAME} login succeeded but current account could not be read",
            )

            environment_page.open_list()
            environment_page.clear_search()
            serial, _ = environment_page.first_environment_serial_and_name()
            assert_true(bool(serial), "first environment serial is empty")

            environment_page.click_environment_serial_cell(serial)
            environment_page.hover_environment_row_by_serial(serial)

            quick_edit = environment_page.quick_edit_entries_in_row_by_serial(serial)
            assert_true(
                not quick_edit.get("found"),
                "quick edit entries should be hidden for no-edit-permission member: "
                f"serial={serial}, columns={quick_edit.get('columns', [])}",
            )

            environment_page.click_environment_more_by_serial(serial)
            time.sleep(0.5)
            assert_true(
                not environment_page.dropdown_item_visible("编辑"),
                f"row dropdown '编辑' should be hidden for no-edit-permission member: serial={serial}",
            )
            self.cdp.press("Escape")

            environment_page.select_environments_by_serials([serial])
            assert_true(
                not environment_page.batch_action_visible("编辑备注"),
                f"batch action '编辑备注' should be hidden for no-edit-permission member: serial={serial}",
            )

            environment_page.hover_batch_more_operation()
            time.sleep(0.5)
            for item_text in ("设置环境分组", "编辑标签", "编辑环境"):
                assert_true(
                    not environment_page.batch_more_menu_item_visible(item_text),
                    f"batch more menu '{item_text}' should be hidden for no-edit-permission member",
                )
            self.cdp.press("Escape")

            environment_page.clear_selected_environments()
            login_page.logout()
            time.sleep(1)

            login_page.login()
            time.sleep(3)
            self._assert_logged_in_as_config_account(login_page)
            should_restore_config_account = False

        finally:
            if should_restore_config_account:
                self._restore_config_account(login_page)
            self._cleanup_environment_page(environment_page)

    def _assert_logged_in_as_config_account(self, login_page: LoginPage) -> None:
        assert_true(login_page.is_logged_in(), "automation account re-login failed after test")
        final_account = login_page.current_account()
        expected_account = str(self.config.get("account", {}).get("username", "")).strip()
        assert_true(
            bool(final_account) and (not expected_account or final_account == expected_account),
            f"automation account re-login verification failed: expected={expected_account}, actual={final_account}",
        )

    @staticmethod
    def _restore_config_account(login_page: LoginPage) -> None:
        try:
            login_page.logout()
        except Exception:
            pass
        try:
            login_page.login()
            login_page.is_logged_in()
        except Exception:
            pass

    @staticmethod
    def _cleanup_environment_page(environment_page: EnvironmentPage) -> None:
        try:
            environment_page.clear_selected_environments()
        except Exception:
            pass
        try:
            environment_page.clear_search()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
