from __future__ import annotations

import time

from core.config import timeout_seconds as config_timeout_seconds
from pages.base_page import BasePage


class GlobalSettingsPage(BasePage):
    def open(self) -> None:
        self._dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_menu_item_script("全局设置"))
        self._wait_for_global_settings_page()

    def ensure_disable_view_password_enabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_enabled("禁止查看网站密码")

    def ensure_disable_devtools_enabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_enabled("禁止打开浏览器开发者工具界面")

    def ensure_disable_extension_management_enabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_enabled("禁止管理/移除扩展，以及从本地安装扩展至浏览器")

    def ensure_disable_extension_management_disabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_disabled("禁止管理/移除扩展，以及从本地安装扩展至浏览器")

    def ensure_disable_member_google_extension_pages_enabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_enabled("禁止成员访问谷歌扩展商店和扩展设置页面")

    def ensure_disable_member_google_extension_pages_disabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_disabled("禁止成员访问谷歌扩展商店和扩展设置页面")

    def configure_website_restriction_blocklist(
        self,
        urls: list[str],
        shortcut_name: str = "谷歌应用商店",
    ) -> None:
        """Enable website restriction and save a blocklist with a shortcut option."""
        self._wait_for_website_restriction()
        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        if not self.website_restriction_enabled():
            self._set_website_restriction_enabled(True)

        self._select_website_restriction_mode("禁止访问指定网址")
        self._ensure_website_restriction_shortcut_checked(shortcut_name)
        self.cdp.fill_element_by_script(
            self._website_restriction_url_textarea_script(),
            "\n".join(urls),
        )
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names={shortcut_name},
            allowed_switch_names={"访问网站限制"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_website_restriction_enabled(True)
        self._wait_website_restriction_urls(urls)

    def configure_website_restriction_allowlist(self, urls: list[str]) -> None:
        """Enable website restriction and save an allowlist."""
        self._wait_for_website_restriction()
        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        if not self.website_restriction_enabled():
            self._set_website_restriction_enabled(True)

        self._select_website_restriction_mode("允许访问指定网址")
        self.cdp.fill_element_by_script(
            self._website_restriction_url_textarea_script(),
            "\n".join(urls),
        )
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"访问网站限制"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_website_restriction_enabled(True)
        self._wait_website_restriction_mode("允许访问指定网址")
        self._wait_website_restriction_urls(urls)

    def validate_website_restriction_controls_without_saving(
        self,
        test_url: str,
        shortcut_name: str | None = "谷歌应用商店",
        mode_text: str = "禁止访问指定网址",
    ) -> None:
        """Probe website restriction controls and restore UI state without saving."""
        self._wait_for_website_restriction()
        baseline_checkboxes, baseline_switches = self._wait_global_setting_states_stable()
        baseline_enabled = self.website_restriction_enabled()

        if not baseline_enabled:
            self._set_website_restriction_enabled(True)

        after_toggle_checkboxes, after_toggle_switches = self._wait_global_setting_states_stable()
        self._assert_no_unexpected_existing_state_changes_from_states(
            before_checkboxes=baseline_checkboxes,
            before_switches=baseline_switches,
            after_checkboxes=after_toggle_checkboxes,
            after_switches=after_toggle_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"访问网站限制"},
        )

        original_url_value = self.cdp.evaluate(self._website_restriction_url_value_script())
        self._select_website_restriction_mode(mode_text)
        if shortcut_name:
            self._ensure_website_restriction_shortcut_checked(shortcut_name)
        self.cdp.fill_element_by_script(self._website_restriction_url_textarea_script(), test_url)

        after_content_checkboxes, after_content_switches = self._wait_global_setting_states_stable()
        self._assert_no_unexpected_existing_state_changes_from_states(
            before_checkboxes=baseline_checkboxes,
            before_switches=baseline_switches,
            after_checkboxes=after_content_checkboxes,
            after_switches=after_content_switches,
            allowed_checkbox_names={shortcut_name} if shortcut_name else set(),
            allowed_switch_names={"访问网站限制"},
        )
        if self.cdp.evaluate(self._website_restriction_url_value_script()) != test_url:
            raise AssertionError("访问网站限制网址列表输入后未回显预期内容")
        if shortcut_name and not self.cdp.evaluate(self._website_restriction_shortcut_checked_script(shortcut_name)):
            raise AssertionError(f"访问网站限制快捷选择未保持勾选: {shortcut_name}")
        if not self.cdp.evaluate(self._website_restriction_radio_checked_script(mode_text)):
            raise AssertionError(f"访问网站限制方式未保持为：{mode_text}")

        self.cdp.fill_element_by_script(
            self._website_restriction_url_textarea_script(),
            str(original_url_value or ""),
        )
        if self.website_restriction_enabled() != baseline_enabled:
            self._set_website_restriction_enabled(baseline_enabled)

        final_checkboxes, final_switches = self._wait_global_setting_states_stable()
        self._assert_no_unexpected_existing_state_changes_from_states(
            before_checkboxes=baseline_checkboxes,
            before_switches=baseline_switches,
            after_checkboxes=final_checkboxes,
            after_switches=final_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names=set(),
        )
        if self.website_restriction_enabled() != baseline_enabled:
            raise AssertionError("访问网站限制非保存探针结束后未恢复原始开关状态")

    def disable_website_restriction(self) -> bool:
        """Disable website restriction and save. Return True when this method changed it."""
        changed = False
        for _ in range(3):
            self._wait_for_website_restriction()
            self._wait_global_setting_states_stable()
            if not self.website_restriction_enabled():
                return changed

            before_checkboxes, before_switches = self._wait_global_setting_states_stable()
            self._set_website_restriction_enabled(False)
            self._assert_no_unexpected_existing_state_changes(
                before_checkboxes=before_checkboxes,
                before_switches=before_switches,
                allowed_checkbox_names=set(),
                allowed_switch_names={"访问网站限制"},
            )
            self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
            self._wait_save_finished()
            self._wait_website_restriction_enabled(False)
            changed = True

            time.sleep(1)
            self.open()
            self._wait_global_setting_states_stable()
            if not self.website_restriction_enabled():
                return changed

        raise AssertionError("访问网站限制功能开关关闭保存后仍然保持开启")

    def website_restriction_enabled(self) -> bool:
        value = self.cdp.evaluate(self._website_restriction_enabled_script())
        if value is None:
            raise RuntimeError("访问网站限制 switch was not found")
        return bool(value)

    def ensure_checkbox_enabled(self, label_text: str) -> bool:
        """Enable one global setting checkbox without allowing other checkbox changes."""
        self._wait_for_checkbox(label_text)
        before_states = self._wait_checkbox_states_stable()
        if self.checkbox_checked(label_text):
            return False

        self.cdp.click_element_by_script(self._checkbox_script(label_text))
        self._wait_checkbox_checked(label_text, True)
        after_states = self.checkbox_states()
        self._assert_only_checkbox_changed(label_text, before_states, after_states)
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_checkbox_states_stable()
        self._wait_checkbox_checked(label_text, True)
        return True

    def ensure_checkbox_disabled(self, label_text: str) -> bool:
        """Disable one global setting checkbox without allowing other checkbox changes."""
        self._wait_for_checkbox(label_text)
        before_states = self._wait_checkbox_states_stable()
        if not self.checkbox_checked(label_text):
            return False

        self.cdp.click_element_by_script(self._checkbox_script(label_text))
        self._wait_checkbox_checked(label_text, False)
        after_states = self.checkbox_states()
        self._assert_only_checkbox_changed(label_text, before_states, after_states, expected_change=(True, False))
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_checkbox_states_stable()
        self._wait_checkbox_checked(label_text, False)
        return True

    def disable_view_password_checked(self) -> bool:
        return self.checkbox_checked("禁止查看网站密码")

    def checkbox_checked(self, label_text: str) -> bool:
        value = self.cdp.evaluate(self._checkbox_checked_script(label_text))
        if value is None:
            raise RuntimeError(f"{label_text} checkbox was not found")
        return bool(value)

    def checkbox_states(self) -> dict[str, bool]:
        value = self.cdp.evaluate(
            """
            () => {
                const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                };
                const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const states = {};
                for (const checkbox of Array.from(document.querySelectorAll(".el-checkbox")).filter(visible)) {
                    const text = clean(checkbox.innerText || checkbox.textContent);
                    if (!text) continue;
                    const input = checkbox.querySelector("input[type='checkbox']");
                    const stateEl = checkbox.querySelector(".el-checkbox__input") || checkbox;
                    states[text] = input ? Boolean(input.checked) : stateEl.classList.contains("is-checked");
                }
                return states;
            }
            """
        )
        if not isinstance(value, dict):
            return {}
        return {str(key): bool(item) for key, item in value.items()}

    def switch_states(self) -> dict[str, bool]:
        value = self.cdp.evaluate(
            """
            () => {
                const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                };
                const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const state = (switchEl) => {
                    const input = switchEl.querySelector("input");
                    const aria = input?.getAttribute("aria-checked") || switchEl.getAttribute("aria-checked") || "";
                    if (aria === "true") return true;
                    if (aria === "false") return false;
                    return switchEl.classList.contains("is-checked") || Boolean(input?.checked);
                };
                const states = {};
                for (const switchEl of Array.from(document.querySelectorAll(".el-switch")).filter(visible)) {
                    const item = switchEl.closest(".el-form-item") || switchEl.parentElement || switchEl;
                    let text = clean(item.innerText || item.textContent);
                    if (!text) {
                        const rect = switchEl.getBoundingClientRect();
                        const candidates = Array.from(document.querySelectorAll(".el-form-item"))
                            .filter(visible)
                            .map((el) => ({ el, text: clean(el.innerText || el.textContent), rect: el.getBoundingClientRect() }))
                            .filter((item) => item.text)
                            .filter((item) => Math.abs(item.rect.y - rect.y) < 120)
                            .sort((left, right) => Math.abs(left.rect.y - rect.y) - Math.abs(right.rect.y - rect.y));
                        text = candidates[0]?.text || "";
                    }
                    if (!text) continue;
                    const name = text.split(" ")[0] || text;
                    states[name] = state(switchEl);
                }
                return states;
            }
            """
        )
        if not isinstance(value, dict):
            return {}
        return {str(key): bool(item) for key, item in value.items()}

    def _assert_no_unexpected_existing_state_changes(
        self,
        before_checkboxes: dict[str, bool],
        before_switches: dict[str, bool],
        allowed_checkbox_names: set[str],
        allowed_switch_names: set[str],
    ) -> None:
        after_checkboxes = self.checkbox_states()
        after_switches = self.switch_states()
        self._assert_no_unexpected_existing_state_changes_from_states(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            after_checkboxes=after_checkboxes,
            after_switches=after_switches,
            allowed_checkbox_names=allowed_checkbox_names,
            allowed_switch_names=allowed_switch_names,
        )

    def _assert_no_unexpected_existing_state_changes_from_states(
        self,
        before_checkboxes: dict[str, bool],
        before_switches: dict[str, bool],
        after_checkboxes: dict[str, bool],
        after_switches: dict[str, bool],
        allowed_checkbox_names: set[str],
        allowed_switch_names: set[str],
    ) -> None:
        changed_checkboxes = {
            name: (before_checkboxes[name], after_checkboxes.get(name))
            for name in before_checkboxes
            if name in after_checkboxes
            and before_checkboxes[name] != after_checkboxes.get(name)
            and name not in allowed_checkbox_names
        }
        changed_switches = {
            name: (before_switches[name], after_switches.get(name))
            for name in before_switches
            if name in after_switches
            and before_switches[name] != after_switches.get(name)
            and name not in allowed_switch_names
        }
        if changed_checkboxes or changed_switches:
            raise AssertionError(
                "unexpected global settings state changes before save: "
                f"checkboxes={changed_checkboxes}, switches={changed_switches}"
            )

    def _wait_global_setting_states_stable(
        self,
        timeout_seconds: int | None = None,
    ) -> tuple[dict[str, bool], dict[str, bool]]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        stable_since = 0.0
        previous: tuple[dict[str, bool], dict[str, bool]] | None = None
        last: tuple[dict[str, bool], dict[str, bool]] = ({}, {})
        while time.time() < deadline:
            self._wait_until_not_loading()
            current = (self.checkbox_states(), self.switch_states())
            if current[0] and current == previous:
                if stable_since == 0:
                    stable_since = time.time()
                if time.time() - stable_since >= 1.5:
                    return current
            else:
                stable_since = 0.0
                previous = current
            last = current
            time.sleep(0.3)
        raise TimeoutError(f"global settings states did not become stable: checkboxes={last[0]}, switches={last[1]}")

    def _wait_for_global_settings_page(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(
                """
                () => {
                    const text = document.body ? (document.body.innerText || "") : "";
                    return text.includes("全局设置") && text.includes("禁止查看网站密码");
                }
                """
            ):
                return
            time.sleep(0.2)
        raise TimeoutError("global settings page did not appear")

    def _wait_for_checkbox(self, label_text: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._checkbox_exists_script(label_text)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"{label_text} checkbox did not appear")

    def _wait_for_website_restriction(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._website_restriction_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("访问网站限制 switch did not appear")

    def _wait_checkbox_checked(
        self,
        label_text: str,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._checkbox_checked_script(label_text))
            if value is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"{label_text} checkbox state did not become expected: {expected}")

    def _wait_website_restriction_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._website_restriction_enabled_script())
            if value is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"访问网站限制 switch state did not become expected: {expected}")

    def _set_website_restriction_enabled(self, expected: bool) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        last_state = None
        while time.time() < deadline:
            current = self.cdp.evaluate(self._website_restriction_enabled_script())
            last_state = current
            if current is expected:
                return

            clicked = bool(self.cdp.evaluate(self._website_restriction_switch_dom_click_script()))
            time.sleep(0.4)
            if self.cdp.evaluate(self._website_restriction_enabled_script()) is expected:
                return

            if not clicked:
                point = self.cdp.evaluate(self._website_restriction_switch_center_script())
                if not isinstance(point, dict):
                    raise RuntimeError(f"访问网站限制 switch center was not found: {point}")
                x = float(point.get("x", 0))
                y = float(point.get("y", 0))
                if x <= 0 or y <= 0:
                    raise RuntimeError(f"访问网站限制 switch center is invalid: {point}")
                self.cdp.click_at(x, y)
                time.sleep(0.5)

        raise TimeoutError(
            f"访问网站限制 switch state did not become expected: expected={expected}, last={last_state}"
        )

    def _wait_website_restriction_urls(
        self,
        urls: list[str],
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        expected = "\n".join(urls)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._website_restriction_url_value_script())
            if value == expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"访问网站限制网址列表未保存为预期值: expected={expected}")

    def _wait_website_restriction_mode(
        self,
        mode_text: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._website_restriction_radio_checked_script(mode_text)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"访问网站限制方式未保存为预期值: {mode_text}")

    def _select_website_restriction_mode(self, mode_text: str) -> None:
        if self.cdp.evaluate(self._website_restriction_radio_checked_script(mode_text)):
            return
        self.cdp.click_element_by_script(self._website_restriction_radio_script(mode_text))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._website_restriction_radio_checked_script(mode_text)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"访问网站限制方式未切换到: {mode_text}")

    def _ensure_website_restriction_shortcut_checked(self, shortcut_name: str) -> None:
        if self.cdp.evaluate(self._website_restriction_shortcut_checked_script(shortcut_name)):
            return
        self.cdp.click_element_by_script(self._website_restriction_shortcut_script(shortcut_name))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._website_restriction_shortcut_checked_script(shortcut_name)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"访问网站限制快捷选择未勾选: {shortcut_name}")

    def _wait_checkbox_states_stable(self, timeout_seconds: int | None = None) -> dict[str, bool]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        stable_since = 0.0
        previous: dict[str, bool] = {}
        last: dict[str, bool] = {}
        while time.time() < deadline:
            self._wait_until_not_loading()
            current = self.checkbox_states()
            if current and current == previous:
                if stable_since == 0:
                    stable_since = time.time()
                if time.time() - stable_since >= 1.5:
                    return current
            else:
                stable_since = 0.0
                previous = current
            last = current
            time.sleep(0.3)
        raise TimeoutError(f"global settings checkbox states did not become stable: {last}")

    def _assert_only_checkbox_changed(
        self,
        label_text: str,
        before_states: dict[str, bool],
        after_states: dict[str, bool],
        expected_change: tuple[bool, bool] = (False, True),
    ) -> None:
        changed = {
            name: (before_states.get(name), after_states.get(name))
            for name in sorted(set(before_states) & set(after_states))
            if before_states.get(name) != after_states.get(name)
        }
        allowed = {label_text: expected_change}
        unexpected = {
            name: value
            for name, value in changed.items()
            if name not in allowed or value != allowed[name]
        }
        if unexpected:
            raise AssertionError(f"unexpected global settings checkbox changes before save: {unexpected}")

    def _wait_save_finished(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self._has_visible_loading():
                return
            time.sleep(0.2)
        raise TimeoutError("global settings save did not finish")

    def _wait_until_not_loading(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self._has_visible_loading():
                return
            time.sleep(0.2)
        raise TimeoutError("global settings page still has visible loading mask")

    def _has_visible_loading(self) -> bool:
        return bool(
            self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== "none"
                            && style.visibility !== "hidden"
                            && rect.width > 0
                            && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-loading-mask, .el-loading-spinner"))
                        .some(visible);
                }
                """
            )
        )

    def _dismiss_blocking_overlays(self) -> None:
        for _ in range(4):
            has_overlay = bool(
                self.cdp.evaluate(
                    """
                    () => Boolean(document.querySelector(".el-drawer, .el-dialog, .el-message-box"))
                    """
                )
            )
            if not has_overlay:
                return
            clicked = bool(
                self.cdp.evaluate(
                    """
                    () => {
                        const visible = (el) => {
                            const rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        };
                        const selectors = [
                            ".el-drawer__close-btn",
                            ".el-dialog__headerbtn",
                            ".el-message-box__headerbtn",
                            ".el-overlay button[aria-label='Close']",
                        ];
                        for (const selector of selectors) {
                            const button = Array.from(document.querySelectorAll(selector)).find(visible);
                            if (button) {
                                button.click();
                                return true;
                            }
                        }
                        return false;
                    }
                    """
                )
            )
            if not clicked:
                self.cdp.press("Escape")
            time.sleep(0.3)

    def _checkbox_exists_script(self, label_text: str) -> str:
        return """
        () => Boolean((() => {
            const text = __TEXT__;
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(".el-checkbox, label, .el-form-item"))
                .filter(visible)
                .find((el) => (el.innerText || el.textContent || "").includes(text));
        })())
        """.replace("__TEXT__", repr(label_text))

    def _checkbox_script(self, label_text: str) -> str:
        return """
        () => {
            const text = __TEXT__;
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const candidates = Array.from(document.querySelectorAll(".el-checkbox, label"))
                .filter(visible)
                .filter((el) => (el.innerText || el.textContent || "").includes(text));
            const checkbox = candidates.find((el) => el.classList.contains("el-checkbox")) || candidates[0] || null;
            if (!checkbox) return null;
            return checkbox.querySelector(".el-checkbox__input, input[type='checkbox']") || checkbox;
        }
        """.replace("__TEXT__", repr(label_text))

    def _checkbox_checked_script(self, label_text: str) -> str:
        return """
        () => {
            const text = __TEXT__;
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const candidates = Array.from(document.querySelectorAll(".el-checkbox, label"))
                .filter(visible)
                .filter((el) => (el.innerText || el.textContent || "").includes(text));
            const checkbox = candidates.find((el) => el.classList.contains("el-checkbox")) || candidates[0] || null;
            if (!checkbox) return null;
            const input = checkbox.querySelector("input[type='checkbox']");
            if (input) return Boolean(input.checked);
            const stateEl = checkbox.querySelector(".el-checkbox__input") || checkbox;
            const ariaChecked = stateEl.getAttribute("aria-checked");
            if (ariaChecked === "true") return true;
            if (ariaChecked === "false") return false;
            return stateEl.classList.contains("is-checked") || checkbox.classList.contains("is-checked");
        }
        """.replace("__TEXT__", repr(label_text))

    def _website_restriction_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const root = __WEBSITE_RESTRICTION_ROOT__();
            return root && root.querySelector(".el-switch");
        })())
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function())

    def _website_restriction_switch_script(self) -> str:
        return """
        () => {
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(".el-switch");
            if (!switchEl) return null;
            switchEl.scrollIntoView({ block: "center" });
            return switchEl.querySelector(".el-switch__core") || switchEl;
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function())

    def _website_restriction_switch_center_script(self) -> str:
        return """
        () => {
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(".el-switch");
            if (!switchEl) return null;
            const core = switchEl.querySelector(".el-switch__core") || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            return {
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                width: rect.width,
                height: rect.height,
                className: String(switchEl.className || ""),
            };
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function())

    def _website_restriction_switch_dom_click_script(self) -> str:
        return """
        () => {
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return false;
            const switchEl = root.querySelector(".el-switch");
            if (!switchEl) return false;
            const core = switchEl.querySelector(".el-switch__core") || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return false;
            const eventOptions = { bubbles: true, cancelable: true, view: window };
            core.dispatchEvent(new MouseEvent("mouseover", eventOptions));
            core.dispatchEvent(new MouseEvent("mousemove", eventOptions));
            core.dispatchEvent(new MouseEvent("mousedown", eventOptions));
            core.dispatchEvent(new MouseEvent("mouseup", eventOptions));
            core.click();
            return true;
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function())

    def _website_restriction_enabled_script(self) -> str:
        return """
        () => {
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(".el-switch");
            if (!switchEl) return null;
            const input = switchEl.querySelector("input");
            const ariaChecked = switchEl.getAttribute("aria-checked");
            if (ariaChecked === "true") return true;
            if (ariaChecked === "false") return false;
            return switchEl.classList.contains("is-checked") || Boolean(input?.checked);
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function())

    def _website_restriction_radio_script(self, mode_text: str) -> str:
        return """
        () => {
            const modeText = __MODE_TEXT__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const radio = Array.from(root.querySelectorAll(".el-radio"))
                .find((el) => (el.innerText || el.textContent || "").includes(modeText));
            if (!radio) return null;
            radio.scrollIntoView({ block: "center" });
            return radio;
        }
        """.replace("__MODE_TEXT__", repr(mode_text)).replace(
            "__WEBSITE_RESTRICTION_ROOT__",
            self._website_restriction_root_function(),
        )

    def _website_restriction_radio_checked_script(self, mode_text: str) -> str:
        return """
        () => {
            const modeText = __MODE_TEXT__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return false;
            const radio = Array.from(root.querySelectorAll(".el-radio"))
                .find((el) => (el.innerText || el.textContent || "").includes(modeText));
            if (!radio) return false;
            return radio.classList.contains("is-checked") || Boolean(radio.querySelector("input")?.checked);
        }
        """.replace("__MODE_TEXT__", repr(mode_text)).replace(
            "__WEBSITE_RESTRICTION_ROOT__",
            self._website_restriction_root_function(),
        )

    def _website_restriction_shortcut_script(self, shortcut_name: str) -> str:
        return """
        () => {
            const shortcutName = __SHORTCUT_NAME__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const checkbox = Array.from(root.querySelectorAll(".el-checkbox"))
                .find((el) => (el.innerText || el.textContent || "").includes(shortcutName));
            if (!checkbox) return null;
            checkbox.scrollIntoView({ block: "center" });
            return checkbox;
        }
        """.replace("__SHORTCUT_NAME__", repr(shortcut_name)).replace(
            "__WEBSITE_RESTRICTION_ROOT__",
            self._website_restriction_root_function(),
        )

    def _website_restriction_shortcut_checked_script(self, shortcut_name: str) -> str:
        return """
        () => {
            const shortcutName = __SHORTCUT_NAME__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return false;
            const checkbox = Array.from(root.querySelectorAll(".el-checkbox"))
                .find((el) => (el.innerText || el.textContent || "").includes(shortcutName));
            if (!checkbox) return false;
            return checkbox.classList.contains("is-checked") || Boolean(checkbox.querySelector("input")?.checked);
        }
        """.replace("__SHORTCUT_NAME__", repr(shortcut_name)).replace(
            "__WEBSITE_RESTRICTION_ROOT__",
            self._website_restriction_root_function(),
        )

    def _website_restriction_url_textarea_script(self) -> str:
        return """
        () => {
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const textarea = Array.from(root.querySelectorAll("textarea"))
                .find((el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });
            if (!textarea) return null;
            textarea.scrollIntoView({ block: "center" });
            return textarea;
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function())

    def _website_restriction_url_value_script(self) -> str:
        return """
        () => {
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const textarea = Array.from(root.querySelectorAll("textarea"))
                .find((el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });
            return textarea ? String(textarea.value || "") : null;
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function())

    def _website_restriction_root_function(self) -> str:
        return """
        (() => {
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(".el-form-item"))
                .filter(visible)
                .filter((el) => clean(el.innerText || el.textContent).includes("访问网站限制"))
                .filter((el) => el.querySelector(".el-switch"))
                .sort((left, right) => {
                    const leftText = clean(left.innerText || left.textContent);
                    const rightText = clean(right.innerText || right.textContent);
                    const leftScore = leftText.startsWith("访问网站限制") ? 0 : 1;
                    const rightScore = rightText.startsWith("访问网站限制") ? 0 : 1;
                    if (leftScore !== rightScore) return leftScore - rightScore;
                    const leftRect = left.getBoundingClientRect();
                    const rightRect = right.getBoundingClientRect();
                    return (leftRect.width * leftRect.height) - (rightRect.width * rightRect.height);
                });
            return candidates[0] || null;
        })
        """

    def _visible_menu_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (el) => (el.innerText || el.textContent || "").trim();
            const exactMenuItems = Array.from(document.querySelectorAll(".el-menu-item, [role='menuitem']"))
                .filter((el) => visible(el) && clean(el) === expectedText);
            if (exactMenuItems.length) return exactMenuItems[0];
            const exactItems = Array.from(document.querySelectorAll("a, button, .el-sub-menu__title"))
                .filter((el) => visible(el) && clean(el) === expectedText);
            if (exactItems.length) return exactItems[0];
            const menuItems = Array.from(document.querySelectorAll(".el-menu-item, [role='menuitem']"))
                .filter((el) => visible(el) && clean(el).includes(expectedText));
            return menuItems[0] || null;
        }}
        """

    def _visible_button_by_text_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const buttons = Array.from(document.querySelectorAll("button"))
                .filter((button) => visible(button))
                .filter((button) => (button.innerText || button.textContent || "").trim() === expectedText)
                .map((button) => {{
                    const rect = button.getBoundingClientRect();
                    return {{ button, rect }};
                }})
                .sort((left, right) => (right.rect.y - left.rect.y) || (right.rect.x - left.rect.x));
            return buttons[0]?.button || null;
        }}
        """
