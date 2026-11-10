from __future__ import annotations

import unittest

from core.ui_log_filter import (
    failure_detail_text,
    localized_failure_overview_text,
    unsuccessful_log_text,
)


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

    def test_localized_overview_precedes_original_failure_log(self) -> None:
        log_text = "\n".join(
            [
                "2026-09-29 10:00:00 [ERROR] CASE ERROR tests.demo.TestBad.test_bad elapsed=2.00s",
                "Traceback (most recent call last):",
                "TimeoutError: element did not appear",
                "2026-09-29 10:00:03 [INFO] Final test summary: total=1 passed=0 failed=0 errors=1",
            ]
        )

        overview = localized_failure_overview_text(log_text)
        displayed = unsuccessful_log_text(log_text)

        self.assertIn("等待超时（TimeoutError）", overview)
        self.assertIn("中文失败摘要", displayed)
        self.assertLess(displayed.index("中文失败摘要"), displayed.index("原始失败日志"))
        self.assertIn("TimeoutError: element did not appear", displayed)

    def test_startup_configuration_errors_are_visible_before_a_run_log_exists(self) -> None:
        for error in ("Config error: invalid APP path", "配置加载失败：测试 APP 路径无效",
                      "测试 APP 包未选择独立测试账号组，已拒绝复用生产账号"):
            with self.subTest(error=error):
                visible = unsuccessful_log_text("已选择 2 条用例，开始执行\n" + error + "\n本机用例执行失败：退出码=2")
                self.assertIn(error, visible)
                self.assertIn("退出码=2", visible)
                self.assertNotIn("已选择 2 条用例", visible)


if __name__ == "__main__":
    unittest.main()
