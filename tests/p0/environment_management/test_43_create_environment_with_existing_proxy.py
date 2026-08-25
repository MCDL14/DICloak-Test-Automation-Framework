from __future__ import annotations

import unittest
import urllib.parse
from pathlib import Path

from core.app_config import resolve_app_config
from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.kernel_cdp import KernelPageResult, open_kernel_url_and_read_page
from core.kernel_process import resolve_kernel_runtime
from core.logger import setup_logger
from core.process import main_process_ids, wait_for_new_main_process_ids
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"
ENVIRONMENT_NAME = "自动化-使用-已有代理-的环境"
PROXY_SEARCH_TEXT = "7897"
ENVIRONMENT_OPEN_TIMEOUT_SECONDS = 60
CHROME_WEBSTORE_URL = "https://chromewebstore.google.com/"
CHROME_WEBSTORE_TIMEOUT_SECONDS = 60
MINIMUM_REACHABLE_PAGE_TEXT_LENGTH = 20


def chrome_webstore_page_reachable(result: KernelPageResult) -> bool:
    requested_host = urllib.parse.urlparse(CHROME_WEBSTORE_URL).hostname or ""
    target_host = urllib.parse.urlparse(result.target_url).hostname or ""
    evidence = "\n".join(
        [
            result.error_text,
            result.title,
            result.target_url,
            result.text,
        ]
    ).upper()
    return (
        target_host.lower() == requested_host.lower()
        and not result.error_text.strip()
        and "ERR_" not in evidence
        and len(result.text.strip()) > MINIMUM_REACHABLE_PAGE_TEXT_LENGTH
    )


def chrome_webstore_failure_message(result: KernelPageResult) -> str:
    return (
        "使用已有代理的环境无法访问 Chrome Web Store: "
        f"requested_url={result.requested_url}, target_url={result.target_url}, "
        f"title={result.title!r}, error={result.error_text!r}, "
        f"page_text={result.text[:1000]!r}"
    )


class TestCreateEnvironmentWithExistingProxy(unittest.TestCase):
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

    def test_create_environment_with_existing_proxy_open_close_delete(self) -> None:
        close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)
        browser_process_name = resolve_app_config(self.config).browser_process_name
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        cleanup_exact_environment = False
        delayed_assertions: list[AssertionError] = []

        try:
            environment_page.open_list()
            self._remove_environment_if_present(environment_page, close_timeout)
            environment_page.clear_search()
            cleanup_exact_environment = True

            environment_page.open_create_environment_drawer()
            environment_page.fill_create_environment_name(ENVIRONMENT_NAME)
            environment_page.select_create_environment_proxy_mode("已有代理")
            environment_page.select_first_create_environment_existing_proxy(
                PROXY_SEARCH_TEXT
            )

            environment_page.submit_create_environment(
                "create environment with existing proxy"
            )
            environment_page.search_environment_without_assert(ENVIRONMENT_NAME)

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

            try:
                environment_page.wait_environment_action_text(
                    ENVIRONMENT_NAME,
                    "关闭",
                    timeout_seconds=ENVIRONMENT_OPEN_TIMEOUT_SECONDS,
                )
            except TimeoutError as exc:
                raise AssertionError(
                    "环境打开后操作按钮未在时限内从打开扭转为关闭"
                ) from exc
            assert_equal(
                environment_page.environment_action_text(ENVIRONMENT_NAME),
                "关闭",
                "环境打开后操作按钮未从打开扭转为关闭",
            )

            try:
                kernel_runtime = resolve_kernel_runtime(
                    ENVIRONMENT_NAME,
                    new_browser_process_ids[0],
                    timeout_seconds=kernel_cdp_timeout,
                    probe_timeout_seconds=kernel_cdp_probe_timeout,
                    http_timeout_seconds=http_probe_timeout,
                )
                chrome_webstore_result = open_kernel_url_and_read_page(
                    kernel_runtime.cdp_port,
                    CHROME_WEBSTORE_URL,
                    timeout_seconds=CHROME_WEBSTORE_TIMEOUT_SECONDS,
                    http_timeout_seconds=http_probe_timeout,
                )
                reachable = chrome_webstore_page_reachable(chrome_webstore_result)
                self.logger.info(
                    "Existing proxy Chrome Web Store connectivity: reachable=%s "
                    "target_url=%s title=%r error=%r text_length=%s",
                    reachable,
                    chrome_webstore_result.target_url,
                    chrome_webstore_result.title,
                    chrome_webstore_result.error_text,
                    len(chrome_webstore_result.text.strip()),
                )
                assert_true(
                    reachable,
                    chrome_webstore_failure_message(chrome_webstore_result),
                )
            except AssertionError as exc:
                delayed_assertions.append(exc)
            except Exception as exc:
                delayed_assertions.append(
                    AssertionError(
                        "使用已有代理的环境访问 Chrome Web Store 时发生异常: "
                        f"{type(exc).__name__}: {exc}"
                    )
                )

            try:
                environment_page.close_environment_and_confirm(
                    ENVIRONMENT_NAME,
                    timeout_seconds=close_timeout,
                )
            except TimeoutError as exc:
                if "environment action text did not become 打开" not in str(exc):
                    raise
                raise AssertionError(
                    "环境关闭后操作按钮未在时限内从关闭扭转为打开"
                ) from exc
            assert_equal(
                environment_page.environment_action_text(ENVIRONMENT_NAME),
                "打开",
                "环境关闭后操作按钮未从关闭扭转为打开",
            )

            environment_page.select_environments([ENVIRONMENT_NAME])
            environment_page.delete_selected_environments_from_batch_menu()

            if delayed_assertions:
                raise AssertionError("\n".join(str(item) for item in delayed_assertions))
        finally:
            if cleanup_exact_environment:
                try:
                    environment_page.open_list()
                    self._remove_environment_if_present(environment_page, close_timeout)
                except Exception as exc:
                    self.logger.warning(
                        "Existing proxy environment cleanup failed name=%s error=%s",
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
