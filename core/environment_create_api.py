from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


ENVIRONMENT_CREATE_API_URL = "https://gin-server.dicloak.com/gin/v1/env"
ENVIRONMENT_CREATE_REQUEST_TIMEOUT_SECONDS = 30
ENVIRONMENT_CREATE_REQUEST_ATTEMPTS = 3
ENVIRONMENT_CREATE_PAYLOAD_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "test_data"
    / "environment_create_api_payload.json"
)


class EnvironmentCreateRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnvironmentCreateIdentity:
    app_version: str


class EnvironmentCreateApiClient:
    """Create environments through the APP-authenticated environment API.

    The current token is read and used only inside the APP page context. It is
    never returned to Python or included in log messages.
    """

    def __init__(
        self,
        cdp_driver,
        *,
        timeout_seconds: int = ENVIRONMENT_CREATE_REQUEST_TIMEOUT_SECONDS,
        attempts: int = ENVIRONMENT_CREATE_REQUEST_ATTEMPTS,
        payload_template_path: Path | str = ENVIRONMENT_CREATE_PAYLOAD_TEMPLATE_PATH,
    ) -> None:
        self.cdp = cdp_driver
        self.timeout_seconds = _positive_int(timeout_seconds, "timeout_seconds")
        self.attempts = _positive_int(attempts, "attempts")
        self.payload_template_path = Path(payload_template_path)
        self.logger = getattr(cdp_driver, "logger", None)

    def identity(self) -> EnvironmentCreateIdentity:
        raw = self.cdp.evaluate(
            """
            () => {
                let state = {};
                try {
                    state = JSON.parse(localStorage.getItem("basic:state") || "{}");
                } catch (_) {}
                return {
                    has_token: Boolean(String(state.token || "").trim()),
                    app_version: String((document.title.match(/V(\\d+\\.\\d+\\.\\d+)/) || [])[1] || "").trim(),
                };
            }
            """
        )
        if not isinstance(raw, dict):
            raise EnvironmentCreateRequestError("APP identity query did not return an object")
        if not raw.get("has_token"):
            raise EnvironmentCreateRequestError("current APP login token is unavailable")
        app_version = str(raw.get("app_version", "")).strip()
        if not app_version:
            raise EnvironmentCreateRequestError("current APP version is unavailable")
        return EnvironmentCreateIdentity(app_version=app_version)

    def build_payload(
        self,
        *,
        name: str,
        browser_version_id: str = "142",
        remark: str | None = None,
    ) -> dict[str, object]:
        return build_environment_create_payload(
            name=name,
            browser_version_id=browser_version_id,
            remark=remark,
            template_path=self.payload_template_path,
        )

    def create_environment(
        self,
        *,
        name: str,
        browser_version_id: str = "142",
        remark: str | None = None,
    ) -> dict[str, object]:
        identity = self.identity()
        payload = self.build_payload(
            name=name,
            browser_version_id=browser_version_id,
            remark=remark,
        )
        return self._request_with_retry(identity, payload)

    def _request_with_retry(
        self,
        identity: EnvironmentCreateIdentity,
        payload: Mapping[str, object],
    ) -> dict[str, object]:
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            started = time.monotonic()
            try:
                result = self._request_once(identity, dict(payload))
                response = validate_environment_create_response(
                    status=result.get("status"),
                    response_body=result.get("response_body"),
                )
                self._log(
                    "info",
                    "Environment create API succeeded: attempt=%s/%s elapsed=%.2fs status=200",
                    attempt,
                    self.attempts,
                    time.monotonic() - started,
                )
                return response
            except Exception as exc:
                last_error = exc
                self._log(
                    "warning",
                    "Environment create API failed: attempt=%s/%s elapsed=%.2fs error=%s",
                    attempt,
                    self.attempts,
                    time.monotonic() - started,
                    exc,
                )
                if attempt < self.attempts:
                    time.sleep(attempt)
        raise EnvironmentCreateRequestError(
            f"environment create API failed after {self.attempts} attempts: {last_error}"
        ) from last_error

    def _request_once(
        self,
        identity: EnvironmentCreateIdentity,
        payload: dict[str, object],
    ) -> dict[str, object]:
        result = self.cdp.evaluate_with_args(
            """
            async ({ version, payload, timeoutMs, apiUrl }) => {
                let state = {};
                try {
                    state = JSON.parse(localStorage.getItem("basic:state") || "{}");
                } catch (_) {}
                const token = String(state.token || "").trim();
                if (!token) return { status: 0, response_body: "", error: "missing token" };

                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), timeoutMs);
                try {
                    const response = await fetch(apiUrl, {
                        method: "POST",
                        headers: {
                            "accept": "application/json, text/plain, */*",
                            "content-type": "application/json",
                            "x-lang": "zh_CN",
                            "x-platform": "APP",
                            "x-token": token,
                            "x-version": version,
                        },
                        body: JSON.stringify(payload),
                        signal: controller.signal,
                    });
                    return {
                        status: Number(response.status || 0),
                        response_body: await response.text(),
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
                "version": identity.app_version,
                "payload": payload,
                "timeoutMs": self.timeout_seconds * 1000,
                "apiUrl": ENVIRONMENT_CREATE_API_URL,
            },
        )
        if not isinstance(result, dict):
            raise EnvironmentCreateRequestError("environment create request did not return an object")
        if result.get("error"):
            raise EnvironmentCreateRequestError(str(result.get("error")))
        return result

    def _log(self, level: str, message: str, *args: object) -> None:
        if self.logger is not None:
            getattr(self.logger, level)(message, *args)


def load_environment_create_payload_template(
    template_path: Path | str = ENVIRONMENT_CREATE_PAYLOAD_TEMPLATE_PATH,
) -> dict[str, object]:
    path = Path(template_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EnvironmentCreateRequestError(
            f"environment create payload template cannot be read: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise EnvironmentCreateRequestError(
            f"environment create payload template is not valid JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise EnvironmentCreateRequestError(
            f"environment create payload template root is not an object: {path}"
        )
    return payload


def build_environment_create_payload(
    *,
    name: str,
    browser_version_id: str = "142",
    remark: str | None = None,
    template_path: Path | str = ENVIRONMENT_CREATE_PAYLOAD_TEMPLATE_PATH,
) -> dict[str, object]:
    clean_name = str(name or "").strip()
    clean_browser_version_id = str(browser_version_id or "").strip()
    if not clean_name:
        raise ValueError("environment name is empty")
    if not clean_browser_version_id:
        raise ValueError("environment browser_version_id is empty")

    payload = load_environment_create_payload_template(template_path)
    payload["browser_version_id"] = clean_browser_version_id
    payload["name"] = clean_name
    clean_remark = str(remark or "").strip()
    if clean_remark:
        payload["remark"] = clean_remark
    else:
        payload.pop("remark", None)
    return payload


def validate_environment_create_response(
    *,
    status: object,
    response_body: object,
) -> dict[str, object]:
    try:
        status_code = int(status)
    except (TypeError, ValueError):
        status_code = 0
    if status_code != 200:
        raise EnvironmentCreateRequestError(f"unexpected HTTP status: {status_code}")

    if isinstance(response_body, dict):
        payload = dict(response_body)
    else:
        try:
            payload = json.loads(str(response_body or ""))
        except json.JSONDecodeError as exc:
            raise EnvironmentCreateRequestError(
                "environment create response is not valid JSON"
            ) from exc
    if not isinstance(payload, dict):
        raise EnvironmentCreateRequestError(
            "environment create response JSON is not an object"
        )
    if payload.get("code") != 0:
        raise EnvironmentCreateRequestError(
            "environment create business response failed: "
            f"code={payload.get('code')!r}, msg={payload.get('msg')!r}"
        )
    return payload


def _positive_int(value: object, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return parsed
