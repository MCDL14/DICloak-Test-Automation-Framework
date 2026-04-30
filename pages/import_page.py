from __future__ import annotations

import time
from pathlib import Path

from core.config import timeout_seconds as config_timeout_seconds
from pages.base_page import BasePage


class ImportPage(BasePage):
    locator_file = "import_locators.yaml"

    def open_batch_import(self) -> None:
        self.cdp.click_element_by_script(self._batch_create_dropdown_caret_script())
        self.cdp.click_element_by_script(self._visible_dropdown_item_script("批量导入"))
        self._wait_batch_import_drawer_visible()

    def choose_import_file(self, file_path: str | Path) -> None:
        file_path = Path(file_path)
        self.cdp._page().locator("input[type=file][name=file]").set_input_files(str(file_path))
        self._wait_import_file_uploaded(file_path.name)

    def submit_import(self) -> None:
        self.cdp.click_element_by_script(self._active_overlay_button_script("确定"))

    def read_import_result(self) -> str:
        return str(self.cdp.evaluate(self._import_result_dialog_text_script()) or "")

    def failed_environment_text(self) -> str:
        rows = self.import_result_rows()
        failed_rows = [row for row in rows if row.get("result") != "成功"]
        return "\n".join(str(row) for row in failed_rows)

    def wait_import_result(self, expected_count: int, timeout_seconds: int | None = None) -> list[dict[str, str]]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "batch_import_seconds", 120)
        deadline = time.time() + timeout_seconds
        last_text = ""
        while time.time() < deadline:
            last_text = self.read_import_result()
            rows = self.import_result_rows()
            if rows and len(rows) >= expected_count:
                return rows[:expected_count]
            time.sleep(0.5)
        raise TimeoutError(f"batch import result did not appear: expected={expected_count}, text={last_text}")

    def import_result_rows(self) -> list[dict[str, str]]:
        value = self.cdp.evaluate(
            """
            () => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };
                const dialogs = Array.from(document.querySelectorAll(".el-dialog"))
                    .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("导入结果"));
                const dialog = dialogs[dialogs.length - 1];
                if (!dialog) return [];
                return Array.from(dialog.querySelectorAll(".el-table__row, tbody tr"))
                    .filter(visible)
                    .map((row) => {
                        const cells = Array.from(row.querySelectorAll("td"))
                            .map((cell) => (cell.innerText || cell.textContent || "").trim())
                            .filter(Boolean);
                        return {
                            line: cells[0] || "",
                            result: cells[1] || "",
                            reason: cells[2] || "",
                            cells: cells.join("\\n"),
                        };
                    })
                    .filter((row) => row.line || row.result || row.reason);
            }
            """
        )
        return value if isinstance(value, list) else []

    def close_import_result(self) -> None:
        self.cdp.click_element_by_script(self._import_result_close_button_script())
        self._wait_import_result_closed()

    def _wait_batch_import_drawer_visible(self) -> None:
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
                        .some((drawer) => visible(drawer) && (drawer.innerText || "").includes("批量导入"));
                }
                """
            )
            if visible:
                return
            time.sleep(0.3)
        raise TimeoutError("batch import drawer did not appear")

    def _wait_import_file_uploaded(self, file_name: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            uploaded = self.cdp.evaluate(
                f"""
                () => {{
                    const expectedName = {file_name!r};
                    const visible = (el) => {{
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    }};
                    return Array.from(document.querySelectorAll(".el-drawer"))
                        .some((drawer) => visible(drawer) && (drawer.innerText || "").includes(expectedName));
                }}
                """
            )
            if uploaded:
                return
            time.sleep(0.3)
        raise TimeoutError(f"batch import file was not shown after upload: {file_name}")

    def _wait_import_result_closed(self) -> None:
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
                        .some((dialog) => visible(dialog) && (dialog.innerText || "").includes("导入结果"));
                }
                """
            )
            if not visible:
                return
            time.sleep(0.3)
        raise TimeoutError("batch import result dialog did not close")

    def _batch_create_dropdown_caret_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const dropdowns = Array.from(document.querySelectorAll(".el-dropdown"))
                .filter((el) => visible(el) && (el.innerText || "").includes("批量创建"));
            for (const dropdown of dropdowns) {
                const button = dropdown.querySelector("button.el-dropdown__caret-button");
                if (button && visible(button)) return button;
            }
            return null;
        }
        """

    def _visible_dropdown_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const items = Array.from(document.querySelectorAll(".el-dropdown-menu__item, li"))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
            return items[items.length - 1] || null;
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
            const overlays = Array.from(document.querySelectorAll(".el-dialog, .el-drawer, .el-message-box"))
                .filter((el) => visible(el));
            for (const overlay of overlays.reverse()) {{
                const button = Array.from(overlay.querySelectorAll("button"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (button) return button;
            }}
            return null;
        }}
        """

    def _import_result_dialog_text_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const dialogs = Array.from(document.querySelectorAll(".el-dialog"))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("导入结果"));
            return dialogs[dialogs.length - 1]?.innerText || "";
        }
        """

    def _import_result_close_button_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const dialogs = Array.from(document.querySelectorAll(".el-dialog"))
                .filter((dialog) => visible(dialog) && (dialog.innerText || "").includes("导入结果"));
            const dialog = dialogs[dialogs.length - 1];
            if (!dialog) return null;
            return Array.from(dialog.querySelectorAll("button"))
                .find((button) => visible(button) && (button.innerText || button.textContent || "").trim() === "关闭")
                || null;
        }
        """
