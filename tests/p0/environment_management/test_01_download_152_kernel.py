from __future__ import annotations

import unittest

from tests.p0.environment_management.kernel_download_case import KernelDownloadCaseMixin


CASE_MODULE = "环境管理"


class TestDownload152Kernel(KernelDownloadCaseMixin, unittest.TestCase):
    def test_download_152_kernel_and_verify_environment(self) -> None:
        self._download_kernel_and_verify_environment("152")


if __name__ == "__main__":
    unittest.main()
