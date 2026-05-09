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
        self._wait_for_disable_view_password_checkbox()
        before_states = self._wait_checkbox_states_stable()
        if self.disable_view_password_checked():
            return False

        self.cdp.click_element_by_script(self._disable_view_password_checkbox_script())
        self._wait_disable_view_password_checked(True)
        after_states = self.checkbox_states()
        self._assert_only_disable_view_password_changed(before_states, after_states)
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_checkbox_states_stable()
        self._wait_disable_view_password_checked(True)
        return True

    def disable_view_password_checked(self) -> bool:
        value = self.cdp.evaluate(self._disable_view_password_checked_script())
        if value is None:
            raise RuntimeError("禁止查看网站密码 checkbox was not found")
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

    def _wait_for_disable_view_password_checkbox(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._disable_view_password_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("禁止查看网站密码 checkbox did not appear")

    def _wait_disable_view_password_checked(self, expected: bool, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._disable_view_password_checked_script())
            if value is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"禁止查看网站密码 checkbox state did not become expected: {expected}")

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

    def _assert_only_disable_view_password_changed(
        self,
        before_states: dict[str, bool],
        after_states: dict[str, bool],
    ) -> None:
        changed = {
            name: (before_states.get(name), after_states.get(name))
            for name in sorted(set(before_states) | set(after_states))
            if before_states.get(name) != after_states.get(name)
        }
        allowed = {"禁止查看网站密码": (False, True)}
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

    def _disable_view_password_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const text = "禁止查看网站密码";
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(".el-checkbox, label, .el-form-item"))
                .filter(visible)
                .find((el) => (el.innerText || el.textContent || "").includes(text));
        })())
        """

    def _disable_view_password_checkbox_script(self) -> str:
        return """
        () => {
            const text = "禁止查看网站密码";
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
        """

    def _disable_view_password_checked_script(self) -> str:
        return """
        () => {
            const text = "禁止查看网站密码";
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
