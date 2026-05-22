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


class TestFilterMemberName(unittest.TestCase):
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

    def test_filter_member_name_and_id(self) -> None:
        name_keyword = "自动化成员"
        target_member_id = "1972494001272483841"
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)

        try:
            member_page.open_list()
            member_page.clear_filters()

            member_page.filter_by_member_name_or_id(name_keyword)
            name_values = member_page.member_name_id_values_in_current_list()
            assert_true(name_values, f"member name filter returned no rows: {name_keyword}")
            for value in name_values:
                assert_true(
                    name_keyword in value["name"],
                    f"member name filter result mismatch: keyword={name_keyword}, actual={value}",
                )

            member_page.clear_filters()
            member_page.filter_by_member_name_or_id(target_member_id)
            id_values = member_page.member_name_id_values_in_current_list()
            assert_true(id_values, f"member id filter returned no rows: {target_member_id}")
            for value in id_values:
                assert_equal(
                    value["id"],
                    target_member_id,
                    f"member id filter result mismatch: expected={target_member_id}, actual={value}",
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
