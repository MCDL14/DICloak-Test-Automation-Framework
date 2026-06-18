from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import queue
import shlex
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from core.remote_runner import RemoteHost, RemoteRunError, _connect_ssh_client, _sanitize_log_line


MANIFEST_NAME = ".remote_manifest.json"
SYNC_RULES_PATH = Path("config/remote_sync.yaml")

DEFAULT_INCLUDE_PATTERNS = (
    "*.md",
    "run.py",
    "streamlit_runner.py",
    "requirements*.txt",
    "pyproject.toml",
    "core/**",
    "locators/**",
    "pages/**",
    "tests/**",
    "ui/**",
    "config/*.example.yaml",
    "test_data/README.md",
    "test_data/import/**",
    "test_data/export/**",
    "test_data/bookmarks/**",
    "test_data/members/**",
    "test_data/extensions/**",
    "test_data/Tools/**",
)

PROTECTED_EXCLUDE_PATTERNS = (
    "logs/**",
    "reports/**",
    "screenshots/**",
    "remote_artifacts/**",
    "config/config.yaml",
    "config/test_data.yaml",
    "config/remote_hosts.yaml",
    "config/remote_sync.yaml",
    "config/remote_connection_cache.yaml",
)

DEFAULT_EXCLUDE_PATTERNS = (
    ".git/**",
    ".venv/**",
    "venv/**",
    "env/**",
    "__pycache__/**",
    "**/__pycache__/**",
    "*.pyc",
    "*.pyo",
    ".pytest_cache/**",
    ".mypy_cache/**",
    ".ruff_cache/**",
    *PROTECTED_EXCLUDE_PATTERNS,
)


@dataclass(frozen=True)
class LocalSyncBundle:
    manifest: dict[str, Any]
    files: tuple[tuple[str, Path], ...]
    archive_path: Path


@dataclass(frozen=True)
class RemoteCodeStatus:
    host_name: str
    state: str
    local_hash: str
    remote_hash: str
    local_file_count: int
    remote_file_count: int
    active_path: str
    synced_at: str
    source_branch: str
    source_commit: str
    message: str


@dataclass(frozen=True)
class RemoteSyncResult:
    host_name: str
    release_dir: str
    active_path: str
    backup_path: str
    switch_mode: str
    content_hash: str
    file_count: int
    archive_size: int
    started_at: float
    finished_at: float


def check_remote_code_status(
    host: RemoteHost,
    log_queue: queue.Queue | None = None,
    *,
    project_root: Path | str = ".",
) -> RemoteCodeStatus:
    """Compare local sync manifest with the manifest currently active on a remote host."""
    root = Path(project_root).resolve()
    manifest, files = build_local_manifest(root)
    _put(log_queue, f"远程代码检查：开始 节点={host.name}")
    _put(log_queue, f"本地快照：hash={manifest['content_hash']} 文件数={len(files)}")

    client = _connect_ssh_client(host)
    try:
        active_path = _remote_active_path(client, host)
        remote_manifest = _read_remote_manifest(client, host)
    finally:
        client.close()

    if not active_path:
        message = f"远端项目目录不存在：{host.project_dir}"
        state = "missing"
        remote_hash = ""
        remote_file_count = 0
        synced_at = ""
        source_branch = ""
        source_commit = ""
    elif not remote_manifest:
        message = "远端缺少同步清单，无法确认是否为当前代码。"
        state = "unknown"
        remote_hash = ""
        remote_file_count = 0
        synced_at = ""
        source_branch = ""
        source_commit = ""
    else:
        remote_hash = str(remote_manifest.get("content_hash", ""))
        remote_file_count = int(remote_manifest.get("file_count", 0) or 0)
        synced_at = str(remote_manifest.get("synced_at", ""))
        source_branch = str(remote_manifest.get("source_branch", ""))
        source_commit = str(remote_manifest.get("source_commit", ""))
        state = "synced" if remote_hash == manifest["content_hash"] else "outdated"
        message = "远端代码已同步。" if state == "synced" else "远端代码与本地当前工作区不一致。"

    _put(
        log_queue,
        "远程代码检查完成 → "
        f"节点={host.name} 状态={state} 本地={manifest['content_hash']} 远端={remote_hash or '-'}",
    )
    if message:
        _put(log_queue, message)

    return RemoteCodeStatus(
        host_name=host.name,
        state=state,
        local_hash=str(manifest["content_hash"]),
        remote_hash=remote_hash,
        local_file_count=len(files),
        remote_file_count=remote_file_count,
        active_path=active_path,
        synced_at=synced_at,
        source_branch=source_branch,
        source_commit=source_commit,
        message=message,
    )


