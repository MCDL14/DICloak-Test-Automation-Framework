from __future__ import annotations

import glob
import ipaddress
import logging
import os
import shutil
import socket
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


def is_test_app_package(config: dict[str, Any]) -> bool:
    return config.get("_app_package_kind") == "test" or config.get("app", {}).get("isolation") == "executable_path"


def _normalized_executable_path(value: str | Path) -> str:
    if not isinstance(value, (str, Path)):
        raise AppStartupError("无法确认测试 APP 的可执行文件路径，已拒绝操作未知进程")
    path = Path(value).expanduser()
    if not str(value).strip() or not path.is_absolute():
        raise AppStartupError("测试 APP 可执行文件必须配置为明确的绝对路径，不能回退到生产 APP")
    return os.path.normcase(os.path.realpath(str(path)))


def _test_target_path(config: dict[str, Any]) -> str:
    return _normalized_executable_path(resolve_app_config(config).exe_path)


def _process_executable(process: Any) -> str:
    value = (getattr(process, "info", {}) or {}).get("exe") or process.exe()
    return _normalized_executable_path(value)


def _matching_test_processes(config: dict[str, Any]) -> list[Any]:
    if psutil is None:
        raise AppStartupError("测试 APP 隔离需要 psutil；无法确认进程路径，已拒绝按进程名操作")
    target = _test_target_path(config)
    target_name = resolve_app_config(config).process_name.casefold()
    result = []
    try:
        processes = psutil.process_iter(["pid", "name", "exe", "status"])
        for process in processes:
            try:
                info = getattr(process, "info", {}) or {}
                if info.get("status") == psutil.STATUS_ZOMBIE:
                    continue
                if _process_executable(process) == target:
                    result.append(process)
            except psutil.NoSuchProcess:
                continue
            except (psutil.Error, OSError, AppStartupError):
                # Inaccessible unrelated system processes are expected. A same-
                # named APP is ambiguous and must not be treated as our target.
                name = str((getattr(process, "info", {}) or {}).get("name") or "").casefold()
                if name == target_name:
                    raise AppStartupError("无法确认同名 APP 的可执行文件路径，测试包进程操作已拒绝；不会按名称关闭生产 APP") from None
    except AppStartupError:
        raise
    except (psutil.Error, OSError):
        raise AppStartupError("无法枚举测试 APP 的进程路径，已拒绝操作生产或未知进程") from None
    return result


def _connection_listens_on(connection: Any, port: int) -> bool:
    if getattr(connection, "status", "") != "LISTEN":
        return False
    address = getattr(connection, "laddr", None)
    if address is None:
        return False
    address_port = getattr(address, "port", None)
    if address_port is None:
        try:
            address_port = address[1]
        except (IndexError, TypeError):
            return False
    return address_port == port


