from __future__ import annotations

from typing import Any

from core.platform.capabilities import current_capabilities


class UnsupportedPlatformError(RuntimeError):
    pass


def system_proxy_supported() -> bool:
    return current_capabilities().system_proxy


def unsupported_system_proxy_message() -> str:
    platform_name = current_capabilities().name
    return f"system proxy is not supported on platform: {platform_name}"


def proxy_server_from_config(config: dict[str, Any]) -> str:
    proxy_config = config.get("system_proxy") or config.get("windows_system_proxy", {})
    host = str(proxy_config.get("host") or "127.0.0.1").strip()
    port = str(proxy_config.get("port") or "7897").strip()
    if not host:
        raise ValueError("system proxy host is empty")
    if not port:
        raise ValueError("system proxy port is empty")
    return f"{host}:{port}"


def read_system_proxy_settings() -> dict[str, tuple[bool, Any, int | None]]:
    if not system_proxy_supported():
        raise UnsupportedPlatformError(unsupported_system_proxy_message())
    from core.windows_proxy import read_windows_system_proxy_settings

    return read_windows_system_proxy_settings()


def enable_system_proxy(proxy_server: str) -> dict[str, tuple[bool, Any, int | None]]:
    if not system_proxy_supported():
        raise UnsupportedPlatformError(unsupported_system_proxy_message())
    from core.windows_proxy import enable_windows_system_proxy

    return enable_windows_system_proxy(proxy_server)


def disable_system_proxy() -> None:
    if not system_proxy_supported():
        raise UnsupportedPlatformError(unsupported_system_proxy_message())
    from core.windows_proxy import disable_windows_system_proxy

    disable_windows_system_proxy()


def restore_system_proxy_settings(settings: dict[str, tuple[bool, Any, int | None]]) -> None:
    if not system_proxy_supported():
        raise UnsupportedPlatformError(unsupported_system_proxy_message())
    from core.windows_proxy import restore_windows_system_proxy_settings

    restore_windows_system_proxy_settings(settings)
