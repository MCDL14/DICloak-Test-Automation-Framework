from __future__ import annotations

import re

from core.process import process_command_lines
from pages.base_page import BasePage


class KernelPage(BasePage):
    locator_file = "kernel_locators.yaml"

    def open_kernel_manager(self) -> None:
        self.click("kernel_menu")
        self.wait_visible("kernel_table")

    def read_kernel_table(self) -> str:
        return self.text("kernel_table")

    def delete_kernel(self, version: str) -> None:
        self.fill("kernel_search_input", version)
        self.click("delete_kernel_button")
        self.click("confirm_button")

    def download_kernel(self, version: str) -> None:
        self.fill("kernel_search_input", version)
        self.click("download_kernel_button")

    def read_environment_kernel_version(self) -> str:
        return self.text("environment_kernel_version")

    def read_kernel_version_from_process(self, process_name: str = "GinsBrowser.exe") -> str:
        command_lines = process_command_lines(process_name)
        for command_line in command_lines:
            version = self._extract_kernel_version(command_line)
            if version:
                return version
        raise RuntimeError(f"kernel version was not found from process command line: {process_name}")

    def _extract_kernel_version(self, text: str) -> str:
        patterns = [
            r"browsers[\\/]+([0-9]+(?:\\.[0-9]+)+)",
            r"GinsBrowser[\\/]+([0-9]+(?:\\.[0-9]+)+)",
            r"([0-9]{3}(?:\\.[0-9]+)+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return ""
