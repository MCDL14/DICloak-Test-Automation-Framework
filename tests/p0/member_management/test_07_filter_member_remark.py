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


class TestFilterMemberRemark(unittest.TestCase):
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

    def test_filter_member_remark(self) -> None:
        remark_keyword = "必要数据"
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)

        try:
            member_page.open_list()
            member_page.clear_filters()

            member_page.filter_by_remark(remark_keyword)
            remark_values = member_page.member_remark_values_in_current_list()
            assert_true(remark_values, f"member remark filter returned no rows: {remark_keyword}")
            for actual_remark in remark_values:
                assert_true(
                    remark_keyword in actual_remark,
                    f"member remark filter result mismatch: keyword={remark_keyword}, actual={actual_remark}",
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
