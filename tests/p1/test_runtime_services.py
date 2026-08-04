from __future__ import annotations

import unittest
import tempfile
from copy import deepcopy
from logging import getLogger
from unittest.mock import patch

from core.config import DEFAULT_CONFIG, deep_merge, validate_config
from core.local_auth_lab.precheck import LocalAuthLabPrechecker
from core.runtime_services import (
    RuntimeServiceError,
    RuntimeServiceManager,
    collect_required_runtime_services,
)


class RuntimeServiceDependencyTests(unittest.TestCase):
    def test_ordinary_suite_has_empty_fast_path(self) -> None:
        suite = unittest.TestSuite([_case()])
        self.assertEqual(collect_required_runtime_services(suite), frozenset())
        self.assertFalse(DEFAULT_CONFIG["local_auth_lab"]["enabled"])
        legacy_config = deepcopy(DEFAULT_CONFIG)
        legacy_config.pop("local_auth_lab")
        merged = deep_merge(DEFAULT_CONFIG, legacy_config)
        validate_config(merged)
        self.assertFalse(merged["local_auth_lab"]["enabled"])
        manager = RuntimeServiceManager(merged, getLogger("runtime-services-test"))
        manager.start(())
        self.assertIsNone(manager.local_auth_lab)

    def test_nested_suite_collects_explicit_auth_lab_dependency(self) -> None:
        suite = unittest.TestSuite([unittest.TestSuite([_case(), _case({"local_auth_lab"})])])
        self.assertEqual(collect_required_runtime_services(suite), frozenset({"local_auth_lab"}))

    def test_unknown_runtime_service_fails_before_app_start(self) -> None:
        with self.assertRaises(RuntimeServiceError):
            collect_required_runtime_services(unittest.TestSuite([_case({"unknown_service"})]))

    def test_explicit_dependency_rejects_non_persistent_disabled_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            config = deepcopy(DEFAULT_CONFIG)
            config["_project_root"] = raw_dir
            self.assertFalse(config["local_auth_lab"]["enabled"])
            manager = RuntimeServiceManager(config, getLogger("runtime-services-reuse-test"))

            with patch(
                "core.runtime_services.LocalAuthLabServer.try_reuse_existing",
                side_effect=AssertionError("disabled configuration must not reuse a service"),
            ), patch(
                "core.runtime_services.LocalAuthLabPrechecker.run",
                wraps=LocalAuthLabPrechecker(config).run,
            ):
                with self.assertRaisesRegex(RuntimeServiceError, "local_auth_lab is disabled"):
                    manager.start({"local_auth_lab"})

            self.assertIsNone(manager.local_auth_lab)


def _case(required: set[str] | None = None) -> unittest.FunctionTestCase:
    case = unittest.FunctionTestCase(lambda: None)
    if required is not None:
        case.REQUIRED_RUNTIME_SERVICES = required
    return case


if __name__ == "__main__":
    unittest.main()
