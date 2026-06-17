from __future__ import annotations

import os
import re
import shlex
import subprocess
import time

from core.platform.detect import is_windows

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is declared in requirements.
    psutil = None


def is_process_running(process_name: str) -> bool:
    if not process_name:
        return False
    if _psutil_processes_by_name(process_name):
        return True
    if not is_windows():
        return False
    return _windows_is_process_running(process_name)


def _windows_is_process_running(process_name: str) -> bool:
    normalized_name = process_name[:-4] if process_name.lower().endswith(".exe") else process_name
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="ignore",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        completed = None
    if completed and process_name.lower() in completed.stdout.lower():
        return True

    try:
        fallback = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"if (Get-Process -Name {normalized_name!r} -ErrorAction SilentlyContinue) {{ 'FOUND' }}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "FOUND" in fallback.stdout


def wait_for_process_running(process_name: str, timeout_seconds: int = 60) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_process_running(process_name):
            return True
        time.sleep(0.5)
    return False


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if psutil is not None:
        try:
            process = psutil.Process(pid)
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except (psutil.Error, OSError):
            return False
    if not is_windows():
        return False
    return _windows_is_pid_running(pid)


def _windows_is_pid_running(pid: int) -> bool:
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="ignore",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return str(pid) in completed.stdout


def wait_for_pid_running(pid: int, timeout_seconds: int = 60) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_pid_running(pid):
            return True
        time.sleep(0.5)
    return False


def wait_for_pid_stopped(pid: int, timeout_seconds: int = 60) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not is_pid_running(pid):
            return True
        time.sleep(0.5)
    return False


def wait_for_process_stopped(process_name: str, timeout_seconds: int = 60) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not is_process_running(process_name):
            return True
        time.sleep(0.5)
    return False


def process_command_lines(process_name: str) -> list[str]:
    if not process_name:
        return []
    lines = [
        command_line
        for process in _psutil_processes_by_name(process_name)
        if (command_line := _psutil_command_line(process))
    ]
    if lines:
        return lines
    if not is_windows():
        return []
    return _windows_process_command_lines(process_name)


