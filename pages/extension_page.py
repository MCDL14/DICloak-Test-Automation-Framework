from __future__ import annotations

import re
import shutil
import tempfile
import time
from pathlib import Path

from core.config import timeout_seconds as config_timeout_seconds
from pages.base_page import BasePage


class ExtensionPage(BasePage):
    locator_file = "extension_locators.yaml"

    def __init__(self, cdp_driver, ui_driver=None, config: dict | None = None):
        super().__init__(cdp_driver=cdp_driver, ui_driver=ui_driver, config=config)
        self._temporary_upload_dirs: list[Path] = []

    def recover_to_module_home(self) -> None:
        self.open_list()
        self.dismiss_blocking_overlays()

    def open_list(self) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_menu_item_script("扩展管理"))
        self._wait_for_extension_list()
        self._wait_for_extension_list_not_loading()

    def open_added_extensions_tab(self) -> None:
        self.cdp.click_element_by_script(self._extension_tab_script("添加扩展"))
        self._wait_for_extension_list_not_loading()

    def open_market_tab(self) -> None:
        self.cdp.click_element_by_script(self._extension_tab_script("扩展市场"))
        self._wait_for_extension_list_not_loading()

    def add_local_extension(self, package_file: str | Path, extension_name: str, group_name: str = "未分组") -> None:
        package_path = Path(package_file).expanduser().resolve()
        if not package_path.is_file():
            raise FileNotFoundError(f"local extension package does not exist: {package_path}")

        self.dismiss_blocking_overlays()
        self.open_added_extensions_tab()
        self.cdp.click_element_by_script(self._primary_text_button_script("添加扩展"))
        self._wait_for_add_extension_dialog()
        self.cdp.click_element_by_script(self._dialog_radio_button_script("安装包"))
        self._wait_for_local_package_mode()
        try:
            self.cdp.fill_element_by_script(self._dialog_input_by_label_script("扩展名称"), extension_name)
            self._wait_dialog_field_value("扩展名称", extension_name)
            self._choose_package_file(package_path)
            self._wait_dialog_field_value("扩展名称", extension_name)
            self.ensure_extension_group(group_name)
            self._click_overlay_button_wait_loading_then_closed("确定")
            self._wait_for_extension_list_not_loading()
            self.wait_extension_visible(extension_name)
        finally:
            self._cleanup_temporary_upload_files()

    def search_market_extension(self, name: str) -> None:
        self.cdp.fill_element_by_script(self._market_search_input_script("扩展名称"), name)
        self.cdp.click_element_by_script(self._text_button_script("搜索"))
        self._wait_for_extension_list_not_loading()

    def search_added_extension(self, name: str) -> None:
        self.cdp.fill_element_by_script(self._extension_name_search_input_script(), name)
        self._wait_for_extension_name_search_value(name)
        self.cdp.click_element_by_script(self._list_search_button_script())
        self._wait_for_extension_list_stable()

    def filter_added_extensions_by_group(self, group_name: str) -> None:
        group_name = str(group_name).strip()
        if not group_name:
            raise ValueError("extension group filter cannot be empty")
        if self._list_filter_value(0) == group_name:
            self._wait_for_extension_list_stable()
            return
        self.cdp.click_element_by_script(self._list_filter_select_script(0))
        self.cdp.click_element_by_script(self._dropdown_item_script(group_name))
        self._wait_for_list_filter_value(0, group_name)
        self._wait_for_extension_list_stable()

    def clear_added_extension_filters(self) -> None:
        for index, placeholder in ((0, "分组"), (1, "启用状态")):
            if self._list_filter_value(index) == placeholder:
                continue
            self.cdp.hover_element_by_script(self._list_filter_select_script(index))
            self.cdp.click_element_by_script(self._list_filter_clear_script(index))
            self._wait_for_list_filter_value(index, placeholder)
            self._wait_for_extension_list_stable()
        if self._extension_name_search_value():
            self.cdp.fill_element_by_script(self._extension_name_search_input_script(), "")
            self._wait_for_extension_name_search_value("")
        self.cdp.click_element_by_script(self._list_search_button_script())
        self._wait_for_extension_list_stable()

    def add_market_extension(
        self,
        name: str,
        description: str,
        group_name: str = "未分组",
    ) -> None:
        self.wait_market_extension_visible(name, description)
        self.cdp.click_element_by_script(self._market_extension_add_button_script(name, description))
        self._wait_for_market_add_dialog_ready(name, group_name)
        self._click_overlay_button_wait_loading_then_closed("确定")
        self._wait_for_extension_list_not_loading()

    def add_google_store_extension(
        self,
        extension_url: str,
        extension_name: str,
        group_name: str = "未分组",
        enable_extension: bool = True,
    ) -> None:
        self.dismiss_blocking_overlays()
        self.open_added_extensions_tab()
        self.cdp.click_element_by_script(self._primary_text_button_script("添加扩展"))
        self._wait_for_add_extension_dialog()
        self.cdp.click_element_by_script(self._dialog_radio_button_script("Chrome 应用商店"))
        self.cdp.fill_element_by_script(self._dialog_field_by_label_script("扩展URL", "textarea,input"), extension_url)
        self._wait_dialog_field_value("扩展URL", extension_url)
        self.ensure_extension_group(group_name, wait_for_async_default_seconds=20)
        if enable_extension:
            self.ensure_dialog_checkbox_checked("同时启用该扩展")
        self._click_overlay_button_wait_loading_then_closed(
            "确定",
            timeout_seconds=config_timeout_seconds(self.config, "extension_install_seconds", 180),
        )
        self._wait_for_extension_list_not_loading(timeout_seconds=60)
        self.wait_extension_visible(extension_name, timeout_seconds=60)

    def edit_extension_hide_settings(
        self,
        name: str,
        *,
        hidden: bool,
        member_group: str = "全部分组",
    ) -> None:
        self.open_extension_edit_dialog(name)
        self.ensure_dialog_switch_state("隐藏设置", hidden)
        if hidden:
            self.ensure_dialog_member_group(member_group)
        try:
            self._click_overlay_button_wait_loading_then_closed("确定", timeout_seconds=60)
        except TimeoutError as exc:
            raise TimeoutError(
                f"edit extension hide settings did not complete: "
                f"name={name}, hidden={hidden}, member_group={member_group}"
            ) from exc
        self._wait_for_extension_list_not_loading(timeout_seconds=30)

    def open_extension_edit_dialog(self, name: str) -> None:
        self.cdp.hover_element_by_script(self._extension_card_script(name))
        self.cdp.hover_element_by_script(self._extension_card_more_button_script(name))
        self.cdp.click_element_by_script(self._dropdown_item_script("编辑"))
        self._wait_for_edit_extension_dialog_visible()
        self._wait_for_dialog_extension_groups_ready()

    def dialog_extension_groups(self) -> list[str]:
        groups = self.cdp.evaluate(self._dialog_extension_groups_script())
        if not isinstance(groups, list):
            return []
        return [str(group).strip() for group in groups if str(group).strip()]

    def set_dialog_extension_groups(self, group_names: list[str] | tuple[str, ...]) -> None:
        expected = list(dict.fromkeys(str(group).strip() for group in group_names if str(group).strip()))
        if not expected:
            raise ValueError("at least one extension group must remain selected")

        current = self.dialog_extension_groups()
        for group_name in [group for group in current if group not in expected]:
            self._ensure_dialog_extension_group_dropdown_open()
            self.cdp.click_element_by_script(self._dropdown_item_script(group_name))
            self._wait_for_dialog_extension_group_membership(group_name, selected=False)

        current = self.dialog_extension_groups()
        for group_name in [group for group in expected if group not in current]:
            self._ensure_dialog_extension_group_dropdown_open()
            self.cdp.click_element_by_script(self._dropdown_item_script(group_name))
            self._wait_for_dialog_extension_group_membership(group_name, selected=True)
        if self.cdp.evaluate(self._dialog_extension_group_dropdown_open_script()):
            self.cdp.press("Escape")
        self._wait_for_dialog_extension_groups(expected)

    def save_extension_edit(self) -> None:
        self._click_overlay_button_wait_loading_then_closed("确定", timeout_seconds=60)
        self._wait_for_extension_list_stable(timeout_seconds=30)

    def set_dialog_extension_name(self, name: str) -> None:
        expected_name = str(name or "").strip()
        if not expected_name:
            raise ValueError("extension name cannot be empty")
        self.cdp.fill_element_by_script(
            self._dialog_field_by_label_script("扩展名称", "input"),
            expected_name,
        )
        self._wait_dialog_field_value("扩展名称", expected_name)

    def wait_dialog_extension_name(self, expected_name: str) -> None:
        self._wait_dialog_field_value("扩展名称", str(expected_name or "").strip())

    def restore_extension_name_if_needed(self, original_name: str, edited_name: str) -> None:
        original = str(original_name or "").strip()
        edited = str(edited_name or "").strip()
        if not original or not edited or original == edited:
            raise ValueError("original and edited extension names must be non-empty and different")

        self.dismiss_blocking_overlays()
        self.open_list()
        self.open_added_extensions_tab()
        self.clear_added_extension_filters()
        self.search_added_extension(original)
        if self.extension_exact_name_visible(original):
            return

        self.search_added_extension(edited)
        if not self.extension_exact_name_visible(edited):
            raise RuntimeError(
                "extension name cleanup could not find either state: "
                f"original={original!r}, edited={edited!r}"
            )
        self.open_extension_edit_dialog(edited)
        self.wait_dialog_extension_name(edited)
        self.set_dialog_extension_name(original)
        self.save_extension_edit()
        self.search_added_extension(original)
        self.wait_extension_visible(original)
        if not self.extension_exact_name_visible(original):
            raise RuntimeError(f"extension name cleanup did not restore original name: {original!r}")

    def open_extension_group_manager(self) -> None:
        self.cdp.click_element_by_script(self._primary_text_button_script("分组管理"))
        self._wait_for_extension_group_drawer_visible()
        self._wait_for_extension_group_table_stable()

    def close_extension_group_manager(self) -> None:
        if not self.cdp.evaluate(self._extension_group_drawer_visible_script()):
            return
        self.cdp.click_element_by_script(self._extension_group_drawer_close_script())
        self._wait_for_extension_group_drawer_hidden()
        self._wait_for_extension_list_stable()

    def create_extension_group(self, name: str, remark: str) -> None:
        clean_name = str(name or "").strip()
        clean_remark = str(remark or "").strip()
        if not clean_name:
            raise ValueError("extension group name cannot be empty")
        self.cdp.click_element_by_script(self._primary_text_button_script("创建分组"))
        self._wait_for_extension_group_overlay_visible("创建扩展分组")
        for field_label, value in (("分组名称", clean_name), ("备注", clean_remark)):
            self.cdp.fill_element_by_script(
                self._dialog_field_by_label_script(field_label, "input"),
                value,
            )
            self._wait_dialog_field_value(field_label, value)
        self._click_extension_group_overlay_button_wait_loading_then_closed(
            overlay_text="创建扩展分组",
            button_text="确定",
        )
        self._wait_for_extension_group_table_stable()
        self.wait_extension_group_visible(clean_name)

    def delete_extension_group(self, name: str) -> None:
        clean_name = str(name or "").strip()
        group = self.extension_group_by_name(clean_name)
        if not group:
            raise RuntimeError(f"extension group does not exist: {clean_name!r}")
        if not bool(group.get("deletable")):
            raise RuntimeError(f"extension group is not deletable: {group}")
        self.cdp.click_element_by_script(self._extension_group_row_delete_script(clean_name))
        confirmation_text = "是否确定删除该分组？"
        self._wait_for_extension_group_overlay_visible(confirmation_text)
        self._click_extension_group_overlay_button_wait_loading_then_closed(
            overlay_text=confirmation_text,
            button_text="确定",
        )
        self._wait_for_extension_group_table_stable()
        self.wait_extension_group_absent(clean_name)

    def delete_extension_group_if_exists(self, name: str) -> None:
        clean_name = str(name or "").strip()
        if not clean_name:
            return
        group = self.extension_group_by_name(clean_name)
        if not group:
            return
        self.delete_extension_group(clean_name)

    def extension_group_by_name(self, name: str) -> dict[str, object]:
        clean_name = str(name or "").strip()
        matches = [row for row in self._extension_group_rows() if row["name"] == clean_name]
        if len(matches) > 1:
            raise RuntimeError(
                f"extension group name is ambiguous: name={clean_name!r}, matches={len(matches)}"
            )
        return matches[0] if matches else {}

    def extension_group_by_identity(self, remark: str, created_at: str) -> dict[str, object]:
        clean_remark = str(remark or "").strip()
        clean_created_at = str(created_at or "").strip()
        if not clean_created_at:
            raise ValueError("extension group created_at cannot be empty")
        matches = [
            row
            for row in self._extension_group_rows()
            if row["remark"] == clean_remark and row["created_at"] == clean_created_at
        ]
        if len(matches) != 1:
            raise RuntimeError(
                "extension group identity must match exactly one row: "
                f"remark={clean_remark!r}, created_at={clean_created_at!r}, matches={len(matches)}"
            )
        return matches[0]

    def edit_extension_group_name_by_identity(
        self,
        *,
        remark: str,
        created_at: str,
        new_name: str,
        expected_current_name: str = "",
    ) -> None:
        clean_remark = str(remark or "").strip()
        clean_created_at = str(created_at or "").strip()
        clean_name = str(new_name or "").strip()
        if not clean_name:
            raise ValueError("extension group name cannot be empty")
        current = self.extension_group_by_identity(clean_remark, clean_created_at)
        current_name = str(current["name"])
        if expected_current_name and current_name != str(expected_current_name).strip():
            raise AssertionError(
                "extension group current name does not match before edit: "
                f"expected={expected_current_name!r}, actual={current_name!r}"
            )
        if not bool(current.get("editable")):
            raise RuntimeError(f"extension group is not editable: {current}")

        self.cdp.click_element_by_script(
            self._extension_group_row_edit_by_identity_script(clean_remark, clean_created_at)
        )
        self._wait_for_extension_group_overlay_visible("编辑扩展分组")
        self._wait_dialog_field_value("分组名称", current_name)
        self._wait_dialog_field_value("备注", clean_remark)
        self.cdp.fill_element_by_script(
            self._dialog_field_by_label_script("分组名称", "input"),
            clean_name,
        )
        self._wait_dialog_field_value("分组名称", clean_name)
        self._click_extension_group_overlay_button_wait_loading_then_closed(
            overlay_text="编辑扩展分组",
            button_text="确定",
        )
        self._wait_for_extension_group_table_stable()
        self.wait_extension_group_name_by_identity(clean_remark, clean_created_at, clean_name)

    def restore_extension_group_name_if_needed(
        self,
        *,
        remark: str,
        created_at: str,
        original_name: str,
    ) -> None:
        current = self.extension_group_by_identity(remark, created_at)
        clean_original_name = str(original_name or "").strip()
        if current["name"] == clean_original_name:
            return
        self.edit_extension_group_name_by_identity(
            remark=remark,
            created_at=created_at,
            new_name=clean_original_name,
            expected_current_name=str(current["name"]),
        )

    def wait_extension_group_name_by_identity(
        self,
        remark: str,
        created_at: str,
        expected_name: str,
        timeout_seconds: int | None = None,
    ) -> None:
        clean_remark = str(remark or "").strip()
        clean_created_at = str(created_at or "").strip()
        clean_expected_name = str(expected_name or "").strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_matches: list[dict[str, object]] = []
        while time.time() < deadline:
            last_matches = [
                row
                for row in self._extension_group_rows()
                if row["remark"] == clean_remark and row["created_at"] == clean_created_at
            ]
            if len(last_matches) > 1:
                raise RuntimeError(
                    "extension group identity became ambiguous while waiting for name: "
                    f"remark={clean_remark!r}, created_at={clean_created_at!r}, "
                    f"matches={len(last_matches)}"
                )
            if len(last_matches) == 1 and last_matches[0]["name"] == clean_expected_name:
                return
            time.sleep(0.2)
        raise TimeoutError(
            "extension group name did not reach expected value by identity: "
            f"remark={clean_remark!r}, created_at={clean_created_at!r}, "
            f"expected={clean_expected_name!r}, matches={last_matches}"
        )

    def extension_group_visible(self, name: str) -> bool:
        return bool(self.extension_group_by_name(name))

    def wait_extension_group_visible(
        self,
        name: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.extension_group_visible(name):
                return
            time.sleep(0.2)
        raise TimeoutError(f"extension group did not appear in list: {name!r}")

    def wait_extension_group_absent(
        self,
        name: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.extension_group_visible(name):
                return
            time.sleep(0.2)
        raise TimeoutError(f"extension group still exists in list: {name!r}")

    def _extension_group_rows(self) -> list[dict[str, object]]:
        value = self.cdp.evaluate(self._extension_group_rows_script())
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
                    "containing_extensions": str(item.get("containing_extensions", "") or "").strip(),
                    "bound_environments": str(item.get("bound_environments", "") or "").strip(),
                    "creator": str(item.get("creator", "") or "").strip(),
                    "created_at": str(item.get("created_at", "") or "").strip(),
                    "editable": bool(item.get("editable")),
                    "deletable": bool(item.get("deletable")),
                }
            )
        return rows

    def restore_extension_groups_if_needed(self, name: str, original_groups: list[str] | tuple[str, ...]) -> None:
        expected = list(dict.fromkeys(str(group).strip() for group in original_groups if str(group).strip()))
        if not expected:
            raise ValueError("original extension groups cannot be empty")

        self.dismiss_blocking_overlays()
        self.open_list()
        self.open_added_extensions_tab()
        self.clear_added_extension_filters()
        self.search_added_extension(name)
        self.wait_extension_visible(name)
        self.open_extension_edit_dialog(name)
        if set(self.dialog_extension_groups()) == set(expected):
            self.cdp.click_element_by_script(self._active_overlay_button_script("取消"))
            self._wait_for_edit_extension_dialog_hidden()
            return
        self.set_dialog_extension_groups(expected)
        self.save_extension_edit()

    def _ensure_dialog_extension_group_dropdown_open(self) -> None:
        if self.cdp.evaluate(self._dialog_extension_group_dropdown_open_script()):
            return
        self.cdp.click_element_by_script(self._dialog_select_by_label_script("扩展分组"))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._dialog_extension_group_dropdown_open_script()):
                return
            time.sleep(0.1)
        raise TimeoutError("extension group dropdown did not open")

    def ensure_dialog_switch_state(self, label_text: str, enabled: bool) -> None:
        if self.cdp.evaluate(self._dialog_switch_checked_script(label_text)) == enabled:
            return
        self.cdp.click_element_by_script(self._dialog_switch_script(label_text))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._dialog_switch_checked_script(label_text)) == enabled:
                return
            time.sleep(0.2)
        raise TimeoutError(f"dialog switch did not become {enabled}: {label_text}")

    def ensure_dialog_member_group(self, group_name: str) -> None:
        self._wait_dialog_member_group_visible()
        current = str(self.cdp.evaluate(self._dialog_member_group_value_script()) or "").strip()
        if group_name in current:
            return
        self._clear_dialog_member_group()
        self.cdp.click_element_by_script(self._dialog_member_group_select_script())
        self.cdp.click_element_by_script(self._dropdown_item_script(group_name))
        self.cdp.press("Escape")
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            current = str(self.cdp.evaluate(self._dialog_member_group_value_script()) or "").strip()
            if group_name in current:
                return
            time.sleep(0.2)
        raise TimeoutError(f"dialog member group did not become {group_name}: actual={current}")

    def extension_enabled(self, name: str) -> bool:
        return bool(self.cdp.evaluate(self._extension_card_switch_checked_script(name)))

    def set_extension_enabled(self, name: str, enabled: bool, retries: int = 3) -> None:
        for attempt in range(1, retries + 1):
            if self.extension_enabled(name) == enabled:
                return
            self.cdp.click_element_by_script(self._extension_card_switch_script(name))
            self._confirm_if_present(timeout_seconds=2)
            try:
                self._wait_extension_switch_state(name, enabled, timeout_seconds=30)
                return
            except TimeoutError:
                if attempt >= retries:
                    break
                time.sleep(0.5)
        actual = self.extension_enabled(name)
        raise AssertionError(f"extension switch did not become {enabled}: name={name}, actual={actual}")

    def market_extension_visible(self, name: str, description: str) -> bool:
        return bool(self.cdp.evaluate(self._market_extension_exists_script(name, description)))

    def wait_market_extension_visible(
        self,
        name: str,
        description: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.market_extension_visible(name, description):
                return
            time.sleep(0.3)
        raise TimeoutError(f"market extension did not appear: name={name}, description={description}")

    def ensure_extension_group(self, group_name: str, wait_for_async_default_seconds: int = 0) -> None:
        current = ""
        deadline = time.time() + wait_for_async_default_seconds
        while time.time() < deadline:
            current = str(self.cdp.evaluate(self._dialog_select_value_by_label_script("扩展分组")) or "").strip()
            if current == group_name or group_name in current:
                return
            time.sleep(0.3)
        current = str(self.cdp.evaluate(self._dialog_select_value_by_label_script("扩展分组")) or "").strip()
        if current == group_name or group_name in current:
            return
        self._clear_dialog_select_by_label("扩展分组")
        self.cdp.click_element_by_script(self._dialog_select_by_label_script("扩展分组"))
        self.cdp.click_element_by_script(self._dropdown_item_script(group_name))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            current = str(self.cdp.evaluate(self._dialog_select_value_by_label_script("扩展分组")) or "").strip()
            if current == group_name:
                return
            time.sleep(0.2)
        raise TimeoutError(f"extension group did not become {group_name}: actual={current}")

    def ensure_dialog_checkbox_checked(self, label_text: str) -> None:
        if self.cdp.evaluate(self._dialog_checkbox_checked_script(label_text)):
            return
        self.cdp.click_element_by_script(self._dialog_checkbox_script(label_text))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._dialog_checkbox_checked_script(label_text)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"dialog checkbox did not become checked: {label_text}")

    def delete_extension(self, name: str) -> None:
        self.cdp.hover_element_by_script(self._extension_card_script(name))
        self.cdp.click_element_by_script(self._extension_card_more_button_script(name))
        self.cdp.click_element_by_script(self._dropdown_item_script("删除"))
        self._wait_delete_extension_dialog_visible()
        self._click_overlay_button_wait_loading_then_closed("确定")
        self._wait_for_extension_list_not_loading()
        self.wait_extension_absent(name)

    def delete_extension_if_exists(self, name: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "search_result_seconds", 10)
        while time.time() < deadline:
            if not self.extension_visible(name):
                return
            self.delete_extension(name)
            time.sleep(0.3)
        if self.extension_visible(name):
            raise TimeoutError(f"extension still exists after cleanup: {name}")

    def extension_visible(self, name: str) -> bool:
        return bool(self.cdp.evaluate(self._extension_exists_script(name)))

    def extension_exact_name_visible(self, name: str) -> bool:
        return bool(self.cdp.evaluate(self._extension_exact_name_exists_script(name)))

    def extension_with_description_visible(self, name: str, description: str) -> bool:
        return bool(self.cdp.evaluate(self._extension_with_description_exists_script(name, description)))

    def wait_extension_visible(self, name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.extension_visible(name):
                return
            time.sleep(0.3)
        raise TimeoutError(f"extension did not appear in list: {name}")

    def wait_extension_with_description_visible(
        self,
        name: str,
        description: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.extension_with_description_visible(name, description):
                return
            time.sleep(0.3)
        raise TimeoutError(f"extension with description did not appear in list: name={name}, description={description}")

    def wait_extension_absent(self, name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.extension_visible(name):
                return
            time.sleep(0.3)
        raise TimeoutError(f"extension still exists in list: {name}")

    def extension_card_details(self, name: str) -> dict[str, str]:
        value = self.cdp.evaluate(self._extension_card_details_script(name))
        if not isinstance(value, dict):
            return {}
        details = {str(key): str(item or "").strip() for key, item in value.items()}
        raw = details.get("raw", "")
        if not details.get("provider") and "提供方:" in raw:
            provider = raw.split("提供方:", 1)[1].strip()
            details["provider"] = re.split(r"\s+", provider)[0].strip()
        return details

    def dismiss_blocking_overlays(self) -> None:
        for _ in range(5):
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
                                .find((button) => ["取消", "关闭"].includes(clean(button.innerText || button.textContent)));
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
            time.sleep(0.4)

    def _choose_package_file(self, package_path: Path) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="dicloak_ext_upload_"))
        self._temporary_upload_dirs.append(temp_dir)
        ascii_package = temp_dir / "dicloak-local-extension.zip"
        shutil.copy2(package_path, ascii_package)

        self.cdp.evaluate_with_args(
            """
            (filePath) => {
                Object.defineProperty(File.prototype, "path", {
                    configurable: true,
                    get() {
                        return filePath;
                    },
                });
            }
            """,
            str(package_path),
        )
        upload_button = self.cdp._wait_for_element_by_script(self._dialog_package_upload_button_script())
        with self.cdp._page().expect_file_chooser(timeout=config_timeout_seconds(self.config, "page_seconds", 10) * 1000) as chooser:
            upload_button.click()
        chooser.value.set_files(str(ascii_package))
        expected_markers = [str(package_path), package_path.name, ascii_package.name]
        if self._wait_package_dialog_upload_shown(expected_markers, timeout_seconds=10):
            return
        raise TimeoutError(
            "local extension package was not shown after upload: "
            f"expected_markers={expected_markers}"
        )

    def _cleanup_temporary_upload_files(self) -> None:
        for temp_dir in self._temporary_upload_dirs:
            try:
                shutil.rmtree(temp_dir)
            except OSError:
                pass
        self._temporary_upload_dirs.clear()

    def _wait_package_dialog_upload_shown(self, expected_markers: list[str], timeout_seconds: int) -> bool:
        markers = [str(marker).strip() for marker in expected_markers if str(marker).strip()]
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate_with_args(
                """
                (expectedMarkers) => {
                    const visible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== "none"
                            && style.visibility !== "hidden"
                            && rect.width > 0
                            && rect.height > 0;
                    };
                    const dialog = Array.from(document.querySelectorAll(".el-dialog")).filter(visible).slice(-1)[0];
                    const text = dialog ? (dialog.innerText || dialog.textContent || "") : "";
                    return expectedMarkers.some((marker) => text.includes(marker));
                }
                """,
                markers,
            ):
                return True
            time.sleep(0.2)
        return False

    def _wait_for_extension_list(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._extension_list_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("extension management list did not appear")

    def _wait_for_extension_list_not_loading(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.cdp.evaluate(self._loading_visible_script()):
                return
            time.sleep(0.3)
        raise TimeoutError("extension management list is still loading")

    def _wait_for_extension_list_stable(
        self,
        timeout_seconds: int | None = None,
        stable_seconds: float = 0.5,
        poll_seconds: float = 0.1,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        stable_since: float | None = None
        last_signature = ""
        last_state: dict[str, object] = {}
        while time.time() < deadline:
            value = self.cdp.evaluate(self._extension_list_state_script())
            last_state = value if isinstance(value, dict) else {}
            if bool(last_state.get("loading")):
                stable_since = None
                last_signature = ""
                time.sleep(poll_seconds)
                continue
            signature = str(last_state.get("signature", ""))
            if signature != last_signature:
                last_signature = signature
                stable_since = time.time()
            elif stable_since is not None and time.time() - stable_since >= stable_seconds:
                return
            time.sleep(poll_seconds)
        raise TimeoutError(f"extension management list did not become stable: {last_state}")

    def _wait_for_extension_group_drawer_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._extension_group_drawer_visible_script()):
                return
            time.sleep(0.1)
        raise TimeoutError("extension group management drawer did not appear")

    def _wait_for_extension_group_drawer_hidden(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.cdp.evaluate(self._extension_group_drawer_visible_script()):
                return
            time.sleep(0.1)
        raise TimeoutError("extension group management drawer did not close")

    def _wait_for_extension_group_table_stable(
        self,
        timeout_seconds: int | None = None,
        stable_seconds: float = 0.5,
        poll_seconds: float = 0.1,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        stable_since: float | None = None
        last_signature = ""
        last_state: dict[str, object] = {}
        while time.time() < deadline:
            value = self.cdp.evaluate(self._extension_group_table_state_script())
            last_state = value if isinstance(value, dict) else {}
            if not bool(last_state.get("drawer_visible")) or bool(last_state.get("loading")):
                stable_since = None
                last_signature = ""
                time.sleep(poll_seconds)
                continue
            signature = str(last_state.get("signature", ""))
            if signature != last_signature:
                last_signature = signature
                stable_since = time.time()
            elif stable_since is not None and time.time() - stable_since >= stable_seconds:
                return
            time.sleep(poll_seconds)
        raise TimeoutError(f"extension group table did not become stable: {last_state}")

    def _wait_for_extension_group_overlay_visible(
        self,
        overlay_text: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._extension_group_overlay_visible_script(overlay_text)):
                return
            time.sleep(0.1)
        raise TimeoutError(f"extension group overlay did not appear: {overlay_text!r}")

    def _click_extension_group_overlay_button_wait_loading_then_closed(
        self,
        *,
        overlay_text: str,
        button_text: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        self.cdp.click_element_by_script(
            self._extension_group_overlay_button_script(overlay_text, button_text)
        )
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.cdp.evaluate(self._extension_group_overlay_visible_script(overlay_text)):
                return
            self.cdp.evaluate(
                self._extension_group_overlay_button_state_script(overlay_text, button_text)
            )
            time.sleep(0.1)
        raise TimeoutError(
            f"extension group overlay did not close: overlay={overlay_text!r}, button={button_text!r}"
        )

    def _wait_for_add_extension_dialog(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._add_extension_dialog_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("add extension dialog did not appear")

    def _wait_for_edit_extension_dialog_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._edit_extension_dialog_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("edit extension dialog did not appear")

    def _wait_for_edit_extension_dialog_hidden(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.cdp.evaluate(self._edit_extension_dialog_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("edit extension dialog did not close")

    def _wait_for_dialog_extension_groups_ready(
        self,
        timeout_seconds: int | None = None,
        stable_seconds: float = 0.4,
        poll_seconds: float = 0.1,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        self._ensure_dialog_extension_group_dropdown_open()
        while time.time() < deadline:
            if self.cdp.evaluate(self._dialog_extension_group_options_rendered_script()):
                self.cdp.press("Escape")
                break
            time.sleep(poll_seconds)
        else:
            raise TimeoutError("extension group dropdown options did not render")
        stable_since: float | None = None
        last_groups: list[str] = []
        while time.time() < deadline:
            groups = self.dialog_extension_groups()
            if groups and groups == last_groups:
                stable_since = stable_since or time.time()
                if time.time() - stable_since >= stable_seconds:
                    return
            else:
                last_groups = groups
                stable_since = time.time() if groups else None
            time.sleep(poll_seconds)
        raise TimeoutError(f"edit extension groups did not become ready: groups={last_groups}")

    def _wait_for_dialog_extension_group_membership(
        self,
        group_name: str,
        *,
        selected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_groups: list[str] = []
        while time.time() < deadline:
            last_groups = self.dialog_extension_groups()
            if (group_name in last_groups) == selected:
                return
            time.sleep(0.1)
        raise TimeoutError(
            f"dialog extension group membership did not become {selected}: "
            f"group={group_name}, actual={last_groups}"
        )

    def _wait_for_dialog_extension_groups(
        self,
        expected_groups: list[str] | tuple[str, ...],
        timeout_seconds: int | None = None,
    ) -> None:
        expected = {str(group).strip() for group in expected_groups if str(group).strip()}
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_groups: list[str] = []
        while time.time() < deadline:
            last_groups = self.dialog_extension_groups()
            if set(last_groups) == expected:
                return
            time.sleep(0.1)
        raise TimeoutError(f"dialog extension groups did not match: expected={expected}, actual={last_groups}")

    def _wait_for_list_filter_value(
        self,
        index: int,
        expected_value: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_value = ""
        while time.time() < deadline:
            last_value = self._list_filter_value(index)
            if last_value == expected_value:
                return
            time.sleep(0.1)
        raise TimeoutError(
            f"extension list filter did not become expected: "
            f"index={index}, expected={expected_value}, actual={last_value}"
        )

    def _wait_for_extension_name_search_value(
        self,
        expected_value: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_value = ""
        while time.time() < deadline:
            last_value = self._extension_name_search_value()
            if last_value == expected_value:
                return
            time.sleep(0.1)
        raise TimeoutError(
            f"extension name search did not become expected: expected={expected_value!r}, actual={last_value!r}"
        )

    def _list_filter_value(self, index: int) -> str:
        return str(self.cdp.evaluate(self._list_filter_value_script(index)) or "").strip()

    def _extension_name_search_value(self) -> str:
        return str(self.cdp.evaluate(self._extension_name_search_value_script()) or "").strip()

    def _wait_dialog_member_group_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._dialog_member_group_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("dialog member group field did not appear")

    def _wait_extension_switch_state(self, name: str, enabled: bool, timeout_seconds: int) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.extension_enabled(name) == enabled:
                return
            time.sleep(0.3)
        raise TimeoutError(f"extension switch state did not become {enabled}: {name}")

    def _wait_for_local_package_mode(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._local_package_mode_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("local package mode did not appear in add extension dialog")

    def _wait_delete_extension_dialog_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._delete_extension_dialog_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("delete extension confirmation dialog did not appear")

    def _wait_dialog_field_value(
        self,
        field_label: str,
        expected_value: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_value = ""
        while time.time() < deadline:
            last_value = str(self.cdp.evaluate(self._dialog_field_value_script(field_label)) or "").strip()
            if last_value == expected_value:
                return
            time.sleep(0.2)
        raise TimeoutError(
            "extension dialog field value did not become expected: "
            f"field={field_label}, expected={expected_value}, actual={last_value}"
        )

    def _click_overlay_button_wait_loading_then_closed(self, text: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        self.cdp.click_element_by_script(self._active_overlay_button_script(text))
        deadline = time.time() + timeout_seconds
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
            self._wait_for_overlay_closed(timeout_seconds=timeout_seconds)
            return
        self._wait_for_overlay_closed(timeout_seconds=timeout_seconds)

    def _wait_for_overlay_closed(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.cdp.evaluate(self._active_overlay_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("overlay did not close")

    def _active_overlay_button_state(self, text: str) -> dict[str, object]:
        value = self.cdp.evaluate(self._active_overlay_button_state_script(text))
        return value if isinstance(value, dict) else {}

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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return Array.from(document.querySelectorAll({self.locator("menu_candidates")!r}))
                .filter(visible)
                .find((el) => clean(el.innerText || el.textContent) === expectedText) || null;
        }}
        """

    def _primary_text_button_script(self, text: str) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return Array.from(document.querySelectorAll({self.locator("button")!r}))
                .filter(visible)
                .find((button) => clean(button.innerText || button.textContent) === expectedText
                    && button.classList.contains("el-button--primary")) || null;
        }}
        """

    def _text_button_script(self, text: str) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return Array.from(document.querySelectorAll({self.locator("button")!r}))
                .filter(visible)
                .find((button) => clean(button.innerText || button.textContent) === expectedText) || null;
        }}
        """

    def _extension_tab_script(self, text: str) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(
                ".env-segmented-tabs__item, .el-tabs__item, [role='tab']"
            )).filter(visible);
            return candidates.find((item) => clean(item.innerText || item.textContent) === expectedText)
                || candidates.find((item) => clean(item.innerText || item.textContent).includes(expectedText))
                || null;
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const overlays = Array.from(document.querySelectorAll({self.locator("blocking_overlay")!r}))
                .filter(visible);
            for (const overlay of overlays.reverse()) {{
                const button = Array.from(overlay.querySelectorAll({self.locator("button")!r}))
                    .find((el) => visible(el) && clean(el.innerText || el.textContent) === expectedText);
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const overlays = Array.from(document.querySelectorAll({self.locator("blocking_overlay")!r}))
                .filter(visible);
            for (const overlay of overlays.reverse()) {{
                const button = Array.from(overlay.querySelectorAll({self.locator("button")!r}))
                    .find((el) => visible(el) && clean(el.innerText || el.textContent) === expectedText);
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

    def _dialog_field_value_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const field = ({self._dialog_field_by_label_script(field_label, "input,textarea")})();
            return field ? String(field.value || "") : "";
        }}
        """

    def _extension_group_drawer_script(self) -> str:
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
            return Array.from(document.querySelectorAll({self.locator("group_drawer")!r}))
                .filter(visible)
                .reverse()
                .find((drawer) => clean(
                    drawer.querySelector({self.locator("group_drawer_title")!r})?.innerText
                        || drawer.innerText
                        || drawer.textContent
                ).includes("扩展分组管理")) || null;
        }}
        """

    def _extension_group_drawer_visible_script(self) -> str:
        return f"""
        () => Boolean(({self._extension_group_drawer_script()})())
        """

    def _extension_group_drawer_close_script(self) -> str:
        return f"""
        () => {{
            const drawer = ({self._extension_group_drawer_script()})();
            return drawer?.querySelector({self.locator("overlay_close_button")!r}) || null;
        }}
        """

    def _extension_group_rows_script(self) -> str:
        return f"""
        () => {{
            const drawer = ({self._extension_group_drawer_script()})();
            if (!drawer) return [];
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const table = drawer.querySelector({self.locator("group_table")!r});
            return Array.from(table?.querySelectorAll({self.locator("group_table_row")!r}) || [])
                .filter(visible)
                .map((row) => {{
                    const cells = Array.from(row.querySelectorAll({self.locator("group_table_cell")!r}));
                    const texts = cells.map((cell) => clean(cell.innerText || cell.textContent));
                    const operation = cells[6] || cells[cells.length - 1] || null;
                    const icons = Array.from(operation?.querySelectorAll(".iconfont") || []).filter(visible);
                    return {{
                        name: texts[0] || "",
                        remark: texts[1] || "",
                        containing_extensions: texts[2] || "",
                        bound_environments: texts[3] || "",
                        creator: texts[4] || "",
                        created_at: texts[5] || "",
                        editable: Boolean(icons[0]?.matches({self.locator("group_edit_icon")!r})),
                        deletable: Boolean(icons[1]?.matches({self.locator("group_delete_icon")!r})),
                    }};
                }})
                .filter((row) => row.name);
        }}
        """

    def _extension_group_row_delete_script(self, name: str) -> str:
        return f"""
        () => {{
            const expectedName = {name!r};
            const drawer = ({self._extension_group_drawer_script()})();
            if (!drawer) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const rows = Array.from(drawer.querySelectorAll({self.locator("group_table_row")!r}))
                .filter(visible)
                .filter((row) => {{
                    const firstCell = row.querySelector({self.locator("group_table_cell")!r});
                    return clean(firstCell?.innerText || firstCell?.textContent) === expectedName;
                }});
            if (rows.length !== 1) return null;
            const cells = Array.from(rows[0].querySelectorAll({self.locator("group_table_cell")!r}));
            const operation = cells[6] || cells[cells.length - 1] || null;
            const icons = Array.from(operation?.querySelectorAll(".iconfont") || []).filter(visible);
            const secondIcon = icons[1] || null;
            return secondIcon?.matches({self.locator("group_delete_icon")!r}) ? secondIcon : null;
        }}
        """

    def _extension_group_row_edit_by_identity_script(self, remark: str, created_at: str) -> str:
        return f"""
        () => {{
            const expectedRemark = {str(remark or '').strip()!r};
            const expectedCreatedAt = {str(created_at or '').strip()!r};
            const drawer = ({self._extension_group_drawer_script()})();
            if (!drawer) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const rows = Array.from(drawer.querySelectorAll({self.locator("group_table_row")!r}))
                .filter(visible)
                .filter((row) => {{
                    const cells = Array.from(row.querySelectorAll({self.locator("group_table_cell")!r}));
                    return clean(cells[1]?.innerText || cells[1]?.textContent) === expectedRemark
                        && clean(cells[5]?.innerText || cells[5]?.textContent) === expectedCreatedAt;
                }});
            if (rows.length !== 1) return null;
            const cells = Array.from(rows[0].querySelectorAll({self.locator("group_table_cell")!r}));
            const operation = cells[6] || cells[cells.length - 1] || null;
            const icons = Array.from(operation?.querySelectorAll(".iconfont") || []).filter(visible);
            const firstIcon = icons[0] || null;
            return firstIcon?.matches({self.locator("group_edit_icon")!r}) ? firstIcon : null;
        }}
        """

    def _extension_group_table_state_script(self) -> str:
        return f"""
        () => {{
            const drawer = ({self._extension_group_drawer_script()})();
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            if (!drawer) return {{ drawer_visible: false, loading: false, signature: "" }};
            const loading = Array.from(drawer.querySelectorAll(".el-loading-mask")).some(visible);
            const rows = ({self._extension_group_rows_script()})();
            return {{
                drawer_visible: true,
                loading,
                signature: JSON.stringify(rows),
            }};
        }}
        """

    def _extension_group_overlay_visible_script(self, overlay_text: str) -> str:
        return f"""
        () => {{
            const expectedText = {overlay_text!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return Array.from(document.querySelectorAll(".el-dialog, .el-message-box"))
                .filter(visible)
                .some((overlay) => clean(overlay.innerText || overlay.textContent).includes(expectedText));
        }}
        """

    def _extension_group_overlay_button_script(self, overlay_text: str, button_text: str) -> str:
        return f"""
        () => {{
            const expectedOverlayText = {overlay_text!r};
            const expectedButtonText = {button_text!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const overlay = Array.from(document.querySelectorAll(".el-dialog, .el-message-box"))
                .filter(visible)
                .reverse()
                .find((item) => clean(item.innerText || item.textContent).includes(expectedOverlayText));
            return Array.from(overlay?.querySelectorAll({self.locator("button")!r}) || [])
                .filter(visible)
                .find((button) => clean(button.innerText || button.textContent) === expectedButtonText) || null;
        }}
        """

    def _extension_group_overlay_button_state_script(
        self,
        overlay_text: str,
        button_text: str,
    ) -> str:
        return f"""
        () => {{
            const button = ({self._extension_group_overlay_button_script(overlay_text, button_text)})();
            if (!button) return {{ visible: false, loading: false, disabled: false }};
            return {{
                visible: true,
                loading: button.classList.contains("is-loading")
                    || Boolean(button.querySelector(".is-loading, .el-icon-loading, [class*='loading']")),
                disabled: Boolean(button.disabled)
                    || button.getAttribute("aria-disabled") === "true"
                    || button.classList.contains("is-disabled"),
            }};
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

    def _dialog_radio_button_script(self, text: str) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const dialogs = Array.from(document.querySelectorAll({self.locator("dialog")!r})).filter(visible);
            for (const dialog of dialogs.reverse()) {{
                const item = Array.from(dialog.querySelectorAll(".el-radio-button, label, button, span"))
                    .filter(visible)
                    .find((el) => clean(el.innerText || el.textContent) === expectedText);
                if (item) return item;
            }}
            return null;
        }}
        """

    def _dialog_package_upload_button_script(self) -> str:
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
            for (const dialog of dialogs.reverse()) {{
                const formItems = Array.from(dialog.querySelectorAll(".el-form-item")).filter(visible);
                const packageItem = formItems.find((item) => {{
                    const itemText = clean(item.innerText || item.textContent);
                    const accepts = Array.from(item.querySelectorAll("input[type='file']"))
                        .map((input) => String(input.getAttribute("accept") || "").toLowerCase());
                    const hasZipInput = accepts.some((accept) => accept.includes("zip"));
                    return itemText.includes("安装包") && (itemText.includes("ZIP") || itemText.includes("zip") || hasZipInput);
                }});
                if (packageItem) {{
                    const uploadTarget = Array.from(packageItem.querySelectorAll(".el-upload, .el-upload-dragger, button, [role='button']"))
                        .filter(visible)
                        .find((item) => {{
                            const itemText = clean(item.innerText || item.textContent);
                            return itemText.includes("上传") || itemText.includes("ZIP") || item.classList.contains("el-upload");
                        }});
                    if (uploadTarget) return uploadTarget;
                }}
                const button = Array.from(dialog.querySelectorAll("button, .el-upload, .el-upload-dragger"))
                    .filter(visible)
                    .find((item) => {{
                        const itemText = clean(item.innerText || item.textContent);
                        return itemText.includes("将 ZIP 文件") || itemText === "上传";
                    }});
                if (button) return button;
            }}
            return null;
        }}
        """

    def _dialog_select_by_label_script(self, field_label: str) -> str:
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
                const formItem = Array.from(dialog.querySelectorAll({self.locator("form_item")!r}))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent).includes(clean(expectedLabel)));
                const select = Array.from(formItem?.querySelectorAll(".el-select, .el-select__wrapper") || []).find(visible);
                if (select) return select;
            }}
            return null;
        }}
        """

    def _dialog_select_value_by_label_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const select = ({self._dialog_select_by_label_script(field_label)})();
            if (!select) return "";
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return clean(select.innerText || select.textContent || "");
        }}
        """

    def _dialog_extension_groups_script(self) -> str:
        return f"""
        () => {{
            const select = ({self._dialog_select_by_label_script("扩展分组")})();
            if (!select) return [];
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const input = select.querySelector("input[role='combobox']");
            const controls = String(input?.getAttribute("aria-controls") || "");
            const dropdown = controls ? document.getElementById(controls) : null;
            const selectedOptions = Array.from(dropdown?.querySelectorAll(".el-select-dropdown__item") || [])
                .filter((item) => item.classList.contains("is-selected")
                    || item.getAttribute("aria-selected") === "true")
                .map((item) => clean(item.innerText || item.textContent))
                .filter(Boolean);
            if (selectedOptions.length) return selectedOptions;
            return Array.from(select.querySelectorAll({self.locator("select_tag")!r}))
                .map((tag) => clean(tag.querySelector(".el-tag__content")?.innerText || tag.innerText || tag.textContent))
                .filter((value) => value && !/^\\+\\s*\\d+$/.test(value));
        }}
        """

    def _dialog_extension_group_dropdown_open_script(self) -> str:
        return f"""
        () => {{
            const select = ({self._dialog_select_by_label_script("扩展分组")})();
            const input = select?.querySelector("input[role='combobox']");
            return input?.getAttribute("aria-expanded") === "true";
        }}
        """

    def _dialog_extension_group_options_rendered_script(self) -> str:
        return f"""
        () => {{
            const select = ({self._dialog_select_by_label_script("扩展分组")})();
            const input = select?.querySelector("input[role='combobox']");
            const controls = String(input?.getAttribute("aria-controls") || "");
            const dropdown = controls ? document.getElementById(controls) : null;
            return Boolean(dropdown?.querySelector(".el-select-dropdown__item"));
        }}
        """

    def _dialog_extension_group_tag_close_script(self, group_name: str) -> str:
        return f"""
        () => {{
            const expectedGroup = {group_name!r};
            const select = ({self._dialog_select_by_label_script("扩展分组")})();
            if (!select) return null;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const tag = Array.from(select.querySelectorAll({self.locator("select_tag")!r}))
                .find((item) => clean(
                    item.querySelector(".el-tag__content")?.innerText || item.innerText || item.textContent
                ) === expectedGroup);
            return tag?.querySelector(".el-tag__close") || null;
        }}
        """

    def _clear_dialog_select_by_label(self, field_label: str) -> None:
        clicked = bool(self.cdp.evaluate(self._clear_dialog_select_by_label_script(field_label)))
        if clicked:
            time.sleep(0.2)

    def _clear_dialog_select_by_label_script(self, field_label: str) -> str:
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
                const formItem = Array.from(dialog.querySelectorAll({self.locator("form_item")!r}))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent).includes(clean(expectedLabel)));
                if (!formItem) continue;
                const clearButton = Array.from(formItem.querySelectorAll(
                    ".el-select__caret.is-show-close, .el-tag__close, [class*='close']"
                )).find(visible);
                if (clearButton) {{
                    clearButton.click();
                    return true;
                }}
            }}
            return false;
        }}
        """

    def _dialog_checkbox_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const expectedText = {label_text!r};
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
            for (const dialog of dialogs.reverse()) {{
                const checkbox = Array.from(dialog.querySelectorAll(".el-checkbox, label"))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent).includes(expectedText));
                if (checkbox) return checkbox;
            }}
            return null;
        }}
        """

    def _dialog_checkbox_checked_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const expectedText = {label_text!r};
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
            for (const dialog of dialogs.reverse()) {{
                const checkbox = Array.from(dialog.querySelectorAll(".el-checkbox, label"))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent).includes(expectedText));
                if (!checkbox) continue;
                return checkbox.classList.contains("is-checked")
                    || Boolean(checkbox.querySelector("input[type='checkbox']:checked"));
            }}
            return false;
        }}
        """

    def _dialog_switch_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const expectedText = {label_text!r};
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
            for (const dialog of dialogs.reverse()) {{
                const formItem = Array.from(dialog.querySelectorAll({self.locator("form_item")!r}))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent).includes(expectedText));
                const switchEl = Array.from(formItem?.querySelectorAll(".el-switch") || []).find(visible);
                if (switchEl) return switchEl;
            }}
            return null;
        }}
        """

    def _dialog_switch_checked_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const expectedText = {label_text!r};
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
            for (const dialog of dialogs.reverse()) {{
                const formItem = Array.from(dialog.querySelectorAll({self.locator("form_item")!r}))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent).includes(expectedText));
                const switchEl = Array.from(formItem?.querySelectorAll(".el-switch") || []).find(visible);
                if (!switchEl) continue;
                return switchEl.classList.contains("is-checked")
                    || switchEl.getAttribute("aria-checked") === "true"
                    || Boolean(switchEl.querySelector("input:checked"));
            }}
            return false;
        }}
        """

    def _dialog_member_group_visible_script(self) -> str:
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
            return dialogs.some((dialog) => clean(dialog.innerText || dialog.textContent).includes("成员分组"));
        }}
        """

    def _dialog_member_group_select_script(self) -> str:
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
            for (const dialog of dialogs.reverse()) {{
                const formItem = Array.from(dialog.querySelectorAll({self.locator("form_item")!r}))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent).includes("成员分组"));
                const select = Array.from(formItem?.querySelectorAll(".el-select, .el-select__wrapper") || []).find(visible);
                if (select) return select;
            }}
            return null;
        }}
        """

    def _dialog_member_group_value_script(self) -> str:
        return f"""
        () => {{
            const select = ({self._dialog_member_group_select_script()})();
            if (!select) return "";
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return clean(select.innerText || select.textContent || "");
        }}
        """

    def _clear_dialog_member_group(self) -> None:
        self.cdp.evaluate(
            f"""
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
                for (const dialog of dialogs.reverse()) {{
                    const formItem = Array.from(dialog.querySelectorAll({self.locator("form_item")!r}))
                        .filter(visible)
                        .find((item) => clean(item.innerText || item.textContent).includes("成员分组"));
                    const closeButtons = Array.from(formItem?.querySelectorAll(
                        ".el-tag__close, .el-select__caret.is-show-close, [class*='close']"
                    ) || []).filter(visible);
                    closeButtons.forEach((button) => button.click());
                    return true;
                }}
                return false;
            }}
            """
        )
        time.sleep(0.2)

    def _market_search_input_script(self, field_label: str) -> str:
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
            const forms = Array.from(document.querySelectorAll(".el-form-item, label, div")).filter(visible);
            for (const item of forms) {{
                const text = clean(item.innerText || item.textContent);
                if (!text.includes(clean(expectedLabel))) continue;
                const input = Array.from(item.querySelectorAll("input")).find(visible);
                if (input) return input;
            }}
            return Array.from(document.querySelectorAll("input"))
                .filter(visible)
                .find((input) => clean(input.getAttribute("placeholder") || "").includes(clean(expectedLabel))) || null;
        }}
        """

    def _extension_name_search_input_script(self) -> str:
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
            return Array.from(document.querySelectorAll({self.locator("extension_name_search_input")!r}))
                .find((input) => visible(input) && !input.closest(".el-dialog")) || null;
        }}
        """

    def _extension_name_search_value_script(self) -> str:
        return f"""
        () => {{
            const input = ({self._extension_name_search_input_script()})();
            return input ? String(input.value || "") : "";
        }}
        """

    def _list_search_button_script(self) -> str:
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
            return Array.from(document.querySelectorAll({self.locator("list_search_button")!r}))
                .find((button) => visible(button) && !button.closest(".el-dialog")) || null;
        }}
        """

    def _list_filter_select_script(self, index: int) -> str:
        return f"""
        () => {{
            const expectedIndex = {index};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const selects = Array.from(document.querySelectorAll(".el-select"))
                .filter((select) => visible(select) && !select.closest(".el-dialog"));
            return selects[expectedIndex] || null;
        }}
        """

    def _list_filter_value_script(self, index: int) -> str:
        return f"""
        () => {{
            const select = ({self._list_filter_select_script(index)})();
            if (!select) return "";
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return clean(select.innerText || select.textContent || "");
        }}
        """

    def _list_filter_clear_script(self, index: int) -> str:
        return f"""
        () => {{
            const select = ({self._list_filter_select_script(index)})();
            return select?.querySelector({self.locator("select_clear_icon")!r}) || null;
        }}
        """

    def _market_extension_exists_script(self, name: str, description: str) -> str:
        return f"""
        () => Boolean(({self._market_extension_card_script(name, description)})())
        """

    def _market_extension_card_script(self, name: str, description: str) -> str:
        return f"""
        () => {{
            const expectedName = {name!r};
            const expectedDescription = {description!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(
                ".el-card, .extension-item, .market-item, .el-row, .el-col, li, tr, div"
            )).filter(visible);
            const matches = candidates
                .map((item) => {{
                    const card = item.closest(".el-card") || item;
                    const text = clean(card.innerText || card.textContent);
                    return {{ card, text, length: text.length }};
                }})
                .filter((item) => item.text.includes(expectedName) && item.text.includes(expectedDescription))
                .sort((left, right) => left.length - right.length);
            return matches.length ? matches[0].card : null;
        }}
        """

    def _market_extension_add_button_script(self, name: str, description: str) -> str:
        return f"""
        () => {{
            const card = ({self._market_extension_card_script(name, description)})();
            if (!card) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return Array.from(card.querySelectorAll("button, [role='button'], span, div"))
                .filter(visible)
                .find((button) => clean(button.innerText || button.textContent) === "添加") || null;
        }}
        """

    def _wait_for_market_add_dialog_ready(
        self,
        name: str,
        group_name: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._market_add_dialog_ready_script(name, group_name)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"market add dialog did not become ready: name={name}, group={group_name}")

    def _market_add_dialog_ready_script(self, name: str, group_name: str) -> str:
        return f"""
        () => {{
            const expectedName = {name!r};
            const expectedGroup = {group_name!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-message-box")).filter(visible);
            const overlay = overlays.slice(-1)[0];
            const text = overlay ? clean(overlay.innerText || overlay.textContent) : "";
            return text.includes("添加扩展")
                && text.includes(expectedName)
                && text.includes(expectedGroup)
                && text.includes("确定");
        }}
        """

    def _dropdown_item_script(self, text: str) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return Array.from(document.querySelectorAll({self.locator("dropdown_item")!r}))
                .filter(visible)
                .find((item) => clean(item.innerText || item.textContent) === expectedText) || null;
        }}
        """

    def _extension_exists_script(self, name: str) -> str:
        return f"""
        () => Boolean(({self._extension_card_script(name)})())
        """

    def _extension_exact_name_exists_script(self, name: str) -> str:
        return f"""
        () => {{
            const card = ({self._extension_card_script(name)})();
            if (!card) return false;
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
            const nodes = Array.from(card.querySelectorAll("span, div, button")).filter(visible);
            const providerLabelIndex = nodes.findIndex((item) => clean(item.innerText || item.textContent) === "提供方:");
            if (providerLabelIndex < 0) return false;
            return nodes.slice(0, providerLabelIndex)
                .map((item) => clean(item.innerText || item.textContent))
                .some((text) => text === expectedName);
        }}
        """

    def _extension_with_description_exists_script(self, name: str, description: str) -> str:
        return f"""
        () => {{
            const card = ({self._extension_card_script(name)})();
            if (!card) return false;
            const expectedDescription = {description!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const text = clean(card.innerText || card.textContent);
            return text.includes(expectedDescription);
        }}
        """

    def _extension_card_switch_script(self, name: str) -> str:
        return f"""
        () => {{
            const card = ({self._extension_card_script(name)})();
            if (!card) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            return Array.from(card.querySelectorAll(".el-switch")).find(visible) || null;
        }}
        """

    def _extension_card_switch_checked_script(self, name: str) -> str:
        return f"""
        () => {{
            const switchEl = ({self._extension_card_switch_script(name)})();
            if (!switchEl) return false;
            return switchEl.classList.contains("is-checked")
                || switchEl.getAttribute("aria-checked") === "true"
                || Boolean(switchEl.querySelector("input:checked"));
        }}
        """

    def _extension_card_script(self, name: str) -> str:
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
            const cards = Array.from(document.querySelectorAll({self.locator("extension_card")!r}))
                .filter(visible);
            const nameCandidates = (card) => {{
                const nodes = Array.from(card.querySelectorAll("span, div, button")).filter(visible);
                const providerLabelIndex = nodes.findIndex((item) => clean(item.innerText || item.textContent) === "提供方:");
                if (providerLabelIndex < 0) return [];
                return nodes.slice(0, providerLabelIndex)
                    .map((item) => clean(item.innerText || item.textContent))
                    .filter((text) => text && !text.includes("提供方:") && text !== "删除");
            }};
            return cards.find((card) => nameCandidates(card).some((text) => text === expectedName))
                || cards.find((card) => {{
                const text = clean(card.innerText || card.textContent);
                return text.includes("提供方:") && text.split("提供方:", 1)[0].includes(expectedName);
            }}) || cards.find((card) => clean(card.innerText || card.textContent).includes(expectedName)) || null;
        }}
        """

    def _extension_card_details_script(self, name: str) -> str:
        return f"""
        () => {{
            const card = ({self._extension_card_script(name)})();
            if (!card) return {{}};
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
            const spans = Array.from(card.querySelectorAll("span, div, button")).filter(visible);
            const providerLabelIndex = spans.findIndex((item) => clean(item.innerText || item.textContent) === "提供方:");
            let provider = "";
            let actualName = "";
            let nameNode = null;
            if (providerLabelIndex >= 0) {{
                const candidateNodes = spans.slice(0, providerLabelIndex)
                    .filter((item) => {{
                        const text = clean(item.innerText || item.textContent);
                        return text && !text.includes("提供方:") && text !== "删除";
                    }});
                const nameCandidates = candidateNodes.map((item) => clean(item.innerText || item.textContent));
                actualName = nameCandidates.find((text) => text === expectedName) || "";
                nameNode = candidateNodes.find(
                    (item) => clean(item.innerText || item.textContent) === actualName
                ) || null;
                if (!actualName) {{
                    const containsExpected = nameCandidates
                        .filter((text) => text.includes(expectedName))
                        .sort((left, right) => left.length - right.length);
                    actualName = containsExpected[0] || nameCandidates[nameCandidates.length - 1] || "";
                    nameNode = candidateNodes.find(
                        (item) => clean(item.innerText || item.textContent) === actualName
                    ) || null;
                }}
                for (const item of spans.slice(providerLabelIndex + 1)) {{
                    const text = clean(item.innerText || item.textContent);
                    if (text && text !== "提供方:") {{
                        provider = text;
                        break;
                    }}
                }}
            }}
            const raw = clean(card.innerText || card.textContent);
            if (!actualName && raw.includes("提供方:")) {{
                actualName = clean(raw.split("提供方:", 1)[0]);
            }}
            const metadataRoot = nameNode?.parentElement || null;
            const metadataTexts = Array.from(metadataRoot?.children || [])
                .map((item) => clean(item.innerText || item.textContent))
                .filter(Boolean);
            const version = metadataTexts.find(
                (text) => text !== actualName
                    && /^v?[0-9]+(?:[.][0-9]+)+(?:[-+][A-Za-z0-9_.-]+)?$/i.test(text)
            ) || "";
            const group = metadataTexts.find((text) => text.startsWith("分组:")) || "";
            const description = clean(
                Array.from(card.querySelectorAll("p"))
                    .filter(visible)
                    .map((item) => clean(item.innerText || item.textContent))
                    .find(Boolean) || ""
            );
            return {{
                name: actualName,
                version,
                description,
                group,
                provider,
                raw,
            }};
        }}
        """

    def _confirm_if_present(self, timeout_seconds: int | None = None) -> bool:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            clicked = bool(self.cdp.evaluate(self._confirm_button_if_present_script()))
            if clicked:
                self._wait_for_message_box_closed(timeout_seconds=20)
                return True
            time.sleep(0.2)
        return False

    def _confirm_button_if_present_script(self) -> str:
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
            const overlays = Array.from(document.querySelectorAll(".el-message-box, .el-dialog")).filter(visible);
            for (const overlay of overlays.reverse()) {{
                const text = clean(overlay.innerText || overlay.textContent);
                if (!text.includes("确定")) continue;
                const button = Array.from(overlay.querySelectorAll({self.locator("button")!r}))
                    .filter(visible)
                    .find((item) => clean(item.innerText || item.textContent) === "确定");
                if (button) {{
                    button.click();
                    return true;
                }}
            }}
            return false;
        }}
        """

    def _wait_for_message_box_closed(self, timeout_seconds: int) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.cdp.evaluate(
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
                    return Array.from(document.querySelectorAll(".el-message-box")).some(visible);
                }
                """
            ):
                return
            time.sleep(0.2)
        raise TimeoutError("message box did not close")

    def _extension_card_more_button_script(self, name: str) -> str:
        return f"""
        () => {{
            const card = ({self._extension_card_script(name)})();
            if (!card) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const dropdown = Array.from(card.querySelectorAll({self.locator("card_dropdown")!r})).find(visible);
            if (dropdown) return dropdown;
            const candidates = Array.from(card.querySelectorAll("button, [role='button'], i, svg"))
                .filter(visible);
            return candidates[0] || null;
        }}
        """

    def _extension_list_visible_script(self) -> str:
        return """
        () => {
            const route = String(window.location.hash || "").split("?")[0].replace(/\\/+$/, "");
            const text = document.body.innerText || document.body.textContent || "";
            return route === "#/expansion"
                && text.includes("扩展管理")
                && text.includes("添加扩展")
                && text.includes("扩展市场");
        }
        """

    def _loading_visible_script(self) -> str:
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

    def _extension_list_state_script(self) -> str:
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
            const loading = Array.from(document.querySelectorAll(".el-loading-mask")).some(visible);
            const cards = Array.from(document.querySelectorAll({self.locator("extension_card")!r}))
                .filter(visible)
                .map((card) => clean(card.innerText || card.textContent));
            const bodyText = clean(document.body?.innerText || document.body?.textContent || "");
            const empty = bodyText.includes("暂无数据") || bodyText.includes("暂无扩展");
            return {{
                loading,
                signature: JSON.stringify({{ cards, empty }}),
                card_count: cards.length,
            }};
        }}
        """

    def _add_extension_dialog_visible_script(self) -> str:
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
                .some((dialog) => text(dialog).includes("添加扩展") && text(dialog).includes("添加方式"));
        }
        """

    def _edit_extension_dialog_visible_script(self) -> str:
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
            return Array.from(document.querySelectorAll(".el-dialog"))
                .filter(visible)
                .some((dialog) => {
                    const text = clean(dialog.innerText || dialog.textContent);
                    return text.includes("编辑扩展") && text.includes("确定");
                });
        }
        """

    def _local_package_mode_visible_script(self) -> str:
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
            const dialogs = Array.from(document.querySelectorAll(".el-dialog")).filter(visible);
            for (const dialog of dialogs.reverse()) {
                const text = clean(dialog.innerText || dialog.textContent);
                if (!text.includes("添加扩展") || !text.includes("安装包")) continue;
                const localSelected = Array.from(dialog.querySelectorAll(".el-radio-button, label"))
                    .filter(visible)
                    .some((item) => {
                        const itemText = clean(item.innerText || item.textContent);
                        return itemText === "安装包"
                            && (item.classList.contains("is-active") || Boolean(item.querySelector("input:checked")));
                    });
                const fileInputs = Array.from(dialog.querySelectorAll("input[type='file']"));
                const hasZipInput = fileInputs.some((input) => {
                    const accept = String(input.getAttribute("accept") || "").toLowerCase();
                    return accept.includes("zip");
                });
                const hasZipUploadText = text.includes("将 ZIP 文件") || text.includes("仅支持 ZIP 格式");
                const hasNameField = text.includes("扩展名称") || Boolean(
                    Array.from(dialog.querySelectorAll("input"))
                        .some((input) => String(input.getAttribute("placeholder") || "").includes("扩展名称"))
                );
                if (localSelected && hasZipInput && hasZipUploadText && hasNameField) return true;
            }
            return false;
        }
        """

    def _delete_extension_dialog_visible_script(self) -> str:
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
                    return text.includes("删除") && text.includes("确定");
                });
        }
        """
