from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.platform import current_platform
from core.platform.detect import LINUX, MACOS, WINDOWS


@dataclass(frozen=True)
class ResolvedAppConfig:
    platform_name: str
    exe_path: Path
    work_dir: Path
    process_name: str
    browser_process_name: str
    startup_args: list[str]


def resolve_app_config(config: dict[str, Any], platform_name: str | None = None) -> ResolvedAppConfig:
    platform_key = platform_name or current_platform()
    app = config.get("app", {})
    platform_app = _platform_app_config(config, platform_key)

    platform_exe_path = _configured_path(platform_app, "executable_path", "exe_path")
    app_exe_path = _configured_path(app, "executable_path", "exe_path")
    exe_path = platform_exe_path or app_exe_path or Path("")

    platform_work_dir = _configured_path(platform_app, "work_dir")
    app_work_dir = _configured_path(app, "work_dir")
    if platform_work_dir is not None:
        work_dir = platform_work_dir
    elif platform_exe_path is not None:
        work_dir = platform_exe_path.parent
    elif app_work_dir is not None:
        work_dir = app_work_dir
    elif app_exe_path is not None:
        work_dir = app_exe_path.parent
    else:
        work_dir = Path("")

    return ResolvedAppConfig(
        platform_name=platform_key,
        exe_path=exe_path,
        work_dir=work_dir,
        process_name=str(platform_app.get("process_name", app.get("process_name", _default_process_name(platform_key)))),
        browser_process_name=str(
            platform_app.get("browser_process_name", app.get("browser_process_name", _default_browser_process_name(platform_key)))
        ),
        startup_args=[str(arg) for arg in platform_app.get("startup_args", app.get("startup_args", []))],
    )


def _platform_app_config(config: dict[str, Any], platform_name: str) -> dict[str, Any]:
    platforms = config.get("platforms", {})
    if not isinstance(platforms, dict):
        return {}
    platform_config = platforms.get(platform_name, {})
    if not isinstance(platform_config, dict):
        return {}
    app_config = platform_config.get("app", platform_config)
    return app_config if isinstance(app_config, dict) else {}


def _configured_path(source: dict[str, Any], *keys: str) -> Path | None:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return Path(str(value)).expanduser()
    return None


def _default_process_name(platform_name: str) -> str:
    if platform_name == MACOS:
        return "DICloak"
    if platform_name == LINUX:
        return "dicloak"
    if platform_name == WINDOWS:
        return "DICloak.exe"
    return "DICloak.exe"


def _default_browser_process_name(platform_name: str) -> str:
    if platform_name == MACOS:
        return "GinsBrowser"
    if platform_name == LINUX:
        return "ginsbrowser"
    if platform_name == WINDOWS:
        return "GinsBrowser.exe"
    return "GinsBrowser.exe"