def _listener_pids(port: int) -> set[int] | None:
    """Find positive listener ownership; never assume an inaccessible port is safe."""
    if psutil is None:
        return None
    try:
        connections = psutil.net_connections(kind="tcp")
        listeners = [item for item in connections if _connection_listens_on(item, port)]
        if listeners:
            if any(not isinstance(item.pid, int) or item.pid <= 0 for item in listeners):
                return None
            return {item.pid for item in listeners}
    except (psutil.Error, OSError):
        pass

    # macOS can forbid the machine-wide table while allowing connections owned
    # by the current SSH / desktop user. Inspect those processes individually.
    pids: set[int] = set()
    try:
        for process in psutil.process_iter(["pid"]):
            try:
                reader = getattr(process, "net_connections", None)
                if not callable(reader):
                    reader = getattr(process, "connections", None)
                if not callable(reader):
                    continue
                if any(_connection_listens_on(item, port) for item in reader(kind="tcp")):
                    pids.add(process.pid)
            except (psutil.Error, OSError):
                continue
    except (psutil.Error, OSError):
        pass
    if pids:
        return pids

    # A bounded read-only fallback for macOS, where lsof is normally available.
    executable = shutil.which("lsof")
    if executable:
        try:
            completed = subprocess.run(
                [executable, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            if completed.returncode == 0:
                for line in completed.stdout.splitlines():
                    if line.startswith("p") and line[1:].isdigit() and int(line[1:]) > 0:
                        pids.add(int(line[1:]))
        except (OSError, subprocess.SubprocessError):
            pass
    return pids or None


def _test_cdp_address(config: dict[str, Any]) -> tuple[str, int]:
    cdp = config.get("cdp", {})
    host = str(cdp.get("host", "127.0.0.1")).strip()
    local = host.rstrip(".").casefold() == "localhost"
    if not local:
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
    port = cdp.get("port", 9223)
    if not local or type(port) is not int or not 1 <= port <= 65535:
        raise AppStartupError("测试 APP 的 CDP 必须使用本机回环地址和有效独立端口，不能连接生产或未知远端地址")
    return host, port


def _test_cdp_port_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def assert_test_app_cdp_target(
    config: dict[str, Any], *, listening: bool | None = None, require_listening: bool = False,
) -> None:
    """Test-package guard. Production retains its existing startup semantics."""
    if not is_test_app_package(config):
        return
    host, port = _test_cdp_address(config)
    target = _test_target_path(config)
    available = _test_cdp_port_listening(host, port) if listening is None else listening
    if not available:
        if require_listening:
            raise AppStartupError("测试 APP 的 CDP 端口未监听，不能复用现有 APP")
        return
    pids = _listener_pids(port)
    if not pids or psutil is None:
        raise AppStartupError("测试 APP 的 CDP 端口已占用，但无法确认监听进程身份；为避免误连生产 APP，已拒绝执行")
    for pid in pids:
        try:
            if _process_executable(psutil.Process(pid)) != target:
                raise AppStartupError("测试 APP 的 CDP 端口由其他程序或生产 APP 占用，已拒绝连接或启动；请关闭冲突程序或修改测试端口")
        except AppStartupError:
            raise
        except (psutil.Error, OSError):
            raise AppStartupError("无法读取测试 CDP 监听进程的可执行路径，已拒绝连接或启动生产或未知 APP") from None


def wait_for_test_app_cdp_target(config: dict[str, Any]) -> None:
    """Before CDP attach, wait for a test listener and positively identify it."""
    if not is_test_app_package(config):
        return
    host, port = _test_cdp_address(config)
    timeout = max(0, int(config.get("cdp", {}).get("connect_timeout", 30)))
    deadline = time.monotonic() + timeout
    while True:
        available = _test_cdp_port_listening(host, port)
        assert_test_app_cdp_target(config, listening=available)
        if available:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AppStartupError("等待测试 APP 的独立 CDP 端口超时，尚未连接任何 APP")
        time.sleep(min(0.2, remaining))


class AppManager:
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.process: subprocess.Popen | None = None

    @property
    def process_name(self) -> str:
        return resolve_app_config(self.config).process_name

    def is_running(self, process_name: str | None = None) -> bool:
        if is_test_app_package(self.config):
            return bool(_matching_test_processes(self.config))
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
        assert_test_app_cdp_target(self.config)

        try:
            enabled = auth_enabled(self.config)
            if is_test_app_package(self.config) and not enabled:
                raise AppCdpAuthError("测试 APP 包托管启动必须开启 CDP 凭证签发配置，不能沿用未鉴权的生产启动参数")
            startup_args = normalized_app_startup_args(self.config, app_config.startup_args)
            if enabled:
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
        assert_test_app_cdp_target(self.config)
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
        if is_test_app_package(self.config):
            self._close_test_package()
            return
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

    def _close_test_package(self) -> None:
        target = _test_target_path(self.config)
        for process in _matching_test_processes(self.config):
            try:
                # Recheck immediately before signalling in case the process has
                # exited or the PID has been reused since enumeration.
                if _process_executable(process) != target:
                    continue
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
            except (psutil.Error, OSError, AppStartupError):
                raise AppStartupError("按测试 APP 路径清理进程失败；未按名称关闭任何生产 APP") from None

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
