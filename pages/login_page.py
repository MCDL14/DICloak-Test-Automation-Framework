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
        self._assert_current_account(expected_username)
        self.ensure_current_team(expected_team)

    def is_logged_in(self) -> bool:
        try:
            return bool(
                self.cdp.wait_for_selector(
                    self.locator("logged_in_marker"),
                    timeout=timeout_ms(self.config, "login_marker_seconds", 3),
                )
            )
        except Exception:
            return False

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

    def login_failed_message(self) -> str:
        try:
            return self.text("login_error")
        except Exception:
            return ""

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
        self._open_account_menu()
        try:
            self.click("switch_team_button")
        except Exception as exc:
            self._click_visible_text("切换团队", original_error=exc, within_selector=".userInfo-popover")

        self._wait_for_visible_text(team_name, timeout=timeout)
        self._click_visible_text(team_name, within_selector="body")
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
            if self._current_team_from_state() == team_name:
                return
            time.sleep(0.5)
        raise LoginStateError(f"team state did not switch before timeout: {team_name}")

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
