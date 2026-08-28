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
EDITED_MEMBER_GROUP_NAME = "自动化-编辑成员分组名称"


class TestEditMemberGroupName(unittest.TestCase):
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

    def test_edit_first_member_group_name_and_restore(self) -> None:
        member_group_page = MemberGroupPage(cdp_driver=self.cdp, config=self.config)
        target: dict[str, object] = {}
        restore_required = False
        primary_error: BaseException | None = None

        try:
            member_group_page.open_list()
            target = member_group_page.first_member_group()
            original_name = str(target["name"])
            remark = str(target["remark"])
            created_at = str(target["created_at"])

            assert_true(bool(original_name), f"成员分组首行名称为空: {target}")
            assert_true(bool(created_at), f"成员分组首行创建时间为空: {target}")
            assert_true(bool(target["editable"]), f"成员分组首行没有编辑按钮: {target}")
            assert_true(
                original_name != EDITED_MEMBER_GROUP_NAME,
                f"成员分组首行已使用自动化临时名称，无法记录可还原的原名称: {target}",
            )
            assert_true(
                not member_group_page.member_group_visible(EDITED_MEMBER_GROUP_NAME),
                f"自动化临时名称已被其他成员分组占用: {EDITED_MEMBER_GROUP_NAME}",
            )

            restore_required = True
            member_group_page.edit_member_group_name_by_identity(
                remark=remark,
                created_at=created_at,
                new_name=EDITED_MEMBER_GROUP_NAME,
                expected_current_name=original_name,
            )
            changed = member_group_page.member_group_by_identity(remark, created_at)
            assert_equal(
                changed["name"],
                EDITED_MEMBER_GROUP_NAME,
                f"通过备注和创建时间回找后，成员分组名称未修改成功: {changed}",
            )
            assert_equal(changed["remark"], remark, f"编辑名称后成员分组备注发生变化: {changed}")
            assert_equal(
                changed["created_at"],
                created_at,
                f"编辑名称后成员分组创建时间发生变化: {changed}",
            )

            member_group_page.edit_member_group_name_by_identity(
                remark=remark,
                created_at=created_at,
                new_name=original_name,
                expected_current_name=EDITED_MEMBER_GROUP_NAME,
            )
            restored = member_group_page.member_group_by_identity(remark, created_at)
            assert_equal(
                restored["name"],
                original_name,
                f"通过备注和创建时间回找后，成员分组名称未还原成功: {restored}",
            )
            assert_equal(restored["remark"], remark, f"还原名称后成员分组备注发生变化: {restored}")
            assert_equal(
                restored["created_at"],
                created_at,
                f"还原名称后成员分组创建时间发生变化: {restored}",
            )
            restore_required = False
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            if target and restore_required:
                try:
                    member_group_page.open_list()
                    member_group_page.restore_member_group_name_if_needed(
                        remark=str(target["remark"]),
                        created_at=str(target["created_at"]),
                        original_name=str(target["name"]),
                    )
                except Exception as cleanup_error:
                    self.logger.error(
                        "Member group name cleanup failed original_name=%r remark=%r created_at=%r "
                        "primary_error=%r cleanup_error=%r",
                        target.get("name"),
                        target.get("remark"),
                        target.get("created_at"),
                        primary_error,
                        cleanup_error,
                    )
                    if primary_error is None:
                        raise


if __name__ == "__main__":
    unittest.main()