def _windows_process_command_lines(process_name: str) -> list[str]:
    command = [
        "wmic",
        "process",
        "where",
        f"name='{process_name}'",
        "get",
        "CommandLine",
        "/value",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="ignore",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    lines: list[str] = []
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("CommandLine="):
            value = line.split("=", 1)[1].strip()
            if value:
                lines.append(value)
    return lines


def process_command_line_by_pid(pid: int) -> str:
    if pid <= 0:
        return ""
    if psutil is not None:
        try:
            command_line = _psutil_command_line(psutil.Process(pid))
            if command_line:
                return command_line
        except (psutil.Error, OSError):
            pass
    if not is_windows():
        return ""
    return _windows_process_command_line_by_pid(pid)


def _windows_process_command_line_by_pid(pid: int) -> str:
    command = [
        "wmic",
        "process",
        "where",
        f"ProcessId={pid}",
        "get",
        "CommandLine",
        "/value",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="ignore",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("CommandLine="):
            return line.split("=", 1)[1].strip()
    return ""


def main_process_ids(process_name: str) -> list[int]:
    if not process_name:
        return []
    ids = [
        process.pid
        for process in _psutil_processes_by_name(process_name)
        if _is_main_process_command_line(_psutil_command_line(process))
    ]
    if ids:
        return sorted(set(ids))
    if not is_windows():
        return []
    return _windows_main_process_ids(process_name)


def _windows_main_process_ids(process_name: str) -> list[int]:
    safe_name = process_name.replace("'", "''")
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            f"Get-CimInstance Win32_Process -Filter \"Name = '{safe_name}'\" | "
            "Where-Object { $_.CommandLine -and $_.CommandLine -notmatch '\\s--type=' } | "
            "Select-Object -ExpandProperty ProcessId"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    ids: list[int] = []
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if line.isdigit():
            ids.append(int(line))
    return sorted(set(ids))


def wait_for_new_main_process_ids(
    process_name: str,
    existing_ids: set[int],
    expected_count: int,
    timeout_seconds: int = 60,
) -> list[int]:
    deadline = time.time() + timeout_seconds
    last_new_ids: list[int] = []
    while time.time() < deadline:
        current_ids = main_process_ids(process_name)
        last_new_ids = [pid for pid in current_ids if pid not in existing_ids]
        if len(last_new_ids) >= expected_count:
            return last_new_ids[:expected_count]
        time.sleep(0.5)
    raise TimeoutError(
        "new main process count did not reach expected count: "
        f"process={process_name}, expected={expected_count}, actual={len(last_new_ids)}, pids={last_new_ids}"
    )


def process_executable_path_by_pid(pid: int) -> str:
    if pid <= 0:
        return ""
    if psutil is not None:
        try:
            process = psutil.Process(pid)
            executable_path = process.exe()
            if executable_path:
                return executable_path
            command_line = _psutil_command_line(process)
            fallback_path = _executable_path_from_command_line(command_line)
            if fallback_path:
                return fallback_path
        except (psutil.Error, OSError):
            pass
    if not is_windows():
        return ""
    return _windows_process_executable_path_by_pid(pid)


def _windows_process_executable_path_by_pid(pid: int) -> str:
    command = [
        "wmic",
        "process",
        "where",
        f"ProcessId={pid}",
        "get",
        "ExecutablePath,CommandLine",
        "/value",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="ignore",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    command_line = ""
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("ExecutablePath="):
            value = line.split("=", 1)[1].strip()
            if value:
                return value
        if line.startswith("CommandLine="):
            command_line = line.split("=", 1)[1].strip()

    return _executable_path_from_command_line(command_line, require_windows_exe=True)


def listening_ports_by_pid(pid: int) -> list[int]:
    if pid <= 0:
        return []
    ports = _psutil_listening_ports_by_pid(pid)
    if ports:
        return ports
    if not is_windows():
        return []
    return _windows_listening_ports_by_pid(pid)


def _windows_listening_ports_by_pid(pid: int) -> list[int]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"Get-NetTCPConnection -State Listen -OwningProcess {pid} | Select-Object -ExpandProperty LocalPort",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    ports: list[int] = []
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if line.isdigit():
            ports.append(int(line))
    return sorted(set(ports))


def _psutil_processes_by_name(process_name: str):
    if psutil is None or not process_name:
        return []
    expected = _normalize_process_name(process_name)
    processes = []
    try:
        iterator = psutil.process_iter(["pid", "name"])
    except (psutil.Error, OSError):
        return []
    for process in iterator:
        try:
            name = process.info.get("name") or process.name()
        except (psutil.Error, OSError):
            continue
        if _normalize_process_name(name) == expected:
            processes.append(process)
    return processes


def _normalize_process_name(process_name: str) -> str:
    name = os.path.basename(str(process_name or "")).strip().lower()
    return name[:-4] if name.endswith(".exe") else name


def _psutil_command_line(process) -> str:
    if psutil is None:
        return ""
    try:
        cmdline = process.cmdline()
    except (psutil.Error, OSError):
        return ""
    if not cmdline:
        return ""
    if os.name == "nt":
        return subprocess.list2cmdline([str(arg) for arg in cmdline])
    return shlex.join(str(arg) for arg in cmdline)


def _is_main_process_command_line(command_line: str) -> bool:
    return bool(command_line) and not re.search(r"\s--type=", command_line)


def _executable_path_from_command_line(command_line: str, require_windows_exe: bool = False) -> str:
    if not command_line:
        return ""
    match = re.match(r'^"([^"]+)"', command_line)
    if match:
        return match.group(1)
    first_arg = command_line.split(" ", 1)[0].strip()
    if not first_arg:
        return ""
    if require_windows_exe and not first_arg.lower().endswith(".exe"):
        return ""
    return first_arg


def _psutil_listening_ports_by_pid(pid: int) -> list[int]:
    if psutil is None:
        return []
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.Error, OSError):
        return []
    ports = []
    for connection in connections:
        if connection.pid != pid or connection.status != psutil.CONN_LISTEN:
            continue
        port = _connection_local_port(connection)
        if port:
            ports.append(port)
    return sorted(set(ports))


def _connection_local_port(connection) -> int:
    local_address = getattr(connection, "laddr", None)
    if not local_address:
        return 0
    port = getattr(local_address, "port", None)
    if isinstance(port, int):
        return port
    if isinstance(local_address, tuple) and len(local_address) >= 2 and isinstance(local_address[1], int):
        return local_address[1]
    return 0
