from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Mapping

from core.global_settings_baseline import ORG_CONFIG_COMPARE_BLOCKS


@dataclass(frozen=True)
class OrgConfigDiff:
    path: str
    expected: object
    actual: object

    def summary(self) -> str:
        return f"{self.path} expected={self.expected!r} actual={self.actual!r}"


_ORDER_INSENSITIVE_PATHS = frozenset(
    {
        "bookmark_config.env_group_ids",
        "env_data_sync.role_ids",
        "proxy_detect_config.member_group_list",
        "access_limit.member_mroup_list",
        "access_limit.quick_selection_option",
        "env_title_config.member_group_list",
    }
)
_OPTIONAL_GET_PATHS = frozenset(
    {
        "bookmark_config.file_name",
        "access_limit.quick_selection_option",
        "local_data_config.browser_type",
    }
)


def semantic_org_config_diff(
    expected: Mapping[str, object],
    actual: Mapping[str, object],
    *,
    blocks: Iterable[str] = ORG_CONFIG_COMPARE_BLOCKS,
    bit_masks: Mapping[str, int] | None = None,
) -> list[OrgConfigDiff]:
    masks = dict(bit_masks or {})
    diffs: list[OrgConfigDiff] = []
    for block in blocks:
        if block not in expected:
            continue
        expected_block = expected.get(block)
        actual_block = actual.get(block)
        if not isinstance(expected_block, Mapping):
            _compare_value(block, expected_block, actual_block, diffs)
            continue
        if not isinstance(actual_block, Mapping):
            diffs.append(OrgConfigDiff(block, dict(expected_block), actual_block))
            continue
        _compare_block(
            block,
            expected_block,
            actual_block,
            diffs,
            bit_mask=masks.get(f"{block}.type", masks.get(block)),
        )
    return diffs


def format_org_config_diffs(diffs: Iterable[OrgConfigDiff], limit: int = 12) -> str:
    items = list(diffs)
    rendered = "; ".join(diff.summary() for diff in items[:limit])
    if len(items) > limit:
        rendered += f"; ... and {len(items) - limit} more"
    return rendered


def merge_masked_value(current: int, baseline: int, mask: int) -> int:
    return (int(current) & ~int(mask)) | (int(baseline) & int(mask))


def _compare_block(
    block: str,
    expected: Mapping[str, object],
    actual: Mapping[str, object],
    diffs: list[OrgConfigDiff],
    *,
    bit_mask: int | None,
) -> None:
    if block in {"browser_config", "data_sync_config"}:
        _compare_type(block, expected, actual, diffs, bit_mask=bit_mask)
        if block == "data_sync_config" or bit_mask is not None:
            return
        for key, expected_value in expected.items():
            if key != "type":
                _compare_path(block, key, expected_value, actual, diffs)
        return

    if block == "local_data_config":
        expected_type = expected.get("type")
        _compare_path(block, "type", expected_type, actual, diffs)
        if expected_type == 0:
            return
        for key, expected_value in expected.items():
            if key != "type":
                _compare_path(block, key, expected_value, actual, diffs)
        return

    if "status" in expected:
        expected_status = bool(expected.get("status"))
        actual_status = actual.get("status")
        if actual_status is None or bool(actual_status) != expected_status:
            diffs.append(OrgConfigDiff(f"{block}.status", expected_status, actual_status))
            return
        if not expected_status:
            return

    for key, expected_value in expected.items():
        if key == "status":
            continue
        _compare_path(block, key, expected_value, actual, diffs)


def _compare_type(
    block: str,
    expected: Mapping[str, object],
    actual: Mapping[str, object],
    diffs: list[OrgConfigDiff],
    *,
    bit_mask: int | None,
) -> None:
    expected_value = expected.get("type")
    actual_value = actual.get("type")
    path = f"{block}.type"
    if not isinstance(expected_value, int) or not isinstance(actual_value, int):
        _compare_value(path, expected_value, actual_value, diffs)
        return
    if bit_mask is None:
        if expected_value != actual_value:
            diffs.append(OrgConfigDiff(path, expected_value, actual_value))
        return
    expected_masked = expected_value & bit_mask
    actual_masked = actual_value & bit_mask
    if expected_masked != actual_masked:
        diffs.append(OrgConfigDiff(f"{path}&{bit_mask}", expected_masked, actual_masked))


def _compare_path(
    block: str,
    key: str,
    expected_value: object,
    actual: Mapping[str, object],
    diffs: list[OrgConfigDiff],
) -> None:
    path = f"{block}.{key}"
    if key not in actual and path in _OPTIONAL_GET_PATHS:
        return
    actual_value = actual.get(key)
    if path == "env_title_config.env_title":
        expected_value = _parse_json_value(expected_value)
        actual_value = _parse_json_value(actual_value)
    if path in _ORDER_INSENSITIVE_PATHS:
        expected_value = _normalized_collection(expected_value)
        actual_value = _normalized_collection(actual_value)
    _compare_value(path, expected_value, actual_value, diffs)


def _compare_value(
    path: str,
    expected: object,
    actual: object,
    diffs: list[OrgConfigDiff],
) -> None:
    if expected != actual:
        diffs.append(OrgConfigDiff(path, expected, actual))


def _normalized_collection(value: object) -> object:
    if not isinstance(value, list):
        return value
    return sorted((json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value))


def _parse_json_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
