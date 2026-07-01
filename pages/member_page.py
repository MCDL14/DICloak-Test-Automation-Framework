from __future__ import annotations

import json
import time
from pathlib import Path

from core.config import timeout_seconds as config_timeout_seconds
from core.ui_driver import UIDriver
from pages.base_page import BasePage


class MemberPage(BasePage):
    locator_file = "member_locators.yaml"

    def recover_to_module_home(self) -> None:
        self.open_list()
        self.dismiss_blocking_overlays()

    def open_list(self) -> None:
        self.dismiss_blocking_overlays()
        self._expand_team_management_if_needed()
        self.cdp.click_element_by_script(self._visible_menu_item_script("成员列表"))
        self._wait_for_member_list()

    def open_member_edit_dialog(self, member_name: str) -> None:
        self.cdp.click_element_by_script(self._member_row_edit_button_script(member_name))
        self._wait_for_edit_member_dialog(member_name)

    def rename_member(self, current_name: str, new_name: str, supervisor: str = "") -> None:
        self.open_member_edit_dialog(current_name)
        self.cdp.fill_element_by_script(self._dialog_input_by_label_script("成员名称"), new_name)
        if supervisor and self.cdp.evaluate(self._dialog_select_label_exists_script("上级经理")):
            self._select_dialog_option_by_label("上级经理", supervisor)
        self.cdp.click_element_by_script(self._active_dialog_button_script("确定"))
        self._wait_for_overlay_closed()
        self.wait_member_visible(new_name)
        self.wait_member_absent(current_name)

    def create_external_member(
        self,
        member_name: str,
        member_group: str,
        email: str,
        environment_group: str,
        identity: str,
        supervisor: str = "",
    ) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_text_button_script("创建成员"))
        self.cdp.click_element_by_script(self._create_member_type_card_button_script("外部成员", "创建"))
        self._wait_for_create_external_member_dialog()
        self.cdp.fill_element_by_script(self._dialog_input_by_label_script("成员名称"), member_name)
        self._select_dialog_option_by_label("成员分组", member_group)
        self.cdp.fill_element_by_script(self._dialog_input_by_label_script("成员邮箱"), email)
        self._select_dialog_option_by_label("环境分组", environment_group)
        if not self.cdp.evaluate(self._click_dialog_radio_by_label_script("成员身份", identity)):
            raise TimeoutError(f"member identity radio was not clicked: {identity}")
        if supervisor:
            self._select_dialog_option_by_label("上级经理", supervisor)
        self._disable_expiration_switch_if_enabled()
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()
        self.wait_member_visible(member_name)

    def create_internal_member(
        self,
        member_name: str,
        member_group: str,
        login_account: str,
        login_password: str,
        environment_group: str,
        identity: str,
        supervisor: str = "",
    ) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_text_button_script("创建成员"))
        self.cdp.click_element_by_script(self._create_member_type_card_button_script("内部成员", "创建"))
        self._wait_for_create_internal_member_dialog()
        self.cdp.fill_element_by_script(self._dialog_input_by_label_script("成员名称"), member_name)
        self.cdp.fill_element_by_script(self._dialog_input_by_label_script("登录账号"), login_account)
        self.cdp.fill_element_by_script(self._dialog_input_by_label_script("登录密码"), login_password)
        self._select_dialog_option_by_label("成员分组", member_group)
        self._select_dialog_option_by_label("环境分组", environment_group)
        if not self.cdp.evaluate(self._click_dialog_radio_by_label_script("成员身份", identity)):
            raise TimeoutError(f"member identity radio was not clicked: {identity}")
        if supervisor:
            self._select_dialog_option_by_label("上级经理", supervisor)
        self._disable_expiration_switch_if_enabled()
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._close_internal_member_success_dialog_if_present()
        self._wait_for_overlay_closed()
        self.wait_member_visible(member_name)

    def delete_member(self, member_name: str) -> None:
        self.cdp.click_element_by_script(self._member_row_delete_button_script(member_name))
        self.confirm_secondary_dialog()
        self.wait_member_absent(member_name)

    def delete_member_if_exists(self, member_name: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "search_result_seconds", 10)
        while time.time() < deadline:
            if not self.member_visible(member_name):
                return
            self.delete_member(member_name)
            time.sleep(0.3)
        if self.member_visible(member_name):
            raise TimeoutError(f"member still exists after cleanup: {member_name}")

    def member_visible(self, member_name: str) -> bool:
        return bool(self.cdp.evaluate(self._member_exists_script(member_name)))

    def member_row_details(self, member_name: str) -> dict[str, str]:
        value = self.cdp.evaluate(self._member_row_details_script(member_name))
        if not isinstance(value, dict):
            return {}
        return {str(key): str(item or "").strip() for key, item in value.items()}

    def filter_by_member_group(self, group_name: str) -> None:
        clean_name = str(group_name or "").strip()
        if not clean_name:
            raise ValueError("member group filter name is empty")
        self.cdp.click_element_by_script(self._member_group_filter_select_script())
        self.cdp.click_element_by_script(self._select_dropdown_item_script(clean_name))
        self.wait_member_group_filter_result(clean_name)

    def filter_by_member_name_or_id(self, keyword: str) -> None:
        clean_keyword = str(keyword or "").strip()
        if not clean_keyword:
            raise ValueError("member name/id filter keyword is empty")
        self.cdp.fill_element_by_script(self._member_name_id_filter_input_script(), clean_keyword)
        self.cdp.click_element_by_script(self._search_filter_button_script())
        self.wait_member_name_id_filter_result(clean_keyword)

    def filter_by_remark(self, remark: str) -> None:
        clean_remark = str(remark or "").strip()
        if not clean_remark:
            raise ValueError("member remark filter keyword is empty")
        self.cdp.click_element_by_script(self._more_filter_button_script())
        self._wait_for_filter_drawer_visible()
        self.cdp.fill_element_by_script(self._filter_drawer_input_by_label_script("备注"), clean_remark)
        self.cdp.click_element_by_script(self._filter_drawer_button_script("立即筛选"))
        self._wait_for_filter_drawer_closed()
        self.wait_member_remark_filter_result(clean_remark)

    def filter_by_login_account_or_email(self, keyword: str) -> None:
        clean_keyword = str(keyword or "").strip()
        if not clean_keyword:
            raise ValueError("member login account/email filter keyword is empty")
        self.cdp.click_element_by_script(self._more_filter_button_script())
        self._wait_for_filter_drawer_visible()
        self.cdp.fill_element_by_script(self._filter_drawer_input_by_label_script("登录账号/邮箱"), clean_keyword)
        self.cdp.click_element_by_script(self._filter_drawer_button_script("立即筛选"))
        self._wait_for_filter_drawer_closed()
        self.wait_member_login_account_email_filter_result(clean_keyword)

    def clear_filters(self) -> None:
        # 仅在存在"清除筛选"按钮时才点击，避免无筛选状态误触发超时异常
        if not bool(self.cdp.evaluate(self._clear_filter_button_script())):
            return
        self.cdp.click_element_by_script(self._clear_filter_button_script())
        self.wait_member_filters_cleared()

    def member_name_id_values_in_current_list(self) -> list[dict[str, str]]:
        return [
            {
                "name": value["name"],
                "id": value["id"],
                "raw": value["raw"],
            }
            for value in self._member_records_in_current_list()
        ]

    def member_names_in_current_list(self) -> list[str]:
        return [
            value["name"]
            for value in self.member_name_id_values_in_current_list()
            if str(value.get("name") or "").strip()
        ]

    def _member_records_in_current_list(self) -> list[dict[str, str]]:
        visible_rows = self.cdp.evaluate(self._member_visible_rows_script())
        api_rows = self.cdp.evaluate(self._member_api_records_script())
        if not isinstance(visible_rows, list):
            return []
        api_records = self._normalize_member_api_records(api_rows if isinstance(api_rows, list) else [])
        result: list[dict[str, str]] = []
        for row in visible_rows:
            if not isinstance(row, dict):
                continue
            visible_record = {
                "id": str(row.get("id") or "").strip(),
                "name": str(row.get("name") or "").strip(),
                "raw": str(row.get("raw") or "").strip(),
                "remark": str(row.get("remark") or "").strip(),
                "created_time": str(row.get("created_time") or "").strip(),
                "text": str(row.get("text") or "").strip(),
            }
            matched_record = self._match_member_api_record(visible_record, api_records)
            if matched_record:
                visible_record["id"] = matched_record["id"]
                visible_record["name"] = visible_record["name"] or matched_record["name"]
                visible_record["remark"] = matched_record["remark"]
                visible_record["created_time"] = visible_record["created_time"] or matched_record["created_time"]
            result.append(visible_record)
        return result

    def _member_record_by_id_in_current_list(self, member_id: str) -> dict[str, str] | None:
        clean_id = str(member_id or "").strip()
        if not clean_id:
            return None
        for record in self._member_records_in_current_list():
            if record.get("id") == clean_id:
                return record
        return None

    def _member_api_record_by_id(self, member_id: str) -> dict[str, str] | None:
        clean_id = str(member_id or "").strip()
        if not clean_id:
            return None
        api_rows = self.cdp.evaluate(self._member_api_records_script())
        if not isinstance(api_rows, list):
            return None
        for record in self._normalize_member_api_records(api_rows):
            if record["id"] == clean_id:
                return record
        return None

    def _normalize_member_api_records(self, rows: list[object]) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            records.append(
                {
                    "id": str(row.get("id") or "").strip(),
                    "name": str(row.get("name") or "").strip(),
                    "remark": self._member_list_display_value(row.get("remark")),
                    "created_time": str(row.get("create_time") or "").strip(),
                    "creator": str(row.get("create_by_name") or "").strip(),
                    "email": str(row.get("email") or "").strip(),
                    "raw": str(row.get("name") or "").strip(),
                }
            )
        return records

    def _match_member_api_record(
        self,
        visible_record: dict[str, str],
        api_records: list[dict[str, str]],
    ) -> dict[str, str] | None:
        visible_id = visible_record.get("id", "")
        if visible_id:
            matched_by_id = [record for record in api_records if record["id"] == visible_id]
            if len(matched_by_id) == 1:
                return matched_by_id[0]

        name = visible_record.get("name", "")
        if not name:
            return None
        candidates = [record for record in api_records if record["name"] == name]
        if len(candidates) == 1:
            return candidates[0]

        remark = visible_record.get("remark", "")
        if remark:
            remark_matches = [record for record in candidates if record["remark"] == remark]
            if len(remark_matches) == 1:
                return remark_matches[0]
            if remark_matches:
                candidates = remark_matches

        created_time = visible_record.get("created_time", "")
        if created_time:
            created_matches = [record for record in candidates if record["created_time"] == created_time]
            if len(created_matches) == 1:
                return created_matches[0]
            if created_matches:
                candidates = created_matches

        return None

    def _member_list_display_value(self, value: object) -> str:
        text = str(value or "").strip()
        return text if text else "--"

    def member_id_by_exact_name(self, member_name: str) -> str:
        clean_name = str(member_name or "").strip()
        if not clean_name:
            raise ValueError("member name is empty")
        self.filter_by_member_name_or_id(clean_name)
        for value in self.member_name_id_values_in_current_list():
            if value["name"] == clean_name and value["id"]:
                return value["id"]
        raise TimeoutError(f"member id was not found by exact name: {clean_name}")

    def member_remark_values_in_current_list(self) -> list[str]:
        values = self.cdp.evaluate(self._member_remark_values_in_current_list_script())
        if not isinstance(values, list):
            return []
        return [str(value).strip() for value in values if str(value or "").strip()]

    def member_group_values_in_current_list(self) -> list[str]:
        values = self.cdp.evaluate(self._member_group_values_in_current_list_script())
        if not isinstance(values, list):
            return []
        return [str(value).strip() for value in values if str(value or "").strip()]

    def wait_member_visible(self, member_name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.member_visible(member_name):
                return
            time.sleep(0.3)
        raise TimeoutError(f"member did not appear in list: {member_name}")

    def wait_member_absent(self, member_name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.member_visible(member_name):
                return
            time.sleep(0.3)
        raise TimeoutError(f"member still exists in list: {member_name}")

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

    def edit_dialog_field_value(self, field_label: str) -> str:
        return str(self.cdp.evaluate(self._dialog_field_value_script(field_label)) or "").strip()

    def close_active_dialog(self) -> None:
        self.cdp.click_element_by_script(self._active_overlay_button_script("取消"))
        self._wait_for_overlay_closed()

    # ── 批量操作 ──────────────────────────────────────────────────────────

    def member_ids_by_remark(self, remark: str) -> list[str]:
        clean_remark = str(remark or "").strip()
        return [
            value["id"]
            for value in self._member_records_in_current_list()
            if value["id"] and value["remark"] == clean_remark
        ]

    def member_remark_values_by_ids(self, member_ids: list[str]) -> dict[str, str]:
        expected_ids = {str(member_id).strip() for member_id in member_ids if str(member_id or "").strip()}
        return {
            value["id"]: value["remark"]
            for value in self._member_records_in_current_list()
            if value["id"] in expected_ids
        }

    def select_visible_members_by_ids(self, member_ids: list[str]) -> None:
        self.open_list()
        self.clear_filters()
        self.clear_selected_members()
        records_by_id = {value["id"]: value for value in self._member_records_in_current_list() if value["id"]}
        for member_id in member_ids:
            clean_id = str(member_id or "").strip()
            record = records_by_id.get(clean_id)
            if not record:
                raise TimeoutError(f"member row was not found by id in current list: {clean_id}")
            self.cdp.click_element_by_script(self._member_checkbox_by_record_script(record))
        self._wait_member_selected_count(len(member_ids))
        self.wait_batch_more_operation_visible()

    def select_members_by_ids(self, member_ids: list[str]) -> None:
        self.select_visible_members_by_ids(member_ids)

    def clear_selected_members(self) -> None:
        for _ in range(5):
            selected_count = self._selected_member_count()
            if selected_count == 0:
                return
            self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    const checked = Array.from(document.querySelectorAll(".el-checkbox.is-checked"))
                        .filter((el) => visible(el) && !el.closest("thead"));
                    for (const checkbox of checked) {
                        checkbox.click();
                    }
                }
                """
            )
            time.sleep(0.3)
        if self._selected_member_count() != 0:
            raise TimeoutError("selected members were not cleared")

    def batch_edit_remark(self, modify_mode: str, remark_content: str) -> None:
        self.cdp.hover_element_by_script(self._batch_more_operation_script())
        self.cdp.click_element_by_script(self._batch_menu_item_script("编辑备注"))
        self._wait_batch_edit_remark_dialog_visible()
        self.cdp.click_element_by_script(self._batch_remark_modify_mode_script(modify_mode))
        self._wait_batch_remark_modify_mode_selected(modify_mode)
        self.cdp.fill_element_by_script(self._batch_remark_input_script(), remark_content)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()

    def wait_member_remarks_by_ids(
        self,
        member_ids: list[str],
        expected_remark: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            remark_values = self.member_remark_values_by_ids(member_ids)
            if remark_values and all(remark == expected_remark for remark in remark_values.values()):
                return
            time.sleep(0.3)
        raise TimeoutError(
            "member remark values did not match expected: "
            f"expected={expected_remark}, actual={self.member_remark_values_by_ids(member_ids)}"
        )

    # ── 批量操作结束 ──────────────────────────────────────────────────────

    def select_members_by_names(self, member_names: list[str]) -> None:
        self.clear_selected_members()
        for name in member_names:
            self.cdp.click_element_by_script(self._member_checkbox_by_name_script(name))
        self._wait_member_selected_count(len(member_names))
        self.wait_batch_more_operation_visible()

    def wait_batch_more_operation_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._batch_more_operation_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("member batch more-operation menu was not visible")

    def open_export_selected_members_dialog(self) -> None:
        # 顶部批量工具栏"更多操作"里先展开"导出成员"，再点击二级菜单"导出所选"。
        # 点击"导出所选"后直接触发下载，没有 .el-dialog 确认弹窗。
        self._click_batch_nested_menu_item("导出成员", "导出所选")

    def export_selected_members_and_save_download(
        self,
        file_path: str | Path,
        timeout_seconds: int | None = None,
    ) -> str:
        # 一次性完成：hover 更多操作 → hover 导出成员 → click 导出所选 → 捕获 Chromium 下载事件并保存。
        # 因为点击"导出所选"后直接触发下载，不存在 .el-dialog 确认步骤，所以整个过程必须在一个连续流程中完成。
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "batch_export_seconds", 120)
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cdp._page().expect_download(timeout=timeout_seconds * 1000) as download_info:
            self._click_batch_nested_menu_item("导出成员", "导出所选")
        download = download_info.value
        suggested_filename = download.suggested_filename
        download.save_as(str(file_path))
        return suggested_filename

    def export_selected_members_via_save_dialog(
        self,
        file_path: str | Path,
    ) -> None:
        # 当 Chromium 下载事件未触发时，回退到 Windows 系统保存弹窗的 UI 自动化。
        self._click_batch_nested_menu_item("导出成员", "导出所选")
        ui_driver = UIDriver(self.config, self.logger)
        ui_driver.save_file_in_dialog(file_path, timeout=15)

    # ── 导出成员结束 ──────────────────────────────────────────────────────

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

    def wait_member_group_filter_result(self, group_name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            group_values = self.member_group_values_in_current_list()
            if group_values and all(value == group_name for value in group_values):
                return
            time.sleep(0.3)
        raise TimeoutError(
            "member group filter result did not match expected group: "
            f"expected={group_name}, actual={self.member_group_values_in_current_list()}"
        )

    def wait_member_name_id_filter_result(self, keyword: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        clean_keyword = str(keyword).strip()
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            name_id_values = self.member_name_id_values_in_current_list()
            if clean_keyword.isdigit():
                if name_id_values and all(value["id"] == clean_keyword for value in name_id_values):
                    return
            elif name_id_values and all(clean_keyword in value["name"] for value in name_id_values):
                return
            time.sleep(0.3)
        raise TimeoutError(
            "member name/id filter result did not match expected keyword: "
            f"keyword={clean_keyword}, actual={self.member_name_id_values_in_current_list()}"
        )

    def wait_member_remark_filter_result(self, remark: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        clean_remark = str(remark).strip()
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            remark_values = self.member_remark_values_in_current_list()
            if remark_values and all(clean_remark in value for value in remark_values):
                return
            time.sleep(0.3)
        raise TimeoutError(
            "member remark filter result did not match expected keyword: "
            f"keyword={clean_remark}, actual={self.member_remark_values_in_current_list()}"
        )

    def wait_member_login_account_email_filter_result(self, keyword: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            member_names = self.member_names_in_current_list()
            if member_names:
                return
            time.sleep(0.3)
        raise TimeoutError(f"member login account/email filter returned no rows: {keyword}")

    def wait_member_filters_cleared(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._member_group_filter_empty_script()) and self.cdp.evaluate(
                self._member_name_id_filter_empty_script()
            ):
                return
            time.sleep(0.3)
        raise TimeoutError("member list filters were not cleared")

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

    def _wait_for_filter_drawer_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._filter_drawer_visible_script()):
                return
            time.sleep(0.2)
        raise RuntimeError("member more-filter drawer did not appear")

    def _wait_for_filter_drawer_closed(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.cdp.evaluate(self._filter_drawer_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("member more-filter drawer did not close")

    def _wait_for_edit_member_dialog(self, member_name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._edit_member_dialog_visible_script(member_name)):
                return
            time.sleep(0.2)
        raise RuntimeError(f"edit member dialog did not appear: {member_name}")

    def _wait_for_create_external_member_dialog(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._create_external_member_dialog_visible_script()):
                return
            time.sleep(0.2)
        raise RuntimeError("create external member dialog did not appear")

    def _wait_for_create_internal_member_dialog(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._create_internal_member_dialog_visible_script()):
                return
            time.sleep(0.2)
        raise RuntimeError("create internal member dialog did not appear")

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

    def _select_dialog_option_by_label(self, field_label: str, option_text: str) -> None:
        self.cdp.click_element_by_script(self._dialog_select_control_by_label_script(field_label))
        try:
            self.cdp.click_element_by_script(self._select_dropdown_item_script(option_text), timeout=1500)
        except Exception:
            self.cdp.fill_element_by_script(self._dialog_select_input_by_label_script(field_label), option_text)
            self.cdp.click_element_by_script(self._select_dropdown_item_script(option_text))

    def _member_group_filter_select_script(self) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
            return Array.from(document.querySelectorAll(__FILTER_SELECT_SELECTOR__))
                .filter(visible)
                .find((el) => clean(el.innerText || el.textContent).includes("成员分组")) || null;
        }
        """.replace("__FILTER_SELECT_SELECTOR__", repr(self.locator("filter_select_control")))

    def _member_name_id_filter_input_script(self) -> str:
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
            return Array.from(document.querySelectorAll(__FILTER_INPUT_SELECTOR__))
                .filter(visible)
                .find((input) => String(input.getAttribute("placeholder") || "").includes("成员名称/ID")) || null;
        }
        """.replace("__FILTER_INPUT_SELECTOR__", repr(self.locator("filter_input")))

    def _search_filter_button_script(self) -> str:
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
            return Array.from(document.querySelectorAll(__BUTTON_SELECTOR__))
                .filter(visible)
                .find((button) => button.querySelector(__SEARCH_FILTER_ICON_SELECTOR__)) || null;
        }
        """.replace("__BUTTON_SELECTOR__", repr(self.locator("button"))).replace(
            "__SEARCH_FILTER_ICON_SELECTOR__",
            repr(self.locator("search_filter_icon")),
        )

    def _more_filter_button_script(self) -> str:
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
            const input = Array.from(document.querySelectorAll(__FILTER_INPUT_SELECTOR__))
                .filter(visible)
                .find((item) => String(item.getAttribute("placeholder") || "").includes("成员名称/ID"));
            if (!input) return null;
            const inputRect = input.getBoundingClientRect();
            const buttons = Array.from(document.querySelectorAll(__BUTTON_SELECTOR__))
                .filter(visible)
                .map((button) => ({ button, rect: button.getBoundingClientRect() }))
                .filter((item) => item.rect.x >= inputRect.x + inputRect.width)
                .filter((item) => Math.abs(item.rect.y - inputRect.y) < 30)
                .sort((left, right) => left.rect.x - right.rect.x);
            return buttons[1]?.button || null;
        }
        """.replace("__FILTER_INPUT_SELECTOR__", repr(self.locator("filter_input"))).replace(
            "__BUTTON_SELECTOR__",
            repr(self.locator("button")),
        )

    def _clear_filter_button_script(self) -> str:
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
            return Array.from(document.querySelectorAll(__BUTTON_SELECTOR__))
                .filter(visible)
                .find((button) => button.querySelector(__CLEAR_FILTER_ICON_SELECTOR__)) || null;
        }
        """.replace("__BUTTON_SELECTOR__", repr(self.locator("button"))).replace(
            "__CLEAR_FILTER_ICON_SELECTOR__",
            repr(self.locator("clear_filter_icon")),
        )

    def _filter_drawer_visible_script(self) -> str:
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
            return Array.from(document.querySelectorAll(__DRAWER_SELECTOR__))
                .filter(visible)
                .some((drawer) => (drawer.innerText || drawer.textContent || "").includes("更多筛选")
                    && (drawer.innerText || drawer.textContent || "").includes("立即筛选"));
        }
        """.replace("__DRAWER_SELECTOR__", repr(self.locator("drawer")))

    def _filter_drawer_input_by_label_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const drawers = Array.from(document.querySelectorAll({self.locator("drawer")!r}))
                .filter((drawer) => visible(drawer) && (drawer.innerText || "").includes("更多筛选"));
            for (const drawer of drawers.reverse()) {{
                const formItems = Array.from(drawer.querySelectorAll({self.locator("form_item")!r})).filter(visible);
                for (const formItem of formItems) {{
                    const labels = Array.from(formItem.querySelectorAll("label, .el-form-item__label")).filter(visible);
                    const matched = labels.some((label) => clean(label.innerText || label.textContent) === clean(expectedLabel));
                    if (!matched) continue;
                    const input = Array.from(formItem.querySelectorAll("input, textarea"))
                        .filter(visible)
                        .find((item) => !item.disabled && !item.readOnly);
                    if (input) return input;
                }}
            }}
            return null;
        }}
        """

    def _filter_drawer_button_script(self, text: str) -> str:
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
            const drawers = Array.from(document.querySelectorAll({self.locator("drawer")!r}))
                .filter((drawer) => visible(drawer) && (drawer.innerText || "").includes("更多筛选"));
            for (const drawer of drawers.reverse()) {{
                const button = Array.from(drawer.querySelectorAll({self.locator("button")!r}))
                    .filter(visible)
                    .find((item) => (item.innerText || item.textContent || "").trim() === expectedText);
                if (button) return button;
            }}
            return null;
        }}
        """

    def _disable_expiration_switch_if_enabled(self) -> None:
        if self.cdp.evaluate(self._dialog_switch_enabled_script("到期停用")):
            if not self.cdp.evaluate(self._click_dialog_switch_by_label_script("到期停用")):
                raise TimeoutError("expiration switch was not clicked")
            deadline = time.time() + config_timeout_seconds(self.config, "search_result_seconds", 10)
            while time.time() < deadline:
                if not self.cdp.evaluate(self._dialog_switch_enabled_script("到期停用")):
                    return
                time.sleep(0.2)
            raise TimeoutError("expiration switch was still enabled after click")

    def _close_internal_member_success_dialog_if_present(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._success_dialog_visible_script("创建成功")):
                self.cdp.click_element_by_script(self._active_overlay_button_script("关闭"))
                return
            if not self.cdp.evaluate(self._any_visible_overlay_script()):
                return
            time.sleep(0.2)

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

    def _expand_team_management_if_needed(self) -> None:
        if self.cdp.evaluate(self._visible_menu_item_exists_script("成员列表")):
            return
        self.cdp.click_element_by_script(self._visible_menu_item_script("团队管理"))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._visible_menu_item_exists_script("成员列表")):
                return
            time.sleep(0.2)
        raise TimeoutError("team management menu did not expand to show member list")

    def _visible_menu_item_exists_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const selector = {self.locator("member_menu_candidates")!r};
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

    def _create_member_type_card_button_script(self, card_text: str, button_text: str) -> str:
        return f"""
        () => {{
            const expectedCardText = {card_text!r};
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
            const overlays = Array.from(document.querySelectorAll({self.locator("create_member_type_popover")!r}))
                .filter(visible);
            for (const overlay of overlays.reverse()) {{
                const candidates = Array.from(overlay.querySelectorAll("div, section, article, li"))
                    .filter(visible)
                    .map((item) => ({{ item, text: clean(item.innerText || item.textContent) }}))
                    .filter((candidate) => candidate.text.includes(expectedCardText))
                    .sort((left, right) => {{
                        const leftOnlyTarget = left.text.includes(expectedCardText) && !left.text.includes("内部成员") ? 0 : 1;
                        const rightOnlyTarget = right.text.includes(expectedCardText) && !right.text.includes("内部成员") ? 0 : 1;
                        return leftOnlyTarget - rightOnlyTarget || left.text.length - right.text.length;
                    }});
                for (const candidate of candidates) {{
                    const button = Array.from(candidate.item.querySelectorAll({self.locator("button")!r}))
                        .filter(visible)
                        .find((el) => clean(el.innerText || el.textContent) === expectedButtonText);
                    if (button) return button;
                }}
            }}
            return null;
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const memberInfo = (row) => {{
                const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                    .filter(visible)
                    .map((header) => cleanCompact(header.innerText || header.textContent));
                let nameIndex = headers.findIndex((header) => header.includes("成员名称"));
                if (nameIndex < 0) nameIndex = 1;
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const raw = clean(cells[nameIndex]?.innerText || cells[nameIndex]?.textContent || "");
                const match = raw.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                return {{
                    name: match ? clean(match[1]) : raw,
                    id: match ? match[2] : "",
                }};
            }};
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            for (const row of rows) {{
                if (memberInfo(row).name !== expectedName) continue;
                const operationCell = Array.from(row.children).filter(visible).at(-1) || row;
                const editIcon = Array.from(operationCell.querySelectorAll({self.locator("edit_icon")!r}))
                    .filter(visible)
                    .sort((left, right) => left.getBoundingClientRect().x - right.getBoundingClientRect().x)[0];
                if (editIcon) return editIcon.closest("button, [role='button']") || editIcon;
            }}
            return null;
        }}
        """

    def _member_row_delete_button_script(self, member_name: str) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const memberInfo = (row) => {{
                const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                    .filter(visible)
                    .map((header) => cleanCompact(header.innerText || header.textContent));
                let nameIndex = headers.findIndex((header) => header.includes("成员名称"));
                if (nameIndex < 0) nameIndex = 1;
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const raw = clean(cells[nameIndex]?.innerText || cells[nameIndex]?.textContent || "");
                const match = raw.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                return {{
                    name: match ? clean(match[1]) : raw,
                    id: match ? match[2] : "",
                }};
            }};
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            for (const row of rows) {{
                if (memberInfo(row).name !== expectedName) continue;
                const operationCell = Array.from(row.children).filter(visible).at(-1) || row;
                const deleteIcon = Array.from(operationCell.querySelectorAll({self.locator("delete_icon")!r}))
                    .filter(visible)
                    .sort((left, right) => right.getBoundingClientRect().x - left.getBoundingClientRect().x)[0];
                if (deleteIcon) return deleteIcon.closest("button, [role='button']") || deleteIcon;

                const iconActions = Array.from(operationCell.querySelectorAll({self.locator("row_icon_action_candidates")!r}))
                    .filter(visible)
                    .map((el) => {{
                        const rect = el.getBoundingClientRect();
                        return {{
                            el: el.closest("button, [role='button']") || el,
                            x: rect.x,
                            area: rect.width * rect.height,
                        }};
                    }})
                    .filter((item) => item.area > 0)
                    .sort((left, right) => right.x - left.x);
                if (iconActions[0]) return iconActions[0].el;
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

    def _dialog_input_by_label_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
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
                const input = formItem ? Array.from(formItem.querySelectorAll("input")).find(visible) : null;
                if (input) return input;
            }}
            return null;
        }}
        """

    def _dialog_select_control_by_label_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
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
                const select = formItem?.querySelector({self.locator("select_control")!r});
                if (select && visible(select)) return select;
            }}
            return null;
        }}
        """

    def _dialog_select_input_by_label_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
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
                const input = formItem ? Array.from(formItem.querySelectorAll("input")).find(visible) : null;
                if (input) return input;
            }}
            return null;
        }}
        """

    def _dialog_select_label_exists_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const dialogs = Array.from(document.querySelectorAll({self.locator("dialog")!r})).filter(visible);
            return dialogs.some((dialog) => Array.from(dialog.querySelectorAll({self.locator("form_item")!r}))
                .filter(visible)
                .some((item) => clean(item.innerText || item.textContent).includes(clean(expectedLabel))));
        }}
        """

    def _dialog_radio_by_label_script(self, field_label: str, option_text: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const expectedOption = {option_text!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
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
                const radios = Array.from(formItem.querySelectorAll({self.locator("radio")!r}))
                    .filter(visible);
                const radio = radios.find((item) => clean(item.innerText || item.textContent) === clean(expectedOption)
                    || clean(item.innerText || item.textContent).includes(clean(expectedOption)));
                if (radio) return radio;
            }}
            return null;
        }}
        """

    def _click_dialog_radio_by_label_script(self, field_label: str, option_text: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const expectedOption = {option_text!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
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
                const radios = Array.from(formItem.querySelectorAll({self.locator("radio")!r}))
                    .filter(visible);
                const radio = radios.find((item) => clean(item.innerText || item.textContent) === clean(expectedOption)
                    || clean(item.innerText || item.textContent).includes(clean(expectedOption)));
                if (!radio) continue;
                const input = radio.querySelector("input");
                if (input && !input.checked) input.click();
                else radio.click();
                return true;
            }}
            return false;
        }}
        """

    def _dialog_switch_by_label_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
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
                const switchEl = formItem?.querySelector({self.locator("switch")!r});
                if (switchEl && visible(switchEl)) return switchEl;
            }}
            return null;
        }}
        """

    def _click_dialog_switch_by_label_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
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
                const switchEl = formItem?.querySelector({self.locator("switch")!r});
                if (!switchEl || !visible(switchEl)) continue;
                const input = switchEl.querySelector("input");
                if (input) input.click();
                else switchEl.click();
                return true;
            }}
            return false;
        }}
        """

    def _dialog_switch_enabled_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
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
                const switchEl = formItem?.querySelector({self.locator("switch")!r});
                if (!switchEl || !visible(switchEl)) continue;
                const input = switchEl.querySelector("input");
                return Boolean(switchEl.classList.contains("is-checked") || input?.checked);
            }}
            return false;
        }}
        """

    def _success_dialog_visible_script(self, title_text: str) -> str:
        return f"""
        () => {{
            const expectedTitle = {title_text!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            return Array.from(document.querySelectorAll({self.locator("blocking_overlay")!r}))
                .filter(visible)
                .some((overlay) => (overlay.innerText || overlay.textContent || "").includes(expectedTitle));
        }}
        """

    def _any_visible_overlay_script(self) -> str:
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

    def _dialog_field_value_script(self, field_label: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {field_label!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const cleanText = (value) => String(value || "").replace(/\\s+/g, " ").trim();
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
                const input = Array.from(formItem.querySelectorAll("input")).find(visible);
                if (input && String(input.value || input.getAttribute("value") || "").trim()) {{
                    return String(input.value || input.getAttribute("value") || "").trim();
                }}
                const selectedTexts = Array.from(formItem.querySelectorAll({self.locator("selected_text_candidates")!r}))
                    .filter(visible)
                    .map((el) => cleanText(el.innerText || el.textContent))
                    .filter((text) => text && text !== "×" && text !== expectedLabel);
                if (selectedTexts.length) return selectedTexts.join("、");
                return cleanText(formItem.innerText || formItem.textContent).replace(new RegExp("^" + expectedLabel + "\\\\s*"), "");
            }}
            return "";
        }}
        """

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

    def _member_group_values_in_current_list_script(self) -> str:
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
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => cleanCompact(header.innerText || header.textContent));
            let groupIndex = headers.findIndex((header) => header.includes("所属成员分组"));
            if (groupIndex < 0) groupIndex = 5;
            return Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .map((row) => {{
                    const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                    return clean(cells[groupIndex]?.innerText || cells[groupIndex]?.textContent || "");
                }})
                .filter(Boolean);
        }}
        """

    def _member_name_id_values_in_current_list_script(self) -> str:
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
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => cleanCompact(header.innerText || header.textContent));
            let nameIndex = headers.findIndex((header) => header.includes("成员名称"));
            if (nameIndex < 0) nameIndex = 1;
            return Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .map((row) => {{
                    const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                    const raw = clean(cells[nameIndex]?.innerText || cells[nameIndex]?.textContent || "");
                    const match = raw.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                    return {{
                        raw,
                        name: match ? clean(match[1]) : raw,
                        id: match ? match[2] : "",
                    }};
                }})
                .filter((item) => item.raw);
        }}
        """

    def _member_visible_rows_script(self) -> str:
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
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const parseNameId = (value) => {{
                const raw = clean(value);
                const match = raw.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                return {{
                    raw,
                    name: match ? clean(match[1]) : raw,
                    id: match ? match[2] : "",
                }};
            }};
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => cleanCompact(header.innerText || header.textContent));
            let nameIndex = headers.findIndex((header) => header.includes("鎴愬憳鍚嶇О"));
            if (nameIndex < 0) nameIndex = 1;
            let remarkIndex = headers.findIndex((header) => header === "澶囨敞");
            if (remarkIndex < 0) remarkIndex = 2;
            let createdIndex = headers.findIndex((header) => header.includes("鍒涘缓鏃堕棿"));
            if (createdIndex < 0) createdIndex = 12;
            return Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .map((row, rowIndex) => {{
                    const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                    const parsed = parseNameId(cells[nameIndex]?.innerText || cells[nameIndex]?.textContent || "");
                    return {{
                        id: parsed.id,
                        name: parsed.name,
                        raw: parsed.raw,
                        remark: clean(cells[remarkIndex]?.innerText || cells[remarkIndex]?.textContent || ""),
                        created_time: clean(cells[createdIndex]?.innerText || cells[createdIndex]?.textContent || ""),
                        text: clean(row.innerText || row.textContent || ""),
                        row_index: String(rowIndex),
                    }};
                }})
                .filter((item) => item.raw);
        }}
        """

    def _member_api_records_script(self) -> str:
        return """
        async () => {
            const parseJson = (value) => {
                try {
                    return JSON.parse(value || "{}");
                } catch (error) {
                    return {};
                }
            };
            const state = parseJson(localStorage.getItem("basic:state"));
            const token = String(state.token || "").trim();
            if (!token) return [];
            const url = "https://gin-server.dicloak.com/gin/v1/member?page_size=200&page_no=1&not_logged=false&detail=true";
            const response = await fetch(url, {
                headers: {
                    "Accept": "application/json, text/plain, */*",
                    "X-TOKEN": token,
                    "X-LANG": "zh_CN",
                    "X-Version": (document.title.match(/V(\\d+\\.\\d+\\.\\d+)/) || [])[1] || "",
                    "X-Platform": "APP",
                },
            });
            const payload = await response.json().catch(() => ({}));
            if (payload && payload.code === 0 && payload.data && Array.isArray(payload.data.list)) {
                return payload.data.list;
            }
            return [];
        }
        """

    def _member_remark_values_in_current_list_script(self) -> str:
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
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => cleanCompact(header.innerText || header.textContent));
            let remarkIndex = headers.findIndex((header) => header === "备注");
            if (remarkIndex < 0) remarkIndex = 2;
            return Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .map((row) => {{
                    const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                    return clean(cells[remarkIndex]?.innerText || cells[remarkIndex]?.textContent || "");
                }})
                .filter(Boolean);
        }}
        """

    def _member_group_filter_empty_script(self) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, "");
            const selects = Array.from(document.querySelectorAll({self.locator("filter_select_control")!r}))
                .filter(visible)
                .filter((el) => clean(el.innerText || el.textContent).includes("成员分组"));
            return selects.some((select) => {{
                const input = Array.from(select.querySelectorAll("input")).find(visible);
                const selectedTexts = Array.from(select.querySelectorAll({self.locator("filter_selected_text_candidates")!r}))
                    .filter(visible)
                    .map((el) => clean(el.innerText || el.textContent))
                    .filter((text) => text && text !== "×" && text !== "成员分组");
                const text = clean(select.innerText || select.textContent);
                const inputValue = input ? String(input.value || input.getAttribute("value") || "").trim() : "";
                return !inputValue && selectedTexts.length === 0 && text === "成员分组";
            }});
        }}
        """

    def _member_name_id_filter_empty_script(self) -> str:
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
            const input = Array.from(document.querySelectorAll({self.locator("filter_input")!r}))
                .filter(visible)
                .find((item) => String(item.getAttribute("placeholder") || "").includes("成员名称/ID"));
            return Boolean(input) && !String(input.value || input.getAttribute("value") || "").trim();
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
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => cleanCompact(header.innerText || header.textContent));
            let groupCellIndex = headers.findIndex((text) => text.includes("授权环境分组"));
            if (groupCellIndex < 0) groupCellIndex = headers.findIndex((text) => text === "环境分组");
            if (groupCellIndex < 0) groupCellIndex = 3;
            let nameIndex = headers.findIndex((header) => header.includes("成员名称"));
            if (nameIndex < 0) nameIndex = 1;
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            for (const row of rows) {{
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const nameText = clean(cells[nameIndex]?.innerText || cells[nameIndex]?.textContent || "");
                const match = nameText.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                const actualName = match ? clean(match[1]) : nameText;
                if (actualName !== expectedName) continue;
                const groupCell = cells[groupCellIndex] || cells[3] || null;
                if (!groupCell) return [];
                const text = clean(groupCell.innerText || groupCell.textContent);
                if (!text || text === "--") return [];
                return text.split(/[、,，\\n]+/).map((item) => clean(item)).filter(Boolean);
            }}
            return [];
        }}
        """

    def _member_exists_script(self, member_name: str) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => cleanCompact(header.innerText || header.textContent));
            let nameIndex = headers.findIndex((header) => header.includes("成员名称"));
            if (nameIndex < 0) nameIndex = 1;
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            return rows.some((row) => {{
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const nameCell = cells[nameIndex] || cells[1] || cells[0] || row;
                const nameText = clean(nameCell.innerText || nameCell.textContent || "");
                const match = nameText.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                return (match ? clean(match[1]) : nameText) === expectedName;
            }});
        }}
        """

    def _member_row_details_script(self, member_name: str) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => clean(header.innerText || header.textContent));
            const headerKeys = headers.map((header) => header.replace(/\\s+/g, ""));
            let nameIndex = headerKeys.findIndex((header) => header.includes("成员名称"));
            if (nameIndex < 0) nameIndex = 1;
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            for (const row of rows) {{
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const nameCell = cells[nameIndex] || cells[1] || cells[0] || row;
                const nameText = clean(nameCell.innerText || nameCell.textContent);
                const match = nameText.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                const actualName = match ? clean(match[1]) : nameText;
                if (actualName !== expectedName) continue;
                const detail = {{
                    id: match ? match[2] : "",
                    name: actualName,
                }};
                headers.forEach((header, index) => {{
                    if (!header) return;
                    detail[header] = clean(cells[index]?.innerText || cells[index]?.textContent || "");
                }});
                return detail;
            }}
            return {{}};
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
            const hasCreate = Array.from(document.querySelectorAll(__VISIBLE_TEXT_SELECTOR__))
                .some((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "创建成员");
            const hasTable = Array.from(document.querySelectorAll(__TABLE_CONTAINER_SELECTOR__)).some(visible);
            return bodyText.includes("成员列表") && (hasCreate || hasTable);
        }
        """.replace("__VISIBLE_TEXT_SELECTOR__", repr(self.locator("visible_text_candidates"))).replace(
            "__TABLE_CONTAINER_SELECTOR__",
            repr(self.locator("table_container")),
        )

    def _create_external_member_dialog_visible_script(self) -> str:
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
            return Array.from(document.querySelectorAll({self.locator("dialog")!r}))
                .filter(visible)
                .some((dialog) => {{
                    const text = dialog.innerText || dialog.textContent || "";
                    return text.includes("创建外部成员")
                        && text.includes("成员邮箱")
                        && text.includes("环境分组");
                }});
        }}
        """

    def _create_internal_member_dialog_visible_script(self) -> str:
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
            return Array.from(document.querySelectorAll({self.locator("dialog")!r}))
                .filter(visible)
                .some((dialog) => {{
                    const text = dialog.innerText || dialog.textContent || "";
                    return text.includes("创建内部成员")
                        && text.includes("登录账号")
                        && text.includes("登录密码")
                        && text.includes("环境分组");
                }});
        }}
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
                    return (text.includes("编辑内部成员") || text.includes("编辑外部成员"))
                        && text.includes("环境分组")
                        && inputValues.includes(expectedName);
                }});
        }}
        """

    # ── 批量操作私有脚本 ──────────────────────────────────────────────────

    def _member_ids_by_remark_script(self, remark: str) -> str:
        return f"""
        () => {{
            const expectedRemark = {remark!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => cleanCompact(header.innerText || header.textContent));
            let remarkIndex = headers.findIndex((header) => header === "备注");
            if (remarkIndex < 0) remarkIndex = 2;
            let nameIndex = headers.findIndex((header) => header.includes("成员名称"));
            if (nameIndex < 0) nameIndex = 1;
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible);
            const result = [];
            for (const row of rows) {{
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const remarkValue = clean(cells[remarkIndex]?.innerText || cells[remarkIndex]?.textContent || "");
                if (remarkValue !== expectedRemark) continue;
                const nameCell = cells[nameIndex] || cells[0] || row;
                const nameText = clean(nameCell.innerText || nameCell.textContent);
                const match = nameText.match(/ID:\\s*(\\d+)/);
                if (match) result.push(match[1]);
            }}
            return result;
        }}
        """

    def _member_id_remark_values_script(self) -> str:
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
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => cleanCompact(header.innerText || header.textContent));
            let remarkIndex = headers.findIndex((header) => header === "备注");
            if (remarkIndex < 0) remarkIndex = 2;
            let nameIndex = headers.findIndex((header) => header.includes("成员名称"));
            if (nameIndex < 0) nameIndex = 1;
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible);
            const result = {{}};
            for (const row of rows) {{
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const nameCell = cells[nameIndex] || cells[0] || row;
                const nameText = clean(nameCell.innerText || nameCell.textContent);
                const match = nameText.match(/ID:\\s*(\\d+)/);
                if (!match) continue;
                const remarkValue = clean(cells[remarkIndex]?.innerText || cells[remarkIndex]?.textContent || "");
                result[match[1]] = remarkValue;
            }}
            return result;
        }}
        """

    def _member_checkbox_by_id_script(self, member_id: str) -> str:
        return f"""
        () => {{
            const expectedId = {member_id!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter((row) => visible(row));
            for (const row of rows) {{
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const matched = cells.some((cell) => {{
                    const text = cell.innerText || cell.textContent || "";
                    const match = text.match(/ID:\\s*(\\d+)/);
                    return match && match[1] === expectedId;
                }});
                if (!matched) continue;
                const checkbox = Array.from(row.querySelectorAll(".el-checkbox, label"))
                    .find((el) => visible(el));
                if (!checkbox) return null;
                const wrapper = checkbox.closest(".el-checkbox") || checkbox;
                if (wrapper.classList.contains("is-checked")) return null;
                return checkbox;
            }}
            return null;
        }}
        """

    def _member_checkbox_by_record_script(self, member_record: dict[str, str]) -> str:
        return f"""
        () => {{
            const expected = {json.dumps(member_record, ensure_ascii=False)};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const parseNameId = (value) => {{
                const raw = clean(value);
                const match = raw.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                return {{
                    raw,
                    name: match ? clean(match[1]) : raw,
                    id: match ? match[2] : "",
                }};
            }};
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => cleanCompact(header.innerText || header.textContent));
            let nameIndex = headers.findIndex((header) => header.includes("鎴愬憳鍚嶇О"));
            if (nameIndex < 0) nameIndex = 1;
            let remarkIndex = headers.findIndex((header) => header === "澶囨敞");
            if (remarkIndex < 0) remarkIndex = 2;
            let createdIndex = headers.findIndex((header) => header.includes("鍒涘缓鏃堕棿"));
            if (createdIndex < 0) createdIndex = 12;
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter((row) => visible(row));
            for (const row of rows) {{
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const parsed = parseNameId(cells[nameIndex]?.innerText || cells[nameIndex]?.textContent || "");
                const remark = clean(cells[remarkIndex]?.innerText || cells[remarkIndex]?.textContent || "");
                const createdTime = clean(cells[createdIndex]?.innerText || cells[createdIndex]?.textContent || "");
                if (parsed.id && expected.id && parsed.id !== expected.id) continue;
                if (parsed.name !== expected.name) continue;
                if (expected.remark && remark !== expected.remark) continue;
                if (expected.created_time && createdTime !== expected.created_time) continue;
                const checkbox = Array.from(row.querySelectorAll(".el-checkbox, label"))
                    .find((el) => visible(el));
                if (!checkbox) return null;
                const wrapper = checkbox.closest(".el-checkbox") || checkbox;
                if (wrapper.classList.contains("is-checked")) return null;
                return checkbox;
            }}
            return null;
        }}
        """

    def _member_checkbox_by_name_script(self, member_name: str) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const cleanCompact = (value) => String(value || "").replace(/\\s+/g, "");
            const headers = Array.from(document.querySelectorAll({self.locator("table_header")!r}))
                .filter(visible)
                .map((header) => cleanCompact(header.innerText || header.textContent));
            let nameIndex = headers.findIndex((header) => header.includes("成员名称"));
            if (nameIndex < 0) nameIndex = 1;
            const rows = Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter((row) => visible(row));
            for (const row of rows) {{
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const nameCell = cells[nameIndex] || cells[1] || cells[0] || row;
                const nameText = clean(nameCell.innerText || nameCell.textContent || "");
                const match = nameText.match(/^(.*?)\\s*ID:\\s*(\\d+)/);
                const actualName = match ? clean(match[1]) : nameText;
                if (actualName !== expectedName) continue;
                const checkbox = Array.from(row.querySelectorAll(".el-checkbox, label"))
                    .find((el) => visible(el));
                if (!checkbox) return null;
                const wrapper = checkbox.closest(".el-checkbox") || checkbox;
                if (wrapper.classList.contains("is-checked")) return null;
                return checkbox;
            }}
            return null;
        }}
        """

    def _selected_member_count(self) -> int:
        script = """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(".el-checkbox.is-checked"))
                .filter((el) => visible(el) && !el.closest("thead")).length;
        }
        """
        return int(self.cdp.evaluate(script) or 0)

    def _wait_member_selected_count(self, expected_count: int) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self._selected_member_count() == expected_count:
                return
            time.sleep(0.2)
        raise TimeoutError(f"selected member count did not become {expected_count}")

    def _batch_more_operation_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(".el-sub-menu__title"))
                .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "更多操作") || null;
        }
        """

    def _batch_menu_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const poppers = Array.from(document.querySelectorAll(".el-popper, .el-menu--popup-container"))
                .filter(visible);
            for (const popper of poppers) {{
                const item = Array.from(popper.querySelectorAll(".el-menu-item, li, div"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (item) return item;
            }}
            return null;
        }}
        """

    def _click_batch_nested_menu_item(self, parent_text: str, child_text: str) -> None:
        self.cdp.hover_element_by_script(self._batch_more_operation_script())
        self._wait_batch_menu_item_visible(parent_text)
        self.cdp.hover_element_by_script(self._batch_menu_item_script(parent_text))
        self._wait_batch_menu_item_visible(child_text)
        self.cdp.click_element_by_script(self._batch_menu_item_script(child_text))

    def _wait_batch_menu_item_visible(self, text: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._batch_menu_item_script(text)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"batch menu item was not visible: {text}")

    def _wait_batch_edit_remark_dialog_visible(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                        .some((overlay) => visible(overlay) && (overlay.innerText || "").includes("编辑备注"));
                }
                """
            )
            if visible:
                return
            time.sleep(0.3)
        raise TimeoutError("batch edit member remark dialog did not appear")

    def _batch_remark_modify_mode_script(self, modify_mode: str) -> str:
        return f"""
        () => {{
            const expectedText = {modify_mode!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("编辑备注"));
            for (const overlay of overlays.reverse()) {{
                const radios = Array.from(overlay.querySelectorAll(".el-radio, label, span"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                for (const radio of radios) {{
                    return radio.closest(".el-radio") || radio;
                }}
            }}
            return null;
        }}
        """

    def _batch_remark_modify_mode_selected_script(self, modify_mode: str) -> str:
        return f"""
        () => {{
            const expectedText = {modify_mode!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("编辑备注"));
            for (const overlay of overlays.reverse()) {{
                const radios = Array.from(overlay.querySelectorAll(".el-radio"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                for (const radio of radios) {{
                    const input = radio.querySelector("input");
                    if (radio.classList.contains("is-checked") || input?.checked) return true;
                }}
            }}
            return false;
        }}
        """

    def _wait_batch_remark_modify_mode_selected(self, modify_mode: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            selected = self.cdp.evaluate(self._batch_remark_modify_mode_selected_script(modify_mode))
            if selected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"batch remark modify mode was not selected: {modify_mode}")

    def _batch_remark_input_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("编辑备注"));
            for (const overlay of overlays.reverse()) {
                const textarea = Array.from(overlay.querySelectorAll("textarea"))
                    .find((el) => visible(el));
                if (textarea) return textarea;
                const input = Array.from(overlay.querySelectorAll("input"))
                    .filter((el) => visible(el) && !el.readOnly)
                    .find((el) => !el.closest(".el-radio") && !el.closest(".el-checkbox"));
                if (input) return input;
            }
            return null;
        }
        """

    # ── 批量操作私有脚本结束 ──────────────────────────────────────────────

    def _unique_non_empty(self, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            clean_value = str(value).strip()
            if clean_value.isdigit() and len(clean_value) > 8:
                continue
            if clean_value and clean_value not in result:
                result.append(clean_value)
        return result
