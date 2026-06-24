from __future__ import annotations

import copy
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.cdp_driver import CDPDriver
from core.config import DEFAULT_CONFIG
from core.result import AutomationTestResult
from core.screenshot import _safe_filename, _screenshot_dir, capture_failure_screenshot


class _FakeCDP:
    def __init__(self, *, healthy: bool = True, fail: bool = False) -> None:
        self.healthy = healthy
        self.fail = fail
        self.paths: list[str] = []

    def health_check(self) -> bool:
        return self.healthy

    def screenshot(self, path: str) -> None:
        self.paths.append(path)
        if self.fail:
            raise RuntimeError("cdp screenshot failed")
        Path(path).write_bytes(b"fake screenshot")


class _FakePage:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def screenshot(self, **kwargs) -> None:  # noqa: ANN003
        self.calls.append(kwargs)


class ScreenshotTests(unittest.TestCase):
    def test_capture_failure_screenshot_prefers_cdp(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            config = {"_project_root": raw_dir, "run": {"screenshot_on_failure": True}}
            cdp = _FakeCDP()

            path = capture_failure_screenshot(
                config=config,
                test_id="tests.p0.example.TestCase.test_one",
                cdp=cdp,
                logger=logging.getLogger("test_screenshot"),
            )

            self.assertTrue(path)
            self.assertEqual(cdp.paths, [path])
            self.assertTrue(Path(path).is_file())
            self.assertEqual(Path(path).parent, Path(raw_dir) / "screenshots")

    def test_capture_failure_screenshot_skips_unhealthy_cdp_and_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            fallback_path = Path(raw_dir) / "fallback.png"
            config = {"_project_root": raw_dir, "run": {"screenshot_on_failure": True}}
            cdp = _FakeCDP(healthy=False)

            with mock.patch("core.screenshot._capture_with_mss", return_value=str(fallback_path)) as capture_mss:
                path = capture_failure_screenshot(
                    config=config,
                    test_id="tests.p0.example.TestCase.test_one",
                    cdp=cdp,
                    logger=logging.getLogger("test_screenshot"),
                )

            self.assertEqual(path, str(fallback_path))
            self.assertEqual(cdp.paths, [])
            capture_mss.assert_called_once()

    def test_windows_uses_uiautomation_after_mss_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            fallback_path = Path(raw_dir) / "ui.png"
            config = {"_project_root": raw_dir, "run": {"screenshot_on_failure": True}}

            with mock.patch("core.screenshot._capture_with_mss", return_value=""):
                with mock.patch("core.screenshot.platform.system", return_value="Windows"):
                    with mock.patch(
                        "core.screenshot._capture_with_uiautomation",
                        return_value=str(fallback_path),
                    ) as capture_ui:
                        path = capture_failure_screenshot(
                            config=config,
                            test_id="tests.p0.example.TestCase.test_one",
                            logger=logging.getLogger("test_screenshot"),
                        )

            self.assertEqual(path, str(fallback_path))
            capture_ui.assert_called_once()

    def test_non_windows_does_not_use_uiautomation_after_mss_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            config = {"_project_root": raw_dir, "run": {"screenshot_on_failure": True}}

            with mock.patch("core.screenshot._capture_with_mss", return_value=""):
                with mock.patch("core.screenshot.platform.system", return_value="Linux"):
                    with mock.patch("core.screenshot._capture_with_uiautomation") as capture_ui:
                        path = capture_failure_screenshot(
                            config=config,
                            test_id="tests.p0.example.TestCase.test_one",
                            logger=logging.getLogger("test_screenshot"),
                        )

            self.assertEqual(path, "")
            capture_ui.assert_not_called()

    def test_result_respects_screenshot_on_failure_disabled(self) -> None:
        result = AutomationTestResult(stream=None, descriptions=True, verbosity=1)

        class SampleCase(unittest.TestCase):
            config = {"run": {"screenshot_on_failure": False}}

            def runTest(self) -> None:
                pass

        with mock.patch("core.result.capture_failure_screenshot") as capture:
            path = result._capture_screenshot(SampleCase())

        self.assertEqual(path, "")
        capture.assert_not_called()

    def test_screenshot_dir_uses_project_root_for_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            path = _screenshot_dir(
                {
                    "_project_root": raw_dir,
                    "screenshots_dir": "custom_screenshots",
                }
            )

        self.assertEqual(path, Path(raw_dir) / "custom_screenshots")

    def test_safe_filename_removes_unsafe_characters(self) -> None:
        safe = _safe_filename("tests.p0.成员/TestCase:test one_failure.png")

        self.assertNotIn("/", safe)
        self.assertNotIn(":", safe)
        self.assertTrue(safe.endswith("_failure.png"))

    def test_cdp_driver_screenshot_uses_explicit_timeout(self) -> None:
        config = copy.deepcopy(DEFAULT_CONFIG)
        config["timeouts"]["screenshot_seconds"] = 7
        driver = CDPDriver(config, logging.getLogger("test_screenshot"))
        fake_page = _FakePage()
        driver.page = fake_page

        driver.screenshot("target.png")

        self.assertEqual(
            fake_page.calls,
            [{"path": "target.png", "full_page": True, "timeout": 7000}],
        )


if __name__ == "__main__":
    unittest.main()