def sync_remote_project(
    host: RemoteHost,
    log_queue: queue.Queue | None = None,
    *,
    project_root: Path | str = ".",
    compile_check: bool = True,
) -> RemoteSyncResult:
    """Publish the current local workspace to a remote Linux/macOS node as a new release snapshot."""
    if not host.sync_enabled:
        raise RemoteRunError(f"remote sync is disabled for host: {host.name}")

    root = Path(project_root).resolve()
    started_at = time.time()
    bundle = create_local_sync_bundle(root)
    manifest = bundle.manifest
    release_root = remote_release_root(host)
    release_name = _release_name(manifest)
    release_dir = _remote_join(release_root, release_name)
    remote_archive = f"/tmp/dicloak_sync_{release_name}.tar.gz"
    archive_size = bundle.archive_path.stat().st_size

    _put(log_queue, f"远程代码同步：开始 节点={host.name}")
    _put(log_queue, f"本地快照：hash={manifest['content_hash']} 文件数={manifest['file_count']}")
    _put(log_queue, f"远程发布目录：{release_dir}")

    client = _connect_ssh_client(host)
    try:
        _exec_checked(client, f"mkdir -p {shlex.quote(release_root)}", log_queue)
        _put(log_queue, f"上传快照包：{bundle.archive_path.name} ({bundle.archive_path.stat().st_size} bytes)")
        sftp = client.open_sftp()
        try:
            sftp.put(str(bundle.archive_path), remote_archive)
        finally:
            sftp.close()

        setup_output = _exec_checked(
            client,
            _remote_setup_script(
                host=host,
                remote_archive=remote_archive,
                release_root=release_root,
                release_dir=release_dir,
                release_name=release_name,
                keep_releases=host.sync_keep_releases,
                compile_check=compile_check,
            ),
            log_queue,
        )
        parsed = _parse_setup_output(setup_output)
    finally:
        client.close()
        try:
            bundle.archive_path.unlink()
        except OSError:
            pass

    finished_at = time.time()
    _put(
        log_queue,
        "远程代码同步完成 → "
        f"节点={host.name} 状态=synced 文件数={manifest['file_count']} 发布目录={release_dir}",
    )
    return RemoteSyncResult(
        host_name=host.name,
        release_dir=release_dir,
        active_path=parsed.get("ACTIVE_REAL", ""),
        backup_path=parsed.get("BACKUP_PATH", ""),
        switch_mode=parsed.get("SWITCH_MODE", ""),
        content_hash=str(manifest["content_hash"]),
        file_count=int(manifest["file_count"]),
        archive_size=archive_size,
        started_at=started_at,
        finished_at=finished_at,
    )


def create_local_sync_bundle(project_root: Path | str = ".") -> LocalSyncBundle:
    root = Path(project_root).resolve()
    manifest, files = build_local_manifest(root)
    archive_path = _create_archive(root, files, manifest)
    return LocalSyncBundle(
        manifest=manifest,
        files=tuple(files),
        archive_path=archive_path,
    )


def build_local_manifest(project_root: Path | str = ".") -> tuple[dict[str, Any], list[tuple[str, Path]]]:
    root = Path(project_root).resolve()
    include_patterns, exclude_patterns = _load_sync_rules(root)
    files = _collect_sync_files(root, include_patterns, exclude_patterns)
    content_hash = _content_hash(files)
    git_info = _git_info(root)
    manifest = {
        "schema": 1,
        "sync_method": "sftp_snapshot",
        "content_hash": content_hash,
        "file_count": len(files),
        "source_branch": git_info.get("branch", ""),
        "source_commit": git_info.get("commit", ""),
        "source_dirty": git_info.get("dirty", False),
        "source_status_count": git_info.get("status_count", 0),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "manifest_name": MANIFEST_NAME,
    }
    return manifest, files


