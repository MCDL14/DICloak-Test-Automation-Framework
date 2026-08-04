from __future__ import annotations

import json
import logging
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from core.local_auth_lab.database import LocalAuthDatabase, SCHEMA_VERSION
from core.local_auth_lab.security import (
    TokenValidationError,
    decode_token_payload_unverified,
    issue_token,
    signing_key_id,
    token_fingerprint,
    token_hash,
    validate_token,
)
from core.local_auth_lab.settings import LocalAuthLabSettings


SERVICE_NAME = "dicloak-local-auth-lab"
SERVICE_VERSION = "1.0.0"
AUTH_SITE_IDS = {"cookie", "localstorage", "indexeddb"}
STORAGE_LABELS = {
    "cookie": "Cookie",
    "localstorage": "Local Storage",
    "indexeddb": "IndexedDB",
}
STORAGE_TYPES = {
    "cookie": "cookie",
    "localstorage": "localStorage",
    "indexeddb": "indexedDB",
}


class LocalAuthLabServerError(RuntimeError):
    pass


class LocalAuthLabServer:
    def __init__(self, settings: LocalAuthLabSettings, logger: logging.Logger | None = None):
        self.settings = settings
        self.logger = logger or logging.getLogger("dicloak_automation.local_auth_lab")
        self.database = LocalAuthDatabase(settings.database_path)
        self.instance_id = f"lab-{uuid.uuid4().hex[:12]}"
        self.started_at = ""
        self.owned_by_current_run = False
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_urls(self) -> dict[str, str]:
        return self.settings.base_urls

    @property
    def running(self) -> bool:
        return bool(self._server and self._thread and self._thread.is_alive())

    def start(self) -> "LocalAuthLabServer":
        try:
            self.settings.validate_for_start()
        except ValueError as exc:
            raise LocalAuthLabServerError(str(exc)) from exc

        existing = self._existing_health()
        if existing:
            if self._health_is_compatible(existing):
                self._adopt_existing_health(existing)
                return self
            raise LocalAuthLabServerError(
                f"local auth lab port is occupied by an unknown or incompatible service: "
                f"{self.settings.host}:{self.settings.port}"
            )
        if _port_open(self.settings.host, self.settings.port):
            raise LocalAuthLabServerError(
                f"local auth lab port is occupied: {self.settings.host}:{self.settings.port}"
            )

        self.database.initialize()
        handler = _build_handler(self)
        try:
            self._server = ThreadingHTTPServer((self.settings.host, self.settings.port), handler)
        except OSError as exc:
            raise LocalAuthLabServerError(
                f"cannot bind local auth lab at {self.settings.host}:{self.settings.port}: {exc}"
            ) from exc
        self._server.daemon_threads = True
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="dicloak-local-auth-lab",
            daemon=True,
        )
        self._thread.start()
        self.owned_by_current_run = True
        self.wait_ready()
        self.logger.info(
            "Local auth lab started: instance=%s host=%s port=%s",
            self.instance_id,
            self.settings.host,
            self.settings.port,
        )
        return self

    def try_reuse_existing(self) -> bool:
        """Attach to a compatible existing service without requiring start-only secrets."""
        existing = self._existing_health()
        if not existing or not self._health_is_compatible(existing):
            return False
        self._adopt_existing_health(existing)
        return True

    def wait_ready(self, timeout_seconds: float = 5) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        last_error = ""
        while time.time() < deadline:
            try:
                health = self.health_check(timeout_seconds=1)
                if health.get("status") == "ok":
                    return health
            except Exception as exc:
                last_error = str(exc)
            time.sleep(0.1)
        self.stop()
        raise LocalAuthLabServerError(f"local auth lab did not become ready: {last_error}")

    def health_check(self, timeout_seconds: float = 2) -> dict[str, Any]:
        request = urllib.request.Request(
            f"http://{self.settings.host}:{self.settings.port}/__automation__/health",
            headers={"Host": self.settings.domains["control"]},
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise LocalAuthLabServerError("unexpected local auth lab health payload")
        return payload

    def diagnostics(self) -> dict[str, Any]:
        try:
            health = self.health_check()
        except Exception as exc:
            return {"service": SERVICE_NAME, "status": "unavailable", "error": str(exc)}
        return {
            "service": health.get("service"),
            "status": health.get("status"),
            "version": health.get("version"),
            "instanceId": health.get("instanceId"),
            "schemaVersion": health.get("schemaVersion"),
            "originMode": health.get("originMode"),
            "sites": health.get("sites", []),
        }

    def stop(self) -> None:
        if not self.owned_by_current_run:
            return
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        self.owned_by_current_run = False
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=3)
        self.logger.info("Local auth lab stopped: instance=%s", self.instance_id)

    def _existing_health(self) -> dict[str, Any]:
        try:
            return self.health_check(timeout_seconds=0.5)
        except Exception:
            return {}

    def _adopt_existing_health(self, health: dict[str, Any]) -> None:
        self.instance_id = str(health.get("instanceId", "existing"))
        self.started_at = str(health.get("startedAt", ""))
        self.owned_by_current_run = False
        self.logger.info(
            "Reusing existing local auth lab: instance=%s port=%s",
            self.instance_id,
            self.settings.port,
        )

    def _health_is_compatible(self, health: dict[str, Any]) -> bool:
        sites = set(health.get("sites", [])) if isinstance(health.get("sites"), list) else set()
        domains = health.get("domains", {}) if isinstance(health.get("domains"), dict) else {}
        return (
            self.settings.credentials_persistent
            and health.get("service") == SERVICE_NAME
            and str(health.get("version", "")).split(".", 1)[0] == SERVICE_VERSION.split(".", 1)[0]
            and int(health.get("schemaVersion", 0) or 0) == SCHEMA_VERSION
            and health.get("originMode") == self.settings.origin_mode
            and AUTH_SITE_IDS.issubset(sites)
            and int(health.get("port", 0) or 0) == self.settings.port
            and domains == self.settings.domains
            and int(health.get("sessionTtlSeconds", 0) or 0)
            == self.settings.session_ttl_seconds
            and health.get("signingKeyId") == signing_key_id(self.settings.signing_secret)
        )


