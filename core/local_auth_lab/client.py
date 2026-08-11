from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from core.local_auth_lab.settings import LocalAuthLabSettings


class LocalAuthLabClientError(RuntimeError):
    pass


class LocalAuthLabClient:
    def __init__(self, settings: LocalAuthLabSettings, timeout_seconds: float = 5):
        self.settings = settings
        self.timeout_seconds = timeout_seconds

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/__automation__/health", require_admin=False)

    def version(self) -> dict[str, Any]:
        return self._request("GET", "/__automation__/version")

    def state(self) -> dict[str, Any]:
        return self._request("GET", "/__automation__/state")

    def ensure_user(self, site_id: str, username: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/__automation__/users/ensure",
            {"siteId": site_id, "username": username, "password": password},
        )

    def revoke_session(self, site_id: str, jti: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/__automation__/sessions/revoke",
            {"siteId": site_id, "jti": jti},
        )

    def cleanup(self, **filters: str) -> dict[str, Any]:
        payload = {
            key: value
            for key, value in {
                "siteId": filters.get("site_id", ""),
                "username": filters.get("username", ""),
                "runId": filters.get("run_id", ""),
                "jti": filters.get("jti", ""),
            }.items()
            if value
        }
        return self._request("POST", "/__automation__/cleanup", payload)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        require_admin: bool = True,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Host": self.settings.domains["control"],
            "Content-Type": "application/json",
        }
        if require_admin:
            headers["X-Auth-Lab-Admin-Key"] = self.settings.admin_key
        request = urllib.request.Request(
            f"http://{self.settings.host}:{self.settings.port}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LocalAuthLabClientError(
                f"local auth lab request failed: method={method} path={path} status={exc.code} body={body}"
            ) from exc
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise LocalAuthLabClientError(
                f"local auth lab request failed: method={method} path={path}: {exc}"
            ) from exc
        if not isinstance(result, dict):
            raise LocalAuthLabClientError(f"unexpected local auth lab response: {result}")
        return result
