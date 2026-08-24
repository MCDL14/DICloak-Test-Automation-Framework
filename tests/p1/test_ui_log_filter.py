from __future__ import annotations

import unittest

from core.ui_log_filter import failure_detail_text, unsuccessful_log_text


class UiLogFilterTests(unittest.TestCase):
    def test_failure_detail_keeps_failed_case_block_and_drops_passed_case_logs(self) -> None:
        log_text = "\n".join(
            [
                "2026-08-21 10:00:00 [INFO] CASE START #1 tests.demo.TestOk.test_ok",
                "2026-08-21 10:00:01 [INFO] CASE PASS tests.demo.TestOk.test_ok elapsed=1.00s",
                "2026-08-21 10:00:02 [INFO] CASE START #2 tests.demo.TestBad.test_bad",
                "2026-08-21 10:00:03 [ERROR] CASE FAIL tests.demo.TestBad.test_bad elapsed=1.00s",
                "Traceback (most recent call last):",
                "AssertionError: expected value",
                "2026-08-21 10:00:04 [INFO] CASE START #3 tests.demo.TestAfter.test_after",
                "2026-08-21 10:00:05 [INFO] CASE PASS tests.demo.TestAfter.test_after elapsed=1.00s",
                "2026-08-21 10:00:06 [INFO] Final test summary: total=3 passed=2 failed=1 errors=0 skipped=0 flaky=0",
            ]
        )

        detail = failure_detail_text(log_text)

        self.assertIn("CASE FAIL tests.demo.TestBad.test_bad", detail)
        self.assertIn("AssertionError: expected value", detail)
        self.assertNotIn("CASE PASS tests.demo.TestOk.test_ok", detail)
        self.assertNotIn("CASE PASS tests.demo.TestAfter.test_after", detail)

    def test_unittest_error_block_is_kept(self) -> None:
        log_text = "\n".join(
            [
                "======================================================================",
                "ERROR: test_bad (tests.demo.TestBad.test_bad)",
                "----------------------------------------------------------------------",
                "Traceback (most recent call last):",
                "RuntimeError: boom",
                "----------------------------------------------------------------------",
                "Ran 1 test in 0.001s",
            ]
        )

        detail = failure_detail_text(log_text)

        self.assertIn("ERROR: test_bad", detail)
        self.assertIn("RuntimeError: boom", detail)

    def test_successful_run_returns_empty_message(self) -> None:
        log_text = "\n".join(
            [
                "2026-08-21 10:00:00 [INFO] CASE START #1 tests.demo.TestOk.test_ok",
                "2026-08-21 10:00:01 [INFO] CASE PASS tests.demo.TestOk.test_ok elapsed=1.00s",
                "2026-08-21 10:00:02 [INFO] Final test summary: total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0",
            ]
        )

        self.assertEqual(
            unsuccessful_log_text(log_text),
            "本次执行没有失败、错误或异常日志。",
        )

    def test_remote_fail_lines_are_kept_when_no_case_block_exists(self) -> None:
        log_text = "\n".join(
            [
                "[PASS] Python dependency ok",
                "[FAIL] APP path missing",
                "远程执行失败：退出码=1",
            ]
        )

        detail = failure_detail_text(log_text)

        self.assertIn("[FAIL] APP path missing", detail)
        self.assertIn("远程执行失败：退出码=1", detail)
        self.assertNotIn("[PASS] Python dependency ok", detail)


if __name__ == "__main__":
    unittest.main()
