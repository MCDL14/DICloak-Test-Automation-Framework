from __future__ import annotations

import re
import time
from pathlib import Path


def kernel_version_cache_entries(browsers_dir: Path, major_prefix: str) -> list[Path]:
    """列出目标内核的全部缓存条目，删除校验也需识别同名文件和失效链接。"""
    pattern = re.compile(rf"^{re.escape(str(major_prefix))}\.\d+(?:\.\d+)+$")
    try:
        return sorted(item for item in browsers_dir.iterdir() if pattern.fullmatch(item.name))
    except FileNotFoundError:
        return []


def kernel_version_dirs(browsers_dir: Path, major_prefix: str) -> list[Path]:
    return [item for item in kernel_version_cache_entries(browsers_dir, major_prefix) if item.is_dir()]


def _has_kernel_version_dirs(browsers_dir: Path) -> bool:
    if not browsers_dir.exists():
        return False
    pattern = re.compile(r"^\d+\.\d+(?:\.\d+)+$")
    return any(item.is_dir() and pattern.match(item.name) for item in browsers_dir.iterdir())


def kernel_browsers_dir_candidates(cache_dir: Path, subdir_name: str = "browsers") -> list[Path]:
    direct_dir = cache_dir / subdir_name
    macos_user_data_dir = cache_dir.parent / "DICloak" / subdir_name
    return list(dict.fromkeys([direct_dir, macos_user_data_dir]))


def resolve_kernel_browsers_dir(
    cache_dir: Path, subdir_name: str = "browsers", *, version: str | None = None
) -> Path:
    candidates = kernel_browsers_dir_candidates(cache_dir, subdir_name)
    if version is not None:
        for candidate in candidates:
            if (candidate / version).is_dir():
                return candidate
    for candidate in candidates:
        if _has_kernel_version_dirs(candidate):
            return candidate
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def wait_for_kernel_version_dir(
    browsers_dir: Path,
    major_prefix: str,
    timeout_seconds: int = 300,
) -> Path:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        version_dirs = kernel_version_dirs(browsers_dir, major_prefix)
        if version_dirs:
            return version_dirs[-1]
        time.sleep(1)
    raise TimeoutError(f"kernel cache dir was not found: {browsers_dir}\\{major_prefix}.x.xx")


def wait_for_kernel_executable_dir(
    browsers_dir: Path,
    major_prefix: str,
    executable_name: str = "GinsBrowser.exe",
    timeout_seconds: int = 300,
    *,
    version: str | None = None,
) -> Path:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for version_dir in reversed(kernel_version_dirs(browsers_dir, major_prefix)):
            if version is not None and version_dir.name != version:
                continue
            if any(item.name.lower() == executable_name.lower() for item in version_dir.rglob(executable_name)):
                return version_dir
        time.sleep(1)
    raise TimeoutError(
        f"kernel executable was not found: {browsers_dir}\\{version or f'{major_prefix}.x.xx'}\\**\\{executable_name}"
    )
