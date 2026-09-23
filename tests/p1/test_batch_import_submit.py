from __future__ import annotations

import unittest
from pathlib import Path

from pages.import_page import ImportPage, _BatchImportSubmitNotStarted


class _BatchImportSubmitProbe(ImportPage):
    BATCH_IMPORT_SECOND_SUBMIT_DELAY_SECONDS = 0

    def __init__(self, wait_states: list[str], delayed_states: list[str] | None = None) -> None:
        self.cdp = self
        self.wait_states = list(wait_states)
        self.delayed_states = list(delayed_states or [])
        self.calls: list[object] = []

    def _batch_import_button_script(self, text: str) -> str:
        return f"button:{text}"

    def click_element_by_script(self, script: str, timeout: int | None = None) -> None:
        self.calls.append(("click", script))

    def _wait_batch_import_submit_state(self, timeout_seconds: int) -> str:
        self.calls.append(("wait-state", timeout_seconds))
        return self.wait_states.pop(0)

    def _current_batch_import_submit_state(self) -> str:
        self.calls.append("read-delayed-state")
        return self.delayed_states.pop(0)

    def _batch_import_confirm_button_state(self) -> dict:
        return {"loading": False}


class _BatchImportRetryProbe(ImportPage):
    BATCH_IMPORT_DRAWER_REOPEN_RETRIES = 2

    def __init__(self) -> None:
        self.cdp = self
        self._selected_import_file = Path("自动化-导入环境.xlsx")
        self.calls: list[object] = []
        self.submit_attempts = 0

    def _submit_active_batch_import_drawer(self) -> None:
        self.submit_attempts += 1
        self.calls.append(("submit", self.submit_attempts))
        if self.submit_attempts < 3:
            raise _BatchImportSubmitNotStarted("idle")

    def _close_batch_import_drawer_for_retry(self) -> None:
        self.calls.append("close-drawer")

    def open_batch_import(self) -> None:
        self.calls.append("open-drawer")

    def choose_import_file(self, file_path: str | Path) -> None:
        self.calls.append(("choose-file", Path(file_path)))
        self._selected_import_file = Path(file_path)


class BatchImportSubmitTests(unittest.TestCase):
    def test_first_click_loading_does_not_click_again(self) -> None:
        page = _BatchImportSubmitProbe(["loading"])

        page._submit_active_batch_import_drawer()

        self.assertEqual(page.calls, [("click", "button:确定"), ("wait-state", 3)])

    def test_idle_first_click_uses_second_confirm_and_accepts_result(self) -> None:
        page = _BatchImportSubmitProbe(["idle", "result"], ["idle"])

        page._submit_active_batch_import_drawer()

        self.assertEqual(
            page.calls,
            [
                ("click", "button:确定"),
                ("wait-state", 3),
                "read-delayed-state",
                ("click", "button:确定"),
                ("wait-state", 3),
            ],
        )

    def test_late_loading_before_second_click_prevents_duplicate_submit(self) -> None:
        page = _BatchImportSubmitProbe(["idle"], ["loading"])

        page._submit_active_batch_import_drawer()

        self.assertEqual(
            page.calls,
            [
                ("click", "button:确定"),
                ("wait-state", 3),
                "read-delayed-state",
            ],
        )

    def test_submit_reopens_drawer_and_reuploads_after_two_idle_attempts(self) -> None:
        page = _BatchImportRetryProbe()

        page.submit_import()

        self.assertEqual(
            page.calls,
            [
                ("submit", 1),
                "close-drawer",
                "open-drawer",
                ("choose-file", Path("自动化-导入环境.xlsx")),
                ("submit", 2),
                "close-drawer",
                "open-drawer",
                ("choose-file", Path("自动化-导入环境.xlsx")),
                ("submit", 3),
            ],
        )


if __name__ == "__main__":
    unittest.main()
