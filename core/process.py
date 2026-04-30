from __future__ import annotations

import re
import subprocess
import time


def is_process_running(process_name: str) -> bool:
    if not process_name:
        return False
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

    match = re.match(r'^"([^"]+)"', command_line)
    if match:
        return match.group(1)
    first_arg = command_line.split(" ", 1)[0].strip()
    return first_arg if first_arg.lower().endswith(".exe") else ""


def listening_ports_by_pid(pid: int) -> list[int]:
    if pid <= 0:
        return []
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
