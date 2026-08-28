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
GROUP_NAME = "自动化-创建扩展分组"
GROUP_REMARK = "自动化-扩展分组备注"


class TestCreateExtensionGroup(unittest.TestCase):
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

    def test_create_extension_group_and_delete(self) -> None:
        extension_page = ExtensionPage(cdp_driver=self.cdp, config=self.config)
        cleanup_required = False
        primary_error: BaseException | None = None

        try:
            extension_page.open_list()
            extension_page.open_added_extensions_tab()
            extension_page.open_extension_group_manager()
            extension_page.delete_extension_group_if_exists(GROUP_NAME)
            extension_page.wait_extension_group_absent(GROUP_NAME)

            cleanup_required = True
            extension_page.create_extension_group(GROUP_NAME, GROUP_REMARK)
            created_group = extension_page.extension_group_by_name(GROUP_NAME)
            assert_true(created_group, f"创建后未找到扩展分组: {GROUP_NAME}")
            assert_equal(
                created_group.get("name"),
                GROUP_NAME,
                f"创建后的扩展分组名称错误: {created_group}",
            )
            assert_equal(
                created_group.get("remark"),
                GROUP_REMARK,
                f"创建后的扩展分组备注错误: {created_group}",
            )
            assert_true(
                bool(created_group.get("deletable")),
                f"新建扩展分组没有第二个删除操作按钮: {created_group}",
            )

            extension_page.delete_extension_group(GROUP_NAME)
            cleanup_required = False
            assert_true(
                not extension_page.extension_group_visible(GROUP_NAME),
                f"删除后扩展分组仍然存在: {GROUP_NAME}",
            )
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            cleanup_error: Exception | None = None
            if cleanup_required:
                try:
                    extension_page.dismiss_blocking_overlays()
                    extension_page.open_list()
                    extension_page.open_added_extensions_tab()
                    extension_page.open_extension_group_manager()
                    extension_page.delete_extension_group_if_exists(GROUP_NAME)
                except Exception as exc:
                    cleanup_error = exc
                    self.logger.error(
                        "Extension group cleanup failed name=%r primary_error=%r cleanup_error=%r",
                        GROUP_NAME,
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
                    "Extension group list cleanup failed name=%r primary_error=%r cleanup_error=%r",
                    GROUP_NAME,
                    primary_error,
                    exc,
                )
            if primary_error is None and cleanup_error is not None:
                raise cleanup_error


if __name__ == "__main__":
    unittest.main()
