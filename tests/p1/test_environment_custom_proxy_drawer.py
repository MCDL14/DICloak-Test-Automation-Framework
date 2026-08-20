from __future__ import annotations

import unittest

from pages.environment_page import EnvironmentPage


class _CustomProxyDrawerProbe(EnvironmentPage):
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.cdp = self
        self.config = {}

    def fill(self, name: str, value: str) -> None:
        self.calls.append(("fill-name", (name, value)))

    def click_element_by_script(self, script: str, timeout: int | None = None) -> None:
        if script.startswith("radio:"):
            self.calls.append(("select-mode", script.removeprefix("radio:")))
        elif script.startswith("button:"):
            self.calls.append(("click-parse", script.removeprefix("button:")))
        elif script == "create-button":
            self.calls.append(("click-create", None))

    def fill_element_by_script(self, script: str, text: str, timeout: int | None = None) -> None:
        self.calls.append(("fill-quick-input", (script.removeprefix("input:"), text)))

    def _visible_locator_script(self, locator_name: str) -> str:
        return "create-button"

    def _wait_create_environment_default_group_selected(self, timeout_seconds: int) -> None:
        self.calls.append(("wait-default-group", timeout_seconds))

    def _active_drawer_form_radio_button_selected(self, label_text: str, option_text: str) -> bool:
        return False

    def _active_drawer_form_radio_button_script(self, label_text: str, option_text: str) -> str:
        return f"radio:{option_text}"

    def _wait_active_drawer_form_radio_button_selected(self, label_text: str, option_text: str) -> None:
        self.calls.append(("wait-mode", (label_text, option_text)))

    def _active_drawer_input_by_placeholder_script(self, placeholder: str) -> str:
        return f"input:{placeholder}"

    def _active_drawer_form_button_script(self, label_text: str, button_text: str) -> str:
        return f"button:{label_text}:{button_text}"

    def _wait_create_environment_proxy_values(self, expected_ip: str, expected_port: str) -> None:
        self.calls.append(("wait-parsed", (expected_ip, expected_port)))

    def _submit_active_create_environment_drawer(self, context: str) -> None:
        self.calls.append(("submit", context))

    def _wait_for_environment_list_not_loading_with_refresh_retry(self) -> None:
        self.calls.append(("wait-list", None))

    def click_environment_action(self, name: str, action_text: str) -> None:
        self.calls.append(("environment-action", (name, action_text)))

    def _wait_active_overlay_visible(self, timeout_seconds: int | None = None) -> bool:
        self.calls.append(("wait-close-dialog", timeout_seconds))
        return True

    def confirm_secondary_dialog(self, preferred_texts: tuple[str, ...] = ("确定", "确认")) -> None:
        self.calls.append(("confirm-close", preferred_texts))

    def wait_environment_action_text(
        self,
        name: str,
        action_text: str,
        timeout_seconds: int | None = None,
    ) -> None:
        self.calls.append(("wait-environment-action", (name, action_text, timeout_seconds)))


class EnvironmentCustomProxyDrawerTests(unittest.TestCase):
    def test_parses_http_quick_input_host_and_port(self) -> None:
        self.assertEqual(
            EnvironmentPage._proxy_host_port_from_quick_input("http://192.168.20.33:7897"),
            ("192.168.20.33", "7897"),
        )

    def test_opens_create_drawer_and_waits_until_ready(self) -> None:
        page = _CustomProxyDrawerProbe()

        page.open_create_environment_drawer()

        self.assertEqual(
            page.calls,
            [
                ("click-create", None),
                ("wait-default-group", page.CREATE_ENVIRONMENT_DEFAULT_GROUP_SECONDS),
            ],
        )

    def test_custom_proxy_flow_fills_name_selects_mode_and_parses_address(self) -> None:
        page = _CustomProxyDrawerProbe()

        page.fill_create_environment_name("测试自定义代理")
        page.select_create_environment_proxy_mode("自定义代理")
        page.parse_create_environment_proxy("http://192.168.20.33:7897")

        self.assertEqual(
            page.calls,
            [
                ("fill-name", ("environment_name_input", "测试自定义代理")),
                ("select-mode", "自定义代理"),
                ("wait-mode", ("代理设置", "自定义代理")),
                ("fill-quick-input", ("选填", "http://192.168.20.33:7897")),
                ("click-parse", "快捷输入:解析"),
                ("wait-parsed", ("192.168.20.33", "7897")),
            ],
        )

    def test_submit_waits_for_drawer_to_close_and_list_to_finish_loading(self) -> None:
        page = _CustomProxyDrawerProbe()

        page.submit_create_environment("create custom proxy environment")

        self.assertEqual(
            page.calls,
            [
                ("submit", "create custom proxy environment"),
                ("wait-list", None),
            ],
        )

    def test_close_confirms_dialog_and_waits_until_environment_is_closed(self) -> None:
        page = _CustomProxyDrawerProbe()

        page.close_environment_and_confirm("测试自定义代理", timeout_seconds=100)

        self.assertEqual(
            page.calls,
            [
                ("environment-action", ("测试自定义代理", "关闭")),
                ("wait-close-dialog", 10),
                ("confirm-close", ("确定", "确认")),
                ("wait-environment-action", ("测试自定义代理", "打开", 100)),
            ],
        )


if __name__ == "__main__":
    unittest.main()
