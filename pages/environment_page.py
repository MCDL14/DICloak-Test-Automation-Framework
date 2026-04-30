from __future__ import annotations

import json
import time

from core.config import timeout_seconds as config_timeout_seconds
from core.process import main_process_ids, wait_for_new_main_process_ids
from pages.base_page import BasePage


class EnvironmentPage(BasePage):
    locator_file = "environment_locators.yaml"

    def open_list(self) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_menu_item_script("环境管理"))
        self._wait_for_environment_list()
        self.clear_selected_environments()

    def create_environment(self, name: str) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click("#createEnvBtn, button:has-text('创建环境')")
        self.cdp.fill("input[placeholder='请填写环境名称']", name)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()

    def create_environment_with_kernel(self, name: str, kernel_label: str) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click("#createEnvBtn, button:has-text('创建环境')")
        self.cdp.fill("input[placeholder='请填写环境名称']", name)
        self._expand_create_environment_fingerprint_settings()
        self._expand_more_fingerprint_settings()
        self._select_create_environment_kernel(kernel_label)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()

    def batch_create_environments(self, name_prefix: str, count: int) -> None:
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self.cdp.click_element_by_script(self._visible_text_element_script("批量创建"))
        self.cdp.fill("input[placeholder='请输入创建数量']", str(count))
        self.cdp.fill("input[placeholder='请输入环境名称前缀']", name_prefix)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()

    def batch_create_environments_with_kernel(self, name_prefix: str, count: int, kernel_label: str) -> None:
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self.cdp.click_element_by_script(self._visible_text_element_script("批量创建"))
        self.cdp.fill("input[placeholder='请输入创建数量']", str(count))
        self.cdp.fill("input[placeholder='请输入环境名称前缀']", name_prefix)
        self._expand_create_environment_fingerprint_settings()
        self._expand_more_fingerprint_settings()
        self._select_create_environment_kernel(kernel_label)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()

    def search_environment(self, name: str) -> None:
        # “序号/名称/备注”筛选框默认展示；直接 fill 触发 Vue/Element Plus 的真实输入绑定。
        self.clear_selected_environments()
        self._wait_for_search_input_visible()
        self._fill_search_input(name)
        self.cdp.click_element_by_script(self._search_button_script())
        self._wait_for_search_result(name)

    def clear_search(self) -> None:
        # 清空筛选按钮在搜索按钮右侧更靠后的位置；按输入框同一行、按钮 x 坐标顺序定位。
        self.clear_selected_environments()
        self._wait_for_search_input_visible()
        self.cdp.click_element_by_script(self._clear_search_button_script())
        self._wait_for_environment_list()

    def filter_by_environment_group(self, group_name: str) -> None:
        # 环境分组筛选框位于“序号/名称/备注”输入框左侧，筛选后需要点击搜索按钮才会刷新列表。
        self.clear_selected_environments()
        self._wait_for_environment_group_filter_visible()
        self.cdp.click_element_by_script(self._environment_group_filter_select_script())
        self.cdp.click_element_by_script(self._select_dropdown_option_script(group_name))
        self._wait_environment_group_filter_selected(group_name)
        self.cdp.click_element_by_script(self._search_button_script())
        self.wait_environment_groups_in_current_list(group_name)

    def environment_group_values_in_current_list(self) -> list[str]:
        return [
            str(row.get("group", "")).strip()
            for row in self._environment_rows()
            if str(row.get("group", "")).strip()
        ]

    def wait_environment_groups_in_current_list(
        self,
        group_name: str,
        timeout_seconds: int | None = None,
    ) -> list[str]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_groups: list[str] = []
        while time.time() < deadline:
            rows = self._environment_rows()
            last_groups = [
                str(row.get("group", "")).strip()
                for row in rows
                if str(row.get("group", "")).strip()
            ]
            if rows and last_groups and all(group == group_name for group in last_groups):
                return last_groups
            time.sleep(0.5)
        raise TimeoutError(
            "environment group filter result did not match expected group: "
            f"expected={group_name}, actual={last_groups}"
        )

    def dismiss_blocking_overlays(self) -> None:
        # 调试中断后可能残留创建环境抽屉、二次确认弹窗等，先关闭避免遮挡列表按钮。
        for _ in range(4):
            has_overlay = self.cdp.evaluate(
                """
                () => Boolean(document.querySelector(".el-drawer, .el-dialog, .el-message-box"))
                """
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
                    const selectors = [
                        ".el-drawer__close-btn",
                        ".el-dialog__headerbtn",
                        ".el-message-box__headerbtn",
                        ".el-overlay button[aria-label='Close']",
                    ];
                    for (const selector of selectors) {
                        const button = Array.from(document.querySelectorAll(selector)).find(visible);
                        if (button) {
                            button.click();
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
            if not clicked:
                self.cdp.press("Escape")
            time.sleep(0.5)

    def _wait_for_search_input_visible(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self._is_search_input_visible():
                return
            time.sleep(0.2)
        raise RuntimeError("environment search input did not appear")

    def _is_search_input_visible(self) -> bool:
        script = """
        () => {
            const input = document.querySelector("input[placeholder='序号/名称/备注']");
            if (!input) return false;
            const rect = input.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }
        """
        return bool(self.cdp.evaluate(script))

    def _fill_search_input(self, name: str) -> None:
        self.cdp.fill("input[placeholder='序号/名称/备注']", name)

    def _wait_for_environment_group_filter_visible(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(
                """
                () => {
                    const input = document.querySelector("input[placeholder='序号/名称/备注']");
                    if (!input) return false;
                    const inputRect = input.getBoundingClientRect();
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-select"))
                        .filter(visible)
                        .some((select) => {
                            const rect = select.getBoundingClientRect();
                            return rect.x < inputRect.x && Math.abs(rect.y - inputRect.y) < 30;
                        });
                }
                """
            ):
                return
            time.sleep(0.2)
        raise RuntimeError("environment group filter did not appear")

    def _environment_group_filter_select_script(self) -> str:
        # 环境分组筛选控件没有稳定的业务 id；按“搜索输入框左侧同一行最近的 el-select”定位。
        return """
        () => {
            const input = document.querySelector("input[placeholder='序号/名称/备注']");
            if (!input) return null;
            const inputRect = input.getBoundingClientRect();
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const selects = Array.from(document.querySelectorAll(".el-select"))
                .filter(visible)
                .map((select) => {
                    const rect = select.getBoundingClientRect();
                    return { select, rect };
                })
                .filter((item) => item.rect.x < inputRect.x)
                .filter((item) => Math.abs(item.rect.y - inputRect.y) < 30)
                .sort((left, right) => right.rect.x - left.rect.x);
            const select = selects[0]?.select || null;
            if (!select) return null;
            return select.querySelector(".el-select__wrapper, input") || select;
        }
        """

    def _wait_environment_group_filter_selected(self, group_name: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        expected = json.dumps(str(group_name))
        while time.time() < deadline:
            selected = self.cdp.evaluate(
                f"""
                () => {{
                    const expected = {expected};
                    const input = document.querySelector("input[placeholder='序号/名称/备注']");
                    if (!input) return false;
                    const inputRect = input.getBoundingClientRect();
                    const visible = (el) => {{
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    }};
                    const selects = Array.from(document.querySelectorAll(".el-select"))
                        .filter(visible)
                        .map((select) => {{
                            const rect = select.getBoundingClientRect();
                            return {{ select, rect }};
                        }})
                        .filter((item) => item.rect.x < inputRect.x)
                        .filter((item) => Math.abs(item.rect.y - inputRect.y) < 30)
                        .sort((left, right) => right.rect.x - left.rect.x);
                    const select = selects[0]?.select || null;
                    if (!select) return false;
                    const text = (select.innerText || select.textContent || "").trim();
                    const value = select.querySelector("input")?.value || "";
                    return text.includes(expected) || value.includes(expected);
                }}
                """,
            )
            if selected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"environment group filter was not selected: {group_name}")

    def _search_button_script(self) -> str:
        # 放大镜只负责提交搜索；按输入框右侧同一行的搜索按钮定位，避免点到表格行按钮。
        return """
        () => {
            const input = document.querySelector("input[placeholder='序号/名称/备注']");
            if (!input) return null;
            const inputRect = input.getBoundingClientRect();
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const buttons = Array.from(document.querySelectorAll("button"))
                .filter((button) => visible(button) && button.querySelector(".icon-search"))
                .map((button) => {
                    const rect = button.getBoundingClientRect();
                    return { button, rect };
                })
                .filter((item) => item.rect.x >= inputRect.x + inputRect.width)
                .filter((item) => Math.abs(item.rect.y - inputRect.y) < 30)
                .sort((left, right) => left.rect.x - right.rect.x);
            return buttons[0]?.button || null;
        }
        """

    def _clear_search_button_script(self) -> str:
        return """
        () => {
            const input = document.querySelector("input[placeholder='序号/名称/备注']");
            if (!input) return null;
            const inputRect = input.getBoundingClientRect();
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const buttons = Array.from(document.querySelectorAll("button"))
                .filter((button) => visible(button))
                .map((button) => {
                    const rect = button.getBoundingClientRect();
                    return { button, rect };
                })
                .filter((item) => item.rect.x >= inputRect.x + inputRect.width)
                .filter((item) => Math.abs(item.rect.y - inputRect.y) < 30)
                .sort((left, right) => left.rect.x - right.rect.x);
            return buttons[2]?.button || null;
        }
        """

    def _wait_for_search_result(self, keyword: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            rows = self._environment_rows()
            if rows and any(keyword in "\n".join(row.get("cells", [])) for row in rows):
                return
            time.sleep(0.5)
        raise TimeoutError(f"environment search result did not appear: {keyword}")

    def environment_exists(self, name: str) -> bool:
        self.search_environment_without_assert(name)
        deadline = time.time() + config_timeout_seconds(self.config, "search_result_seconds", 10)
        while time.time() < deadline:
            if self.environment_visible_in_current_list(name):
                return True
            if self._table_empty_text_visible():
                return False
            time.sleep(0.5)
        return False

    def environment_visible_in_current_list(self, name: str) -> bool:
        return any(row.get("name") == name for row in self._environment_rows())

    def environment_names_by_prefix_in_current_list(self, name_prefix: str) -> list[str]:
        return [
            str(row.get("name", ""))
            for row in self._environment_rows()
            if str(row.get("name", "")).startswith(name_prefix)
        ]

    def wait_environment_visible_in_current_list(self, name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.environment_visible_in_current_list(name):
                return
            time.sleep(0.5)
        raise TimeoutError(f"environment did not appear in current list: {name}")

    def wait_environment_absent_in_current_list(self, name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.environment_visible_in_current_list(name):
                return
            time.sleep(0.5)
        raise TimeoutError(f"environment still exists in current list: {name}")

    def wait_environment_count_by_prefix_in_current_list(
        self,
        name_prefix: str,
        expected_count: int,
        timeout_seconds: int | None = None,
    ) -> list[str]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_names: list[str] = []
        while time.time() < deadline:
            last_names = self.environment_names_by_prefix_in_current_list(name_prefix)
            if len(last_names) >= expected_count:
                return last_names[:expected_count]
            time.sleep(0.5)
        raise TimeoutError(
            "environment count by prefix did not reach expected count: "
            f"prefix={name_prefix}, expected={expected_count}, actual={len(last_names)}, names={last_names}"
        )

    def wait_no_environment_by_prefix_in_current_list(
        self,
        name_prefix: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.environment_names_by_prefix_in_current_list(name_prefix):
                return
            time.sleep(0.5)
        raise TimeoutError(f"environment still exists by prefix: {name_prefix}")

    def search_environment_without_assert(self, name: str) -> None:
        self.clear_selected_environments()
        self._wait_for_search_input_visible()
        self._fill_search_input(name)
        self.cdp.click_element_by_script(self._search_button_script())
        time.sleep(0.5)

    def open_environment(self, name: str) -> None:
        self.search_environment(name)
        self.click_environment_action(name, "打开")

    def close_environment(self, name: str) -> None:
        self.search_environment(name)
        self.click_environment_action(name, "关闭")

    def delete_environment(self, name: str) -> None:
        self.search_environment(name)
        self.delete_environment_from_current_list(name)
        self.wait_environment_deleted(name)

    def delete_environment_from_current_list(self, name: str) -> None:
        self.click_environment_more(name)
        self.click_visible_dropdown_item("删除")
        self.confirm_secondary_dialog()
        self.wait_environment_absent_in_current_list(name)

    def delete_environments_by_prefix_from_current_list(self, name_prefix: str) -> None:
        # 批量删除当前筛选结果中指定前缀的环境：勾选行 -> 顶部“更多操作” -> “删除环境” -> 确定。
        names = self.environment_names_by_prefix_in_current_list(name_prefix)
        if not names:
            return
        self.select_environments(names)
        self.delete_selected_environments_from_batch_menu()
        self.wait_no_environment_by_prefix_in_current_list(name_prefix)

    def click_environment_more(self, name: str) -> None:
        # 行内“打开”右侧的 icon-more 按钮，必须限定在目标环境所在行内点击。
        self.cdp.click_element_by_script(self._environment_more_button_script(name))

    def click_environment_more_by_serial(self, serial: str) -> None:
        # 环境名称会被编辑；编辑类用例用环境序号精确定位同一行。
        self.cdp.click_element_by_script(self._environment_more_button_by_serial_script(serial))

    def click_visible_dropdown_item(self, text: str) -> None:
        self.cdp.click_element_by_script(self._visible_dropdown_item_script(text))

    def confirm_secondary_dialog(self) -> None:
        # 删除环境的二次弹窗可能显示“确认”或“确定”，两个文案都兼容。
        try:
            self.cdp.click_element_by_script(self._active_overlay_button_script("确认"))
        except TimeoutError:
            self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()

    def confirm_secondary_dialog_if_present(self) -> None:
        if not self._active_overlay_visible():
            return
        self.confirm_secondary_dialog()

    def wait_environment_deleted(self, name: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "search_result_seconds", 10)
        while time.time() < deadline:
            self.search_environment_without_assert(name)
            if not any(row.get("name") == name for row in self._environment_rows()):
                return
            time.sleep(0.5)
        raise TimeoutError(f"environment was not deleted: {name}")

    def read_environment_table(self) -> str:
        return self.text("environment_table")

    def first_environment_name(self) -> str:
        rows = self._environment_rows()
        if not rows:
            raise RuntimeError("environment list has no visible rows")
        return str(rows[0].get("name", "")).strip()

    def first_environment_serial_and_name(self) -> tuple[str, str]:
        rows = self._environment_rows()
        if not rows:
            raise RuntimeError("environment list has no visible rows")
        return str(rows[0].get("serial", "")).strip(), str(rows[0].get("name", "")).strip()

    def environment_name_by_serial(self, serial: str) -> str:
        row = self._environment_row_by_serial(serial)
        return str(row.get("name", "")).strip()

    def environment_action_text(self, name: str) -> str:
        row = self._environment_row(name)
        return str(row.get("action", "")).strip()

    def click_environment_action(self, name: str, action_text: str) -> None:
        self.cdp.click_element_by_script(self._environment_action_element_script(name, action_text))

    def select_environments(self, names: list[str]) -> None:
        self.clear_selected_environments()
        for name in names:
            self.cdp.click_element_by_script(self._environment_checkbox_script(name))
        self._wait_selected_count(len(names))

    def clear_selected_environments(self) -> None:
        # 列表选择状态会影响顶部工具栏；用例开始和切换操作前统一清掉已有选择。
        for _ in range(5):
            selected_count = int(self._selected_environment_count())
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
        if self._selected_environment_count() != 0:
            raise TimeoutError("selected environments were not cleared")

    def click_batch_action(self, action_text: str) -> None:
        # 选中环境后顶部批量工具栏里的操作是 div 结构，不是 button；按可见文案定位可点击容器。
        self.cdp.click_element_by_script(self._batch_action_element_script(action_text))

    def delete_selected_environments_from_batch_menu(self) -> None:
        # 批量删除入口在顶部批量工具栏“更多操作”的 hover 菜单中，菜单项文案为“删除环境”。
        self.cdp.hover_element_by_script(self._batch_more_operation_script())
        self.cdp.click_element_by_script(self._batch_more_menu_item_script("删除环境"))
        self.confirm_secondary_dialog()

    def wait_environments_action_text(
        self,
        names: list[str],
        action_text: str,
        timeout_seconds: int | None = None,
    ) -> None:
        default_key = "environment_open_seconds" if action_text == "关闭" else "environment_close_seconds"
        default_value = 90 if action_text in {"打开", "关闭"} else 60
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, default_key, default_value)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            rows_by_name = {
                str(row.get("name", "")): str(row.get("action", "")).strip()
                for row in self._environment_rows()
            }
            if all(rows_by_name.get(name) == action_text for name in names):
                return
            time.sleep(0.5)
        states = {
            name: self.environment_action_text(name)
            for name in names
            if self.environment_visible_in_current_list(name)
        }
        raise TimeoutError(f"environment action text did not become {action_text}: states={states}")

    def open_environment_and_capture_pid(self, name: str, timeout_seconds: int | None = None) -> int:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "environment_open_seconds", 90)
        request = self.cdp.click_element_by_script_and_wait_for_request(
            script=self._environment_action_element_script(name, "打开"),
            url_contains="/open_env",
            method="PATCH",
            timeout=timeout_seconds * 1000,
        )
        return self._pid_from_open_env_request(request)

    def edit_environment_name_by_serial(self, serial: str, new_name: str) -> None:
        self.click_environment_more_by_serial(serial)
        self.click_visible_dropdown_item("编辑")
        self._wait_edit_environment_drawer_visible()
        self.cdp.fill("input[placeholder='请填写环境名称']", new_name)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._confirm_edit_save_message_if_present()
        self._wait_for_overlay_closed()

    def edit_environment_fixed_open_url(self, name: str, fixed_url: str) -> None:
        # 编辑环境 -> 高级设置 -> 固定打开网页。按表单标签定位 textarea，避免依赖输入框顺序。
        self.click_environment_more(name)
        self.click_visible_dropdown_item("编辑")
        self._wait_edit_environment_drawer_visible()
        self._expand_edit_environment_advanced_settings()
        self.cdp.fill_element_by_script(self._active_drawer_form_control_script("固定打开网页"), fixed_url)
        self._wait_active_drawer_form_control_value("固定打开网页", fixed_url)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._confirm_edit_save_message_if_present()
        self._wait_for_overlay_closed()

    def wait_environment_name_by_serial(
        self,
        serial: str,
        expected_name: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_name = ""
        while time.time() < deadline:
            try:
                last_name = self.environment_name_by_serial(serial)
                if last_name == expected_name:
                    return
            except Exception:
                pass
            time.sleep(0.5)
        raise TimeoutError(
            f"environment name did not become expected by serial: serial={serial}, "
            f"expected={expected_name}, actual={last_name}"
        )

    def open_selected_environments_and_capture_pids(
        self,
        expected_count: int,
        timeout_seconds: int | None = None,
    ) -> list[int]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "environment_open_seconds", 90)
        process_name = str(
            self.config.get("test_data", {})
            .get("kernel_integrity", {})
            .get("browser_process_name", "GinsBrowser.exe")
        )
        existing_pids = set(main_process_ids(process_name))
        requests = self.cdp.click_element_by_script_and_collect_requests(
            script=self._batch_action_element_script("打开环境"),
            url_contains="/open_env",
            method="PATCH",
            expected_count=expected_count,
            timeout=timeout_seconds * 1000,
            raise_on_timeout=False,
        )
        pids = [self._pid_from_open_env_request(request) for request in requests]
        if len(pids) >= expected_count:
            return pids[:expected_count]
        # 部分批量打开请求不经过当前 CDP page 事件；此时用点击前后的内核主进程 PID 差集兜底。
        fallback_pids = wait_for_new_main_process_ids(
            process_name,
            existing_pids,
            expected_count=expected_count,
            timeout_seconds=timeout_seconds,
        )
        return fallback_pids[:expected_count]


    def _environment_action_element_script(self, name: str, action_text: str) -> str:
        # 环境“打开/关闭”按钮不能全局按文案点，必须先匹配环境名称所在行，再在该行内找按钮。
        return f"""
        () => {{
            const expectedName = {name!r};
            const expectedAction = {action_text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const rows = Array.from(document.querySelectorAll(".el-table__row, tbody tr"))
                .filter((row) => visible(row) && (row.innerText || "").includes(expectedName));
            for (const row of rows) {{
                const button = Array.from(row.querySelectorAll("button"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedAction);
                if (button) return button;
            }}
            return null;
        }}
        """

    def _environment_more_button_script(self, name: str) -> str:
        return f"""
        () => {{
            const expectedName = {name!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const rows = Array.from(document.querySelectorAll(".el-table__row, tbody tr"))
                .filter((row) => visible(row) && (row.innerText || "").includes(expectedName));
            for (const row of rows) {{
                const button = Array.from(row.querySelectorAll("button.more-btn"))
                    .find((el) => visible(el) && el.querySelector(".icon-more"));
                if (button) return button;
            }}
            return null;
        }}
        """

    def _environment_more_button_by_serial_script(self, serial: str) -> str:
        return f"""
        () => {{
            const expectedSerial = {serial!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const rows = Array.from(document.querySelectorAll(".el-table__row, tbody tr"))
                .filter(visible);
            for (const row of rows) {{
                const cells = Array.from(row.querySelectorAll("td"))
                    .map((cell) => (cell.innerText || cell.textContent || "").trim())
                    .filter(Boolean);
                if (cells[0] !== expectedSerial) continue;
                const button = Array.from(row.querySelectorAll("button.more-btn"))
                    .find((el) => visible(el) && el.querySelector(".icon-more"));
                if (button) return button;
            }}
            return null;
        }}
        """

    def _environment_checkbox_script(self, name: str) -> str:
        return f"""
        () => {{
            const expectedName = {name!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const rows = Array.from(document.querySelectorAll(".el-table__row, tbody tr"))
                .filter((row) => visible(row) && (row.innerText || "").includes(expectedName));
            for (const row of rows) {{
                const checkbox = Array.from(row.querySelectorAll(".el-checkbox, label"))
                    .find((el) => visible(el));
                if (checkbox && !checkbox.classList.contains("is-checked")) return checkbox;
            }}
            return null;
        }}
        """

    def _expand_create_environment_fingerprint_settings(self) -> None:
        if self._create_environment_fingerprint_settings_expanded():
            return
        self.cdp.click_element_by_script(self._collapsed_active_drawer_collapse_header_script("指纹设置"))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self._create_environment_fingerprint_settings_expanded():
                return
            time.sleep(0.2)
        raise TimeoutError("create environment fingerprint settings did not expand")

    def _expand_more_fingerprint_settings(self) -> None:
        if self._browser_kernel_select_visible():
            return
        self.cdp.click_element_by_script(self._more_fingerprint_button_script())
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self._browser_kernel_select_visible():
                return
            time.sleep(0.2)
        raise TimeoutError("more fingerprint settings did not expand")

    def _select_create_environment_kernel(self, kernel_label: str) -> None:
        self.cdp.click_element_by_script(self._browser_kernel_select_script())
        self.cdp.click_element_by_script(self._select_dropdown_option_script(kernel_label))
        self._wait_create_environment_kernel_selected(kernel_label)

    def _expand_edit_environment_advanced_settings(self) -> None:
        if self._active_drawer_form_control_visible("固定打开网页"):
            return
        self.cdp.click_element_by_script(self._collapsed_active_drawer_collapse_header_script("高级设置"))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self._active_drawer_form_control_visible("固定打开网页"):
                return
            time.sleep(0.2)
        raise TimeoutError("edit environment advanced settings did not expand")

    def _active_drawer_form_control_visible(self, label_text: str) -> bool:
        return bool(self.cdp.evaluate(self._active_drawer_form_control_visible_script(label_text)))

    def _wait_active_drawer_form_control_value(self, label_text: str, expected_value: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            actual_value = self.cdp.evaluate(self._active_drawer_form_control_value_script(label_text))
            if actual_value == expected_value:
                return
            time.sleep(0.2)
        raise TimeoutError(f"form control value did not become expected: label={label_text}")

    def _active_drawer_form_control_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const expectedLabel = {label_text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
            for (const drawer of drawers.reverse()) {{
                const items = Array.from(drawer.querySelectorAll(".el-form-item"));
                for (const item of items) {{
                    const label = item.querySelector("label, .el-form-item__label");
                    if (!label || (label.innerText || label.textContent || "").trim() !== expectedLabel) continue;
                    const control = Array.from(item.querySelectorAll("textarea, input"))
                        .find((el) => visible(el) && !el.disabled && el.getAttribute("type") !== "radio");
                    if (control) return control;
                }}
            }}
            return null;
        }}
        """

    def _active_drawer_form_control_visible_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const finder = {self._active_drawer_form_control_script(label_text)};
            return Boolean(finder());
        }}
        """

    def _active_drawer_form_control_value_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const finder = {self._active_drawer_form_control_script(label_text)};
            const control = finder();
            return control ? String(control.value || "") : null;
        }}
        """

    def _active_drawer_collapse_header_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const drawers = Array.from(document.querySelectorAll(".el-drawer"))
                .filter(visible);
            for (const drawer of drawers.reverse()) {{
                const button = Array.from(drawer.querySelectorAll(".el-collapse-item__header, button"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (button && !button.classList.contains("is-active")) return button;
                if (button) return button;
            }}
            return null;
        }}
        """

    def _collapsed_active_drawer_collapse_header_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const drawers = Array.from(document.querySelectorAll(".el-drawer"))
                .filter(visible);
            for (const drawer of drawers.reverse()) {{
                const items = Array.from(drawer.querySelectorAll(".el-collapse-item"));
                for (const item of items) {{
                    const header = item.querySelector(".el-collapse-item__header");
                    if (!header || !visible(header)) continue;
                    if ((header.innerText || header.textContent || "").trim() !== expectedText) continue;
                    if (item.classList.contains("is-active") || header.classList.contains("is-active")) return null;
                    return header;
                }}
            }}
            return null;
        }}
        """

    def _create_environment_fingerprint_settings_expanded(self) -> bool:
        return bool(
            self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
                    for (const drawer of drawers.reverse()) {
                        const items = Array.from(drawer.querySelectorAll(".el-collapse-item"));
                        for (const item of items) {
                            const header = item.querySelector(".el-collapse-item__header");
                            if (!header || !visible(header)) continue;
                            if ((header.innerText || header.textContent || "").trim() !== "指纹设置") continue;
                            if (!item.classList.contains("is-active") && !header.classList.contains("is-active")) {
                                return false;
                            }
                            const content = item.querySelector(".el-collapse-item__content");
                            return Boolean(content && visible(content) && (content.innerText || "").includes("更多指纹"));
                        }
                    }
                    return false;
                }
                """
            )
        )

    def _more_fingerprint_button_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
            for (const drawer of drawers.reverse()) {
                const activeFingerprintItems = Array.from(drawer.querySelectorAll(".el-collapse-item.is-active"))
                    .filter((item) => {
                        const header = item.querySelector(".el-collapse-item__header");
                        return header && (header.innerText || header.textContent || "").trim() === "指纹设置";
                    });
                for (const item of activeFingerprintItems) {
                    const button = Array.from(item.querySelectorAll(".tw-cursor-pointer, div, span"))
                        .find((el) =>
                            visible(el)
                            && (el.innerText || el.textContent || "").trim() === "更多指纹"
                            && String(el.className || "").includes("tw-cursor-pointer")
                        );
                    if (button) return button;
                }
                const button = Array.from(drawer.querySelectorAll(".tw-cursor-pointer"))
                    .find((el) =>
                        visible(el)
                        && (el.innerText || el.textContent || "").trim() === "更多指纹"
                        && String(el.className || "").includes("tw-cursor-pointer")
                    );
                if (button) return button;
            }
            return null;
        }
        """

    def _browser_kernel_select_visible(self) -> bool:
        return bool(
            self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
                    for (const drawer of drawers.reverse()) {
                        const labels = Array.from(drawer.querySelectorAll("label, .el-form-item__label"))
                            .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "浏览器内核");
                        for (const label of labels) {
                            const formItem = label.closest(".el-form-item");
                            const wrapper = formItem?.querySelector(".el-select__wrapper");
                            if (wrapper && visible(wrapper)) return true;
                        }
                    }
                    return false;
                }
                """
            )
        )

    def _browser_kernel_select_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
            for (const drawer of drawers.reverse()) {
                const labels = Array.from(drawer.querySelectorAll("label, .el-form-item__label"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "浏览器内核");
                for (const label of labels) {
                    const formItem = label.closest(".el-form-item");
                    const wrapper = formItem?.querySelector(".el-select__wrapper");
                    if (wrapper && visible(wrapper)) return wrapper;
                }
            }
            return null;
        }
        """

    def _select_dropdown_option_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const poppers = Array.from(document.querySelectorAll(".el-select__popper, .el-popper"))
                .filter(visible);
            for (const popper of poppers) {{
                const item = Array.from(popper.querySelectorAll(".el-select-dropdown__item, li, span, div"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (item) return item.closest(".el-select-dropdown__item") || item;
            }}
            return null;
        }}
        """

    def _wait_create_environment_kernel_selected(self, kernel_label: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            selected = self.cdp.evaluate(
                f"""
                () => {{
                    const expectedText = {kernel_label!r};
                    const visible = (el) => {{
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    }};
                    const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
                    for (const drawer of drawers.reverse()) {{
                        const labels = Array.from(drawer.querySelectorAll("label, .el-form-item__label"))
                            .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "浏览器内核");
                        for (const label of labels) {{
                            const formItem = label.closest(".el-form-item");
                            if (formItem && (formItem.innerText || "").includes(expectedText)) return true;
                        }}
                    }}
                    return false;
                }}
                """
            )
            if selected:
                return
            time.sleep(0.3)
        raise TimeoutError(f"create environment kernel was not selected: {kernel_label}")

    def _batch_action_element_script(self, action_text: str) -> str:
        return f"""
        () => {{
            const expectedText = {action_text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const candidates = Array.from(document.querySelectorAll("div,span"))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
            for (const candidate of candidates) {{
                const clickable = candidate.closest(".tw-cursor-pointer") || candidate.parentElement;
                if (clickable && clickable.classList.contains("tw-cursor-pointer") && visible(clickable)) return clickable;
            }}
            for (const candidate of candidates) {{
                const childClickable = Array.from(candidate.querySelectorAll(".tw-cursor-pointer"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (childClickable) return childClickable;
            }}
            for (const candidate of candidates) {{
                const clickable = candidate.parentElement;
                if (clickable && visible(clickable)) return clickable;
            }}
            return null;
        }}
        """

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

    def _batch_more_menu_item_script(self, text: str) -> str:
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

    def _visible_dropdown_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const poppers = Array.from(document.querySelectorAll(".el-dropdown__popper, .el-popper"))
                .filter((el) => visible(el));
            for (const popper of poppers) {{
                const item = Array.from(popper.querySelectorAll(".el-dropdown-menu__item, li, button, span"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (item) return item;
            }}
            return null;
        }}
        """

    def _visible_text_element_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const candidates = Array.from(document.querySelectorAll("button,div,span,a"))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText)
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    return {{ el, area: rect.width * rect.height }};
                }})
                .sort((left, right) => left.area - right.area);
            return candidates[0]?.el || null;
        }}
        """

    def _visible_menu_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const candidates = Array.from(document.querySelectorAll(".el-menu-item, li, a, button"))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText)
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    return {{ el, visibleArea: Math.max(0, rect.width) * Math.max(0, Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0)) }};
                }})
                .sort((left, right) => right.visibleArea - left.visibleArea);
            return candidates[0]?.el || null;
        }}
        """

    def _active_overlay_button_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(".el-drawer, .el-dialog, .el-message-box"))
                .filter((el) => visible(el));
            for (const overlay of overlays.reverse()) {{
                const button = Array.from(overlay.querySelectorAll("button"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (button) return button;
            }}
            return null;
        }}
        """

    def _environment_action_rect(self, name: str, action_text: str) -> dict:
        script = f"""
        () => {{
            const expectedName = {name!r};
            const expectedAction = {action_text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const rows = Array.from(document.querySelectorAll(".el-table__row, tbody tr"))
                .filter((row) => visible(row) && (row.innerText || "").includes(expectedName));
            const row = rows[0];
            if (!row) return null;
            const button = Array.from(row.querySelectorAll("button"))
                .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedAction);
            if (!button) return null;
            const rect = button.getBoundingClientRect();
            return {{ x: rect.x, y: rect.y, width: rect.width, height: rect.height }};
        }}
        """
        rect = self.cdp.evaluate(script)
        if not rect:
            raise RuntimeError(f"environment action was not found: name={name}, action={action_text}")
        return rect

    def _selected_environment_count(self) -> int:
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

    def _wait_selected_count(self, expected_count: int) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self._selected_environment_count() == expected_count:
                return
            time.sleep(0.2)
        raise TimeoutError(f"selected environment count did not become {expected_count}")

    def _pid_from_open_env_request(self, request: dict[str, str]) -> int:
        # APP 打开环境时 /open_env 请求体里带内核主进程 PID，后续用该 PID 读取命令行和 CDP 端口。
        post_data = request.get("post_data", "")
        try:
            payload = json.loads(post_data)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"open_env request body is not valid JSON: {post_data}") from exc
        pid = str(payload.get("pid", "")).strip()
        if not pid.isdigit():
            raise RuntimeError(f"open_env request did not contain a valid pid: {post_data}")
        return int(pid)

    def wait_environment_action_text(
        self,
        name: str,
        action_text: str,
        timeout_seconds: int | None = None,
    ) -> None:
        default_key = "environment_open_seconds" if action_text == "关闭" else "environment_close_seconds"
        default_value = 90 if action_text in {"打开", "关闭"} else 60
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, default_key, default_value)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.environment_action_text(name) == action_text:
                return
            time.sleep(0.5)
        raise TimeoutError(f"environment action text did not become {action_text}: {name}")

    def _environment_row(self, name: str) -> dict:
        for row in self._environment_rows():
            if row.get("name") == name:
                return row
        raise RuntimeError(f"environment row was not found: {name}")

    def _environment_row_by_serial(self, serial: str) -> dict:
        for row in self._environment_rows():
            if str(row.get("serial", "")).strip() == str(serial).strip():
                return row
        raise RuntimeError(f"environment row was not found by serial: {serial}")

    def _environment_rows(self) -> list[dict]:
        # Element Plus 表格列可能动态隐藏/冻结；这里读取可见 tr/td，并约定 cells[1] 是环境名称列。
        script = """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(".el-table__row, tbody tr"))
                .filter((row) => visible(row))
                .map((row) => {
                    let cells = Array.from(row.querySelectorAll("td"))
                        .map((cell) => (cell.innerText || cell.textContent || "").trim())
                        .filter(Boolean);
                    if (cells.length === 0) {
                        cells = Array.from(row.querySelectorAll(".cell"))
                            .map((cell) => (cell.innerText || cell.textContent || "").trim())
                            .filter(Boolean);
                    }
                    const buttons = Array.from(row.querySelectorAll("button"))
                        .map((button) => (button.innerText || button.textContent || "").trim())
                        .filter(Boolean);
                    return {
                        serial: cells[0] || "",
                        name: cells[1] || "",
                        group: cells[3] || "",
                        cells,
                        action: buttons.find((text) => ["打开", "关闭"].includes(text)) || "",
                    };
                })
                .filter((row) => row.name);
        }
        """
        value = self.cdp.evaluate(script)
        return value if isinstance(value, list) else []

    def _wait_for_environment_list(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                if self._environment_rows():
                    return
            except Exception:
                pass
            time.sleep(0.5)
        raise TimeoutError("environment list did not appear")

    def _wait_for_overlay_closed(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible_overlay_count = self.cdp.evaluate(
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
            if int(visible_overlay_count or 0) == 0:
                return
            time.sleep(0.3)
        raise TimeoutError("overlay did not close")

    def _wait_edit_environment_drawer_visible(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-drawer"))
                        .some((drawer) => visible(drawer) && (drawer.innerText || "").includes("编辑环境"));
                }
                """
            )
            if visible:
                return
            time.sleep(0.3)
        raise TimeoutError("edit environment drawer did not appear")

    def _confirm_edit_save_message_if_present(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-message-box"))
                        .some((box) => visible(box) && (box.innerText || "").includes("是否确定保存编辑"));
                }
                """
            )
            if visible:
                self.cdp.click_element_by_script(
                    """
                    () => {
                        const visible = (el) => {
                            const rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        };
                        const boxes = Array.from(document.querySelectorAll(".el-message-box"))
                            .filter((box) => visible(box) && (box.innerText || "").includes("是否确定保存编辑"));
                        const box = boxes[boxes.length - 1];
                        if (!box) return null;
                        return Array.from(box.querySelectorAll("button"))
                            .find((button) => visible(button) && (button.innerText || button.textContent || "").trim() === "确定")
                            || null;
                    }
                    """
                )
                return
            time.sleep(0.2)

    def _active_overlay_visible(self) -> bool:
        return bool(
            self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-drawer, .el-dialog, .el-message-box"))
                        .some(visible);
                }
                """
            )
        )

    def _table_empty_text_visible(self) -> bool:
        script = """
        () => {
            const empty = document.querySelector(".el-table__empty-text, .el-empty__description");
            if (!empty) return false;
            const rect = empty.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }
        """
        return bool(self.cdp.evaluate(script))

    def _click_visible_text(self, text: str) -> None:
        script = f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const candidates = Array.from(document.querySelectorAll("li,button,div,span,a"))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText)
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    return {{ x: rect.x, y: rect.y, width: rect.width, height: rect.height, area: rect.width * rect.height }};
                }});
            candidates.sort((left, right) => left.area - right.area);
            return candidates[0] || null;
        }}
        """
        rect = self.cdp.evaluate(script)
        if not rect:
            raise RuntimeError(f"visible text was not found: {text}")
        self.cdp.click_at(float(rect["x"]) + float(rect["width"]) / 2, float(rect["y"]) + float(rect["height"]) / 2)
