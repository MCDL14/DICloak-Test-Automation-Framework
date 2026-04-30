from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


class UIAutomationError(RuntimeError):
    pass


class UIDriver:
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        try:
            import uiautomation as auto
        except ImportError as exc:
            raise UIAutomationError("uiautomation is not installed") from exc
        self.auto = auto

    def find_main_window(self, timeout: int = 10):
        process_name = self.config["app"].get("process_name", "")
        window = self.auto.WindowControl(searchDepth=1, RegexName=".*")
        if window.Exists(maxSearchSeconds=timeout):
            self.logger.info("Main window found for APP process hint: %s", process_name)
            return window
        raise UIAutomationError("APP main window was not found")

    def find_control(self, parent, control_type: str, name: str | None = None, timeout: int = 10):
        kwargs = {}
        if name:
            kwargs["Name"] = name
        factory = getattr(parent, f"{control_type}Control", None) or getattr(self.auto, f"{control_type}Control", None)
        if factory is None:
            raise UIAutomationError(f"unsupported control type: {control_type}")
        control = factory(**kwargs)
        if control.Exists(maxSearchSeconds=timeout):
            return control
        raise UIAutomationError(f"control not found: type={control_type}, name={name}")

    def click_button(self, parent, name: str, timeout: int = 10) -> None:
        button = self.find_control(parent, "Button", name, timeout)
        button.Click()

    def input_text(self, parent, name: str, text: str, timeout: int = 10) -> None:
        edit = self.find_control(parent, "Edit", name, timeout)
        edit.SetValue(text)

    def select_file_in_dialog(self, file_path: str | Path, timeout: int = 10) -> None:
        dialog = self.auto.WindowControl(searchDepth=1, ClassName="#32770")
        if not dialog.Exists(maxSearchSeconds=timeout):
            raise UIAutomationError("Windows file picker dialog was not found")
        edit = dialog.EditControl()
        if not edit.Exists(maxSearchSeconds=timeout):
            raise UIAutomationError("file path input was not found in file picker")
        edit.SetValue(str(file_path))
        open_button = dialog.ButtonControl(Name="打开")
        if not open_button.Exists(maxSearchSeconds=timeout):
            open_button = dialog.ButtonControl(Name="Open")
        if not open_button.Exists(maxSearchSeconds=timeout):
            raise UIAutomationError("open button was not found in file picker")
        open_button.Click()

    def confirm_or_close_popup(self, timeout: int = 5) -> bool:
        popup = self.auto.WindowControl(searchDepth=1, RegexName=".*")
        if not popup.Exists(maxSearchSeconds=timeout):
            return False
        for name in ("确定", "OK", "关闭", "Close"):
            button = popup.ButtonControl(Name=name)
            if button.Exists(maxSearchSeconds=1):
                button.Click()
                return True
        return False

    def desktop_screenshot(self, path: str | Path) -> None:
        self.auto.GetRootControl().CaptureToImage(str(path))
