from __future__ import annotations

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
                    "text": str(row.get("text", "") or "").strip(),
                }
            )
        return normalized

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

    def detect_proxy_in_create_dialog(self) -> str:
        self.cdp.click_element_by_script(self._create_dialog_button_script("检测代理"))
        return self.wait_create_dialog_detect_result()

    def wait_create_dialog_detect_result(self, timeout_seconds: int | None = None) -> str:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "proxy_detect_seconds", 45)
        deadline = time.time() + timeout_seconds
        last_text = ""
        while time.time() < deadline:
            result = str(self.cdp.evaluate(self._create_dialog_detect_result_script()) or "").strip()
            if result:
                return result
            last_text = str(self.cdp.evaluate(self._active_dialog_text_script()) or "").strip()
            time.sleep(0.5)
        raise TimeoutError(f"proxy detect result did not appear in create dialog: last_text={last_text}")

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
        while time.time() < deadline:
            current_index = self.cdp.evaluate(self._proxy_row_cell_index_contains_text_script(clean_id, "检测中"))
            if isinstance(current_index, int) and current_index >= 0:
                return current_index
            current_text = self.row_detect_result(clean_id)
            if current_text and current_text != before_clean:
                return None
            time.sleep(0.2)
        raise TimeoutError(f"proxy row detect status did not appear or change: id={clean_id}, before={before_clean}")

    def wait_row_detecting_hidden(self, proxy_id: str, timeout_seconds: int | None = None) -> int | None:
        clean_id = str(proxy_id).strip()
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "proxy_detect_seconds", 45)
        deadline = time.time() + timeout_seconds
        detecting_cell_index: int | None = None
        while time.time() < deadline:
            current_index = self.cdp.evaluate(self._proxy_row_cell_index_contains_text_script(clean_id, "检测中"))
            if isinstance(current_index, int) and current_index >= 0:
                detecting_cell_index = current_index
            if not self.cdp.evaluate(self._proxy_row_contains_text_script(clean_id, "检测中")):
                return detecting_cell_index
            time.sleep(0.5)
        raise TimeoutError(f"proxy row detect status did not disappear: id={clean_id}")

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

    def delete_proxy_by_id(self, proxy_id: str) -> None:
        clean_id = str(proxy_id).strip()
        if not clean_id:
            return
        if not self.proxy_exists_by_id(clean_id):
            return
        self.cdp.click_element_by_script(self._proxy_row_operation_button_by_position_script(clean_id, "last"))
        self.confirm_secondary_dialog()
        self.wait_proxy_absent(clean_id)

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

    def confirm_secondary_dialog(self, preferred_texts: tuple[str, ...] = ("确认删除", "确定", "确认")) -> None:
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
                && Boolean(Array.from(document.querySelectorAll({self.locator("table_container")!r})).find(visible));
        }}
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
            const match = `${value} ${text}`.match(/\\b(HTTP|HTTPS|SOCKS5|SOCKS4)\\b/i);
            return match ? match[1].toUpperCase() : "";
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
            const protocolPattern = /\\b(HTTP|HTTPS|SOCKS5|SOCKS4)\\b/i;
            const selects = Array.from(dialog.querySelectorAll(".el-select, .el-select__wrapper"))
                .filter(visible)
                .map((el) => {
                    const input = el.querySelector("input");
                    const rect = el.getBoundingClientRect();
                    const text = clean(el.innerText || el.textContent || "");
                    const value = clean(input ? input.value : "");
                    return { el, text, value, x: rect.x, y: rect.y };
                })
                .filter((item, index, array) => array.findIndex((other) => other.el === item.el) === index)
                .sort((left, right) => left.y - right.y || left.x - right.x);
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
            return options.find((item) => item.text === expectedText)?.option || null;
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

    def _active_dialog_text_script(self) -> str:
        return """
        () => {
            const dialog = __CREATE_DIALOG__();
            return dialog ? String(dialog.innerText || dialog.textContent || "") : "";
        }
        """.replace("__CREATE_DIALOG__", self._create_dialog_function())

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
            const parse = (text) => {{
                const idMatch = text.match(/ID:\\s*(\\d+)/);
                const proxyMatch = text.match(/([A-Z0-9]+):\\/\\/([^:\\s]+):(\\d+)/i);
                return {{
                    id: idMatch ? idMatch[1] : "",
                    type: proxyMatch ? proxyMatch[1].toUpperCase() : "",
                    host: proxyMatch ? proxyMatch[2] : "",
                    port: proxyMatch ? proxyMatch[3] : "",
                    text,
                }};
            }};
            return Array.from(document.querySelectorAll({self.locator("table_row")!r}))
                .filter(visible)
                .map((row) => parse(clean(row.innerText || row.textContent)))
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
            const expectedTexts = new Set(["确认删除", "确定", "确认"]);
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
