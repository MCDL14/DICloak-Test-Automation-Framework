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

    def first_editable_group(
        self,
        excluded_names: set[str] | None = None,
        excluded_remarks: set[str] | None = None,
    ) -> dict[str, str]:
        excluded_names = excluded_names or set()
        excluded_remarks = excluded_remarks or set()
        groups = self.cdp.evaluate(self._editable_group_rows_script())
        if not isinstance(groups, list):
            groups = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            normalized = {
                "id": str(group.get("id", "") or "").strip(),
                "name": str(group.get("name", "") or "").strip(),
                "remark": str(group.get("remark", "") or "").strip(),
                "text": str(group.get("text", "") or "").strip(),
            }
            if (
                normalized["id"]
                and normalized["name"]
                and normalized["name"] not in excluded_names
                and normalized["remark"] not in excluded_remarks
            ):
                return normalized
        raise RuntimeError("no editable environment group was found in current list")

    def edit_group_name_by_id(self, group_id: str, group_name: str) -> None:
        clean_id = str(group_id).strip()
        clean_name = str(group_name).strip()
        if not clean_id:
            raise ValueError("environment group id is empty")
        if not clean_name:
            raise ValueError("environment group name is empty")
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._group_row_edit_button_by_id_script(clean_id))
        self._wait_edit_group_dialog_visible()
        self.cdp.fill_element_by_script(self._edit_group_name_input_script(), clean_name)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()
        self.wait_group_name_by_id(clean_id, clean_name)

    def edit_group_remark_by_id(self, group_id: str, remark: str) -> None:
        clean_id = str(group_id).strip()
        clean_remark = str(remark)
        if not clean_id:
            raise ValueError("environment group id is empty")
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._group_row_edit_button_by_id_script(clean_id))
        self._wait_edit_group_dialog_visible()
        self.cdp.fill_element_by_script(self._edit_group_remark_input_script(), clean_remark)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()
        self.wait_group_remark_by_id(clean_id, self._remark_list_display_value(clean_remark))

    def group_name_by_id(self, group_id: str) -> str:
        return str(self.cdp.evaluate(self._group_name_by_id_script(str(group_id).strip())) or "").strip()

    def group_remark_by_id(self, group_id: str) -> str:
        return str(self.cdp.evaluate(self._group_remark_by_id_script(str(group_id).strip())) or "").strip()

    def _remark_list_display_value(self, remark: str) -> str:
        return str(remark).strip() or "--"

    def wait_group_name_by_id(
        self,
        group_id: str,
        expected_name: str,
        timeout_seconds: int | None = None,
    ) -> None:
        clean_id = str(group_id).strip()
        clean_name = str(expected_name).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.group_name_by_id(clean_id) == clean_name:
                return
            time.sleep(0.3)
        actual_name = self.group_name_by_id(clean_id)
        raise TimeoutError(
            f"environment group name did not match by id: id={clean_id}, expected={clean_name}, actual={actual_name}"
        )

    def wait_group_remark_by_id(
        self,
        group_id: str,
        expected_remark: str,
        timeout_seconds: int | None = None,
    ) -> None:
        clean_id = str(group_id).strip()
        clean_remark = self._remark_list_display_value(expected_remark)
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.group_remark_by_id(clean_id) == clean_remark:
                return
            time.sleep(0.3)
        actual_remark = self.group_remark_by_id(clean_id)
        raise TimeoutError(
            "environment group remark did not match by id: "
            f"id={clean_id}, expected={clean_remark}, actual={actual_remark}"
        )

    def filter_by_containing_environment(self, environment_name: str) -> None:
        clean_name = str(environment_name).strip()
        if not clean_name:
            raise ValueError("environment name for group filter is empty")
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._containing_environment_filter_select_script())
        self.cdp.fill_element_by_script(self._containing_environment_filter_input_script(), clean_name)
        self.cdp.click_element_by_script(self._select_dropdown_item_script(clean_name))
        self.wait_containing_environment_filter_result(clean_name)

    def filter_by_authorized_member(self, member_name: str) -> None:
        clean_name = str(member_name).strip()
        if not clean_name:
            raise ValueError("member name for group filter is empty")
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._filter_select_script("授权成员"))
        try:
            self.cdp.click_element_by_script(self._select_dropdown_item_script(clean_name), timeout=3000)
        except Exception:
            self.cdp.evaluate(self._set_filter_input_value_script("授权成员", clean_name))
            self.cdp.click_element_by_script(self._select_dropdown_item_script(clean_name))
        self.cdp.click_element_by_script(self._search_filter_button_script())
        self.wait_authorized_member_filter_result(clean_name)

    def filter_by_group_name(self, group_name: str) -> None:
        clean_name = str(group_name).strip()
        if not clean_name:
            raise ValueError("group name for group filter is empty")
        self.dismiss_blocking_overlays()
        self.switch_group_text_filter_mode("分组名称")
        self.cdp.fill_element_by_script(self._group_text_filter_input_script(), clean_name)
        self.cdp.click_element_by_script(self._search_filter_button_script())
        self.wait_group_name_filter_result(clean_name)

    def filter_by_group_remark(self, remark: str) -> None:
        clean_remark = str(remark).strip()
        if not clean_remark:
            raise ValueError("remark for group filter is empty")
        self.dismiss_blocking_overlays()
        self.switch_group_text_filter_mode("备注")
        self.cdp.fill_element_by_script(self._group_text_filter_input_script(), clean_remark)
        self.cdp.click_element_by_script(self._search_filter_button_script())
        self.wait_group_remark_filter_result(clean_remark)

    def switch_group_text_filter_mode(self, mode_name: str) -> None:
        clean_mode = str(mode_name).strip()
        if not clean_mode:
            raise ValueError("group text filter mode is empty")
        if self.cdp.evaluate(self._group_text_filter_mode_selected_script(clean_mode)):
            return
        self.cdp.click_element_by_script(self._group_text_filter_mode_button_script())
        self.cdp.click_element_by_script(self._dropdown_menu_item_script(clean_mode))
        self.wait_group_text_filter_mode(clean_mode)

    def clear_filters(self) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._clear_filter_button_script())
        self.wait_filters_cleared()

    def group_rows_in_current_list(self) -> list[dict[str, str]]:
        rows = self.cdp.evaluate(self._group_rows_script())
        if not isinstance(rows, list):
            return []
        normalized: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "id": str(row.get("id", "") or "").strip(),
                    "name": str(row.get("name", "") or "").strip(),
                    "remark": str(row.get("remark", "") or "").strip(),
                    "text": str(row.get("text", "") or "").strip(),
                }
            )
        return normalized

    def wait_containing_environment_filter_result(
        self,
        environment_name: str,
        timeout_seconds: int | None = None,
    ) -> list[dict[str, str]]:
        clean_name = str(environment_name).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            rows = self.group_rows_in_current_list()
            if rows and all(clean_name in row["text"] for row in rows):
                return rows
            time.sleep(0.3)
        raise TimeoutError(f"environment group filter result did not match containing environment: {clean_name}")

    def wait_containing_environment_filter_cleared(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._filter_empty_script("包含环境")):
                return
            time.sleep(0.3)
        raise TimeoutError("environment group containing-environment filter was not cleared")

    def wait_filters_cleared(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        filter_labels = ("分组名称", "包含环境", "授权成员")
        while time.time() < deadline:
            if all(self.cdp.evaluate(self._filter_empty_script(label)) for label in filter_labels):
                return
            time.sleep(0.3)
        raise TimeoutError("environment group filters were not cleared")

    def wait_group_name_filter_result(
        self,
        group_name: str,
        timeout_seconds: int | None = None,
    ) -> list[dict[str, str]]:
        clean_name = str(group_name).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            rows = self.group_rows_in_current_list()
            if rows and all(clean_name in row["name"] for row in rows):
                return rows
            time.sleep(0.3)
        raise TimeoutError(f"environment group filter result did not match group name: {clean_name}")

    def wait_group_remark_filter_result(
        self,
        remark: str,
        timeout_seconds: int | None = None,
    ) -> list[dict[str, str]]:
        clean_remark = str(remark).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            rows = self.group_rows_in_current_list()
            if rows and all(clean_remark in row["remark"] for row in rows):
                return rows
            time.sleep(0.3)
        raise TimeoutError(f"environment group filter result did not match remark: {clean_remark}")

    def wait_group_text_filter_mode(self, mode_name: str, timeout_seconds: int | None = None) -> None:
        clean_mode = str(mode_name).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._group_text_filter_mode_selected_script(clean_mode)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"environment group text filter mode was not selected: {clean_mode}")

    def wait_authorized_member_filter_result(
        self,
        member_name: str,
        timeout_seconds: int | None = None,
    ) -> list[dict[str, str]]:
        clean_name = str(member_name).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            rows = self.group_rows_in_current_list()
            if (
                rows
                and all(clean_name in row["text"] for row in rows)
                and self.cdp.evaluate(self._filter_has_value_script("授权成员", clean_name))
            ):
                return rows
            time.sleep(0.3)
        raise TimeoutError(f"environment group filter result did not match authorized member: {clean_name}")

    def authorized_member_popover_text(self, group_name: str) -> str:
        self.cdp.click_element_by_script(self._group_authorized_members_view_script(group_name))
        return self._wait_authorized_member_popover_text()

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
        timeout_ms = config_timeout_seconds(self.config, "page_seconds", 10) * 1000
        for text in preferred_texts:
            try:
                self.cdp.click_element_by_script(self._active_overlay_button_script(text), timeout=timeout_ms)
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
                    return Array.from(document.querySelectorAll(__OVERLAY_SELECTOR__))
                        .filter(visible).length;
                }
                """.replace("__OVERLAY_SELECTOR__", repr(self.locator("blocking_overlay")))
            )
            if int(visible_count or 0) == 0:
                return
            time.sleep(0.2)
        raise TimeoutError("overlay did not close")

    def _wait_edit_group_dialog_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._edit_group_dialog_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("edit environment group dialog did not appear")

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
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(overlaySelector))
                .filter((el) => visible(el));
            for (const overlay of overlays.reverse()) {{
                const button = Array.from(overlay.querySelectorAll(buttonSelector))
                    .find((el) => {{
                        if (!visible(el) || el.disabled || el.getAttribute("aria-disabled") === "true") return false;
                        const text = clean(el.innerText || el.textContent);
                        return text === clean(expectedText) || text.includes(clean(expectedText));
                    }});
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
                const candidates = Array.from(overlay.querySelectorAll(__CHECKBOX_OR_LABEL_SELECTOR__))
                    .filter(visible)
                    .map((el) => el.closest(__CHECKBOX_ROOT_SELECTOR__) || el)
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
        """.replace("__CHECKBOX_OR_LABEL_SELECTOR__", repr(self.locator("checkbox_or_label"))).replace(
            "__CHECKBOX_ROOT_SELECTOR__",
            repr(self.locator("checkbox_root")),
        )

    def _group_name_input_script(self) -> str:
        return f"""
        () => {{
            const inputSelector = {self.locator("input")!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(__DIALOG_OR_DRAWER_SELECTOR__))
                .filter(visible);
            for (const overlay of overlays.reverse()) {{
                const labels = Array.from(overlay.querySelectorAll(__FORM_ITEM_SELECTOR__))
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
        """.replace("__DIALOG_OR_DRAWER_SELECTOR__", repr(self.locator("dialog_or_drawer"))).replace(
            "__FORM_ITEM_SELECTOR__",
            repr(self.locator("form_item")),
        )

    def _edit_group_name_input_script(self) -> str:
        return f"""
        () => {{
            const inputSelector = {self.locator("input")!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const dialogs = Array.from(document.querySelectorAll(__DIALOG_SELECTOR__))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("编辑环境分组"));
            for (const dialog of dialogs.reverse()) {{
                const byPlaceholder = Array.from(dialog.querySelectorAll(inputSelector))
                    .find((input) => visible(input) && String(input.getAttribute("placeholder") || "").includes("请填写分组名称"));
                if (byPlaceholder) return byPlaceholder;
                const formItem = Array.from(dialog.querySelectorAll(__FORM_ITEM_SELECTOR__))
                    .find((item) => visible(item) && (item.innerText || item.textContent || "").includes("分组名称"));
                const input = formItem ? Array.from(formItem.querySelectorAll(inputSelector)).find(visible) : null;
                if (input) return input;
            }}
            return null;
        }}
        """.replace("__DIALOG_SELECTOR__", repr(self.locator("dialog"))).replace(
            "__FORM_ITEM_SELECTOR__",
            repr(self.locator("form_item")),
        )

    def _edit_group_remark_input_script(self) -> str:
        return f"""
        () => {{
            const inputSelector = {self.locator("input")!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const dialogs = Array.from(document.querySelectorAll(__DIALOG_SELECTOR__))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("编辑环境分组"));
            for (const dialog of dialogs.reverse()) {{
                const byPlaceholder = Array.from(dialog.querySelectorAll(inputSelector))
                    .find((input) => visible(input) && String(input.getAttribute("placeholder") || "").includes("备注"));
                if (byPlaceholder) return byPlaceholder;
                const formItem = Array.from(dialog.querySelectorAll(__FORM_ITEM_SELECTOR__))
                    .find((item) => visible(item) && (item.innerText || item.textContent || "").includes("备注"));
                const input = formItem ? Array.from(formItem.querySelectorAll(inputSelector)).find(visible) : null;
                if (input) return input;
            }}
            return null;
        }}
        """.replace("__DIALOG_SELECTOR__", repr(self.locator("dialog"))).replace(
            "__FORM_ITEM_SELECTOR__",
            repr(self.locator("form_item")),
        )

    def _containing_environment_filter_select_script(self) -> str:
        return self._filter_select_script("包含环境")

    def _filter_select_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {label_text!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const formItems = Array.from(document.querySelectorAll(__FORM_ITEM_SELECTOR__))
                .filter(visible)
                .filter((item) => clean(item.innerText || item.textContent).includes(clean(expectedLabel)));
            for (const formItem of formItems) {{
                const select = formItem.querySelector(__SELECT_CONTROL_SELECTOR__);
                if (select && visible(select)) return select;
            }}
            return null;
        }}
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__SELECT_CONTROL_SELECTOR__",
            repr(self.locator("filter_select_control")),
        )

    def _containing_environment_filter_input_script(self) -> str:
        return self._filter_input_script("包含环境")

    def _group_name_filter_input_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(__INPUT_SELECTOR__))
                .filter(visible)
                .find((input) => String(input.getAttribute("placeholder") || "").includes("分组名称")) || null;
        }
        """.replace("__INPUT_SELECTOR__", repr(self.locator("input")))

    def _group_text_filter_input_script(self) -> str:
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
            const formItems = Array.from(document.querySelectorAll(__FORM_ITEM_SELECTOR__)).filter(visible);
            for (const formItem of formItems) {
                if (!formItem.querySelector(__MODE_ICON_SELECTOR__)) continue;
                const input = Array.from(formItem.querySelectorAll(__INPUT_SELECTOR__)).find(visible);
                if (input) return input;
            }
            return Array.from(document.querySelectorAll(__INPUT_SELECTOR__))
                .filter(visible)
                .find((input) => {
                    const placeholder = String(input.getAttribute("placeholder") || "");
                    return placeholder.includes("分组名称") || placeholder.includes("备注");
                }) || null;
        }
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__MODE_ICON_SELECTOR__",
            repr(self.locator("group_text_filter_mode_icon")),
        ).replace("__INPUT_SELECTOR__", repr(self.locator("input")))

    def _group_text_filter_mode_button_script(self) -> str:
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
            const formItems = Array.from(document.querySelectorAll(__FORM_ITEM_SELECTOR__)).filter(visible);
            for (const formItem of formItems) {
                const icon = formItem.querySelector(__MODE_ICON_SELECTOR__);
                if (!icon || !visible(icon)) continue;
                return icon.closest("button, [role='button']") || icon;
            }
            return null;
        }
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__MODE_ICON_SELECTOR__",
            repr(self.locator("group_text_filter_mode_icon")),
        )

    def _group_text_filter_mode_selected_script(self, mode_name: str) -> str:
        return f"""
        () => {{
            const expectedMode = {mode_name!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const formItems = Array.from(document.querySelectorAll(__FORM_ITEM_SELECTOR__)).filter(visible);
            for (const formItem of formItems) {{
                if (!formItem.querySelector(__MODE_ICON_SELECTOR__)) continue;
                const input = Array.from(formItem.querySelectorAll(__INPUT_SELECTOR__)).find(visible);
                if (String(input?.getAttribute("placeholder") || "").includes(expectedMode)) return true;
            }}
            return false;
        }}
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__MODE_ICON_SELECTOR__",
            repr(self.locator("group_text_filter_mode_icon")),
        ).replace("__INPUT_SELECTOR__", repr(self.locator("input")))

    def _filter_input_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {label_text!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const formItems = Array.from(document.querySelectorAll(__FORM_ITEM_SELECTOR__))
                .filter(visible)
                .filter((item) => clean(item.innerText || item.textContent).includes(clean(expectedLabel)));
            for (const formItem of formItems) {{
                const input = formItem.querySelector(__INPUT_SELECTOR__);
                if (input && visible(input)) return input;
            }}
            return null;
        }}
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__INPUT_SELECTOR__",
            repr(self.locator("input")),
        )

    def _set_filter_input_value_script(self, label_text: str, value: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {label_text!r};
            const expectedValue = {value!r};
            const clean = (text) => String(text || "").replace(/\\s+/g, "");
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const formItems = Array.from(document.querySelectorAll(__FORM_ITEM_SELECTOR__))
                .filter(visible)
                .filter((item) => clean(item.innerText || item.textContent).includes(clean(expectedLabel)));
            for (const formItem of formItems) {{
                const input = Array.from(formItem.querySelectorAll(__INPUT_SELECTOR__)).find(visible);
                if (!input) continue;
                input.removeAttribute("readonly");
                input.focus();
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
                if (setter) setter.call(input, expectedValue);
                else input.value = expectedValue;
                input.dispatchEvent(new Event("input", {{ bubbles: true }}));
                input.dispatchEvent(new Event("change", {{ bubbles: true }}));
                return true;
            }}
            return false;
        }}
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__INPUT_SELECTOR__",
            repr(self.locator("input")),
        )

    def _search_filter_button_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(__BUTTON_SELECTOR__))
                .filter(visible)
                .find((button) => button.querySelector(__SEARCH_FILTER_ICON_SELECTOR__)) || null;
        }
        """.replace("__BUTTON_SELECTOR__", repr(self.locator("button"))).replace(
            "__SEARCH_FILTER_ICON_SELECTOR__",
            repr(self.locator("search_filter_icon")),
        )

    def _select_dropdown_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const items = Array.from(document.querySelectorAll(__DROPDOWN_ITEM_SELECTOR__))
                .filter(visible)
                .filter((item) => (item.innerText || item.textContent || "").trim() === expectedText);
            return items[0] || null;
        }}
        """.replace("__DROPDOWN_ITEM_SELECTOR__", repr(self.locator("select_dropdown_item")))

    def _dropdown_menu_item_script(self, text: str) -> str:
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
            const items = Array.from(document.querySelectorAll(__DROPDOWN_MENU_ITEM_SELECTOR__))
                .filter(visible)
                .filter((item) => (item.innerText || item.textContent || "").trim() === expectedText);
            return items[0] || null;
        }}
        """.replace("__DROPDOWN_MENU_ITEM_SELECTOR__", repr(self.locator("dropdown_menu_item")))

    def _clear_filter_button_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(__BUTTON_SELECTOR__))
                .filter(visible)
                .find((button) => button.querySelector(__CLEAR_FILTER_ICON_SELECTOR__)) || null;
        }
        """.replace("__BUTTON_SELECTOR__", repr(self.locator("button"))).replace(
            "__CLEAR_FILTER_ICON_SELECTOR__",
            repr(self.locator("clear_filter_icon")),
        )

    def _filter_has_value_script(self, label_text: str, expected_value: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {label_text!r};
            const expectedValue = {expected_value!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const formItems = Array.from(document.querySelectorAll(__FORM_ITEM_SELECTOR__))
                .filter(visible);
            return formItems.some((item) => {{
                const input = item.querySelector(__INPUT_SELECTOR__);
                const texts = Array.from(item.querySelectorAll(__FILTER_SELECTED_TEXT_SELECTOR__))
                    .filter(visible)
                    .map((el) => clean(el.innerText || el.textContent))
                    .filter(Boolean);
                const itemText = clean(item.innerText || item.textContent);
                const inputValue = input ? clean(input.value || input.getAttribute("value") || "") : "";
                return inputValue === clean(expectedValue)
                    || texts.includes(clean(expectedValue))
                    || itemText === clean(expectedValue)
                    || (itemText.includes(clean(expectedLabel)) && itemText.includes(clean(expectedValue)));
            }});
        }}
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__INPUT_SELECTOR__",
            repr(self.locator("input")),
        ).replace("__FILTER_SELECTED_TEXT_SELECTOR__", repr(self.locator("filter_selected_text_candidates")))

    def _filter_empty_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {label_text!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            if (clean(expectedLabel) === "分组名称") {{
                return Array.from(document.querySelectorAll(__INPUT_SELECTOR__))
                    .filter(visible)
                    .some((input) => clean(input.getAttribute("placeholder") || "").includes("分组名称")
                        && !String(input.value || input.getAttribute("value") || "").trim());
            }}
            const formItems = Array.from(document.querySelectorAll(__FORM_ITEM_SELECTOR__))
                .filter(visible)
                .filter((item) => clean(item.innerText || item.textContent).includes(clean(expectedLabel)));
            return formItems.some((item) => {{
                const input = item.querySelector(__INPUT_SELECTOR__);
                const selectedTexts = Array.from(item.querySelectorAll(__FILTER_SELECTED_TEXT_SELECTOR__))
                    .filter(visible)
                    .map((el) => clean(el.innerText || el.textContent))
                    .filter((text) => text && text !== "×" && text !== clean(expectedLabel));
                const inputValue = input ? String(input.value || input.getAttribute("value") || "").trim() : "";
                return !inputValue && selectedTexts.length === 0;
            }});
        }}
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__INPUT_SELECTOR__",
            repr(self.locator("input")),
        ).replace("__FILTER_SELECTED_TEXT_SELECTOR__", repr(self.locator("filter_selected_text_candidates")))

    def _group_rows_script(self) -> str:
        return f"""
        () => {{
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const parseNameAndId = (value) => {{
                const normalized = clean(value).replace(/\\s+/g, " ");
                const match = normalized.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                return {{
                    name: match ? clean(match[1]) : normalized,
                    id: match ? match[2] : "",
                }};
            }};
            const rowKey = (cells, rowIndex) => {{
                const parsed = parseNameAndId(cells[0] || "");
                if (parsed.id) return parsed.id;
                const createdAt = clean(cells[4] || "");
                return createdAt ? "created:" + createdAt : "row:" + rowIndex;
            }};
            return Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .map((row, rowIndex) => {{
                    const cells = Array.from(row.querySelectorAll(__TABLE_CELL_SELECTOR__))
                        .filter(visible)
                        .map((cell) => clean(cell.innerText || cell.textContent));
                    const text = clean(row.innerText || row.textContent);
                    const parsed = parseNameAndId(cells[0] || String(text.split("\\n")[0] || "").trim());
                    const id = rowKey(cells, rowIndex);
                    const name = parsed.name;
                    const remark = cells[1] || "";
                    return {{ id, name, remark, text }};
                }})
                .filter((row) => row.text);
        }}
        """.replace("__TABLE_CELL_SELECTOR__", repr(self.locator("table_cell")))

    def _editable_group_rows_script(self) -> str:
        return f"""
        () => {{
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const parseNameAndId = (value) => {{
                const normalized = clean(value);
                const match = normalized.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                return {{
                    name: match ? clean(match[1]) : normalized,
                    id: match ? match[2] : "",
                }};
            }};
            const rowKey = (cells, rowIndex) => {{
                const parsed = parseNameAndId(cells[0]?.innerText || cells[0]?.textContent || "");
                if (parsed.id) return parsed.id;
                const createdAt = clean(cells[4]?.innerText || cells[4]?.textContent || "");
                return createdAt ? "created:" + createdAt : "row:" + rowIndex;
            }};
            return Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .map((row, rowIndex) => {{
                    const cells = Array.from(row.querySelectorAll(__TABLE_CELL_SELECTOR__)).filter(visible);
                    const operationCell = cells.at(-1) || row;
                    const parsed = parseNameAndId(cells[0]?.innerText || cells[0]?.textContent || "");
                    return {{
                        id: rowKey(cells, rowIndex),
                        name: parsed.name,
                        remark: clean(cells[1]?.innerText || cells[1]?.textContent || ""),
                        text: clean(row.innerText || row.textContent),
                        editable: Boolean(operationCell.querySelector(__EDIT_ICON_SELECTOR__)),
                    }};
                }})
                .filter((row) => row.id && row.name && row.editable);
        }}
        """.replace("__TABLE_CELL_SELECTOR__", repr(self.locator("table_cell"))).replace(
            "__EDIT_ICON_SELECTOR__",
            repr(self.locator("edit_icon")),
        )

    def _group_name_by_id_script(self, group_id: str) -> str:
        return f"""
        () => {{
            const expectedId = {group_id!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const parseNameAndId = (value) => {{
                const normalized = clean(value);
                const match = normalized.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                return {{
                    name: match ? clean(match[1]) : normalized,
                    id: match ? match[2] : "",
                }};
            }};
            const rowKey = (cells, rowIndex) => {{
                const parsed = parseNameAndId(cells[0]?.innerText || cells[0]?.textContent || "");
                if (parsed.id) return parsed.id;
                const createdAt = clean(cells[4]?.innerText || cells[4]?.textContent || "");
                return createdAt ? "created:" + createdAt : "row:" + rowIndex;
            }};
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            for (const [rowIndex, row] of rows.entries()) {{
                const cells = Array.from(row.querySelectorAll(__TABLE_CELL_SELECTOR__)).filter(visible);
                const firstCellText = clean(cells[0]?.innerText || cells[0]?.textContent || "");
                const parsed = parseNameAndId(firstCellText);
                if (rowKey(cells, rowIndex) === expectedId) return parsed.name;
            }}
            return "";
        }}
        """.replace("__TABLE_CELL_SELECTOR__", repr(self.locator("table_cell")))

    def _group_remark_by_id_script(self, group_id: str) -> str:
        return f"""
        () => {{
            const expectedId = {group_id!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const parseNameAndId = (value) => {{
                const normalized = clean(value);
                const match = normalized.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                return {{
                    name: match ? clean(match[1]) : normalized,
                    id: match ? match[2] : "",
                }};
            }};
            const rowKey = (cells, rowIndex) => {{
                const parsed = parseNameAndId(cells[0]?.innerText || cells[0]?.textContent || "");
                if (parsed.id) return parsed.id;
                const createdAt = clean(cells[4]?.innerText || cells[4]?.textContent || "");
                return createdAt ? "created:" + createdAt : "row:" + rowIndex;
            }};
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            for (const [rowIndex, row] of rows.entries()) {{
                const cells = Array.from(row.querySelectorAll(__TABLE_CELL_SELECTOR__)).filter(visible);
                if (rowKey(cells, rowIndex) === expectedId) return clean(cells[1]?.innerText || cells[1]?.textContent || "");
            }}
            return "";
        }}
        """.replace("__TABLE_CELL_SELECTOR__", repr(self.locator("table_cell")))

    def _group_row_edit_button_by_id_script(self, group_id: str) -> str:
        return f"""
        () => {{
            const expectedId = {group_id!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const parseNameAndId = (value) => {{
                const normalized = clean(value);
                const match = normalized.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                return {{
                    name: match ? clean(match[1]) : normalized,
                    id: match ? match[2] : "",
                }};
            }};
            const rowKey = (cells, rowIndex) => {{
                const parsed = parseNameAndId(cells[0]?.innerText || cells[0]?.textContent || "");
                if (parsed.id) return parsed.id;
                const createdAt = clean(cells[4]?.innerText || cells[4]?.textContent || "");
                return createdAt ? "created:" + createdAt : "row:" + rowIndex;
            }};
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            for (const [rowIndex, row] of rows.entries()) {{
                const cells = Array.from(row.querySelectorAll(__TABLE_CELL_SELECTOR__)).filter(visible);
                if (rowKey(cells, rowIndex) !== expectedId) continue;
                const operationCell = cells.at(-1) || row;
                const editIcon = Array.from(operationCell.querySelectorAll(__EDIT_ICON_SELECTOR__)).find(visible);
                if (editIcon) return editIcon.closest("button, [role='button']") || editIcon;
            }}
            return null;
        }}
        """.replace("__TABLE_CELL_SELECTOR__", repr(self.locator("table_cell"))).replace(
            "__EDIT_ICON_SELECTOR__",
            repr(self.locator("edit_icon")),
        )

    def _edit_group_dialog_visible_script(self) -> str:
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
            return Array.from(document.querySelectorAll(__DIALOG_SELECTOR__))
                .some((dialog) => visible(dialog)
                    && (dialog.innerText || dialog.textContent || "").includes("编辑环境分组")
                    && (dialog.innerText || dialog.textContent || "").includes("分组名称"));
        }
        """.replace("__DIALOG_SELECTOR__", repr(self.locator("dialog")))

    def _group_authorized_members_view_script(self, group_name: str) -> str:
        return f"""
        () => {{
            const expectedGroup = {group_name!r};
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
                if (!(row.innerText || row.textContent || "").includes(expectedGroup)) continue;
                const viewButtons = Array.from(row.querySelectorAll(__ROW_ACTION_SELECTOR__))
                    .filter(visible)
                    .map((el) => {{
                        const rect = el.getBoundingClientRect();
                        return {{ el, text: (el.innerText || el.textContent || "").trim(), rect }};
                    }})
                    .filter((item) => item.text === "查看")
                    .sort((left, right) => left.rect.x - right.rect.x);
                return viewButtons.at(-1)?.el || null;
            }}
            return null;
        }}
        """.replace("__ROW_ACTION_SELECTOR__", repr(self.locator("row_action_candidates")))

    def _wait_authorized_member_popover_text(self, timeout_seconds: int | None = None) -> str:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            text = str(self.cdp.evaluate(self._authorized_member_popover_text_script()) or "").strip()
            if text:
                return text
            time.sleep(0.2)
        raise TimeoutError("authorized member popover did not appear")

    def _authorized_member_popover_text_script(self) -> str:
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
            const popover = Array.from(document.querySelectorAll(__AUTHORIZED_MEMBER_POPOVER_SELECTOR__))
                .filter(visible)
                .find((el) => (el.getAttribute("aria-label") || "").includes("授权成员")
                    || (el.innerText || el.textContent || "").includes("授权成员"));
            return popover ? (popover.innerText || popover.textContent || "").trim() : "";
        }
        """.replace(
            "__AUTHORIZED_MEMBER_POPOVER_SELECTOR__",
            repr(self.locator("authorized_member_popover")),
        )

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
            return rows.some((row) => Array.from(row.querySelectorAll(__ROW_NAME_CELL_SELECTOR__))
                .some((cell) => (cell.innerText || cell.textContent || "").trim() === expectedName));
        }}
        """.replace("__ROW_NAME_CELL_SELECTOR__", repr(self.locator("row_name_cell_candidates")))

    def _group_row_action_button_script(self, group_name: str, action_text: str) -> str:
        return f"""
        () => {{
            const expectedName = {group_name!r};
            const expectedAction = {action_text!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
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
                const hasName = Array.from(row.querySelectorAll(__ROW_NAME_CELL_SELECTOR__))
                    .some((cell) => {{
                        const text = clean(cell.innerText || cell.textContent);
                        const name = clean(expectedName);
                        return text === name || text.startsWith(name) || text.includes(name);
                    }});
                if (!hasName) continue;
                const actions = Array.from(row.querySelectorAll(__ROW_ACTION_SELECTOR__))
                    .filter((el) => visible(el) && clean(el.innerText || el.textContent) === clean(expectedAction))
                    .map((el) => {{
                        const rect = el.getBoundingClientRect();
                        return {{ el, area: rect.width * rect.height }};
                    }})
                    .sort((left, right) => left.area - right.area);
                if (actions[0]) return actions[0].el;

                if (expectedAction === "删除") {{
                    const cells = Array.from(row.children).filter(visible);
                    const operationCell = cells[cells.length - 1] || row;
                    const deleteIcon = operationCell.querySelector(".icon-delete");
                    const deleteButton = deleteIcon?.closest("button, [role='button']");
                    if (deleteButton && visible(deleteButton)) return deleteButton;

                    const iconActions = Array.from(operationCell.querySelectorAll(__ROW_ICON_ACTION_SELECTOR__))
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
        """.replace("__ROW_NAME_CELL_SELECTOR__", repr(self.locator("row_name_cell_candidates"))).replace(
            "__ROW_ACTION_SELECTOR__",
            repr(self.locator("row_action_candidates")),
        ).replace("__ROW_ICON_ACTION_SELECTOR__", repr(self.locator("row_icon_action_candidates")))

    def _group_list_visible_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const bodyText = document.body ? (document.body.innerText || document.body.textContent || "") : "";
            const hasCreate = Array.from(document.querySelectorAll(__VISIBLE_TEXT_SELECTOR__))
                .some((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "创建环境分组");
            const hasTable = Array.from(document.querySelectorAll(__TABLE_CONTAINER_SELECTOR__)).some(visible);
            return bodyText.includes("环境分组") && (hasCreate || hasTable);
        }
        """.replace("__VISIBLE_TEXT_SELECTOR__", repr(self.locator("visible_text_candidates"))).replace(
            "__TABLE_CONTAINER_SELECTOR__",
            repr(self.locator("table_container")),
        )
