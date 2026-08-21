from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.login_page import LoginPage
from pages.member_group_page import MemberGroupPage


CASE_MODULE = "成员分组管理"
MEMBER_GROUP_NAME = "自动化-创建成员分组"
MEMBER_GROUP_REMARK = "自动化-成员分组备注"


class TestCreateMemberGroup(unittest.TestCase):
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

    def test_create_member_group_and_delete(self) -> None:
        member_group_page = MemberGroupPage(cdp_driver=self.cdp, config=self.config)
        created = False

        try:
            member_group_page.open_list()
            member_group_page.delete_member_group_if_exists(MEMBER_GROUP_NAME)

            member_group_page.create_member_group(
                name=MEMBER_GROUP_NAME,
                remark=MEMBER_GROUP_REMARK,
            )
            created = True

            details = member_group_page.member_group_row_details(MEMBER_GROUP_NAME)
            assert_equal(
                details.get("成员分组名称"),
                MEMBER_GROUP_NAME,
                f"成员分组名称创建后列表展示错误: {details}",
            )
            assert_equal(
                details.get("备注"),
                MEMBER_GROUP_REMARK,
                f"成员分组备注创建后列表展示错误: {details}",
            )
            assert_true(
                member_group_page.member_group_visible(MEMBER_GROUP_NAME),
                f"成员分组创建后未在列表中出现: {MEMBER_GROUP_NAME}",
            )

            member_group_page.delete_member_group(MEMBER_GROUP_NAME)
            created = False
            assert_true(
                not member_group_page.member_group_visible(MEMBER_GROUP_NAME),
                f"成员分组删除后仍然存在: {MEMBER_GROUP_NAME}",
            )
        finally:
            if created:
                try:
                    member_group_page.open_list()
                    member_group_page.delete_member_group_if_exists(MEMBER_GROUP_NAME)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
