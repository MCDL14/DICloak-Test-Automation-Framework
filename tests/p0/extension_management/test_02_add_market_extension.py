from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import get_value, load_config
from core.logger import setup_logger
from pages.extension_page import ExtensionPage
from pages.login_page import LoginPage


CASE_MODULE = "扩展管理"
DEFAULT_EXTENSION_NAME = "网页元素隐藏器"
DEFAULT_EXTENSION_DESCRIPTION = "通过网页元素隐藏器，可隐藏多个网站的敏感操作或内容，防止隐私泄露（将对绑定该扩展的所有环境生效）"
DEFAULT_EXTENSION_GROUP = "未分组"


class TestAddMarketExtension(unittest.TestCase):
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

    def test_add_market_extension_and_delete(self) -> None:
        extension_page = ExtensionPage(cdp_driver=self.cdp, config=self.config)
        extension_name = str(
            get_value(self.config, "test_data.extension_market.extension_name", DEFAULT_EXTENSION_NAME)
            or DEFAULT_EXTENSION_NAME
        ).strip()
        extension_description = str(
            get_value(self.config, "test_data.extension_market.extension_description", DEFAULT_EXTENSION_DESCRIPTION)
            or DEFAULT_EXTENSION_DESCRIPTION
        ).strip()
        created = False

        try:
            assert_true(extension_name, "扩展市场测试数据的扩展名称不能为空")
            assert_true(extension_description, "扩展市场测试数据的扩展描述不能为空")

            extension_page.open_list()
            extension_page.open_added_extensions_tab()
            extension_page.delete_extension_if_exists(extension_name)

            extension_page.open_market_tab()
            extension_page.search_market_extension(extension_name)
            extension_page.add_market_extension(
                name=extension_name,
                description=extension_description,
                group_name=DEFAULT_EXTENSION_GROUP,
            )
            created = True

            extension_page.open_added_extensions_tab()
            extension_page.wait_extension_with_description_visible(extension_name, extension_description)
            details = extension_page.extension_card_details(extension_name)
            assert_equal(
                details.get("name"),
                extension_name,
                f"扩展市场添加后列表卡片名称错误: {details}",
            )
            assert_true(
                extension_description in details.get("raw", ""),
                f"扩展市场添加后列表卡片描述错误: {details}",
            )

            extension_page.delete_extension(extension_name)
            created = False
            assert_true(
                not extension_page.extension_visible(extension_name),
                f"扩展市场扩展删除后仍然存在: {extension_name}",
            )
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
