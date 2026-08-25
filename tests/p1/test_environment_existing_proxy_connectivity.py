from __future__ import annotations

import unittest

from core.kernel_cdp import KernelPageResult
from tests.p0.environment_management.test_43_create_environment_with_existing_proxy import (
    CHROME_WEBSTORE_URL,
    chrome_webstore_page_reachable,
)


class ExistingProxyChromeWebStoreReachabilityTests(unittest.TestCase):
    def test_matching_loaded_page_is_reachable(self) -> None:
        result = self._result(
            target_url="https://chromewebstore.google.com/category/extensions",
            title="Chrome Web Store",
            text="Chrome Web Store extensions and themes are available here.",
        )

        self.assertTrue(chrome_webstore_page_reachable(result))

    def test_navigation_error_is_not_reachable(self) -> None:
        result = self._result(
            target_url=CHROME_WEBSTORE_URL,
            title="chromewebstore.google.com",
            text="This site cannot be reached ERR_PROXY_CONNECTION_FAILED",
            error_text="net::ERR_PROXY_CONNECTION_FAILED",
        )

        self.assertFalse(chrome_webstore_page_reachable(result))

    def test_unexpected_target_host_is_not_reachable(self) -> None:
        result = self._result(
            target_url="https://example.com/",
            title="Example Domain",
            text="Example Domain is available for illustrative examples.",
        )

        self.assertFalse(chrome_webstore_page_reachable(result))

    def test_blank_target_page_is_not_reachable(self) -> None:
        result = self._result(
            target_url=CHROME_WEBSTORE_URL,
            title="",
            text="",
        )

        self.assertFalse(chrome_webstore_page_reachable(result))

    @staticmethod
    def _result(
        *,
        target_url: str,
        title: str,
        text: str,
        error_text: str = "",
    ) -> KernelPageResult:
        return KernelPageResult(
            requested_url=CHROME_WEBSTORE_URL,
            target_id="target-1",
            target_url=target_url,
            title=title,
            text=text,
            error_text=error_text,
        )


if __name__ == "__main__":
    unittest.main()