def _build_handler(app: LocalAuthLabServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = SERVICE_NAME

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def log_message(self, format: str, *args: object) -> None:
            app.logger.debug("Local auth lab HTTP: %s", format % args)

        def _dispatch(self, method: str) -> None:
            request_id = uuid.uuid4().hex[:12]
            started = time.perf_counter()
            path = self.path.split("?", 1)[0]
            site_id = app.settings.site_id_for_host(self.headers.get("Host", ""))
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            try:
                if not site_id:
                    status = self._json(HTTPStatus.BAD_REQUEST, {"code": "UNKNOWN_HOST"})
                    return
                if path == "/__automation__/health" and method == "GET":
                    status = self._json(HTTPStatus.OK, _health_payload(app))
                    return
                if path.startswith("/__automation__/"):
                    status = self._automation(method, path, site_id)
                    return
                if path == "/static/styles.css" and method == "GET":
                    status = self._file(
                        app.settings.template_dir / "static" / "styles.css",
                        "text/css; charset=utf-8",
                    )
                    return
                if site_id == "control":
                    if method == "GET" and path == "/":
                        status = self._control_page()
                    else:
                        status = self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND"})
                    return
                if path == "/" and method == "GET":
                    status = self._auth_page(site_id)
                elif path == "/static/auth.js" and method == "GET":
                    status = self._file(
                        app.settings.template_dir / "static" / "auth.js",
                        "application/javascript; charset=utf-8",
                    )
                elif path == "/api/register" and method == "POST":
                    status = self._register(site_id)
                elif path == "/api/login" and method == "POST":
                    status = self._login(site_id)
                elif path == "/api/session" and method == "GET":
                    status = self._session(site_id)
                elif path == "/api/logout" and method == "POST":
                    status = self._logout(site_id)
                else:
                    status = self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND"})
            except Exception:
                app.logger.exception(
                    "Local auth lab request failed: request_id=%s site=%s method=%s path=%s",
                    request_id,
                    site_id or "unknown",
                    method,
                    path,
                )
                status = self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"success": False, "code": "INTERNAL_ERROR", "message": "服务内部错误"},
                )
            finally:
                app.logger.info(
                    "Local auth lab request: request_id=%s site=%s method=%s path=%s status=%s elapsed_ms=%s",
                    request_id,
                    site_id or "unknown",
                    method,
                    path,
                    int(status),
                    int((time.perf_counter() - started) * 1000),
                )

        def _register(self, site_id: str) -> HTTPStatus:
            body = self._body_json()
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", ""))
            confirm_password = str(body.get("confirmPassword", ""))
            validation = _validate_registration(username, password, confirm_password)
            if validation:
                return self._json(HTTPStatus.BAD_REQUEST, validation)
            created = app.database.register_user(site_id, username, password)
            if not created:
                return self._json(
                    HTTPStatus.CONFLICT,
                    {"success": False, "code": "USERNAME_EXISTS", "message": "账号已存在"},
                )
            return self._json(
                HTTPStatus.CREATED,
                {
                    "success": True,
                    "code": "REGISTERED",
                    "message": "注册成功，请登录",
                    "siteId": site_id,
                    "username": username,
                },
            )

        def _login(self, site_id: str) -> HTTPStatus:
            body = self._body_json()
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", ""))
            run_id = str(body.get("runId", "")).strip()[:200]
            user = app.database.authenticate(site_id, username, password)
            if not user:
                return self._json(
                    HTTPStatus.UNAUTHORIZED,
                    {"success": False, "code": "INVALID_CREDENTIALS", "message": "账号或密码错误"},
                )
            issued = issue_token(
                secret=app.settings.signing_secret,
                site_id=site_id,
                username=username,
                ttl_seconds=app.settings.session_ttl_seconds,
                run_id=run_id,
            )
            app.database.create_session(
                site_id=site_id,
                username=username,
                jti=str(issued.payload["jti"]),
                token_hash=issued.token_hash,
                run_id=run_id,
                issued_at=_epoch_iso(int(issued.payload["issuedAt"])),
                expires_at=_epoch_iso(int(issued.payload["expiresAt"])),
            )
            payload = {
                "success": True,
                "code": "AUTHENTICATED",
                "siteId": site_id,
                "storageType": STORAGE_TYPES[site_id],
                "username": username,
                "runId": run_id,
                "tokenFingerprint": issued.fingerprint,
                "issuedAt": _epoch_iso(int(issued.payload["issuedAt"])),
                "expiresAt": _epoch_iso(int(issued.payload["expiresAt"])),
            }
            headers: dict[str, str] = {}
            if site_id == "cookie":
                headers["Set-Cookie"] = _set_cookie_header(app.settings, issued.token)
            else:
                payload["token"] = issued.token
            return self._json(HTTPStatus.OK, payload, headers=headers)

        def _session(self, site_id: str) -> HTTPStatus:
            token = self._request_token(site_id)
            if not token:
                return self._unauthenticated("TOKEN_MISSING")
            try:
                state, renewed_token = _validate_or_migrate_session(app, site_id, token)
            except TokenValidationError as exc:
                headers = (
                    {"Set-Cookie": _clear_cookie_header(app.settings)}
                    if site_id == "cookie"
                    else None
                )
                return self._unauthenticated(exc.reason, headers=headers)
            headers: dict[str, str] = {}
            if renewed_token:
                if site_id == "cookie":
                    headers["Set-Cookie"] = _set_cookie_header(app.settings, renewed_token)
                else:
                    state["token"] = renewed_token
            return self._json(HTTPStatus.OK, state, headers=headers)

        def _logout(self, site_id: str) -> HTTPStatus:
            token = self._request_token(site_id)
            if token:
                try:
                    payload = validate_token(token, app.settings.signing_secret, site_id)
                    app.database.revoke_session(site_id, str(payload.get("jti", "")), "USER_LOGOUT")
                except TokenValidationError:
                    pass
            headers = {"Set-Cookie": _clear_cookie_header(app.settings)} if site_id == "cookie" else {}
            return self._json(
                HTTPStatus.OK,
                {"success": True, "authenticated": False, "status": "UNAUTHENTICATED"},
                headers=headers,
            )

        def _automation(self, method: str, path: str, site_id: str) -> HTTPStatus:
            if not app.settings.automation_api_enabled:
                return self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND"})
            if not _is_loopback(self.client_address[0]):
                return self._json(HTTPStatus.FORBIDDEN, {"code": "LOOPBACK_ONLY"})
            if not _safe_compare(self.headers.get("X-Auth-Lab-Admin-Key", ""), app.settings.admin_key):
                return self._json(HTTPStatus.UNAUTHORIZED, {"code": "ADMIN_KEY_INVALID"})
            if path == "/__automation__/version" and method == "GET":
                return self._json(
                    HTTPStatus.OK,
                    {"service": SERVICE_NAME, "version": SERVICE_VERSION, "schemaVersion": SCHEMA_VERSION},
                )
            if path == "/__automation__/state" and method == "GET":
                return self._json(HTTPStatus.OK, app.database.state_summary())
            body = self._body_json()
            if path == "/__automation__/users/ensure" and method == "POST":
                target_site = str(body.get("siteId", "")).strip().lower()
                username = str(body.get("username", "")).strip()
                password = str(body.get("password", ""))
                validation = _validate_registration(username, password, password)
                if target_site not in AUTH_SITE_IDS or validation:
                    return self._json(HTTPStatus.BAD_REQUEST, {"code": "VALIDATION_ERROR"})
                created = app.database.ensure_user(target_site, username, password)
                return self._json(
                    HTTPStatus.OK,
                    {"success": True, "created": created, "siteId": target_site, "username": username},
                )
            if path == "/__automation__/sessions/revoke" and method == "POST":
                target_site = str(body.get("siteId", "")).strip().lower()
                jti = str(body.get("jti", "")).strip()
                if target_site not in AUTH_SITE_IDS or not jti:
                    return self._json(HTTPStatus.BAD_REQUEST, {"code": "VALIDATION_ERROR"})
                revoked = app.database.revoke_session(target_site, jti, "AUTOMATION_REVOKE")
                return self._json(HTTPStatus.OK, {"success": True, "revoked": revoked})
            if path == "/__automation__/cleanup" and method == "POST":
                try:
                    result = app.database.cleanup(
                        site_id=str(body.get("siteId", "")).strip().lower(),
                        username=str(body.get("username", "")).strip(),
                        run_id=str(body.get("runId", "")).strip(),
                        jti=str(body.get("jti", "")).strip(),
                    )
                except ValueError as exc:
                    return self._json(HTTPStatus.BAD_REQUEST, {"code": "VALIDATION_ERROR", "message": str(exc)})
                return self._json(HTTPStatus.OK, {"success": True, **result})
            return self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND", "siteId": site_id})

        def _auth_page(self, site_id: str) -> HTTPStatus:
            path = app.settings.template_dir / "auth.html"
            text = path.read_text(encoding="utf-8")
            text = (
                text.replace("{{SITE_ID}}", site_id)
                .replace("{{SITE_NAME}}", f"{STORAGE_LABELS[site_id]} 登录模拟站")
                .replace("{{STORAGE_TYPE}}", STORAGE_LABELS[site_id])
                .replace("{{STORAGE_ID}}", STORAGE_TYPES[site_id])
            )
            return self._bytes(HTTPStatus.OK, text.encode("utf-8"), "text/html; charset=utf-8")

        def _control_page(self) -> HTTPStatus:
            path = app.settings.template_dir / "control.html"
            text = path.read_text(encoding="utf-8")
            for site_id, url in app.settings.base_urls.items():
                text = text.replace(f"{{{{{site_id.upper()}_URL}}}}", url)
            return self._bytes(HTTPStatus.OK, text.encode("utf-8"), "text/html; charset=utf-8")

        def _file(self, path: Path, content_type: str) -> HTTPStatus:
            try:
                data = path.read_bytes()
            except OSError:
                return self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND"})
            return self._bytes(HTTPStatus.OK, data, content_type)

        def _body_json(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > 1024 * 1024:
                return {}
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {}
            return payload if isinstance(payload, dict) else {}

        def _request_token(self, site_id: str) -> str:
            if site_id == "cookie":
                cookie = SimpleCookie()
                try:
                    cookie.load(self.headers.get("Cookie", ""))
                except Exception:
                    return ""
                morsel = cookie.get(app.settings.cookie_name)
                return morsel.value if morsel else ""
            authorization = self.headers.get("Authorization", "")
            prefix = "Bearer "
            return authorization[len(prefix) :].strip() if authorization.startswith(prefix) else ""

        def _unauthenticated(
            self,
            reason: str,
            headers: dict[str, str] | None = None,
        ) -> HTTPStatus:
            return self._json(
                HTTPStatus.UNAUTHORIZED,
                {"authenticated": False, "status": "UNAUTHENTICATED", "reason": reason},
                headers=headers,
            )

        def _json(
            self,
            status: HTTPStatus,
            payload: dict[str, Any],
            headers: dict[str, str] | None = None,
        ) -> HTTPStatus:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            return self._bytes(status, data, "application/json; charset=utf-8", headers=headers)

        def _bytes(
            self,
            status: HTTPStatus,
            data: bytes,
            content_type: str,
            headers: dict[str, str] | None = None,
        ) -> HTTPStatus:
            self.send_response(int(status))
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; object-src 'none'")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)
            return status

    return Handler


def _health_payload(app: LocalAuthLabServer) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "instanceId": app.instance_id,
        "startedAt": app.started_at,
        "pid": __import__("os").getpid(),
        "host": app.settings.host,
        "port": app.settings.port,
        "database": "ready",
        "schemaVersion": SCHEMA_VERSION,
        "originMode": app.settings.origin_mode,
        "sites": sorted(AUTH_SITE_IDS),
        "domains": dict(app.settings.domains),
        "sessionTtlSeconds": app.settings.session_ttl_seconds,
        "signingKeyId": signing_key_id(app.settings.signing_secret),
    }


