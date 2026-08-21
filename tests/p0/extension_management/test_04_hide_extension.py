from __future__ import annotations

import time
import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import get_value, load_config, timeout_seconds
from core.kernel_cdp_session import KernelCDPSession
from core.kernel_process import resolve_kernel_runtime
from core.logger import setup_logger
from core.process import wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.extension_page import ExtensionPage
from pages.login_page import LoginPage


CASE_MODULE = "扩展管理"
DEFAULT_EXTENSION_NAME = "ZeroOmega"
DEFAULT_EXTENSION_KEYWORD = "ZeroOmega"
DEFAULT_MEMBER_GROUP = "全部分组"
DEFAULT_ENVIRONMENT_NAME = "自动化扩展启用验证"


class TestHideExtension(unittest.TestCase):
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

    def test_hide_extension_from_chrome_extensions_page(self) -> None:
        extension_page = ExtensionPage(cdp_driver=self.cdp, config=self.config)
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        extension_name = DEFAULT_EXTENSION_NAME
        extension_keyword = str(
            get_value(self.config, "test_data.hide_extension.extension_keyword", DEFAULT_EXTENSION_KEYWORD)
            or DEFAULT_EXTENSION_KEYWORD
        ).strip()
        member_group = str(
            get_value(self.config, "test_data.hide_extension.member_group", DEFAULT_MEMBER_GROUP)
            or DEFAULT_MEMBER_GROUP
        ).strip()
        environment_name = str(
            get_value(self.config, "test_data.hide_extension.environment_name", DEFAULT_ENVIRONMENT_NAME)
            or DEFAULT_ENVIRONMENT_NAME
        ).strip()
        kernel_pid = 0
        delayed_assertions: list[AssertionError] = []

        try:
            assert_true(extension_name, "隐藏扩展测试数据的扩展名称不能为空")
            assert_true(extension_keyword, "隐藏扩展测试数据的扩展名称关键字不能为空")
            assert_true(member_group, "隐藏扩展测试数据的成员分组不能为空")
            assert_true(environment_name, "隐藏扩展测试数据的验证环境名称不能为空")

            extension_page.open_list()
            extension_page.open_added_extensions_tab()
            assert_true(
                extension_page.extension_exact_name_visible(extension_name),
                f"隐藏扩展用例缺少前置扩展，请先在扩展列表中准备已有扩展: {extension_name}",
            )

            extension_page.edit_extension_hide_settings(
                extension_name,
                hidden=True,
                member_group=member_group,
            )
            extension_page.set_extension_enabled(extension_name, True)

            environment_page.open_list()
            environment_page.search_environment(environment_name)
            try:
                kernel_pid = self._open_environment_and_assert_hidden(
                    environment_page,
                    environment_name=environment_name,
                    extension_keyword=extension_keyword,
                )
            except AssertionError as exc:
                delayed_assertions.append(exc)
            finally:
                try:
                    self._close_environment_if_open(
                        environment_page,
                        environment_name=environment_name,
                        kernel_pid=kernel_pid,
                    )
                except AssertionError as exc:
                    delayed_assertions.append(exc)
                kernel_pid = 0
                try:
                    assert_true(
                        environment_page.environment_action_text(environment_name) == "打开",
                        f"关闭环境后操作按钮未恢复为打开: {environment_name}",
                    )
                except AssertionError as exc:
                    delayed_assertions.append(exc)
                environment_page.clear_search()

            extension_page.open_list()
            extension_page.open_added_extensions_tab()
            extension_page.set_extension_enabled(extension_name, False, retries=3)
            assert_true(
                not extension_page.extension_enabled(extension_name),
                f"隐藏扩展用例关闭扩展开关后仍为开启: {extension_name}",
            )
            extension_page.edit_extension_hide_settings(extension_name, hidden=False)

            if delayed_assertions:
                raise AssertionError("\n".join(str(item) for item in delayed_assertions))
        finally:
            try:
                environment_page.open_list()
                environment_page.search_environment_without_assert(environment_name)
                self._close_environment_if_open(
                    environment_page,
                    environment_name=environment_name,
                    kernel_pid=kernel_pid,
                )
                environment_page.clear_search()
            except Exception:
                pass
            try:
                extension_page.open_list()
                extension_page.open_added_extensions_tab()
                if extension_page.extension_visible(extension_name):
                    try:
                        extension_page.set_extension_enabled(extension_name, False, retries=3)
                    except Exception:
                        pass
                    try:
                        extension_page.edit_extension_hide_settings(extension_name, hidden=False)
                    except Exception:
                        pass
            except Exception:
                pass

    def _open_environment_and_assert_hidden(
        self,
        environment_page: EnvironmentPage,
        *,
        environment_name: str,
        extension_keyword: str,
    ) -> int:
        assert_true(
            environment_page.environment_visible_in_current_list(environment_name),
            f"用于隐藏扩展验证的环境不存在: {environment_name}",
        )
        kernel_pid = environment_page.open_environment_and_capture_pid(environment_name)
        assert_true(
            wait_for_pid_running(
                kernel_pid,
                timeout_seconds=timeout_seconds(self.config, "kernel_process_seconds", 90),
            ),
            f"浏览器内核进程未启动: pid={kernel_pid}",
        )
        environment_page.wait_environment_action_text(
            environment_name,
            "关闭",
            timeout_seconds=timeout_seconds(self.config, "environment_open_seconds", 90),
        )
        kernel_runtime = resolve_kernel_runtime(
            environment_name,
            kernel_pid,
            timeout_seconds=timeout_seconds(self.config, "kernel_cdp_seconds", 30),
            probe_timeout_seconds=timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3),
            http_timeout_seconds=timeout_seconds(self.config, "http_probe_seconds", 2),
        )
        with KernelCDPSession(kernel_runtime.cdp_port, timeout_seconds=30) as kernel_session:
            kernel_session.navigate("chrome://extensions/", timeout_seconds=30)
            contains_keyword, page_text = self._wait_chrome_extensions_keyword_state(
                kernel_session,
                extension_keyword,
                expected_present=False,
                timeout_seconds=30,
            )
            assert_true(
                not contains_keyword,
                "隐藏扩展后 chrome://extensions/ 仍展示目标扩展关键字: "
                f"keyword={extension_keyword}, page_text={page_text[:500]}",
            )
            self.logger.info(
                "Hidden extension runtime target probe skipped: no stable extension id for existing extension %s",
                extension_keyword,
            )
        return kernel_pid

    def _close_environment_if_open(
        self,
        environment_page: EnvironmentPage,
        *,
        environment_name: str,
        kernel_pid: int,
    ) -> None:
        if not environment_page.environment_visible_in_current_list(environment_name):
            return
        if environment_page.environment_action_text(environment_name) != "关闭":
            return
        environment_page.click_environment_action(environment_name, "关闭")
        if kernel_pid:
            assert_true(
                wait_for_pid_stopped(
                    kernel_pid,
                    timeout_seconds=timeout_seconds(self.config, "kernel_process_seconds", 90),
                ),
                f"浏览器内核进程未停止: pid={kernel_pid}",
            )
        environment_page.wait_environment_action_text(
            environment_name,
            "打开",
            timeout_seconds=timeout_seconds(self.config, "environment_close_seconds", 90),
        )

    def _wait_chrome_extensions_keyword_state(
        self,
        kernel_session: KernelCDPSession,
        keyword: str,
        *,
        expected_present: bool,
        timeout_seconds: int,
    ) -> tuple[bool, str]:
        deadline = time.time() + timeout_seconds
        last_text = ""
        while time.time() < deadline:
            last_text = self._chrome_extensions_page_text(kernel_session)
            contains = keyword in last_text
            if contains == expected_present:
                return contains, last_text
            time.sleep(1)
        return keyword in last_text, last_text

    def _chrome_extensions_page_text(self, kernel_session: KernelCDPSession) -> str:
        value = kernel_session.evaluate(
            """
            (() => {
              const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
              const seen = new Set();
              const parts = [];
              const walk = (node) => {
                if (!node || seen.has(node)) return;
                seen.add(node);
                if (node.nodeType === Node.TEXT_NODE) {
                  const text = clean(node.textContent || '');
                  if (text) parts.push(text);
                  return;
                }
                if (node.shadowRoot) walk(node.shadowRoot);
                for (const child of Array.from(node.childNodes || [])) walk(child);
              };
              walk(document);
              return clean(parts.join(' '));
            })()
            """,
            timeout_seconds=10,
        )
        return str(value or "")


if __name__ == "__main__":
    unittest.main()
