from __future__ import annotations

import time
from pathlib import Path

from core.config import timeout_seconds as config_timeout_seconds
from pages.base_page import BasePage


class _BatchImportSubmitNotStarted(RuntimeError):
    pass


class ImportPage(BasePage):
    locator_file = "import_locators.yaml"
    BATCH_IMPORT_DRAWER_REOPEN_RETRIES = 2
    BATCH_IMPORT_SUBMIT_STATE_SECONDS = 3
    BATCH_IMPORT_SECOND_SUBMIT_DELAY_SECONDS = 2
    IMPORT_RESULT_TERMINAL_STATUSES = {"成功", "失败"}

    def open_batch_import(self) -> None:
        self.cdp.click_element_by_script(self._batch_create_dropdown_caret_script())
        self.cdp.click_element_by_script(self._visible_dropdown_item_script("批量导入"))
        self._wait_batch_import_drawer_visible()

    def choose_import_file(self, file_path: str | Path) -> None:
        file_path = Path(file_path)
        self.cdp._page().locator("input[type=file][name=file]").set_input_files(str(file_path))
        self._wait_import_file_uploaded(file_path.name)
        self._selected_import_file = file_path

    def submit_import(self) -> None:
        file_path = getattr(self, "_selected_import_file", None)
        attempts = self.BATCH_IMPORT_DRAWER_REOPEN_RETRIES + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                if file_path is None:
                    break
                self._close_batch_import_drawer_for_retry()
                self.open_batch_import()
                self.choose_import_file(file_path)
            try:
                self._submit_active_batch_import_drawer()
                return
            except _BatchImportSubmitNotStarted as exc:
                last_error = exc
        raise TimeoutError(
            "batch import submit did not start after "
            f"{self.BATCH_IMPORT_DRAWER_REOPEN_RETRIES} drawer reopen retries: "
            f"file={file_path}; last_error={last_error}"
        )

    def _submit_active_batch_import_drawer(self) -> None:
        self.cdp.click_element_by_script(self._batch_import_button_script("确定"))
        state = self._wait_batch_import_submit_state(
            timeout_seconds=self.BATCH_IMPORT_SUBMIT_STATE_SECONDS
        )
        if state != "idle":
            return

        time.sleep(self.BATCH_IMPORT_SECOND_SUBMIT_DELAY_SECONDS)
        # 第一次点击可能延迟启动；补点前再读一次，避免请求已经进入 loading 时重复提交。
        delayed_state = self._current_batch_import_submit_state()
        if delayed_state != "idle":
            return

        self.cdp.click_element_by_script(self._batch_import_button_script("确定"))
        second_state = self._wait_batch_import_submit_state(
            timeout_seconds=self.BATCH_IMPORT_SUBMIT_STATE_SECONDS
        )
        if second_state != "idle":
            return

        raise _BatchImportSubmitNotStarted(
            "batch import drawer submit did not start loading or show the result after second confirm click: "
            f"button_state={self._batch_import_confirm_button_state()}"
        )

    def _wait_batch_import_submit_state(self, timeout_seconds: int) -> str:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            state = self._current_batch_import_submit_state()
            if state != "idle":
                return state
            time.sleep(0.2)
        return self._current_batch_import_submit_state()

    def _current_batch_import_submit_state(self) -> str:
        if self._import_result_dialog_visible():
            return "result"
        if not self._batch_import_drawer_visible():
            return "closed"
        button_state = self._batch_import_confirm_button_state()
        if bool(button_state.get("loading")):
            return "loading"
        return "idle"

    def _close_batch_import_drawer_for_retry(self) -> None:
        if not self._batch_import_drawer_visible():
            return
        try:
            self.cdp.click_element_by_script(self._batch_import_button_script("取消"), timeout=3000)
        except Exception:
            self.cdp.press("Escape")
        self._wait_batch_import_drawer_closed()

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
        last_rows: list[dict[str, str]] = []
        while time.time() < deadline:
            last_text = self.read_import_result()
            rows = self.import_result_rows()
            last_rows = rows[:expected_count]
            if len(last_rows) == expected_count and all(
                row.get("result") in self.IMPORT_RESULT_TERMINAL_STATUSES
                for row in last_rows
            ):
                return last_rows
            time.sleep(0.5)
        raise TimeoutError(
            "batch import result did not finish rendering: "
            f"expected={expected_count}, rows={last_rows}, text={last_text}"
        )

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

    def close_import_result_if_visible(self) -> bool:
        """Best-effort idempotent cleanup for normal and assertion-failure paths."""
        if not self._import_result_dialog_visible():
            return False
        click_error: Exception | None = None
        try:
            self.close_import_result()
            return True
        except Exception as exc:
            click_error = exc
            # Element Plus overlays can be mid-transition when an assertion interrupts the flow.
            # Escape is a safe secondary close path for the top-most result dialog.
        try:
            self.cdp.press("Escape")
            self._wait_import_result_closed()
            return True
        except Exception as escape_error:
            raise RuntimeError(
                "failed to close batch import result dialog with button and Escape: "
                f"button_error={click_error}; escape_error={escape_error}"
            ) from escape_error

    def close_batch_import_if_visible(self) -> bool:
        if not self._batch_import_drawer_visible():
            return False
        self._close_batch_import_drawer_for_retry()
        return True

    def close_import_overlays(self) -> None:
        """Leave the environment list usable even when import verification fails."""
        errors: list[str] = []
        for label, closer in (
            ("result_dialog", self.close_import_result_if_visible),
            ("import_drawer", self.close_batch_import_if_visible),
        ):
            try:
                closer()
            except Exception as exc:
                errors.append(f"{label}={type(exc).__name__}: {exc}")
        if errors:
            raise RuntimeError("batch import overlay cleanup incomplete: " + "; ".join(errors))

    def _wait_batch_import_drawer_visible(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self._batch_import_drawer_visible():
                return
            time.sleep(0.3)
        raise TimeoutError("batch import drawer did not appear")

    def _wait_batch_import_drawer_closed(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if not self._batch_import_drawer_visible():
                return
            time.sleep(0.2)
        raise TimeoutError("batch import drawer did not close before retry")

    def _batch_import_drawer_visible(self) -> bool:
        return bool(self.cdp.evaluate(self._batch_import_drawer_visible_script()))

    def _batch_import_confirm_button_state(self) -> dict:
        value = self.cdp.evaluate(self._batch_import_confirm_button_state_script())
        return value if isinstance(value, dict) else {}

    def _import_result_dialog_visible(self) -> bool:
        return bool(self.cdp.evaluate(self._import_result_dialog_visible_script()))

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

    def _batch_import_drawer_visible_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity || "1") > 0.01
                    && el.getAttribute("aria-hidden") !== "true"
                    && !el.classList.contains("is-leave")
                    && rect.width > 0
                    && rect.height > 0
                    && rect.right > 0
                    && rect.bottom > 0
                    && rect.left < window.innerWidth
                    && rect.top < window.innerHeight;
            };
            return Array.from(document.querySelectorAll(".el-drawer"))
                .some((drawer) => visible(drawer) && (drawer.innerText || "").includes("批量导入"));
        }
        """

    def _batch_import_button_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity || "1") > 0.01
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const drawers = Array.from(document.querySelectorAll(".el-drawer"))
                .filter((drawer) => visible(drawer) && (drawer.innerText || "").includes("批量导入"));
            for (const drawer of drawers.reverse()) {{
                const button = Array.from(drawer.querySelectorAll("button"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (button) return button;
            }}
            return null;
        }}
        """

    def _batch_import_confirm_button_state_script(self) -> str:
        return f"""
        () => {{
            const finder = {self._batch_import_button_script("确定")};
            const button = finder();
            if (!button) return {{ visible: false, loading: false, disabled: false }};
            const className = String(button.className || "");
            const ariaDisabled = button.getAttribute("aria-disabled");
            const loading = button.classList.contains("is-loading")
                || Boolean(button.querySelector(".is-loading, .el-icon-loading, [class*='loading']"));
            const disabled = Boolean(button.disabled)
                || ariaDisabled === "true"
                || button.classList.contains("is-disabled");
            return {{ visible: true, loading, disabled, ariaDisabled, className }};
        }}
        """

    def _import_result_dialog_visible_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity || "1") > 0.01
                    && rect.width > 0
                    && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(".el-dialog"))
                .some((dialog) => visible(dialog) && (dialog.innerText || "").includes("导入结果"));
        }
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
