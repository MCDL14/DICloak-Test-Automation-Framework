from __future__ import annotations

import copy
import logging
import sys
import types
import unittest
from unittest import mock

from core.cdp_driver import CDPConnectionError, CDPDriver
from core.config import DEFAULT_CONFIG


def _config(**cdp_overrides):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["cdp"].update(cdp_overrides)
    return config


class TestCDPDriverConnection(unittest.TestCase):
    def test_playwright_connect_timeout_is_passed_to_cdp_attach(self) -> None:
        seen_timeouts: list[int | None] = []

        class FakeChromium:
            def connect_over_cdp(self, endpoint, timeout=None):
                seen_timeouts.append(timeout)
                raise RuntimeError(f"attach failed: {endpoint}")

        class FakePlaywright:
            chromium = FakeChromium()

            def stop(self):
                return None

        fake_sync_api = types.ModuleType("playwright.sync_api")
        fake_sync_api.sync_playwright = lambda: types.SimpleNamespace(start=lambda: FakePlaywright())
        fake_playwright = types.ModuleType("playwright")
        fake_playwright.sync_api = fake_sync_api

        driver = CDPDriver(
            _config(connect_timeout=1),
            logging.getLogger("test_cdp_driver"),
        )

        with mock.patch.dict(sys.modules, {"playwright": fake_playwright, "playwright.sync_api": fake_sync_api}):
            with self.assertRaisesRegex(CDPConnectionError, "after 1s"):
                driver.connect_playwright()

        self.assertTrue(seen_timeouts)
        self.assertTrue(all(timeout is not None for timeout in seen_timeouts))
        self.assertLessEqual(max(timeout for timeout in seen_timeouts if timeout is not None), 1000)

    def test_websocket_fallback_is_not_treated_as_page_automation_success(self) -> None:
        driver = CDPDriver(
            _config(fallback_driver="websocket"),
            logging.getLogger("test_cdp_driver"),
        )

        with mock.patch.object(driver, "connect_playwright", side_effect=CDPConnectionError("boom")):
            with mock.patch.object(driver, "connect_websocket") as connect_websocket:
                with self.assertRaisesRegex(CDPConnectionError, "raw WebSocket fallback is disabled"):
                    driver.connect()

        connect_websocket.assert_not_called()

    def test_default_config_disables_raw_websocket_fallback(self) -> None:
        self.assertEqual(DEFAULT_CONFIG["cdp"]["fallback_driver"], "")


if __name__ == "__main__":
    unittest.main()
