from __future__ import annotations

import os
import json
import secrets
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml


DEFAULT_DOMAINS = {
    "control": "sync.dicloak.localhost",
    "cookie": "cookie.dicloak.localhost",
    "localstorage": "localstorage.dicloak.localhost",
    "indexeddb": "indexeddb.dicloak.localhost",
}
ORIGIN_MODES = {"localhost", "custom_domains"}
LOCAL_OVERRIDE_PATH = Path("config/local_auth_lab.yaml")
DEFAULT_CREDENTIALS_PATH = "test_data/local_auth_lab/credentials.json"


@dataclass(frozen=True)
class LocalAuthLabSettings:
    enabled: bool = False
    origin_mode: str = "localhost"
    host: str = "127.0.0.1"
    port: int = 18080
    database_path: Path = Path("test_data/local_auth_lab/auth.db")
    template_dir: Path = Path("web_templates/local_auth_lab")
    domains: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_DOMAINS))
    session_ttl_seconds: int = 15552000
    signing_secret: str = field(default="", repr=False)
    signing_secret_env: str = "DICLOAK_AUTH_LAB_SIGNING_SECRET"
    credentials_path: Path = Path(DEFAULT_CREDENTIALS_PATH)
    credentials_persistent: bool = False
    cookie_name: str = "dicloak_auth"
    cookie_http_only: bool = True
    cookie_same_site: str = "Lax"
    cookie_secure: bool = False
    cookie_path: str = "/"
    automation_api_enabled: bool = True
    admin_key: str = field(default="", repr=False)
    admin_key_env: str = "DICLOAK_AUTH_LAB_ADMIN_KEY"

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "LocalAuthLabSettings":
        root = Path(str(config.get("_project_root") or Path.cwd())).resolve()
        section = _merged_local_auth_lab_section(config, root)
        if not isinstance(section, dict):
            section = {}
        domains = dict(DEFAULT_DOMAINS)
        configured_domains = section.get("domains", {})
        if isinstance(configured_domains, dict):
            for key in domains:
                value = str(configured_domains.get(key, "") or "").strip().lower()
                if value:
                    domains[key] = value

        session = section.get("session", {}) if isinstance(section.get("session", {}), dict) else {}
        cookie = section.get("cookie", {}) if isinstance(section.get("cookie", {}), dict) else {}
        automation_api = (
            section.get("automation_api", {})
            if isinstance(section.get("automation_api", {}), dict)
            else {}
        )
        signing_secret_env = str(
            session.get("signing_secret_env", "DICLOAK_AUTH_LAB_SIGNING_SECRET")
        ).strip()
        admin_key_env = str(
            automation_api.get("admin_key_env", "DICLOAK_AUTH_LAB_ADMIN_KEY")
        ).strip()

        return cls(
            enabled=_as_bool(section.get("enabled", False)),
            origin_mode=str(section.get("origin_mode", "localhost") or "localhost").strip().lower(),
            host=str(section.get("host", "127.0.0.1") or "127.0.0.1").strip(),
            port=_as_int(section.get("port", 18080), 18080),
            database_path=_resolve_path(root, section.get("database_path"), "test_data/local_auth_lab/auth.db"),
            template_dir=_resolve_path(root, section.get("template_dir"), "web_templates/local_auth_lab"),
            domains=domains,
            session_ttl_seconds=_as_int(session.get("ttl_seconds", 15552000), 15552000),
            signing_secret=str(os.environ.get(signing_secret_env, "")) if signing_secret_env else "",
            signing_secret_env=signing_secret_env,
            credentials_path=_resolve_path(
                root,
                section.get("credentials_path"),
                DEFAULT_CREDENTIALS_PATH,
            ),
            cookie_name=str(cookie.get("name", "dicloak_auth") or "dicloak_auth").strip(),
            cookie_http_only=_as_bool(cookie.get("http_only", True)),
            cookie_same_site=str(cookie.get("same_site", "Lax") or "Lax").strip(),
            cookie_secure=_as_bool(cookie.get("secure", False)),
            cookie_path=str(cookie.get("path", "/") or "/").strip(),
            automation_api_enabled=_as_bool(automation_api.get("enabled", True)),
            admin_key=str(os.environ.get(admin_key_env, "")) if admin_key_env else "",
            admin_key_env=admin_key_env,
        )

    def ensure_persistent_credentials(self) -> "LocalAuthLabSettings":
        """Load or atomically create the persistent credentials shared by all run nodes."""
        if not self.enabled:
            return self

        path = self.credentials_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            payload = _read_credentials(path)
        else:
            payload = {
                "schema": 1,
                "signing_secret": self.signing_secret or secrets.token_urlsafe(48),
                "admin_key": self.admin_key or secrets.token_urlsafe(36),
            }
            _create_credentials_exclusively(path, payload)
            payload = _read_credentials(path)

        signing_secret = str(payload.get("signing_secret", "")).strip()
        admin_key = str(payload.get("admin_key", "")).strip()
        if len(signing_secret) < 32:
            raise ValueError(f"local auth lab persistent signing secret is invalid: {path}")
        if self.automation_api_enabled and len(admin_key) < 24:
            raise ValueError(f"local auth lab persistent admin key is invalid: {path}")
        return replace(
            self,
            signing_secret=signing_secret,
            admin_key=admin_key,
            credentials_persistent=True,
        )

    @property
    def scheme(self) -> str:
        return "https" if self.cookie_secure else "http"

    @property
    def base_urls(self) -> dict[str, str]:
        return {
            key: f"{self.scheme}://{domain}:{self.port}"
            for key, domain in self.domains.items()
        }

    def validate_for_start(self) -> None:
        if not self.enabled:
            raise ValueError("local_auth_lab is disabled")
        if self.origin_mode not in ORIGIN_MODES:
            raise ValueError("local_auth_lab.origin_mode must be localhost or custom_domains")
        if self.host not in {"127.0.0.1", "localhost"}:
            raise ValueError("local_auth_lab.host must be a loopback address")
        if not 1 <= self.port <= 65535:
            raise ValueError("local_auth_lab.port must be between 1 and 65535")
        if self.session_ttl_seconds <= 0:
            raise ValueError("local_auth_lab.session.ttl_seconds must be positive")
        if self.cookie_secure:
            raise ValueError("local_auth_lab.cookie.secure must be false until HTTPS is configured")
        if self.cookie_same_site not in {"Strict", "Lax", "None"}:
            raise ValueError("local_auth_lab.cookie.same_site must be Strict, Lax, or None")
        if not self.signing_secret:
            raise ValueError(
                f"local auth lab signing secret is missing: env={self.signing_secret_env or '-'}"
            )
        if not self.credentials_persistent:
            raise ValueError(
                "local auth lab must use persistent credentials: "
                f"credentials_path={self.credentials_path}"
            )
        if self.automation_api_enabled and not self.admin_key:
            raise ValueError(
                f"local auth lab admin key is missing: env={self.admin_key_env or '-'}"
            )
        required_templates = (
            self.template_dir / "auth.html",
            self.template_dir / "control.html",
            self.template_dir / "static" / "auth.js",
            self.template_dir / "static" / "styles.css",
        )
        missing = [str(path) for path in required_templates if not path.is_file()]
        if missing:
            raise ValueError(f"local auth lab template files are missing: {', '.join(missing)}")
        if len(set(self.domains.values())) != len(self.domains):
            raise ValueError("local_auth_lab domains must be unique")
        if any(not domain or ":" in domain or "/" in domain for domain in self.domains.values()):
            raise ValueError("local_auth_lab domains must be host names without scheme, port, or path")
        if self.origin_mode == "localhost" and any(
            domain != "localhost" and not domain.endswith(".localhost")
            for domain in self.domains.values()
        ):
            raise ValueError(
                "local_auth_lab localhost mode requires localhost or *.localhost domains"
            )

    def site_id_for_host(self, host_header: str) -> str:
        hostname = host_header.split(":", 1)[0].strip().lower()
        for site_id, domain in self.domains.items():
            if hostname == domain.lower():
                return site_id
        return ""


def _resolve_path(root: Path, value: object, default: str) -> Path:
    candidate = Path(str(value or default))
    return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()


def _merged_local_auth_lab_section(config: dict[str, Any], root: Path) -> dict[str, Any]:
    base = config.get("local_auth_lab", {})
    result = dict(base) if isinstance(base, dict) else {}
    override_path = root / LOCAL_OVERRIDE_PATH
    if not override_path.is_file():
        return result
    try:
        loaded = yaml.safe_load(override_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid local auth lab override: {override_path}: {exc}") from exc
    override = loaded.get("local_auth_lab", loaded)
    if not isinstance(override, dict):
        raise ValueError(f"local auth lab override must be a mapping: {override_path}")
    return _deep_merge(result, override)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_credentials(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid local auth lab credentials file: {path}: {exc}") from exc
    if not isinstance(loaded, dict) or int(loaded.get("schema", 0) or 0) != 1:
        raise ValueError(f"unsupported local auth lab credentials file: {path}")
    return loaded


def _create_credentials_exclusively(path: Path, payload: dict[str, Any]) -> None:
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    try:
        with os.fdopen(descriptor, "wb") as file_obj:
            file_obj.write(data)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
