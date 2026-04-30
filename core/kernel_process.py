from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from core.process import listening_ports_by_pid, process_command_line_by_pid


@dataclass
class KernelRuntime:
    environment_name: str
    pid: int
    cdp_port: int
    command_line: str = ""

    @property
    def cdp_endpoint(self) -> str:
        return f"http://127.0.0.1:{self.cdp_port}"


@dataclass
class KernelTarget:
    id: str
    title: str
    url: str
    type: str = ""


def resolve_kernel_runtime(
    environment_name: str,
    pid: int,
    timeout_seconds: int = 30,
    cdp_port: int = 0,
    probe_timeout_seconds: int = 3,
    http_timeout_seconds: int = 2,
) -> KernelRuntime:
    command_line = process_command_line_by_pid(pid)
    candidate_ports = [
        cdp_port,
        extract_remote_debugging_port(command_line),
        extract_cdp_port_from_request_params(command_line),
    ]
    for candidate_port in candidate_ports:
        if candidate_port and wait_kernel_cdp_ready(
            candidate_port,
            timeout_seconds=probe_timeout_seconds,
            http_timeout_seconds=http_timeout_seconds,
            raise_on_timeout=False,
        ):
            cdp_port = candidate_port
            break
    else:
        cdp_port = wait_for_cdp_port_by_pid(
            pid,
            timeout_seconds=timeout_seconds,
            http_timeout_seconds=http_timeout_seconds,
        )
    wait_kernel_cdp_ready(cdp_port, timeout_seconds=timeout_seconds, http_timeout_seconds=http_timeout_seconds)
    return KernelRuntime(
        environment_name=environment_name,
        pid=pid,
        cdp_port=cdp_port,
        command_line=command_line,
    )


def extract_remote_debugging_port(command_line: str) -> int:
    if not command_line:
        return 0
    patterns = [
        r"--remote-debugging-port=(\d+)",
        r"--remote-debugging-port\s+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, command_line)
        if match:
            return int(match.group(1))
    return 0


def extract_cdp_port_from_request_params(command_line: str) -> int:
    if not command_line:
        return 0

    urls = re.findall(r"https?://[^\s\"']+", command_line)
    preferred_param_names = (
        "debugPort",
        "debug_port",
        "cdpPort",
        "cdp_port",
        "remoteDebuggingPort",
        "remote_debugging_port",
    )
    fallback_param_names = ("port",)

    for param_names in (preferred_param_names, fallback_param_names):
        for url in urls:
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            for param_name in param_names:
                for value in params.get(param_name, []):
                    text = str(value).strip()
                    if text.isdigit():
                        return int(text)
    return 0


def wait_for_cdp_port_by_pid(pid: int, timeout_seconds: int = 30, http_timeout_seconds: int = 2) -> int:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for port in listening_ports_by_pid(pid):
            if is_kernel_cdp_ready(port, timeout_seconds=http_timeout_seconds):
                return port
        time.sleep(0.5)
    raise TimeoutError(f"kernel CDP port was not found for pid={pid}")


def wait_kernel_cdp_ready(
    port: int,
    timeout_seconds: int = 30,
    http_timeout_seconds: int = 2,
    raise_on_timeout: bool = True,
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_kernel_cdp_ready(port, timeout_seconds=http_timeout_seconds):
            return True
        time.sleep(0.5)
    if raise_on_timeout:
        raise TimeoutError(f"kernel CDP was not ready: port={port}")
    return False


def is_kernel_cdp_ready(port: int, timeout_seconds: int = 2) -> bool:
    if port <= 0:
        return False
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return False
    return bool(payload.get("webSocketDebuggerUrl") or payload.get("Browser"))


def list_kernel_targets(port: int, timeout_seconds: int = 2) -> list[KernelTarget]:
    if port <= 0:
        return []
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [
        KernelTarget(
            id=str(item.get("id", "")),
            title=str(item.get("title", "")),
            url=str(item.get("url", "")),
            type=str(item.get("type", "")),
        )
        for item in payload
        if isinstance(item, dict)
    ]


def wait_kernel_target_url(
    port: int,
    url_keyword: str,
    expected_present: bool = True,
    timeout_seconds: int = 30,
    http_timeout_seconds: int = 2,
    stable_absence_seconds: int = 3,
) -> bool:
    deadline = time.time() + timeout_seconds
    absent_since = 0.0
    while time.time() < deadline:
        targets = list_kernel_targets(port, timeout_seconds=http_timeout_seconds)
        has_match = any(url_keyword in target.url for target in targets)
        if expected_present and has_match:
            return True
        if not expected_present:
            if not has_match:
                if absent_since == 0:
                    absent_since = time.time()
                if time.time() - absent_since >= stable_absence_seconds:
                    return True
            else:
                absent_since = 0.0
        time.sleep(0.5)
    return False


def close_kernel_target_by_url(port: int, url_keyword: str, timeout_seconds: int = 2) -> bool:
    closed = False
    for target in list_kernel_targets(port, timeout_seconds=timeout_seconds):
        if url_keyword not in target.url or not target.id:
            continue
        target_id = urllib.parse.quote(target.id, safe="")
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/close/{target_id}",
                timeout=timeout_seconds,
            ):
                closed = True
        except (OSError, urllib.error.URLError):
            continue
    return closed


def kernel_version_from_command_line(command_line: str) -> str:
    if not command_line:
        return ""
    patterns = [
        r"Chrome/([0-9]{3}(?:\.[0-9]+)+)",
        r"browsers[\\/]+([0-9]+(?:\.[0-9]+)+)",
        r"GinsBrowser[\\/]+([0-9]+(?:\.[0-9]+)+)",
        r"([0-9]{3}(?:\.[0-9]+)+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, command_line)
        if match:
            return match.group(1)
    return ""


def kernel_version_from_cdp(port: int, timeout_seconds: int = 2) -> str:
    if port <= 0:
        return ""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return ""

    for key in ("Browser", "User-Agent"):
        value = str(payload.get(key, ""))
        match = re.search(r"(?:Chrome|GinsBrowser)/([0-9]{3}(?:\.[0-9]+)+)", value)
        if match:
            return match.group(1)
    return ""
