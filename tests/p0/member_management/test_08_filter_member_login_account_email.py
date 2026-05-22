from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.login_page import LoginPage
from pages.member_page import MemberPage


CASE_MODULE = "成员管理"


class TestFilterMemberLoginAccountEmail(unittest.TestCase):
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

    def test_filter_member_login_account_and_email(self) -> None:
        login_account_keyword = "mcdl003"
        email_keyword = "oytrhsjwe@tempmail.cn"
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)

        try:
            member_page.open_list()
            member_page.clear_filters()

            member_page.filter_by_login_account_or_email(login_account_keyword)
            account_member_names = member_page.member_names_in_current_list()
            assert_true(account_member_names, f"member login account filter returned no rows: {login_account_keyword}")
            for member_name in account_member_names:
                member_page.open_member_edit_dialog(member_name)
                account_value = member_page.edit_dialog_field_value("登录账号")
                member_page.close_active_dialog()
                assert_true(
                    login_account_keyword in account_value,
                    "member login account filter result mismatch: "
                    f"keyword={login_account_keyword}, member={member_name}, actual={account_value}",
                )

            member_page.clear_filters()
            member_page.filter_by_login_account_or_email(email_keyword)
            email_member_names = member_page.member_names_in_current_list()
            assert_true(email_member_names, f"member email filter returned no rows: {email_keyword}")
            for member_name in email_member_names:
                member_page.open_member_edit_dialog(member_name)
                email_value = member_page.edit_dialog_field_value("成员邮箱")
                member_page.close_active_dialog()
                assert_true(
                    email_keyword in email_value,
                    "member email filter result mismatch: "
                    f"keyword={email_keyword}, member={member_name}, actual={email_value}",
                )

            member_page.clear_filters()
        finally:
            try:
                member_page.open_list()
                member_page.clear_filters()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
