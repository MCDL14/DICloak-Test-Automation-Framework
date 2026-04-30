from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path
from typing import Any

from core.app import AppManager, AppStartupError
from core.case_module import get_test_case_module, normalize_case_module, supported_case_modules_text
from core.cdp_driver import CDPConnectionError, CDPDriver
from core.circuit_breaker import BreakerName, CircuitBreakerRegistry
from core.feishu import FeishuNotifier
from core.precheck import EnvironmentPrechecker
from core.result import AutomationTextRunner, RunResult


class ExitCode:
    SUCCESS = 0
    TEST_FAILED = 1
    CONFIG_OR_PRECHECK_ERROR = 2
    APP_OR_CDP_ERROR = 3
    USER_INTERRUPTED = 130


class AutomationRunner:
    PRIORITY_TEST_MODULES = (
        "tests.p0.environment_management.test_01_kernel_integrity",
    )

    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.notifier = FeishuNotifier(config, logger)
        self.breakers = CircuitBreakerRegistry()

    def run_precheck_only(self) -> int:
        result = EnvironmentPrechecker(self.config, self.logger).run()
        return ExitCode.SUCCESS if result.passed else ExitCode.CONFIG_OR_PRECHECK_ERROR

    def run(
        self,
        level: str | None = None,
        module: str | None = None,
        business_module: str | None = None,
        case: str | None = None,
        attach_existing_app: bool = False,
    ) -> int:
        if self.config["run"].get("precheck_before_run", True):
            precheck = EnvironmentPrechecker(self.config, self.logger).run()
            if not precheck.passed:
                self.notifier.send_failure(
                    "Dicloak 自动化环境预检失败",
                    "\n".join(f"{item.name}: {item.message}" for item in precheck.failed_items),
                )
                return ExitCode.CONFIG_OR_PRECHECK_ERROR

        suite = self._build_suite(level=level, module=module, case=case)
        if business_module:
            suite = self._filter_suite_by_business_module(suite, business_module)
        suite = self._prioritize_suite(suite)
        case_count = suite.countTestCases()
        self.logger.info("Discovered %s test case(s)", case_count)
        if case_count == 0:
            empty_result = RunResult(total=0)
            self.notifier.send_summary(empty_result)
            return ExitCode.SUCCESS

        app_manager = AppManager(self.config, self.logger)
        cdp_driver = CDPDriver(self.config, self.logger)
        app_started = False
        try:
            if attach_existing_app:
                self.logger.info("Attach existing APP mode enabled; skipping APP startup and shutdown")
            else:
                app_started = app_manager.launch_fresh()
                if not app_started:
                    self.notifier.send_failure(
                        "Dicloak APP 进程检测失败",
                        "启动后 30 秒内未检测到 APP 进程，将继续尝试 CDP 连接。",
                    )
            cdp_driver.connect()
            cdp_driver.close()
            self.logger.info("CDP startup check passed and connection released before test execution")
        except (AppStartupError, CDPConnectionError, OSError) as exc:
            self.breakers.trip(BreakerName.APP_STARTUP, str(exc))
            self.notifier.send_failure("Dicloak APP 启动或 CDP 连接失败", str(exc))
            return ExitCode.APP_OR_CDP_ERROR

        try:
            result = self._run_suite(suite)
            self.notifier.send_summary(result)
            return ExitCode.SUCCESS if result.success else ExitCode.TEST_FAILED
        finally:
            cdp_driver.close()
            if not attach_existing_app:
                app_manager.close()

    def _build_suite(self, level: str | None, module: str | None, case: str | None) -> unittest.TestSuite:
        tests_root = Path("tests")
        selected_level = (level or self.config["run"].get("case_level") or "P0").lower()

        if case:
            suite = self._discover_suite(tests_root)
            return self._filter_suite(suite, case)

        if module:
            return self._build_module_suite(
                tests_root=tests_root,
                selected_level=selected_level,
                module=module,
                level_was_explicit=level is not None,
            )

        start_dir = tests_root / selected_level
        return self._discover_suite(start_dir)

    def _build_module_suite(
        self,
        tests_root: Path,
        selected_level: str,
        module: str,
        level_was_explicit: bool,
    ) -> unittest.TestSuite:
        module_value = module.strip()
        if not module_value:
            self.logger.warning("Module argument is empty")
            return unittest.TestSuite()

        module_path = self._resolve_module_path(tests_root, selected_level, module_value)
        if module_path:
            if module_path.is_file():
                self.logger.info("Running test module file: %s", module_path)
                return self._discover_suite(module_path.parent, pattern=module_path.name)
            if module_path.is_dir():
                self.logger.info("Running test module directory: %s", module_path)
                return self._discover_suite(module_path)

        start_dir = tests_root / selected_level if level_was_explicit else tests_root
        suite = self._discover_suite(start_dir)
        module_key = self._normalize_module_keyword(module_value)
        filtered = self._filter_suite(suite, module_key)
        if filtered.countTestCases() == 0:
            self.logger.warning(
                "No test cases matched module '%s'. Supported forms include: "
                "--module test_xxx.py, --module p0/test_xxx.py, --module tests/p0/test_xxx.py, "
                "or --module package.module_keyword",
                module,
            )
        return filtered

    def _discover_suite(self, start_dir: Path, pattern: str = "test_*.py") -> unittest.TestSuite:
        if not start_dir.exists():
            self.logger.warning("Test directory does not exist: %s", start_dir)
            return unittest.TestSuite()
        return unittest.defaultTestLoader.discover(
            str(start_dir.resolve()),
            pattern=pattern,
            top_level_dir=str(Path.cwd().resolve()),
        )

    def _filter_suite(self, suite: unittest.TestSuite, keyword: str) -> unittest.TestSuite:
        filtered = unittest.TestSuite()
        for test in self._iter_tests(suite):
            if keyword in test.id():
                filtered.addTest(test)
        return filtered

    def _filter_suite_by_business_module(self, suite: unittest.TestSuite, business_module: str) -> unittest.TestSuite:
        expected_module = normalize_case_module(business_module)
        filtered = unittest.TestSuite()
        if not expected_module:
            self.logger.warning(
                "Unsupported business module '%s'. Supported modules: %s",
                business_module,
                supported_case_modules_text(),
            )
            return filtered

        for test in self._iter_tests(suite):
            if get_test_case_module(test) == expected_module:
                filtered.addTest(test)

        if filtered.countTestCases() == 0:
            self.logger.warning(
                "No test cases matched business module '%s'. Supported modules: %s",
                business_module,
                supported_case_modules_text(),
            )
        else:
            self.logger.info(
                "Applied business module filter: %s, matched %s test case(s)",
                expected_module,
                filtered.countTestCases(),
            )
        return filtered

    def _iter_tests(self, suite: unittest.TestSuite):
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                yield from self._iter_tests(item)
            else:
                yield item

    def _prioritize_suite(self, suite: unittest.TestSuite) -> unittest.TestSuite:
        tests = list(self._iter_tests(suite))
        if len(tests) <= 1:
            return suite

        def sort_key(test) -> tuple[int, str]:
            test_id = test.id()
            for index, module_name in enumerate(self.PRIORITY_TEST_MODULES):
                if test_id.startswith(module_name):
                    return index, test_id
            return len(self.PRIORITY_TEST_MODULES), test_id

        ordered = sorted(tests, key=sort_key)
        if ordered != tests:
            self.logger.info(
                "Applied test execution priority: %s",
                ", ".join(self.PRIORITY_TEST_MODULES),
            )
        return unittest.TestSuite(ordered)

    def _resolve_module_path(self, tests_root: Path, selected_level: str, module: str) -> Path | None:
        normalized = module.replace("\\", "/").strip("/")
        path_forms = [normalized]
        if "." in normalized and "/" not in normalized:
            path_forms.append(normalized.replace(".", "/"))

        candidates: list[Path] = []
        for path_form in path_forms:
            raw_path = Path(path_form)
            candidate_roots = [Path.cwd(), tests_root, tests_root / selected_level]
            for root in candidate_roots:
                candidates.append(root / raw_path)
                if raw_path.suffix != ".py":
                    candidates.append(root / f"{path_form}.py")

        tests_root_resolved = tests_root.resolve()
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if not self._is_inside(resolved, tests_root_resolved):
                continue
            if resolved.is_file() or resolved.is_dir():
                return resolved
        return None

    def _normalize_module_keyword(self, module: str) -> str:
        keyword = module.replace("\\", "/").strip()
        if keyword.endswith(".py"):
            keyword = keyword[:-3]
        if keyword.startswith("tests/"):
            keyword = keyword[len("tests/") :]
        return keyword.strip("/").replace("/", ".")

    def _is_inside(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    def _run_suite(self, suite: unittest.TestSuite) -> RunResult:
        runner = AutomationTextRunner(stream=sys.stdout, verbosity=2)
        unittest_result = runner.run(suite)
        return unittest_result.run_result
