from __future__ import annotations

import time
import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
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
DEFAULT_EXTENSION_URL = "https://chromewebstore.google.com/detail/proxy-switchyomega-3-zero/pfnededegaaopdmhkdmcofjmoldfiped?hl=zh-CN"
DEFAULT_EXTENSION_NAME = "Proxy SwitchyOmega 3 (ZeroOmega)"
DEFAULT_EXTENSION_DESCRIPTION = "轻松快捷地管理和切换多个代理设置。"
DEFAULT_EXTENSION_PROVIDER = "谷歌商店"
DEFAULT_EXTENSION_GROUP = "未分组"
DEFAULT_ENVIRONMENT_NAME = "自动化扩展启用验证"


class TestCreateGoogleExtensionAndEnable(unittest.TestCase):
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

    def test_create_google_extension_enable_and_delete(self) -> None:
        extension_page = ExtensionPage(cdp_driver=self.cdp, config=self.config)
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        extension_url = str(
            get_value(self.config, "test_data.google_extension.extension_url", DEFAULT_EXTENSION_URL)
            or DEFAULT_EXTENSION_URL
        ).strip()
        extension_name = str(
            get_value(self.config, "test_data.google_extension.extension_name", DEFAULT_EXTENSION_NAME)
            or DEFAULT_EXTENSION_NAME
        ).strip()
        extension_description = str(
            get_value(self.config, "test_data.google_extension.extension_description", DEFAULT_EXTENSION_DESCRIPTION)
            or DEFAULT_EXTENSION_DESCRIPTION
        ).strip()
        environment_name = str(
            get_value(self.config, "test_data.google_extension.environment_name", DEFAULT_ENVIRONMENT_NAME)
            or DEFAULT_ENVIRONMENT_NAME
        ).strip()
        created = False
        kernel_pid = 0
        delayed_assertions: list[AssertionError] = []

        try:
            assert_true(extension_url, "谷歌扩展测试数据的扩展 URL 不能为空")
            assert_true(extension_name, "谷歌扩展测试数据的扩展名称不能为空")
            assert_true(extension_description, "谷歌扩展测试数据的扩展描述不能为空")
            assert_true(environment_name, "谷歌扩展启用验证环境名称不能为空")

            extension_page.open_list()
            extension_page.open_added_extensions_tab()
            extension_page.delete_extension_if_exists(extension_name)

            extension_page.add_google_store_extension(
                extension_url=extension_url,
                extension_name=extension_name,
                group_name=DEFAULT_EXTENSION_GROUP,
                enable_extension=True,
            )
            created = True

            extension_page.wait_extension_with_description_visible(extension_name, extension_description)
            details = extension_page.extension_card_details(extension_name)
            assert_equal(
                details.get("name"),
                extension_name,
                f"谷歌扩展创建后列表卡片名称错误: {details}",
            )
            assert_true(
                extension_description in details.get("raw", ""),
                f"谷歌扩展创建后列表卡片描述错误: {details}",
            )
            try:
                assert_equal(
                    details.get("provider"),
                    DEFAULT_EXTENSION_PROVIDER,
                    f"谷歌扩展创建后列表卡片提供方错误: {details}",
                )
            except AssertionError as exc:
                delayed_assertions.append(exc)

            environment_page.open_list()
            environment_page.search_environment(environment_name)
            assert_true(
                environment_page.environment_visible_in_current_list(environment_name),
                f"用于验证扩展启用的环境不存在: {environment_name}",
            )
            try:
                kernel_pid = self._open_environment_and_assert_extension_enabled(
                    environment_page,
                    environment_name=environment_name,
                    extension_name=extension_name,
                    extension_description=extension_description,
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
                    assert_equal(
                        environment_page.environment_action_text(environment_name),
                        "打开",
                        f"关闭环境后操作按钮未恢复为打开: {environment_name}",
                    )
                except AssertionError as exc:
                    delayed_assertions.append(exc)
                environment_page.clear_search()

            extension_page.open_list()
            extension_page.open_added_extensions_tab()
            extension_page.delete_extension(extension_name)
            created = False
            assert_true(
                not extension_page.extension_visible(extension_name),
                f"谷歌扩展删除后仍然存在: {extension_name}",
            )

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
            if created:
                try:
                    extension_page.open_list()
                    extension_page.open_added_extensions_tab()
                    extension_page.delete_extension_if_exists(extension_name)
                except Exception:
                    pass

    def _open_environment_and_assert_extension_enabled(
        self,
        environment_page: EnvironmentPage,
        *,
        environment_name: str,
        extension_name: str,
        extension_description: str,
    ) -> int:
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
        with KernelCDPSession(
            kernel_runtime.cdp_port,
            timeout_seconds=max(timeout_seconds(self.config, "kernel_cdp_seconds", 30), 20),
        ) as kernel_session:
            kernel_session.navigate("chrome://extensions/", timeout_seconds=30)
            found, page_text = self._wait_chrome_extensions_page_contains(
                kernel_session,
                extension_name,
                extension_description,
                timeout_seconds=30,
            )
            assert_true(
                found,
                "环境内 chrome://extensions/ 未找到目标扩展名称和描述: "
                f"name={extension_name}, description={extension_description}, page_text={page_text[:500]}",
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

    def _wait_chrome_extensions_page_contains(
        self,
        kernel_session: KernelCDPSession,
        extension_name: str,
        extension_description: str,
        timeout_seconds: int,
    ) -> tuple[bool, str]:
        deadline = time.time() + timeout_seconds
        last_text = ""
        while time.time() < deadline:
            last_text = self._chrome_extensions_page_text(kernel_session)
            if extension_name in last_text and extension_description in last_text:
                return True, last_text
            time.sleep(1)
        return False, last_text

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
