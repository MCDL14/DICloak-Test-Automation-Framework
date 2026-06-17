from __future__ import annotations

import os
import queue
import re
import shlex
import socket
import stat
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml


class RemoteConfigError(Exception):
    """Raised when remote host configuration is missing or invalid."""


class RemoteRunError(Exception):
    """Raised when a remote command cannot be started."""


@dataclass(frozen=True)
class RemoteHost:
    name: str
    host: str
    username: str
    project_dir: str
    python: str = "python"
    config: str = "config/config.yaml"
    port: int = 22
    enabled: bool = True
    platform: str = ""
    password_env: str = ""
    key_filename: str = ""
    venv_activate: str = ""
    command_prefix: str = ""


@dataclass(frozen=True)
class RemoteRunRequest:
    scope: str
    value: str = ""
    attach_existing_app: bool = False


@dataclass(frozen=True)
class RemoteRunResult:
    host_name: str
    command: str
    exit_code: int
    started_at: float
    finished_at: float


@dataclass(frozen=True)
class RemoteHealthResult:
    host_name: str
    command: str
    exit_code: int
    started_at: float
    finished_at: float


@dataclass(frozen=True)
class RemoteArtifactResult:
    host_name: str
    local_dir: Path
    files_copied: int
    dirs_checked: tuple[str, ...]
    started_at: float
    finished_at: float


_HOST_LOCKS: dict[str, threading.Lock] = {}
_HOST_LOCKS_GUARD = threading.Lock()
_SENSITIVE_LOG_PATTERNS = (
    (re.compile(r"(apiSecret=)[^,\s]+"), r"\1<redacted>"),
    (re.compile(r'("apiSecret"\s*:\s*")[^"]*(")'), r"\1<redacted>\2"),
    (re.compile(r'("email"\s*:\s*")[^"]*(")'), r"\1<redacted>\2"),
    (re.compile(r'("name"\s*:\s*")[^"]*(")'), r"\1<redacted>\2"),
    (re.compile(r'("realName"\s*:\s*")[^"]*(")'), r"\1<redacted>\2"),
    (re.compile(r'("idCard"\s*:\s*")[^"]*(")'), r"\1<redacted>\2"),
    (re.compile(r'("mobile"\s*:\s*")[^"]*(")'), r"\1<redacted>\2"),
    (re.compile(r"(BOOT_TOKEN\s*=\s*)\S+"), r"\1<redacted>"),
    (re.compile(r"(USER_PASSWD\s*=\s*)\S+"), r"\1<redacted>"),
    (re.compile(r"(?i)(password\s*[:=]\s*)[^,\s]+"), r"\1<redacted>"),
    (re.compile(r"(?i)(token\s*[:=]\s*)[^,\s]+"), r"\1<redacted>"),
)


def load_remote_hosts(path: Path | str = "config/remote_hosts.yaml") -> list[RemoteHost]:
    config_path = Path(path)
    if not config_path.exists():
        return []
    try:
        with config_path.open("r", encoding="utf-8") as file_obj:
            loaded = yaml.safe_load(file_obj) or {}
    except yaml.YAMLError as exc:
        raise RemoteConfigError(f"invalid remote host YAML: {config_path}: {exc}") from exc
    except OSError as exc:
        raise RemoteConfigError(f"cannot read remote host config: {config_path}: {exc}") from exc

    hosts = loaded.get("hosts", [])
    if not isinstance(hosts, list):
        raise RemoteConfigError("remote host config field 'hosts' must be a list")

    result: list[RemoteHost] = []
    for index, item in enumerate(hosts, start=1):
        if not isinstance(item, dict):
            raise RemoteConfigError(f"remote host #{index} must be a mapping")
        host = _parse_remote_host(item, index)
        if host.enabled:
            result.append(host)
    return result


def run_remote_tests(
    host: RemoteHost,
    request: RemoteRunRequest,
    log_queue: queue.Queue,
) -> RemoteRunResult:
    lock = _host_lock(host.name)
    if not lock.acquire(blocking=False):
        log_queue.put(f"远程节点 {host.name} 已有任务正在运行，请等待当前任务结束后再启动。")
        raise RemoteRunError(f"remote host is busy: {host.name}")

    started_at = time.time()
    command = build_remote_command(host, request)
    try:
        log_queue.put(f"远程节点：{host.name} ({host.username}@{host.host}:{host.port})")
        log_queue.put(f"远程命令：{command}")
        exit_code = _exec_ssh_command(host, command, log_queue)
        finished_at = time.time()
        return RemoteRunResult(
            host_name=host.name,
            command=command,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=finished_at,
        )
    finally:
        lock.release()


