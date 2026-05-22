from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.login_page import LoginPage
from pages.member_page import MemberPage


CASE_MODULE = "成员管理"


class TestEditExternalMemberName(unittest.TestCase):
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

    def test_edit_external_member_name_and_restore(self) -> None:
        original_name = "外部成员1"
        edited_name = "自动化-编辑外部成员名称"
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)
        renamed = False

        try:
            member_page.open_list()
            if member_page.member_visible(edited_name) and not member_page.member_visible(original_name):
                member_page.rename_member(edited_name, original_name)

            assert_true(member_page.member_visible(original_name), f"external member was not found: {original_name}")

            member_page.rename_member(original_name, edited_name)
            renamed = True
            details = member_page.member_row_details(edited_name)
            assert_equal(details.get("name"), edited_name, f"member name was not updated in list: {details}")

            member_page.rename_member(edited_name, original_name)
            renamed = False
            details = member_page.member_row_details(original_name)
            assert_equal(details.get("name"), original_name, f"member name was not restored in list: {details}")
        finally:
            if renamed:
                try:
                    member_page.open_list()
                    if member_page.member_visible(edited_name):
                        member_page.rename_member(edited_name, original_name)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
