from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class LocatorError(RuntimeError):
    pass


class BasePage:
    locator_file: str = ""

    def __init__(self, cdp_driver, ui_driver=None, config: dict[str, Any] | None = None):
        self.cdp = cdp_driver
        self.ui = ui_driver
        self.config = config or {}
        self.locators = self._load_locators()

    def locator(self, name: str) -> str:
        value = self.locators.get(name)
        if not value:
            raise LocatorError(f"locator is not defined: {name}")
        if isinstance(value, dict):
            selector = value.get("selector")
            if not selector:
                raise LocatorError(f"locator selector is not defined: {name}")
            return str(selector)
        return str(value)

    def click(self, name: str) -> None:
        self.cdp.click(self.locator(name))

    def fill(self, name: str, value: str) -> None:
        self.cdp.fill(self.locator(name), value)

    def text(self, name: str) -> str:
        return self.cdp.text(self.locator(name))

    def wait_visible(self, name: str) -> None:
        self.cdp.wait_for_selector(self.locator(name))

    def _load_locators(self) -> dict[str, Any]:
        if not self.locator_file:
            return {}
        path = Path("locators") / self.locator_file
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as file_obj:
            return yaml.safe_load(file_obj) or {}
