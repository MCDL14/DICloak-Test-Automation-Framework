from __future__ import annotations

import unittest

from pages.environment_page import EnvironmentPage


class _EnvironmentGroupPopoverProbe(EnvironmentPage):
    def __init__(self) -> None:
        self.cdp = self
        self.calls: list[object] = []

    def environment_group_text_by_serial(self, serial: str) -> str:
        self.calls.append(("base-text", serial))
        return "分组二 等 3 个\n查看"

    def _environment_group_view_button_by_serial_script(self, serial: str) -> str:
        self.calls.append(("button-script", serial))
        return f"view-button:{serial}"

    def _dismiss_environment_group_popover(self, button_script: str | None = None) -> None:
        self.calls.append(("dismiss-popover", button_script))

    def _element_rect_by_script(self, script: str) -> dict:
        self.calls.append(("rect", script))
        return {"x": 100, "y": 200, "width": 40, "height": 20}

    def click_element_by_script(self, script: str) -> None:
        self.calls.append(("click", script))

    def _wait_environment_group_detail_text(
        self,
        base_text: str = "",
        button_rect: dict | None = None,
    ) -> str:
        self.calls.append(("detail", base_text, button_rect))
        return "未分组、分组二、分组三"


class _BatchGroupOrderProbe(EnvironmentPage):
    def __init__(self) -> None:
        self.cdp = self
        self.calls: list[object] = []

    def hover_element_by_script(self, script: str) -> None:
        self.calls.append(("hover", script))

    def click_element_by_script(self, script: str) -> None:
        self.calls.append(("click", script))

    def press(self, key: str) -> None:
        self.calls.append(("press", key))

    def _batch_more_operation_script(self) -> str:
        return "more-operation"

    def _batch_more_menu_item_script(self, text: str) -> str:
        return f"menu:{text}"

    def _wait_batch_set_group_dialog_visible(self) -> None:
        self.calls.append("wait-dialog")

    def _select_batch_environment_groups(self, group_names: list[str]) -> None:
        self.calls.append(("select-groups", group_names))

    def batch_environment_group_selected_values(self) -> list[str]:
        self.calls.append("read-selected-groups")
        return ["分组三", "分组二"]

    def _wait_select_dropdown_closed(self) -> None:
        self.calls.append("wait-select-closed")

    def _select_batch_group_modify_mode(self, modify_mode: str) -> None:
        self.calls.append(("select-mode", modify_mode))

    def _active_overlay_button_script(self, text: str) -> str:
        return f"button:{text}"

    def _wait_for_overlay_closed(self) -> None:
        self.calls.append("wait-overlay-closed")

    def _wait_for_environment_list_not_loading_with_refresh_retry(self) -> None:
        self.calls.append("wait-list-loaded")


class EnvironmentGroupPopoverTests(unittest.TestCase):
    def test_group_parser_removes_collapsed_summary_and_view_action(self) -> None:
        page = object.__new__(EnvironmentPage)

        groups = page._parse_environment_group_text(
            "分组二 等 3 个\n查看\n未分组、分组二、分组三"
        )

        self.assertEqual(groups, ["分组二", "未分组", "分组三"])
        self.assertEqual(page._parse_environment_group_text("查看"), [])

    def test_serial_group_reader_uses_detail_only_and_waits_for_popover_close(self) -> None:
        page = _EnvironmentGroupPopoverProbe()

        text = page.environment_group_full_text_by_serial("4739")

        self.assertEqual(text, "未分组、分组二、分组三")
        self.assertEqual(
            page.calls,
            [
                ("base-text", "4739"),
                ("button-script", "4739"),
                ("dismiss-popover", None),
                ("rect", "view-button:4739"),
                ("click", "view-button:4739"),
                (
                    "detail",
                    "分组二 等 3 个\n查看",
                    {"x": 100, "y": 200, "width": 40, "height": 20},
                ),
                ("dismiss-popover", "view-button:4739"),
            ],
        )

    def test_batch_group_mode_is_selected_after_group_dropdown_closes(self) -> None:
        page = _BatchGroupOrderProbe()

        selected = page.batch_set_environment_groups("覆盖", ["分组三", "分组二"])

        self.assertEqual(selected, ["分组三", "分组二"])
        self.assertEqual(
            page.calls,
            [
                ("hover", "more-operation"),
                ("click", "menu:设置环境分组"),
                "wait-dialog",
                ("select-groups", ["分组三", "分组二"]),
                "read-selected-groups",
                ("press", "Escape"),
                "wait-select-closed",
                ("select-mode", "覆盖"),
                ("click", "button:确定"),
                "wait-overlay-closed",
                "wait-list-loaded",
            ],
        )


if __name__ == "__main__":
    unittest.main()
