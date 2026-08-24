from __future__ import annotations

import unittest

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
        self.assertEqual(rows[("macOS", "tests.demo.TestOne.test_one")]["状态"], "失败")
        self.assertEqual(rows[("Windows", "tests.demo.TestTwo.test_two")]["状态"], "待执行")
        self.assertEqual(rows[("macOS", "tests.demo.TestTwo.test_two")]["状态"], "待执行")
        self.assertEqual(snapshot["total"], 4)
        self.assertEqual(snapshot["finished"], 2)
        self.assertEqual(snapshot["problem"], 1)


if __name__ == "__main__":
    unittest.main()
