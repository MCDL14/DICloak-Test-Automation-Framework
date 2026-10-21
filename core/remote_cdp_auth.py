from __future__ import annotations

import errno
import hashlib
import os
import re
import stat
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import yaml

from core.app_cdp_auth import auth_enabled, resolve_cdp_private_key_path
from core.remote_runner import RemoteHost, RemoteRunError


_MAX_PRIVATE_KEY_BYTES = 16 * 1024


@dataclass(frozen=True)
class RemoteCdpKeyDeployment:
    remote_key_path: str
    override_path: str


def prepare_cdp_private_key(config: dict[str, Any]) -> bytes | None:
    """Read exactly the configured key for explicit remote sync; never sign a token."""
    try:
        if not auth_enabled(config):
            return None
        key_path = resolve_cdp_private_key_path(config)
        if not key_path.is_file():
            raise ValueError
        with key_path.open("rb") as key_file:
            info = os.fstat(key_file.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= _MAX_PRIVATE_KEY_BYTES:
                raise ValueError
            key_bytes = key_file.read(_MAX_PRIVATE_KEY_BYTES + 1)
        _validate_key_bytes(key_bytes)
        return key_bytes
    except Exception:
        raise RemoteRunError(
            "无法准备 CDP 私钥同步：请配置可读取的 app.cdp_auth.private_key_path "
            "或环境变量 DICLOAK_CDP_PRIVATE_KEY_PATH；"
            "文件须为不超过 16 KiB 的未加密 Ed25519 PKCS8 PEM 私钥"
        ) from None


def _validate_key_bytes(key_bytes: bytes) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if not isinstance(key_bytes, bytes) or not 0 < len(key_bytes) <= _MAX_PRIVATE_KEY_BYTES:
        raise ValueError
    normalized = key_bytes.strip().replace(b"\r\n", b"\n")
    if not re.fullmatch(
        rb"-----BEGIN PRIVATE KEY-----\n[A-Za-z0-9+/=\n]+-----END PRIVATE KEY-----", normalized
    ):
        # Only unencrypted PKCS8 PEM is supported, not OpenSSH/RSA/encrypted PEM.
        raise ValueError
    if not isinstance(serialization.load_pem_private_key(normalized, password=None), Ed25519PrivateKey):
        raise ValueError


def deploy_remote_cdp_private_key(
    client: Any,
    host: RemoteHost,
    key_bytes: bytes,
    *,
    release_dir: str,
    log_queue: Any = None,
) -> RemoteCdpKeyDeployment:
    """Deploy only this key over logged-in SFTP, separately from code archives/commands."""
    sftp = None
    try:
        _validate_key_bytes(key_bytes)
        _verify_authenticated_connection(client)
        project = _absolute_path(host.project_dir)
        release = _absolute_path(release_dir)
        override_path = _override_path(host.config, project=project, release=release)
        if log_queue is not None:
            log_queue.put("CDP 私钥安全同步：开始（独立加密通道，不进入代码快照）")
        sftp = client.open_sftp()
        remote_home = _absolute_path(sftp.normalize("."))
        # project_dir scopes one installation without exposing its configured local key path.
        namespace = hashlib.sha256(host.project_dir.encode("utf-8")).hexdigest()[:16]
        key_dir = remote_home / ".dicloak" / "cdp-keys" / namespace
        for private_dir in (remote_home / ".dicloak", remote_home / ".dicloak" / "cdp-keys", key_dir):
            _ensure_directory(sftp, private_dir, private=True)
        remote_key = key_dir / "private.pem"
        _ensure_directory(sftp, override_path.parent)
        # Validate both destinations before sending secret bytes; a bad sidecar cannot trigger a key write.
        _assert_regular_or_missing(sftp, remote_key)
        _assert_regular_or_missing(sftp, override_path)
        _atomic_private_write(sftp, remote_key, key_bytes)
        override_bytes = yaml.safe_dump(
            {"private_key_path": str(remote_key), "script_path": ""},
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
        _atomic_private_write(sftp, override_path, override_bytes)
        result = RemoteCdpKeyDeployment(str(remote_key), str(override_path))
        if log_queue is not None:
            log_queue.put("CDP 私钥安全同步：成功（私钥文件 0600，专属目录 0700）")
        return result
    except Exception:
        raise RemoteRunError(
            "CDP 私钥安全同步失败：请检查 SSH 登录连接、远端路径与权限，以及 SFTP 原子替换支持；"
            "不会将私钥写入代码快照、命令或日志"
        ) from None
    finally:
        if sftp is not None:
            try:
                sftp.close()
            except Exception:
                pass


def _verify_authenticated_connection(client: Any) -> None:
    """Require a live SSH login, but do not pin replaceable nodes to known_hosts."""
    transport = client.get_transport()
    if transport is None or not transport.is_active() or not transport.is_authenticated():
        raise ValueError


def _absolute_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError
    path = PurePosixPath(value)
    if not path.is_absolute() or str(path) == "/" or ".." in path.parts or value.startswith("//"):
        raise ValueError
    return path


def _override_path(config_path: str, *, project: PurePosixPath, release: PurePosixPath) -> PurePosixPath:
    if not config_path or "\\" in config_path or "\x00" in config_path:
        raise ValueError
    path = PurePosixPath(config_path)
    if ".." in path.parts or str(path) in {".", "/"}:
        raise ValueError
    if path.is_absolute():
        path = _absolute_path(config_path)
        if path == project:
            raise ValueError
        if project in path.parents:
            path = release / path.relative_to(project)
    else:
        path = release / path
    return path.with_name(path.name + ".cdp-auth.local.yaml")


def _lstat_or_none(sftp: Any, path: PurePosixPath) -> Any:
    try:
        return sftp.lstat(str(path))
    except OSError as exc:
        if isinstance(exc, FileNotFoundError) or exc.errno == errno.ENOENT:
            return None
        raise


def _ensure_directory(sftp: Any, path: PurePosixPath, *, private: bool = False) -> None:
    """Check every ancestor using lstat; never follow remote symlinks for key writes."""
    for directory in (*reversed(path.parents), path):
        if str(directory) == "/":
            continue
        info = _lstat_or_none(sftp, directory)
        if info is None:
            sftp.mkdir(str(directory), mode=0o700)
            info = sftp.lstat(str(directory))
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError
    if private:
        sftp.chmod(str(path), 0o700)
        if stat.S_IMODE(sftp.lstat(str(path)).st_mode) != 0o700:
            raise ValueError


def _assert_regular_or_missing(sftp: Any, path: PurePosixPath) -> None:
    info = _lstat_or_none(sftp, path)
    if info is not None and not stat.S_ISREG(info.st_mode):
        raise ValueError


def _atomic_private_write(sftp: Any, destination: PurePosixPath, payload: bytes) -> None:
    _assert_regular_or_missing(sftp, destination)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    created = False
    try:
        with sftp.open(str(temporary), "wx") as remote_file:
            created = True
            sftp.chmod(str(temporary), 0o600)
            if stat.S_IMODE(sftp.lstat(str(temporary)).st_mode) != 0o600:
                raise ValueError
            remote_file.write(payload)
            remote_file.flush()
        # No remove+rename fallback: preserve the old key when atomic replacement is unsupported.
        _assert_regular_or_missing(sftp, destination)
        sftp.posix_rename(str(temporary), str(destination))
        created = False
    finally:
        if created:
            try:
                sftp.remove(str(temporary))
            except Exception:
                pass
