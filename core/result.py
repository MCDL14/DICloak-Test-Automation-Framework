from __future__ import annotations

import sys
import traceback
import unittest
from dataclasses import dataclass, field


@dataclass
class CaseFailure:
    test_id: str
    status: str
    message: str


@dataclass
class RunResult:
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    flaky: int = 0
    failures: list[CaseFailure] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.passed / self.total * 100, 2)

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0

    def failed_summary(self) -> str:
        if not self.failures:
            return ""
        lines = []
        for failure in self.failures:
            first_line = failure.message.splitlines()[0] if failure.message else ""
            lines.append(f"{failure.status}: {failure.test_id} - {first_line}")
        return "\n".join(lines)


class AutomationTestResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.run_result = RunResult()

    def startTestRun(self) -> None:
        super().startTestRun()
        self.run_result = RunResult()

    def startTest(self, test: unittest.case.TestCase) -> None:
        super().startTest(test)
        self.run_result.total += 1

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        super().addSuccess(test)
        self.run_result.passed += 1

    def addFailure(self, test: unittest.case.TestCase, err) -> None:
        super().addFailure(test, err)
        self.run_result.failed += 1
        self.run_result.failures.append(
            CaseFailure(test.id(), "failed", _format_error(err))
        )

    def addError(self, test: unittest.case.TestCase, err) -> None:
        super().addError(test, err)
        self.run_result.errors += 1
        self.run_result.failures.append(
            CaseFailure(test.id(), "error", _format_error(err))
        )

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self.run_result.skipped += 1


def _format_error(err) -> str:
    return "".join(traceback.format_exception(*err)).strip()


class AutomationTextRunner(unittest.TextTestRunner):
    resultclass = AutomationTestResult

    def run(self, test):
        result = super().run(test)
        if isinstance(result, AutomationTestResult):
            return result
        print("Unexpected unittest result type", file=sys.stderr)
        return result
