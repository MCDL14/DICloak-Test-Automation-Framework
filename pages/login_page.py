from __future__ import annotations

import json
import time

from core.config import timeout_ms
from pages.base_page import BasePage


class LoginStateError(RuntimeError):
    pass


class LoginPage(BasePage):
    locator_file = "login_locators.yaml"

    def ensure_logged_in_as_config_account(self) -> None:
        account = self.config.get("account", {})
        expected_username = str(account.get("username", "")).strip()
        password = str(account.get("password", ""))
        expected_team = str(account.get("team_name", "")).strip()
        if not expected_username:
            raise LoginStateError("account.username is empty")

        if not self.is_logged_in():
            self.login(expected_username, password)
            self.wait_logged_in()
            self._assert_current_account(expected_username)
            self.ensure_current_team(expected_team)
            return

        current_username = self.current_account()
        if current_username == expected_username:
            self.ensure_current_team(expected_team)
            return

        if not current_username:
            raise LoginStateError("APP is logged in, but current account cannot be identified")

        self.logout()
        self.login(expected_username, password)
        self.wait_logged_in()
        self._assert_current_account(expected_username)
        self.ensure_current_team(expected_team)

    def is_logged_in(self) -> bool:
        if self._app_logged_in_from_state():
            return True
        try:
            return bool(
                self.cdp.wait_for_selector(
                    self.locator("logged_in_marker"),
                    timeout=timeout_ms(self.config, "login_marker_seconds", 3),
                )
            )
        except Exception:
            return False

    def _app_logged_in_from_state(self) -> bool:
        script = """
        () => {
            const raw = localStorage.getItem("basic:state");
            if (!raw) return false;
            try {
                const state = JSON.parse(raw);
                const user = state.userInfo || {};
                const hasUser = Boolean(user.email || user.name || user.userId || user.memberId);
                const bodyText = document.body ? (document.body.innerText || document.body.textContent || "") : "";
                const hasAppShell = Boolean(document.querySelector(".el-menu, aside, nav"))
                    || bodyText.includes("环境管理")
                    || bodyText.includes("成员列表")
                    || bodyText.includes("环境分组")
                    || bodyText.includes("代理管理");
                return hasUser && hasAppShell;
            } catch {
                return false;
            }
        }
        """
        try:
            return bool(self.cdp.evaluate(script))
        except Exception:
            return False

    def wait_logged_in(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or int(self.config.get("timeouts", {}).get("page_seconds", 10))
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.is_logged_in():
                return
            time.sleep(0.3)
        raise LoginStateError("logged_in_marker not found after login")

    def login(self, username: str | None = None, password: str | None = None) -> None:
        account = self.config.get("account", {})
        login_username = str(username or account.get("username", ""))
        login_password = str(password or account.get("password", ""))
        try:
            self.fill("username_input", login_username)
            self.fill("password_input", login_password)
            self.click("login_button")
        except Exception as exc:
            self._login_by_visible_inputs(login_username, login_password, exc)

    def click_login_button(self) -> None:
        try:
            self.click("login_button")
        except Exception:
            self.cdp.click_element_by_script(self._login_button_script())

    def login_failed_message(self) -> str:
        message = self.latest_visible_message_text()
        if message:
            return message
        try:
            return self.text("login_error")
        except Exception:
            return ""

    def latest_visible_message_text(self) -> str:
        try:
            value = self.cdp.evaluate(self._visible_message_text_script())
        except Exception:
            return ""
        return str(value or "").strip()

    def wait_login_failed_message(self, expected_text: str, timeout_seconds: int | None = None) -> str:
        timeout_seconds = timeout_seconds or int(self.config.get("timeouts", {}).get("page_seconds", 10))
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            message = self.login_failed_message()
            if expected_text in message:
                return message
            time.sleep(0.3)
        raise TimeoutError(f"login failed message did not appear: expected={expected_text}")

    def current_account(self) -> str:
        account_from_state = self._current_account_from_state()
        if account_from_state:
            return account_from_state
        try:
            self.click("account_menu")
            return self.text("current_account").strip()
        except Exception:
            return ""

    def current_team(self) -> str:
        team_from_state = self._current_team_from_state()
        if team_from_state:
            return team_from_state
        try:
            self._open_account_menu()
            text = self.text("current_team").strip()
        except Exception:
            return ""
        if text.startswith("团队:"):
            return text.split("团队:", 1)[1].splitlines()[0].strip()
        return text

    def ensure_current_team(self, expected_team: str | None = None) -> None:
        team_name = str(expected_team or self.config.get("account", {}).get("team_name", "")).strip()
        if not team_name:
            return
        if self.current_team() == team_name:
            return
        self.switch_team(team_name)
        current_team = self.current_team()
        if current_team != team_name:
            raise LoginStateError(f"team switch failed: expected={team_name}, actual={current_team or 'unknown'}")

    def switch_team(self, team_name: str) -> None:
        if not team_name:
            raise LoginStateError("team_name is empty")
        timeout = int(self.config.get("account", {}).get("team_switch_timeout", 20))
        self._open_switch_team_popover(timeout=timeout)
        self._wait_for_team_switch_item(team_name, timeout=timeout)
        self.cdp.click_element_by_script(self._team_switch_item_script(team_name))
        self._wait_until_current_team(team_name, timeout=timeout)

    def logout(self) -> None:
        self._open_account_menu()
        self.click("logout_button")
        try:
            confirm_selector = self.locator("confirm_logout_button")
        except Exception:
            confirm_selector = ""
        if confirm_selector:
            try:
                self.click("confirm_logout_button")
            except Exception:
                pass

    def logout_to_login_page(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or int(self.config.get("timeouts", {}).get("page_seconds", 10))
        if not self.is_logged_in():
            self.wait_login_page_visible(timeout_seconds=timeout_seconds)
            return

        last_error: Exception | None = None
        for _ in range(3):
            try:
                self.logout()
                self._confirm_logout_dialog_if_present()
                self.wait_login_page_visible(timeout_seconds=timeout_seconds)
                return
            except Exception as exc:
                last_error = exc
                try:
                    self.cdp.press("Escape")
                except Exception:
                    pass
                time.sleep(0.5)
                if not self.is_logged_in():
                    self.wait_login_page_visible(timeout_seconds=timeout_seconds)
                    return
        raise TimeoutError(f"logout did not reach login page: {last_error}")

    def wait_force_logout_popup(self, timeout_seconds: int | None = None) -> str:
        timeout_seconds = timeout_seconds or int(self.config.get("timeouts", {}).get("page_seconds", 10))
        logout_text = "\u9000\u51fa\u767b\u5f55"
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                text = str(self.cdp.evaluate(self._force_logout_popup_text_script()) or "").strip()
            except Exception:
                time.sleep(0.3)
                continue
            if logout_text in text:
                return text
            time.sleep(0.3)
        raise TimeoutError("force logout popup did not appear")

    def click_force_logout_button(self) -> None:
        self.cdp.click_element_by_script(self._force_logout_button_script())
        self.wait_login_page_visible()

    def wait_login_page_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or int(self.config.get("timeouts", {}).get("page_seconds", 10))
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                if self.cdp.evaluate(self._login_page_visible_script()):
                    return
            except Exception:
                time.sleep(0.3)
                continue
            try:
                self.cdp.wait_for_selector(self.locator("password_input"), timeout=1000)
                return
            except Exception:
                pass
            time.sleep(0.3)
        raise TimeoutError("login page did not appear")

    def _assert_current_account(self, expected_username: str) -> None:
        if not self.is_logged_in():
            message = self.login_failed_message()
            raise LoginStateError(f"login failed: {message or 'logged_in_marker not found'}")
        current_username = self.current_account()
        if current_username and current_username != expected_username:
            raise LoginStateError(
                f"logged in account mismatch: expected={expected_username}, actual={current_username}"
            )

    def _current_account_from_state(self) -> str:
        script = """
        () => {
            const raw = localStorage.getItem("basic:state");
            if (!raw) return "";
            try {
                const state = JSON.parse(raw);
                const user = state.userInfo || {};
                return user.email || user.name || "";
            } catch {
                return "";
            }
        }
        """
        try:
            value = self.cdp.evaluate(script)
        except Exception:
            return ""
        return str(value or "").strip()

    def _current_team_from_state(self) -> str:
        script = """
        () => {
            const raw = localStorage.getItem("basic:state");
            if (!raw) return "";
            try {
                const state = JSON.parse(raw);
                const user = state.userInfo || {};
                return user.orgName || user.teamName || "";
            } catch {
                return "";
            }
        }
        """
        try:
            value = self.cdp.evaluate(script)
        except Exception:
            return ""
        return str(value or "").strip()

    def _open_account_menu(self) -> None:
        if self._is_account_menu_open():
            return
        self.click("account_menu")
        deadline = time.time() + 5
        while time.time() < deadline:
            if self._is_account_menu_open():
                return
            time.sleep(0.2)
        raise LoginStateError("account menu did not open")

    def _is_account_menu_open(self) -> bool:
        script = """
        () => {
            const el = document.querySelector(".userInfo-popover");
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }
        """
        try:
            return bool(self.cdp.evaluate(script))
        except Exception:
            return False

    def _open_switch_team_popover(self, timeout: int) -> None:
        self._open_account_menu()
        try:
            self.cdp.hover_element_by_script(self._switch_team_trigger_script())
        except Exception as exc:
            self._click_visible_text("切换团队", original_error=exc, within_selector=".userInfo-popover")

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._is_switch_team_popover_open():
                return
            try:
                self.cdp.click_element_by_script(self._switch_team_trigger_script(), timeout=1000)
                self.cdp.hover_element_by_script(self._switch_team_trigger_script(), timeout=1000)
            except Exception:
                pass
            time.sleep(0.2)
        raise LoginStateError("switch team popover did not open")

    def _is_switch_team_popover_open(self) -> bool:
        script = """
        () => {
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(".org-change-popover"))
                .some((el) => visible(el) && (el.innerText || el.textContent || "").trim().length > 0);
        }
        """
        try:
            return bool(self.cdp.evaluate(script))
        except Exception:
            return False

    def _wait_for_team_switch_item(self, team_name: str, timeout: int) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.cdp.evaluate(self._team_switch_item_exists_script(team_name)):
                    return
            except Exception:
                pass
            time.sleep(0.3)
        raise LoginStateError(f"team switch item did not appear before timeout: {team_name}")

    def _wait_for_visible_text(self, text: str, timeout: int) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._visible_text_rect(text):
                return
            time.sleep(0.5)
        raise LoginStateError(f"text did not appear before timeout: {text}")

    def _wait_until_current_team(self, team_name: str, timeout: int) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            current = self._current_team_from_state()
            if current == team_name:
                return
            try:
                if self.current_team() == team_name:
                    return
            except Exception:
                pass
            time.sleep(0.3)
        raise LoginStateError(f"team state did not switch before timeout: {team_name}")

    def _team_switch_item_exists_script(self, team_name: str) -> str:
        return f"""
        () => Boolean(({self._team_switch_item_body_script(team_name)})())
        """

    def _team_switch_item_script(self, team_name: str) -> str:
        return f"""
        () => ({self._team_switch_item_body_script(team_name)})()
        """

    def _switch_team_trigger_script(self) -> str:
        return """
        () => {
            const expected = "切换团队";
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const root = Array.from(document.querySelectorAll(".userInfo-popover")).find(visible);
            if (!root) return null;
            const candidates = Array.from(root.querySelectorAll("li, button, div, span"))
                .filter((el) => visible(el))
                .map((el) => {
                    const text = (el.innerText || el.textContent || "").trim();
                    const item = el.closest("li") || el;
                    const rect = item.getBoundingClientRect();
                    const itemText = (item.innerText || item.textContent || "").trim();
                    return {
                        el: item,
                        exact: text === expected || itemText === expected,
                        includes: text.includes(expected) || itemText.includes(expected),
                        area: rect.width * rect.height,
                    };
                })
                .filter((item) => item.includes && visible(item.el))
                .sort((left, right) => {
                    if (left.exact !== right.exact) return left.exact ? -1 : 1;
                    return left.area - right.area;
                });
            return candidates[0]?.el || null;
        }
        """

    def _team_switch_item_body_script(self, team_name: str) -> str:
        return f"""
        () => {{
            const expected = {json.dumps(team_name)};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const roots = Array.from(document.querySelectorAll(".org-change-popover, .el-popover, .el-popper"))
                .filter(visible)
                .reverse();
            for (const root of roots) {{
                const candidates = Array.from(root.querySelectorAll("li, .el-dropdown-menu__item, div, span"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim().includes(expected))
                    .map((el) => {{
                        const item = el.closest("li, .el-dropdown-menu__item, [role='menuitem']") || el;
                        const rect = item.getBoundingClientRect();
                        const text = (item.innerText || item.textContent || "").trim();
                        return {{
                            el: item,
                            exact: text === expected,
                            area: rect.width * rect.height,
                        }};
                    }})
                    .filter((item) => visible(item.el));
                candidates.sort((left, right) => {{
                    if (left.exact !== right.exact) return left.exact ? -1 : 1;
                    return left.area - right.area;
                }});
                if (candidates[0]) return candidates[0].el;
            }}
            return null;
        }}
        """

    def _click_visible_text(
        self,
        text: str,
        original_error: Exception | None = None,
        within_selector: str = "body",
    ) -> None:
        rect = self._visible_text_rect(text, within_selector=within_selector)
        if not rect:
            error = LoginStateError(f"visible text not found: {text}")
            if original_error:
                raise error from original_error
            raise error
        x = float(rect["x"]) + float(rect["width"]) / 2
        y = float(rect["y"]) + float(rect["height"]) / 2
        if hasattr(self.cdp, "click_at"):
            self.cdp.click_at(x, y)
            return

        click_script = f"""
        (() => {{
            const x = {json.dumps(x)};
            const y = {json.dumps(y)};
            const target = document.elementFromPoint(x, y);
            if (!target) return false;
            target.dispatchEvent(new MouseEvent("click", {{
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: x,
                clientY: y,
            }}));
            return true;
        }})()
        """
        if not self.cdp.evaluate(click_script):
            raise LoginStateError(f"click visible text failed: {text}")

    def _visible_text_rect(self, text: str, within_selector: str = "body") -> dict | None:
        script = f"""
        (() => {{
            const expectedText = {json.dumps(text)};
            const withinSelector = {json.dumps(within_selector)};
            const root = document.querySelector(withinSelector) || document.body;
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const candidates = Array.from(root.querySelectorAll("li,button,div,span"))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").includes(expectedText))
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    const text = (el.innerText || el.textContent || "").trim();
                    return {{
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height,
                        text,
                        exact: text === expectedText,
                        area: rect.width * rect.height,
                    }};
                }});
            candidates.sort((left, right) => {{
                if (left.exact !== right.exact) return left.exact ? -1 : 1;
                return left.area - right.area;
            }});
            return candidates[0] || null;
        }})()
        """
        try:
            result = self.cdp.evaluate(script)
        except Exception:
            return None
        return result if isinstance(result, dict) else None

    def _force_logout_popup_text_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const candidates = Array.from(document.querySelectorAll(
                ".el-message-box, .el-dialog, .el-overlay, .el-notification, .el-popover"
            )).filter(visible);
            for (const el of candidates.reverse()) {
                const text = (el.innerText || el.textContent || "").trim();
                if (text.includes(__LOGOUT_TEXT__)) return text;
            }
            return "";
        }
        """.replace("__LOGOUT_TEXT__", json.dumps("\u9000\u51fa\u767b\u5f55"))

    def _force_logout_button_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const overlays = Array.from(document.querySelectorAll(
                ".el-message-box, .el-dialog, .el-overlay, .el-notification, .el-popover"
            )).filter((el) => visible(el) && (el.innerText || el.textContent || "").includes(__LOGOUT_TEXT__));
            for (const overlay of overlays.reverse()) {
                const button = Array.from(overlay.querySelectorAll("button, [role='button'], a, span, div"))
                    .filter(visible)
                    .map((el) => ({
                        el: el.closest("button, [role='button'], a") || el,
                        text: (el.innerText || el.textContent || "").trim(),
                        area: el.getBoundingClientRect().width * el.getBoundingClientRect().height,
                    }))
                    .filter((item) => item.text === __LOGOUT_TEXT__)
                    .sort((left, right) => left.area - right.area)[0];
                if (button) return button.el;
            }
            return null;
        }
        """.replace("__LOGOUT_TEXT__", json.dumps("\u9000\u51fa\u767b\u5f55"))

    def _login_page_visible_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const inputs = Array.from(document.querySelectorAll("input")).filter(visible);
            const passwordInput = inputs.find((input) => input.type === "password");
            const loginButton = Array.from(document.querySelectorAll("button"))
                .find((button) => visible(button) && (button.innerText || button.textContent || "").trim() === __LOGIN_TEXT__);
            return Boolean(passwordInput && loginButton);
        }
        """.replace("__LOGIN_TEXT__", json.dumps("\u7acb\u5373\u767b\u5f55"))

    def _confirm_logout_dialog_if_present(self) -> None:
        for text in ("确定", "确认", "退出登录"):
            try:
                self.cdp.click_element_by_script(self._visible_overlay_button_script(text), timeout=1000)
                time.sleep(0.3)
                return
            except TimeoutError:
                continue

    def _visible_overlay_button_script(self, text: str) -> str:
        return """
        () => {
            const expected = __EXPECTED_TEXT__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const overlays = Array.from(document.querySelectorAll(
                ".el-message-box, .el-dialog, .el-overlay, .el-popover"
            )).filter(visible).reverse();
            for (const overlay of overlays) {
                const button = Array.from(overlay.querySelectorAll("button, [role='button'], a, span, div"))
                    .filter(visible)
                    .map((el) => ({
                        el: el.closest("button, [role='button'], a") || el,
                        text: (el.innerText || el.textContent || "").trim(),
                        area: el.getBoundingClientRect().width * el.getBoundingClientRect().height,
                    }))
                    .filter((item) => item.text === expected)
                    .sort((left, right) => left.area - right.area)[0];
                if (button) return button.el;
            }
            return null;
        }
        """.replace("__EXPECTED_TEXT__", json.dumps(text))

    def _login_button_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            return Array.from(document.querySelectorAll("button, [role='button']"))
                .find((button) => visible(button) && (button.innerText || button.textContent || "").trim() === __LOGIN_TEXT__)
                || null;
        }
        """.replace("__LOGIN_TEXT__", json.dumps("\u7acb\u5373\u767b\u5f55"))

    def _visible_message_text_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const candidates = Array.from(document.querySelectorAll(
                ".el-message, .el-notification, .el-message-box, .el-dialog, .el-form-item__error"
            ))
                .filter(visible)
                .map((el) => (el.innerText || el.textContent || "").trim())
                .filter(Boolean);
            return candidates.reverse()[0] || "";
        }
        """

    def _login_by_visible_inputs(self, username: str, password: str, original_error: Exception) -> None:
        script = f"""
        (() => {{
            const username = {json.dumps(username)};
            const password = {json.dumps(password)};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const setValue = (el, value) => {{
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
                setter.call(el, value);
                try {{
                    el.dispatchEvent(new InputEvent("input", {{
                        bubbles: true,
                        inputType: "insertText",
                        data: value,
                    }}));
                }} catch {{
                    el.dispatchEvent(new Event("input", {{ bubbles: true }}));
                }}
                el.dispatchEvent(new Event("change", {{ bubbles: true }}));
            }};
            const inputs = Array.from(document.querySelectorAll("input")).filter(visible);
            const usernameInput = inputs.find((el) => ["text", "email", ""].includes(el.type));
            const passwordInput = inputs.find((el) => el.type === "password");
            const loginButton = Array.from(document.querySelectorAll("button"))
                .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "立即登录");
            if (!usernameInput || !passwordInput || !loginButton) {{
                return {{
                    ok: false,
                    reason: "login controls not found",
                    inputCount: inputs.length,
                    buttonTexts: Array.from(document.querySelectorAll("button"))
                        .map((el) => (el.innerText || el.textContent || "").trim())
                        .filter(Boolean),
                }};
            }}
            setValue(usernameInput, username);
            setValue(passwordInput, password);
            const rect = loginButton.getBoundingClientRect();
            return {{
                ok: true,
                button: {{
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                }},
            }};
        }})()
        """
        try:
            result = self.cdp.evaluate(script)
        except Exception as exc:
            raise LoginStateError(f"login failed: selector login failed and fallback failed: {exc}") from original_error

        if not isinstance(result, dict) or not result.get("ok"):
            reason = result.get("reason") if isinstance(result, dict) else result
            raise LoginStateError(f"login failed: selector login failed and fallback failed: {reason}") from original_error

        button = result.get("button") or {}
        x = float(button["x"]) + float(button["width"]) / 2
        y = float(button["y"]) + float(button["height"]) / 2
        if hasattr(self.cdp, "click_at"):
            self.cdp.click_at(x, y)
            return

        click_script = f"""
        (() => {{
            const x = {json.dumps(x)};
            const y = {json.dumps(y)};
            const target = document.elementFromPoint(x, y);
            if (!target) return false;
            target.dispatchEvent(new MouseEvent("click", {{
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: x,
                clientY: y,
            }}));
            return true;
        }})()
        """
        if not self.cdp.evaluate(click_script):
            raise LoginStateError("login failed: fallback login button click failed") from original_error
