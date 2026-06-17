from __future__ import annotations

import platform


WINDOWS = "windows"
MACOS = "macos"
LINUX = "linux"


def current_platform() -> str:
    system = platform.system().lower()
    if system == "windows":
        return WINDOWS
    if system == "darwin":
        return MACOS
    if system == "linux":
        return LINUX
    return system or "unknown"


def is_windows() -> bool:
    return current_platform() == WINDOWS


def is_macos() -> bool:
    return current_platform() == MACOS


def is_linux() -> bool:
    return current_platform() == LINUX
