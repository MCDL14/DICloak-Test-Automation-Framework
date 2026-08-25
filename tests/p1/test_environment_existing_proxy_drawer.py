from __future__ import annotations

import unittest

from pages.environment_page import EnvironmentPage


class _ExistingProxyDrawerProbe(EnvironmentPage):
    def __init__(self, visible_sequence: list[bool] | None = None) -> None:
        self.calls: list[tuple[str, object]] = []
        self.cdp = self
        self.config = {}
        self.visible_sequence = list(visible_sequence or [True])

    def _active_drawer_select_visible_by_placeholder_text(self, placeholder: str) -> bool:
        self.calls.append(("select-visible", placeholder))
        if len(self.visible_sequence) > 1:
            return self.visible_sequence.pop(0)
        return self.visible_sequence[0]

    def _active_drawer_select_search_input_by_placeholder_text_script(
        self,
        placeholder: str,
    ) -> str:
        self.calls.append(("input-script", placeholder))
        return "existing-proxy-input"

    def _select_search_input_control_id(self, input_script: str) -> str:
        self.calls.append(("control-id", input_script))
        return "existing-proxy-listbox"

    def click_element_by_script(self, script: str, timeout: int | None = None) -> None:
        if script == "existing-proxy-input":
            self.calls.append(("click-search-input", script))
        elif script == "first-existing-proxy-option":
            self.calls.append(("click-first-option", script))

    def fill_element_by_script(
        self,
        script: str,
        text: str,
        timeout: int | None = None,
    ) -> None:
        self.calls.append(("fill-search-input", (script, text)))

    def _wait_first_visible_enabled_select_dropdown_item(self) -> None:
        self.calls.append(("wait-first-option", None))

    def _first_visible_enabled_select_dropdown_item_script(self) -> str:
        self.calls.append(("first-option-script", None))
        return "first-existing-proxy-option"

    def _wait_select_dropdown_closed(self) -> None:
        self.calls.append(("wait-dropdown-closed", None))

    def _wait_create_environment_existing_proxy_selected_text(
        self,
        control_id: str,
    ) -> str:
        self.calls.append(("wait-selected-text", control_id))
        return "SOCKS5://127.0.0.1:7897 (序号:604 | 已绑0个)"


class _ExistingProxyControlIdProbe(EnvironmentPage):
    def __init__(self, values: list[str]) -> None:
        self.cdp = self
        self.config = {"timeouts": {"page_seconds": 1}}
        self.values = list(values)

    def evaluate(self, script: str) -> str:
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]


class EnvironmentExistingProxyDrawerTests(unittest.TestCase):
    def test_existing_proxy_control_id_waits_for_async_attribute(self) -> None:
        page = _ExistingProxyControlIdProbe(["", "existing-proxy-listbox"])

        control_id = page._select_search_input_control_id("() => null")

        self.assertEqual(control_id, "existing-proxy-listbox")

    def test_existing_proxy_select_visibility_uses_displayed_placeholder_text(self) -> None:
        page = _ExistingProxyDrawerProbe()

        self.assertTrue(page.create_environment_existing_proxy_select_visible())
        self.assertEqual(page.calls, [("select-visible", "请选择已有代理")])

    def test_existing_proxy_select_visibility_waits_for_async_render(self) -> None:
        page = _ExistingProxyDrawerProbe(visible_sequence=[False, False, True])

        self.assertTrue(page.create_environment_existing_proxy_select_visible())
        self.assertEqual(
            page.calls,
            [
                ("select-visible", "请选择已有代理"),
                ("select-visible", "请选择已有代理"),
                ("select-visible", "请选择已有代理"),
            ],
        )

    def test_searches_right_hand_existing_proxy_select_and_chooses_first_result(self) -> None:
        page = _ExistingProxyDrawerProbe()

        selected_text = page.select_first_create_environment_existing_proxy("7897")

        self.assertEqual(
            selected_text,
            "SOCKS5://127.0.0.1:7897 (序号:604 | 已绑0个)",
        )
        self.assertEqual(
            page.calls,
            [
                ("input-script", "请选择已有代理"),
                ("control-id", "existing-proxy-input"),
                ("click-search-input", "existing-proxy-input"),
                ("fill-search-input", ("existing-proxy-input", "7897")),
                ("wait-first-option", None),
                ("first-option-script", None),
                ("click-first-option", "first-existing-proxy-option"),
                ("wait-dropdown-closed", None),
                ("wait-selected-text", "existing-proxy-listbox"),
            ],
        )

    def test_selected_proxy_text_does_not_fall_back_to_uncommitted_search_value(self) -> None:
        page = _ExistingProxyDrawerProbe()

        script = page._active_drawer_select_selected_text_by_control_id_script(
            "existing-proxy-listbox"
        )

        self.assertIn(".el-select__selected-item", script)
        self.assertNotIn("return clean(input.value);", script)


if __name__ == "__main__":
    unittest.main()
