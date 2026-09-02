from __future__ import annotations

import unittest
from unittest import mock

from pages.proxy_page import ProxyPage


PROXY_DIALOG_HTML = """
<html>
  <head>
    <style>
      .el-dialog { display:block; width:760px; height:600px; }
      .el-form-item { display:block; width:700px; min-height:48px; }
      .el-form-item__label, .el-radio-button, .el-select, input, button {
        display:inline-block; min-width:80px; min-height:24px;
      }
    </style>
  </head>
  <body>
    <section class="el-dialog">
      <h2>创建代理</h2>
      <div class="el-form-item">
        <label class="el-form-item__label">代理方式</label>
        <label class="el-radio-button is-active"><input type="radio" value="IP_RESOURCE" checked>PuraRoute代理</label>
        <label class="el-radio-button" data-method="custom"><input type="radio" value="CUSTOM">自定义代理</label>
        <label class="el-radio-button"><input type="radio" value="FROM_API">API提取</label>
      </div>
      <div class="el-form-item">
        <label class="el-form-item__label">代理分组</label>
        <div class="el-select"><span>错误候选</span></div>
      </div>
      <div class="el-form-item">
        <label class="el-form-item__label">代理类型</label>
        <div class="el-select"><span>SOCKS5</span><input role="combobox"></div>
      </div>
      <input placeholder="代理主机">
      <input placeholder="代理端口">
      <button>检测代理</button>
    </section>
  </body>
</html>
"""


class ProxyCreateDialogModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cdp = mock.MagicMock()
        self.page = ProxyPage(cdp_driver=self.cdp, config={})

    def test_proxy_method_and_type_scripts_use_exact_form_labels(self) -> None:
        with _playwright_page() as browser_page:
            browser_page.set_content(PROXY_DIALOG_HTML)
            page = ProxyPage(cdp_driver=None, config={})
            method = browser_page.evaluate(page._create_dialog_proxy_method_value_script())
            custom_target = browser_page.evaluate(
                f"""
                () => {{
                  const target = ({page._create_dialog_proxy_method_option_script('自定义代理')})();
                  return target?.getAttribute('data-method') || '';
                }}
                """
            )
            proxy_type = browser_page.evaluate(page._create_dialog_proxy_type_value_script())
            custom_state = browser_page.evaluate(page._create_dialog_custom_proxy_form_state_script())

        self.assertEqual(method, "PuraRoute代理")
        self.assertEqual(custom_target, "custom")
        self.assertEqual(proxy_type, "SOCKS5")
        self.assertTrue(custom_state["ready"])

    def test_ensure_custom_method_waits_for_linked_form(self) -> None:
        with (
            mock.patch.object(
                self.page,
                "create_dialog_proxy_method",
                side_effect=["PuraRoute代理", "自定义代理"],
            ),
            mock.patch.object(self.page, "_wait_create_dialog_visible"),
        ):
            self.cdp.evaluate.return_value = {
                "ready": True,
                "proxy_type": True,
                "host": True,
                "port": True,
                "detect_button": True,
            }
            self.page.ensure_create_dialog_proxy_method("自定义代理")

        method_script = self.cdp.click_element_by_script.call_args.args[0]
        self.assertIn("自定义代理", method_script)
        self.assertIn("代理方式", method_script)

    def test_ensure_proxy_type_selects_custom_method_first(self) -> None:
        with (
            mock.patch.object(self.page, "_wait_create_dialog_visible"),
            mock.patch.object(self.page, "ensure_create_dialog_proxy_method") as method_mock,
            mock.patch.object(self.page, "create_dialog_proxy_type", side_effect=["SOCKS5", "HTTP"]),
        ):
            self.page.ensure_create_dialog_proxy_type("HTTP")

        method_mock.assert_called_once_with("自定义代理")
        self.assertEqual(self.cdp.click_element_by_script.call_count, 2)

    def test_proxy_type_normalization_accepts_decorated_name(self) -> None:
        self.assertEqual(
            self.page._normalize_create_dialog_proxy_type("NodeMaven (动态代理)"),
            "NODEMAVEN",
        )


class _playwright_page:
    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise unittest.SkipTest("playwright is not installed") from exc
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=True)
        except Exception as exc:
            self._playwright.stop()
            raise unittest.SkipTest(f"playwright chromium is not available: {exc}") from exc
        self._page = self._browser.new_page(viewport={"width": 1100, "height": 800})
        return self._page

    def __exit__(self, exc_type, exc, tb):
        self._browser.close()
        self._playwright.stop()


if __name__ == "__main__":
    unittest.main()
