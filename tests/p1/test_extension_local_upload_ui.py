from __future__ import annotations

import unittest

from pages.extension_page import ExtensionPage


LOCAL_EXTENSION_DIALOG_HTML = """
<html>
  <body>
    <div class="el-dialog" style="display:block; visibility:visible; width:650px; height:850px;">
      <div>添加扩展</div>
      <div class="el-form-item">
        <label class="el-form-item__label">添加方式</label>
        <div>
          <label class="el-radio-button">
            <input class="el-radio-button__original-radio" type="radio" value="GOOGLE">
            <span>Chrome 应用商店</span>
          </label>
          <label class="el-radio-button is-active">
            <input class="el-radio-button__original-radio" type="radio" value="LOCAL" checked>
            <span>安装包</span>
          </label>
        </div>
      </div>
      <div class="el-form-item">
        <label class="el-form-item__label">安装包</label>
        <div class="el-upload el-upload--text is-drag" tabindex="0">
          <input class="el-upload__input" name="file" accept=".zip,application/zip" type="file" style="display:none">
          <div class="el-upload-dragger">将 ZIP 文件拖到此处，或点击上传 仅支持 ZIP 格式，不超过 100MB</div>
        </div>
      </div>
      <div class="el-form-item">
        <label class="el-form-item__label">扩展名称</label>
        <input class="el-input__inner" maxlength="50" type="text" placeholder="请输入扩展名称">
      </div>
      <div class="el-form-item">
        <label class="el-form-item__label">扩展图标</label>
        <div class="el-upload el-upload--text is-drag" tabindex="0">
          <input class="el-upload__input" name="file" accept=".png,.jpg,.jpeg,image/png,image/jpeg" type="file" style="display:none">
          <div class="el-upload-dragger">点击或拖拽上传</div>
        </div>
      </div>
      <button>取消</button>
      <button>确定</button>
    </div>
  </body>
</html>
"""


class ExtensionLocalUploadUiTests(unittest.TestCase):
    def test_local_package_mode_accepts_new_zip_accept_attribute(self) -> None:
        with _playwright_page() as browser_page:
            browser_page.set_content(LOCAL_EXTENSION_DIALOG_HTML)
            extension_page = ExtensionPage(cdp_driver=None, config={})

            visible = browser_page.evaluate(extension_page._local_package_mode_visible_script())

        self.assertTrue(visible)

    def test_package_upload_target_prefers_zip_area_over_icon_upload(self) -> None:
        with _playwright_page() as browser_page:
            browser_page.set_content(LOCAL_EXTENSION_DIALOG_HTML)
            extension_page = ExtensionPage(cdp_driver=None, config={})

            handle = browser_page.evaluate_handle(extension_page._dialog_package_upload_button_script())
            target = handle.evaluate(
                """
                (el) => ({
                    text: String(el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim(),
                    className: String(el.className || ""),
                })
                """
            )

        self.assertIn("将 ZIP 文件拖到此处", target["text"])
        self.assertIn("el-upload", target["className"])
        self.assertNotEqual(target["text"], "点击或拖拽上传")


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
        self._page = self._browser.new_page(viewport={"width": 1000, "height": 900})
        return self._page

    def __exit__(self, exc_type, exc, tb):
        self._browser.close()
        self._playwright.stop()


if __name__ == "__main__":
    unittest.main()
