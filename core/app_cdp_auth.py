from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
from importlib import import_module
from pathlib import Path
from typing import Any

from core.app_config import resolve_app_config
from core.app_cdp_token import DEFAULT_TTL_SECONDS


class AppCdpAuthError(RuntimeError):
    """Safe-to-log failure while preparing an APP startup credential."""


_PORT_FLAGS = ("--remote-debugging-port", "--dicloak-debug-port")
_TOKEN_FLAG = "--dicloak-debug-token"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def _settings(config: dict[str, Any]) -> dict[str, Any]:
    return resolve_app_config(config).cdp_auth


def auth_enabled(config: dict[str, Any]) -> bool:
    enabled = _settings(config).get("enabled", True)
    if type(enabled) is not bool:
        raise AppCdpAuthError("app.cdp_auth.enabled 必须为布尔值")
    return enabled


def _integer(value: object, label: str, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise AppCdpAuthError(f"{label} 必须为 1 到 {maximum} 的整数")
    return value


def _port(config: dict[str, Any]) -> int:
    return _integer(config.get("cdp", {}).get("port", 9222), "cdp.port", 65535)


def _paths(config: dict[str, Any], settings: dict[str, Any]) -> tuple[Path, Path]:
    root = Path(config.get("_project_root") or Path(__file__).resolve().parent.parent)

    def resolve(value: str) -> Path:
        candidate = Path(value).expanduser()
        return candidate if candidate.is_absolute() else root / candidate

    script_value = str(settings.get("script_path") or "").strip()
    script = resolve(script_value) if script_value else Path(__file__).with_name("app_cdp_token.py")
    key_value = str(settings.get("private_key_path") or "").strip()
    if not key_value:
        env_name = str(settings.get("private_key_env", "DICLOAK_CDP_PRIVATE_KEY_PATH") or "").strip()
        key_value = os.environ.get(env_name, "").strip() if env_name else ""
    if not key_value:
        raise AppCdpAuthError("请配置 app.cdp_auth.private_key_path 或私钥路径环境变量 DICLOAK_CDP_PRIVATE_KEY_PATH")
    return script, resolve(key_value)


def resolve_cdp_private_key_path(config: dict[str, Any]) -> Path:
    """Resolve the explicitly configured key, without reading or searching files."""
    return _paths(config, _settings(config))[1]


def _validate_signing_dependencies() -> None:
    """Import the issuer's dependencies without loading a key or issuing a token."""
    try:
        import_module("cryptography")
        serialization = import_module("cryptography.hazmat.primitives.serialization")
        ed25519 = import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
        if not callable(getattr(serialization, "load_pem_private_key", None)) or not callable(
            getattr(ed25519, "Ed25519PrivateKey", None)
        ):
            raise ImportError
    except Exception:
        # Import failures can contain system paths or other uncontrolled output.
        # Keep the log actionable without exposing dependency exception details.
        raise AppCdpAuthError(
            "CDP 凭证签发依赖 cryptography 缺失或无法加载；请在当前执行框架的 Python 虚拟环境中执行 "
            'python -m pip install "cryptography>=41.0.0" 后重试'
        ) from None


def validate_cdp_auth_setup(config: dict[str, Any]) -> None:
    """Check configuration/files/dependencies. Never sign, read a key, or start an APP."""
    if not auth_enabled(config):
        return
    settings = _settings(config)
    _port(config)
    _integer(settings.get("ttl_seconds", DEFAULT_TTL_SECONDS), "app.cdp_auth.ttl_seconds", 86400)
    _integer(settings.get("timeout_seconds", 10), "app.cdp_auth.timeout_seconds", 3600)
    script, key = _paths(config, settings)
    if not script.is_file():
        raise AppCdpAuthError("CDP 凭证生成脚本不存在，请检查 app.cdp_auth.script_path")
    if not key.is_file():
        raise AppCdpAuthError("CDP 私钥文件不存在，请检查私钥路径；不会自动创建或复制私钥")
    _validate_signing_dependencies()


def _without_debug_args(args: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(args):
        arg = str(args[index])
        flag = arg.split("=", 1)[0]
        if flag in (*_PORT_FLAGS, _TOKEN_FLAG):
            if "=" not in arg and index + 1 < len(args) and not str(args[index + 1]).startswith("--"):
                index += 1
        else:
            result.append(arg)
        index += 1
    return result


def normalized_app_startup_args(config: dict[str, Any], startup_args: list[str]) -> list[str]:
    if not auth_enabled(config):
        return list(startup_args)
    args = _without_debug_args(startup_args)
    args.append(f"--dicloak-debug-port={_port(config)}")
    if not any(str(arg).split("=", 1)[0] == "--remote-allow-origins" for arg in args):
        args.append("--remote-allow-origins=*")
    return args


def redact_app_startup_args(args: list[str]) -> list[str]:
    safe: list[str] = []
    hide_next = False
    for value in args:
        arg = str(value)
        if hide_next:
            # A missing split value must not hide the following option itself.
            if not arg.startswith("--"):
                safe.append("<redacted>")
                hide_next = False
                continue
            hide_next = False
        if arg == _TOKEN_FLAG:
            safe.append(arg)
            hide_next = True
        elif arg.startswith(_TOKEN_FLAG + "="):
            safe.append(_TOKEN_FLAG + "=<redacted>")
        else:
            safe.append(arg)
    return safe


def _validate_token(token: str, *, port: int, ttl_seconds: int) -> None:
    try:
        if len(token) > 8192 or not _TOKEN_PATTERN.fullmatch(token):
            raise ValueError
        payload_part, signature_part = token.split(".")
        decode = lambda part: base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
        payload = json.loads(decode(payload_part))
        signature = decode(signature_part)
        if not isinstance(payload, dict) or len(signature) != 64:
            raise ValueError
        if type(payload.get("v")) is not int or payload["v"] != 1 or payload.get("aud") != "dicloak-app-cdp":
            raise ValueError
        if type(payload.get("port")) is not int or payload["port"] != port:
            raise ValueError
        issued, expires = payload.get("iat"), payload.get("exp")
        if type(issued) is not int or type(expires) is not int or expires - issued != ttl_seconds:
            raise ValueError
        now = int(time.time())
        if issued < 0 or issued > now + 5 or expires - now < min(30, ttl_seconds):
            raise ValueError
    except Exception:
        # Never echo stdout (the token) or decoder exceptions into a traceback.
        raise AppCdpAuthError("CDP 凭证输出无效、端口不匹配或即将过期，请检查签发脚本和系统时间") from None


def validate_app_cdp_token(config: dict[str, Any], token: str) -> None:
    """Recheck a prepared token immediately before launch, without signing again."""
    settings = _settings(config)
    ttl = _integer(settings.get("ttl_seconds", DEFAULT_TTL_SECONDS), "app.cdp_auth.ttl_seconds", 86400)
    _validate_token(token, port=_port(config), ttl_seconds=ttl)


def generate_app_cdp_token(config: dict[str, Any]) -> str:
    validate_cdp_auth_setup(config)
    if not auth_enabled(config):
        raise AppCdpAuthError("CDP 凭证签发未启用")
    settings = _settings(config)
    script, key = _paths(config, settings)
    ttl = settings.get("ttl_seconds", DEFAULT_TTL_SECONDS)
    port = _port(config)
    command = [sys.executable, str(script), "--private-key", str(key), "--port", str(port), "--ttl-seconds", str(ttl)]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="strict",
            timeout=settings.get("timeout_seconds", 10), check=False,
        )
    except subprocess.TimeoutExpired:
        raise AppCdpAuthError("CDP 凭证生成超时，脚本输出已隐藏") from None
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise AppCdpAuthError("无法执行 CDP 凭证生成脚本，请检查 Python、脚本路径和读取权限") from None
    if completed.returncode != 0:
        raise AppCdpAuthError(
            f"CDP 凭证生成失败（退出码 {completed.returncode}），请检查私钥及 cryptography 依赖；脚本输出已隐藏"
        )
    token = completed.stdout.strip()
    _validate_token(token, port=port, ttl_seconds=ttl)
    return token
