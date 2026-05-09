from __future__ import annotations

import logging
import unittest
from typing import Any

from core.case_module import get_test_case_module
from pages.app_page import AppPage
from pages.environment_page import EnvironmentPage


class TestRecoveryManager:
    """Central recovery hook used by the unittest result layer.

    Recovery has three scopes:
    - global APP recovery closes blocking overlays and waits for an operable shell;
    - module recovery enters the module home page and clears module-owned state;
    - case cleanup stays in the test case because only the case knows its data.
    """

    def recover_before_test(self, test: unittest.TestCase) -> None:
        self._recover(test, stage="before")

    def recover_after_test(self, test: unittest.TestCase) -> None:
        self._recover(test, stage="after")

    def _recover(self, test: unittest.TestCase, stage: str) -> None:
        config = getattr(test, "config", None) or getattr(test.__class__, "config", None)
        cdp = getattr(test, "cdp", None) or getattr(test.__class__, "cdp", None)
        logger = self._logger(test)
        if not isinstance(config, dict) or cdp is None:
            return
        if not self._recovery_enabled(config):
            return
        if not self._cdp_healthy(cdp):
            logger.warning("Skip %s-test recovery because CDP is not healthy: %s", stage, test.id())
            return

        try:
            AppPage(cdp_driver=cdp, config=config).recover_to_stable_state()
            self._recover_module_home(test, cdp, config)
        except Exception as exc:
            logger.warning("%s-test recovery failed for %s: %s", stage.capitalize(), test.id(), exc)

    def _recover_module_home(self, test: unittest.TestCase, cdp: Any, config: dict[str, Any]) -> None:
        module_name = get_test_case_module(test)
        if module_name == "环境管理":
            EnvironmentPage(cdp_driver=cdp, config=config).recover_to_module_home()

    def _recovery_enabled(self, config: dict[str, Any]) -> bool:
        return bool(config.get("run", {}).get("recovery_enabled", True))

    def _cdp_healthy(self, cdp: Any) -> bool:
        try:
            health_check = getattr(cdp, "health_check", None)
            return bool(health_check()) if callable(health_check) else bool(getattr(cdp, "page", None))
        except Exception:
            return False

    def _logger(self, test: unittest.TestCase) -> logging.Logger:
        logger = getattr(test, "logger", None) or getattr(test.__class__, "logger", None)
        if isinstance(logger, logging.Logger):
            return logger
        return logging.getLogger(__name__)