def run_remote_health_check(host: RemoteHost, log_queue: queue.Queue) -> RemoteHealthResult:
    lock = _host_lock(host.name)
    if not lock.acquire(blocking=False):
        log_queue.put(f"远程节点 {host.name} 已有任务正在运行，请等待当前任务结束后再检查。")
        raise RemoteRunError(f"remote host is busy: {host.name}")

    started_at = time.time()
    command = build_remote_health_check_command(host)
    try:
        log_queue.put(f"远程节点：{host.name} ({host.username}@{host.host}:{host.port})")
        log_queue.put("远程健康检查：开始")
        exit_code = _exec_ssh_command(host, command, log_queue)
        finished_at = time.time()
        return RemoteHealthResult(
            host_name=host.name,
            command=command,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=finished_at,
        )
    finally:
        lock.release()


def collect_remote_artifacts(
    host: RemoteHost,
    since_timestamp: float,
    log_queue: queue.Queue,
    *,
    local_root: Path | str = "remote_artifacts",
    remote_dirs: tuple[str, ...] = ("logs", "screenshots", "reports"),
) -> RemoteArtifactResult:
    started_at = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    local_dir = Path(local_root) / _safe_path_name(host.name) / timestamp
    local_dir.mkdir(parents=True, exist_ok=True)
    copied = 0

    log_queue.put(f"远程产物拉取：开始 local_dir={local_dir}")
    try:
        client = _connect_ssh_client(host)
        try:
            sftp = client.open_sftp()
            try:
                cutoff = max(0.0, since_timestamp - 5)
                for remote_dir in remote_dirs:
                    remote_path = _remote_join(host.project_dir, remote_dir)
                    copied += _copy_recent_remote_tree(
                        sftp,
                        remote_path=remote_path,
                        local_base=local_dir / remote_dir,
                        since_timestamp=cutoff,
                        log_queue=log_queue,
                    )
            finally:
                sftp.close()
        finally:
            client.close()
    except RemoteRunError:
        raise
    except Exception as exc:
        raise RemoteRunError(f"remote artifact collection failed on {host.name}: {exc}") from exc

    finished_at = time.time()
    log_queue.put(f"远程产物拉取完成 → 文件数={copied} local_dir={local_dir}")
    return RemoteArtifactResult(
        host_name=host.name,
        local_dir=local_dir,
        files_copied=copied,
        dirs_checked=remote_dirs,
        started_at=started_at,
        finished_at=finished_at,
    )


def build_remote_command(host: RemoteHost, request: RemoteRunRequest) -> str:
    parts = [
        "cd",
        _quote(host.project_dir),
        "&&",
    ]
    if host.command_prefix.strip():
        parts.extend([host.command_prefix.strip(), "&&"])
    if host.venv_activate.strip():
        parts.extend([".", _quote(host.venv_activate), "&&"])

    run_parts = [
        _quote(host.python),
        "run.py",
        "--config",
        _quote(host.config),
    ]
    scope = request.scope.strip()
    value = request.value.strip()
    if scope == "precheck":
        run_parts.append("--precheck")
    elif scope == "level":
        run_parts.extend(["--level", _quote(value)])
    elif scope == "module":
        run_parts.extend(["--module", _quote(value)])
    elif scope == "business_module":
        run_parts.extend(["--business-module", _quote(value)])
    elif scope == "case":
        run_parts.extend(["--case", _quote(value)])
    else:
        raise RemoteConfigError(f"unsupported remote run scope: {scope}")

    if request.attach_existing_app and scope != "precheck":
        run_parts.append("--attach-existing-app")
    parts.extend(run_parts)
    return " ".join(parts)


