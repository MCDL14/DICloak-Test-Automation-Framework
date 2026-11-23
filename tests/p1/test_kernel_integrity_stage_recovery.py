from __future__ import annotations

import copy
import logging
import unittest

from core.config import DEFAULT_CONFIG
from core.runner import AutomationRunner
from tests.p0.environment_management import test_01_kernel_integrity as old_integrity


class KernelDownloadDiscoveryTests(unittest.TestCase):
    def test_old_kernel_integrity_is_fully_disabled(self) -> None:
        suite = unittest.defaultTestLoader.loadTestsFromModule(old_integrity)
        self.assertEqual(suite.countTestCases(), 0)
        self.assertFalse(hasattr(old_integrity, "TestKernelIntegrity"))

    def test_downloads_run_first_and_old_case_is_absent(self) -> None:
        runner = AutomationRunner(copy.deepcopy(DEFAULT_CONFIG), logging.getLogger("kernel-discovery-test"))
        suite = runner._prioritize_suite(runner._build_suite(level="p0", module=None, case=None))
        ids = [case.id() for case in runner._iter_tests(suite)]

        self.assertEqual(len(ids), 101)
        self.assertTrue(ids[0].endswith("TestDownload142Kernel.test_download_142_kernel_and_verify_environment"))
        self.assertTrue(ids[1].endswith("TestDownload152Kernel.test_download_152_kernel_and_verify_environment"))
        self.assertFalse(any("test_01_kernel_integrity" in case_id for case_id in ids))
        self.assertFalse(any("134_kernel" in case_id for case_id in ids))


if __name__ == "__main__":
    unittest.main()
