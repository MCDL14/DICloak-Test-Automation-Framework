from __future__ import annotations

import unittest
from unittest import mock

from tests.p0.environment_management import test_01_kernel_integrity as kernel_integrity


class KernelIntegrityStageRecoveryTests(unittest.TestCase):
    def test_later_stage_runs_after_previous_stage_failure(self) -> None:
        case = object.__new__(kernel_integrity.TestKernelIntegrity)
        case.logger = mock.MagicMock()
        failures: list[str] = []
        executed: list[str] = []

        def fail_copy_validation() -> None:
            executed.append("copy")
            raise AssertionError("copied kernel path mismatch")

        def download_134() -> str:
            executed.append("download-134")
            return "downloaded"

        first_result = case._run_validation_stage(failures, "校验 142 内核拷贝", fail_copy_validation)
        second_result = case._run_validation_stage(failures, "触发 134 内核下载", download_134)

        self.assertIsNone(first_result)
        self.assertEqual(second_result, "downloaded")
        self.assertEqual(executed, ["copy", "download-134"])
        self.assertEqual(len(failures), 1)
        self.assertIn("copied kernel path mismatch", failures[0])


if __name__ == "__main__":
    unittest.main()
