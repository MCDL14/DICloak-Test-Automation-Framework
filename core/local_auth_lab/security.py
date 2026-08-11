from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any


class TokenValidationError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class IssuedToken:
    token: str = field(repr=False)
    payload: dict[str, Any]
    fingerprint: str
    token_hash: str


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    actual_salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=actual_salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return _b64(actual_salt), _b64(derived)


def verify_password(password: str, salt_text: str, expected_hash: str) -> bool:
    try:
        salt = _b64decode(salt_text)
        _, actual_hash = hash_password(password, salt=salt)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual_hash, expected_hash)


def issue_token(
    secret: str,
    site_id: str,
    username: str,
    ttl_seconds: int,
    run_id: str = "",
    now: int | None = None,
) -> IssuedToken:
    issued_at = int(time.time()) if now is None else int(now)
    payload = {
        "version": 1,
        "siteId": site_id,
        "username": username,
        "runId": run_id,
        "issuedAt": issued_at,
        "expiresAt": issued_at + int(ttl_seconds),
        "jti": secrets.token_urlsafe(18),
    }
    payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    encoded_payload = _b64(payload_text.encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    token = f"{encoded_payload}.{_b64(signature)}"
    return IssuedToken(
        token=token,
        payload=payload,
        fingerprint=token_fingerprint(token),
        token_hash=token_hash(token),
    )


def validate_token(
    token: str,
    secret: str,
    expected_site_id: str,
    now: int | None = None,
) -> dict[str, Any]:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        actual_signature = _b64decode(encoded_signature)
        expected_signature = hmac.new(
            secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(actual_signature, expected_signature):
            raise TokenValidationError("TOKEN_INVALID")
        payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
    except TokenValidationError:
        raise
    except Exception as exc:
        raise TokenValidationError("TOKEN_INVALID") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise TokenValidationError("TOKEN_INVALID")
    if str(payload.get("siteId", "")) != expected_site_id:
        raise TokenValidationError("TOKEN_SITE_MISMATCH")
    current = int(time.time()) if now is None else int(now)
    try:
        expires_at = int(payload.get("expiresAt", 0))
    except (TypeError, ValueError) as exc:
        raise TokenValidationError("TOKEN_INVALID") from exc
    if expires_at <= current:
        raise TokenValidationError("TOKEN_EXPIRED")
    if not str(payload.get("username", "")) or not str(payload.get("jti", "")):
        raise TokenValidationError("TOKEN_INVALID")
    return payload


def decode_token_payload_unverified(token: str) -> dict[str, Any]:
    """Decode a token only for legacy-key migration; callers must verify its stored hash."""
    try:
        encoded_payload, _ = token.split(".", 1)
        payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
    except Exception as exc:
        raise TokenValidationError("TOKEN_INVALID") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise TokenValidationError("TOKEN_INVALID")
    return payload


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_fingerprint(token: str) -> str:
    return token_hash(token)[:12]


def signing_key_id(secret: str) -> str:
    """Return a non-secret identifier used to detect cross-node key mismatches."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16] if secret else ""


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
