from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_group_page import EnvironmentGroupPage
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage
from pages.member_page import MemberPage
from tests.p0.member_management.api_case_recovery import recover_automation_account_after_api_case
from tests.p0.member_management.member_open_api import MemberEditApiClient


CASE_MODULE = "成员管理"

class TestApiDisableExternalMember(unittest.TestCase):
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

    def test_api_disable_external_member_forces_logout(self) -> None:
        login_page = LoginPage(cdp_driver=self.cdp, config=self.config)
        environment_group_page = EnvironmentGroupPage(cdp_driver=self.cdp, config=self.config)
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)
        api_client = MemberEditApiClient(self.config)
        disabled = False

        try:
            try:
                disable_payload = api_client.edit_member(status="DISABLED")
                disabled = True
                assert_equal(disable_payload["status_code"], 200, f"disable member http status mismatch: {disable_payload}")
                assert_equal(disable_payload["json"].get("msg"), "success", f"disable member api msg mismatch: {disable_payload}")

                popup_text = self._trigger_force_logout_popup(login_page, environment_group_page, environment_page)
                assert_true("\u9000\u51fa\u767b\u5f55" in popup_text, f"force logout popup text mismatch: {popup_text}")
                login_page.click_force_logout_button()
                login_page.wait_login_page_visible()

            finally:
                if disabled:
                    enable_payload = api_client.edit_member(status="ENABLED")
                    assert_equal(enable_payload["status_code"], 200, f"enable member http status mismatch: {enable_payload}")
                    assert_equal(enable_payload["json"].get("msg"), "success", f"enable member api msg mismatch: {enable_payload}")
                login_page.ensure_logged_in_as_config_account()
                login_page.ensure_current_team()
                member_page.open_list()

        except Exception:
            recover_automation_account_after_api_case(api_client, login_page, member_page)
            raise

    @staticmethod
    def _try_open_page(open_func) -> None:
        try:
            open_func()
        except Exception:
            pass

    def _trigger_force_logout_popup(
        self,
        login_page: LoginPage,
        environment_group_page: EnvironmentGroupPage,
        environment_page: EnvironmentPage,
    ) -> str:
        popup_text = self._try_get_force_logout_popup(login_page, timeout_seconds=2)
        if popup_text:
            return popup_text

        self._try_open_page(environment_group_page.open_list)
        popup_text = self._try_get_force_logout_popup(login_page, timeout_seconds=3)
        if popup_text:
            return popup_text

        self._try_open_page(environment_page.open_list)
        return login_page.wait_force_logout_popup()

    @staticmethod
    def _try_get_force_logout_popup(login_page: LoginPage, timeout_seconds: int) -> str:
        try:
            return login_page.wait_force_logout_popup(timeout_seconds=timeout_seconds)
        except TimeoutError:
            return ""


if __name__ == "__main__":
    unittest.main()
