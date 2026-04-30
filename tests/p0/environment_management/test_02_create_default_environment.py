from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.logger import setup_logger
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestCreateDefaultEnvironment(unittest.TestCase):
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

    def test_create_open_close_delete_default_environment(self) -> None:
        data = self.config["test_data"]["environment_create_default"]
        environment_name = str(data.get("environment_name", "自动化-创建环境"))
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        environment_created = False
        environment_opened = False

        try:
            environment_page.open_list()
            environment_page.search_environment_without_assert(environment_name)
            if environment_page.environment_visible_in_current_list(environment_name):
                environment_page.delete_environment_from_current_list(environment_name)
                assert_true(
                    not environment_page.environment_visible_in_current_list(environment_name),
                    f"existing test environment was not cleaned before create: {environment_name}",
                )

            environment_page.create_environment(environment_name)
            environment_created = True
            environment_page.wait_environment_visible_in_current_list(environment_name)

            assert_equal(
                environment_page.environment_action_text(environment_name),
                "打开",
                f"created environment is not ready to open: {environment_name}",
            )
            environment_page.click_environment_action(environment_name, "打开")
            environment_page.wait_environment_action_text(
                environment_name,
                "关闭",
                timeout_seconds=environment_open_timeout,
            )
            environment_opened = True

            environment_page.click_environment_action(environment_name, "关闭")
            environment_opened = False
            environment_page.wait_environment_action_text(
                environment_name,
                "打开",
                timeout_seconds=environment_close_timeout,
            )

            environment_page.delete_environment_from_current_list(environment_name)
            environment_created = False
            environment_page.search_environment_without_assert(environment_name)
            assert_true(
                not environment_page.environment_visible_in_current_list(environment_name),
                f"environment was not deleted: {environment_name}",
            )
        finally:
            try:
                if environment_opened:
                    try:
                        environment_page.click_environment_action(environment_name, "关闭")
                        environment_page.wait_environment_action_text(
                            environment_name,
                            "打开",
                            timeout_seconds=environment_close_timeout,
                        )
                    except Exception:
                        pass
                if environment_created:
                    try:
                        environment_page.search_environment_without_assert(environment_name)
                        if environment_page.environment_visible_in_current_list(environment_name):
                            environment_page.delete_environment_from_current_list(environment_name)
                    except Exception:
                        pass
            finally:
                try:
                    environment_page.clear_search()
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