def build_remote_health_check_command(host: RemoteHost) -> str:
    import_code = (
        "import importlib.util;"
        "mods=['yaml','playwright','psutil','openpyxl'];"
        "missing=[m for m in mods if importlib.util.find_spec(m) is None];"
        "print('missing=' + ','.join(missing) if missing else 'all core modules importable');"
        "raise SystemExit(1 if missing else 0)"
    )
    config_code = (
        "from pathlib import Path;"
        "from core.config import load_config;"
        f"cfg=load_config(Path({host.config!r}));"
        "print('config loaded; platform=' + str(cfg.get('platform', {}).get('name', 'auto')))"
    )
    app_code = (
        "from pathlib import Path;"
        "from core.config import load_config;"
        "from core.app_config import resolve_app_config;"
        f"cfg=load_config(Path({host.config!r}));"
        "app=resolve_app_config(cfg);"
        "path=Path(app.exe_path);"
        "print(str(path));"
        "raise SystemExit(0 if path.exists() else 1)"
    )
    lines = [
        "fail_count=0",
        "pass_check() { printf '[PASS] %s\\n' \"$1\"; }",
        "fail_check() { printf '[FAIL] %s\\n' \"$1\"; fail_count=$((fail_count + 1)); }",
        f"PROJECT_DIR={_quote(host.project_dir)}",
        f"CONFIG_PATH={_quote(host.config)}",
        f"VENV_ACTIVATE={_quote(host.venv_activate)}",
        f"PYTHON_BIN={_quote(host.python)}",
        'if [ -d "$PROJECT_DIR" ]; then pass_check "project_dir: $PROJECT_DIR"; else fail_check "project_dir missing: $PROJECT_DIR"; printf "远程健康检查完成 → 失败=%s\\n" "$fail_count"; exit "$fail_count"; fi',
        'cd "$PROJECT_DIR" || { fail_check "cannot enter project_dir: $PROJECT_DIR"; printf "远程健康检查完成 → 失败=%s\\n" "$fail_count"; exit "$fail_count"; }',
    ]
    if host.command_prefix.strip():
        lines.append(f"{host.command_prefix.strip()} || fail_check \"command_prefix failed\"")
    lines.extend([
        'if [ -f "run.py" ]; then pass_check "run.py exists"; else fail_check "run.py missing"; fi',
        'if [ -f "$CONFIG_PATH" ]; then pass_check "config exists: $CONFIG_PATH"; else fail_check "config missing: $CONFIG_PATH"; fi',
        'if [ -n "$VENV_ACTIVATE" ]; then if [ -f "$VENV_ACTIVATE" ]; then pass_check "venv activate exists: $VENV_ACTIVATE"; . "$VENV_ACTIVATE" || fail_check "venv activate failed: $VENV_ACTIVATE"; else fail_check "venv activate missing: $VENV_ACTIVATE"; fi; fi',
        'python_version_out=$("$PYTHON_BIN" --version 2>&1)',
        'if [ $? -eq 0 ]; then pass_check "python version: $python_version_out"; else fail_check "python version failed: $python_version_out"; fi',
        f'dep_out=$("$PYTHON_BIN" -c {_quote(import_code)} 2>&1)',
        'if [ $? -eq 0 ]; then pass_check "python dependencies: $dep_out"; else fail_check "python dependencies: $dep_out"; fi',
        f'config_out=$("$PYTHON_BIN" -c {_quote(config_code)} 2>&1)',
        'if [ $? -eq 0 ]; then pass_check "config load: $config_out"; else fail_check "config load failed: $config_out"; fi',
        f'app_out=$("$PYTHON_BIN" -c {_quote(app_code)} 2>&1)',
        'if [ $? -eq 0 ]; then pass_check "APP path exists: $app_out"; else fail_check "APP path missing or config unresolved: $app_out"; fi',
        'printf "远程健康检查完成 → 失败=%s\\n" "$fail_count"',
        'exit "$fail_count"',
    ])
    return " ; ".join(lines)


def _parse_remote_host(item: dict[str, Any], index: int) -> RemoteHost:
    name = str(item.get("name", "")).strip()
    host = str(item.get("host", "")).strip()
    username = str(item.get("username", "")).strip()
    project_dir = str(item.get("project_dir", "")).strip()
    if not name:
        raise RemoteConfigError(f"remote host #{index} is missing name")
    if not host:
        raise RemoteConfigError(f"remote host {name} is missing host")
    if not username:
        raise RemoteConfigError(f"remote host {name} is missing username")
    if not project_dir:
        raise RemoteConfigError(f"remote host {name} is missing project_dir")

    port = item.get("port", 22)
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise RemoteConfigError(f"remote host {name} port must be an integer between 1 and 65535")

    return RemoteHost(
        name=name,
        host=host,
        username=username,
        project_dir=project_dir,
        python=str(item.get("python", "python")).strip() or "python",
        config=str(item.get("config", "config/config.yaml")).strip() or "config/config.yaml",
        port=port,
        enabled=bool(item.get("enabled", True)),
        platform=str(item.get("platform", "")).strip(),
        password_env=str(item.get("password_env", "")).strip(),
        key_filename=str(item.get("key_filename", "")).strip(),
        venv_activate=str(item.get("venv_activate", "")).strip(),
        command_prefix=str(item.get("command_prefix", "")).strip(),
    )