def _validate_registration(username: str, password: str, confirmation: str) -> dict[str, Any]:
    if not 3 <= len(username) <= 64 or not all(char.isalnum() or char in "._-@" for char in username):
        return {"success": False, "code": "VALIDATION_ERROR", "message": "账号格式不正确"}
    if not 8 <= len(password) <= 128:
        return {"success": False, "code": "VALIDATION_ERROR", "message": "密码长度应为 8 至 128 位"}
    if password != confirmation:
        return {"success": False, "code": "VALIDATION_ERROR", "message": "两次输入的密码不一致"}
    return {}


def _validate_or_migrate_session(
    app: LocalAuthLabServer,
    site_id: str,
    token: str,
) -> tuple[dict[str, Any], str]:
    try:
        payload = validate_token(token, app.settings.signing_secret, site_id)
    except TokenValidationError as exc:
        if exc.reason != "TOKEN_INVALID":
            raise
        return _migrate_legacy_session(app, site_id, token)
    return _session_state(app, site_id, token, payload), ""


def _session_state(
    app: LocalAuthLabServer,
    site_id: str,
    token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    username = str(payload["username"])
    user = app.database.get_user(site_id, username)
    if not user or not user.enabled:
        raise TokenValidationError("ACCOUNT_DISABLED")
    session = app.database.get_session(site_id, str(payload["jti"]))
    if not session:
        raise TokenValidationError("SESSION_NOT_FOUND")
    if session.revoked_at:
        raise TokenValidationError("TOKEN_REVOKED")
    if not _safe_compare(session.token_hash, token_hash(token)):
        raise TokenValidationError("TOKEN_INVALID")
    return {
        "authenticated": True,
        "status": "AUTHENTICATED",
        "siteId": site_id,
        "storageType": STORAGE_TYPES[site_id],
        "username": username,
        "runId": str(payload.get("runId", "")),
        "tokenFingerprint": token_fingerprint(token),
        "issuedAt": _epoch_iso(int(payload["issuedAt"])),
        "expiresAt": _epoch_iso(int(payload["expiresAt"])),
    }


def _migrate_legacy_session(
    app: LocalAuthLabServer,
    site_id: str,
    token: str,
) -> tuple[dict[str, Any], str]:
    payload = decode_token_payload_unverified(token)
    if str(payload.get("siteId", "")) != site_id:
        raise TokenValidationError("TOKEN_SITE_MISMATCH")
    username = str(payload.get("username", ""))
    jti = str(payload.get("jti", ""))
    try:
        expires_at = int(payload.get("expiresAt", 0))
    except (TypeError, ValueError) as exc:
        raise TokenValidationError("TOKEN_INVALID") from exc
    if not username or not jti:
        raise TokenValidationError("TOKEN_INVALID")
    if expires_at <= int(time.time()):
        raise TokenValidationError("TOKEN_EXPIRED")

    user = app.database.get_user(site_id, username)
    if not user or not user.enabled:
        raise TokenValidationError("ACCOUNT_DISABLED")
    legacy = app.database.get_session(site_id, jti)
    if not legacy:
        raise TokenValidationError("SESSION_NOT_FOUND")
    if legacy.revoked_at:
        raise TokenValidationError("TOKEN_REVOKED")
    if not _safe_compare(legacy.token_hash, token_hash(token)):
        raise TokenValidationError("TOKEN_INVALID")

    issued = issue_token(
        secret=app.settings.signing_secret,
        site_id=site_id,
        username=username,
        ttl_seconds=app.settings.session_ttl_seconds,
        run_id=str(payload.get("runId", "")),
    )
    app.database.create_session(
        site_id=site_id,
        username=username,
        jti=str(issued.payload["jti"]),
        token_hash=issued.token_hash,
        run_id=str(issued.payload.get("runId", "")),
        issued_at=_epoch_iso(int(issued.payload["issuedAt"])),
        expires_at=_epoch_iso(int(issued.payload["expiresAt"])),
    )
    state = _session_state(app, site_id, issued.token, issued.payload)
    state["sessionMigrated"] = True
    app.logger.info(
        "Local auth lab migrated legacy session: site=%s username=%s old_fingerprint=%s new_fingerprint=%s",
        site_id,
        username,
        token_fingerprint(token),
        issued.fingerprint,
    )
    return state, issued.token


def _set_cookie_header(settings: LocalAuthLabSettings, token: str) -> str:
    parts = [
        f"{settings.cookie_name}={token}",
        f"Path={settings.cookie_path}",
        f"Max-Age={settings.session_ttl_seconds}",
        f"SameSite={settings.cookie_same_site}",
    ]
    if settings.cookie_http_only:
        parts.append("HttpOnly")
    if settings.cookie_secure:
        parts.append("Secure")
    return "; ".join(parts)


def _clear_cookie_header(settings: LocalAuthLabSettings) -> str:
    parts = [
        f"{settings.cookie_name}=",
        f"Path={settings.cookie_path}",
        "Max-Age=0",
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
        f"SameSite={settings.cookie_same_site}",
    ]
    if settings.cookie_http_only:
        parts.append("HttpOnly")
    if settings.cookie_secure:
        parts.append("Secure")
    return "; ".join(parts)


def _epoch_iso(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def _is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "::1"} or host.startswith("127.")


def _safe_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(str(left), str(right))
