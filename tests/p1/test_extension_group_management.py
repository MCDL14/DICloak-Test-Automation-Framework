from __future__ import annotations

import unittest
from unittest import mock

from pages.extension_page import ExtensionPage


EXTENSION_GROUP_DRAWER_HTML = """
<html>
  <head>
    <style>
      .el-drawer { display:block; width:900px; height:600px; }
      .el-table { display:block; width:850px; height:400px; }
      table, tbody, tr { display:block; width:850px; min-height:40px; }
      td { display:inline-block; width:110px; height:36px; }
      i { display:inline-block; width:20px; height:20px; }
    </style>
  </head>
  <body>
    <section class="el-drawer">
      <header class="el-drawer__header"><span class="el-drawer__title">扩展分组管理</span></header>
      <div class="el-table">
        <table>
          <tbody>
            <tr class="el-table__row">
              <td class="el-table__cell">未分组</td><td class="el-table__cell">--</td>
              <td class="el-table__cell">--</td><td class="el-table__cell">--</td>
              <td class="el-table__cell">系统</td><td class="el-table__cell">2024-11-11 18:46:23</td>
              <td class="el-table__cell"></td>
            </tr>
            <tr class="el-table__row" data-target="yes">
              <td class="el-table__cell">自动化-创建扩展分组</td>
              <td class="el-table__cell">自动化-扩展分组备注</td>
              <td class="el-table__cell">--</td><td class="el-table__cell">--</td>
              <td class="el-table__cell">测试账号</td><td class="el-table__cell">2026-08-27 17:30:00</td>
              <td class="el-table__cell">
                <i class="iconfont icon-edit"></i><i class="iconfont icon-delete"></i>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </body>
</html>
"""


class ExtensionGroupManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cdp = mock.MagicMock()
        self.extension_page = ExtensionPage(cdp_driver=self.cdp, config={})

    def test_group_rows_are_parsed_by_column_and_operation_order(self) -> None:
        with _playwright_page() as browser_page:
            browser_page.set_content(EXTENSION_GROUP_DRAWER_HTML)
            page = ExtensionPage(cdp_driver=None, config={})

            rows = browser_page.evaluate(page._extension_group_rows_script())
            delete_target = browser_page.evaluate(
                f"""
                () => {{
                  const target = ({page._extension_group_row_delete_script("自动化-创建扩展分组")})();
                  return {{
                    className: String(target?.className || ""),
                    rowTarget: target?.closest("tr")?.getAttribute("data-target") || "",
                  }};
                }}
                """
            )
            edit_target = browser_page.evaluate(
                f"""
                () => {{
                  const target = ({page._extension_group_row_edit_by_identity_script(
                      "自动化-扩展分组备注",
                      "2026-08-27 17:30:00",
                  )})();
                  return {{
                    className: String(target?.className || ""),
                    rowTarget: target?.closest("tr")?.getAttribute("data-target") || "",
                  }};
                }}
                """
            )

        self.assertEqual(rows[0]["name"], "未分组")
        self.assertFalse(rows[0]["deletable"])
        self.assertEqual(rows[1]["name"], "自动化-创建扩展分组")
        self.assertEqual(rows[1]["remark"], "自动化-扩展分组备注")
        self.assertTrue(rows[1]["editable"])
        self.assertTrue(rows[1]["deletable"])
        self.assertIn("icon-delete", delete_target["className"])
        self.assertEqual(delete_target["rowTarget"], "yes")
        self.assertIn("icon-edit", edit_target["className"])
        self.assertEqual(edit_target["rowTarget"], "yes")

    def test_group_identity_requires_unique_remark_and_created_at(self) -> None:
        self.cdp.evaluate.return_value = [
            {
                "name": "扩展分组03",
                "remark": "重要分组",
                "created_at": "2025-09-28 17:54:50",
                "editable": True,
            },
            {
                "name": "同身份分组",
                "remark": "重要分组",
                "created_at": "2025-09-28 17:54:50",
                "editable": True,
            },
        ]

        with self.assertRaisesRegex(RuntimeError, "matches=2"):
            self.extension_page.extension_group_by_identity(
                "重要分组",
                "2025-09-28 17:54:50",
            )

    def test_edit_extension_group_name_uses_identity_and_waits_for_refresh(self) -> None:
        group = {
            "name": "扩展分组03",
            "remark": "重要分组",
            "created_at": "2025-09-28 17:54:50",
            "editable": True,
        }
        with (
            mock.patch.object(self.extension_page, "extension_group_by_identity", return_value=group),
            mock.patch.object(self.extension_page, "_wait_for_extension_group_overlay_visible") as overlay_mock,
            mock.patch.object(self.extension_page, "_wait_dialog_field_value") as field_mock,
            mock.patch.object(
                self.extension_page,
                "_click_extension_group_overlay_button_wait_loading_then_closed",
            ) as submit_mock,
            mock.patch.object(self.extension_page, "_wait_for_extension_group_table_stable") as table_mock,
            mock.patch.object(self.extension_page, "wait_extension_group_name_by_identity") as name_mock,
        ):
            self.extension_page.edit_extension_group_name_by_identity(
                remark="重要分组",
                created_at="2025-09-28 17:54:50",
                new_name="自动化-修改扩展分组名称",
                expected_current_name="扩展分组03",
            )

        edit_script = self.cdp.click_element_by_script.call_args.args[0]
        self.assertIn("icon-edit", edit_script)
        overlay_mock.assert_called_once_with("编辑扩展分组")
        self.assertEqual(
            [call.args for call in field_mock.call_args_list],
            [
                ("分组名称", "扩展分组03"),
                ("备注", "重要分组"),
                ("分组名称", "自动化-修改扩展分组名称"),
            ],
        )
        submit_mock.assert_called_once_with(overlay_text="编辑扩展分组", button_text="确定")
        table_mock.assert_called_once_with()
        name_mock.assert_called_once_with(
            "重要分组",
            "2025-09-28 17:54:50",
            "自动化-修改扩展分组名称",
        )

    def test_restore_extension_group_name_is_idempotent(self) -> None:
        restored = {
            "name": "扩展分组03",
            "remark": "重要分组",
            "created_at": "2025-09-28 17:54:50",
            "editable": True,
        }
        edited = {**restored, "name": "自动化-修改扩展分组名称"}
        with (
            mock.patch.object(self.extension_page, "extension_group_by_identity", return_value=restored),
            mock.patch.object(self.extension_page, "edit_extension_group_name_by_identity") as edit_mock,
        ):
            self.extension_page.restore_extension_group_name_if_needed(
                remark="重要分组",
                created_at="2025-09-28 17:54:50",
                original_name="扩展分组03",
            )
            edit_mock.assert_not_called()

        with (
            mock.patch.object(self.extension_page, "extension_group_by_identity", return_value=edited),
            mock.patch.object(self.extension_page, "edit_extension_group_name_by_identity") as edit_mock,
        ):
            self.extension_page.restore_extension_group_name_if_needed(
                remark="重要分组",
                created_at="2025-09-28 17:54:50",
                original_name="扩展分组03",
            )
            edit_mock.assert_called_once_with(
                remark="重要分组",
                created_at="2025-09-28 17:54:50",
                new_name="扩展分组03",
                expected_current_name="自动化-修改扩展分组名称",
            )

    def test_create_extension_group_fills_fields_and_waits_for_drawer_refresh(self) -> None:
        with (
            mock.patch.object(self.extension_page, "_wait_for_extension_group_overlay_visible") as overlay_mock,
            mock.patch.object(self.extension_page, "_wait_dialog_field_value") as field_mock,
            mock.patch.object(
                self.extension_page,
                "_click_extension_group_overlay_button_wait_loading_then_closed",
            ) as submit_mock,
            mock.patch.object(self.extension_page, "_wait_for_extension_group_table_stable") as table_mock,
            mock.patch.object(self.extension_page, "wait_extension_group_visible") as visible_mock,
        ):
            self.extension_page.create_extension_group(
                "自动化-创建扩展分组",
                "自动化-扩展分组备注",
            )

        self.assertEqual(self.cdp.fill_element_by_script.call_count, 2)
        self.assertEqual(
            [call.args for call in field_mock.call_args_list],
            [("分组名称", "自动化-创建扩展分组"), ("备注", "自动化-扩展分组备注")],
        )
        overlay_mock.assert_called_once_with("创建扩展分组")
        submit_mock.assert_called_once_with(overlay_text="创建扩展分组", button_text="确定")
        table_mock.assert_called_once_with()
        visible_mock.assert_called_once_with("自动化-创建扩展分组")

    def test_delete_extension_group_uses_second_row_icon_and_confirmation(self) -> None:
        group = {
            "name": "自动化-创建扩展分组",
            "remark": "自动化-扩展分组备注",
            "deletable": True,
        }
        with (
            mock.patch.object(self.extension_page, "extension_group_by_name", return_value=group),
            mock.patch.object(self.extension_page, "_wait_for_extension_group_overlay_visible") as overlay_mock,
            mock.patch.object(
                self.extension_page,
                "_click_extension_group_overlay_button_wait_loading_then_closed",
            ) as confirm_mock,
            mock.patch.object(self.extension_page, "_wait_for_extension_group_table_stable") as table_mock,
            mock.patch.object(self.extension_page, "wait_extension_group_absent") as absent_mock,
        ):
            self.extension_page.delete_extension_group("自动化-创建扩展分组")

        self.cdp.click_element_by_script.assert_called_once()
        overlay_mock.assert_called_once_with("是否确定删除该分组？")
        confirm_mock.assert_called_once_with(
            overlay_text="是否确定删除该分组？",
            button_text="确定",
        )
        table_mock.assert_called_once_with()
        absent_mock.assert_called_once_with("自动化-创建扩展分组")


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
