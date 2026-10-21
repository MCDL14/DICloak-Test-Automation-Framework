from __future__ import annotations

import glob
import logging
import os
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from core.app_config import ResolvedAppConfig, resolve_app_config
from core.app_cdp_auth import (
    AppCdpAuthError,
    auth_enabled,
    generate_app_cdp_token,
    normalized_app_startup_args,
    redact_app_startup_args,
    validate_app_cdp_token,
)
from core.platform.detect import is_linux, is_windows
from core.process import is_process_running

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is declared in requirements.
    psutil = None


class AppStartupError(RuntimeError):
    pass


class AppManager:
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.process: subprocess.Popen | None = None

    @property
    def process_name(self) -> str:
        return resolve_app_config(self.config).process_name

    def is_running(self, process_name: str | None = None) -> bool:
        target = process_name or self.process_name
        return is_process_running(target)

    def close_existing_if_needed(self, *, force: bool = False) -> None:
        if not force and not self.config["app"].get("close_existing_before_start", True):
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
        app_config, command = self._prepare_launch()
        self._start_prepared(app_config.work_dir, command)

    def _prepare_launch(self) -> tuple[ResolvedAppConfig, list[str]]:
        app_config = resolve_app_config(self.config)
        exe_path = app_config.exe_path
        work_dir = app_config.work_dir

        if not exe_path.is_file():
            raise AppStartupError(f"APP exe does not exist: {exe_path}")
        if not work_dir.is_dir():
            raise AppStartupError(f"APP work_dir does not exist: {work_dir}")

        try:
            startup_args = normalized_app_startup_args(self.config, app_config.startup_args)
            if auth_enabled(self.config):
                token = generate_app_cdp_token(self.config)
                startup_args.append(f"--dicloak-debug-token={token}")
        except AppCdpAuthError as exc:
            raise AppStartupError(str(exc)) from None
        return app_config, [str(exe_path), *startup_args]

    def _start_prepared(self, work_dir: Path, command: list[str], *, detach_stdio: bool = False) -> None:
        try:
            if auth_enabled(self.config):
                token = next((arg.split("=", 1)[1] for arg in command if arg.startswith("--dicloak-debug-token=")), "")
                validate_app_cdp_token(self.config, token)
        except AppCdpAuthError as exc:
            raise AppStartupError(str(exc)) from None
        self.logger.info("Starting APP: %s", " ".join(redact_app_startup_args(command)))
        popen_kwargs: dict[str, Any] = {"cwd": str(work_dir), "env": self._launch_environment()}
        if detach_stdio:
            # Attach fallback keeps the APP after the CLI exits. Do not let it
            # keep the UI's CLI output pipe open, otherwise progress never ends.
            popen_kwargs.update(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if is_windows():
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
        try:
            self.process = subprocess.Popen(command, **popen_kwargs)
        except (OSError, subprocess.SubprocessError):
            # Some launch errors include the complete command in their message.
            raise AppStartupError("APP 启动失败，请检查可执行文件、权限与工作目录；启动凭证已隐藏") from None

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

    def launch_fresh(self, *, force_close_existing: bool = False) -> bool:
        # Signing/validation must succeed before touching an existing user APP.
        app_config, command = self._prepare_launch()
        if force_close_existing:
            self.close_existing_if_needed(force=True)
            self._start_prepared(app_config.work_dir, command, detach_stdio=True)
        else:
            self.close_existing_if_needed()
            self._start_prepared(app_config.work_dir, command)
        return self.wait_until_running()

    def close(self) -> None:
        if not self.is_running():
            return
        if not is_windows():
            self._close_with_psutil()
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

    def _close_with_psutil(self) -> None:
        if psutil is None:
            self.logger.warning("Unable to close APP process on this platform because psutil is unavailable")
            return

        matched_processes = []
        target_name = self.process_name.lower()
        for process in psutil.process_iter(["pid", "name"]):
            try:
                process_name = str(process.info.get("name") or process.name()).lower()
            except (psutil.Error, OSError):
                continue
            if process_name == target_name:
                matched_processes.append(process)

        for process in matched_processes:
            try:
                children = _existing_children(process)
                for child in children:
                    with suppress(psutil.NoSuchProcess):
                        child.terminate()
                with suppress(psutil.NoSuchProcess):
                    process.terminate()
                _gone, alive = psutil.wait_procs([*children, process], timeout=10)
                for alive_process in alive:
                    with suppress(psutil.NoSuchProcess):
                        alive_process.kill()
                psutil.wait_procs(alive, timeout=5)
            except psutil.NoSuchProcess:
                continue
            except (psutil.Error, OSError) as exc:
                self.logger.warning("Unable to close APP process %s: %s", process.pid, exc)

    def _launch_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        if is_linux():
            _fill_linux_desktop_environment(env)
        return env


def _fill_linux_desktop_environment(env: dict[str, str]) -> None:
    uid = os.getuid()
    runtime_dir = env.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    if os.path.isdir(runtime_dir):
        env.setdefault("XDG_RUNTIME_DIR", runtime_dir)

    bus_path = os.path.join(runtime_dir, "bus")
    if os.path.exists(bus_path):
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={bus_path}")

    wayland_socket = os.path.join(runtime_dir, "wayland-0")
    if os.path.exists(wayland_socket):
        env.setdefault("WAYLAND_DISPLAY", "wayland-0")

    if not env.get("DISPLAY"):
        for candidate in ("/tmp/.X11-unix/X0", "/tmp/.X11-unix/X1"):
            if os.path.exists(candidate):
                env["DISPLAY"] = f":{candidate.rsplit('X', 1)[-1]}"
                break

    if not env.get("XAUTHORITY"):
        auth_files = sorted(glob.glob(os.path.join(runtime_dir, ".mutter-Xwaylandauth.*")))
        if auth_files:
            env["XAUTHORITY"] = auth_files[0]


def _existing_children(process) -> list:
    try:
        return process.children(recursive=True)
    except psutil.NoSuchProcess:
        return []
