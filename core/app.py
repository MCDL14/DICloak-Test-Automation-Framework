from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from core.process import is_process_running


class AppStartupError(RuntimeError):
    pass


class AppManager:
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.process: subprocess.Popen | None = None

    @property
    def process_name(self) -> str:
        return str(self.config["app"].get("process_name", "Dicloak.exe"))

    def is_running(self, process_name: str | None = None) -> bool:
        target = process_name or self.process_name
        return is_process_running(target)

    def close_existing_if_needed(self) -> None:
        if not self.config["app"].get("close_existing_before_start", True):
            return
        if not self.is_running():
            return
        self.logger.info("Existing APP process found, force killing it before startup: %s", self.process_name)
        self.close()
        timeout = int(self.config["app"].get("shutdown_timeout", 20))
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.is_running():
                return
            time.sleep(1)
        raise AppStartupError(f"existing APP process did not close within {timeout}s")

    def start(self) -> None:
        app = self.config["app"]
        exe_path = Path(app.get("exe_path", ""))
        work_dir = Path(app.get("work_dir", "")) if app.get("work_dir") else exe_path.parent
        startup_args = [str(arg) for arg in app.get("startup_args", [])]

        if not exe_path.is_file():
            raise AppStartupError(f"APP exe does not exist: {exe_path}")
        if not work_dir.is_dir():
            raise AppStartupError(f"APP work_dir does not exist: {work_dir}")

        command = [str(exe_path), *startup_args]
        self.logger.info("Starting APP: %s", " ".join(command))
        self.process = subprocess.Popen(command, cwd=str(work_dir))

    def wait_until_running(self) -> bool:
        timeout = int(self.config["app"].get("process_check_timeout", 30))
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_running():
                self.logger.info("APP process detected: %s", self.process_name)
                return True
            time.sleep(1)
        self.logger.error("APP process was not detected within %ss: %s", timeout, self.process_name)
        return False

    def launch_fresh(self) -> bool:
        self.close_existing_if_needed()
        self.start()
        return self.wait_until_running()

    def close(self) -> None:
        if not self.is_running():
            return
        try:
            completed = subprocess.run(
                ["taskkill", "/F", "/T", "/IM", self.process_name],
                capture_output=True,
                text=True,
                encoding="mbcs",
                errors="ignore",
                timeout=15,
                check=False,
            )
            if completed.returncode != 0:
                message = (completed.stderr or completed.stdout or "").strip()
                self.logger.warning("Force kill APP process failed: %s", message)
        except (OSError, subprocess.SubprocessError) as exc:
            self.logger.warning("Unable to close APP process normally: %s", exc)
