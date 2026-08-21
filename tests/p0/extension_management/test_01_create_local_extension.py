from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import get_value, load_config
from core.files import local_extension_file
from core.logger import setup_logger
from pages.extension_page import ExtensionPage
from pages.login_page import LoginPage


CASE_MODULE = "扩展管理"
DEFAULT_EXTENSION_NAME = "自动化测试-创建本地上传的扩展"
DEFAULT_EXTENSION_GROUP = "未分组"


class TestCreateLocalExtension(unittest.TestCase):
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

    def test_create_local_extension_and_delete(self) -> None:
        extension_page = ExtensionPage(cdp_driver=self.cdp, config=self.config)
        package_file = local_extension_file(self.config)
        extension_name = str(
            get_value(self.config, "test_data.local_extension.extension_name", DEFAULT_EXTENSION_NAME)
            or DEFAULT_EXTENSION_NAME
        ).strip()
        created = False
        delayed_assertion: AssertionError | None = None

        try:
            assert_true(package_file.is_file(), f"本地扩展安装包不存在: {package_file}")
            assert_true(extension_name, "本地扩展名称配置不能为空")

            extension_page.open_list()
            extension_page.open_added_extensions_tab()
            extension_page.delete_extension_if_exists(extension_name)

            extension_page.add_local_extension(
                package_file=package_file,
                extension_name=extension_name,
                group_name=DEFAULT_EXTENSION_GROUP,
            )
            created = True

            assert_true(
                extension_page.extension_visible(extension_name),
                f"本地扩展创建后未在扩展列表出现: {extension_name}",
            )
            details = extension_page.extension_card_details(extension_name)
            assert_equal(
                details.get("name"),
                extension_name,
                f"扩展名称创建后列表展示错误: {details}",
            )
            try:
                assert_equal(
                    details.get("provider"),
                    "本地扩展",
                    f"本地扩展提供方展示错误: {details}",
                )
            except AssertionError as exc:
                delayed_assertion = exc

            extension_page.delete_extension(extension_name)
            created = False
            assert_true(
                not extension_page.extension_visible(extension_name),
                f"本地扩展删除后仍然存在: {extension_name}",
            )

            if delayed_assertion:
                raise delayed_assertion
        finally:
            if created:
                try:
                    extension_page.open_list()
                    extension_page.open_added_extensions_tab()
                    extension_page.delete_extension_if_exists(extension_name)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
