from __future__ import annotations

import unittest
from unittest import mock

from pages.extension_page import ExtensionPage


EXTENSION_GROUP_HTML = """
<html>
  <body>
    <section style="display:flex; width:800px; height:100px;">
      <div class="el-select" style="width:180px; height:40px;">
        <div class="el-select__wrapper">
          <div class="el-select__placeholder"><span>扩展分组01</span></div>
          <i class="el-select__clear"></i>
        </div>
      </div>
      <div class="el-select" style="width:180px; height:40px;">
        <div class="el-select__wrapper">
          <div class="el-select__placeholder"><span>启用状态</span></div>
        </div>
      </div>
      <input placeholder="扩展名称" value="Cookie-Editor" style="width:180px; height:40px;">
    </section>
    <div class="el-dialog" style="display:block; visibility:visible; width:650px; height:500px;">
      <div>编辑扩展</div>
      <div class="el-form-item" style="width:600px; height:100px;">
        <label>扩展分组</label>
        <div class="el-select" style="width:450px; height:50px;">
          <div class="el-select__wrapper" style="width:450px; height:50px;">
            <span class="el-tag"><span class="el-tag__content">未分组</span><i class="el-tag__close"></i></span>
            <span class="el-tag"><span class="el-tag__content">+ 1</span></span>
            <input role="combobox" aria-controls="extension-group-options" aria-expanded="false">
          </div>
        </div>
      </div>
      <button>取消</button>
      <button>确定</button>
    </div>
    <ul id="extension-group-options" style="display:none;">
      <li class="el-select-dropdown__item is-selected">未分组</li>
      <li class="el-select-dropdown__item is-selected">扩展分组01</li>
      <li class="el-select-dropdown__item">扩展分组02</li>
    </ul>
  </body>
</html>
"""

EXTENSION_CARD_HTML = """
<html>
  <body>
    <div class="el-card" style="display:block; width:500px; height:260px;">
      <div>
        <div>
          <div>
            <div class="tw-font-medium">ZeroOmega</div>
            <div class="tw-text-subText">3.4.1</div>
            <span class="tw-text-subText">分组: 未分组</span>
          </div>
        </div>
        <p>自动化需要数据。请勿删除，请保留此扩展。</p>
      </div>
      <div><span>提供方:</span><button>本地扩展</button></div>
    </div>
  </body>
</html>
"""


class ExtensionGroupEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cdp = mock.MagicMock()
        self.extension_page = ExtensionPage(cdp_driver=self.cdp, config={})

    def test_dialog_group_script_reads_exact_selected_tags(self) -> None:
        with _playwright_page() as browser_page:
            browser_page.set_content(EXTENSION_GROUP_HTML)
            page = ExtensionPage(cdp_driver=None, config={})

            groups = browser_page.evaluate(page._dialog_extension_groups_script())

        self.assertEqual(groups, ["未分组", "扩展分组01"])

    def test_list_filter_scripts_ignore_dialog_select(self) -> None:
        with _playwright_page() as browser_page:
            browser_page.set_content(EXTENSION_GROUP_HTML)
            page = ExtensionPage(cdp_driver=None, config={})

            group_value = browser_page.evaluate(page._list_filter_value_script(0))
            status_value = browser_page.evaluate(page._list_filter_value_script(1))
            search_value = browser_page.evaluate(page._extension_name_search_value_script())

        self.assertEqual(group_value, "扩展分组01")
        self.assertEqual(status_value, "启用状态")
        self.assertEqual(search_value, "Cookie-Editor")

    def test_append_dialog_group_preserves_existing_groups(self) -> None:
        with (
            mock.patch.object(
                self.extension_page,
                "dialog_extension_groups",
                side_effect=[["未分组"], ["未分组"]],
            ),
            mock.patch.object(
                self.extension_page,
                "_wait_for_dialog_extension_group_membership",
            ) as membership_mock,
            mock.patch.object(
                self.extension_page,
                "_ensure_dialog_extension_group_dropdown_open",
            ) as dropdown_mock,
            mock.patch.object(self.extension_page, "_wait_for_dialog_extension_groups") as groups_mock,
        ):
            self.extension_page.set_dialog_extension_groups(["未分组", "扩展分组01"])

        dropdown_mock.assert_called_once_with()
        self.cdp.click_element_by_script.assert_called_once()
        membership_mock.assert_called_once_with("扩展分组01", selected=True)
        self.cdp.press.assert_called_once_with("Escape")
        groups_mock.assert_called_once_with(["未分组", "扩展分组01"])

    def test_remove_dialog_group_keeps_original_group(self) -> None:
        with (
            mock.patch.object(
                self.extension_page,
                "dialog_extension_groups",
                side_effect=[["未分组", "扩展分组01"], ["未分组"]],
            ),
            mock.patch.object(
                self.extension_page,
                "_wait_for_dialog_extension_group_membership",
            ) as membership_mock,
            mock.patch.object(
                self.extension_page,
                "_ensure_dialog_extension_group_dropdown_open",
            ) as dropdown_mock,
            mock.patch.object(self.extension_page, "_wait_for_dialog_extension_groups") as groups_mock,
        ):
            self.extension_page.set_dialog_extension_groups(["未分组"])

        dropdown_mock.assert_called_once_with()
        self.cdp.click_element_by_script.assert_called_once()
        membership_mock.assert_called_once_with("扩展分组01", selected=False)
        self.cdp.press.assert_called_once_with("Escape")
        groups_mock.assert_called_once_with(["未分组"])

    def test_search_and_clear_filters_submit_list_query(self) -> None:
        with (
            mock.patch.object(self.extension_page, "_wait_for_extension_name_search_value") as value_mock,
            mock.patch.object(self.extension_page, "_wait_for_extension_list_stable") as stable_mock,
        ):
            self.extension_page.search_added_extension("Cookie-Editor")

        self.cdp.fill_element_by_script.assert_called_once()
        value_mock.assert_called_once_with("Cookie-Editor")
        self.cdp.click_element_by_script.assert_called_once()
        stable_mock.assert_called_once_with()

        self.cdp.reset_mock()
        with (
            mock.patch.object(
                self.extension_page,
                "_list_filter_value",
                side_effect=lambda index: "分组" if index == 0 else "启用状态",
            ),
            mock.patch.object(self.extension_page, "_extension_name_search_value", return_value=""),
            mock.patch.object(self.extension_page, "_wait_for_extension_list_stable") as stable_mock,
        ):
            self.extension_page.clear_added_extension_filters()

        self.cdp.fill_element_by_script.assert_not_called()
        self.cdp.click_element_by_script.assert_called_once()
        stable_mock.assert_called_once_with()

    def test_extension_card_details_separate_version_and_description(self) -> None:
        with _playwright_page() as browser_page:
            browser_page.set_content(EXTENSION_CARD_HTML)
            page = ExtensionPage(cdp_driver=None, config={})

            details = browser_page.evaluate(page._extension_card_details_script("ZeroOmega"))

        self.assertEqual(details["name"], "ZeroOmega")
        self.assertEqual(details["version"], "3.4.1")
        self.assertEqual(details["description"], "自动化需要数据。请勿删除，请保留此扩展。")
        self.assertEqual(details["group"], "分组: 未分组")
        self.assertEqual(details["provider"], "本地扩展")

    def test_set_dialog_extension_name_fills_and_waits_for_exact_value(self) -> None:
        with mock.patch.object(self.extension_page, "_wait_dialog_field_value") as wait_mock:
            self.extension_page.set_dialog_extension_name("自动化-编辑本地扩展名称")

        self.cdp.fill_element_by_script.assert_called_once()
        wait_mock.assert_called_once_with("扩展名称", "自动化-编辑本地扩展名称")

    def test_restore_extension_name_only_edits_when_original_is_missing(self) -> None:
        with (
            mock.patch.object(self.extension_page, "dismiss_blocking_overlays"),
            mock.patch.object(self.extension_page, "open_list"),
            mock.patch.object(self.extension_page, "open_added_extensions_tab"),
            mock.patch.object(self.extension_page, "clear_added_extension_filters"),
            mock.patch.object(self.extension_page, "search_added_extension") as search_mock,
            mock.patch.object(
                self.extension_page,
                "extension_exact_name_visible",
                side_effect=[False, True, True],
            ),
            mock.patch.object(self.extension_page, "open_extension_edit_dialog") as open_mock,
            mock.patch.object(self.extension_page, "wait_dialog_extension_name") as wait_name_mock,
            mock.patch.object(self.extension_page, "set_dialog_extension_name") as set_name_mock,
            mock.patch.object(self.extension_page, "save_extension_edit") as save_mock,
            mock.patch.object(self.extension_page, "wait_extension_visible") as wait_visible_mock,
        ):
            self.extension_page.restore_extension_name_if_needed(
                "ZeroOmega",
                "自动化-编辑本地扩展名称",
            )

        self.assertEqual(
            [call.args[0] for call in search_mock.call_args_list],
            ["ZeroOmega", "自动化-编辑本地扩展名称", "ZeroOmega"],
        )
        open_mock.assert_called_once_with("自动化-编辑本地扩展名称")
        wait_name_mock.assert_called_once_with("自动化-编辑本地扩展名称")
        set_name_mock.assert_called_once_with("ZeroOmega")
        save_mock.assert_called_once_with()
        wait_visible_mock.assert_called_once_with("ZeroOmega")


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
