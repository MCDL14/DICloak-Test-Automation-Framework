from __future__ import annotations

import re
import time

from core.config import timeout_seconds as config_timeout_seconds
from pages.base_page import BasePage


class ProxyPage(BasePage):
    locator_file = "proxy_locators.yaml"

    SUCCESS_TEXTS = ("连接测试成功", "连接成功")
    FAILURE_TEXT = "连接失败"

    def recover_to_module_home(self) -> None:
        self.open_list()
        self.dismiss_blocking_overlays()

    def open_list(self) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_menu_item_script("代理管理"))
        if self.cdp.evaluate(self._batch_create_page_visible_script()):
            self.return_from_batch_create()
        self._wait_for_proxy_list()

    def proxy_ids_by_host_port(self, host: str, port: str) -> set[str]:
        return {
            str(row.get("id", "")).strip()
            for row in self.proxy_rows()
            if row.get("host") == str(host).strip() and row.get("port") == str(port).strip() and row.get("id")
        }

    def proxy_ids_by_type_host_port(self, proxy_type: str, host: str, port: str) -> set[str]:
        clean_type = str(proxy_type).strip().upper()
        clean_host = str(host).strip()
        clean_port = str(port).strip()
        return {
            str(row.get("id", "")).strip()
            for row in self.proxy_rows()
            if row.get("type") == clean_type
            and row.get("host") == clean_host
            and row.get("port") == clean_port
            and row.get("id")
        }

    def proxy_row_by_id(self, proxy_id: str) -> dict[str, str]:
        clean_id = str(proxy_id).strip()
        if not clean_id:
            return {}
        return next((row for row in self.proxy_rows() if row.get("id") == clean_id), {})

    def proxy_exists_by_type_host_port_id(self, proxy_type: str, host: str, port: str, proxy_id: str) -> bool:
        row = self.proxy_row_by_id(proxy_id)
        return bool(
            row
            and row.get("type") == str(proxy_type).strip().upper()
            and row.get("host") == str(host).strip()
            and row.get("port") == str(port).strip()
        )

    def proxy_rows(self) -> list[dict[str, str]]:
        rows = self.cdp.evaluate(self._proxy_rows_script())
        if not isinstance(rows, list):
            return []
        normalized: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "id": str(row.get("id", "") or "").strip(),
                    "type": str(row.get("type", "") or "").strip().upper(),
                    "host": str(row.get("host", "") or "").strip(),
                    "port": str(row.get("port", "") or "").strip(),
                    "account": str(row.get("account", "") or "").strip(),
                    "ip_protocol": str(row.get("ip_protocol", "") or "").strip().upper(),
                    "password": str(row.get("password", "") or "").strip(),
                    "outbound_ip": str(row.get("outbound_ip", "") or "").strip(),
                    "remark": str(row.get("remark", "") or "").strip(),
                    "text": str(row.get("text", "") or "").strip(),
                }
            )
        return normalized

    def open_batch_create_page(self) -> None:
        self.open_list()
        self.clear_proxy_selection()
        self.cdp.click_element_by_script(self._visible_text_element_script("批量创建", exact=True))
        self._wait_batch_create_page_visible()

    def fill_batch_proxy_text(self, text: str) -> None:
        self._wait_batch_create_page_visible()
        self.cdp.fill_element_by_script(self._batch_proxy_textarea_script(), text)
        self.cdp.press("Tab")

    def batch_preview_rows(self) -> list[dict[str, str]]:
        rows = self.cdp.evaluate(self._batch_preview_rows_script())
        if not isinstance(rows, list):
            return []
        normalized: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "type": str(row.get("type", "") or "").strip().upper(),
                    "host": str(row.get("host", "") or "").strip(),
                    "port": str(row.get("port", "") or "").strip(),
                    "account": str(row.get("account", "") or "").strip(),
                    "ip_protocol": str(row.get("ip_protocol", "") or "").strip().upper(),
                    "password": str(row.get("password", "") or "").strip(),
                    "outbound_ip": str(row.get("outbound_ip", "") or "").strip(),
                    "remark": str(row.get("remark", "") or "").strip(),
                    "text": str(row.get("text", "") or "").strip(),
                }
            )
        return normalized

    def wait_batch_preview_rows(self, expected_count: int, timeout_seconds: int | None = None) -> list[dict[str, str]]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_rows: list[dict[str, str]] = []
        while time.time() < deadline:
            last_rows = self.batch_preview_rows()
            if len(last_rows) == expected_count:
                return last_rows
            time.sleep(0.2)
        raise TimeoutError(f"batch proxy preview row count mismatch: expected={expected_count}, rows={last_rows}")

    def batch_validation_error_text(self) -> str:
        self._wait_batch_create_page_visible()
        text = str(self.cdp.evaluate(self._batch_page_text_script()) or "")
        matches = re.findall(r"第\d+行格式有误", text)
        return "; ".join(matches)

    def wait_batch_validation_error_contains(self, expected_text: str, timeout_seconds: int | None = None) -> str:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_text = ""
        while time.time() < deadline:
            last_text = self.batch_validation_error_text()
            if expected_text in last_text:
                return last_text
            time.sleep(0.2)
        return last_text

    def detect_batch_proxies(self) -> None:
        self._wait_batch_create_page_visible()
        self.cdp.click_element_by_script(self._batch_page_button_script("检测代理"))

    def wait_batch_detection_finished(self, timeout_seconds: int | None = None) -> list[dict[str, str]]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "proxy_detect_seconds", 45)
        deadline = time.time() + timeout_seconds
        seen_activity = False
        seen_loading = False
        seen_button_disabled = False
        last_state: dict[str, object] = {}
        while time.time() < deadline:
            state = self.cdp.evaluate(self._batch_detection_state_script())
            if isinstance(state, dict):
                last_state = state
            loading = bool(last_state.get("loading"))
            button_disabled = bool(last_state.get("button_disabled"))
            outbound_texts = last_state.get("outbound_texts") if isinstance(last_state.get("outbound_texts"), list) else []
            if loading or button_disabled:
                seen_activity = True
            if loading:
                seen_loading = True
            if button_disabled:
                seen_button_disabled = True
            if not loading and not button_disabled:
                if seen_activity:
                    return self.batch_preview_rows()
                if any(str(text or "").strip().replace("\n", " ") not in {"", "--", "-- --"} for text in outbound_texts):
                    return self.batch_preview_rows()
            time.sleep(0.5)
        raise TimeoutError(
            "batch proxy detection did not finish: "
            f"seen_activity={seen_activity}, seen_loading={seen_loading}, "
            f"seen_button_disabled={seen_button_disabled}, state={last_state}, rows={self.batch_preview_rows()}"
        )

    def confirm_batch_create(self) -> dict[str, str | int]:
        self._wait_batch_create_page_visible()
        self.cdp.click_element_by_script(self._batch_page_button_script("确定"))
        return self.wait_batch_result_dialog()

    def wait_batch_result_dialog(self, timeout_seconds: int | None = None) -> dict[str, str | int]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_text = ""
        while time.time() < deadline:
            text = str(self.cdp.evaluate(self._active_confirmation_overlay_text_script()) or "").strip()
            if text:
                last_text = text
                success = self._extract_count_from_text(text, ("成功", "新增成功", "添加成功"))
                duplicate = self._extract_count_from_text(text, ("重复", "已存在"))
                if success is not None and duplicate is not None:
                    return {"success": success, "duplicate": duplicate, "text": text}
            time.sleep(0.2)
        raise TimeoutError(f"batch proxy result dialog did not appear: last_text={last_text}")

    def confirm_batch_result_dialog(self) -> None:
        try:
            self.cdp.click_element_by_script(self._latest_message_box_footer_button_script(), timeout=5000)
            self._wait_confirmation_overlay_closed()
        except Exception:
            self.confirm_secondary_dialog(("确定", "确认"))
        self._wait_for_proxy_list()

    def return_from_batch_create(self) -> None:
        if not self.cdp.evaluate(self._batch_create_page_visible_script()):
            return
        try:
            self.cdp.click_element_by_script(self._batch_page_text_element_script("返回"), timeout=3000)
        except Exception:
            self.cdp.click_element_by_script(self._batch_page_button_script("取消"), timeout=3000)
        self._wait_for_proxy_list()

    def open_create_dialog(self) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_text_element_script("创建代理"))
        self._wait_create_dialog_visible()

    def ensure_create_dialog_proxy_type(self, proxy_type: str = "HTTP") -> None:
        self._wait_create_dialog_visible()
        clean_type = str(proxy_type).strip().upper()
        if not clean_type:
            raise ValueError("proxy type is empty")
        current_type = self.create_dialog_proxy_type()
        if current_type == clean_type:
            return
        self.cdp.click_element_by_script(self._create_dialog_proxy_type_select_script())
        self.cdp.click_element_by_script(self._visible_dropdown_option_script(clean_type))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            current_type = self.create_dialog_proxy_type()
            if current_type == clean_type:
                return
            time.sleep(0.2)
        raise TimeoutError(f"create proxy dialog proxy type was not selected: expected={clean_type}, actual={current_type}")

    def create_dialog_proxy_type(self) -> str:
        self._wait_create_dialog_visible()
        return str(self.cdp.evaluate(self._create_dialog_proxy_type_value_script()) or "").strip().upper()

    def fill_create_dialog(self, host: str, port: str, account: str, password: str) -> None:
        self._wait_create_dialog_visible()
        self.cdp.fill_element_by_script(self._create_dialog_input_script("host"), host)
        self.cdp.fill_element_by_script(self._create_dialog_input_script("port"), port)
        self.cdp.fill_element_by_script(self._create_dialog_input_script("account"), account)
        self.cdp.fill_element_by_script(self._create_dialog_input_script("password"), password)

    def select_create_dialog_country(self, country: str) -> None:
        self._wait_create_dialog_visible()
        self.cdp.click_element_by_script(self._create_dialog_select_by_label_script("国家/地区"))
        self.cdp.click_element_by_script(self._visible_dropdown_option_script(country))

    def fill_create_dialog_remark(self, remark: str) -> None:
        self._wait_create_dialog_visible()
        self.cdp.fill_element_by_script(self._create_dialog_input_by_label_or_placeholder_script("备注", "备注"), remark)

    def detect_proxy_in_create_dialog(self) -> str:
        before_text = self.create_dialog_text()
        self.cdp.click_element_by_script(self._create_dialog_button_script("检测代理"))
        self.wait_create_dialog_detection_started(before_text)
        return self.wait_create_dialog_detect_result()

    def wait_create_dialog_detection_started(
        self,
        before_text: str,
        timeout_seconds: int | None = None,
    ) -> dict[str, object]:
        timeout_seconds = timeout_seconds or min(config_timeout_seconds(self.config, "page_seconds", 10), 8)
        deadline = time.time() + timeout_seconds
        before_clean = self._compact_debug_text(before_text, limit=600)
        last_state: dict[str, object] = {}
        while time.time() < deadline:
            state = self.cdp.evaluate(self._create_dialog_detection_state_script())
            if isinstance(state, dict):
                last_state = state
            result = str(last_state.get("result") or "").strip()
            if result:
                return last_state
            if (
                last_state.get("has_loading")
                or last_state.get("button_disabled")
                or last_state.get("button_loading")
            ):
                return last_state
            current_text = self._compact_debug_text(last_state.get("text"), limit=600)
            if before_clean and current_text and current_text != before_clean:
                return last_state
            time.sleep(0.2)
        raise TimeoutError(
            "proxy detect did not start in create dialog: "
            f"before_text={before_clean!r}, state={self._compact_state_for_error(last_state)}"
        )

    def wait_create_dialog_detect_result(self, timeout_seconds: int | None = None) -> str:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "proxy_detect_seconds", 45)
        deadline = time.time() + timeout_seconds
        last_state: dict[str, object] = {}
        while time.time() < deadline:
            state = self.cdp.evaluate(self._create_dialog_detection_state_script())
            if isinstance(state, dict):
                last_state = state
            result = str(last_state.get("result") or "").strip()
            if result:
                return result
            time.sleep(0.5)
        raise TimeoutError(
            "proxy detect result did not appear in create dialog: "
            f"state={self._compact_state_for_error(last_state)}"
        )

    def create_dialog_text(self) -> str:
        self._wait_create_dialog_visible()
        return str(self.cdp.evaluate(self._active_dialog_text_script()) or "").strip()

    def confirm_create_dialog(self) -> None:
        self.cdp.click_element_by_script(self._create_dialog_button_script("确定"))
        if not self._wait_create_dialog_closed():
            raise TimeoutError("create proxy dialog did not close after confirm")
        self._wait_for_proxy_list()

    def try_confirm_create_dialog(self, timeout_seconds: int = 5) -> bool:
        self.cdp.click_element_by_script(self._create_dialog_button_script("确定"))
        if not self._wait_create_dialog_closed(timeout_seconds=timeout_seconds):
            return False
        self._wait_for_proxy_list()
        return True

    def cancel_create_dialog(self) -> None:
        if not self.cdp.evaluate(self._create_dialog_visible_script()):
            return
        try:
            self.cdp.click_element_by_script(self._create_dialog_button_script("取消"), timeout=3000)
        except Exception:
            self.cdp.click_element_by_script(self._create_dialog_close_button_script(), timeout=3000)
        if not self._wait_create_dialog_closed(timeout_seconds=5):
            self.cdp.press("Escape")
            if not self._wait_create_dialog_closed(timeout_seconds=3):
                raise TimeoutError("create proxy dialog did not close after cancel")
        self._wait_for_proxy_list()

    def wait_new_proxy_visible(
        self,
        host: str,
        port: str,
        existing_ids: set[str],
        timeout_seconds: int | None = None,
    ) -> str:
        clean_host = str(host).strip()
        clean_port = str(port).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_rows: list[dict[str, str]] = []
        while time.time() < deadline:
            last_rows = self.proxy_rows()
            for row in last_rows:
                row_id = str(row.get("id", "")).strip()
                if (
                    row_id
                    and row_id not in existing_ids
                    and row.get("host") == clean_host
                    and row.get("port") == clean_port
                ):
                    return row_id
            time.sleep(0.5)
        raise TimeoutError(
            "created proxy row was not found: "
            f"host={clean_host}, port={clean_port}, existing_ids={sorted(existing_ids)}, rows={last_rows}"
        )

    def wait_new_proxy_visible_by_type(
        self,
        proxy_type: str,
        host: str,
        port: str,
        existing_ids: set[str],
        timeout_seconds: int | None = None,
    ) -> str:
        clean_type = str(proxy_type).strip().upper()
        clean_host = str(host).strip()
        clean_port = str(port).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_rows: list[dict[str, str]] = []
        while time.time() < deadline:
            last_rows = self.proxy_rows()
            for row in last_rows:
                row_id = str(row.get("id", "")).strip()
                if (
                    row_id
                    and row_id not in existing_ids
                    and row.get("type") == clean_type
                    and row.get("host") == clean_host
                    and row.get("port") == clean_port
                ):
                    return row_id
            time.sleep(0.5)
        raise TimeoutError(
            "created proxy row was not found: "
            f"type={clean_type}, host={clean_host}, port={clean_port}, "
            f"existing_ids={sorted(existing_ids)}, rows={last_rows}"
        )

    def proxy_exists_by_id(self, proxy_id: str) -> bool:
        clean_id = str(proxy_id).strip()
        if not clean_id:
            return False
        return bool(self.cdp.evaluate(self._proxy_row_exists_by_id_script(clean_id)))

    def detect_proxy_in_row(self, proxy_id: str) -> str:
        clean_id = str(proxy_id).strip()
        if not clean_id:
            raise ValueError("proxy id is empty")
        before_text = self.row_detect_result(clean_id)
        self.cdp.click_element_by_script(self._proxy_row_operation_button_by_position_script(clean_id, "first"))
        detecting_cell_index = self.wait_row_detecting_visible_or_result_changed(clean_id, before_text)
        self.wait_row_detecting_hidden(clean_id)
        return self.row_detect_result(clean_id, cell_index=detecting_cell_index)

    def wait_row_detecting_visible_or_result_changed(
        self,
        proxy_id: str,
        before_text: str,
        timeout_seconds: int | None = None,
    ) -> int | None:
        clean_id = str(proxy_id).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        before_clean = str(before_text or "").strip()
        last_index: int | None = None
        last_text = ""
        last_row_text = ""
        while time.time() < deadline:
            current_index = self.cdp.evaluate(self._proxy_row_cell_index_contains_text_script(clean_id, "检测中"))
            if isinstance(current_index, int) and current_index >= 0:
                return current_index
            last_index = current_index if isinstance(current_index, int) else None
            current_text = self.row_detect_result(clean_id)
            last_text = current_text
            last_row_text = self.row_text_by_id(clean_id)
            if current_text and current_text != before_clean:
                return None
            time.sleep(0.2)
        raise TimeoutError(
            "proxy row detect status did not appear or change: "
            f"id={clean_id}, before={before_clean}, last_index={last_index}, "
            f"last_text={self._compact_debug_text(last_text)!r}, "
            f"row_text={self._compact_debug_text(last_row_text)!r}"
        )

    def wait_row_detecting_hidden(self, proxy_id: str, timeout_seconds: int | None = None) -> int | None:
        clean_id = str(proxy_id).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "proxy_detect_seconds", 45)
        deadline = time.time() + timeout_seconds
        detecting_cell_index: int | None = None
        last_row_text = ""
        while time.time() < deadline:
            current_index = self.cdp.evaluate(self._proxy_row_cell_index_contains_text_script(clean_id, "检测中"))
            if isinstance(current_index, int) and current_index >= 0:
                detecting_cell_index = current_index
            last_row_text = self.row_text_by_id(clean_id)
            if not self.cdp.evaluate(self._proxy_row_contains_text_script(clean_id, "检测中")):
                return detecting_cell_index
            time.sleep(0.5)
        raise TimeoutError(
            "proxy row detect status did not disappear: "
            f"id={clean_id}, detecting_cell_index={detecting_cell_index}, "
            f"row_text={self._compact_debug_text(last_row_text)!r}"
        )

    def row_detect_result(self, proxy_id: str, cell_index: int | None = None) -> str:
        clean_id = str(proxy_id).strip()
        result_text = ""
        if cell_index is not None:
            result_text = str(self.cdp.evaluate(self._proxy_row_cell_text_by_index_script(clean_id, cell_index)) or "").strip()
        row_text = str(self.cdp.evaluate(self._proxy_row_text_by_id_script(clean_id)) or "").strip()
        text = result_text or row_text
        if self.FAILURE_TEXT in text:
            return self.FAILURE_TEXT
        for success_text in self.SUCCESS_TEXTS:
            if success_text in text:
                return success_text
        return text

    def row_text_by_id(self, proxy_id: str) -> str:
        clean_id = str(proxy_id).strip()
        if not clean_id:
            return ""
        return str(self.cdp.evaluate(self._proxy_row_text_by_id_script(clean_id)) or "").strip()

    @staticmethod
    def _compact_debug_text(value: object, limit: int = 500) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    @classmethod
    def _compact_state_for_error(cls, state: dict[str, object]) -> dict[str, object]:
        compact = dict(state)
        for key in ("text", "line_summary"):
            if key in compact:
                compact[key] = cls._compact_debug_text(compact.get(key), limit=600)
        return compact

    def delete_proxy_by_id(self, proxy_id: str) -> None:
        clean_id = str(proxy_id).strip()
        if not clean_id:
            return
        if not self.proxy_exists_by_id(clean_id):
            return
        self.cdp.click_element_by_script(self._proxy_row_operation_button_by_position_script(clean_id, "last"))
        self.confirm_secondary_dialog()
        self.wait_proxy_absent(clean_id)

    def clear_proxy_selection(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "search_result_seconds", 10)
        while time.time() < deadline:
            count = self.cdp.evaluate(self._proxy_selected_count_script())
            if count == 0:
                return
            self.cdp.evaluate(self._clear_proxy_selection_script())
            time.sleep(0.2)
        raise TimeoutError(f"proxy selection did not clear: selected_count={self.cdp.evaluate(self._proxy_selected_count_script())}")

    def select_proxy_rows_by_ids(self, proxy_ids: set[str]) -> None:
        clean_ids = {str(proxy_id).strip() for proxy_id in proxy_ids if str(proxy_id).strip()}
        if not clean_ids:
            return
        self.clear_proxy_selection()
        for proxy_id in clean_ids:
            self.cdp.click_element_by_script(self._proxy_row_selection_checkbox_script(proxy_id))
        self.wait_proxy_selected_count(len(clean_ids))

    def wait_proxy_selected_count(self, expected_count: int, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_count = -1
        while time.time() < deadline:
            count = self.cdp.evaluate(self._proxy_selected_count_script())
            if isinstance(count, int):
                last_count = count
            if last_count == expected_count:
                return
            time.sleep(0.2)
        raise TimeoutError(f"proxy selected count mismatch: expected={expected_count}, actual={last_count}")

    def bulk_delete_selected_proxies(self, proxy_ids: set[str]) -> None:
        clean_ids = {str(proxy_id).strip() for proxy_id in proxy_ids if str(proxy_id).strip()}
        if not clean_ids:
            return
        self.select_proxy_rows_by_ids(clean_ids)
        self.click_proxy_bulk_action(("删除",))
        self.confirm_secondary_dialog(("确定删除", "确认删除", "确定", "确认"))
        for proxy_id in clean_ids:
            self.wait_proxy_absent(proxy_id)
        self.wait_proxy_selected_count(0)

    def click_proxy_bulk_action(self, texts: tuple[str, ...]) -> None:
        self._wait_for_proxy_list()
        last_error: Exception | None = None
        for text in texts:
            try:
                self.cdp.click_element_by_script(self._proxy_bulk_action_script(text), timeout=5000)
                return
            except Exception as exc:
                last_error = exc
        raise TimeoutError(f"proxy bulk action was not found: {texts}") from last_error

    def start_bulk_detect_selected_proxies(self, proxy_ids: set[str]) -> dict[str, str]:
        clean_ids = {str(proxy_id).strip() for proxy_id in proxy_ids if str(proxy_id).strip()}
        if not clean_ids:
            return {}
        before_results = {proxy_id: self.row_detect_result(proxy_id) for proxy_id in clean_ids}
        self.select_proxy_rows_by_ids(clean_ids)
        self.click_proxy_bulk_action(("批量检测", "检测代理", "检测"))
        return before_results

    def wait_proxy_row_detection_finished(self, proxy_id: str, before_text: str) -> str:
        clean_id = str(proxy_id).strip()
        detecting_cell_index = self.wait_row_detecting_visible_or_result_changed(clean_id, before_text)
        hidden_cell_index = self.wait_row_detecting_hidden(clean_id)
        return self.row_detect_result(
            clean_id,
            cell_index=detecting_cell_index if detecting_cell_index is not None else hidden_cell_index,
        )

    def wait_proxy_absent(self, proxy_id: str, timeout_seconds: int | None = None) -> None:
        clean_id = str(proxy_id).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.proxy_exists_by_id(clean_id):
                return
            time.sleep(0.5)
        raise TimeoutError(f"proxy row still exists after delete: id={clean_id}")

    def delete_newest_proxy_by_host_port_excluding(self, host: str, port: str, excluded_ids: set[str]) -> None:
        candidates = [
            row
            for row in self.proxy_rows()
            if row.get("host") == str(host).strip()
            and row.get("port") == str(port).strip()
            and row.get("id")
            and row.get("id") not in excluded_ids
        ]
        for row in candidates:
            try:
                self.delete_proxy_by_id(str(row["id"]))
            except Exception:
                continue

    def dismiss_blocking_overlays(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            closed = bool(self.cdp.evaluate(self._close_latest_overlay_script()))
            if not closed:
                return
            time.sleep(0.3)

    def confirm_secondary_dialog(self, preferred_texts: tuple[str, ...] = ("确定删除", "确认删除", "确定", "确认")) -> None:
        last_error: Exception | None = None
        for text in preferred_texts:
            try:
                self.cdp.click_element_by_script(self._confirmation_button_script(text), timeout=3000)
                self._wait_confirmation_overlay_closed()
                return
            except Exception as exc:
                last_error = exc
        raise TimeoutError(f"secondary confirmation button was not found: {preferred_texts}") from last_error

    def _wait_for_proxy_list(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._proxy_list_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("proxy list did not appear")

    def _wait_batch_create_page_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._batch_create_page_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("batch create proxy page did not appear")

    def _extract_count_from_text(self, text: str, labels: tuple[str, ...]) -> int | None:
        clean_text = str(text or "").replace("\n", " ")
        for label in labels:
            patterns = (
                rf"{re.escape(label)}\s*[:：]?\s*(\d+)",
                rf"{re.escape(label)}\D{{0,12}}(\d+)\s*个?",
                rf"(\d+)\s*个?\D{{0,6}}{re.escape(label)}",
            )
            for pattern in patterns:
                match = re.search(pattern, clean_text)
                if match:
                    return int(match.group(1))
        return None

    def _wait_create_dialog_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._create_dialog_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("create proxy dialog did not appear")

    def _wait_create_dialog_closed(self, timeout_seconds: int | None = None) -> bool:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.cdp.evaluate(self._create_dialog_visible_script()):
                return True
            time.sleep(0.2)
        return False

    def _wait_confirmation_overlay_closed(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.cdp.evaluate(self._active_confirmation_overlay_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("proxy secondary confirmation overlay did not close")

    def _wait_for_overlay_closed(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.cdp.evaluate(self._active_overlay_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("proxy overlay did not close")

    def _visible_menu_item_script(self, text: str) -> str:
        return self._visible_text_element_script(text, exact=True, selector_name="proxy_menu_candidates")

    def _visible_text_element_script(
        self,
        text: str,
        exact: bool = True,
        selector_name: str = "visible_text_candidates",
    ) -> str:
        return f"""
        () => {{
            const selector = {self.locator(selector_name)!r};
            const expectedText = {text!r};
            const exact = {str(exact).lower()};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const candidates = Array.from(document.querySelectorAll(selector))
                .filter(visible)
                .filter((el) => {{
                    const text = clean(el.innerText || el.textContent);
                    return exact ? text === expectedText : text.includes(expectedText);
                }})
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    return {{ el, area: rect.width * rect.height }};
                }})
                .sort((left, right) => left.area - right.area);
            return candidates[0]?.el || null;
        }}
        """

    def _proxy_list_visible_script(self) -> str:
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
            const bodyText = document.body ? (document.body.innerText || "") : "";
            return location.hash.includes("/proxy")
                && bodyText.includes("代理管理")
                && !bodyText.includes("请输入代理信息，输入多个请换行")
                && Boolean(Array.from(document.querySelectorAll({self.locator("table_container")!r})).find(visible));
        }}
        """

    def _batch_create_page_visible_script(self) -> str:
        return """
        () => {
            const bodyText = document.body ? (document.body.innerText || "") : "";
            const textarea = Array.from(document.querySelectorAll("textarea,input"))
                .find((el) => (el.getAttribute("placeholder") || "").includes("请输入代理信息，输入多个请换行"));
            return location.hash.includes("/proxy")
                && bodyText.includes("返回")
                && bodyText.includes("已添加代理")
                && Boolean(textarea);
        }
        """

    def _batch_proxy_textarea_script(self) -> str:
        return """
        () => Array.from(document.querySelectorAll("textarea,input"))
            .find((el) => (el.getAttribute("placeholder") || "").includes("请输入代理信息，输入多个请换行"))
            || null
        """

    def _batch_page_text_script(self) -> str:
        return """
        () => {
            const page = __BATCH_PAGE__();
            return page ? String(page.innerText || page.textContent || "") : "";
        }
        """.replace("__BATCH_PAGE__", self._batch_page_function())

    def _batch_page_text_element_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const page = __BATCH_PAGE__();
            if (!page) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const items = Array.from(page.querySelectorAll("button, .el-button, [role='button'], span, div, a"))
                .filter(visible)
                .filter((el) => clean(el.innerText || el.textContent) === expectedText)
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    return {{ el, area: rect.width * rect.height, y: rect.y, x: rect.x }};
                }})
                .sort((left, right) => left.area - right.area || left.y - right.y || left.x - right.x);
            return items[0]?.el || null;
        }}
        """.replace("__BATCH_PAGE__", self._batch_page_function())

    def _batch_page_button_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const page = __BATCH_PAGE__();
            if (!page) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const buttons = Array.from(page.querySelectorAll({self.locator("button")!r}))
                .filter(visible)
                .filter((button) => clean(button.innerText || button.textContent) === expectedText)
                .map((button) => {{
                    const rect = button.getBoundingClientRect();
                    return {{ button, y: rect.y, x: rect.x }};
                }})
                .sort((left, right) => (right.y - left.y) || (right.x - left.x));
            return buttons[0]?.button || null;
        }}
        """.replace("__BATCH_PAGE__", self._batch_page_function())

    def _batch_preview_rows_script(self) -> str:
        return f"""
        () => {{
            const page = __BATCH_PAGE__();
            if (!page) return [];
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return Array.from(page.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .map((row) => {{
                    const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r}))
                        .filter(visible)
                        .map((cell) => clean(cell.innerText || cell.textContent));
                    return {{
                        type: cells[0] || "",
                        host: cells[1] || "",
                        port: cells[2] || "",
                        account: cells[3] || "",
                        ip_protocol: cells[4] || "",
                        password: cells[5] || "",
                        outbound_ip: cells[6] || "",
                        remark: cells[7] || "",
                        text: clean(row.innerText || row.textContent),
                    }};
                }})
                .filter((row) => row.text);
        }}
        """.replace("__BATCH_PAGE__", self._batch_page_function())

    def _batch_detection_state_script(self) -> str:
        return f"""
        () => {{
            const page = __BATCH_PAGE__();
            if (!page) return {{ loading: false, button_disabled: false, outbound_texts: [] }};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const button = Array.from(page.querySelectorAll({self.locator("button")!r}))
                .filter(visible)
                .find((candidate) => clean(candidate.innerText || candidate.textContent) === "检测代理");
            const buttonDisabled = Boolean(button && (
                button.disabled
                || button.classList.contains("is-disabled")
                || button.getAttribute("aria-disabled") === "true"
            ));
            const rows = Array.from(page.querySelectorAll({self.locator("table_row")!r})).filter(visible);
            const outboundTexts = rows.map((row) => {{
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                return clean(cells[6] ? (cells[6].innerText || cells[6].textContent) : "");
            }});
            const loading = rows.some((row) => {{
                const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
                const cell = cells[6] || row;
                const text = clean(cell.innerText || cell.textContent);
                return text.includes("检测中")
                    || Boolean(cell.querySelector(".is-loading, .el-icon-loading, .icon-loading, [class*='loading'], [class*='Loading']"));
            }});
            return {{ loading, button_disabled: buttonDisabled, outbound_texts: outboundTexts }};
        }}
        """.replace("__BATCH_PAGE__", self._batch_page_function())

    def _batch_page_function(self) -> str:
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
            return Array.from(document.querySelectorAll("main, .el-main, .app-main, .layout-content, body"))
                .filter(visible)
                .find((el) => {
                    const text = el.innerText || el.textContent || "";
                    const textarea = Array.from(el.querySelectorAll("textarea,input"))
                        .find((input) => (input.getAttribute("placeholder") || "").includes("请输入代理信息，输入多个请换行"));
                    return text.includes("已添加代理") && Boolean(textarea);
                })
                || null;
        })
        """

    def _create_dialog_visible_script(self) -> str:
        return """
        () => Boolean((() => {
            const dialog = __CREATE_DIALOG__();
            return dialog;
        })())
        """.replace("__CREATE_DIALOG__", self._create_dialog_function())

    def _create_dialog_function(self) -> str:
        return f"""
        (() => {{
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const dialogs = Array.from(document.querySelectorAll({self.locator("dialog_or_drawer")!r}))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("创建代理"));
            return dialogs[dialogs.length - 1] || null;
        }})
        """

    def _create_dialog_input_script(self, field_name: str) -> str:
        return f"""
        () => {{
            const fieldName = {field_name!r};
            const dialog = __CREATE_DIALOG__();
            if (!dialog) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const inputs = Array.from(dialog.querySelectorAll("input.el-input__inner, textarea"))
                .filter(visible);
            const byPlaceholder = (patterns) => inputs.find((input) => {{
                const placeholder = input.getAttribute("placeholder") || "";
                return patterns.some((pattern) => placeholder.includes(pattern));
            }});
            const byOrder = () => {{
                const textInputs = inputs.filter((input) => !["选择", "请选择"].includes(input.getAttribute("placeholder") || ""));
                if (fieldName === "host") return textInputs[0] || null;
                if (fieldName === "port") return textInputs[1] || null;
                if (fieldName === "account") return textInputs[2] || null;
                if (fieldName === "password") return textInputs[3] || null;
                return null;
            }};
            if (fieldName === "host") return byPlaceholder(["主机", "代理主机"]) || byOrder();
            if (fieldName === "port") return byPlaceholder(["端口", "代理端口"]) || byOrder();
            if (fieldName === "account") return byPlaceholder(["账号", "代理账号"]) || byOrder();
            if (fieldName === "password") return byPlaceholder(["密码", "代理密码"]) || byOrder();
            return null;
        }}
        """.replace("__CREATE_DIALOG__", self._create_dialog_function())

    def _create_dialog_input_by_label_or_placeholder_script(self, label_text: str, placeholder_text: str) -> str:
        return f"""
        () => {{
            const labelText = {label_text!r};
            const placeholderText = {placeholder_text!r};
            const dialog = __CREATE_DIALOG__();
            if (!dialog) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const formItems = Array.from(dialog.querySelectorAll(".el-form-item"))
                .filter(visible)
                .map((item) => {{
                    const label = clean(item.querySelector(".el-form-item__label")?.innerText || "");
                    const input = Array.from(item.querySelectorAll("input.el-input__inner, textarea")).find(visible);
                    return {{ item, label, input }};
                }});
            const byLabel = formItems.find((item) => item.label === labelText && item.input);
            if (byLabel) return byLabel.input;
            return Array.from(dialog.querySelectorAll("input.el-input__inner, textarea"))
                .filter(visible)
                .find((input) => (input.getAttribute("placeholder") || "") === placeholderText)
                || null;
        }}
        """.replace("__CREATE_DIALOG__", self._create_dialog_function())

    def _create_dialog_select_by_label_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const labelText = {label_text!r};
            const dialog = __CREATE_DIALOG__();
            if (!dialog) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const item = Array.from(dialog.querySelectorAll(".el-form-item"))
                .filter(visible)
                .find((candidate) => clean(candidate.querySelector(".el-form-item__label")?.innerText || "") === labelText);
            if (!item) return null;
            return item.querySelector(".el-select, .el-select__wrapper, input.el-input__inner") || null;
        }}
        """.replace("__CREATE_DIALOG__", self._create_dialog_function())

    def _create_dialog_button_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const dialog = __CREATE_DIALOG__();
            if (!dialog) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const buttons = Array.from(dialog.querySelectorAll({self.locator("button")!r}))
                .filter(visible)
                .filter((button) => clean(button.innerText || button.textContent) === expectedText)
                .map((button) => {{
                    const rect = button.getBoundingClientRect();
                    return {{ button, y: rect.y, x: rect.x }};
                }})
                .sort((left, right) => (right.y - left.y) || (right.x - left.x));
            return buttons[0]?.button || null;
        }}
        """.replace("__CREATE_DIALOG__", self._create_dialog_function())

    def _create_dialog_proxy_type_value_script(self) -> str:
        return """
        () => {
            const dialog = __CREATE_DIALOG__();
            if (!dialog) return "";
            const item = __PROXY_TYPE_SELECT__();
            if (!item) return "";
            const text = item.text || "";
            const value = item.value || "";
            const combined = `${value} ${text}`.trim();
            const match = combined.match(/\\b(HTTP|HTTPS|SOCKS5|SOCKS4|NODEMAVEN|IPFLY|922S5|IPROYAL|NETNUT)\\b/i);
            return match ? match[1].toUpperCase() : combined.toUpperCase();
        }
        """.replace("__CREATE_DIALOG__", self._create_dialog_function()).replace(
            "__PROXY_TYPE_SELECT__", self._create_dialog_proxy_type_select_function()
        )

    def _create_dialog_proxy_type_select_script(self) -> str:
        return """
        () => {
            const dialog = __CREATE_DIALOG__();
            if (!dialog) return null;
            const item = __PROXY_TYPE_SELECT__();
            if (!item) return null;
            return item.el;
        }
        """.replace("__CREATE_DIALOG__", self._create_dialog_function()).replace(
            "__PROXY_TYPE_SELECT__", self._create_dialog_proxy_type_select_function()
        )

    def _create_dialog_proxy_type_select_function(self) -> str:
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
            const labelText = (el) => clean(el.closest(".el-form-item")?.querySelector(".el-form-item__label")?.innerText || "");
            const protocolPattern = /\\b(HTTP|HTTPS|SOCKS5|SOCKS4|NODEMAVEN|IPFLY|922S5|IPROYAL|NETNUT)\\b/i;
            const selects = Array.from(dialog.querySelectorAll(".el-select, .el-select__wrapper"))
                .filter(visible)
                .map((el) => {
                    const input = el.querySelector("input");
                    const rect = el.getBoundingClientRect();
                    const text = clean(el.innerText || el.textContent || "");
                    const value = clean(input ? input.value : "");
                    return { el, text, value, label: labelText(el), x: rect.x, y: rect.y };
                })
                .filter((item, index, array) => array.findIndex((other) => other.el === item.el) === index)
                .sort((left, right) => left.y - right.y || left.x - right.x);
            const byLabel = selects.find((item) => item.label === "代理类型");
            if (byLabel) return byLabel;
            const byProtocol = selects.find((item) => protocolPattern.test(`${item.value} ${item.text}`));
            if (byProtocol) return byProtocol;
            return selects[1] || selects[0] || null;
        })
        """

    def _visible_dropdown_option_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r}.toUpperCase();
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim().toUpperCase();
            const options = Array.from(document.querySelectorAll(".el-select-dropdown__item, [role='option'], li"))
                .filter(visible)
                .filter((option) => !option.classList.contains("is-disabled") && option.getAttribute("aria-disabled") !== "true")
                .map((option) => {{
                    const rect = option.getBoundingClientRect();
                    return {{ option, text: clean(option.innerText || option.textContent), y: rect.y, x: rect.x }};
                }})
                .sort((left, right) => left.y - right.y || left.x - right.x);
            return options.find((item) => item.text === expectedText)?.option
                || options.find((item) => item.text.includes(expectedText))?.option
                || null;
        }}
        """

    def _create_dialog_close_button_script(self) -> str:
        return f"""
        () => {{
            const dialog = __CREATE_DIALOG__();
            if (!dialog) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            return Array.from(dialog.querySelectorAll({self.locator("overlay_close_button")!r}))
                .find(visible)
                || null;
        }}
        """.replace("__CREATE_DIALOG__", self._create_dialog_function())

    def _create_dialog_detect_result_script(self) -> str:
        return """
        () => {
            const dialog = __CREATE_DIALOG__();
            if (!dialog) return "";
            const text = dialog.innerText || dialog.textContent || "";
            if (text.includes("连接失败")) return "连接失败";
            if (text.includes("连接测试成功")) return "连接测试成功";
            if (text.includes("连接成功")) return "连接成功";
            return "";
        }
        """.replace("__CREATE_DIALOG__", self._create_dialog_function())

    def _create_dialog_detection_state_script(self) -> str:
        return f"""
        () => {{
            const dialog = __CREATE_DIALOG__();
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const detectResult = (text) => {{
                if (text.includes("连接失败")) return "连接失败";
                if (text.includes("连接测试成功")) return "连接测试成功";
                if (text.includes("连接成功")) return "连接成功";
                return "";
            }};
            if (!dialog) {{
                return {{
                    visible: false,
                    result: "",
                    has_loading: false,
                    button_disabled: false,
                    button_loading: false,
                    button_text: "",
                    text: "",
                    line_summary: "",
                }};
            }}
            const rawText = String(dialog.innerText || dialog.textContent || "");
            const button = Array.from(dialog.querySelectorAll({self.locator("button")!r}))
                .filter(visible)
                .find((candidate) => clean(candidate.innerText || candidate.textContent) === "检测代理")
                || null;
            const buttonText = button ? clean(button.innerText || button.textContent) : "";
            const buttonDisabled = Boolean(button && (
                button.disabled
                || button.classList.contains("is-disabled")
                || button.getAttribute("aria-disabled") === "true"
            ));
            const buttonLoading = Boolean(button && (
                button.classList.contains("is-loading")
                || button.getAttribute("aria-busy") === "true"
                || button.querySelector(".is-loading, .el-icon-loading, .icon-loading, [class*='loading'], [class*='Loading']")
            ));
            const hasLoading = Boolean(
                dialog.querySelector(".is-loading, .el-loading-mask, .el-loading-spinner, .el-icon-loading, .icon-loading, [class*='loading'], [class*='Loading']")
            );
            const lineSummary = rawText
                .split(/\\n+/)
                .map(clean)
                .filter(Boolean)
                .filter((line, index, array) => array.indexOf(line) === index)
                .slice(0, 12)
                .join(" | ");
            return {{
                visible: true,
                result: detectResult(rawText),
                has_loading: hasLoading,
                button_disabled: buttonDisabled,
                button_loading: buttonLoading,
                button_text: buttonText,
                text: rawText,
                line_summary: lineSummary,
            }};
        }}
        """.replace("__CREATE_DIALOG__", self._create_dialog_function())

    def _active_dialog_text_script(self) -> str:
        return """
        () => {
            const dialog = __CREATE_DIALOG__();
            return dialog ? String(dialog.innerText || dialog.textContent || "") : "";
        }
        """.replace("__CREATE_DIALOG__", self._create_dialog_function())

    def _active_confirmation_overlay_text_script(self) -> str:
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
            const overlays = Array.from(document.querySelectorAll({self.locator("confirmation_overlay")!r}))
                .filter(visible)
                .map((overlay) => {{
                    const rect = overlay.getBoundingClientRect();
                    const zIndex = Number.parseInt(window.getComputedStyle(overlay).zIndex, 10) || 0;
                    return {{ overlay, zIndex, y: rect.y, x: rect.x }};
                }})
                .sort((left, right) => (right.zIndex - left.zIndex) || (right.y - left.y) || (right.x - left.x));
            return overlays.length ? String(overlays[0].overlay.innerText || overlays[0].overlay.textContent || "") : "";
        }}
        """

    def _proxy_rows_script(self) -> str:
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
            const parseProxyCell = (text) => {{
                const idMatch = text.match(/ID:\\s*(\\d+)/);
                const proxyMatch = text.match(/([A-Z0-9]+):\\/\\/([^:\\s]+):(\\d+)(?::([^:\\s]+):([^\\s]+))?/i);
                return {{
                    id: idMatch ? idMatch[1] : "",
                    type: proxyMatch ? proxyMatch[1].toUpperCase() : "",
                    host: proxyMatch ? proxyMatch[2] : "",
                    port: proxyMatch ? proxyMatch[3] : "",
                    account: proxyMatch && proxyMatch[4] ? proxyMatch[4] : "",
                    password: proxyMatch && proxyMatch[5] ? proxyMatch[5] : "",
                }};
            }};
            const parse = (text) => {{
                const idMatch = text.match(/ID:\\s*(\\d+)/);
                const proxyMatch = text.match(/([A-Z0-9]+):\\/\\/([^:\\s]+):(\\d+)/i);
                return {{
                    id: idMatch ? idMatch[1] : "",
                    type: proxyMatch ? proxyMatch[1].toUpperCase() : "",
                    host: proxyMatch ? proxyMatch[2] : "",
                    port: proxyMatch ? proxyMatch[3] : "",
                    account: "",
                    ip_protocol: "",
                    password: "",
                    outbound_ip: "",
                    remark: "",
                    text,
                }};
            }};
            return Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .map((row) => {{
                    const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r}))
                        .filter(visible)
                        .map((cell) => clean(cell.innerText || cell.textContent));
                    const parsed = parse(clean(row.innerText || row.textContent));
                    if (cells.length >= 8) {{
                        const proxyCell = cells.find((cell) => /[A-Z0-9]+:\\/\\//i.test(cell)) || "";
                        const proxy = parseProxyCell(proxyCell);
                        parsed.id = parsed.id || proxy.id;
                        parsed.type = parsed.type || proxy.type;
                        parsed.host = parsed.host || proxy.host;
                        parsed.port = parsed.port || proxy.port;
                        parsed.account = proxy.account;
                        parsed.password = proxy.password;
                        parsed.remark = cells[3] || "";
                        parsed.outbound_ip = cells[4] || "";
                    }}
                    return parsed;
                }})
                .filter((row) => row.text);
        }}
        """

    def _proxy_row_exists_by_id_script(self, proxy_id: str) -> str:
        return f"""
        () => Boolean(__ROW_BY_ID__())
        """.replace("__ROW_BY_ID__", self._proxy_row_by_id_function(proxy_id))

    def _proxy_row_text_by_id_script(self, proxy_id: str) -> str:
        return f"""
        () => {{
            const row = __ROW_BY_ID__();
            return row ? String(row.innerText || row.textContent || "") : "";
        }}
        """.replace("__ROW_BY_ID__", self._proxy_row_by_id_function(proxy_id))

    def _proxy_row_contains_text_script(self, proxy_id: str, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const row = __ROW_BY_ID__();
            return Boolean(row && (row.innerText || row.textContent || "").includes(expectedText));
        }}
        """.replace("__ROW_BY_ID__", self._proxy_row_by_id_function(proxy_id))

    def _proxy_row_cell_index_contains_text_script(self, proxy_id: str, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const row = __ROW_BY_ID__();
            if (!row) return -1;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
            return cells.findIndex((cell) => (cell.innerText || cell.textContent || "").includes(expectedText));
        }}
        """.replace("__ROW_BY_ID__", self._proxy_row_by_id_function(proxy_id))

    def _proxy_row_cell_text_by_index_script(self, proxy_id: str, cell_index: int) -> str:
        return f"""
        () => {{
            const row = __ROW_BY_ID__();
            if (!row) return "";
            const cellIndex = {int(cell_index)};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const cells = Array.from(row.querySelectorAll({self.locator("table_cell")!r})).filter(visible);
            const cell = cells[cellIndex] || null;
            return cell ? String(cell.innerText || cell.textContent || "") : "";
        }}
        """.replace("__ROW_BY_ID__", self._proxy_row_by_id_function(proxy_id))

    def _proxy_row_operation_button_by_position_script(self, proxy_id: str, position: str) -> str:
        if position not in {"first", "last"}:
            raise ValueError(f"unsupported proxy row operation position: {position}")
        return f"""
        () => {{
            const row = __ROW_BY_ID__();
            if (!row) return null;
            const position = {position!r};
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
            const candidates = Array.from(operationCell.querySelectorAll("button, [role='button'], .el-button, i, svg, span"))
                .filter(visible)
                .filter((el) => {{
                    const rect = el.getBoundingClientRect();
                    return rect.width >= 8 && rect.height >= 8;
                }})
                .map((el) => {{
                    const clickable = el.closest("button, [role='button'], .el-button") || el;
                    const rect = clickable.getBoundingClientRect();
                    return {{ el: clickable, x: rect.x, y: rect.y, area: rect.width * rect.height }};
                }})
                .filter((item, index, array) => array.findIndex((other) => other.el === item.el) === index)
                .sort((left, right) => left.x - right.x || left.y - right.y || left.area - right.area);
            if (!candidates.length) return null;
            return position === "first" ? candidates[0].el : candidates[candidates.length - 1].el;
        }}
        """.replace("__ROW_BY_ID__", self._proxy_row_by_id_function(proxy_id))

    def _clear_proxy_selection_script(self) -> str:
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
            const checkedBoxes = Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .filter((row) => Boolean(row.querySelector("input[type='checkbox']:checked, .el-checkbox.is-checked, .el-checkbox__input.is-checked")))
                .map((row) => row.querySelector(".el-checkbox") || row.querySelector("input[type='checkbox']"))
                .filter(Boolean);
            checkedBoxes.forEach((box) => {{
                box.click();
            }});
            return checkedBoxes.length;
        }}
        """

    def _proxy_row_selection_checkbox_script(self, proxy_id: str) -> str:
        return f"""
        () => {{
            const row = __ROW_BY_ID__();
            if (!row) return null;
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const candidates = Array.from(row.querySelectorAll(".el-checkbox, .el-checkbox__input, input[type='checkbox']"))
                .filter(visible)
                .map((el) => el.closest(".el-checkbox") || el);
            return candidates[0] || null;
        }}
        """.replace("__ROW_BY_ID__", self._proxy_row_by_id_function(proxy_id))

    def _proxy_selected_count_script(self) -> str:
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
            return Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .filter((row) => Boolean(row.querySelector("input[type='checkbox']:checked, .el-checkbox.is-checked, .el-checkbox__input.is-checked")))
                .length;
        }}
        """

    def _proxy_bulk_action_script(self, text: str) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const bodyText = document.body ? (document.body.innerText || "") : "";
            if (!bodyText.includes("已选")) return null;
            const candidates = Array.from(document.querySelectorAll("button, .el-button, [role='button'], span, div"))
                .filter(visible)
                .filter((el) => clean(el.innerText || el.textContent) === expectedText)
                .map((el) => {{
                    const clickable = el.closest("button, .el-button, [role='button']") || el;
                    const rect = clickable.getBoundingClientRect();
                    return {{ el: clickable, y: rect.y, x: rect.x, area: rect.width * rect.height }};
                }})
                .filter((item, index, array) => array.findIndex((other) => other.el === item.el) === index)
                .sort((left, right) => left.y - right.y || left.x - right.x || left.area - right.area);
            return candidates[0]?.el || null;
        }}
        """

    def _proxy_row_by_id_function(self, proxy_id: str) -> str:
        return f"""
        (() => {{
            const expectedId = {str(proxy_id).strip()!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            return Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .find((row) => (row.innerText || row.textContent || "").includes(`ID: ${{expectedId}}`))
                || null;
        }})
        """

    def _message_box_button_script(self, text: str) -> str:
        return self._confirmation_button_script(text)

    def _latest_message_box_footer_button_script(self) -> str:
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
            const overlays = Array.from(document.querySelectorAll(".el-message-box, .el-overlay-message-box"))
                .filter(visible)
                .map((overlay) => {
                    const rect = overlay.getBoundingClientRect();
                    const zIndex = Number.parseInt(window.getComputedStyle(overlay).zIndex, 10) || 0;
                    return { overlay, zIndex, y: rect.y, x: rect.x };
                })
                .sort((left, right) => (right.zIndex - left.zIndex) || (right.y - left.y) || (right.x - left.x));
            const overlay = overlays[0]?.overlay || null;
            if (!overlay) return null;
            const buttons = Array.from(overlay.querySelectorAll("button, .el-button, [role='button']"))
                .filter(visible)
                .map((button) => {
                    const rect = button.getBoundingClientRect();
                    return { button, y: rect.y, x: rect.x, area: rect.width * rect.height };
                })
                .sort((left, right) => (right.y - left.y) || (right.x - left.x) || (left.area - right.area));
            return buttons[0]?.button || null;
        }
        """

    def _confirmation_button_script(self, text: str) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const overlays = Array.from(document.querySelectorAll({self.locator("confirmation_overlay")!r}))
                .filter(visible)
                .map((overlay) => {{
                    const rect = overlay.getBoundingClientRect();
                    const zIndex = Number.parseInt(window.getComputedStyle(overlay).zIndex, 10) || 0;
                    return {{ overlay, zIndex, y: rect.y, x: rect.x }};
                }})
                .sort((left, right) => (right.zIndex - left.zIndex) || (right.y - left.y) || (right.x - left.x));
            for (const item of overlays) {{
                const button = Array.from(item.overlay.querySelectorAll({self.locator("button")!r}))
                    .filter(visible)
                    .find((candidate) => {{
                        const buttonText = clean(candidate.innerText || candidate.textContent);
                        return buttonText === expectedText || buttonText.includes(expectedText);
                    }});
                if (button) return button;
            }}
            return null;
        }}
        """

    def _active_confirmation_overlay_visible_script(self) -> str:
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
            const clean = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const expectedTexts = new Set(["确定删除", "确认删除", "确定", "确认"]);
            return Array.from(document.querySelectorAll({self.locator("confirmation_overlay")!r}))
                .filter(visible)
                .some((overlay) => Array.from(overlay.querySelectorAll({self.locator("button")!r}))
                    .filter(visible)
                    .some((button) => expectedTexts.has(clean(button.innerText || button.textContent))));
        }}
        """

    def _close_latest_overlay_script(self) -> str:
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
            const overlays = Array.from(document.querySelectorAll({self.locator("blocking_overlay")!r}))
                .filter(visible);
            const overlay = overlays[overlays.length - 1];
            if (!overlay) return false;
            const close = overlay.querySelector({self.locator("overlay_close_button")!r});
            if (!close || !visible(close)) return false;
            close.click();
            return true;
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
