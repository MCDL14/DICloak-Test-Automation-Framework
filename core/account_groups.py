from __future__ import annotations

import hashlib
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


ACCOUNT_GROUP_SLOTS = ("group_1", "group_2")
ACCOUNT_PROFILE_ENV = "DICLOAK_ACCOUNT_PROFILE_FILE"
DEFAULT_CASE_EXTERNAL_MEMBER_NAME = "外部成员1"
DEFAULT_CASE_EXTERNAL_MEMBER_EMAIL = "oytrhsjwe@tempmail.cn"


class AccountGroupError(Exception):
    """Raised when local account-group data is invalid."""


def default_account_groups(base_config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    groups = {
        slot: {
            "name": f"自动化账号组 {index}",
            "automation_account": {
                "username": "",
                "password": "",
                "team_name": "",
                "member_id": "",
            },
            "case_external_member": {
                "name": DEFAULT_CASE_EXTERNAL_MEMBER_NAME,
                "email": DEFAULT_CASE_EXTERNAL_MEMBER_EMAIL,
            },
            "internal_member": {
                "username": "",
                "password": "",
                "member_id": "",
            },
            "member_api_token": "",
        }
        for index, slot in enumerate(ACCOUNT_GROUP_SLOTS, start=1)
    }
    if not base_config:
        return groups

    account = _mapping(base_config.get("account"))
    test_data = _mapping(base_config.get("test_data"))
    api_data = _mapping(test_data.get("api_member_edit"))
    internal = _mapping(api_data.get("internal_member"))
    case_external = _mapping(test_data.get("case_external_member"))
    groups["group_1"] = normalize_account_group(
        {
            "name": "自动化账号组 1",
            "automation_account": {
                "username": account.get("username", ""),
                "password": account.get("password", ""),
                "team_name": account.get("team_name", ""),
                "member_id": api_data.get("external_member_id", api_data.get("member_id", "")),
            },
            "case_external_member": {
                "name": case_external.get("name", DEFAULT_CASE_EXTERNAL_MEMBER_NAME),
                "email": case_external.get("email", DEFAULT_CASE_EXTERNAL_MEMBER_EMAIL),
            },
            "internal_member": {
                "username": internal.get("username", api_data.get("internal_username", "")),
                "password": internal.get("password", api_data.get("internal_password", "")),
                "member_id": internal.get("member_id", api_data.get("internal_member_id", "")),
            },
            "member_api_token": api_data.get("token", ""),
        },
        slot="group_1",
    )
    return groups


def load_account_groups(
    path: Path | str,
    *,
    base_config: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    config_path = Path(path)
    defaults = default_account_groups(base_config)
    if not config_path.exists():
        return defaults
    try:
        with config_path.open("r", encoding="utf-8") as file_obj:
            loaded = yaml.safe_load(file_obj) or {}
    except yaml.YAMLError as exc:
        raise AccountGroupError(f"账号组 YAML 格式错误：{config_path}: {exc}") from exc
    except OSError as exc:
        raise AccountGroupError(f"账号组配置读取失败：{config_path}: {exc}") from exc

    raw_groups = loaded.get("groups", loaded)
    if not isinstance(raw_groups, dict):
        raise AccountGroupError("账号组配置的 groups 必须是对象")

    result: dict[str, dict[str, Any]] = {}
    for slot in ACCOUNT_GROUP_SLOTS:
        raw_group = raw_groups.get(slot, defaults[slot])
        if not isinstance(raw_group, dict):
            raise AccountGroupError(f"账号组 {slot} 必须是对象")
        result[slot] = normalize_account_group(raw_group, slot=slot)
    return result


def save_account_groups(path: Path | str, groups: dict[str, Any]) -> None:
    normalized = {
        slot: normalize_account_group(_mapping(groups.get(slot)), slot=slot)
        for slot in ACCOUNT_GROUP_SLOTS
    }
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with config_path.open("w", encoding="utf-8") as file_obj:
            yaml.safe_dump(
                {"version": 1, "groups": normalized},
                file_obj,
                allow_unicode=True,
                sort_keys=False,
            )
        if os.name != "nt":
            config_path.chmod(0o600)
    except OSError as exc:
        raise AccountGroupError(f"账号组配置保存失败：{config_path}: {exc}") from exc


def normalize_account_group(group: dict[str, Any], *, slot: str = "") -> dict[str, Any]:
    automation_account = _mapping(group.get("automation_account")) or _mapping(group.get("external"))
    case_external_member = (
        _mapping(group.get("case_external_member"))
        or _mapping(group.get("case_external"))
    )
    internal_member = _mapping(group.get("internal_member")) or _mapping(group.get("internal"))
    case_external_name = (
        case_external_member.get("name")
        if "name" in case_external_member
        else DEFAULT_CASE_EXTERNAL_MEMBER_NAME
    )
    case_external_email = (
        case_external_member.get("email")
        if "email" in case_external_member
        else DEFAULT_CASE_EXTERNAL_MEMBER_EMAIL
    )
    fallback_name = f"自动化账号组 {ACCOUNT_GROUP_SLOTS.index(slot) + 1}" if slot in ACCOUNT_GROUP_SLOTS else "自动化账号组"
    return {
        "name": str(group.get("name", "") or group.get("group_name", "") or fallback_name).strip() or fallback_name,
        "automation_account": {
            "username": str(automation_account.get("username", "") or "").strip(),
            "password": str(automation_account.get("password", "") or ""),
            "team_name": str(automation_account.get("team_name", "") or "").strip(),
            "member_id": str(automation_account.get("member_id", "") or "").strip(),
        },
        "case_external_member": {
            "name": str(case_external_name or "").strip(),
            "email": str(case_external_email or "").strip(),
        },
        "internal_member": {
            "username": str(internal_member.get("username", "") or "").strip(),
            "password": str(internal_member.get("password", "") or ""),
            "member_id": str(internal_member.get("member_id", "") or "").strip(),
        },
        "member_api_token": str(group.get("member_api_token", "") or "").strip(),
    }


def account_group_label(slot: str, group: dict[str, Any]) -> str:
    normalized = normalize_account_group(group, slot=slot)
    name = normalized["name"]
    team_name = normalized["automation_account"]["team_name"]
    return f"{name} ({team_name})" if team_name else name


def account_group_missing_fields(
    group: dict[str, Any],
    *,
    require_internal: bool = False,
    require_member_ids: bool = False,
    require_member_api: bool = False,
    require_case_external: bool = False,
) -> list[str]:
    normalized = normalize_account_group(group)
    automation_account = normalized["automation_account"]
    case_external_member = normalized["case_external_member"]
    internal_member = normalized["internal_member"]
    required = [
        ("自动化主账号", automation_account["username"]),
        ("自动化主账号密码", automation_account["password"]),
        ("自动化团队名称", automation_account["team_name"]),
    ]
    if require_case_external:
        required.extend(
            [
                ("用例外部成员名称", case_external_member["name"]),
                ("用例外部成员邮箱", case_external_member["email"]),
            ]
        )
    if require_internal or require_member_api:
        required.extend(
            [
                ("内部账号", internal_member["username"]),
                ("内部账号密码", internal_member["password"]),
            ]
        )
    if require_member_ids or require_member_api:
        required.extend(
            [
                ("自动化主账号成员 ID", automation_account["member_id"]),
                ("内部成员 ID", internal_member["member_id"]),
            ]
        )
    if require_member_api:
        required.extend(
            [
                ("成员 Open API token", normalized["member_api_token"]),
            ]
        )
    return [label for label, value in required if not str(value or "").strip()]


def concurrent_account_group_conflicts(
    local_group: dict[str, Any],
    remote_group: dict[str, Any],
) -> list[str]:
    local = normalize_account_group(local_group)
    remote = normalize_account_group(remote_group)
    checks = (
        (
            "自动化主账号",
            local["automation_account"]["username"],
            remote["automation_account"]["username"],
        ),
        (
            "自动化团队",
            local["automation_account"]["team_name"],
            remote["automation_account"]["team_name"],
        ),
        (
            "内部账号",
            local["internal_member"]["username"],
            remote["internal_member"]["username"],
        ),
    )
    return [
        f"{label}不能相同"
        for label, local_value, remote_value in checks
        if str(local_value or "").strip()
        and str(local_value or "").strip().casefold() == str(remote_value or "").strip().casefold()
    ]


def account_group_test_suffix(config: dict[str, Any], *, digits: int = 6) -> str:
    account = _mapping(config.get("account"))
    identity = "|".join(
        (
            str(config.get("_account_group_name", "") or "").strip(),
            str(account.get("team_name", "") or "").strip(),
            str(account.get("username", "") or "").strip(),
        )
    )
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()
    modulus = 10 ** max(1, int(digits))
    return f"{int(digest[:12], 16) % modulus:0{max(1, int(digits))}d}"


def runtime_account_profile(group: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_account_group(group)
    return {
        "version": 1,
        "group_name": normalized["name"],
        "automation_account": deepcopy(normalized["automation_account"]),
        "case_external_member": deepcopy(normalized["case_external_member"]),
        "internal_member": deepcopy(normalized["internal_member"]),
        "member_api_token": normalized["member_api_token"],
    }


def load_runtime_account_profile(path: Path | str) -> dict[str, Any]:
    profile_path = Path(path).expanduser()
    if not profile_path.exists() or not profile_path.is_file():
        raise AccountGroupError(f"运行账号配置不存在：{profile_path}")
    try:
        with profile_path.open("r", encoding="utf-8") as file_obj:
            loaded = yaml.safe_load(file_obj) or {}
    except yaml.YAMLError as exc:
        raise AccountGroupError(f"运行账号配置 YAML 格式错误：{profile_path}: {exc}") from exc
    except OSError as exc:
        raise AccountGroupError(f"运行账号配置读取失败：{profile_path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise AccountGroupError("运行账号配置必须是对象")
    return runtime_account_profile(loaded)


def apply_runtime_account_profile(
    config: dict[str, Any],
    profile: dict[str, Any],
    *,
    profile_file: Path | str = "",
) -> dict[str, Any]:
    normalized = runtime_account_profile(profile)
    automation_account = normalized["automation_account"]
    case_external_member = normalized["case_external_member"]
    internal_member = normalized["internal_member"]
    merged = deepcopy(config)

    account = _mapping(merged.get("account"))
    account.update(
        {
            "username": automation_account["username"],
            "password": automation_account["password"],
            "team_name": automation_account["team_name"],
        }
    )
    merged["account"] = account

    test_data = _mapping(merged.get("test_data"))
    api_data = _mapping(test_data.get("api_member_edit"))
    api_data.update(
        {
            "external_member_id": automation_account["member_id"],
            "token": normalized["member_api_token"],
            "internal_member": deepcopy(internal_member),
        }
    )
    test_data["api_member_edit"] = api_data
    test_data["case_external_member"] = deepcopy(case_external_member)
    merged["test_data"] = test_data
    merged["_account_group_name"] = normalized["group_name"]
    if profile_file:
        merged["_account_profile_file"] = str(Path(profile_file).expanduser().resolve())
    return merged


def case_external_member_name(config: dict[str, Any]) -> str:
    member = _mapping(_mapping(config.get("test_data")).get("case_external_member"))
    return str(member.get("name", DEFAULT_CASE_EXTERNAL_MEMBER_NAME) or DEFAULT_CASE_EXTERNAL_MEMBER_NAME).strip()


def case_external_member_email(config: dict[str, Any]) -> str:
    member = _mapping(_mapping(config.get("test_data")).get("case_external_member"))
    return str(
        member.get("email", DEFAULT_CASE_EXTERNAL_MEMBER_EMAIL)
        or DEFAULT_CASE_EXTERNAL_MEMBER_EMAIL
    ).strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
