from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


ENVIRONMENT_CREATE_API_URL = "https://gin-server.dicloak.com/gin/v1/env"
ENVIRONMENT_BATCH_DELETE_API_URL = "https://gin-server.dicloak.com/gin/v1/env/batch"
ENVIRONMENT_LIST_API_URL = "https://gin-server.dicloak.com/gin/v1/env/list"
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
    """Create, list, and delete environments through the APP-authenticated API.

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
        device_id: str | None = None,
    ) -> None:
        self.cdp = cdp_driver
        self.timeout_seconds = _positive_int(timeout_seconds, "timeout_seconds")
        self.attempts = _positive_int(attempts, "attempts")
        self.payload_template_path = Path(payload_template_path)
        self.device_id = str(device_id or "").strip()
        self.logger = getattr(cdp_driver, "logger", None)
        self.last_created_environment_id = ""
        self.created_environment_ids: list[str] = []

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
        response = self._request_with_retry(
            method="POST",
            api_url=ENVIRONMENT_CREATE_API_URL,
            operation="create",
            identity=identity,
            payload=payload,
        )
        environment_id = environment_id_from_create_response(response)
        self.last_created_environment_id = environment_id
        if environment_id not in self.created_environment_ids:
            self.created_environment_ids.append(environment_id)
        return response

    def delete_environments(
        self,
        environment_ids: Iterable[str] | str,
    ) -> dict[str, object]:
        payload = build_environment_delete_payload(environment_ids)
        identity = self.identity()
        response = self._request_with_retry(
            method="DELETE",
            api_url=ENVIRONMENT_BATCH_DELETE_API_URL,
            operation="batch delete",
            identity=identity,
            payload=payload,
        )
        deleted_ids = set(payload["ids"])
        self.created_environment_ids = [
            environment_id
            for environment_id in self.created_environment_ids
            if environment_id not in deleted_ids
        ]
        if self.last_created_environment_id in deleted_ids:
            self.last_created_environment_id = ""
        return response

    def list_environments(
        self,
        *,
        page_size: int = 10,
        page_no: int = 1,
        env_tag_list_type: str = "CONTAIN",
        order_by: str = "ENV_SERIAL_NUM",
        sort: str = "DESC",
        detail: bool = True,
        value: str | None = None,
    ) -> dict[str, object]:
        payload = build_environment_list_payload(
            page_size=page_size,
            page_no=page_no,
            env_tag_list_type=env_tag_list_type,
            order_by=order_by,
            sort=sort,
            detail=detail,
            value=value,
        )
        identity = self.identity()
        return self._request_with_retry(
            method="POST",
            api_url=ENVIRONMENT_LIST_API_URL,
            operation="list",
            identity=identity,
            payload=payload,
        )

    def environment_ids_by_name(
        self,
        name: str,
        *,
        page_size: int = 100,
    ) -> list[str]:
        clean_name = _non_empty_string(name, "environment list name")
        response = self.list_environments(
            page_size=page_size,
            page_no=1,
            value=clean_name,
        )
        environment_ids: list[str] = []
        for record in environment_records_from_list_response(response):
            record_name = _first_mapping_value(
                record,
                ("name", "env_name", "environment_name"),
            )
            if record_name != clean_name:
                continue
            environment_id = _first_mapping_value(
                record,
                ("id", "env_id", "environment_id"),
            )
            if environment_id and environment_id not in environment_ids:
                environment_ids.append(environment_id)
        return environment_ids

    def _request_with_retry(
        self,
        *,
        method: str,
        api_url: str,
        operation: str,
        identity: EnvironmentCreateIdentity,
        payload: Mapping[str, object],
    ) -> dict[str, object]:
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            started = time.monotonic()
            try:
                result = self._request_once(
                    method=method,
                    api_url=api_url,
                    identity=identity,
                    payload=dict(payload),
                )
                response = validate_environment_api_response(
                    status=result.get("status"),
                    response_body=result.get("response_body"),
                    operation=operation,
                )
                self._log(
                    "info",
                    "Environment %s API succeeded: attempt=%s/%s elapsed=%.2fs status=200",
                    operation,
                    attempt,
                    self.attempts,
                    time.monotonic() - started,
                )
                return response
            except Exception as exc:
                last_error = exc
                self._log(
                    "warning",
                    "Environment %s API failed: attempt=%s/%s elapsed=%.2fs error=%s",
                    operation,
                    attempt,
                    self.attempts,
                    time.monotonic() - started,
                    exc,
                )
                if attempt < self.attempts:
                    time.sleep(attempt)
        raise EnvironmentCreateRequestError(
            f"environment {operation} API failed after {self.attempts} attempts: {last_error}"
        ) from last_error

    def _request_once(
        self,
        *,
        method: str,
        api_url: str,
        identity: EnvironmentCreateIdentity,
        payload: dict[str, object],
    ) -> dict[str, object]:
        result = self.cdp.evaluate_with_args(
            """
            async ({ method, version, deviceId, payload, timeoutMs, apiUrl }) => {
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
                        "accept": "application/json, text/plain, */*",
                        "content-type": "application/json",
                        "x-lang": "zh_CN",
                        "x-platform": "APP",
                        "x-token": token,
                        "x-version": version,
                    };
                    if (deviceId) headers["x-device-id"] = deviceId;
                    const response = await fetch(apiUrl, {
                        method,
                        headers,
                        body: JSON.stringify(payload),
                        signal: controller.signal,
                        mode: "cors",
                        credentials: "omit",
                        referrerPolicy: "strict-origin-when-cross-origin",
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
                "method": method,
                "version": identity.app_version,
                "deviceId": self.device_id,
                "payload": payload,
                "timeoutMs": self.timeout_seconds * 1000,
                "apiUrl": api_url,
            },
        )
        if not isinstance(result, dict):
            raise EnvironmentCreateRequestError("environment API request did not return an object")
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


