from __future__ import annotations

import logging
import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_SCREENSHOT_DIR = "screenshots"
SCREENSHOT_TIME_FORMAT = "%Y%m%d_%H%M%S"
WINDOWS_PLATFORM = "windows"


def capture_failure_screenshot(
    config: dict[str, Any] | None,
    test_id: str,
    cdp=None,
    ui=None,
    logger: logging.Logger | None = None,
) -> str:
    """Capture failure evidence and return the saved screenshot path.

    Strategy:
    1. Prefer the APP page through CDP/Playwright.
    2. Fallback to a desktop screenshot through mss.
    3. On Windows, fallback to the existing UIAutomation screenshot.
    """
    config = config or {}
    logger = logger or logging.getLogger("dicloak_automation")
    try:
        screenshot_dir = _screenshot_dir(config)
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        target = screenshot_dir / _safe_filename(
            f"{datetime.now():{SCREENSHOT_TIME_FORMAT}}_{test_id}_failure.png"
        )
    except Exception as exc:
        logger.warning("Failure screenshot path preparation failed: %s", exc)
        return ""

    cdp_path = _capture_with_cdp(target, cdp, logger)
    if cdp_path:
        return cdp_path

    mss_path = _capture_with_mss(target, logger)
    if mss_path:
        return mss_path

    if platform.system().lower() == WINDOWS_PLATFORM:
        ui_path = _capture_with_uiautomation(target, ui, config, logger)
        if ui_path:
            return ui_path

    logger.warning("Failure screenshot was not captured: test_id=%s", test_id)
    return ""


def _screenshot_dir(config: dict[str, Any]) -> Path:
    project_root = Path(str(config.get("_project_root") or Path.cwd()))
    configured_dir = str(config.get("screenshots_dir", "") or "").strip()
    if configured_dir:
        path = Path(configured_dir).expanduser()
        return path if path.is_absolute() else project_root / path
    return project_root / DEFAULT_SCREENSHOT_DIR


def _capture_with_cdp(target: Path, cdp, logger: logging.Logger) -> str:
    if cdp is None:
        return ""
    try:
        if hasattr(cdp, "health_check") and not cdp.health_check():
            logger.debug("Skipping CDP screenshot because CDP health check failed")
            return ""
        cdp.screenshot(str(target))
        logger.info("Failure screenshot captured through CDP: %s", target)
        return str(target)
    except Exception as exc:
        logger.warning("CDP screenshot failed, falling back to desktop screenshot: %s", exc)
        return ""


def _capture_with_mss(target: Path, logger: logging.Logger) -> str:
    try:
        import mss
        import mss.tools
    except ImportError as exc:
        logger.warning("mss is not installed; desktop screenshot fallback is unavailable: %s", exc)
        return ""

    try:
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            image = sct.grab(monitor)
            mss.tools.to_png(image.rgb, image.size, output=str(target))
        logger.info("Failure screenshot captured through mss: %s", target)
        return str(target)
    except Exception as exc:
        logger.warning("mss desktop screenshot failed: %s", exc)
        return ""


def _capture_with_uiautomation(
    target: Path,
    ui,
    config: dict[str, Any],
    logger: logging.Logger,
) -> str:
    try:
        ui_driver = ui
        if ui_driver is None:
            from core.ui_driver import UIDriver

            ui_driver = UIDriver(config, logger)
        ui_driver.desktop_screenshot(target)
        logger.info("Failure screenshot captured through UIAutomation: %s", target)
        return str(target)
    except Exception as exc:
        logger.warning("UIAutomation desktop screenshot failed: %s", exc)
        return ""


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._")
    return safe or "failure.png"
