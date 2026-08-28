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
ORIGINAL_EXTENSION_NAME = "ZeroOmega"
EDITED_EXTENSION_NAME = "自动化-编辑本地扩展名称"


class TestEditLocalExtensionName(unittest.TestCase):
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

    def test_edit_local_extension_name_and_restore(self) -> None:
        extension_page = ExtensionPage(cdp_driver=self.cdp, config=self.config)
        original_version = ""
        original_description = ""
        restore_required = False
        primary_error: BaseException | None = None

        try:
            extension_page.open_list()
            extension_page.open_added_extensions_tab()
            extension_page.clear_added_extension_filters()
            extension_page.search_added_extension(ORIGINAL_EXTENSION_NAME)
            extension_page.wait_extension_visible(ORIGINAL_EXTENSION_NAME)
            assert_true(
                extension_page.extension_exact_name_visible(ORIGINAL_EXTENSION_NAME),
                f"搜索后未找到目标本地扩展: {ORIGINAL_EXTENSION_NAME}",
            )
            original_details = extension_page.extension_card_details(ORIGINAL_EXTENSION_NAME)
            assert_equal(
                original_details.get("name"),
                ORIGINAL_EXTENSION_NAME,
                f"目标扩展卡片名称解析错误: {original_details}",
            )
            original_version = str(original_details.get("version") or "").strip()
            original_description = str(original_details.get("description") or "").strip()
            assert_true(original_version, f"目标扩展版本号为空: {original_details}")
            assert_true(original_description, f"目标扩展详情为空: {original_details}")

            extension_page.search_added_extension(EDITED_EXTENSION_NAME)
            assert_true(
                not extension_page.extension_exact_name_visible(EDITED_EXTENSION_NAME),
                f"待使用的新扩展名称已经存在: {EDITED_EXTENSION_NAME}",
            )
            extension_page.search_added_extension(ORIGINAL_EXTENSION_NAME)
            extension_page.wait_extension_visible(ORIGINAL_EXTENSION_NAME)

            extension_page.open_extension_edit_dialog(ORIGINAL_EXTENSION_NAME)
            extension_page.wait_dialog_extension_name(ORIGINAL_EXTENSION_NAME)
            restore_required = True
            extension_page.set_dialog_extension_name(EDITED_EXTENSION_NAME)
            extension_page.save_extension_edit()

            extension_page.search_added_extension(EDITED_EXTENSION_NAME)
            extension_page.wait_extension_visible(EDITED_EXTENSION_NAME)
            self._assert_extension_metadata(
                extension_page,
                name=EDITED_EXTENSION_NAME,
                expected_version=original_version,
                expected_description=original_description,
            )

            extension_page.open_extension_edit_dialog(EDITED_EXTENSION_NAME)
            extension_page.wait_dialog_extension_name(EDITED_EXTENSION_NAME)
            extension_page.set_dialog_extension_name(ORIGINAL_EXTENSION_NAME)
            extension_page.save_extension_edit()

            extension_page.search_added_extension(ORIGINAL_EXTENSION_NAME)
            extension_page.wait_extension_visible(ORIGINAL_EXTENSION_NAME)
            self._assert_extension_metadata(
                extension_page,
                name=ORIGINAL_EXTENSION_NAME,
                expected_version=original_version,
                expected_description=original_description,
            )
            restore_required = False
            extension_page.clear_added_extension_filters()
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            cleanup_error: Exception | None = None
            if restore_required:
                try:
                    extension_page.restore_extension_name_if_needed(
                        ORIGINAL_EXTENSION_NAME,
                        EDITED_EXTENSION_NAME,
                    )
                except Exception as exc:
                    cleanup_error = exc
                    self.logger.error(
                        "Extension name cleanup failed original=%r edited=%r "
                        "primary_error=%r cleanup_error=%r",
                        ORIGINAL_EXTENSION_NAME,
                        EDITED_EXTENSION_NAME,
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
                    "Extension list cleanup failed original=%r primary_error=%r cleanup_error=%r",
                    ORIGINAL_EXTENSION_NAME,
                    primary_error,
                    exc,
                )
            if primary_error is None and cleanup_error is not None:
                raise cleanup_error

    def _assert_extension_metadata(
        self,
        extension_page: ExtensionPage,
        *,
        name: str,
        expected_version: str,
        expected_description: str,
    ) -> None:
        assert_true(
            extension_page.extension_exact_name_visible(name),
            f"扩展列表没有精确展示目标名称: {name}",
        )
        details = extension_page.extension_card_details(name)
        assert_equal(details.get("name"), name, f"扩展名称展示错误: {details}")
        assert_equal(
            details.get("version"),
            expected_version,
            f"编辑扩展名称后版本号发生变化: {details}",
        )
        assert_equal(
            details.get("description"),
            expected_description,
            f"编辑扩展名称后扩展详情发生变化: {details}",
        )


if __name__ == "__main__":
    unittest.main()
