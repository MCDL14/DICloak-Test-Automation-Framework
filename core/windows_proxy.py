from __future__ import annotations

import ctypes
from typing import Any


def proxy_server_from_config(config: dict[str, Any]) -> str:
    proxy_config = config.get("windows_system_proxy", {})
    host = str(proxy_config.get("host") or "127.0.0.1").strip()
    port = str(proxy_config.get("port") or "7897").strip()
    if not host:
        raise ValueError("windows_system_proxy.host is empty")
    if not port:
        raise ValueError("windows_system_proxy.port is empty")
    return f"{host}:{port}"


def enable_windows_system_proxy(proxy_server: str) -> dict[str, tuple[bool, Any, int | None]]:
    clean_proxy_server = str(proxy_server).strip()
    if not clean_proxy_server:
        raise ValueError("windows system proxy server is empty")
    snapshot = read_windows_system_proxy_settings()
    set_windows_system_proxy_value("ProxyEnable", 1)
    set_windows_system_proxy_value("ProxyServer", clean_proxy_server)
    notify_windows_system_proxy_changed()
    return snapshot


def disable_windows_system_proxy() -> None:
    set_windows_system_proxy_value("ProxyEnable", 0)
    notify_windows_system_proxy_changed()


def read_windows_system_proxy_settings() -> dict[str, tuple[bool, Any, int | None]]:
    import winreg

    names = ("ProxyEnable", "ProxyServer", "ProxyOverride")
    path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    snapshot: dict[str, tuple[bool, Any, int | None]] = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as key:
        for name in names:
            try:
                value, value_type = winreg.QueryValueEx(key, name)
                snapshot[name] = (True, value, value_type)
            except FileNotFoundError:
                snapshot[name] = (False, None, None)
    return snapshot


def set_windows_system_proxy_value(name: str, value: Any) -> None:
    import winreg

    path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    value_type = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, value_type, value)


def notify_windows_system_proxy_changed() -> None:
    internet_option_settings_changed = 39
    internet_option_refresh = 37
    ctypes.windll.Wininet.InternetSetOptionW(0, internet_option_settings_changed, None, 0)
    ctypes.windll.Wininet.InternetSetOptionW(0, internet_option_refresh, None, 0)
