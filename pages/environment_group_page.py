from __future__ import annotations

import time

from core.config import timeout_seconds as config_timeout_seconds
from pages.base_page import BasePage


class EnvironmentGroupPage(BasePage):
    locator_file = "environment_group_locators.yaml"

    def recover_to_module_home(self) -> None:
        self.open_list()
        self.dismiss_blocking_overlays()

    def open_list(self) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_menu_item_script("环境分组"))
        self._wait_for_group_list()

    def create_group(self, group_name: str) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_text_element_script("创建环境分组"))
        self.cdp.fill_element_by_script(self._group_name_input_script(), group_name)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()
        self.wait_group_visible(group_name)

    def delete_group(self, group_name: str, delete_environments: bool = False) -> None:
        self.cdp.click_element_by_script(self._group_row_action_button_script(group_name, "删除"))
        if delete_environments:
            self._check_delete_group_environments()
        self.confirm_secondary_dialog()
        self.wait_group_absent(group_name)

    def delete_group_if_exists(self, group_name: str, delete_environments: bool = False) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "search_result_seconds", 10)
        while time.time() < deadline:
            if not self.group_visible(group_name):
                return
            self.delete_group(group_name, delete_environments=delete_environments)
            time.sleep(0.3)
        if self.group_visible(group_name):
            raise TimeoutError(f"environment group still exists after cleanup: {group_name}")

    def group_visible(self, group_name: str) -> bool:
        return bool(self.cdp.evaluate(self._group_exists_script(group_name)))

    def wait_group_visible(self, group_name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.group_visible(group_name):
                return
            time.sleep(0.3)
        raise TimeoutError(f"environment group did not appear in list: {group_name}")

    def wait_group_absent(self, group_name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.group_visible(group_name):
                return
            time.sleep(0.3)
        raise TimeoutError(f"environment group still exists in list: {group_name}")

    def dismiss_blocking_overlays(self) -> None:
        for _ in range(4):
            has_overlay = self.cdp.evaluate(
                """
                () => Boolean(document.querySelector(__OVERLAY_SELECTOR__))
                """.replace("__OVERLAY_SELECTOR__", repr(self.locator("blocking_overlay")))
            )
            if not has_overlay:
                return
            clicked = self.cdp.evaluate(
                """
                () => {
                    const closeButtonSelector = __CLOSE_BUTTON_SELECTOR__;
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    const button = Array.from(document.querySelectorAll(closeButtonSelector)).find(visible);
                    if (button) {
                        button.click();
                        return true;
                    }
                    return false;
                }
                """.replace("__CLOSE_BUTTON_SELECTOR__", repr(self.locator("overlay_close_button")))
            )
            if not clicked:
                self.cdp.press("Escape")
            time.sleep(0.5)

    def confirm_secondary_dialog(self, preferred_texts: tuple[str, ...] = ("确定", "确认")) -> None:
        last_error: TimeoutError | None = None
        for text in preferred_texts:
            try:
                self.cdp.click_element_by_script(self._active_overlay_button_script(text), timeout=1000)
                self._wait_for_overlay_closed()
                return
            except TimeoutError as exc:
                last_error = exc
        raise TimeoutError(f"secondary dialog confirm button was not found: {preferred_texts}") from last_error

    def _check_delete_group_environments(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            result = str(self.cdp.evaluate(self._check_delete_group_environments_script()) or "")
            if result == "checked":
                return
            time.sleep(0.2)
        raise TimeoutError("delete-group environment checkbox was not checked before confirming")

    def _wait_for_group_list(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._group_list_visible_script()):
                return
            time.sleep(0.2)
        raise RuntimeError("environment group list did not appear")

    def _wait_for_overlay_closed(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible_count = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-drawer, .el-dialog, .el-message-box"))
                        .filter(visible).length;
                }
                """
            )
            if int(visible_count or 0) == 0:
                return
            time.sleep(0.2)
        raise TimeoutError("overlay did not close")

    def _visible_menu_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const selector = {self.locator("environment_group_menu_candidates")!r};
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const candidates = Array.from(document.querySelectorAll(selector))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText)
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    return {{ el, visibleArea: Math.max(0, rect.width) * Math.max(0, Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0)) }};
                }})
                .sort((left, right) => right.visibleArea - left.visibleArea);
            return candidates[0]?.el || null;
        }}
        """

    def _visible_text_element_script(self, text: str) -> str:
        return f"""
        () => {{
            const selector = {self.locator("visible_text_candidates")!r};
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const candidates = Array.from(document.querySelectorAll(selector))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText)
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    return {{ el, area: rect.width * rect.height }};
                }})
                .sort((left, right) => left.area - right.area);
            return candidates[0]?.el || null;
        }}
        """

    def _active_overlay_button_script(self, text: str) -> str:
        return f"""
        () => {{
            const overlaySelector = {self.locator("blocking_overlay")!r};
            const buttonSelector = {self.locator("button")!r};
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(overlaySelector))
                .filter((el) => visible(el));
            for (const overlay of overlays.reverse()) {{
                const button = Array.from(overlay.querySelectorAll(buttonSelector))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (button) return button;
            }}
            return null;
        }}
        """

    def _check_delete_group_environments_script(self) -> str:
        return f"""
        () => {{
            const overlaySelector = {self.locator("blocking_overlay")!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
            const checked = (checkbox) => {{
                const input = checkbox.querySelector?.("input[type='checkbox']");
                return Boolean(checkbox.classList?.contains("is-checked") || input?.checked);
            }};
            const overlays = Array.from(document.querySelectorAll(overlaySelector))
                .filter((el) => visible(el));
            for (const overlay of overlays.reverse()) {{
                const candidates = Array.from(overlay.querySelectorAll(".el-checkbox, label"))
                    .filter(visible)
                    .map((el) => el.closest(".el-checkbox") || el)
                    .filter((el, index, array) => array.indexOf(el) === index)
                    .filter((el) => {{
                        const text = clean(el.innerText || el.textContent);
                        return text.includes("删除") && text.includes("环境") && text.includes("分组");
                    }});
                for (const checkbox of candidates) {{
                    if (checked(checkbox)) return "checked";
                    const input = checkbox.querySelector?.("input[type='checkbox']");
                    if (input && !input.checked) input.click();
                    else checkbox.click();
                    return checked(checkbox) ? "checked" : "clicked";
                }}
            }}
            return "missing";
        }}
        """

    def _group_name_input_script(self) -> str:
        return f"""
        () => {{
            const inputSelector = {self.locator("input")!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(".el-drawer, .el-dialog"))
                .filter(visible);
            for (const overlay of overlays.reverse()) {{
                const labels = Array.from(overlay.querySelectorAll(".el-form-item"))
                    .filter((item) => visible(item) && (item.innerText || item.textContent || "").includes("分组名称"));
                for (const item of labels) {{
                    const input = Array.from(item.querySelectorAll(inputSelector)).find(visible);
                    if (input) return input;
                }}
                const byPlaceholder = Array.from(overlay.querySelectorAll(inputSelector))
                    .find((input) => visible(input) && String(input.getAttribute("placeholder") || "").includes("分组"));
                if (byPlaceholder) return byPlaceholder;
                const firstInput = Array.from(overlay.querySelectorAll(inputSelector)).find(visible);
                if (firstInput) return firstInput;
            }}
            return null;
        }}
        """

    def _group_exists_script(self, group_name: str) -> str:
        return f"""
        () => {{
            const expectedName = {group_name!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible);
            return rows.some((row) => Array.from(row.querySelectorAll(".cell, td, div, span"))
                .some((cell) => (cell.innerText || cell.textContent || "").trim() === expectedName));
        }}
        """

    def _group_row_action_button_script(self, group_name: str, action_text: str) -> str:
        return f"""
        () => {{
            const expectedName = {group_name!r};
            const expectedAction = {action_text!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible);
            for (const row of rows) {{
                const hasName = Array.from(row.querySelectorAll(".cell, td, div, span"))
                    .some((cell) => (cell.innerText || cell.textContent || "").trim() === expectedName);
                if (!hasName) continue;
                const actions = Array.from(row.querySelectorAll("button, a, span, div"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedAction)
                    .map((el) => {{
                        const rect = el.getBoundingClientRect();
                        return {{ el, area: rect.width * rect.height }};
                    }})
                    .sort((left, right) => left.area - right.area);
                if (actions[0]) return actions[0].el;

                if (expectedAction === "删除") {{
                    const cells = Array.from(row.children).filter(visible);
                    const operationCell = cells[cells.length - 1] || row;
                    const iconActions = Array.from(operationCell.querySelectorAll("button, [role='button'], svg, i, span, div"))
                        .filter(visible)
                        .map((el) => {{
                            const rect = el.getBoundingClientRect();
                            const clickable = el.closest("button, [role='button']") || el;
                            return {{
                                el: clickable,
                                x: rect.x,
                                y: rect.y,
                                width: rect.width,
                                height: rect.height,
                                area: rect.width * rect.height,
                            }};
                        }})
                        .filter((item) => item.area > 0)
                        .sort((left, right) => right.x - left.x || left.area - right.area);
                    if (iconActions[0]) return iconActions[0].el;
                }}
            }}
            return null;
        }}
        """

    def _group_list_visible_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const bodyText = document.body ? (document.body.innerText || document.body.textContent || "") : "";
            const hasCreate = Array.from(document.querySelectorAll("button, div, span, a"))
                .some((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "创建环境分组");
            const hasTable = Array.from(document.querySelectorAll(".el-table, table")).some(visible);
            return bodyText.includes("环境分组") && (hasCreate || hasTable);
        }
        """
