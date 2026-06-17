from __future__ import annotations

from dataclasses import dataclass

from core.platform.detect import LINUX, MACOS, WINDOWS, current_platform


@dataclass(frozen=True)
class PlatformCapabilities:
    name: str
    app_managed_launch: bool
    process_command_line: bool
    process_listening_ports: bool
    desktop_file_dialog: bool
    desktop_screenshot: bool
    system_proxy: bool


def current_capabilities() -> PlatformCapabilities:
    platform_name = current_platform()
    if platform_name == WINDOWS:
        return PlatformCapabilities(
            name=platform_name,
            app_managed_launch=True,
            process_command_line=True,
            process_listening_ports=True,
            desktop_file_dialog=True,
            desktop_screenshot=True,
            system_proxy=True,
        )
    if platform_name == MACOS:
        return PlatformCapabilities(
            name=platform_name,
            app_managed_launch=False,
            process_command_line=True,
            process_listening_ports=True,
            desktop_file_dialog=False,
            desktop_screenshot=True,
            system_proxy=False,
        )
    if platform_name == LINUX:
        return PlatformCapabilities(
            name=platform_name,
            app_managed_launch=True,
            process_command_line=True,
            process_listening_ports=True,
            desktop_file_dialog=False,
            desktop_screenshot=True,
            system_proxy=False,
        )
    return PlatformCapabilities(
        name=platform_name,
        app_managed_launch=False,
        process_command_line=False,
        process_listening_ports=False,
        desktop_file_dialog=False,
        desktop_screenshot=False,
        system_proxy=False,
    )