def remote_release_root(host: RemoteHost) -> str:
    if host.sync_release_root.strip():
        return host.sync_release_root.rstrip("/")
    project_dir = host.project_dir.rstrip("/")
    if "/" not in project_dir.strip("/"):
        return f"{project_dir}_releases"
    parent, name = project_dir.rsplit("/", 1)
    return f"{parent}/{name}_releases"


def _load_sync_rules(project_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    rules_path = project_root / SYNC_RULES_PATH
    if not rules_path.exists():
        return DEFAULT_INCLUDE_PATTERNS, DEFAULT_EXCLUDE_PATTERNS
    try:
        loaded = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RemoteRunError(f"invalid remote sync rules: {rules_path}: {exc}") from exc
    include = loaded.get("include", DEFAULT_INCLUDE_PATTERNS)
    exclude = loaded.get("exclude", DEFAULT_EXCLUDE_PATTERNS)
    if not isinstance(include, list) or not isinstance(exclude, list):
        raise RemoteRunError("remote sync rules fields 'include' and 'exclude' must be lists")
    include_patterns = tuple(str(item).strip() for item in include if str(item).strip())
    exclude_patterns = _with_protected_excludes(tuple(str(item).strip() for item in exclude if str(item).strip()))
    return include_patterns, exclude_patterns


def _with_protected_excludes(exclude_patterns: tuple[str, ...]) -> tuple[str, ...]:
    combined = [*exclude_patterns, *PROTECTED_EXCLUDE_PATTERNS]
    return tuple(dict.fromkeys(pattern for pattern in combined if pattern))


def _collect_sync_files(
    project_root: Path,
    include_patterns: tuple[str, ...],
    exclude_patterns: tuple[str, ...],
) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for path in project_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(project_root).as_posix()
        if _matches_any(rel, exclude_patterns):
            continue
        if not _matches_any(rel, include_patterns):
            continue
        result.append((rel, path))
    result.sort(key=lambda item: item[0])
    return result


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _content_hash(files: list[tuple[str, Path]]) -> str:
    digest = hashlib.sha256()
    for rel, path in files:
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        file_digest = hashlib.sha256()
        with path.open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
                file_digest.update(chunk)
        digest.update(file_digest.hexdigest().encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _git_info(project_root: Path) -> dict[str, Any]:
    branch = _git_output(project_root, "rev-parse", "--abbrev-ref", "HEAD")
    commit = _git_output(project_root, "rev-parse", "--short", "HEAD")
    status = _git_output(project_root, "status", "--short")
    status_lines = [line for line in status.splitlines() if line.strip()]
    return {
        "branch": branch.strip(),
        "commit": commit.strip(),
        "dirty": bool(status_lines),
        "status_count": len(status_lines),
    }


def _git_output(project_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _create_archive(
    project_root: Path,
    files: list[tuple[str, Path]],
    manifest: dict[str, Any],
) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix="dicloak_remote_sync_", suffix=".tar.gz")
    os.close(fd)
    archive_path = Path(raw_path)
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    with tarfile.open(archive_path, "w:gz") as tar_obj:
        for rel, path in files:
            tar_obj.add(path, arcname=rel, recursive=False)
        info = tarfile.TarInfo(MANIFEST_NAME)
        info.size = len(manifest_bytes)
        info.mtime = time.time()
        tar_obj.addfile(info, io.BytesIO(manifest_bytes))
    return archive_path


def _remote_setup_script(
    *,
    host: RemoteHost,
    remote_archive: str,
    release_root: str,
    release_dir: str,
    release_name: str,
    keep_releases: int,
    compile_check: bool,
) -> str:
    python_bin = host.python.strip() or "python"
    venv_activate = host.venv_activate.strip()
    command_prefix = host.command_prefix.strip()
    compile_lines = []
    if command_prefix:
        compile_lines.append(f"{command_prefix}")
    if venv_activate:
        compile_lines.append('if [ -f "$VENV_ACTIVATE" ]; then . "$VENV_ACTIVATE"; fi')
    if compile_check:
        compile_lines.append('"$PYTHON_BIN" -m compileall -q core pages tests streamlit_runner.py ui')
    compile_block = "\n".join(compile_lines) if compile_lines else ":"

    return f"""
set -e
PROJECT={shlex.quote(host.project_dir)}
RELEASE_ROOT={shlex.quote(release_root)}
RELEASE_DIR={shlex.quote(release_dir)}
RELEASE_NAME={shlex.quote(release_name)}
REMOTE_ARCHIVE={shlex.quote(remote_archive)}
PYTHON_BIN={shlex.quote(python_bin)}
VENV_ACTIVATE={shlex.quote(venv_activate)}
KEEP_RELEASES={int(keep_releases)}
OLD_EXISTS=0
OLD_REAL=""
BACKUP_PATH=""
SWITCH_MODE=""
if [ -e "$PROJECT" ]; then
  OLD_EXISTS=1
  OLD_REAL=$(cd "$PROJECT" && pwd -P)
fi
mkdir -p "$RELEASE_ROOT" "$RELEASE_DIR"
tar -xzf "$REMOTE_ARCHIVE" -C "$RELEASE_DIR"
rm -f "$REMOTE_ARCHIVE"
if [ "$OLD_EXISTS" = "1" ] && [ -d "$OLD_REAL/config" ]; then
  mkdir -p "$RELEASE_DIR/config"
  for cfg in "$OLD_REAL"/config/*.yaml; do
    [ -f "$cfg" ] || continue
    base=$(basename "$cfg")
    case "$base" in
      *.example.yaml|remote_hosts.yaml|remote_sync.yaml|remote_connection_cache.yaml) continue ;;
    esac
    cp "$cfg" "$RELEASE_DIR/config/"
  done
fi
VENV_REAL=""
if [ "$OLD_EXISTS" = "1" ] && [ -e "$OLD_REAL/.venv" ]; then
  VENV_RESOLVE_PYTHON="$PYTHON_BIN"
  if [ -x "$OLD_REAL/.venv/bin/python" ]; then
    VENV_RESOLVE_PYTHON="$OLD_REAL/.venv/bin/python"
  fi
  VENV_REAL=$(cd "$OLD_REAL" && "$VENV_RESOLVE_PYTHON" -c 'from pathlib import Path; print(Path(".venv").resolve())' 2>/dev/null || true)
fi
if [ -n "$VENV_REAL" ]; then
  rm -f "$RELEASE_DIR/.venv"
  ln -s "$VENV_REAL" "$RELEASE_DIR/.venv"
fi
cd "$RELEASE_DIR"
{compile_block}
PROJECT_PARENT=$(dirname "$PROJECT")
mkdir -p "$PROJECT_PARENT"
if [ -L "$PROJECT" ]; then
  ln -sfn "$RELEASE_DIR" "$PROJECT"
  SWITCH_MODE="replace_symlink"
elif [ -e "$PROJECT" ]; then
  BACKUP_PATH="${{PROJECT}}.backup_${{RELEASE_NAME}}"
  mv "$PROJECT" "$BACKUP_PATH"
  ln -s "$RELEASE_DIR" "$PROJECT"
  SWITCH_MODE="backup_real_dir"
else
  ln -s "$RELEASE_DIR" "$PROJECT"
  SWITCH_MODE="create_symlink"
fi
if [ -n "$VENV_REAL" ]; then
  case "$VENV_REAL" in
    "$OLD_REAL"/*)
      if [ -n "$BACKUP_PATH" ]; then
        VENV_SUFFIX=${{VENV_REAL#"$OLD_REAL"}}
        VENV_REAL="${{BACKUP_PATH}}${{VENV_SUFFIX}}"
      fi
      ;;
  esac
  rm -f "$RELEASE_DIR/.venv"
  ln -s "$VENV_REAL" "$RELEASE_DIR/.venv"
fi
cd "$PROJECT"
ACTIVE_REAL=$(pwd -P)
printf 'ACTIVE_REAL=%s\\n' "$ACTIVE_REAL"
printf 'BACKUP_PATH=%s\\n' "$BACKUP_PATH"
printf 'SWITCH_MODE=%s\\n' "$SWITCH_MODE"
printf 'VENV_REAL=%s\\n' "$VENV_REAL"
if [ "$KEEP_RELEASES" -gt 0 ]; then
  DICLOAK_RELEASE_ROOT="$RELEASE_ROOT" DICLOAK_KEEP_RELEASES="$KEEP_RELEASES" DICLOAK_CURRENT_RELEASE="$RELEASE_DIR" DICLOAK_VENV_REAL="$VENV_REAL" "$PYTHON_BIN" - <<'PY'
from pathlib import Path
import os
import shutil

root = Path(os.environ["DICLOAK_RELEASE_ROOT"])
keep = int(os.environ["DICLOAK_KEEP_RELEASES"])
current = Path(os.environ["DICLOAK_CURRENT_RELEASE"]).resolve()
venv_text = os.environ.get("DICLOAK_VENV_REAL", "")
venv = Path(venv_text).resolve() if venv_text else None
if root.exists():
    releases = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for release in releases[keep:]:
        resolved = release.resolve()
        if resolved == current:
            continue
        if venv and (venv == resolved or resolved in venv.parents):
            continue
        shutil.rmtree(release, ignore_errors=True)
        removed += 1
    print(f"PRUNED_RELEASES={{removed}}")
PY
fi
"""


def _remote_active_path(client: Any, host: RemoteHost) -> str:
    command = (
        f"PROJECT={shlex.quote(host.project_dir)}; "
        'if [ -e "$PROJECT" ]; then cd "$PROJECT" && pwd -P; else exit 2; fi'
    )
    result = _exec_command(client, command)
    if result["exit_code"] != 0:
        return ""
    return str(result["stdout"]).strip().splitlines()[-1] if str(result["stdout"]).strip() else ""


def _read_remote_manifest(client: Any, host: RemoteHost) -> dict[str, Any]:
    try:
        sftp = client.open_sftp()
        try:
            manifest_path = _remote_join(host.project_dir, MANIFEST_NAME)
            with sftp.open(manifest_path, "r") as file_obj:
                raw = file_obj.read()
        finally:
            sftp.close()
    except Exception:
        return {}
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    else:
        text = str(raw)
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _exec_checked(client: Any, command: str, log_queue: queue.Queue | None = None) -> str:
    result = _exec_command(client, command)
    stdout = str(result["stdout"])
    stderr = str(result["stderr"])
    for line in stdout.splitlines():
        if line.strip():
            _put(log_queue, _sanitize_log_line(line.rstrip()))
    for line in stderr.splitlines():
        if line.strip():
            _put(log_queue, _sanitize_log_line(line.rstrip()))
    if int(result["exit_code"]) != 0:
        sanitized_stderr = "\n".join(
            _sanitize_log_line(line.rstrip())
            for line in stderr.splitlines()
            if line.strip()
        )
        raise RemoteRunError(
            f"remote sync command failed: exit_code={result['exit_code']}, stderr={sanitized_stderr}"
        )
    return stdout


def _exec_command(client: Any, command: str) -> dict[str, object]:
    stdin, stdout, stderr = client.exec_command(command)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = int(stdout.channel.recv_exit_status())
    return {"exit_code": code, "stdout": out, "stderr": err}


def _parse_setup_output(output: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in {"ACTIVE_REAL", "BACKUP_PATH", "SWITCH_MODE", "VENV_REAL"}:
            result[key] = value.strip()
    return result


def _release_name(manifest: dict[str, Any]) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{manifest['content_hash']}"


def _remote_join(*parts: str) -> str:
    clean = [str(part).strip("/") for part in parts if str(part).strip("/")]
    if not clean:
        return "/"
    prefix = "/" if str(parts[0]).startswith("/") else ""
    return prefix + "/".join(clean)


def _put(log_queue: queue.Queue | None, message: str) -> None:
    if log_queue is not None:
        log_queue.put(message)
