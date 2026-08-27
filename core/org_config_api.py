from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Mapping


ORG_CONFIG_API_BASE = "https://gin-server.dicloak.net/gin/v1/organization"
ORG_CONFIG_REQUEST_TIMEOUT_SECONDS = 30
ORG_CONFIG_REQUEST_ATTEMPTS = 3


class OrgConfigRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class OrgConfigIdentity:
    org_id: str
    app_version: str

    @property
    def path(self) -> str:
        return f"/gin/v1/organization/{self.org_id}/org_config"


class OrgConfigApiClient:
    def __init__(
        self,
        cdp_driver,
        *,
        timeout_seconds: int = ORG_CONFIG_REQUEST_TIMEOUT_SECONDS,
        attempts: int = ORG_CONFIG_REQUEST_ATTEMPTS,
    ) -> None:
        self.cdp = cdp_driver
        self.timeout_seconds = int(timeout_seconds)
        self.attempts = int(attempts)
        self.logger = getattr(cdp_driver, "logger", None)

    def identity(self) -> OrgConfigIdentity:
        raw = self.cdp.evaluate(
            """
            () => {
                let state = {};
                try {
                    state = JSON.parse(localStorage.getItem("basic:state") || "{}");
                } catch (_) {}
                return {
                    has_token: Boolean(String(state.token || "").trim()),
                    org_id: String(state.userInfo && state.userInfo.orgId || "").trim(),
                    app_version: String((document.title.match(/V(\\d+\\.\\d+\\.\\d+)/) || [])[1] || "").trim(),
                };
            }
            """
        )
        if not isinstance(raw, dict):
            raise OrgConfigRequestError("APP identity query did not return an object")
        if not raw.get("has_token"):
            raise OrgConfigRequestError("current APP login token is unavailable")
        org_id = str(raw.get("org_id", "")).strip()
        app_version = str(raw.get("app_version", "")).strip()
        if not org_id:
            raise OrgConfigRequestError("current APP organization id is unavailable")
        if not app_version:
            raise OrgConfigRequestError("current APP version is unavailable")
        return OrgConfigIdentity(org_id=org_id, app_version=app_version)

    def get_org_config(self) -> dict[str, object]:
        identity = self.identity()
        payload = self._request_with_retry("GET", identity, None)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise OrgConfigRequestError("org config GET data is not an object")
        response_org_id = str(data.get("org_id", "")).strip()
        if response_org_id != identity.org_id:
            raise OrgConfigRequestError(
                "org config GET organization mismatch: "
                f"expected={identity.org_id}, actual={response_org_id}"
            )
        return data

    def post_org_config(self, payload: Mapping[str, object]) -> None:
        identity = self.identity()
        self._request_with_retry("POST", identity, dict(payload))

    def _request_with_retry(
        self,
        method: str,
        identity: OrgConfigIdentity,
        payload: dict[str, object] | None,
    ) -> dict[str, object]:
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            started = time.monotonic()
            try:
                result = self._request_once(method, identity, payload)
                response = validate_org_config_response(
                    status=result.get("status"),
                    response_body=result.get("response_body"),
                )
                self._log(
                    "info",
                    "Org config %s succeeded: attempt=%s/%s elapsed=%.2fs status=200",
                    method,
                    attempt,
                    self.attempts,
                    time.monotonic() - started,
                )
                return response
            except Exception as exc:
                last_error = exc
                self._log(
                    "warning",
                    "Org config %s failed: attempt=%s/%s elapsed=%.2fs error=%s",
                    method,
                    attempt,
                    self.attempts,
                    time.monotonic() - started,
                    exc,
                )
                if attempt < self.attempts:
                    time.sleep(attempt)
        raise OrgConfigRequestError(
            f"org config {method} failed after {self.attempts} attempts: {last_error}"
        ) from last_error

    def _request_once(
        self,
        method: str,
        identity: OrgConfigIdentity,
        payload: dict[str, object] | None,
    ) -> dict[str, object]:
        result = self.cdp.evaluate_with_args(
            """
            async ({ method, orgId, version, payload, timeoutMs, apiBase }) => {
                let state = {};
                try {
                    state = JSON.parse(localStorage.getItem("basic:state") || "{}");
                } catch (_) {}
                const token = String(state.token || "").trim();
                if (!token) return { status: 0, response_body: "", error: "missing token" };

                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), timeoutMs);
                try {
                    const headers = {
                        "Accept": "application/json, text/plain, */*",
                        "X-Version": version,
                        "X-Token": token,
                        "X-Lang": "zh_CN",
                        "X-Platform": "APP",
                    };
                    const options = { method, headers, signal: controller.signal };
                    if (method === "POST") {
                        headers["Content-Type"] = "application/json";
                        options.body = JSON.stringify(payload || {});
                    }
                    const response = await fetch(`${apiBase}/${orgId}/org_config`, options);
                    const responseBody = await response.text();
                    return {
                        status: Number(response.status || 0),
                        response_body: responseBody,
                        error: "",
                    };
                } catch (error) {
                    return {
                        status: 0,
                        response_body: "",
                        error: String(error && error.message || error || "request failed"),
                    };
                } finally {
                    clearTimeout(timer);
                }
            }
            """,
            {
                "method": method,
                "orgId": identity.org_id,
                "version": identity.app_version,
                "payload": payload,
                "timeoutMs": self.timeout_seconds * 1000,
                "apiBase": ORG_CONFIG_API_BASE,
            },
        )
        if not isinstance(result, dict):
            raise OrgConfigRequestError("org config request did not return an object")
        if result.get("error"):
            raise OrgConfigRequestError(str(result.get("error")))
        return result

    def _log(self, level: str, message: str, *args: object) -> None:
        if self.logger is not None:
            getattr(self.logger, level)(message, *args)


def parse_org_config_post_data(post_data: object) -> dict[str, object]:
    if isinstance(post_data, dict):
        return dict(post_data)
    if not isinstance(post_data, str) or not post_data.strip():
        raise OrgConfigRequestError("org config POST request body is empty")
    try:
        payload = json.loads(post_data)
    except json.JSONDecodeError as exc:
        raise OrgConfigRequestError("org config POST request body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise OrgConfigRequestError("org config POST request body is not an object")
    return payload


def validate_org_config_response(*, status: object, response_body: object) -> dict[str, object]:
    try:
        status_code = int(status)
    except (TypeError, ValueError):
        status_code = 0
    if status_code != 200:
        raise OrgConfigRequestError(f"unexpected HTTP status: {status_code}")

    if isinstance(response_body, dict):
        payload = dict(response_body)
    else:
        try:
            payload = json.loads(str(response_body or ""))
        except json.JSONDecodeError as exc:
            raise OrgConfigRequestError("org config response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise OrgConfigRequestError("org config response JSON is not an object")
    if payload.get("code") != 0:
        raise OrgConfigRequestError(
            f"org config business response failed: code={payload.get('code')!r}, msg={payload.get('msg')!r}"
        )
    return payload
