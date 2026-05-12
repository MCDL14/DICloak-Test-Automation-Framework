from __future__ import annotations

import json
import time
from pathlib import Path

from core.config import timeout_seconds as config_timeout_seconds
from core.process import main_process_ids, wait_for_new_main_process_ids
from pages.base_page import BasePage


class EnvironmentPage(BasePage):
    locator_file = "environment_locators.yaml"

    def recover_to_module_home(self) -> None:
        # Module recovery owns only Environment Management state. The global
        # recovery layer handles blocking overlays before this method is called.
        self.open_list()
        self.clear_search()
        self.clear_selected_environments()
        self.dismiss_blocking_overlays()

    def open_list(self) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_menu_item_script("环境管理"))
        self._wait_for_environment_list()
        self.clear_selected_environments()

    def create_environment(self, name: str) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_locator_script("create_button"))
        self.fill("environment_name_input", name)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()

    def create_environment_with_kernel(self, name: str, kernel_label: str) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_locator_script("create_button"))
        self.fill("environment_name_input", name)
        self._expand_create_environment_fingerprint_settings()
        self._expand_more_fingerprint_settings()
        self._select_create_environment_kernel(kernel_label)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()

    def create_environment_with_groups(self, name: str, group_names: list[str]) -> tuple[list[str], list[str]]:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_locator_script("create_button"))
        self.fill("environment_name_input", name)
        initial_groups = self.create_environment_selected_groups()
        self._select_create_environment_groups(group_names)
        expected_groups = self._unique_non_empty(initial_groups + self.create_environment_selected_groups() + group_names)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()
        return initial_groups, expected_groups

    def create_environment_with_tags(self, name: str, tag_names: list[str]) -> list[str]:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._visible_locator_script("create_button"))
        self.fill("environment_name_input", name)
        self.cdp.click_element_by_script(self._create_environment_set_tag_button_script())
        self._select_create_environment_tags(tag_names)
        selected_tags = self._unique_non_empty(tag_names)
        self.cdp.press("Escape")
        self._wait_select_dropdown_closed()
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()
        return selected_tags

    def batch_create_environments(self, name_prefix: str, count: int) -> None:
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self.cdp.click_element_by_script(self._visible_text_element_script("批量创建", "batch_create_button"))
        self.fill("batch_create_count_input", str(count))
        self.fill("batch_create_name_prefix_input", name_prefix)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()

    def batch_create_environments_with_kernel(self, name_prefix: str, count: int, kernel_label: str) -> None:
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self.cdp.click_element_by_script(self._visible_text_element_script("批量创建", "batch_create_button"))
        self.fill("batch_create_count_input", str(count))
        self.fill("batch_create_name_prefix_input", name_prefix)
        self._expand_create_environment_fingerprint_settings()
        self._expand_more_fingerprint_settings()
        self._select_create_environment_kernel(kernel_label)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()

    def batch_create_environments_with_groups(
        self,
        name_prefix: str,
        count: int,
        group_names: list[str],
    ) -> tuple[list[str], list[str]]:
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self.cdp.click_element_by_script(self._visible_text_element_script("批量创建", "batch_create_button"))
        self.fill("batch_create_count_input", str(count))
        self.fill("batch_create_name_prefix_input", name_prefix)
        initial_groups = self.create_environment_selected_groups()
        self._select_create_environment_groups(group_names)
        expected_groups = self._unique_non_empty(initial_groups + self.create_environment_selected_groups() + group_names)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()
        return initial_groups, expected_groups

    def batch_create_environments_with_tags(
        self,
        name_prefix: str,
        count: int,
        tag_names: list[str],
    ) -> list[str]:
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self.cdp.click_element_by_script(self._visible_text_element_script("批量创建", "batch_create_button"))
        self.fill("batch_create_count_input", str(count))
        self.fill("batch_create_name_prefix_input", name_prefix)
        self.cdp.click_element_by_script(self._create_environment_set_tag_button_script())
        self._select_create_environment_tags(tag_names)
        selected_tags = self._unique_non_empty(tag_names)
        self.cdp.press("Escape")
        self._wait_select_dropdown_closed()
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()
        return selected_tags

    def search_environment(self, name: str) -> None:
        # “序号/名称/备注”筛选框默认展示；直接 fill 触发 Vue/Element Plus 的真实输入绑定。
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self._wait_for_search_input_visible()
        self._fill_search_input(name)
        self.cdp.click_element_by_script(self._search_button_script())
        self._wait_for_search_result(name)

    def clear_search(self) -> None:
        # 清空筛选按钮在搜索按钮右侧更靠后的位置；按输入框同一行、按钮 x 坐标顺序定位。
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self._wait_for_search_input_visible()
        self.cdp.click_element_by_script(self._clear_search_button_script())
        self._wait_for_environment_list()

    def filter_by_environment_group(self, group_name: str) -> None:
        # 环境分组筛选框位于“序号/名称/备注”输入框左侧，筛选后需要点击搜索按钮才会刷新列表。
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self._wait_for_environment_group_filter_visible()
        self.cdp.click_element_by_script(self._environment_group_filter_select_script())
        self.cdp.click_element_by_script(self._select_dropdown_option_script(group_name))
        self._wait_environment_group_filter_selected(group_name)
        self.cdp.click_element_by_script(self._search_button_script())
        self.wait_environment_groups_in_current_list(group_name)

    def filter_by_remark_keyword(self, remark_keyword: str) -> None:
        # 备注筛选复用“序号/名称/备注”输入框；筛选后逐行校验备注列，而不是只判断页面有关键字。
        keyword = str(remark_keyword).strip()
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self._wait_for_search_input_visible()
        self._fill_search_input(keyword)
        self.cdp.click_element_by_script(self._search_button_script())
        self.wait_environment_remarks_contain_in_current_list(keyword)

    def filter_by_tag(self, tag_name: str) -> None:
        # 标签筛选位于“更多筛选”抽屉内；结果校验必须回到列表标签列，而不是读取筛选抽屉状态。
        tag = str(tag_name).strip()
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self._wait_for_search_input_visible()
        self.cdp.click_element_by_script(self._more_filter_button_script())
        self._wait_more_filter_drawer_visible()
        self.cdp.fill_element_by_script(self._filter_drawer_tag_input_script(), tag)
        self._click_filter_drawer_tag_option_if_present(tag)
        self.cdp.click_element_by_script(self._active_overlay_button_script("立即筛选"))
        self._wait_for_overlay_closed()
        self.wait_environment_tags_contain_in_current_list(tag)

    def environment_group_values_in_current_list(self) -> list[str]:
        return [
            str(row.get("group", "")).strip()
            for row in self._environment_rows()
            if str(row.get("group", "")).strip()
        ]

    def environment_group_values_by_name_in_current_list(self, name: str) -> list[str]:
        row = self._environment_row(name)
        return self._parse_environment_group_text(str(row.get("group", "")).strip())

    def environment_group_text_by_name_in_current_list(self, name: str) -> str:
        row = self._environment_row(name)
        return str(row.get("group", "")).strip()

    def environment_group_full_text_by_name_in_current_list(self, name: str) -> str:
        base_text = self.environment_group_text_by_name_in_current_list(name)
        if "查看" not in base_text:
            return base_text
        self.cdp.press("Escape")
        button_rect = self._element_rect_by_script(self._environment_group_view_button_script(name))
        self.cdp.click_element_by_script(self._environment_group_view_button_script(name))
        # 多分组折叠后必须点击当前行的“查看”，并读取与该按钮位置匹配的真实环境分组 popover。
        detail_text = self._wait_environment_group_detail_text(base_text, button_rect)
        self.cdp.press("Escape")
        return f"{base_text}\n{detail_text}".strip()

    def environment_group_text_by_serial(self, serial: str) -> str:
        row = self._environment_row_by_serial(serial)
        return str(row.get("group", "")).strip()

    def environment_group_full_text_by_serial(self, serial: str) -> str:
        base_text = self.environment_group_text_by_serial(serial)
        if "查看" not in base_text:
            return base_text
        self.cdp.press("Escape")
        button_rect = self._element_rect_by_script(self._environment_group_view_button_by_serial_script(serial))
        self.cdp.click_element_by_script(self._environment_group_view_button_by_serial_script(serial))
        detail_text = self._wait_environment_group_detail_text(base_text, button_rect)
        self.cdp.press("Escape")
        return f"{base_text}\n{detail_text}".strip()

    def environment_remark_values_in_current_list(self) -> list[str]:
        return [
            str(row.get("remark", "")).strip()
            for row in self._environment_rows()
            if str(row.get("remark", "")).strip()
        ]

    def environment_infos_in_current_list(self) -> list[dict[str, str]]:
        # 读取当前可见环境列表的核心字段，供导出、筛选等用例与外部文件内容做一致性校验。
        infos: list[dict[str, str]] = []
        for row in self._environment_rows():
            infos.append(
                {
                    "serial": str(row.get("serial", "")).strip(),
                    "name": str(row.get("name", "")).strip(),
                    "remark": str(row.get("remark", "")).strip(),
                    "group": str(row.get("group", "")).strip(),
                }
            )
        return infos

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

    def wait_environment_remarks_contain_in_current_list(
        self,
        remark_keyword: str,
        timeout_seconds: int | None = None,
    ) -> list[str]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        keyword = str(remark_keyword).strip()
        deadline = time.time() + timeout_seconds
        last_remarks: list[str] = []
        while time.time() < deadline:
            rows = self._environment_rows()
            last_remarks = [
                str(row.get("remark", "")).strip()
                for row in rows
                if str(row.get("remark", "")).strip()
            ]
            if rows and last_remarks and all(keyword in remark for remark in last_remarks):
                return last_remarks
            time.sleep(0.5)
        raise TimeoutError(
            "environment remark filter result did not match expected keyword: "
            f"expected_contains={keyword}, actual={last_remarks}"
        )

    def dismiss_blocking_overlays(self) -> None:
        # 调试中断后可能残留创建环境抽屉、二次确认弹窗等，先关闭避免遮挡列表按钮。
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
            const input = document.querySelector(__SEARCH_INPUT_SELECTOR__);
            if (!input) return false;
            const rect = input.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }
        """.replace("__SEARCH_INPUT_SELECTOR__", repr(self.locator("search_input")))
        return bool(self.cdp.evaluate(script))

    def _fill_search_input(self, name: str) -> None:
        self.fill("search_input", name)

    def _wait_for_environment_group_filter_visible(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(
                """
                () => {
                    const input = document.querySelector(__SEARCH_INPUT_SELECTOR__);
                    if (!input) return false;
                    const inputRect = input.getBoundingClientRect();
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(__SELECT_SELECTOR__))
                        .filter(visible)
                        .some((select) => {
                            const rect = select.getBoundingClientRect();
                            return rect.x < inputRect.x && Math.abs(rect.y - inputRect.y) < 30;
                        });
                }
                """.replace("__SEARCH_INPUT_SELECTOR__", repr(self.locator("search_input"))).replace(
                    "__SELECT_SELECTOR__",
                    repr(self.locator("select")),
                )
            ):
                return
            time.sleep(0.2)
        raise RuntimeError("environment group filter did not appear")

    def _environment_group_filter_select_script(self) -> str:
        # 环境分组筛选控件没有稳定的业务 id；按“搜索输入框左侧同一行最近的 el-select”定位。
        return """
        () => {
            const input = document.querySelector(__SEARCH_INPUT_SELECTOR__);
            if (!input) return null;
            const inputRect = input.getBoundingClientRect();
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const selects = Array.from(document.querySelectorAll(__SELECT_SELECTOR__))
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
        """.replace("__SEARCH_INPUT_SELECTOR__", repr(self.locator("search_input"))).replace(
            "__SELECT_SELECTOR__",
            repr(self.locator("select")),
        )

    def _wait_environment_group_filter_selected(self, group_name: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        expected = json.dumps(str(group_name))
        while time.time() < deadline:
            selected = self.cdp.evaluate(
                f"""
                () => {{
                    const expected = {expected};
                    const input = document.querySelector({self.locator("search_input")!r});
                    if (!input) return false;
                    const inputRect = input.getBoundingClientRect();
                    const visible = (el) => {{
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    }};
                    const selects = Array.from(document.querySelectorAll({self.locator("select")!r}))
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

    def _click_filter_drawer_tag_option_if_present(self, tag_name: str) -> None:
        try:
            self.cdp.click_element_by_script(self._filter_drawer_tag_option_script(tag_name), timeout=1500)
        except TimeoutError:
            pass

    def _search_button_script(self) -> str:
        # 放大镜只负责提交搜索；按输入框右侧同一行的搜索按钮定位，避免点到表格行按钮。
        return """
        () => {
            const input = document.querySelector(__SEARCH_INPUT_SELECTOR__);
            if (!input) return null;
            const inputRect = input.getBoundingClientRect();
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const buttons = Array.from(document.querySelectorAll(__BUTTON_SELECTOR__))
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
        """.replace("__SEARCH_INPUT_SELECTOR__", repr(self.locator("search_input"))).replace(
            "__BUTTON_SELECTOR__",
            repr(self.locator("button")),
        )

    def _more_filter_button_script(self) -> str:
        # 更多筛选入口位于搜索按钮右侧、清除筛选按钮左侧；同一行按钮按 x 坐标排序后取第二个。
        return """
        () => {
            const input = document.querySelector(__SEARCH_INPUT_SELECTOR__);
            if (!input) return null;
            const inputRect = input.getBoundingClientRect();
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const buttons = Array.from(document.querySelectorAll(__BUTTON_SELECTOR__))
                .filter((button) => visible(button))
                .map((button) => {
                    const rect = button.getBoundingClientRect();
                    return { button, rect };
                })
                .filter((item) => item.rect.x >= inputRect.x + inputRect.width)
                .filter((item) => Math.abs(item.rect.y - inputRect.y) < 30)
                .sort((left, right) => left.rect.x - right.rect.x);
            return buttons[1]?.button || null;
        }
        """.replace("__SEARCH_INPUT_SELECTOR__", repr(self.locator("search_input"))).replace(
            "__BUTTON_SELECTOR__",
            repr(self.locator("button")),
        )

    def _filter_drawer_tag_input_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const clean = (value) => String(value || "").trim();
            const drawers = Array.from(document.querySelectorAll(__DRAWER_SELECTOR__))
                .filter((drawer) => visible(drawer) && (drawer.innerText || "").includes("立即筛选"));
            for (const drawer of drawers.reverse()) {
                const items = Array.from(drawer.querySelectorAll(__FORM_ITEM_SELECTOR__));
                for (const item of items) {
                    const label = item.querySelector("label, .el-form-item__label");
                    if (!label || clean(label.innerText || label.textContent) !== "标签") continue;
                    const input = Array.from(item.querySelectorAll(__INPUT_SELECTOR__))
                        .find((el) => visible(el) && !el.disabled && !el.readOnly);
                    if (input) return input;
                }
            }
            return null;
        }
        """.replace("__DRAWER_SELECTOR__", repr(self.locator("drawer"))).replace(
            "__FORM_ITEM_SELECTOR__",
            repr(self.locator("form_item")),
        ).replace("__INPUT_SELECTOR__", repr(self.locator("input")))

    def _filter_drawer_tag_option_script(self, tag_name: str) -> str:
        return f"""
        () => {{
            const expectedText = {tag_name!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const clean = (value) => String(value || "").trim();
            const poppers = Array.from(document.querySelectorAll(".el-popper, .el-select__popper"))
                .filter((popper) => visible(popper) && (popper.innerText || "").includes(expectedText));
            for (const popper of poppers.reverse()) {{
                const candidates = Array.from(popper.querySelectorAll(".el-select-dropdown__item, li, div, span"))
                    .filter((el) => visible(el) && clean(el.innerText || el.textContent) === expectedText)
                    .map((el) => {{
                        const rect = el.getBoundingClientRect();
                        return {{ el, area: rect.width * rect.height }};
                    }})
                    .sort((left, right) => left.area - right.area);
                if (candidates.length) return candidates[0].el;
            }}
            return null;
        }}
        """

    def _clear_search_button_script(self) -> str:
        return """
        () => {
            const input = document.querySelector(__SEARCH_INPUT_SELECTOR__);
            if (!input) return null;
            const inputRect = input.getBoundingClientRect();
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const buttons = Array.from(document.querySelectorAll(__BUTTON_SELECTOR__))
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
        """.replace("__SEARCH_INPUT_SELECTOR__", repr(self.locator("search_input"))).replace(
            "__BUTTON_SELECTOR__",
            repr(self.locator("button")),
        )

    def _tag_management_button_script(self) -> str:
        # 标签管理按钮位于清除筛选按钮右侧；同一行按钮按 x 坐标排序后取清除按钮后一个。
        return """
        () => {
            const input = document.querySelector(__SEARCH_INPUT_SELECTOR__);
            if (!input) return null;
            const inputRect = input.getBoundingClientRect();
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const buttons = Array.from(document.querySelectorAll(__BUTTON_SELECTOR__))
                .filter((button) => visible(button))
                .map((button) => {
                    const rect = button.getBoundingClientRect();
                    return { button, rect };
                })
                .filter((item) => item.rect.x >= inputRect.x + inputRect.width)
                .filter((item) => Math.abs(item.rect.y - inputRect.y) < 30)
                .sort((left, right) => left.rect.x - right.rect.x);
            return buttons[3]?.button || null;
        }
        """.replace("__SEARCH_INPUT_SELECTOR__", repr(self.locator("search_input"))).replace(
            "__BUTTON_SELECTOR__",
            repr(self.locator("button")),
        )

    def _wait_for_search_result(self, keyword: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            rows = self._environment_rows()
            if rows and all(keyword in "\n".join(row.get("cells", [])) for row in rows):
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

    def environment_row_cells_in_current_list(self, name: str) -> list[str]:
        row = self._environment_row(name)
        cells = row.get("cells", [])
        return [str(cell).strip() for cell in cells if str(cell).strip()] if isinstance(cells, list) else []

    def wait_environment_row_cells_contain(
        self,
        name: str,
        expected_values: list[str],
        timeout_seconds: int | None = None,
    ) -> list[str]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        expected = self._unique_non_empty(expected_values)
        last_cells: list[str] = []
        while time.time() < deadline:
            last_cells = self.environment_row_cells_in_current_list(name)
            row_text = "\n".join(last_cells)
            if all(value in row_text for value in expected):
                return last_cells
            time.sleep(0.5)
        raise TimeoutError(f"environment row cells did not contain expected values: expected={expected}, actual={last_cells}")

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
        self.dismiss_blocking_overlays()
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

    def confirm_secondary_dialog(self, preferred_texts: tuple[str, ...] = ("确定", "确认")) -> None:
        # 二次确认弹窗在不同业务里可能显示“确定”或“确认”；逐个短超时探测，避免等满默认 10 秒。
        last_error: TimeoutError | None = None
        for text in preferred_texts:
            try:
                self.cdp.click_element_by_script(self._active_overlay_button_script(text), timeout=1000)
                self._wait_for_overlay_closed()
                return
            except TimeoutError as exc:
                last_error = exc
        raise TimeoutError(f"secondary dialog confirm button was not found: {preferred_texts}") from last_error

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
        return self.environment_name_at_position(1)

    def environment_name_at_position(self, position: int) -> str:
        rows = self._environment_rows()
        if position <= 0:
            raise ValueError(f"environment row position must be 1-based: {position}")
        if len(rows) < position:
            raise RuntimeError(f"environment list has fewer than {position} visible rows: actual={len(rows)}")
        return str(rows[position - 1].get("name", "")).strip()

    def first_environment_serial_and_name(self) -> tuple[str, str]:
        rows = self._environment_rows()
        if not rows:
            raise RuntimeError("environment list has no visible rows")
        return str(rows[0].get("serial", "")).strip(), str(rows[0].get("name", "")).strip()

    def environment_serial_at_position(self, position: int) -> str:
        rows = self._environment_rows()
        if position <= 0:
            raise ValueError(f"environment row position must be 1-based: {position}")
        if len(rows) < position:
            raise RuntimeError(f"environment list has fewer than {position} visible rows: actual={len(rows)}")
        return str(rows[position - 1].get("serial", "")).strip()

    def first_environment_serial(self) -> str:
        return self.environment_serial_at_position(1)

    def environment_serials_at_positions(self, count: int) -> list[str]:
        rows = self._environment_rows()
        if count <= 0:
            raise ValueError(f"environment row count must be positive: {count}")
        if len(rows) < count:
            raise RuntimeError(f"environment list has fewer than {count} visible rows: actual={len(rows)}")
        return [str(row.get("serial", "")).strip() for row in rows[:count]]

    def environment_serials_in_current_list(self) -> list[int]:
        serials: list[int] = []
        for row in self._environment_rows():
            serial_text = str(row.get("serial", "")).strip()
            if not serial_text:
                continue
            try:
                serials.append(int(serial_text))
            except ValueError:
                continue
        return serials

    def environment_serial_sort_state(self) -> str:
        # Element Plus 会把当前排序方向挂在表头 th class 上：ascending、descending 或无排序。
        value = self.cdp.evaluate(
            """
            () => {
                const th = (() => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-table__header th, thead th"))
                        .filter(visible)
                        .find((item) => (item.innerText || item.textContent || "").trim().includes("环境序号"));
                })();
                if (!th) return "unknown";
                if (th.classList.contains("ascending")) return "ascending";
                if (th.classList.contains("descending")) return "descending";
                return "none";
            }
            """
        )
        return str(value or "unknown")

    def clear_environment_serial_sort_if_active(self) -> None:
        state = self.environment_serial_sort_state()
        if state not in {"ascending", "descending"}:
            return
        self.click_environment_serial_sort(state)
        self.wait_environment_serial_sort_state("none")

    def click_environment_serial_sort(self, direction: str) -> None:
        if direction not in {"ascending", "descending"}:
            raise ValueError(f"unsupported environment serial sort direction: {direction}")
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._environment_serial_sort_caret_script(direction))

    def wait_environment_serial_sort_state(
        self,
        expected_state: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_state = ""
        while time.time() < deadline:
            last_state = self.environment_serial_sort_state()
            if last_state == expected_state:
                return
            time.sleep(0.2)
        raise TimeoutError(
            "environment serial sort state did not become expected: "
            f"expected={expected_state}, actual={last_state}"
        )

    def wait_environment_serials_sorted(
        self,
        direction: str,
        timeout_seconds: int | None = None,
    ) -> list[int]:
        if direction not in {"ascending", "descending"}:
            raise ValueError(f"unsupported environment serial sort direction: {direction}")
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_serials: list[int] = []
        while time.time() < deadline:
            last_serials = self.environment_serials_in_current_list()
            if len(last_serials) >= 2 and self._serials_match_sort(last_serials, direction):
                return last_serials
            time.sleep(0.5)
        raise TimeoutError(
            "environment serials did not match sort direction: "
            f"direction={direction}, serials={last_serials}"
        )

    def sortable_header_sort_buttons_visible_by_header(self) -> dict[str, bool]:
        value = self.cdp.evaluate(self._sortable_header_sort_buttons_visible_by_header_script())
        if not isinstance(value, dict):
            return {}
        return {str(key): bool(item) for key, item in value.items() if str(key).strip()}

    def wait_all_header_sort_buttons_hidden(self, timeout_seconds: int | None = None) -> dict[str, bool]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_states: dict[str, bool] = {}
        while time.time() < deadline:
            last_states = self.sortable_header_sort_buttons_visible_by_header()
            if last_states and not any(last_states.values()):
                return last_states
            time.sleep(0.3)
        raise TimeoutError(f"table header sort buttons were still visible: {last_states}")

    def wait_header_sort_buttons_visible(self, timeout_seconds: int | None = None) -> dict[str, bool]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_states: dict[str, bool] = {}
        while time.time() < deadline:
            last_states = self.sortable_header_sort_buttons_visible_by_header()
            if last_states and any(last_states.values()) and last_states.get("环境序号"):
                return last_states
            time.sleep(0.3)
        raise TimeoutError(f"table header sort buttons did not become visible: {last_states}")

    def wait_environment_tags_contain_in_current_list(
        self,
        tag_name: str,
        timeout_seconds: int | None = None,
    ) -> dict[str, list[str]]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        expected_tag = str(tag_name).strip()
        deadline = time.time() + timeout_seconds
        last_values: dict[str, list[str]] = {}
        while time.time() < deadline:
            last_values = self.environment_tag_values_in_current_list()
            if last_values and all(expected_tag in tags for tags in last_values.values()):
                return last_values
            time.sleep(0.5)
        raise TimeoutError(f"environment tag filter result mismatch: expected={expected_tag}, actual={last_values}")

    def environment_header_texts(self) -> list[str]:
        value = self.cdp.evaluate(
            """
            () => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };
                return Array.from(document.querySelectorAll(".el-table__header th, thead th"))
                    .filter(visible)
                    .map((th) => (th.innerText || th.textContent || "").trim())
                    .filter(Boolean);
            }
            """
        )
        return value if isinstance(value, list) else []

    def environment_business_header_texts(self) -> list[str]:
        return [
            header
            for header in self.environment_header_texts()
            if header and header != "操作"
        ]

    def column_settings_button_visible(self) -> bool:
        return bool(self.cdp.evaluate(self._column_settings_button_visible_script()))

    def wait_column_settings_button_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.column_settings_button_visible():
                return
            time.sleep(0.3)
        raise TimeoutError("column settings button did not become visible")

    def wait_column_settings_button_hidden(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.column_settings_button_visible():
                return
            time.sleep(0.3)
        raise TimeoutError("column settings button did not become hidden")

    def verify_column_settings_button_clickable(self) -> None:
        self.open_column_settings()
        self.dismiss_blocking_overlays()
        self._wait_for_environment_list()

    def open_column_settings(self) -> None:
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._column_settings_button_script())
        self._wait_column_settings_dialog_visible()

    def move_column_before(self, source_text: str, target_text: str) -> None:
        self.cdp.drag_element_by_script_to_element_by_script(
            self._column_settings_sort_icon_script(source_text),
            self._column_settings_sortable_item_script(target_text),
            target_y_ratio=-0.2,
        )
        self._wait_column_settings_field_before(source_text, target_text)

    def move_column_after(self, source_text: str, target_text: str) -> None:
        self.cdp.drag_element_by_script_to_element_by_script(
            self._column_settings_sort_icon_script(source_text),
            self._column_settings_sortable_item_script(target_text),
            target_y_ratio=1.2,
        )
        self._wait_column_settings_field_after(source_text, target_text)

    def confirm_column_settings(self) -> None:
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()
        self._wait_for_environment_list()

    def open_tag_management(self) -> None:
        # 标签管理入口在清除筛选按钮右侧，按搜索输入框同一行按钮的横向顺序定位。
        self.dismiss_blocking_overlays()
        self.clear_selected_environments()
        self._wait_for_search_input_visible()
        self.cdp.click_element_by_script(self._tag_management_button_script())
        self._wait_tag_management_dialog_visible()

    def create_tag(self, tag_name: str) -> None:
        # “标签管理”弹窗内创建标签：先点“创建标签”，再填写标签名称并点“创建”。
        self.cdp.click_element_by_script(self._tag_management_button_by_text_script("创建标签"))
        self.cdp.fill_element_by_script(self._tag_name_input_script(), tag_name)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self.wait_tag_visible(tag_name)

    def delete_tag(self, tag_name: str) -> None:
        # 标签列表操作列第二个按钮是删除入口；删除后如出现二次确认弹窗则兼容确认。
        self.cdp.click_element_by_script(self._tag_delete_button_script(tag_name))
        self._confirm_message_box_if_present()
        self.wait_tag_absent(tag_name)

    def wait_tag_visible(self, tag_name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._tag_exists_in_management_dialog(tag_name):
                return
            time.sleep(0.3)
        raise TimeoutError(f"tag was not visible in tag management dialog: {tag_name}")

    def wait_tag_absent(self, tag_name: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self._tag_exists_in_management_dialog(tag_name):
                return
            time.sleep(0.3)
        raise TimeoutError(f"tag was still visible in tag management dialog: {tag_name}")

    def tag_exists_in_management(self, tag_name: str) -> bool:
        return self._tag_exists_in_management_dialog(tag_name)

    def close_tag_management(self) -> None:
        self.cdp.click_element_by_script(self._tag_management_close_button_script())
        self._wait_for_overlay_closed()

    def wait_header_order(self, expected_prefix: list[str], timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_headers: list[str] = []
        while time.time() < deadline:
            last_headers = self.environment_header_texts()
            if last_headers[: len(expected_prefix)] == expected_prefix:
                return
            time.sleep(0.5)
        raise TimeoutError(f"header order did not match expected prefix: expected={expected_prefix}, actual={last_headers}")

    def wait_business_headers_equal(
        self,
        expected_headers: list[str],
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        expected = [str(item).strip() for item in expected_headers if str(item).strip()]
        deadline = time.time() + timeout_seconds
        last_headers: list[str] = []
        while time.time() < deadline:
            last_headers = self.environment_business_header_texts()
            if last_headers == expected:
                return
            time.sleep(0.5)
        raise TimeoutError(f"business headers did not match expected: expected={expected}, actual={last_headers}")

    def environment_row_count_in_current_page(self) -> int:
        return len(self._environment_rows())

    def pagination_size_selector_visible(self) -> bool:
        return bool(self.cdp.evaluate(self._pagination_size_selector_visible_script()))

    def wait_pagination_size_selector_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.pagination_size_selector_visible():
                return
            time.sleep(0.3)
        raise TimeoutError("pagination size selector did not become visible")

    def wait_pagination_size_selector_hidden(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self.pagination_size_selector_visible():
                return
            time.sleep(0.3)
        raise TimeoutError("pagination size selector did not become hidden")

    def set_pagination_size(self, page_size_text: str) -> None:
        normalized = str(page_size_text or "").replace(" ", "").strip()
        if not normalized:
            raise ValueError("pagination page size must not be empty")
        self.wait_pagination_size_selector_visible()
        if self.cdp.evaluate(self._pagination_size_selected_script(normalized)):
            return
        self.cdp.click_element_by_script(self._pagination_size_selector_script())
        self.cdp.click_element_by_script(self._visible_dropdown_item_by_normalized_text_script(normalized))
        self.wait_pagination_size_selected(normalized)

    def wait_pagination_size_selected(self, page_size_text: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        normalized = str(page_size_text or "").replace(" ", "").strip()
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._pagination_size_selected_script(normalized)):
                return
            time.sleep(0.3)
        raise TimeoutError(f"pagination size was not selected: expected={normalized}")

    def wait_current_page_row_count_between(
        self,
        min_exclusive: int,
        max_inclusive: int,
        timeout_seconds: int | None = None,
    ) -> int:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_count = 0
        while time.time() < deadline:
            last_count = self.environment_row_count_in_current_page()
            if min_exclusive < last_count <= max_inclusive:
                return last_count
            time.sleep(0.5)
        raise TimeoutError(
            "current page environment row count did not fall within expected range: "
            f"min_exclusive={min_exclusive}, max_inclusive={max_inclusive}, actual={last_count}"
        )

    def wait_current_page_row_count(self, expected_count: int, timeout_seconds: int | None = None) -> int:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_count = 0
        while time.time() < deadline:
            last_count = self.environment_row_count_in_current_page()
            if last_count == expected_count:
                return last_count
            time.sleep(0.5)
        raise TimeoutError(f"current page environment row count mismatch: expected={expected_count}, actual={last_count}")

    def environment_name_by_serial(self, serial: str) -> str:
        row = self._environment_row_by_serial(serial)
        return str(row.get("name", "")).strip()

    def wait_environment_by_serial_visible(self, serial: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                self._environment_row_by_serial(serial)
                return
            except RuntimeError:
                time.sleep(0.5)
        raise TimeoutError(f"environment row was not visible by serial: {serial}")

    def top_environment_by_serial(self, serial: str) -> None:
        # 行内“置顶”会调用 env/batch/top；等待接口响应后再交给用例校验列表排序。
        self.click_environment_more_by_serial(serial)
        response = self.cdp.click_element_by_script_and_wait_for_response(
            self._visible_dropdown_item_script("置顶"),
            "env/batch/top",
        )
        self._assert_response_success(response, "top environment")

    def cancel_top_environment_by_serial(self, serial: str) -> None:
        # 取消置顶使用同一个 env/batch/top 接口，菜单文案变为“取消置顶”。
        self.click_environment_more_by_serial(serial)
        response = self.cdp.click_element_by_script_and_wait_for_response(
            self._visible_dropdown_item_script("取消置顶"),
            "env/batch/top",
        )
        self._assert_response_success(response, "cancel top environment")

    def wait_first_environment_serial(
        self,
        serial: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_serial = ""
        while time.time() < deadline:
            last_serial = self.first_environment_serial()
            if last_serial == serial:
                return
            time.sleep(0.5)
        raise TimeoutError(f"first environment serial did not become expected: expected={serial}, actual={last_serial}")

    def wait_first_environment_serial_not(
        self,
        serial: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "search_result_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_serial = ""
        while time.time() < deadline:
            last_serial = self.first_environment_serial()
            if last_serial != serial:
                return
            time.sleep(0.5)
        raise TimeoutError(f"first environment serial was still unexpected top serial: {last_serial}")

    def environment_action_text(self, name: str) -> str:
        row = self._environment_row(name)
        return str(row.get("action", "")).strip()

    def click_environment_action(self, name: str, action_text: str) -> None:
        self.cdp.click_element_by_script(self._environment_action_element_script(name, action_text))

    def forbidden_open_environment_dialog_visible(self) -> bool:
        return bool(self.cdp.evaluate(self._forbidden_open_environment_dialog_visible_script()))

    def wait_for_forbidden_open_environment_dialog(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.forbidden_open_environment_dialog_visible():
                return
            time.sleep(0.2)
        raise TimeoutError("禁止打开环境 dialog did not appear")

    def wait_no_forbidden_open_environment_dialog(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or 3
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.forbidden_open_environment_dialog_visible():
                raise AssertionError("禁止打开环境 dialog appeared unexpectedly")
            time.sleep(0.2)

    def close_forbidden_open_environment_dialog(self) -> None:
        self.cdp.click_element_by_script(self._forbidden_open_environment_dialog_close_button_script())
        self._wait_for_overlay_closed()

    def select_environments(self, names: list[str]) -> None:
        self.clear_selected_environments()
        for name in names:
            self.cdp.click_element_by_script(self._environment_checkbox_script(name))
        self._wait_selected_count(len(names))

    def select_environments_by_serials(self, serials: list[str]) -> None:
        # 批量编辑这类用例不能依赖环境名称，按环境序号逐行勾选能避免名称变更带来的误选。
        self.clear_selected_environments()
        clean_serials = self._unique_non_empty(serials)
        for serial in clean_serials:
            self.cdp.click_element_by_script(self._environment_checkbox_by_serial_script(serial))
        self._wait_selected_count(len(clean_serials))

    def select_all_environments_in_current_list(self) -> int:
        # 表头最左侧全选框只选择当前筛选结果页内的行；先清空旧选择，避免跨用例残留选择影响导出。
        self.clear_selected_environments()
        rows = self._environment_rows()
        if not rows:
            raise RuntimeError("cannot select all environments because current list is empty")
        self.cdp.click_element_by_script(self._header_select_all_checkbox_script())
        self._wait_selected_count(len(rows))
        return len(rows)

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

    def batch_set_environment_groups(self, modify_mode: str, group_names: list[str]) -> list[str]:
        # 顶部批量工具栏“更多操作”进入“设置环境分组”；弹窗内先选修改方式，再选目标分组。
        self.cdp.hover_element_by_script(self._batch_more_operation_script())
        self.cdp.click_element_by_script(self._batch_more_menu_item_script("设置环境分组"))
        self._wait_batch_set_group_dialog_visible()
        self.cdp.click_element_by_script(self._batch_group_modify_mode_script(modify_mode))
        self._wait_batch_group_modify_mode_selected(modify_mode)
        self._select_batch_environment_groups(group_names)
        selected_groups = self.batch_environment_group_selected_values()
        self.cdp.press("Escape")
        self._wait_select_dropdown_closed()
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._wait_for_overlay_closed()
        return selected_groups

    def batch_set_environment_tags(self, modify_mode: str, tag_names: list[str]) -> list[str]:
        self.cdp.click_element_by_script(self._batch_more_operation_script())
        self.cdp.click_element_by_script(self._batch_more_menu_item_script("编辑标签"))
        self._wait_batch_edit_tag_dialog_visible()
        self.cdp.click_element_by_script(self._batch_tag_modify_mode_script(modify_mode))
        self._wait_batch_tag_modify_mode_selected(modify_mode)
        self._select_batch_environment_tags(tag_names)
        selected_tags = self.batch_environment_tag_selected_values()
        self.cdp.press("Escape")
        self._wait_select_dropdown_closed()
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        if str(modify_mode).strip() == "清空标签":
            self.confirm_secondary_dialog()
        else:
            self._wait_for_overlay_closed()
        return selected_tags

    def open_export_selected_environments_dialog(self) -> None:
        # 顶部批量工具栏“更多操作”里先展开“导出环境”，再点击二级菜单“导出所选”。
        self.cdp.hover_element_by_script(self._batch_more_operation_script())
        self.cdp.hover_element_by_script(self._batch_more_menu_item_script("导出环境"))
        self.cdp.click_element_by_script(self._batch_more_menu_item_script("导出所选"))
        self._wait_export_environment_dialog_visible()

    def confirm_export_environment(self) -> None:
        # “导出环境”弹窗确认按钮；确认后可能触发浏览器下载，也可能弹出系统保存窗口。
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))

    def confirm_export_environment_and_save_download(
        self,
        file_path: str | Path,
        timeout_seconds: int | None = None,
    ) -> str:
        # Chromium 下载事件路径：确认导出后直接把下载文件保存到配置中的导出路径。
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "batch_export_seconds", 120)
        return self.cdp.click_element_by_script_and_save_download(
            self._active_overlay_button_script("确定"),
            file_path,
            timeout=timeout_seconds * 1000,
        )

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
        self.fill("environment_name_input", new_name)
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._confirm_edit_save_message_if_present()
        self._wait_for_overlay_closed()

    def edit_environment_groups_by_serial(
        self,
        serial: str,
        add_groups: list[str] | None = None,
        remove_groups: list[str] | None = None,
    ) -> tuple[list[str], list[str]]:
        self.click_environment_more_by_serial(serial)
        self.click_visible_dropdown_item("编辑")
        self._wait_edit_environment_drawer_visible()
        initial_groups = self.create_environment_selected_groups()
        self._select_create_environment_groups(add_groups or [])
        self._deselect_create_environment_groups(remove_groups or [])
        final_groups = self.create_environment_selected_groups()
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._confirm_edit_save_message_if_present()
        self._wait_for_overlay_closed()
        return initial_groups, final_groups

    def edit_environment_tags_by_serial(self, serial: str, tag_names: list[str]) -> list[str]:
        self.click_environment_more_by_serial(serial)
        self.click_visible_dropdown_item("编辑")
        self._wait_edit_environment_drawer_visible()
        self.cdp.click_element_by_script(self._create_environment_set_tag_button_script())
        expected_tags = self._unique_non_empty(tag_names)
        current_tags = self.create_environment_selected_tags()
        extra_tags = [tag for tag in current_tags if tag not in expected_tags]
        self._deselect_create_environment_tags(extra_tags)
        self._select_create_environment_tags(expected_tags)
        final_tags = self.create_environment_selected_tags()
        self.cdp.press("Escape")
        self._wait_select_dropdown_closed()
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))
        self._confirm_edit_save_message_if_present()
        self._wait_for_overlay_closed()
        return final_tags

    def batch_environment_group_selected_values(self) -> list[str]:
        value = self.cdp.evaluate(self._batch_environment_group_selected_values_script())
        if not isinstance(value, list):
            return []
        return self._unique_non_empty([str(item).strip() for item in value])

    def batch_environment_tag_selected_values(self) -> list[str]:
        value = self.cdp.evaluate(self._batch_environment_tag_selected_values_script())
        if not isinstance(value, list):
            return []
        return self._unique_non_empty([str(item).strip() for item in value])

    def environment_group_values_by_serial(self, serial: str) -> list[str]:
        return self._parse_environment_group_text(self.environment_group_full_text_by_serial(serial))

    def environment_tag_text_by_serial(self, serial: str) -> str:
        return "\n".join(self.environment_tag_values_by_serial(serial))

    def environment_tag_values_by_serial(self, serial: str) -> list[str]:
        value = self.cdp.evaluate(self._environment_tag_values_by_serial_script(serial))
        if not isinstance(value, list):
            return []
        return self._normal_tag_values([str(item).strip() for item in value])

    def environment_tag_values_in_current_list(self) -> dict[str, list[str]]:
        values: dict[str, list[str]] = {}
        for serial in self.environment_serials_at_positions(len(self._environment_rows())):
            values[serial] = self.environment_tag_values_by_serial(serial)
        return values

    def quick_edit_environment_name_by_serial(self, serial: str, new_name: str) -> None:
        # 列表快捷编辑入口在环境名称列内，必须先点名称再点名称右侧的 edit 图标。
        self.dismiss_blocking_overlays()
        self.cdp.click_element_by_script(self._environment_name_text_by_serial_script(serial))
        self.cdp.click_element_by_script(self._environment_name_quick_edit_button_by_serial_script(serial))
        self._wait_quick_edit_environment_name_dialog_visible()
        self.cdp.fill_element_by_script(self._quick_edit_environment_name_input_script(), new_name)
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

    def _environment_group_view_button_script(self, name: str) -> str:
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
                const groupCells = Array.from(row.querySelectorAll("td"))
                    .filter((cell) => visible(cell) && (cell.innerText || "").includes("等") && (cell.innerText || "").includes("查看"));
                for (const cell of groupCells) {{
                    const button = Array.from(cell.querySelectorAll("button"))
                        .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "查看");
                    if (button) return button;
                }}
            }}
            return null;
        }}
        """

    def _environment_group_view_button_by_serial_script(self, serial: str) -> str:
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
                const groupCells = Array.from(row.querySelectorAll("td"))
                    .filter((cell) => visible(cell) && (cell.innerText || "").includes("等") && (cell.innerText || "").includes("查看"));
                for (const cell of groupCells) {{
                    const button = Array.from(cell.querySelectorAll("button"))
                        .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "查看");
                    if (button) return button;
                }}
            }}
            return null;
        }}
        """

    def _environment_name_text_by_serial_script(self, serial: str) -> str:
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
                const rawCells = Array.from(row.querySelectorAll("td"));
                const cells = rawCells
                    .map((cell) => (cell.innerText || cell.textContent || "").trim())
                    .filter(Boolean);
                if (cells[0] !== expectedSerial) continue;
                const nameCell = rawCells[2];
                return nameCell?.querySelector(".sle") || nameCell || null;
            }}
            return null;
        }}
        """

    def _environment_name_quick_edit_button_by_serial_script(self, serial: str) -> str:
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
                const rawCells = Array.from(row.querySelectorAll("td"));
                const cells = rawCells
                    .map((cell) => (cell.innerText || cell.textContent || "").trim())
                    .filter(Boolean);
                if (cells[0] !== expectedSerial) continue;
                const nameCell = rawCells[2];
                if (!nameCell) continue;
                return nameCell.querySelector(".edit-btn-on-hover .icon-edit")
                    || nameCell.querySelector(".edit-btn-on-hover")
                    || null;
            }}
            return null;
        }}
        """

    def _environment_serial_sort_caret_script(self, direction: str) -> str:
        return f"""
        () => {{
            const expectedDirection = {direction!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const th = Array.from(document.querySelectorAll(".el-table__header th, thead th"))
                .filter(visible)
                .find((item) => (item.innerText || item.textContent || "").trim().includes("环境序号"));
            if (!th) return null;
            return th.querySelector(`.sort-caret.${{expectedDirection}}`) || null;
        }}
        """

    def _sortable_header_sort_buttons_visible_by_header_script(self) -> str:
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
            const states = {};
            const headers = Array.from(document.querySelectorAll(".el-table__header th, thead th"))
                .filter(visible);
            for (const th of headers) {
                const text = clean(th.innerText || th.textContent);
                const header = text
                    .replace(/升序/g, "")
                    .replace(/降序/g, "")
                    .replace(/排序/g, "")
                    .replace(/[▲▼]/g, "")
                    .trim();
                if (!header || header === "操作") continue;
                const controls = Array.from(th.querySelectorAll(".caret-wrapper, .sort-caret, [class*='sort']"))
                    .filter((item) => !item.classList.contains("cell"))
                    .filter(visible);
                states[header] = controls.length > 0;
            }
            return states;
        }
        """

    def _column_settings_button_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const headers = Array.from(document.querySelectorAll(".el-table__header th, thead th"))
                .filter(visible);
            for (const th of headers) {
                if (!(th.innerText || th.textContent || "").includes("操作")) continue;
                const button = th.querySelector(".custom-list, .icon-custom");
                if (button && visible(button)) return button;
            }
            return Array.from(document.querySelectorAll(".custom-list, .icon-custom")).find(visible) || null;
        }
        """

    def _column_settings_button_visible_script(self) -> str:
        return """
        () => Boolean((() => {
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const headers = Array.from(document.querySelectorAll(".el-table__header th, thead th"))
                .filter(visible);
            for (const th of headers) {
                if (!(th.innerText || th.textContent || "").includes("操作")) continue;
                const button = th.querySelector(".custom-list, .icon-custom");
                if (button && visible(button)) return button;
            }
            return Array.from(document.querySelectorAll(".custom-list, .icon-custom")).find(visible) || null;
        })())
        """

    def _pagination_size_selector_script(self) -> str:
        return """
        () => {
            const selector = ".el-pagination__sizes .el-select__wrapper, .el-pagination__sizes .el-select";
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(selector)).find(visible) || null;
        }
        """

    def _pagination_size_selector_visible_script(self) -> str:
        return """
        () => Boolean((() => {
            const selector = ".el-pagination__sizes .el-select__wrapper, .el-pagination__sizes .el-select";
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(selector)).find(visible) || null;
        })())
        """

    def _pagination_size_selected_script(self, page_size_text: str) -> str:
        return f"""
        () => {{
            const expectedText = {page_size_text!r};
            const normalize = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const size = Array.from(document.querySelectorAll(".el-pagination__sizes"))
                .filter(visible)
                .find((item) => normalize(item.innerText || item.textContent).includes(expectedText));
            return Boolean(size);
        }}
        """

    def _visible_dropdown_item_by_normalized_text_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const normalize = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const items = Array.from(document.querySelectorAll(".el-select-dropdown__item, .el-dropdown-menu__item, li"))
                .filter((el) => visible(el))
                .filter((el) => normalize(el.innerText || el.textContent) === expectedText);
            return items[items.length - 1] || null;
        }}
        """

    def _tag_management_button_by_text_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const dialogs = Array.from(document.querySelectorAll(".el-dialog"))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("标签"));
            for (const dialog of dialogs.reverse()) {{
                const buttons = Array.from(dialog.querySelectorAll("button"))
                    .filter((button) => visible(button) && (button.innerText || button.textContent || "").trim() === expectedText);
                if (buttons.length) return buttons[buttons.length - 1];
            }}
            return null;
        }}
        """

    def _tag_name_input_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const dialogs = Array.from(document.querySelectorAll(".el-dialog"))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("创建标签"));
            for (const dialog of dialogs.reverse()) {
                const labels = Array.from(dialog.querySelectorAll("label, .el-form-item__label"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "标签名称");
                for (const label of labels) {
                    const formItem = label.closest(".el-form-item");
                    const input = formItem?.querySelector("input");
                    if (input && visible(input)) return input;
                }
                const input = Array.from(dialog.querySelectorAll("input"))
                    .find((el) => visible(el) && ["标签名称", "请输入标签名称", "请输入"].includes(el.getAttribute("placeholder") || ""));
                if (input) return input;
            }
            return null;
        }
        """

    def _tag_delete_button_script(self, tag_name: str) -> str:
        return f"""
        () => {{
            const expectedName = {tag_name!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const dialogs = Array.from(document.querySelectorAll(".el-dialog"))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("标签管理"));
            for (const dialog of dialogs.reverse()) {{
                const rows = Array.from(dialog.querySelectorAll(".el-table__row, tbody tr"))
                    .filter((row) => visible(row) && (row.innerText || "").includes(expectedName));
                for (const row of rows) {{
                    const buttons = Array.from(row.querySelectorAll("button"))
                        .filter((button) => visible(button));
                    if (buttons.length >= 2) return buttons[1];
                    const clickables = Array.from(row.querySelectorAll(".tw-cursor-pointer, i, svg"))
                        .filter((el) => visible(el));
                    if (clickables.length >= 2) return clickables[1];
                }}
            }}
            return null;
        }}
        """

    def _tag_management_close_button_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const dialogs = Array.from(document.querySelectorAll(".el-dialog"))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("标签管理"));
            const dialog = dialogs[dialogs.length - 1];
            if (!dialog) return null;
            return dialog.querySelector(".el-dialog__headerbtn, button[aria-label='Close']") || null;
        }
        """

    def _column_settings_sortable_item_script(self, field_text: str) -> str:
        return f"""
        () => {{
            const expectedText = {field_text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const dialogs = Array.from(document.querySelectorAll(".el-dialog"))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("列表字段设置"));
            for (const dialog of dialogs.reverse()) {{
                const item = Array.from(dialog.querySelectorAll(".sortable"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (item) return item;
            }}
            return null;
        }}
        """

    def _column_settings_sort_icon_script(self, field_text: str) -> str:
        return f"""
        () => {{
            const expectedText = {field_text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const dialogs = Array.from(document.querySelectorAll(".el-dialog"))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("列表字段设置"));
            for (const dialog of dialogs.reverse()) {{
                const item = Array.from(dialog.querySelectorAll(".sortable"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (!item) continue;
                return item.querySelector(".sortable-icon, .icon-sort") || item;
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

    def _environment_checkbox_by_serial_script(self, serial: str) -> str:
        # 环境列表行选择框：按第一列环境序号精确定位，避免名称重复或名称被编辑时误选。
        return f"""
        () => {{
            const expectedSerial = {serial!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const rows = Array.from(document.querySelectorAll(".el-table__row, tbody tr"))
                .filter((row) => visible(row));
            for (const row of rows) {{
                let cells = Array.from(row.querySelectorAll("td"))
                    .map((cell) => (cell.innerText || cell.textContent || "").trim())
                    .filter(Boolean);
                if (!cells.length) {{
                    cells = Array.from(row.querySelectorAll(".cell"))
                        .map((cell) => (cell.innerText || cell.textContent || "").trim())
                        .filter(Boolean);
                }}
                if ((cells[0] || "") !== expectedSerial) continue;
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

    def _header_select_all_checkbox_script(self) -> str:
        # 环境列表表头最左侧 checkbox，用于批量导出/删除等当前列表全选操作。
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const headers = Array.from(document.querySelectorAll(".el-table__header-wrapper, thead"))
                .filter(visible);
            for (const header of headers) {
                const checkbox = Array.from(header.querySelectorAll(".el-checkbox, label"))
                    .find((el) => visible(el));
                if (checkbox) return checkbox;
            }
            return null;
        }
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

    def create_environment_selected_groups(self) -> list[str]:
        value = self.cdp.evaluate(self._create_environment_group_selected_values_script())
        if not isinstance(value, list):
            return []
        return self._unique_non_empty([str(item).strip() for item in value])

    def create_environment_selected_tags(self) -> list[str]:
        value = self.cdp.evaluate(self._create_environment_tag_selected_values_script())
        if not isinstance(value, list):
            return []
        return self._normal_tag_values([str(item).strip() for item in value])

    def _select_create_environment_groups(self, group_names: list[str]) -> None:
        # 创建环境抽屉里“环境分组”是多选控件；已默认选中的分组只记录并保留，不重复点击避免反选。
        for group_name in self._unique_non_empty(group_names):
            if group_name in self.create_environment_selected_groups():
                continue
            selected = False
            for _ in range(3):
                if not self._dropdown_option_visible(group_name):
                    self._open_create_environment_group_select()
                try:
                    self.cdp.click_element_by_script(self._select_dropdown_option_script(group_name), timeout=3000)
                    self._wait_create_environment_groups_selected([group_name])
                    selected = True
                    break
                except TimeoutError:
                    time.sleep(0.3)
            if not selected:
                raise TimeoutError(f"create environment group was not selected: {group_name}")
        self._wait_create_environment_groups_selected(group_names)

    def _deselect_create_environment_groups(self, group_names: list[str]) -> None:
        # 编辑环境还原分组时，已选项需要在同一个多选下拉中再次点击才能取消。
        for group_name in self._unique_non_empty(group_names):
            if group_name not in self.create_environment_selected_groups():
                continue
            deselected = False
            for _ in range(3):
                if not self._dropdown_option_visible(group_name):
                    self._open_create_environment_group_select()
                try:
                    self.cdp.click_element_by_script(self._select_dropdown_option_script(group_name), timeout=3000)
                    self._wait_create_environment_groups_not_selected([group_name])
                    deselected = True
                    break
                except TimeoutError:
                    time.sleep(0.3)
            if not deselected:
                raise TimeoutError(f"create environment group was not deselected: {group_name}")

    def _wait_create_environment_groups_selected(self, expected_groups: list[str]) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        expected = set(self._unique_non_empty(expected_groups))
        last_groups: list[str] = []
        while time.time() < deadline:
            last_groups = self.create_environment_selected_groups()
            if expected.issubset(set(last_groups)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"create environment groups were not selected: expected={sorted(expected)}, actual={last_groups}")

    def _wait_create_environment_groups_not_selected(self, unexpected_groups: list[str]) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        unexpected = set(self._unique_non_empty(unexpected_groups))
        last_groups: list[str] = []
        while time.time() < deadline:
            last_groups = self.create_environment_selected_groups()
            if unexpected.isdisjoint(set(last_groups)):
                return
            time.sleep(0.2)
        raise TimeoutError(
            f"create environment groups were still selected: unexpected={sorted(unexpected)}, actual={last_groups}"
        )

    def _select_create_environment_tags(self, tag_names: list[str]) -> None:
        # 创建环境抽屉里“设置标签”是可搜索多选控件；逐个输入标签名并选择下拉项。
        for tag_name in self._unique_non_empty(tag_names):
            if tag_name in self.create_environment_selected_tags():
                continue
            selected = False
            for _ in range(3):
                self.cdp.fill_element_by_script(self._create_environment_tag_input_script(), tag_name)
                time.sleep(0.3)
                try:
                    self.cdp.click_element_by_script(self._create_environment_tag_option_script(tag_name), timeout=3000)
                    self._wait_create_environment_tags_selected([tag_name])
                    selected = True
                    break
                except TimeoutError:
                    self._open_create_environment_tag_select()
                    time.sleep(0.3)
            if not selected:
                raise TimeoutError(f"create environment tag was not selected: {tag_name}")
        self._wait_create_environment_tags_selected(tag_names)

    def _deselect_create_environment_tags(self, tag_names: list[str]) -> None:
        for tag_name in self._unique_non_empty(tag_names):
            if tag_name not in self.create_environment_selected_tags():
                continue
            deselected = False
            try:
                self.cdp.click_element_by_script(
                    self._create_environment_selected_tag_close_script(tag_name),
                    timeout=1500,
                )
                self._wait_create_environment_tags_not_selected([tag_name])
                deselected = True
            except TimeoutError:
                pass
            if deselected:
                continue
            for _ in range(3):
                self.cdp.fill_element_by_script(self._create_environment_tag_input_script(), tag_name)
                time.sleep(0.3)
                try:
                    self.cdp.click_element_by_script(self._create_environment_tag_option_script(tag_name), timeout=3000)
                    self._wait_create_environment_tags_not_selected([tag_name])
                    deselected = True
                    break
                except TimeoutError:
                    self._open_create_environment_tag_select()
                    time.sleep(0.3)
            if not deselected:
                raise TimeoutError(f"create environment tag was not deselected: {tag_name}")

    def _wait_create_environment_tags_selected(self, expected_tags: list[str]) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        expected = set(self._unique_non_empty(expected_tags))
        last_tags: list[str] = []
        while time.time() < deadline:
            last_tags = self.create_environment_selected_tags()
            if expected.issubset(set(last_tags)):
                return
            selected_count = self._selected_tag_count_from_values(last_tags)
            if selected_count >= len(expected):
                return
            time.sleep(0.2)
        raise TimeoutError(f"create environment tags were not selected: expected={sorted(expected)}, actual={last_tags}")

    def _wait_create_environment_tags_not_selected(self, unexpected_tags: list[str]) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        unexpected = set(self._unique_non_empty(unexpected_tags))
        last_tags: list[str] = []
        while time.time() < deadline:
            last_tags = self.create_environment_selected_tags()
            if unexpected.isdisjoint(set(last_tags)):
                return
            time.sleep(0.2)
        raise TimeoutError(
            f"create environment tags were still selected: unexpected={sorted(unexpected)}, actual={last_tags}"
        )

    def _selected_tag_count_from_values(self, values: list[str]) -> int:
        for value in values:
            text = str(value).strip()
            if not text.startswith("设置标签"):
                continue
            try:
                return int(text.split("(", 1)[1].split(")", 1)[0])
            except (IndexError, ValueError):
                continue
        return 0

    def _open_create_environment_tag_select(self) -> None:
        opened = self.cdp.evaluate(self._open_create_environment_tag_select_script())
        if not opened:
            raise TimeoutError("create environment tag select was not opened")

    def _select_batch_environment_groups(self, group_names: list[str]) -> None:
        # 批量设置环境分组弹窗里的“环境分组”同样是 Element Plus 多选控件。
        for group_name in self._unique_non_empty(group_names):
            if group_name in self.batch_environment_group_selected_values():
                continue
            selected = False
            for _ in range(3):
                if not self._dropdown_option_visible(group_name):
                    self._open_batch_environment_group_select()
                try:
                    self.cdp.click_element_by_script(self._select_dropdown_option_script(group_name), timeout=3000)
                    self._wait_batch_environment_groups_selected([group_name])
                    selected = True
                    break
                except TimeoutError:
                    time.sleep(0.3)
            if not selected:
                raise TimeoutError(f"batch environment group was not selected: {group_name}")
        self._wait_batch_environment_groups_selected(group_names)

    def _select_batch_environment_tags(self, tag_names: list[str]) -> None:
        for tag_name in self._unique_non_empty(tag_names):
            if tag_name in self.batch_environment_tag_selected_values():
                continue
            selected = False
            for _ in range(3):
                self.cdp.fill_element_by_script(self._batch_environment_tag_input_script(), tag_name)
                time.sleep(0.3)
                try:
                    self.cdp.click_element_by_script(self._create_environment_tag_option_script(tag_name), timeout=3000)
                    self._wait_batch_environment_tags_selected([tag_name])
                    selected = True
                    break
                except TimeoutError:
                    self._open_batch_environment_tag_select()
                    time.sleep(0.3)
            if not selected:
                raise TimeoutError(f"batch environment tag was not selected: {tag_name}")
        self._wait_batch_environment_tags_selected(tag_names)

    def _wait_batch_environment_groups_selected(self, expected_groups: list[str]) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        expected = set(self._unique_non_empty(expected_groups))
        last_groups: list[str] = []
        while time.time() < deadline:
            last_groups = self.batch_environment_group_selected_values()
            if expected.issubset(set(last_groups)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"batch environment groups were not selected: expected={sorted(expected)}, actual={last_groups}")

    def _wait_batch_environment_tags_selected(self, expected_tags: list[str]) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        expected = set(self._unique_non_empty(expected_tags))
        last_tags: list[str] = []
        while time.time() < deadline:
            last_tags = self.batch_environment_tag_selected_values()
            if expected.issubset(set(last_tags)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"batch environment tags were not selected: expected={sorted(expected)}, actual={last_tags}")

    def _open_batch_environment_group_select(self) -> None:
        # 弹窗多选框普通 click 也可能不展开，复用 pointer/mouse 事件链打开下拉。
        opened = self.cdp.evaluate(self._open_batch_environment_group_select_script())
        if not opened:
            raise TimeoutError("batch environment group select was not opened")
        time.sleep(0.3)

    def _open_batch_environment_tag_select(self) -> None:
        opened = self.cdp.evaluate(self._open_batch_environment_tag_select_script())
        if not opened:
            raise TimeoutError("batch environment tag select was not opened")
        time.sleep(0.3)

    def _open_create_environment_group_select(self) -> None:
        # 该多选框普通 click 不一定展开，Element Plus 需要 pointer/mouse 事件链触发内部 popper。
        opened = self.cdp.evaluate(self._open_create_environment_group_select_script())
        if not opened:
            raise TimeoutError("create environment group select was not opened")
        time.sleep(0.3)

    def _dropdown_option_visible(self, text: str) -> bool:
        return bool(self.cdp.evaluate(self._dropdown_option_visible_script(text)))

    def _wait_select_dropdown_closed(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible_count = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-select__popper, .el-popper"))
                        .filter((popper) => visible(popper) && popper.querySelector(".el-select-dropdown__item"))
                        .length;
                }
                """
            )
            if int(visible_count or 0) == 0:
                return
            self.cdp.press("Escape")
            time.sleep(0.2)
        raise TimeoutError("select dropdown did not close")

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

    def _create_environment_group_select_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
            for (const drawer of drawers.reverse()) {
                const labels = Array.from(drawer.querySelectorAll("label, .el-form-item__label"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "环境分组");
                for (const label of labels) {
                    const formItem = label.closest(".el-form-item");
                    const select = formItem?.querySelector(".el-select");
                    const wrapper = select?.querySelector(".el-select__wrapper");
                    if (wrapper && visible(wrapper)) return wrapper;
                    if (select && visible(select)) return select;
                }
            }
            return null;
        }
        """

    def _create_environment_set_tag_button_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
            for (const drawer of drawers.reverse()) {
                const candidates = Array.from(drawer.querySelectorAll("button, div, span"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim().startsWith("设置标签"));
                for (const candidate of candidates) {
                    return candidate.closest("button") || candidate.closest(".tw-cursor-pointer") || candidate;
                }
            }
            return null;
        }
        """

    def _create_environment_tag_select_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const popovers = Array.from(document.querySelectorAll(".create-env-tag-popover, .el-popover, .el-popper"))
                .filter((popover) => visible(popover) && (popover.innerText || "").includes("标签"));
            for (const popover of popovers.reverse()) {
                const input = Array.from(popover.querySelectorAll("input"))
                    .find((el) => visible(el) && (el.getAttribute("placeholder") || "").includes("请选择/输入创建标签"));
                if (input) return input.closest(".el-input") || input;
            }
            const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
            for (const drawer of drawers.reverse()) {
                const input = Array.from(drawer.querySelectorAll("input"))
                    .find((el) => visible(el) && (el.getAttribute("placeholder") || "").includes("请选择/输入创建标签"));
                if (input) return input.closest(".el-select") || input.closest(".el-input") || input;
                const labels = Array.from(drawer.querySelectorAll("label, .el-form-item__label"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").includes("标签"));
                for (const label of labels) {
                    const formItem = label.closest(".el-form-item");
                    const select = formItem?.querySelector(".el-select");
                    const wrapper = select?.querySelector(".el-select__wrapper");
                    if (wrapper && visible(wrapper)) return wrapper;
                    if (select && visible(select)) return select;
                }
            }
            return null;
        }
        """

    def _create_environment_tag_input_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const popovers = Array.from(document.querySelectorAll(".create-env-tag-popover, .el-popover, .el-popper"))
                .filter((popover) => visible(popover) && (popover.innerText || "").includes("标签"));
            for (const popover of popovers.reverse()) {
                const input = Array.from(popover.querySelectorAll("input"))
                    .find((el) => visible(el) && (el.getAttribute("placeholder") || "").includes("请选择/输入创建标签"));
                if (input) return input;
            }
            const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
            for (const drawer of drawers.reverse()) {
                const input = Array.from(drawer.querySelectorAll("input"))
                    .find((el) => visible(el) && (el.getAttribute("placeholder") || "").includes("请选择/输入创建标签"));
                if (input) return input;
                const labels = Array.from(drawer.querySelectorAll("label, .el-form-item__label"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").includes("标签"));
                for (const label of labels) {
                    const formItem = label.closest(".el-form-item");
                    const input = formItem?.querySelector("input");
                    if (input && visible(input)) return input;
                }
            }
            return null;
        }
        """

    def _create_environment_tag_option_script(self, tag_name: str) -> str:
        return f"""
        () => {{
            const expectedText = {tag_name!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const popovers = Array.from(document.querySelectorAll(".create-env-tag-popover, .el-popover, .el-popper"))
                .filter((popover) => visible(popover) && (popover.innerText || "").includes(expectedText));
            for (const popover of popovers.reverse()) {{
                const candidates = Array.from(popover.querySelectorAll("li, div, span"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText)
                    .map((el) => {{
                        const rect = el.getBoundingClientRect();
                        return {{ el, area: rect.width * rect.height }};
                    }})
                    .sort((left, right) => left.area - right.area);
                if (candidates.length) return candidates[0].el;
            }}
            return null;
        }}
        """

    def _create_environment_selected_tag_close_script(self, tag_name: str) -> str:
        return f"""
        () => {{
            const expectedText = {tag_name!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const clean = (value) => String(value || "").trim();
            const popovers = Array.from(document.querySelectorAll(".create-env-tag-popover, .el-popover, .el-popper"))
                .filter((popover) => visible(popover) && (popover.innerText || "").includes(expectedText));
            for (const popover of popovers.reverse()) {{
                const chips = Array.from(popover.querySelectorAll(".el-tag.is-closable"))
                    .filter((chip) => visible(chip) && !chip.closest(".el-select-dropdown__item"));
                for (const chip of chips) {{
                    const content = chip.querySelector(".el-tag__content, .tw-truncate");
                    const text = clean(content?.innerText || content?.textContent || chip.innerText || chip.textContent);
                    if (text !== expectedText) continue;
                    const close = Array.from(chip.querySelectorAll(".el-tag__close, .el-icon-close, i, svg"))
                        .find(visible);
                    return close || chip;
                }}
            }}
            return null;
        }}
        """

    def _open_create_environment_tag_select_script(self) -> str:
        return f"""
        () => {{
            const finder = {self._create_environment_tag_select_script()};
            const wrapper = finder();
            if (!wrapper) return false;
            const input = wrapper.matches?.("input") ? wrapper : wrapper.querySelector("input");
            const targets = [
                wrapper,
                input,
                wrapper.querySelector?.(".el-select__caret"),
            ].filter(Boolean);
            for (const target of targets) {{
                for (const type of ["pointerdown", "mousedown", "mouseup", "click"]) {{
                    target.dispatchEvent(new MouseEvent(type, {{
                        bubbles: true,
                        cancelable: true,
                        view: window,
                    }}));
                }}
                target.focus?.();
            }}
            return true;
        }}
        """

    def _open_create_environment_group_select_script(self) -> str:
        return f"""
        () => {{
            const finder = {self._create_environment_group_select_script()};
            const wrapper = finder();
            if (!wrapper) return false;
            const input = wrapper.querySelector("input");
            if (input) {{
                input.value = "";
                input.dispatchEvent(new Event("input", {{ bubbles: true }}));
                input.dispatchEvent(new Event("change", {{ bubbles: true }}));
            }}
            const targets = [
                wrapper,
                input,
                wrapper.querySelector(".el-select__caret"),
            ].filter(Boolean);
            for (const target of targets) {{
                for (const type of ["pointerdown", "mousedown", "mouseup", "click"]) {{
                    target.dispatchEvent(new MouseEvent(type, {{
                        bubbles: true,
                        cancelable: true,
                        view: window,
                    }}));
                }}
                target.focus?.();
            }}
            return true;
        }}
        """

    def _batch_group_modify_mode_script(self, modify_mode: str) -> str:
        return f"""
        () => {{
            const expectedText = {modify_mode!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("设置环境分组"));
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

    def _batch_tag_modify_mode_script(self, modify_mode: str) -> str:
        return f"""
        () => {{
            const expectedText = {modify_mode!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("设置标签"));
            for (const overlay of overlays.reverse()) {{
                const radios = Array.from(overlay.querySelectorAll(".el-radio, label"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                for (const radio of radios) {{
                    return radio.closest(".el-radio") || radio;
                }}
            }}
            return null;
        }}
        """

    def _batch_group_modify_mode_selected_script(self, modify_mode: str) -> str:
        return f"""
        () => {{
            const expectedText = {modify_mode!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("设置环境分组"));
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

    def _batch_tag_modify_mode_selected_script(self, modify_mode: str) -> str:
        return f"""
        () => {{
            const expectedText = {modify_mode!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("设置标签"));
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

    def _batch_environment_group_select_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("设置环境分组"));
            for (const overlay of overlays.reverse()) {
                const labels = Array.from(overlay.querySelectorAll("label, .el-form-item__label"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "环境分组");
                for (const label of labels) {
                    const formItem = label.closest(".el-form-item");
                    const select = formItem?.querySelector(".el-select");
                    const wrapper = select?.querySelector(".el-select__wrapper");
                    if (wrapper && visible(wrapper)) return wrapper;
                    if (select && visible(select)) return select;
                }
            }
            return null;
        }
        """

    def _batch_environment_tag_select_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("设置标签"));
            for (const overlay of overlays.reverse()) {
                const input = Array.from(overlay.querySelectorAll("input"))
                    .find((el) =>
                        visible(el)
                        && el.getAttribute("type") !== "radio"
                        && (el.getAttribute("placeholder") || "").includes("请选择/输入创建标签")
                    );
                if (input) return input.closest(".el-select") || input.closest(".el-input") || input;
                const labels = Array.from(overlay.querySelectorAll("label, .el-form-item__label"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "选择标签");
                for (const label of labels) {
                    const formItem = label.closest(".el-form-item");
                    const select = formItem?.querySelector(".el-select");
                    const wrapper = select?.querySelector(".el-select__wrapper");
                    if (wrapper && visible(wrapper)) return wrapper;
                    if (select && visible(select)) return select;
                }
            }
            return null;
        }
        """

    def _batch_environment_tag_input_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("设置标签"));
            for (const overlay of overlays.reverse()) {
                const input = Array.from(overlay.querySelectorAll("input"))
                    .find((el) =>
                        visible(el)
                        && el.getAttribute("type") !== "radio"
                        && (el.getAttribute("placeholder") || "").includes("请选择/输入创建标签")
                    );
                if (input) return input;
                const labels = Array.from(overlay.querySelectorAll("label, .el-form-item__label"))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "选择标签");
                for (const label of labels) {
                    const formItem = label.closest(".el-form-item");
                    const input = Array.from(formItem?.querySelectorAll("input") || [])
                        .find((el) => visible(el) && el.getAttribute("type") !== "radio");
                    if (input && visible(input)) return input;
                }
            }
            return null;
        }
        """

    def _open_batch_environment_group_select_script(self) -> str:
        return f"""
        () => {{
            const finder = {self._batch_environment_group_select_script()};
            const wrapper = finder();
            if (!wrapper) return false;
            const input = wrapper.querySelector("input");
            if (input) {{
                input.value = "";
                input.dispatchEvent(new Event("input", {{ bubbles: true }}));
                input.dispatchEvent(new Event("change", {{ bubbles: true }}));
            }}
            const targets = [
                wrapper,
                input,
                wrapper.querySelector(".el-select__caret"),
            ].filter(Boolean);
            for (const target of targets) {{
                for (const type of ["pointerdown", "mousedown", "mouseup", "click"]) {{
                    target.dispatchEvent(new MouseEvent(type, {{
                        bubbles: true,
                        cancelable: true,
                        view: window,
                    }}));
                }}
                target.focus?.();
            }}
            return true;
        }}
        """

    def _open_batch_environment_tag_select_script(self) -> str:
        return f"""
        () => {{
            const finder = {self._batch_environment_tag_select_script()};
            const wrapper = finder();
            if (!wrapper) return false;
            const input = wrapper.matches?.("input") ? wrapper : wrapper.querySelector("input");
            const targets = [
                wrapper,
                input,
                wrapper.querySelector?.(".el-select__caret"),
            ].filter(Boolean);
            for (const target of targets) {{
                for (const type of ["pointerdown", "mousedown", "mouseup", "click"]) {{
                    target.dispatchEvent(new MouseEvent(type, {{
                        bubbles: true,
                        cancelable: true,
                        view: window,
                    }}));
                }}
                target.focus?.();
            }}
            return true;
        }}
        """

    def _dropdown_option_visible_script(self, text: str) -> str:
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
                if (item) return true;
            }}
            return false;
        }}
        """

    def _batch_environment_group_selected_values_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const clean = (value) => String(value || "").trim();
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("设置环境分组"));
            for (const overlay of overlays.reverse()) {
                const labels = Array.from(overlay.querySelectorAll("label, .el-form-item__label"))
                    .filter((el) => visible(el) && clean(el.innerText || el.textContent) === "环境分组");
                for (const label of labels) {
                    const formItem = label.closest(".el-form-item");
                    const select = formItem?.querySelector(".el-select");
                    if (!select || !visible(select)) continue;
                    const values = [];
                    const tagSelectors = [
                        ".el-tag__content",
                        ".el-select__tags-text",
                        ".el-select__selected-item",
                        ".el-select__selection span",
                    ];
                    for (const selector of tagSelectors) {
                        for (const item of Array.from(select.querySelectorAll(selector)).filter(visible)) {
                            const text = clean(item.innerText || item.textContent);
                            if (text && text !== "×" && !values.includes(text)) values.push(text);
                        }
                    }
                    const poppers = Array.from(document.querySelectorAll(".el-select__popper, .el-popper"))
                        .filter(visible);
                    for (const popper of poppers) {
                        for (const item of Array.from(popper.querySelectorAll(".el-select-dropdown__item.is-selected"))
                            .filter(visible)) {
                            const text = clean(item.innerText || item.textContent);
                            if (text && !values.includes(text)) values.push(text);
                        }
                    }
                    const inputValue = clean(select.querySelector("input")?.value);
                    if (inputValue && !values.includes(inputValue)) values.push(inputValue);
                    return values.filter((item) => (
                        item
                        && !["请选择", "请选择环境分组"].includes(item)
                        && !/^\\+\\s*\\d+$/.test(item)
                    ));
                }
            }
            return [];
        }
        """

    def _batch_environment_tag_selected_values_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const clean = (value) => String(value || "").trim();
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || "").includes("设置标签"));
            for (const overlay of overlays.reverse()) {
                const input = Array.from(overlay.querySelectorAll("input"))
                    .find((el) =>
                        visible(el)
                        && el.getAttribute("type") !== "radio"
                        && (el.getAttribute("placeholder") || "").includes("请选择/输入创建标签")
                    );
                const formItems = Array.from(overlay.querySelectorAll(".el-form-item"))
                    .filter((item) => visible(item) && clean(item.innerText || item.textContent).includes("选择标签"));
                const formItem = input?.closest(".el-form-item") || formItems[formItems.length - 1];
                const select = input?.closest(".el-select") || formItem?.querySelector(".el-select");
                if (!select || !visible(select)) continue;
                const values = [];
                const tagSelectors = [
                    ".el-tag__content",
                    ".el-tag__content .tw-truncate",
                    ".el-select__tags-text",
                    ".el-select__selected-item",
                    ".el-select__selection span",
                ];
                const roots = [select, formItem].filter(Boolean);
                for (const root of roots) {
                    for (const selector of tagSelectors) {
                        for (const item of Array.from(root.querySelectorAll(selector)).filter(visible)) {
                            const text = clean(item.innerText || item.textContent);
                            if (text && text !== "×" && !values.includes(text)) values.push(text);
                        }
                    }
                }
                if (!values.length && formItem) {
                    for (const item of Array.from(formItem.querySelectorAll("span, div")).filter(visible)) {
                        const text = clean(item.innerText || item.textContent);
                        if (
                            text
                            && text !== "×"
                            && text !== "选择标签"
                            && text !== "请选择/输入创建标签"
                            && !text.includes("请选择/输入创建标签")
                            && !values.includes(text)
                        ) values.push(text);
                    }
                }
                const poppers = Array.from(document.querySelectorAll(".el-select__popper, .el-popper"))
                    .filter(visible);
                for (const popper of poppers) {
                    for (const item of Array.from(popper.querySelectorAll(".el-select-dropdown__item.is-selected"))
                        .filter(visible)) {
                        const text = clean(item.innerText || item.textContent);
                        if (text && !values.includes(text)) values.push(text);
                    }
                }
                const inputValue = clean(input?.value);
                if (inputValue && !values.includes(inputValue)) values.push(inputValue);
                return values.filter((item) => (
                    item
                    && !["请选择", "请选择/输入创建标签"].includes(item)
                    && !/^\\+\\s*\\d+$/.test(item)
                ));
            }
            return [];
        }
        """

    def _create_environment_group_selected_values_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const clean = (value) => String(value || "").trim();
            const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
            for (const drawer of drawers.reverse()) {
                const labels = Array.from(drawer.querySelectorAll("label, .el-form-item__label"))
                    .filter((el) => visible(el) && clean(el.innerText || el.textContent) === "环境分组");
                for (const label of labels) {
                    const formItem = label.closest(".el-form-item");
                    const select = formItem?.querySelector(".el-select");
                    if (!select || !visible(select)) continue;
                    const values = [];
                    const tagSelectors = [
                        ".el-tag__content",
                        ".el-select__tags-text",
                        ".el-select__selected-item",
                        ".el-select__selection span",
                    ];
                    for (const selector of tagSelectors) {
                        for (const item of Array.from(select.querySelectorAll(selector)).filter(visible)) {
                            const text = clean(item.innerText || item.textContent);
                            if (text && text !== "×" && !values.includes(text)) values.push(text);
                        }
                    }
                    const poppers = Array.from(document.querySelectorAll(".el-select__popper, .el-popper"))
                        .filter(visible);
                    for (const popper of poppers) {
                        for (const item of Array.from(popper.querySelectorAll(".el-select-dropdown__item.is-selected"))
                            .filter(visible)) {
                            const text = clean(item.innerText || item.textContent);
                            if (text && !values.includes(text)) values.push(text);
                        }
                    }
                    const inputValue = clean(select.querySelector("input")?.value);
                    if (inputValue && !values.includes(inputValue)) values.push(inputValue);
                    return values.filter((item) => (
                        item
                        && !["请选择", "请选择环境分组"].includes(item)
                        && !/^\\+\\s*\\d+$/.test(item)
                    ));
                }
            }
            return [];
        }
        """

    def _create_environment_tag_selected_values_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const clean = (value) => String(value || "").trim();
            const isRealTag = (value) => (
                value
                && value !== "×"
                && !["请选择", "请选择/输入创建标签"].includes(value)
                && !/^设置标签\\(\\d+\\)$/.test(value)
                && !/^\\+\\s*\\d+$/.test(value)
            );
            const unique = (values) => Array.from(new Set(values.filter(isRealTag)));
            const popovers = Array.from(document.querySelectorAll(".create-env-tag-popover, .el-popover, .el-popper"))
                .filter((popover) => visible(popover) && (popover.innerText || "").includes("标签"));
            for (const popover of popovers.reverse()) {
                const selectedChips = Array.from(popover.querySelectorAll(".el-tag.is-closable"))
                    .filter(visible)
                    .filter((el) => !el.closest(".el-select-dropdown__item"))
                    .map((el) => {
                        const content = el.querySelector(".el-tag__content, .tw-truncate");
                        return clean(content?.innerText || content?.textContent || el.innerText || el.textContent);
                    });
                const selected = unique(selectedChips);
                if (selected.length) return selected;
            }
            const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
            for (const drawer of drawers.reverse()) {
                const input = Array.from(drawer.querySelectorAll("input"))
                    .find((el) => visible(el) && (el.getAttribute("placeholder") || "").includes("请选择/输入创建标签"));
                const select = input?.closest(".el-select");
                if (!select || !visible(select)) continue;
                const values = [];
                const tagSelectors = [
                    ".el-tag__content",
                    ".el-select__tags-text",
                    ".el-select__selected-item",
                    ".el-select__selection span",
                ];
                for (const selector of tagSelectors) {
                    for (const item of Array.from(select.querySelectorAll(selector)).filter(visible)) {
                        const text = clean(item.innerText || item.textContent);
                        if (text && text !== "×" && !values.includes(text)) values.push(text);
                    }
                }
                return unique(values);
            }
            return [];
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

    def _visible_locator_script(self, locator_name: str) -> str:
        return f"""
        () => {{
            const selector = {self.locator(locator_name)!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const candidates = Array.from(document.querySelectorAll(selector))
                .filter(visible)
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    return {{ el, area: rect.width * rect.height }};
                }})
                .sort((left, right) => left.area - right.area);
            return candidates[0]?.el || null;
        }}
        """

    def _visible_text_element_script(self, text: str, locator_name: str = "visible_text_candidates") -> str:
        return f"""
        () => {{
            const selector = {self.locator(locator_name)!r};
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

    def _visible_menu_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const selector = {self.locator("environment_menu_candidates")!r};
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

    def _message_box_button_script(self, text: str) -> str:
        return f"""
        () => {{
            const messageBoxSelector = {self.locator("message_box")!r};
            const buttonSelector = {self.locator("button")!r};
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const boxes = Array.from(document.querySelectorAll(messageBoxSelector))
                .filter(visible);
            for (const box of boxes.reverse()) {{
                const button = Array.from(box.querySelectorAll(buttonSelector))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (button) return button;
            }}
            return null;
        }}
        """

    def _forbidden_open_environment_dialog_visible_script(self) -> str:
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
            return Array.from(document.querySelectorAll(".el-message-box, .el-dialog"))
                .some((overlay) => visible(overlay) && (overlay.innerText || overlay.textContent || "").includes("禁止打开环境"));
        }
        """

    def _forbidden_open_environment_dialog_close_button_script(self) -> str:
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
            const overlays = Array.from(document.querySelectorAll(".el-message-box, .el-dialog"))
                .filter((overlay) => visible(overlay) && (overlay.innerText || overlay.textContent || "").includes("禁止打开环境"));
            for (const overlay of overlays.reverse()) {
                const closeButton = Array.from(overlay.querySelectorAll("button"))
                    .find((button) => visible(button) && (button.innerText || button.textContent || "").trim() === "关闭");
                if (closeButton) return closeButton;
                const headerClose = overlay.querySelector(".el-message-box__headerbtn, .el-dialog__headerbtn, button[aria-label='Close']");
                if (headerClose && visible(headerClose)) return headerClose;
            }
            return null;
        }
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

    def _environment_cell_text_by_header_and_serial_script(self, serial: str, header_text: str) -> str:
        return f"""
        () => {{
            const expectedSerial = {str(serial).strip()!r};
            const expectedHeader = {header_text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const clean = (value) => String(value || "").trim();
            const headers = Array.from(document.querySelectorAll(".el-table__header th, thead th"))
                .filter(visible)
                .map((th) => clean(th.innerText || th.textContent));
            const serialIndex = headers.findIndex((text) => text.includes("环境序号"));
            const targetIndex = headers.findIndex((text) => text.includes(expectedHeader));
            if (targetIndex < 0) return "";
            const rows = Array.from(document.querySelectorAll(".el-table__row, tbody tr"))
                .filter(visible);
            for (const row of rows) {{
                const cells = Array.from(row.querySelectorAll("td"))
                    .filter(visible)
                    .map((cell) => clean(cell.innerText || cell.textContent));
                const rowSerial = serialIndex >= 0 ? cells[serialIndex] : cells[0];
                const fallbackSerialMatch = cells.slice(0, 3).includes(expectedSerial);
                if (rowSerial !== expectedSerial && !fallbackSerialMatch) continue;
                return cells[targetIndex] || "";
            }}
            return "";
        }}
        """

    def _environment_tag_values_by_serial_script(self, serial: str) -> str:
        return f"""
        () => {{
            const expectedSerial = {str(serial).strip()!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const clean = (value) => String(value || "").trim();
            const headers = Array.from(document.querySelectorAll(".el-table__header th, thead th"))
                .filter(visible)
                .map((th) => clean(th.innerText || th.textContent));
            const serialIndex = headers.findIndex((text) => text.includes("环境序号"));
            const tagIndex = headers.findIndex((text) => text.includes("标签"));
            if (tagIndex < 0) return [];

            const rows = Array.from(document.querySelectorAll(".el-table__row, tbody tr"))
                .filter(visible);
            for (const row of rows) {{
                const cells = Array.from(row.querySelectorAll("td")).filter(visible);
                const cellTexts = cells.map((cell) => clean(cell.innerText || cell.textContent));
                const rowSerial = serialIndex >= 0 ? cellTexts[serialIndex] : cellTexts[0];
                const fallbackSerialMatch = cellTexts.slice(0, 3).includes(expectedSerial);
                if (rowSerial !== expectedSerial && !fallbackSerialMatch) continue;

                const tagCell = cells[tagIndex];
                if (!tagCell) return [];
                const tagTexts = Array.from(tagCell.querySelectorAll(".el-tag"))
                    .filter(visible)
                    .map((tag) => {{
                        const content = tag.querySelector(".el-tag__content, .tw-truncate");
                        return clean(content?.innerText || content?.textContent || tag.innerText || tag.textContent);
                    }});
                if (tagTexts.length) return Array.from(new Set(tagTexts));

                return clean(tagCell.innerText || tagCell.textContent)
                    .split(/\\n|,|，|、|；|;|\\//)
                    .map((item) => clean(item))
                    .filter(Boolean);
            }}
            return [];
        }}
        """

    def _assert_response_success(self, response: dict[str, str | int], action_name: str) -> None:
        status = int(response.get("status", 0) or 0)
        if not 200 <= status < 300:
            raise RuntimeError(f"{action_name} request failed: status={status}, response={response}")

    @staticmethod
    def _serials_match_sort(serials: list[int], direction: str) -> bool:
        if direction == "ascending":
            return all(left <= right for left, right in zip(serials, serials[1:]))
        if direction == "descending":
            return all(left >= right for left, right in zip(serials, serials[1:]))
        return False

    @staticmethod
    def _unique_non_empty(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value).strip()
            if text and text not in result:
                result.append(text)
        return result

    def _parse_environment_group_text(self, group_text: str) -> list[str]:
        text = str(group_text).strip()
        if not text:
            return []
        normalized = (
            text.replace("，", "\n")
            .replace(",", "\n")
            .replace("、", "\n")
            .replace("；", "\n")
            .replace(";", "\n")
            .replace("/", "\n")
        )
        groups = [item.strip() for item in normalized.splitlines() if item.strip()]
        return self._unique_non_empty(groups or [text])

    def _parse_environment_tag_text(self, tag_text: str) -> list[str]:
        text = str(tag_text).strip()
        if not text or text == "--":
            return []
        normalized = (
            text.replace("查看", "\n")
            .replace(",", "\n")
            .replace("，", "\n")
            .replace("、", "\n")
            .replace("；", "\n")
            .replace(";", "\n")
            .replace("/", "\n")
        )
        return self._normal_tag_values([item.strip() for item in normalized.splitlines()])

    def _normal_tag_values(self, tag_values: list[str]) -> list[str]:
        tags = []
        for value in tag_values:
            text = str(value).strip()
            if (
                not text
                or text == "--"
                or text == "×"
                or text in {"请选择", "请选择/输入创建标签"}
                or text.startswith("设置标签(")
                or text.startswith("+")
            ):
                continue
            tags.append(text)
        return self._unique_non_empty(tags)

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
                        remark: cells[2] || "",
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

    def _wait_for_message_box_closed(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible_count = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-message-box"))
                        .filter(visible).length;
                }
                """
            )
            if int(visible_count or 0) == 0:
                return
            time.sleep(0.2)
        raise TimeoutError("message box did not close")

    def _wait_environment_group_detail_text(self, base_text: str = "", button_rect: dict | None = None) -> str:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        compressed_text = str(base_text or "").strip()
        rect_payload = json.dumps(button_rect or {})
        last_text = ""
        while time.time() < deadline:
            text = self.cdp.evaluate(
                """
                () => {
                    const buttonRect = __BUTTON_RECT__;
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    const nearButton = (el) => {
                        if (!buttonRect || buttonRect.x === undefined) return true;
                        const rect = el.getBoundingClientRect();
                        const buttonCenterX = buttonRect.x + buttonRect.width / 2;
                        const popoverCenterX = rect.x + rect.width / 2;
                        const xClose = Math.abs(popoverCenterX - buttonCenterX) <= Math.max(260, rect.width);
                        const verticalDistance = Math.min(
                            Math.abs(rect.bottom - buttonRect.y),
                            Math.abs(rect.y - (buttonRect.y + buttonRect.height))
                        );
                        return xClose && verticalDistance <= 45;
                    };
                    const groupPopovers = Array.from(document.querySelectorAll(
                        ".el-popover[aria-label='环境分组'], .el-popper[aria-label='环境分组']"
                    )).filter((el) => visible(el) && nearButton(el));
                    for (const popover of groupPopovers.reverse()) {
                        const main = popover.querySelector(".view-more-main");
                        const text = (main?.innerText || main?.textContent || "").trim();
                        if (text) return text;
                    }
                    const overlays = Array.from(document.querySelectorAll(
                        ".el-popper, .el-popover, .el-tooltip__popper, .el-dialog"
                    )).filter(visible);
                    for (const overlay of overlays.reverse()) {
                        const text = (overlay.innerText || overlay.textContent || "").trim();
                        if (text && text !== "查看") return text;
                    }
                    return "";
                }
                """
                .replace("__BUTTON_RECT__", rect_payload)
            )
            last_text = str(text or "").strip()
            # 单元格自身也会触发一个只包含压缩文案和“查看”的 tooltip；这里等真正的完整分组气泡。
            if last_text and "查看" not in last_text and last_text != compressed_text:
                return last_text
            time.sleep(0.2)
        raise TimeoutError(f"environment group detail did not appear: {last_text}")

    def _wait_no_environment_group_popover(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible_count = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(
                        ".el-popover[aria-label='环境分组'], .el-popper[aria-label='环境分组']"
                    )).filter(visible).length;
                }
                """
            )
            if int(visible_count or 0) == 0:
                return
            time.sleep(0.2)
        raise TimeoutError("old environment group popover did not close")

    def _element_rect_by_script(self, script: str) -> dict:
        rect = self.cdp.evaluate(
            f"""
            () => {{
                const finder = {script};
                const element = finder();
                if (!element) return null;
                const rect = element.getBoundingClientRect();
                return {{
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                    top: rect.top,
                    right: rect.right,
                    bottom: rect.bottom,
                    left: rect.left,
                }};
            }}
            """
        )
        if not rect:
            raise TimeoutError("element rect was not available")
        return rect

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

    def _wait_more_filter_drawer_visible(self) -> None:
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
                        .some((drawer) => (
                            visible(drawer)
                            && (drawer.innerText || "").includes("立即筛选")
                            && (drawer.innerText || "").includes("标签")
                        ));
                }
                """
            )
            if visible:
                return
            time.sleep(0.3)
        raise TimeoutError("more filter drawer did not appear")

    def _wait_quick_edit_environment_name_dialog_visible(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".env-update-dialog, .el-dialog"))
                        .some((dialog) => visible(dialog) && (dialog.innerText || "").includes("编辑环境名称"));
                }
                """
            )
            if visible:
                return
            time.sleep(0.3)
        raise TimeoutError("quick edit environment name dialog did not appear")

    def _wait_export_environment_dialog_visible(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-dialog"))
                        .some((dialog) => visible(dialog) && (dialog.innerText || "").includes("导出环境"));
                }
                """
            )
            if visible:
                return
            time.sleep(0.3)
        raise TimeoutError("export environment dialog did not appear")

    def _wait_batch_set_group_dialog_visible(self) -> None:
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
                        .some((overlay) => visible(overlay) && (overlay.innerText || "").includes("设置环境分组"));
                }
                """
            )
            if visible:
                return
            time.sleep(0.3)
        raise TimeoutError("batch set environment group dialog did not appear")

    def _wait_batch_edit_tag_dialog_visible(self) -> None:
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
                        .some((overlay) => visible(overlay) && (overlay.innerText || "").includes("设置标签"));
                }
                """
            )
            if visible:
                return
            time.sleep(0.3)
        raise TimeoutError("batch edit environment tag dialog did not appear")

    def _wait_batch_group_modify_mode_selected(self, modify_mode: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            selected = self.cdp.evaluate(self._batch_group_modify_mode_selected_script(modify_mode))
            if selected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"batch group modify mode was not selected: {modify_mode}")

    def _wait_batch_tag_modify_mode_selected(self, modify_mode: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            selected = self.cdp.evaluate(self._batch_tag_modify_mode_selected_script(modify_mode))
            if selected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"batch tag modify mode was not selected: {modify_mode}")

    def _wait_tag_management_dialog_visible(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-dialog"))
                        .some((dialog) => visible(dialog) && (dialog.innerText || "").includes("标签管理"));
                }
                """
            )
            if visible:
                return
            time.sleep(0.3)
        raise TimeoutError("tag management dialog did not appear")

    def _wait_column_settings_dialog_visible(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            visible = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-dialog"))
                        .some((dialog) => visible(dialog) && (dialog.innerText || "").includes("列表字段设置"));
                }
                """
            )
            if visible:
                return
            time.sleep(0.3)
        raise TimeoutError("column settings dialog did not appear")

    def _wait_column_settings_field_before(self, source_text: str, target_text: str) -> None:
        self._wait_column_settings_field_relative(source_text, target_text, before=True)

    def _wait_column_settings_field_after(self, source_text: str, target_text: str) -> None:
        self._wait_column_settings_field_relative(source_text, target_text, before=False)

    def _wait_column_settings_field_relative(self, source_text: str, target_text: str, before: bool) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            order = self._column_settings_field_order()
            try:
                source_index = order.index(source_text)
                target_index = order.index(target_text)
            except ValueError:
                source_index = -1
                target_index = -1
            if source_index >= 0 and target_index >= 0:
                if before and source_index < target_index:
                    return
                if not before and source_index > target_index:
                    return
            time.sleep(0.3)
        relation = "before" if before else "after"
        raise TimeoutError(f"column settings field was not moved {relation}: source={source_text}, target={target_text}")

    def _column_settings_field_order(self) -> list[str]:
        value = self.cdp.evaluate(
            """
            () => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };
                const dialogs = Array.from(document.querySelectorAll(".el-dialog"))
                    .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("列表字段设置"));
                const dialog = dialogs[dialogs.length - 1];
                if (!dialog) return [];
                return Array.from(dialog.querySelectorAll(".sortable"))
                    .filter(visible)
                    .map((item) => (item.innerText || item.textContent || "").trim())
                    .filter(Boolean);
            }
            """
        )
        return value if isinstance(value, list) else []

    def _quick_edit_environment_name_input_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const dialogs = Array.from(document.querySelectorAll(".env-update-dialog, .el-dialog"))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("编辑环境名称"));
            for (const dialog of dialogs) {
                const input = Array.from(dialog.querySelectorAll("input"))
                    .find((el) => visible(el) && el.getAttribute("placeholder") === "请填写环境名称");
                if (input) return input;
            }
            return null;
        }
        """

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

    def _confirm_message_box_if_present(self) -> None:
        deadline = time.time() + 2
        while time.time() < deadline:
            visible = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(".el-message-box"))
                        .some(visible);
                }
                """
            )
            if visible:
                try:
                    self.cdp.click_element_by_script(self._message_box_button_script("确认"), timeout=3000)
                except TimeoutError:
                    self.cdp.click_element_by_script(self._message_box_button_script("确定"), timeout=3000)
                self._wait_for_message_box_closed()
                return
            time.sleep(0.2)

    def _tag_exists_in_management_dialog(self, tag_name: str) -> bool:
        return bool(
            self.cdp.evaluate(
                f"""
                () => {{
                    const expectedName = {tag_name!r};
                    const visible = (el) => {{
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    }};
                    const dialogs = Array.from(document.querySelectorAll(".el-dialog"))
                        .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("标签管理"));
                    for (const dialog of dialogs.reverse()) {{
                        const rows = Array.from(dialog.querySelectorAll(".el-table__row, tbody tr"))
                            .filter((row) => visible(row));
                        if (rows.some((row) => (row.innerText || "").includes(expectedName))) return true;
                    }}
                    return false;
                }}
                """
            )
        )

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
