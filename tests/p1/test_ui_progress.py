from __future__ import annotations

import unittest
from datetime import datetime
from io import StringIO
from time import perf_counter
from unittest.mock import Mock

from core.result import AutomationTestResult
from core.ui_progress import case_progress_snapshot


CASES = [
    {
        "id": "tests.demo.TestOne.test_one",
        "display_name": "用例一",
        "module": "模块A",
        "method_name": "test_one",
    },
    {
        "id": "tests.demo.TestTwo.test_two",
        "display_name": "用例二",
        "module": "模块A",
        "method_name": "test_two",
    },
]


class UiProgressTests(unittest.TestCase):
    def test_local_case_progress_marks_finished_and_pending_cases(self) -> None:
        snapshot = case_progress_snapshot(
            CASES,
            [
                "2026-08-24 10:00:00 [INFO] CASE START #1 tests.demo.TestOne.test_one",
                "2026-08-24 10:00:02 [INFO] CASE PASS tests.demo.TestOne.test_one elapsed=2.00s",
            ],
            platforms=["本机"],
            default_platform="本机",
        )

        self.assertEqual(snapshot["total"], 2)
        self.assertEqual(snapshot["finished"], 1)
        self.assertEqual(snapshot["pending"], 1)
        self.assertEqual(snapshot["rows"][0]["状态"], "通过")
        self.assertEqual(snapshot["rows"][0]["状态码"], "passed")
        self.assertEqual(snapshot["rows"][0]["用时秒"], 2.0)
        self.assertEqual(snapshot["rows"][1]["状态"], "待执行")

    def test_retry_pass_overrides_first_error_as_flaky_passed(self) -> None:
        snapshot = case_progress_snapshot(
            CASES[:1],
            [
                "2026-08-24 10:00:00 [INFO] CASE START #1 tests.demo.TestOne.test_one",
                "2026-08-24 10:00:01 [ERROR] CASE ERROR tests.demo.TestOne.test_one elapsed=1.00s",
                "2026-08-24 10:00:02 [INFO] Retrying tests.demo.TestOne.test_one after 3.0 second(s)",
                "2026-08-24 10:00:06 [INFO] CASE START #1 tests.demo.TestOne.test_one",
                "2026-08-24 10:00:07 [INFO] CASE PASS tests.demo.TestOne.test_one elapsed=1.00s",
                "2026-08-24 10:00:07 [INFO] Test passed after retry: tests.demo.TestOne.test_one, attempt 2/2",
            ],
            platforms=["本机"],
            default_platform="本机",
        )

        self.assertEqual(snapshot["finished"], 1)
        self.assertEqual(snapshot["problem"], 0)
        self.assertEqual(snapshot["rows"][0]["状态"], "重试通过")
        self.assertGreaterEqual(snapshot["rows"][0]["用时秒"], 2.0)

    def test_prefixed_dual_platform_logs_update_each_platform_independently(self) -> None:
        snapshot = case_progress_snapshot(
            CASES,
            [
                "[Windows] 2026-08-24 10:00:00 [INFO] CASE START #1 tests.demo.TestOne.test_one",
                "[Windows] 2026-08-24 10:00:01 [INFO] CASE PASS tests.demo.TestOne.test_one elapsed=1.00s",
                "[macOS] 2026-08-24 10:00:00 [INFO] CASE START #1 tests.demo.TestOne.test_one",
                "[macOS] 2026-08-24 10:00:01 [ERROR] CASE FAIL tests.demo.TestOne.test_one elapsed=1.00s",
            ],
            platforms=["Windows", "macOS"],
            default_platform="Windows",
        )

        rows = {(row["执行端"], row["原始用例"]): row for row in snapshot["rows"]}
        self.assertEqual(rows[("Windows", "tests.demo.TestOne.test_one")]["状态"], "通过")
        self.assertEqual(rows[("macOS", "tests.demo.TestOne.test_one")]["状态"], "断言失败")
        self.assertEqual(rows[("Windows", "tests.demo.TestTwo.test_two")]["状态"], "待执行")
        self.assertEqual(rows[("macOS", "tests.demo.TestTwo.test_two")]["状态"], "待执行")
        self.assertEqual(snapshot["total"], 4)
        self.assertEqual(snapshot["finished"], 2)
        self.assertEqual(snapshot["problem"], 1)

    def test_failure_error_and_skip_keep_distinct_labels_durations_and_details(self) -> None:
        cases = CASES + [
            {
                "id": "tests.demo.TestThree.test_three",
                "display_name": "用例三",
                "module": "模块B",
                "method_name": "test_three",
            }
        ]
        snapshot = case_progress_snapshot(
            cases,
            [
                "2026-08-24 10:00:00 [INFO] CASE START #1 tests.demo.TestOne.test_one",
                "2026-08-24 10:00:02 [ERROR] CASE FAIL tests.demo.TestOne.test_one elapsed=2.25s\nAssertionError: value mismatch",
                "2026-08-24 10:00:03 [INFO] CASE START #2 tests.demo.TestTwo.test_two",
                "2026-08-24 10:00:07 [ERROR] CASE ERROR tests.demo.TestTwo.test_two elapsed=4.50s\nTimeoutError: element missing",
                "2026-08-24 10:00:08 [INFO] CASE START #3 tests.demo.TestThree.test_three",
                "2026-08-24 10:00:08 [INFO] CASE SKIP tests.demo.TestThree.test_three elapsed=0.10s reason=platform mismatch",
            ],
        )

        rows = {row["状态码"]: row for row in snapshot["rows"]}
        self.assertEqual(snapshot["counts"]["failed"], 1)
        self.assertEqual(snapshot["counts"]["error"], 1)
        self.assertEqual(snapshot["counts"]["skipped"], 1)
        self.assertEqual(rows["failed"]["状态"], "断言失败")
        self.assertEqual(rows["failed"]["用时秒"], 2.25)
        self.assertIn("value mismatch", rows["failed"]["详情"])
        self.assertEqual(rows["error"]["状态"], "执行错误")
        self.assertEqual(rows["error"]["用时秒"], 4.5)
        self.assertIn("element missing", rows["error"]["详情"])
        self.assertEqual(rows["skipped"]["状态"], "跳过")
        self.assertEqual(rows["skipped"]["用时秒"], 0.1)
        self.assertEqual(rows["skipped"]["详情"], "跳过原因：platform mismatch")

    def test_running_case_exposes_live_elapsed_baseline(self) -> None:
        observed_at = datetime.strptime("2026-08-24 10:00:03", "%Y-%m-%d %H:%M:%S").timestamp()
        snapshot = case_progress_snapshot(
            CASES[:1],
            ["2026-08-24 10:00:00 [INFO] CASE START #1 tests.demo.TestOne.test_one"],
            observed_at=observed_at,
        )

        row = snapshot["rows"][0]
        self.assertEqual(row["状态码"], "running")
        self.assertTrue(row["是否计时"])
        self.assertEqual(row["用时秒"], 3.0)

    def test_skipped_case_log_includes_elapsed_seconds(self) -> None:
        test = unittest.FunctionTestCase(lambda: None)
        test.logger = Mock()
        result = AutomationTestResult(stream=StringIO(), descriptions=True, verbosity=1)
        result._test_start_times[test.id()] = perf_counter() - 0.01

        result.addSkip(test, "platform mismatch")

        log_args = test.logger.info.call_args.args
        self.assertEqual(log_args[0], "CASE SKIP %s elapsed=%.2fs reason=%s")
        self.assertEqual(log_args[1], test.id())
        self.assertGreaterEqual(log_args[2], 0.0)
        self.assertEqual(log_args[3], "platform mismatch")


if __name__ == "__main__":
    unittest.main()
