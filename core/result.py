from __future__ import annotations

import sys
import traceback
import unittest
from dataclasses import dataclass, field
from typing import Any

from core.recovery import TestRecoveryManager
from core.screenshot import capture_failure_screenshot


@dataclass
class CaseFailure:
    test_id: str
    status: str
    message: str
    screenshot_path: str = ""


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
            screenshot = f" screenshot={failure.screenshot_path}" if failure.screenshot_path else ""
            lines.append(f"{failure.status}: {failure.test_id} - {first_line}{screenshot}")
        return "\n".join(lines)


class AutomationTestResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.run_result = RunResult()
        self.recovery = TestRecoveryManager()

    def startTestRun(self) -> None:
        super().startTestRun()
        self.run_result = RunResult()

    def startTest(self, test: unittest.case.TestCase) -> None:
        super().startTest(test)
        self.run_result.total += 1
        self.recovery.recover_before_test(test)

    def stopTest(self, test: unittest.case.TestCase) -> None:
        self.recovery.recover_after_test(test)
        super().stopTest(test)

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        super().addSuccess(test)
        self.run_result.passed += 1

    def addFailure(self, test: unittest.case.TestCase, err) -> None:
        super().addFailure(test, err)
        self.run_result.failed += 1
        self._record_case_failure(test, "failed", err)

    def addError(self, test: unittest.case.TestCase, err) -> None:
        super().addError(test, err)
        self.run_result.errors += 1
        self._record_case_failure(test, "error", err)

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self.run_result.skipped += 1

    def _record_case_failure(self, test: unittest.case.TestCase, status: str, err) -> None:
        screenshot_path = self._capture_screenshot(test)
        self.run_result.failures.append(
            CaseFailure(test.id(), status, _format_error(err), screenshot_path=screenshot_path)
        )

    def _capture_screenshot(self, test: unittest.case.TestCase) -> str:
        config = _test_attr(test, "config", {})
        if not isinstance(config, dict):
            config = {}
        if not config.get("run", {}).get("screenshot_on_failure", True):
            return ""
        logger = _test_attr(test, "logger", None)
        screenshot_path = capture_failure_screenshot(
            config=config,
            test_id=test.id(),
            cdp=_test_attr(test, "cdp", None),
            ui=_test_attr(test, "ui", None),
            logger=logger,
        )
        if logger and screenshot_path:
            logger.info("Failure screenshot path recorded for %s: %s", test.id(), screenshot_path)
        return screenshot_path


def _format_error(err) -> str:
    return "".join(traceback.format_exception(*err)).strip()


def _test_attr(test: unittest.case.TestCase, name: str, default: Any = None) -> Any:
    return getattr(test, name, default)


class AutomationTextRunner(unittest.TextTestRunner):
    resultclass = AutomationTestResult

    def run(self, test):
        result = super().run(test)
        if isinstance(result, AutomationTestResult):
            return result
        print("Unexpected unittest result type", file=sys.stderr)
        return result
