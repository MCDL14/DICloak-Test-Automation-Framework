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


class TestCreateExternalMember(unittest.TestCase):
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

    def test_create_external_member_and_delete(self) -> None:
        member_name = "自动化-创建外部成员"
        member_group = "运营组"
        email = "wklocxt1k@tempmail.cn"
        environment_group = "未分组"
        identity = "员工"
        supervisor = "外部成员1"
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)
        created = False

        try:
            member_page.open_list()
            member_page.delete_member_if_exists(member_name)

            member_page.create_external_member(
                member_name=member_name,
                member_group=member_group,
                email=email,
                environment_group=environment_group,
                identity=identity,
                supervisor=supervisor,
            )
            created = True

            details = member_page.member_row_details(member_name)
            assert_equal(details.get("name"), member_name, f"member name did not match in list: {details}")
            assert_equal(
                details.get("授权环境分组"),
                environment_group,
                f"member environment group did not match in list: {details}",
            )
            assert_true(
                identity in details.get("成员身份", "") and "外部成员" in details.get("成员身份", ""),
                f"member identity/type did not match in list: {details}",
            )
            assert_equal(
                details.get("所属成员分组"),
                member_group,
                f"member group did not match in list: {details}",
            )
            assert_equal(details.get("成员状态"), "启用中", f"member status did not match in list: {details}")

            member_page.open_member_edit_dialog(member_name)
            assert_equal(
                member_page.edit_dialog_field_value("成员邮箱"),
                email,
                f"member email did not match in edit dialog: {email}",
            )
            assert_true(
                member_group in member_page.edit_dialog_field_value("成员分组"),
                f"member group did not match in edit dialog: {member_group}",
            )
            assert_true(
                environment_group in member_page.edit_dialog_field_value("环境分组"),
                f"environment group did not match in edit dialog: {environment_group}",
            )
            member_page.close_active_dialog()

            member_page.delete_member(member_name)
            created = False
            assert_true(not member_page.member_visible(member_name), f"member was not deleted: {member_name}")
        finally:
            if created:
                try:
                    member_page.open_list()
                    member_page.delete_member_if_exists(member_name)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
