from __future__ import annotations

import time

from core.config import timeout_seconds as config_timeout_seconds
from pages.base_page import BasePage


class MemberPage(BasePage):
    locator_file = "member_locators.yaml"

    def recover_to_module_home(self) -> None:
        self.open_list()
        self.dismiss_blocking_overlays()

    def open_list(self) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_menu_item_script("成员列表"))
        self._wait_for_member_list()

    def open_member_edit_dialog(self, member_name: str) -> None:
        self.cdp.click_element_by_script(self._member_row_edit_button_script(member_name))
        self._wait_for_edit_member_dialog(member_name)

    def assign_environment_group_to_member(self, member_name: str, group_name: str) -> list[str]:
        self.open_member_edit_dialog(member_name)
        original_groups = self.selected_environment_groups_in_edit_dialog()
        if group_name not in original_groups:
            self._select_environment_group_in_edit_dialog(group_name)
        self._wait_edit_dialog_environment_group_selected(group_name)
        self.cdp.click_element_by_script(self._active_dialog_button_script("确定"))
        self._wait_for_overlay_closed()
        self.wait_member_environment_groups_contain(member_name, group_name)
        return original_groups

    def selected_environment_groups_in_edit_dialog(self) -> list[str]:
        values = self.cdp.evaluate(self._edit_dialog_environment_group_values_script())
        if not isinstance(values, list):
            return []
        return self._unique_non_empty([str(value) for value in values])

    def member_authorized_environment_groups(self, member_name: str) -> list[str]:
        values = self.cdp.evaluate(self._member_row_authorized_group_values_script(member_name))
        if not isinstance(values, list):
            return []
        return self._unique_non_empty([str(value) for value in values])

    def wait_member_environment_groups_equal(
        self,
        member_name: str,
        expected_groups: list[str],
        timeout_seconds: int | None = None,
    ) -> None:
        expected = set(self._unique_non_empty(expected_groups))
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            actual = set(self.member_authorized_environment_groups(member_name))
            if actual == expected:
                return
            time.sleep(0.3)
        raise TimeoutError(
            "member authorized environment groups did not match expected groups: "
            f"member={member_name}, expected={sorted(expected)}, actual={self.member_authorized_environment_groups(member_name)}"
        )

    def wait_member_environment_groups_contain(
        self,
        member_name: str,
        group_name: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            groups = self.member_authorized_environment_groups(member_name)
            if group_name in groups:
                return
            time.sleep(0.3)
        raise TimeoutError(f"member authorized environment groups did not contain group: {member_name}, {group_name}")

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
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    const button = Array.from(document.querySelectorAll(__CLOSE_BUTTON_SELECTOR__)).find(visible);
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

    def _wait_for_member_list(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._member_list_visible_script()):
                return
            time.sleep(0.2)
        raise RuntimeError("member list did not appear")

    def _wait_for_edit_member_dialog(self, member_name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._edit_member_dialog_visible_script(member_name)):
                return
            time.sleep(0.2)
        raise RuntimeError(f"edit member dialog did not appear: {member_name}")

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

    def _select_environment_group_in_edit_dialog(self, group_name: str) -> None:
        self.cdp.click_element_by_script(self._edit_dialog_environment_group_select_script())
        self.cdp.fill_element_by_script(self._edit_dialog_environment_group_input_script(), group_name)
        self.cdp.click_element_by_script(self._select_dropdown_item_script(group_name))

    def _wait_edit_dialog_environment_group_selected(self, group_name: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "search_result_seconds", 10)
        while time.time() < deadline:
            if group_name in self.selected_environment_groups_in_edit_dialog():
                return
            time.sleep(0.3)
        raise TimeoutError(f"environment group was not selected in edit member dialog: {group_name}")

    def _visible_menu_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const selector = {self.locator("member_menu_candidates")!r};
            const items = Array.from(document.querySelectorAll(selector))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
            return items[0] || null;
        }}
        """

    def _member_row_edit_button_script(self, member_name: str) -> str:
        return f"""
        () => {{
            const expectedName = {member_name!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            for (const row of rows) {{
                if (!(row.innerText || row.textContent || "").includes(expectedName)) continue;
                const operationCell = Array.from(row.children).filter(visible).at(-1) || row;
                const editIcon = Array.from(operationCell.querySelectorAll({self.locator("edit_icon")!r}))
                    .filter(visible)
                    .sort((left, right) => left.getBoundingClientRect().x - right.getBoundingClientRect().x)[0];
                if (editIcon) return editIcon.closest("button, [role='button']") || editIcon;
            }}
            return null;
        }}
        """

    def _active_dialog_button_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const dialogs = Array.from(document.querySelectorAll({self.locator("dialog")!r})).filter(visible);
            for (const dialog of dialogs.reverse()) {{
                const button = Array.from(dialog.querySelectorAll({self.locator("button")!r}))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (button) return button;
            }}
            return null;
        }}
        """

    def _edit_dialog_environment_group_values_script(self) -> str:
        return """
        () => {
            const clean = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const cleanText = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const dialogs = Array.from(document.querySelectorAll(__DIALOG_SELECTOR__)).filter(visible);
            for (const dialog of dialogs.reverse()) {
                const formItem = Array.from(dialog.querySelectorAll(__FORM_ITEM_SELECTOR__))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent).includes("环境分组"));
                if (!formItem) continue;
                const values = Array.from(formItem.querySelectorAll(".el-tag, .el-select__tags-text, .el-select__selected-item"))
                    .filter(visible)
                    .map((el) => clean(el.innerText || el.textContent))
                    .filter((text) => text && text !== "×" && text !== "环境分组" && !/^\\d{9,}$/.test(text));
                const textValues = cleanText(formItem.innerText || formItem.textContent)
                    .replace(/^环境分组\\s*/, "")
                    .split(/\\s+/)
                    .map((text) => clean(text))
                    .filter((text) => text && text !== "×" && text !== "环境分组" && !/^\\d{9,}$/.test(text));
                return Array.from(new Set(values.concat(textValues)));
            }
            return [];
        }
        """.replace("__DIALOG_SELECTOR__", repr(self.locator("dialog"))).replace(
            "__FORM_ITEM_SELECTOR__",
            repr(self.locator("form_item")),
        )

    def _edit_dialog_environment_group_select_script(self) -> str:
        return """
        () => {
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const dialogs = Array.from(document.querySelectorAll(__DIALOG_SELECTOR__)).filter(visible);
            for (const dialog of dialogs.reverse()) {
                const formItem = Array.from(dialog.querySelectorAll(__FORM_ITEM_SELECTOR__))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent).includes("环境分组"));
                const select = formItem?.querySelector(__SELECT_CONTROL_SELECTOR__);
                if (select && visible(select)) return select;
            }
            return null;
        }
        """.replace("__DIALOG_SELECTOR__", repr(self.locator("dialog"))).replace(
            "__FORM_ITEM_SELECTOR__",
            repr(self.locator("form_item")),
        ).replace("__SELECT_CONTROL_SELECTOR__", repr(self.locator("select_control")))

    def _edit_dialog_environment_group_input_script(self) -> str:
        return """
        () => {
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const dialogs = Array.from(document.querySelectorAll(__DIALOG_SELECTOR__)).filter(visible);
            for (const dialog of dialogs.reverse()) {
                const formItem = Array.from(dialog.querySelectorAll(__FORM_ITEM_SELECTOR__))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent).includes("环境分组"));
                const input = formItem?.querySelector("input");
                if (input && visible(input)) return input;
            }
            return null;
        }
        """.replace("__DIALOG_SELECTOR__", repr(self.locator("dialog"))).replace(
            "__FORM_ITEM_SELECTOR__",
            repr(self.locator("form_item")),
        )

    def _select_dropdown_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const items = Array.from(document.querySelectorAll({self.locator("select_dropdown_item")!r}))
                .filter(visible)
                .filter((item) => (item.innerText || item.textContent || "").trim() === expectedText);
            return items[0] || null;
        }}
        """

    def _member_row_authorized_group_values_script(self, member_name: str) -> str:
        return f"""
        () => {{
            const expectedName = {member_name!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").trim();
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const headers = Array.from(document.querySelectorAll(".el-table__header-wrapper th, thead th"))
                .filter(visible)
                .map((header) => cleanCompact(header.innerText || header.textContent));
            let groupCellIndex = headers.findIndex((text) => text.includes("授权环境分组"));
            if (groupCellIndex < 0) groupCellIndex = headers.findIndex((text) => text === "环境分组");
            if (groupCellIndex < 0) groupCellIndex = 3;
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            for (const row of rows) {{
                if (!(row.innerText || row.textContent || "").includes(expectedName)) continue;
                const cells = Array.from(row.children).filter(visible);
                const groupCell = cells[groupCellIndex] || cells[3] || null;
                if (!groupCell) return [];
                const text = clean(groupCell.innerText || groupCell.textContent);
                if (!text || text === "--") return [];
                return text.split(/[、,，\\n]+/).map((item) => clean(item)).filter(Boolean);
            }}
            return [];
        }}
        """

    def _member_list_visible_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const bodyText = document.body ? (document.body.innerText || document.body.textContent || "") : "";
            const hasCreate = Array.from(document.querySelectorAll("button, div, span, a"))
                .some((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "创建成员");
            const hasTable = Array.from(document.querySelectorAll(".el-table, table")).some(visible);
            return bodyText.includes("成员列表") && (hasCreate || hasTable);
        }
        """

    def _edit_member_dialog_visible_script(self, member_name: str) -> str:
        return f"""
        () => {{
            const expectedName = {member_name!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            return Array.from(document.querySelectorAll({self.locator("dialog")!r}))
                .filter(visible)
                .some((dialog) => {{
                    const text = dialog.innerText || dialog.textContent || "";
                    const inputValues = Array.from(dialog.querySelectorAll("input"))
                        .map((input) => input.value || input.getAttribute("value") || "")
                        .filter(Boolean);
                    return text.includes("编辑内部成员")
                        && text.includes("环境分组")
                        && inputValues.includes(expectedName);
                }});
        }}
        """

    def _unique_non_empty(self, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            clean_value = str(value).strip()
            if clean_value.isdigit() and len(clean_value) > 8:
                continue
            if clean_value and clean_value not in result:
                result.append(clean_value)
        return result
