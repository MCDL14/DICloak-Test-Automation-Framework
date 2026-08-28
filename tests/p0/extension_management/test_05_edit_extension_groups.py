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
EXTENSION_NAME = "Cookie-Editor"
ADDED_EXTENSION_GROUP = "扩展分组01"


class TestEditExtensionAssignedGroups(unittest.TestCase):
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

    def test_edit_extension_assigned_groups_and_restore(self) -> None:
        extension_page = ExtensionPage(cdp_driver=self.cdp, config=self.config)
        original_groups: list[str] = []
        restore_required = False
        primary_error: BaseException | None = None

        try:
            extension_page.open_list()
            extension_page.open_added_extensions_tab()
            extension_page.clear_added_extension_filters()
            extension_page.search_added_extension(EXTENSION_NAME)
            assert_true(
                extension_page.extension_exact_name_visible(EXTENSION_NAME),
                f"搜索后未找到目标扩展: {EXTENSION_NAME}",
            )

            extension_page.open_extension_edit_dialog(EXTENSION_NAME)
            original_groups = extension_page.dialog_extension_groups()
            assert_true(original_groups, f"目标扩展没有已选择的扩展分组: {EXTENSION_NAME}")
            assert_true(
                ADDED_EXTENSION_GROUP not in original_groups,
                f"待追加的扩展分组已经属于目标扩展，无法验证追加和移除: "
                f"extension={EXTENSION_NAME}, groups={original_groups}",
            )
            original_filter_group = original_groups[0]

            restore_required = True
            expected_groups = [*original_groups, ADDED_EXTENSION_GROUP]
            extension_page.set_dialog_extension_groups(expected_groups)
            assert_equal(
                set(extension_page.dialog_extension_groups()),
                set(expected_groups),
                "保存前编辑弹窗里的扩展分组未按预期追加",
            )
            extension_page.save_extension_edit()

            extension_page.filter_added_extensions_by_group(original_filter_group)
            extension_page.wait_extension_visible(EXTENSION_NAME)
            assert_true(
                extension_page.extension_exact_name_visible(EXTENSION_NAME),
                f"按原扩展分组筛选后未找到目标扩展: "
                f"extension={EXTENSION_NAME}, group={original_filter_group}",
            )

            extension_page.filter_added_extensions_by_group(ADDED_EXTENSION_GROUP)
            extension_page.wait_extension_visible(EXTENSION_NAME)
            assert_true(
                extension_page.extension_exact_name_visible(EXTENSION_NAME),
                f"按新增扩展分组筛选后未找到目标扩展: "
                f"extension={EXTENSION_NAME}, group={ADDED_EXTENSION_GROUP}",
            )

            extension_page.open_extension_edit_dialog(EXTENSION_NAME)
            assert_equal(
                set(extension_page.dialog_extension_groups()),
                set(expected_groups),
                "再次打开编辑弹窗后扩展分组没有正确回显",
            )
            extension_page.set_dialog_extension_groups(original_groups)
            assert_equal(
                set(extension_page.dialog_extension_groups()),
                set(original_groups),
                "保存前编辑弹窗里的扩展分组未恢复为原集合",
            )
            extension_page.save_extension_edit()

            extension_page.filter_added_extensions_by_group(ADDED_EXTENSION_GROUP)
            extension_page.wait_extension_absent(EXTENSION_NAME)
            assert_true(
                not extension_page.extension_exact_name_visible(EXTENSION_NAME),
                f"移除新增分组后，按该分组筛选仍然找到目标扩展: "
                f"extension={EXTENSION_NAME}, group={ADDED_EXTENSION_GROUP}",
            )
            restore_required = False
            extension_page.clear_added_extension_filters()
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            cleanup_error: Exception | None = None
            if restore_required and original_groups:
                try:
                    extension_page.restore_extension_groups_if_needed(
                        EXTENSION_NAME,
                        original_groups,
                    )
                except Exception as exc:
                    cleanup_error = exc
                    self.logger.error(
                        "Extension group cleanup failed extension=%r original_groups=%r "
                        "primary_error=%r cleanup_error=%r",
                        EXTENSION_NAME,
                        original_groups,
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
                    "Extension list filter cleanup failed extension=%r primary_error=%r cleanup_error=%r",
                    EXTENSION_NAME,
                    primary_error,
                    exc,
                )
            if primary_error is None and cleanup_error is not None:
                raise cleanup_error


if __name__ == "__main__":
    unittest.main()
