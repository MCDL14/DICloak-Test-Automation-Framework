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
from tests.p0.member_management.internal_member_api_flow import (
    assert_disabled_member_cannot_login,
    configured_internal_member_id,
    login_internal_member,
    restore_automation_account,
)
from tests.p0.member_management.api_case_recovery import recover_automation_account_after_api_case
from tests.p0.member_management.member_open_api import MemberEditApiClient


CASE_MODULE = "成员管理"


class TestApiDisableInternalMember(unittest.TestCase):
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

    def test_api_disable_internal_member_blocks_login(self) -> None:
        login_page = LoginPage(cdp_driver=self.cdp, config=self.config)
        environment_group_page = EnvironmentGroupPage(cdp_driver=self.cdp, config=self.config)
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)
        api_client = MemberEditApiClient(self.config)
        target_member_id = configured_internal_member_id(self.config)
        disabled = False

        try:
            try:
                login_internal_member(login_page)

                disable_payload = api_client.edit_member(member_id=target_member_id, status="DISABLED")
                disabled = True
                assert_equal(disable_payload["status_code"], 200, f"disable member http status mismatch: {disable_payload}")
                assert_equal(disable_payload["json"].get("msg"), "success", f"disable member api msg mismatch: {disable_payload}")

                self._trigger_auto_logout(login_page, environment_group_page, environment_page)
                login_page.wait_login_page_visible()

                assert_disabled_member_cannot_login(login_page)

                enable_payload = api_client.edit_member(member_id=target_member_id, status="ENABLED")
                disabled = False
                assert_equal(enable_payload["status_code"], 200, f"enable member http status mismatch: {enable_payload}")
                assert_equal(enable_payload["json"].get("msg"), "success", f"enable member api msg mismatch: {enable_payload}")

                login_internal_member(login_page)
                assert_true(login_page.is_logged_in(), "internal member should login after enabled")

                login_page.logout_to_login_page()

                login_page.ensure_logged_in_as_config_account()
                login_page.ensure_current_team()
                member_page.open_list()

            finally:
                if disabled:
                    enable_payload = api_client.edit_member(member_id=target_member_id, status="ENABLED")
                    assert_equal(enable_payload["status_code"], 200, f"enable member http status mismatch: {enable_payload}")
                    assert_equal(enable_payload["json"].get("msg"), "success", f"enable member api msg mismatch: {enable_payload}")
                restore_automation_account(login_page, member_page)

        except Exception:
            recover_automation_account_after_api_case(api_client, login_page, member_page)
            raise

    @staticmethod
    def _try_open_page(open_func) -> None:
        try:
            open_func()
        except Exception:
            pass

    def _trigger_auto_logout(
        self,
        login_page: LoginPage,
        environment_group_page: EnvironmentGroupPage,
        environment_page: EnvironmentPage,
    ) -> None:
        if self._is_login_page_visible(login_page):
            return

        self._try_open_page(environment_group_page.open_list)
        if self._is_login_page_visible(login_page):
            return

        self._try_open_page(environment_page.open_list)
        login_page.wait_login_page_visible()

    @staticmethod
    def _is_login_page_visible(login_page: LoginPage) -> bool:
        try:
            login_page.wait_login_page_visible(timeout_seconds=2)
            return True
        except TimeoutError:
            return False


if __name__ == "__main__":
    unittest.main()
