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


class TestFilterMemberGroup(unittest.TestCase):
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

    def test_filter_member_group(self) -> None:
        operation_group = "运营组"
        manage_group = "管理组"
        temporary_member_name = "自动化-成员分组筛选"
        temporary_member_email = "wklocxt1k+groupfilter@tempmail.cn"
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)
        created = False

        try:
            member_page.open_list()
            member_page.clear_filters()
            member_page.delete_member_if_exists(temporary_member_name)

            member_page.create_external_member(
                member_name=temporary_member_name,
                member_group=operation_group,
                email=temporary_member_email,
                environment_group="未分组",
                identity="员工",
                supervisor="外部成员1",
            )
            created = True
            member_page.clear_filters()

            member_page.filter_by_member_group(operation_group)
            operation_values = member_page.member_group_values_in_current_list()
            assert_true(operation_values, f"member group filter returned no rows: {operation_group}")
            for actual_group in operation_values:
                assert_equal(
                    actual_group,
                    operation_group,
                    f"member group filter result mismatch: expected={operation_group}, actual={actual_group}",
                )

            member_page.clear_filters()
            member_page.filter_by_member_group(manage_group)
            manage_values = member_page.member_group_values_in_current_list()
            assert_true(manage_values, f"member group filter returned no rows: {manage_group}")
            for actual_group in manage_values:
                assert_equal(
                    actual_group,
                    manage_group,
                    f"member group filter result mismatch: expected={manage_group}, actual={actual_group}",
                )

            member_page.clear_filters()
            member_page.delete_member(temporary_member_name)
            created = False
        finally:
            try:
                member_page.open_list()
                member_page.clear_filters()
                if created:
                    member_page.delete_member_if_exists(temporary_member_name)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
