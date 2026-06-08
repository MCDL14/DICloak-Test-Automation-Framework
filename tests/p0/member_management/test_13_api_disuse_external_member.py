from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.app_page import AppPage
from pages.login_page import LoginPage
from pages.member_page import MemberPage
from tests.p0.member_management.api_case_recovery import recover_automation_account_after_api_case
from tests.p0.member_management.member_open_api import MemberEditApiClient, disuse_time, time_zone


CASE_MODULE = "成员管理"


class TestApiDisuseExternalMember(unittest.TestCase):
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

    def test_api_disuse_external_member_forces_logout_after_app_refresh(self) -> None:
        login_page = LoginPage(cdp_driver=self.cdp, config=self.config)
        app_page = AppPage(cdp_driver=self.cdp, config=self.config)
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)
        api_client = MemberEditApiClient(self.config)
        disuse_enabled = False
        status_enabled = False
        disuse_cleared = False

        try:
            try:
                disuse_payload = api_client.edit_member(
                    disuse_enable="true",
                    disuse_time=disuse_time(self.config),
                    time_zone=time_zone(self.config),
                )
                disuse_enabled = True
                assert_equal(disuse_payload["status_code"], 200, f"disuse member http status mismatch: {disuse_payload}")
                assert_equal(disuse_payload["json"].get("msg"), "success", f"disuse member api msg mismatch: {disuse_payload}")

                app_page.click_app_refresh_button()
                popup_text = self._try_get_force_logout_popup(login_page, timeout_seconds=5)
                if not popup_text:
                    app_page.reload_app_page()
                    popup_text = login_page.wait_force_logout_popup()
                assert_true("\u9000\u51fa\u767b\u5f55" in popup_text, f"force logout popup text mismatch: {popup_text}")
                login_page.click_force_logout_button()
                login_page.wait_login_page_visible()

                enable_payload = api_client.edit_member(status="ENABLED")
                status_enabled = True
                assert_equal(enable_payload["status_code"], 200, f"enable member http status mismatch: {enable_payload}")
                assert_equal(enable_payload["json"].get("msg"), "success", f"enable member api msg mismatch: {enable_payload}")

                # The step only requires status=ENABLED; clear expiry so the shared external member is reusable.
                clear_disuse_payload = api_client.edit_member(disuse_enable="false")
                disuse_cleared = True
                assert_equal(
                    clear_disuse_payload["status_code"],
                    200,
                    f"clear disuse http status mismatch: {clear_disuse_payload}",
                )
                assert_equal(
                    clear_disuse_payload["json"].get("msg"),
                    "success",
                    f"clear disuse api msg mismatch: {clear_disuse_payload}",
                )

                login_page.ensure_logged_in_as_config_account()
                login_page.ensure_current_team()
                member_page.open_list()

            finally:
                if disuse_enabled and not status_enabled:
                    enable_payload = api_client.edit_member(status="ENABLED")
                    assert_equal(enable_payload["status_code"], 200, f"enable member http status mismatch: {enable_payload}")
                    assert_equal(enable_payload["json"].get("msg"), "success", f"enable member api msg mismatch: {enable_payload}")
                if disuse_enabled and not disuse_cleared:
                    clear_disuse_payload = api_client.edit_member(disuse_enable="false")
                    assert_equal(
                        clear_disuse_payload["status_code"],
                        200,
                        f"clear disuse http status mismatch: {clear_disuse_payload}",
                    )
                    assert_equal(
                        clear_disuse_payload["json"].get("msg"),
                        "success",
                        f"clear disuse api msg mismatch: {clear_disuse_payload}",
                    )
                if disuse_enabled:
                    login_page.ensure_logged_in_as_config_account()
                    login_page.ensure_current_team()
                    member_page.open_list()

        except Exception:
            recover_automation_account_after_api_case(api_client, login_page, member_page)
            raise

    @staticmethod
    def _try_get_force_logout_popup(login_page: LoginPage, timeout_seconds: int) -> str:
        try:
            return login_page.wait_force_logout_popup(timeout_seconds=timeout_seconds)
        except TimeoutError:
            return ""


if __name__ == "__main__":
    unittest.main()
