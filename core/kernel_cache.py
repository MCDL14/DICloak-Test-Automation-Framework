from __future__ import annotations

import re
import time
from pathlib import Path


def kernel_version_dirs(browsers_dir: Path, major_prefix: str) -> list[Path]:
    if not browsers_dir.exists():
        return []
    pattern = re.compile(rf"^{re.escape(str(major_prefix))}\.\d+(?:\.\d+)+$")
    return sorted(
        item for item in browsers_dir.iterdir()
        if item.is_dir() and pattern.match(item.name)
    )


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
) -> Path:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for version_dir in reversed(kernel_version_dirs(browsers_dir, major_prefix)):
            if any(item.name.lower() == executable_name.lower() for item in version_dir.rglob(executable_name)):
                return version_dir
        time.sleep(1)
    raise TimeoutError(
        f"kernel executable was not found: {browsers_dir}\\{major_prefix}.x.xx\\**\\{executable_name}"
    )
