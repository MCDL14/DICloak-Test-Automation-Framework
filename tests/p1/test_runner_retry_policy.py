from __future__ import annotations

import logging
import unittest

from core.result import CaseFailure, RunResult
from core.runner import AutomationRunner


class _RetryPolicyRunner(AutomationRunner):
    def __init__(self, results: list[RunResult]):
        super().__init__({"run": {"retry_times": 1, "retry_interval_seconds": 0}}, logging.getLogger("test"))
        self.results = list(results)
        self.attempts = 0

    def _reload_test(self, test_id: str) -> unittest.TestCase:
        return unittest.FunctionTestCase(lambda: None)

    def _run_single_test_attempt(self, test: unittest.TestCase) -> tuple[RunResult, str]:
        self.attempts += 1
        return self.results.pop(0), ""


class TestRunnerRetryPolicy(unittest.TestCase):
    def test_assertion_failure_is_not_retried(self) -> None:
        runner = _RetryPolicyRunner(
            [
                RunResult(
                    total=1,
                    failed=1,
                    failures=[CaseFailure("case.id", "failed", "AssertionError: expected value mismatch")],
                ),
                RunResult(total=1, passed=1),
            ]
        )

        result = runner._run_suite_with_retry(
            unittest.TestSuite([unittest.FunctionTestCase(lambda: None)]),
            retry_times=1,
            retry_interval_seconds=0,
        )

        self.assertEqual(runner.attempts, 1)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.errors, 0)
        self.assertEqual(result.passed, 0)
        self.assertEqual(result.flaky, 0)

    def test_error_is_retried_and_counts_as_flaky_when_retry_passes(self) -> None:
        runner = _RetryPolicyRunner(
            [
                RunResult(
                    total=1,
                    errors=1,
                    failures=[CaseFailure("case.id", "error", "RuntimeError: transient UI state")],
                ),
                RunResult(total=1, passed=1),
            ]
        )

        result = runner._run_suite_with_retry(
            unittest.TestSuite([unittest.FunctionTestCase(lambda: None)]),
            retry_times=1,
            retry_interval_seconds=0,
        )

        self.assertEqual(runner.attempts, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.errors, 0)
        self.assertEqual(result.passed, 1)
        self.assertEqual(result.flaky, 1)


if __name__ == "__main__":
    unittest.main()
