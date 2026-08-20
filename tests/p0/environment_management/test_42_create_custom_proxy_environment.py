from __future__ import annotations

import unittest
from pathlib import Path

from core.app_config import resolve_app_config
from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.logger import setup_logger
from core.process import main_process_ids, wait_for_new_main_process_ids
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"
ENVIRONMENT_NAME = "测试自定义代理"
PROXY_ADDRESS = "http://192.168.20.33:7897"
PROXY_IP = "192.168.20.33"
PROXY_PORT = "7897"
ENVIRONMENT_OPEN_TIMEOUT_SECONDS = 100


class TestCreateCustomProxyEnvironment(unittest.TestCase):
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

    def test_create_custom_proxy_environment_open_close_delete(self) -> None:
        close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        browser_process_name = resolve_app_config(self.config).browser_process_name
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        cleanup_exact_environment = False

        try:
            environment_page.open_list()
            self._remove_environment_if_present(environment_page, close_timeout)
            environment_page.clear_search()
            cleanup_exact_environment = True

            create_button_state = environment_page.create_environment_button_state()
            assert_true(
                create_button_state["visible"] and create_button_state["enabled"],
                "创建环境按钮不可见或不可点击",
            )

            environment_page.open_create_environment_drawer()
            assert_true(
                environment_page.create_environment_drawer_visible(),
                "创建环境抽屉未展开",
            )

            environment_page.fill_create_environment_name(ENVIRONMENT_NAME)
            assert_equal(
                environment_page.create_environment_name_value(),
                ENVIRONMENT_NAME,
                "环境名称未成功填入",
            )

            environment_page.select_create_environment_proxy_mode("自定义代理")
            proxy_controls = environment_page.create_environment_proxy_controls_state()
            assert_true(
                proxy_controls["quick_input_visible"],
                "自定义代理快捷输入文本框未显示",
            )
            assert_true(
                proxy_controls["parse_button_visible"],
                "自定义代理解析按钮未显示",
            )

            environment_page.parse_create_environment_proxy(PROXY_ADDRESS)
            proxy_ip, proxy_port = environment_page.create_environment_proxy_values()
            assert_equal(proxy_ip, PROXY_IP, "自定义代理 IP 解析结果不正确")
            assert_equal(proxy_port, PROXY_PORT, "自定义代理端口解析结果不正确")

            environment_page.submit_create_environment("create custom proxy environment")
            assert_true(
                not environment_page.create_environment_drawer_visible(),
                "创建成功后抽屉未关闭",
            )
            environment_page.search_environment_without_assert(ENVIRONMENT_NAME)
            assert_true(
                environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME),
                f"环境管理列表未显示环境: {ENVIRONMENT_NAME}",
            )

            existing_browser_process_ids = set(main_process_ids(browser_process_name))
            environment_page.click_environment_action(ENVIRONMENT_NAME, "打开")
            try:
                new_browser_process_ids = wait_for_new_main_process_ids(
                    browser_process_name,
                    existing_browser_process_ids,
                    expected_count=1,
                    timeout_seconds=ENVIRONMENT_OPEN_TIMEOUT_SECONDS,
                )
            except TimeoutError as exc:
                raise AssertionError(
                    f"{ENVIRONMENT_OPEN_TIMEOUT_SECONDS}s 内未检测到新启动的 "
                    f"{browser_process_name} 主进程"
                ) from exc
            assert_true(
                bool(new_browser_process_ids),
                f"未检测到新启动的 {browser_process_name} 主进程",
            )

            environment_page.wait_environment_action_text(
                ENVIRONMENT_NAME,
                "关闭",
                timeout_seconds=ENVIRONMENT_OPEN_TIMEOUT_SECONDS,
            )
            environment_page.close_environment_and_confirm(
                ENVIRONMENT_NAME,
                timeout_seconds=close_timeout,
            )

            environment_page.select_environments([ENVIRONMENT_NAME])
            environment_page.delete_selected_environments_from_batch_menu()
        finally:
            if cleanup_exact_environment:
                try:
                    environment_page.open_list()
                    self._remove_environment_if_present(environment_page, close_timeout)
                except Exception as exc:
                    self.logger.warning(
                        "Custom proxy environment cleanup failed name=%s error=%s",
                        ENVIRONMENT_NAME,
                        exc,
                    )
            try:
                environment_page.clear_search()
            except Exception:
                pass

    @staticmethod
    def _remove_environment_if_present(
        environment_page: EnvironmentPage,
        close_timeout: int,
    ) -> None:
        environment_page.search_environment_without_assert(ENVIRONMENT_NAME)
        if not environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME):
            return
        if environment_page.environment_action_text(ENVIRONMENT_NAME) == "关闭":
            environment_page.close_environment_and_confirm(
                ENVIRONMENT_NAME,
                timeout_seconds=close_timeout,
            )
        environment_page.select_environments([ENVIRONMENT_NAME])
        environment_page.delete_selected_environments_from_batch_menu()


if __name__ == "__main__":
    unittest.main()
