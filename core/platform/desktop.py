from __future__ import annotations

from core.platform.capabilities import current_capabilities


def desktop_file_dialog_supported() -> bool:
    return current_capabilities().desktop_file_dialog


def unsupported_desktop_file_dialog_message() -> str:
    platform_name = current_capabilities().name
    return f"desktop file dialog automation is not supported on platform: {platform_name}"
