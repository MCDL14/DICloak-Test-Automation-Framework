from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from core.config import timeout_seconds


API_TOKEN_ENV = "DICLOAK_API_MEMBER_EDIT_TOKEN"
API_MEMBER_ID_ENV = "DICLOAK_API_MEMBER_EDIT_MEMBER_ID"
DEFAULT_BASE_URL = "https://app.dicloak.com/gin/v1/api/member/open/edit?"
DEFAULT_MEMBER_ID = "1917463861065080834"
DEFAULT_EXTERNAL_MEMBER_ID = DEFAULT_MEMBER_ID
DEFAULT_INTERNAL_MEMBER_ID = "1947196562844110850"
DEFAULT_INTERNAL_USERNAME = "MCDL007"
DEFAULT_INTERNAL_PASSWORD = "M12345678"
DEFAULT_DISABLED_LOGIN_MESSAGE = "该账号已被停用。您可以联系原团队的管理员处理，或自行注册新账号"
DEFAULT_DISUSE_TIME = "2026-1-31 12:00:00"
DEFAULT_TIME_ZONE = "Etc/GMT-8"
DEFAULT_STATUS_RETRY_TIMES = 3
DEFAULT_STATUS_RETRY_INTERVAL_SECONDS = 1
API_MEMBER_EDIT_DATA_KEY = "api_member_edit"


@dataclass(frozen=True)
class MemberEditApiConfig:
    base_url: str
    token: str
    member_id: str
    status_retry_times: int = DEFAULT_STATUS_RETRY_TIMES
    status_retry_interval_seconds: int = DEFAULT_STATUS_RETRY_INTERVAL_SECONDS


class MemberEditApiClient:
    def __init__(self, config: dict):
        self.config = config
        self.api_config = self._load_api_config()

    def edit_member(self, member_id: str | None = None, **params) -> dict:
        timeout = timeout_seconds(self.config, "request_seconds", 30)
        target_member_id = str(member_id or self.api_config.member_id).strip()
        if not target_member_id:
            raise AssertionError("member edit api member_id is empty")
        query_params = {
            "token": self.api_config.token,
            "member_id": target_member_id,
            **params,
        }
        url = self._build_url(query_params)
        response = self._get_with_status_retry(url, timeout=timeout)
        try:
            body = response.json()
        except ValueError as exc:
            raise AssertionError(f"member edit api did not return json: status={response.status_code}") from exc
        return {
            "status_code": response.status_code,
            "json": body,
            "member_id": target_member_id,
            "params": {key: str(value) for key, value in params.items()},
        }

    def _load_api_config(self) -> MemberEditApiConfig:
        data = api_member_edit_data(self.config)
        base_url = str(data.get("base_url") or DEFAULT_BASE_URL).strip()
        token = str(os.environ.get(API_TOKEN_ENV) or data.get("token") or "").strip()
        member_id = str(
            os.environ.get(API_MEMBER_ID_ENV)
            or data.get("external_member_id")
            or data.get("member_id")
            or DEFAULT_EXTERNAL_MEMBER_ID
        ).strip()
        status_retry = _nested_mapping(data, "status_retry")
        status_retry_times = self._positive_int(
            status_retry.get("times", data.get("status_retry_times")),
            DEFAULT_STATUS_RETRY_TIMES,
        )
        status_retry_interval_seconds = self._positive_int(
            status_retry.get("interval_seconds", data.get("status_retry_interval_seconds")),
            DEFAULT_STATUS_RETRY_INTERVAL_SECONDS,
        )
        if not base_url:
            raise AssertionError("member edit api base_url is empty")
        if not token:
            raise AssertionError(
                f"member edit api token is empty; set {API_TOKEN_ENV} or config/test_data.yaml test_data.api_member_edit.token"
            )
        if not member_id:
            raise AssertionError(
                f"member edit api member_id is empty; set {API_MEMBER_ID_ENV} or config/test_data.yaml test_data.api_member_edit.member_id"
            )
        return MemberEditApiConfig(
            base_url=base_url,
            token=token,
            member_id=member_id,
            status_retry_times=status_retry_times,
            status_retry_interval_seconds=status_retry_interval_seconds,
        )

    def _build_url(self, params: dict) -> str:
        separator = "" if self.api_config.base_url.endswith("?") else (
            "&" if "?" in self.api_config.base_url else "?"
        )
        return f"{self.api_config.base_url}{separator}{urlencode(params)}"

    def _get_with_status_retry(self, url: str, timeout: int):
        max_attempts = self.api_config.status_retry_times + 1
        response = None
        last_error: requests.RequestException | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.get(url, timeout=timeout)
            except requests.RequestException as exc:
                last_error = exc
                if attempt < max_attempts:
                    time.sleep(self.api_config.status_retry_interval_seconds)
                    continue
                raise
            if response.status_code == 200:
                return response
            if attempt < max_attempts:
                time.sleep(self.api_config.status_retry_interval_seconds)
        if response is None and last_error is not None:
            raise last_error
        return response

    @staticmethod
    def _positive_int(value, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed >= 0 else default


def api_member_edit_data(config: dict) -> dict:
    data = config.get("test_data", {}).get(API_MEMBER_EDIT_DATA_KEY, {})
    return data if isinstance(data, dict) else {}


def _nested_mapping(data: dict, key: str) -> dict:
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def api_member_edit_value(config: dict, key: str, default: str) -> str:
    value = api_member_edit_data(config).get(key, default)
    return str(value if value is not None else default).strip()


def external_member_id(config: dict) -> str:
    return api_member_edit_value(config, "external_member_id", DEFAULT_EXTERNAL_MEMBER_ID)


def internal_member_id(config: dict) -> str:
    data = api_member_edit_data(config)
    value = _nested_mapping(data, "internal_member").get("member_id", data.get("internal_member_id", DEFAULT_INTERNAL_MEMBER_ID))
    return str(value if value is not None else DEFAULT_INTERNAL_MEMBER_ID).strip()


def internal_member_username(config: dict) -> str:
    data = api_member_edit_data(config)
    value = _nested_mapping(data, "internal_member").get("username", data.get("internal_username", DEFAULT_INTERNAL_USERNAME))
    return str(value if value is not None else DEFAULT_INTERNAL_USERNAME).strip()


def internal_member_password(config: dict) -> str:
    data = api_member_edit_data(config)
    value = _nested_mapping(data, "internal_member").get("password", data.get("internal_password", DEFAULT_INTERNAL_PASSWORD))
    return str(value if value is not None else DEFAULT_INTERNAL_PASSWORD)


def disabled_login_message(config: dict) -> str:
    return api_member_edit_value(config, "disabled_login_message", DEFAULT_DISABLED_LOGIN_MESSAGE)


def disuse_time(config: dict) -> str:
    data = api_member_edit_data(config)
    value = _nested_mapping(data, "disuse").get("time", data.get("disuse_time", DEFAULT_DISUSE_TIME))
    return str(value if value is not None else DEFAULT_DISUSE_TIME).strip()


def time_zone(config: dict) -> str:
    data = api_member_edit_data(config)
    value = _nested_mapping(data, "disuse").get("time_zone", data.get("time_zone", DEFAULT_TIME_ZONE))
    return str(value if value is not None else DEFAULT_TIME_ZONE).strip()
