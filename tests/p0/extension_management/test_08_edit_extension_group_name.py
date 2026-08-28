from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.extension_page import ExtensionPage
from pages.login_page import LoginPage


CASE_MODULE = "扩展管理"
ORIGINAL_GROUP_NAME = "扩展分组03"
EDITED_GROUP_NAME = "自动化-修改扩展分组名称"


class TestEditExtensionGroupName(unittest.TestCase):
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

    def test_edit_extension_group_name_and_restore(self) -> None:
        extension_page = ExtensionPage(cdp_driver=self.cdp, config=self.config)
        target: dict[str, object] = {}
        restore_required = False
        primary_error: BaseException | None = None

        try:
            extension_page.open_list()
            extension_page.open_added_extensions_tab()
            extension_page.clear_added_extension_filters()
            extension_page.open_extension_group_manager()

            target = extension_page.extension_group_by_name(ORIGINAL_GROUP_NAME)
            if not target:
                stale_target = extension_page.extension_group_by_name(EDITED_GROUP_NAME)
                if stale_target:
                    extension_page.edit_extension_group_name_by_identity(
                        remark=str(stale_target["remark"]),
                        created_at=str(stale_target["created_at"]),
                        new_name=ORIGINAL_GROUP_NAME,
                        expected_current_name=EDITED_GROUP_NAME,
                    )
                    target = extension_page.extension_group_by_name(ORIGINAL_GROUP_NAME)

            assert_true(target, f"未找到待编辑扩展分组: {ORIGINAL_GROUP_NAME}")
            original_name = str(target["name"])
            remark = str(target["remark"])
            created_at = str(target["created_at"])
            assert_true(bool(created_at), f"待编辑扩展分组创建时间为空: {target}")
            assert_true(bool(target["editable"]), f"待编辑扩展分组没有编辑按钮: {target}")
            assert_true(
                not extension_page.extension_group_visible(EDITED_GROUP_NAME),
                f"自动化临时名称已被其他扩展分组占用: {EDITED_GROUP_NAME}",
            )

            restore_required = True
            extension_page.edit_extension_group_name_by_identity(
                remark=remark,
                created_at=created_at,
                new_name=EDITED_GROUP_NAME,
                expected_current_name=original_name,
            )
            changed = extension_page.extension_group_by_identity(remark, created_at)
            assert_equal(
                changed["name"],
                EDITED_GROUP_NAME,
                f"通过备注和创建时间回找后，扩展分组名称未修改成功: {changed}",
            )
            assert_equal(changed["remark"], remark, f"编辑名称后扩展分组备注发生变化: {changed}")
            assert_equal(
                changed["created_at"],
                created_at,
                f"编辑名称后扩展分组创建时间发生变化: {changed}",
            )

            extension_page.edit_extension_group_name_by_identity(
                remark=remark,
                created_at=created_at,
                new_name=original_name,
                expected_current_name=EDITED_GROUP_NAME,
            )
            restored = extension_page.extension_group_by_identity(remark, created_at)
            assert_equal(
                restored["name"],
                original_name,
                f"通过备注和创建时间回找后，扩展分组名称未还原成功: {restored}",
            )
            assert_equal(restored["remark"], remark, f"还原名称后扩展分组备注发生变化: {restored}")
            assert_equal(
                restored["created_at"],
                created_at,
                f"还原名称后扩展分组创建时间发生变化: {restored}",
            )
            restore_required = False
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            cleanup_error: Exception | None = None
            if target and restore_required:
                try:
                    extension_page.dismiss_blocking_overlays()
                    extension_page.open_list()
                    extension_page.open_added_extensions_tab()
                    extension_page.clear_added_extension_filters()
                    extension_page.open_extension_group_manager()
                    extension_page.restore_extension_group_name_if_needed(
                        remark=str(target["remark"]),
                        created_at=str(target["created_at"]),
                        original_name=str(target["name"]),
                    )
                except Exception as exc:
                    cleanup_error = exc
                    self.logger.error(
                        "Extension group name cleanup failed original_name=%r remark=%r "
                        "created_at=%r primary_error=%r cleanup_error=%r",
                        target.get("name"),
                        target.get("remark"),
                        target.get("created_at"),
                        primary_error,
                        exc,
                    )
            try:
                extension_page.dismiss_blocking_overlays()
                extension_page.open_list()
                extension_page.open_added_extensions_tab()
                extension_page.clear_added_extension_filters()
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc
                self.logger.error(
                    "Extension group name list cleanup failed primary_error=%r cleanup_error=%r",
                    primary_error,
                    exc,
                )
            if primary_error is None and cleanup_error is not None:
                raise cleanup_error


if __name__ == "__main__":
    unittest.main()