def build_environment_delete_payload(
    environment_ids: Iterable[str] | str,
) -> dict[str, list[str]]:
    raw_ids = (
        [environment_ids]
        if isinstance(environment_ids, str)
        else list(environment_ids)
    )
    if not raw_ids:
        raise ValueError("environment ids are empty")

    normalized_ids: list[str] = []
    for value in raw_ids:
        environment_id = str(value or "").strip()
        if not environment_id:
            raise ValueError("environment id is empty")
        if environment_id not in normalized_ids:
            normalized_ids.append(environment_id)
    return {"ids": normalized_ids}


def build_environment_list_payload(
    *,
    page_size: int = 10,
    page_no: int = 1,
    env_tag_list_type: str = "CONTAIN",
    order_by: str = "ENV_SERIAL_NUM",
    sort: str = "DESC",
    detail: bool = True,
    value: str | None = None,
) -> dict[str, object]:
    if not isinstance(detail, bool):
        raise ValueError("environment list detail must be a boolean")
    payload: dict[str, object] = {
        "page_size": _positive_int(page_size, "environment list page_size"),
        "page_no": _positive_int(page_no, "environment list page_no"),
        "env_tag_list_type": _non_empty_string(
            env_tag_list_type,
            "environment list env_tag_list_type",
        ),
        "order_by": _non_empty_string(order_by, "environment list order_by"),
        "sort": _non_empty_string(sort, "environment list sort"),
        "detail": detail,
    }
    clean_value = str(value or "").strip()
    if clean_value:
        payload["value"] = clean_value
    return payload


def environment_id_from_create_response(response: Mapping[str, object]) -> str:
    data = response.get("data")
    if not isinstance(data, dict):
        raise EnvironmentCreateRequestError(
            "environment create response data is not an object"
        )
    environment_id = str(data.get("id") or "").strip()
    if not environment_id:
        raise EnvironmentCreateRequestError(
            "environment create response data.id is unavailable"
        )
    return environment_id


def environment_records_from_list_response(
    response: Mapping[str, object],
) -> list[dict[str, object]]:
    data = response.get("data")
    if isinstance(data, list):
        raw_records = data
    elif isinstance(data, dict):
        raw_records = None
        for key in ("list", "records", "items", "rows"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                raw_records = candidate
                break
        if raw_records is None:
            list_values = [value for value in data.values() if isinstance(value, list)]
            if len(list_values) == 1:
                raw_records = list_values[0]
        if raw_records is None:
            raise EnvironmentCreateRequestError(
                "environment list response data does not contain a record list: "
                f"keys={sorted(str(key) for key in data)}"
            )
    else:
        raise EnvironmentCreateRequestError(
            "environment list response data is not an object or list"
        )
    return [dict(record) for record in raw_records if isinstance(record, dict)]


def validate_environment_create_response(
    *,
    status: object,
    response_body: object,
) -> dict[str, object]:
    return validate_environment_api_response(
        status=status,
        response_body=response_body,
        operation="create",
    )


def validate_environment_delete_response(
    *,
    status: object,
    response_body: object,
) -> dict[str, object]:
    return validate_environment_api_response(
        status=status,
        response_body=response_body,
        operation="batch delete",
    )


def validate_environment_list_response(
    *,
    status: object,
    response_body: object,
) -> dict[str, object]:
    return validate_environment_api_response(
        status=status,
        response_body=response_body,
        operation="list",
    )


def validate_environment_api_response(
    *,
    status: object,
    response_body: object,
    operation: str,
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
                f"environment {operation} response is not valid JSON"
            ) from exc
    if not isinstance(payload, dict):
        raise EnvironmentCreateRequestError(
            f"environment {operation} response JSON is not an object"
        )
    if payload.get("code") != 0:
        raise EnvironmentCreateRequestError(
            f"environment {operation} business response failed: "
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


def _non_empty_string(value: object, label: str) -> str:
    parsed = str(value or "").strip()
    if not parsed:
        raise ValueError(f"{label} is empty")
    return parsed


def _first_mapping_value(
    mapping: Mapping[str, object],
    keys: tuple[str, ...],
) -> str:
    for key in keys:
        value = str(mapping.get(key) or "").strip()
        if value:
            return value
    return ""
