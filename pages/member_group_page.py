from __future__ import annotations

import time

from core.config import timeout_seconds as config_timeout_seconds
from pages.base_page import BasePage


class MemberGroupPage(BasePage):
    locator_file = "member_group_locators.yaml"

    def recover_to_module_home(self) -> None:
        self.open_list()
        self.dismiss_blocking_overlays()

    def open_list(self) -> None:
        self.dismiss_blocking_overlays()
        self._expand_team_management_if_needed()
        self.cdp.click_element_by_script(self._visible_menu_item_script("成员分组"))
        self._wait_for_member_group_list()
        self._wait_for_member_group_table_not_loading()

    def create_member_group(self, name: str, remark: str) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_text_button_script("创建成员分组"))
        self._wait_for_create_member_group_dialog()
        self._wait_for_create_member_group_dialog_ready()
        self._fill_create_dialog_fields_stably(name=name, remark=remark)
        self._click_overlay_button_wait_loading_then_closed("确定")
        self._wait_for_member_group_table_not_loading()
        self.wait_member_group_visible(name)

    def delete_member_group(self, name: str) -> None:
        self.cdp.click_element_by_script(self._member_group_row_delete_button_script(name))
        self._wait_delete_member_group_dialog_visible()
        self._click_overlay_button_wait_loading_then_closed("确定并删除")
        self._wait_for_member_group_table_not_loading()
        self.wait_member_group_absent(name)

    def delete_member_group_if_exists(self, name: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "search_result_seconds", 10)
        while time.time() < deadline:
            if not self.member_group_visible(name):
                return
            self.delete_member_group(name)
            time.sleep(0.3)
        if self.member_group_visible(name):
            raise TimeoutError(f"member group still exists after cleanup: {name}")

    def member_group_visible(self, name: str) -> bool:
        return bool(self.cdp.evaluate(self._member_group_exists_script(name)))

    def wait_member_group_visible(self, name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.member_group_visible(name):
                return
            time.sleep(0.3)
        raise TimeoutError(f"member group did not appear in list: {name}")

    def wait_member_group_absent(self, name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.member_group_visible(name):
                return
            time.sleep(0.3)
        raise TimeoutError(f"member group still exists in list: {name}")

    def member_group_row_details(self, name: str) -> dict[str, str]:
        value = self.cdp.evaluate(self._member_group_row_details_script(name))
        if not isinstance(value, dict):
            return {}
        return {str(key): str(item or "").strip() for key, item in value.items()}

    def first_member_group(self) -> dict[str, object]:
        rows = self._member_group_rows()
        if not rows:
            raise RuntimeError("member group list has no visible rows")
        first_row = rows[0]
        if not first_row["editable"]:
            raise RuntimeError(f"first member group is not editable: {first_row}")
        if not first_row["name"] or not first_row["created_at"]:
            raise RuntimeError(f"first member group identity is incomplete: {first_row}")
        return first_row

    def member_group_by_identity(self, remark: str, created_at: str) -> dict[str, object]:
        clean_remark = str(remark).strip()
        clean_created_at = str(created_at).strip()
        matches = [
            row
            for row in self._member_group_rows()
            if row["remark"] == clean_remark and row["created_at"] == clean_created_at
        ]
        if len(matches) != 1:
            raise RuntimeError(
                "member group identity must match exactly one row: "
                f"remark={clean_remark!r}, created_at={clean_created_at!r}, matches={len(matches)}"
            )
        return matches[0]

    def edit_member_group_name_by_identity(
        self,
        *,
        remark: str,
        created_at: str,
        new_name: str,
        expected_current_name: str = "",
    ) -> None:
        clean_name = str(new_name).strip()
        if not clean_name:
            raise ValueError("member group name is empty")
        current = self.member_group_by_identity(remark, created_at)
        current_name = str(current["name"])
        if expected_current_name and current_name != str(expected_current_name).strip():
            raise AssertionError(
                "member group current name does not match before edit: "
                f"expected={expected_current_name!r}, actual={current_name!r}"
            )

        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(
            self._member_group_row_edit_button_by_identity_script(remark, created_at)
        )
        self._wait_for_edit_member_group_dialog(current_name)
        self.cdp.fill_element_by_script(
            self._dialog_input_by_label_script("成员分组名称"),
            clean_name,
        )
        self._wait_for_dialog_field_value("成员分组名称", clean_name)
        self._click_overlay_button_wait_loading_then_closed("确定")
        self._wait_for_member_group_table_not_loading()
        self.wait_member_group_name_by_identity(remark, created_at, clean_name)

    def restore_member_group_name_if_needed(
        self,
        *,
        remark: str,
        created_at: str,
        original_name: str,
    ) -> None:
        current = self.member_group_by_identity(remark, created_at)
        if current["name"] == str(original_name).strip():
            return
        self.edit_member_group_name_by_identity(
            remark=remark,
            created_at=created_at,
            new_name=original_name,
            expected_current_name=str(current["name"]),
        )

    def wait_member_group_name_by_identity(
        self,
        remark: str,
        created_at: str,
        expected_name: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_matches: list[dict[str, object]] = []
        while time.time() < deadline:
            last_matches = [
                row
                for row in self._member_group_rows()
                if row["remark"] == str(remark).strip()
                and row["created_at"] == str(created_at).strip()
            ]
            if len(last_matches) > 1:
                raise RuntimeError(
                    "member group identity became ambiguous while waiting for name: "
                    f"remark={remark!r}, created_at={created_at!r}, matches={len(last_matches)}"
                )
            if len(last_matches) == 1 and last_matches[0]["name"] == str(expected_name).strip():
                return
            time.sleep(0.3)
        raise TimeoutError(
            "member group name did not reach expected value by identity: "
            f"remark={remark!r}, created_at={created_at!r}, expected={expected_name!r}, "
            f"matches={last_matches}"
        )

    def _member_group_rows(self) -> list[dict[str, object]]:
        value = self.cdp.evaluate(self._member_group_rows_script())
        if not isinstance(value, list):
            return []
        rows: list[dict[str, object]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "name": str(item.get("name", "") or "").strip(),
                    "remark": str(item.get("remark", "") or "").strip(),
                    "created_at": str(item.get("created_at", "") or "").strip(),
                    "editable": bool(item.get("editable")),
                }
            )
        return rows

    def dismiss_blocking_overlays(self) -> None:
        for _ in range(4):
            has_overlay = bool(
                self.cdp.evaluate(
                    """
                    () => Boolean(document.querySelector(__OVERLAY_SELECTOR__))
                    """.replace("__OVERLAY_SELECTOR__", repr(self.locator("blocking_overlay")))
                )
            )
            if not has_overlay:
                return
            clicked = bool(
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
                        const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                        const overlays = Array.from(document.querySelectorAll(__OVERLAY_SELECTOR__))
                            .filter(visible);
                        for (const overlay of overlays.reverse()) {
                            const cancel = Array.from(overlay.querySelectorAll("button"))
                                .filter(visible)
                                .find((button) => clean(button.innerText || button.textContent) === "取消");
                            if (cancel) {
                                cancel.click();
                                return true;
                            }
                            const closeButton = overlay.querySelector(__CLOSE_BUTTON_SELECTOR__);
                            if (closeButton && visible(closeButton)) {
                                closeButton.click();
                                return true;
                            }
                        }
                        return false;
                    }
                    """.replace("__OVERLAY_SELECTOR__", repr(self.locator("blocking_overlay"))).replace(
                        "__CLOSE_BUTTON_SELECTOR__",
                        repr(self.locator("overlay_close_button")),
                    )
                )
            )
            if not clicked:
                self.cdp.press("Escape")
            time.sleep(0.5)

    def _wait_for_member_group_list(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._member_group_list_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("member group list did not appear")

    def _wait_for_member_group_table_not_loading(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.cdp.evaluate(self._member_group_table_loading_visible_script()):
                return
            time.sleep(0.3)
        raise TimeoutError("member group table is still loading")

    def _wait_for_create_member_group_dialog(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._create_member_group_dialog_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("create member group dialog did not appear")

    def _wait_for_create_member_group_dialog_ready(
        self,
        timeout_seconds: int | None = None,
        stable_seconds: float = 0.6,
        poll_seconds: float = 0.1,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.monotonic() + timeout_seconds
        stable_since: float | None = None
        stable_signature: tuple[int, bool] | None = None
        last_state: dict[str, object] = {}
        while time.monotonic() < deadline:
            value = self.cdp.evaluate(self._create_member_group_dialog_state_script())
            last_state = value if isinstance(value, dict) else {}
            ready = bool(last_state.get("ready"))
            signature = (
                int(last_state.get("permission_count") or 0),
                bool(last_state.get("loading")),
            )
            now = time.monotonic()
            if ready:
                if signature != stable_signature:
                    stable_signature = signature
                    stable_since = now
                elif stable_since is not None and now - stable_since >= stable_seconds:
                    return
            else:
                stable_signature = None
                stable_since = None
            time.sleep(poll_seconds)
        raise TimeoutError(f"create member group dialog did not become ready: {last_state}")

    def _wait_for_edit_member_group_dialog(
        self,
        expected_name: str,
        timeout_seconds: int | None = None,
        stable_seconds: float = 0.4,
        poll_seconds: float = 0.1,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.monotonic() + timeout_seconds
        stable_since: float | None = None
        last_state: dict[str, object] = {}
        while time.monotonic() < deadline:
            value = self.cdp.evaluate(self._edit_member_group_dialog_state_script())
            last_state = value if isinstance(value, dict) else {}
            ready = (
                last_state.get("title") == "编辑成员分组"
                and last_state.get("name") == str(expected_name).strip()
                and not bool(last_state.get("loading"))
            )
            now = time.monotonic()
            if ready:
                if stable_since is None:
                    stable_since = now
                elif now - stable_since >= stable_seconds:
                    return
            else:
                stable_since = None
            time.sleep(poll_seconds)
        raise TimeoutError(
            "edit member group dialog did not become stable with original name: "
            f"expected_name={expected_name!r}, state={last_state}"
        )

    def _fill_create_dialog_fields_stably(
        self,
        *,
        name: str,
        remark: str,
        timeout_seconds: int | None = None,
        stable_seconds: float = 0.6,
        poll_seconds: float = 0.1,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        expected_values = {
            "成员分组名称": name,
            "备注": remark,
        }
        deadline = time.monotonic() + timeout_seconds
        stable_since: float | None = None
        last_values: dict[str, str] = {}
        while time.monotonic() < deadline:
            refilled = False
            for field_label, expected_value in expected_values.items():
                actual_value = self._dialog_field_value(field_label)
                last_values[field_label] = actual_value
                if actual_value == expected_value:
                    continue
                self._fill_dialog_field(field_label, expected_value)
                refilled = True

            if refilled:
                stable_since = None
            else:
                now = time.monotonic()
                if stable_since is None:
                    stable_since = now
                elif now - stable_since >= stable_seconds:
                    return
            time.sleep(poll_seconds)
        raise TimeoutError(
            "member group dialog fields did not remain stable: "
            f"expected={expected_values}, actual={last_values}"
        )

    def _dialog_field_value(self, field_label: str) -> str:
        return str(self.cdp.evaluate(self._dialog_field_value_script(field_label)) or "").strip()

    def _fill_dialog_field(self, field_label: str, value: str) -> None:
        script = (
            self._dialog_input_by_label_script(field_label)
            if field_label == "成员分组名称"
            else self._dialog_textarea_by_label_script(field_label)
        )
        self.cdp.fill_element_by_script(script, value)

    def _wait_for_dialog_field_value(
        self,
        field_label: str,
        expected_value: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "element_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._dialog_field_value(field_label) == expected_value:
                return
            time.sleep(0.1)
        raise TimeoutError(
            f"member group dialog field did not reach expected value: "
            f"field={field_label}, expected={expected_value!r}"
        )

    def _wait_delete_member_group_dialog_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._delete_member_group_dialog_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("delete member group dialog did not appear")

    def _wait_for_overlay_closed(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            visible_count = int(
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
                        return Array.from(document.querySelectorAll(__OVERLAY_SELECTOR__))
                            .filter(visible).length;
                    }
                    """.replace("__OVERLAY_SELECTOR__", repr(self.locator("blocking_overlay")))
                )
                or 0
            )
            if visible_count == 0:
                return
            time.sleep(0.2)
        raise TimeoutError("overlay did not close")

    def _click_overlay_button_wait_loading_then_closed(self, text: str) -> None:
        self.cdp.click_element_by_script(self._active_overlay_button_script(text))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        saw_loading = False
        while time.time() < deadline:
            if not self.cdp.evaluate(self._active_overlay_visible_script()):
                return
            state = self._active_overlay_button_state(text)
            if bool(state.get("loading")):
                saw_loading = True
                break
            time.sleep(0.1)
        if saw_loading:
            self._wait_for_overlay_closed()
            return
        self._wait_for_overlay_closed()

    def _active_overlay_button_state(self, text: str) -> dict[str, object]:
        value = self.cdp.evaluate(self._active_overlay_button_state_script(text))
        return value if isinstance(value, dict) else {}

    def _expand_team_management_if_needed(self) -> None:
        if self.cdp.evaluate(self._visible_menu_item_exists_script("成员分组")):
            return
        self.cdp.click_element_by_script(self._visible_menu_item_script("团队管理"))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._visible_menu_item_exists_script("成员分组")):
                return
            time.sleep(0.2)
        raise TimeoutError("team management menu did not expand to show member group")

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
            const selector = {self.locator("menu_candidates")!r};
            const items = Array.from(document.querySelectorAll(selector))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
            return items[0] || null;
        }}
        """

    def _visible_menu_item_exists_script(self, text: str) -> str:
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
            const selector = {self.locator("menu_candidates")!r};
            return Array.from(document.querySelectorAll(selector))
                .some((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
        }}
        """

    def _visible_text_button_script(self, text: str) -> str:
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
            return Array.from(document.querySelectorAll({self.locator("button")!r}))
                .filter(visible)
                .find((button) => (button.innerText || button.textContent || "").trim() === expectedText) || null;
        }}
        """

    def _active_overlay_button_script(self, text: str) -> str:
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
            const overlays = Array.from(document.querySelectorAll({self.locator("blocking_overlay")!r}))
                .filter(visible);
            for (const overlay of overlays.reverse()) {{
                const button = Array.from(overlay.querySelectorAll({self.locator("button")!r}))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (button) return button;
            }}
            return null;
        }}
        """

    def _active_overlay_button_state_script(self, text: str) -> str:
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
            const overlays = Array.from(document.querySelectorAll({self.locator("blocking_overlay")!r}))
                .filter(visible);
            for (const overlay of overlays.reverse()) {{
                const button = Array.from(overlay.querySelectorAll({self.locator("button")!r}))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (!button) continue;
                const loading = button.classList.contains("is-loading")
                    || Boolean(button.querySelector(".is-loading, .el-icon-loading, [class*='loading']"));
                const disabled = Boolean(button.disabled)
                    || button.getAttribute("aria-disabled") === "true"
                    || button.classList.contains("is-disabled");
                return {{ visible: true, loading, disabled }};
            }}
            return {{ visible: false, loading: false, disabled: false }};
        }}
        """

    def _active_overlay_visible_script(self) -> str:
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
            return Array.from(document.querySelectorAll({self.locator("blocking_overlay")!r})).some(visible);
        }}
        """

    def _dialog_input_by_label_script(self, field_label: str) -> str:
        return self._dialog_field_by_label_script(field_label, "input")

    def _dialog_textarea_by_label_script(self, field_label: str) -> str:
        return self._dialog_field_by_label_script(field_label, "textarea")

    def _dialog_field_value_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const field = ({self._dialog_field_by_label_script(field_label, "input,textarea")})();
            return field ? String(field.value || "") : "";
        }}
        """

    def _dialog_field_by_label_script(self, field_label: str, field_selector: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const dialogs = Array.from(document.querySelectorAll({self.locator("dialog")!r})).filter(visible);
            for (const dialog of dialogs.reverse()) {{
                const placeholderField = Array.from(dialog.querySelectorAll({field_selector!r}))
                    .filter(visible)
                    .find((item) => clean(item.getAttribute("placeholder") || "").includes(clean(expectedLabel)));
                if (placeholderField) return placeholderField;
                const formItem = Array.from(dialog.querySelectorAll({self.locator("form_item")!r}))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent).includes(clean(expectedLabel)));
                const field = Array.from(formItem?.querySelectorAll({field_selector!r}) || []).find(visible);
                if (field) return field;
            }}
            return null;
        }}
        """

    def _member_group_list_visible_script(self) -> str:
        return f"""
        () => {{
            const route = String(window.location.hash || "").split("?")[0].replace(/\\/+$/, "");
            const text = document.body.innerText || document.body.textContent || "";
            return route === "#/system/role"
                && text.includes("成员分组")
                && text.includes("创建成员分组")
                && Boolean(document.querySelector({self.locator("table_container")!r}));
        }}
        """

    def _member_group_table_loading_visible_script(self) -> str:
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
            return Array.from(document.querySelectorAll(".el-loading-mask")).some(visible);
        }
        """

    def _create_member_group_dialog_visible_script(self) -> str:
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
            const text = (el) => el.innerText || el.textContent || "";
            return Array.from(document.querySelectorAll(".el-dialog"))
                .filter(visible)
                .some((dialog) => text(dialog).includes("创建成员分组") && text(dialog).includes("成员分组名称"));
        }
        """

    def _create_member_group_dialog_state_script(self) -> str:
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
            const text = (el) => el.innerText || el.textContent || "";
            const dialog = Array.from(document.querySelectorAll(".el-dialog"))
                .filter(visible)
                .reverse()
                .find((item) => text(item).includes("创建成员分组") && text(item).includes("功能权限"));
            if (!dialog) {
                return { ready: false, loading: false, permission_count: 0 };
            }
            const loading = Array.from(
                dialog.querySelectorAll(".el-loading-mask, .el-skeleton, [aria-busy='true']")
            ).some(visible);
            const permissionCount = dialog.querySelectorAll(".el-checkbox, input[type='checkbox']").length;
            return {
                ready: !loading && permissionCount > 0,
                loading,
                permission_count: permissionCount,
            };
        }
        """

    def _delete_member_group_dialog_visible_script(self) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return Array.from(document.querySelectorAll(".el-dialog, .el-message-box"))
                .filter(visible)
                .some((overlay) => {
                    const text = clean(overlay.innerText || overlay.textContent);
                    return text.includes("删除")
                        && text.includes("确定并删除");
                });
        }
        """

    def _edit_member_group_dialog_state_script(self) -> str:
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
            const dialogs = Array.from(document.querySelectorAll({self.locator("dialog")!r})).filter(visible);
            const dialog = dialogs.reverse().find((item) =>
                clean(item.querySelector({self.locator("dialog_title")!r})?.textContent) === "编辑成员分组"
            );
            if (!dialog) return {{ title: "", name: "", remark: "", loading: false }};
            const loading = Array.from(
                dialog.querySelectorAll(".el-loading-mask, .el-skeleton, [aria-busy='true']")
            ).some(visible);
            const name = dialog.querySelector("input[placeholder='成员分组名称']");
            const remark = dialog.querySelector("textarea[placeholder='备注']");
            return {{
                title: clean(dialog.querySelector({self.locator("dialog_title")!r})?.textContent),
                name: String(name?.value || "").trim(),
                remark: String(remark?.value || "").trim(),
                loading,
            }};
        }}
        """

    def _member_group_rows_script(self) -> str:
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
            const compact = (value) => clean(value).replace(/\\s+/g, "");
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => compact(header.innerText || header.textContent));
            const nameIndex = headers.findIndex((header) => header.includes("成员分组名称"));
            const remarkIndex = headers.findIndex((header) => header === "备注");
            const createdAtIndex = headers.findIndex((header) => header.includes("创建时间"));
            const operationIndex = headers.findIndex((header) => header === "操作");
            if (nameIndex < 0 || remarkIndex < 0 || createdAtIndex < 0) return [];
            return Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .map((row) => {{
                    const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                    const operationCell = cells[operationIndex] || cells.at(-1) || row;
                    return {{
                        name: clean(cells[nameIndex]?.innerText || cells[nameIndex]?.textContent),
                        remark: clean(cells[remarkIndex]?.innerText || cells[remarkIndex]?.textContent),
                        created_at: clean(cells[createdAtIndex]?.innerText || cells[createdAtIndex]?.textContent),
                        editable: Boolean(operationCell.querySelector({self.locator("edit_icon")!r})),
                    }};
                }});
        }}
        """

    def _member_group_row_edit_button_by_identity_script(self, remark: str, created_at: str) -> str:
        return f"""
        () => {{
            const expectedRemark = {str(remark).strip()!r};
            const expectedCreatedAt = {str(created_at).strip()!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const compact = (value) => clean(value).replace(/\\s+/g, "");
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => compact(header.innerText || header.textContent));
            const remarkIndex = headers.findIndex((header) => header === "备注");
            const createdAtIndex = headers.findIndex((header) => header.includes("创建时间"));
            const operationIndex = headers.findIndex((header) => header === "操作");
            if (remarkIndex < 0 || createdAtIndex < 0) return null;
            const matches = Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .filter((row) => {{
                    const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                    return clean(cells[remarkIndex]?.innerText || cells[remarkIndex]?.textContent) === expectedRemark
                        && clean(cells[createdAtIndex]?.innerText || cells[createdAtIndex]?.textContent) === expectedCreatedAt;
                }});
            if (matches.length !== 1) return null;
            const cells = Array.from(matches[0].querySelectorAll({self.locator("table_cell")!r})).filter(visible);
            const operationCell = cells[operationIndex] || cells.at(-1) || matches[0];
            const editIcon = Array.from(operationCell.querySelectorAll({self.locator("edit_icon")!r}))
                .filter(visible)
                .sort((left, right) => left.getBoundingClientRect().x - right.getBoundingClientRect().x)[0];
            return editIcon ? editIcon.closest("button, [role='button']") || editIcon : null;
        }}
        """

    def _member_group_exists_script(self, name: str) -> str:
        return f"""
        () => Boolean(({self._member_group_row_script(name)})())
        """

    def _member_group_row_details_script(self, name: str) -> str:
        return f"""
        () => {{
            const row = ({self._member_group_row_script(name)})();
            if (!row) return {{}};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const compact = (value) => clean(value).replace(/\\s+/g, "");
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => compact(header.innerText || header.textContent));
            const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
            const result = {{}};
            headers.forEach((header, index) => {{
                if (!header || header === "操作") return;
                result[header] = clean(cells[index]?.innerText || cells[index]?.textContent || "");
            }});
            return result;
        }}
        """

    def _member_group_row_delete_button_script(self, name: str) -> str:
        return f"""
        () => {{
            const row = ({self._member_group_row_script(name)})();
            if (!row) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
            const operationCell = cells[cells.length - 1] || row;
            const deleteIcon = operationCell.querySelector({self.locator("delete_icon")!r});
            if (deleteIcon) return deleteIcon.closest("button, [role='button'], span, div") || deleteIcon;
            const candidates = Array.from(operationCell.querySelectorAll("button, [role='button'], svg, i, span, div"))
                .filter(visible);
            return candidates[candidates.length - 1] || null;
        }}
        """

    def _member_group_row_script(self, name: str) -> str:
        return f"""
        () => {{
            const expectedName = {name!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => clean(header.innerText || header.textContent).replace(/\\s+/g, ""));
            let nameIndex = headers.findIndex((header) => header.includes("成员分组名称"));
            if (nameIndex < 0) nameIndex = 0;
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            return rows.find((row) => {{
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const nameText = clean(cells[nameIndex]?.innerText || cells[nameIndex]?.textContent || "");
                return nameText === expectedName;
            }}) || null;
        }}
        """