def _exec_ssh_command(host: RemoteHost, command: str, log_queue: queue.Queue) -> int:
    client = _connect_ssh_client(host)
    try:
        transport = client.get_transport()
        if transport is None:
            raise RemoteRunError(f"cannot open SSH transport for {host.name}")
        channel = transport.open_session()
        channel.set_combine_stderr(True)
        channel.get_pty()
        channel.exec_command(command)
        _stream_channel(channel, log_queue)
        return int(channel.recv_exit_status())
    finally:
        client.close()


def _connect_ssh_client(host: RemoteHost) -> Any:
    try:
        import paramiko
    except ImportError as exc:
        raise RemoteRunError("paramiko is required for UI remote execution") from exc

    password = os.environ.get(host.password_env, "") if host.password_env else ""
    connect_kwargs: dict[str, Any] = {
        "hostname": host.host,
        "port": host.port,
        "username": host.username,
        "timeout": 15,
        "banner_timeout": 15,
        "auth_timeout": 15,
    }
    if host.key_filename:
        connect_kwargs["key_filename"] = str(Path(host.key_filename).expanduser())
    if password:
        connect_kwargs["password"] = password
    if not host.key_filename and not password:
        connect_kwargs["look_for_keys"] = True
        connect_kwargs["allow_agent"] = True

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(**connect_kwargs)
        return client
    except (OSError, socket.timeout, paramiko.SSHException) as exc:
        client.close()
        raise RemoteRunError(f"remote SSH connection failed on {host.name}: {exc}") from exc


def _stream_channel(channel: Any, log_queue: queue.Queue) -> None:
    buffer = ""
    while True:
        if channel.recv_ready():
            data = channel.recv(4096)
            text = data.decode("utf-8", errors="replace")
            buffer = _flush_complete_lines(buffer + text, log_queue)
        if channel.exit_status_ready():
            while channel.recv_ready():
                data = channel.recv(4096)
                text = data.decode("utf-8", errors="replace")
                buffer = _flush_complete_lines(buffer + text, log_queue)
            break
        time.sleep(0.1)
    if buffer.strip():
        log_queue.put(_sanitize_log_line(buffer.rstrip()))


def _flush_complete_lines(text: str, log_queue: queue.Queue) -> str:
    lines = text.splitlines(keepends=True)
    if not lines:
        return ""
    pending = ""
    if not lines[-1].endswith(("\n", "\r")):
        pending = lines.pop()
    for line in lines:
        clean_line = line.rstrip()
        if clean_line:
            log_queue.put(_sanitize_log_line(clean_line))
    return pending


def _sanitize_log_line(line: str) -> str:
    sanitized = line
    for pattern, replacement in _SENSITIVE_LOG_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def _host_lock(name: str) -> threading.Lock:
    with _HOST_LOCKS_GUARD:
        lock = _HOST_LOCKS.get(name)
        if lock is None:
            lock = threading.Lock()
            _HOST_LOCKS[name] = lock
        return lock


def _quote(value: str) -> str:
    return shlex.quote(value)


def _copy_recent_remote_tree(
    sftp: Any,
    *,
    remote_path: str,
    local_base: Path,
    since_timestamp: float,
    log_queue: queue.Queue,
) -> int:
    try:
        entries = sftp.listdir_attr(remote_path)
    except FileNotFoundError:
        log_queue.put(f"远程产物目录不存在，跳过：{remote_path}")
        return 0
    except OSError as exc:
        log_queue.put(f"远程产物目录读取失败，跳过：{remote_path}: {exc}")
        return 0

    copied = 0
    for entry in entries:
        child_remote = _remote_join(remote_path, entry.filename)
        child_local = local_base / entry.filename
        if stat.S_ISDIR(entry.st_mode):
            copied += _copy_recent_remote_tree(
                sftp,
                remote_path=child_remote,
                local_base=child_local,
                since_timestamp=since_timestamp,
                log_queue=log_queue,
            )
            continue
        if entry.st_mtime < since_timestamp:
            continue
        child_local.parent.mkdir(parents=True, exist_ok=True)
        sftp.get(child_remote, str(child_local))
        copied += 1
        log_queue.put(f"远程产物已拉取：{child_remote} -> {child_local}")
    return copied


def _remote_join(*parts: str) -> str:
    clean = [str(part).strip("/") for part in parts if str(part).strip("/")]
    if not clean:
        return "/"
    prefix = "/" if str(parts[0]).startswith("/") else ""
    return prefix + "/".join(clean)


def _safe_path_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "remote"


def remote_host_names(hosts: Iterable[RemoteHost]) -> list[str]:
    return [host.name for host in hosts]
