from __future__ import annotations

import copy
import json
from pathlib import Path


ORG_CONFIG_BASELINE_PATH = Path("test_data/global_settings/org_config_baseline.json")
ORG_CONFIG_EXPECTED_BLOCKS = frozenset(
    {
        "data_sync_config",
        "browser_config",
        "bookmark_config",
        "env_config",
        "access_limit",
        "proxy_detect_config",
        "app_version_limit_config",
        "local_data_config",
        "env_title_config",
        "browser_show_rule_config",
        "update_frequency_config",
        "env_data_sync",
        "env_sort_config",
        "env_page_config",
        "member_ip_limit_config",
        "device_name_limit_config",
        "proxy_limit_config",
        "my_org_config",
        "cookie_encrypt_config",
        "local_network_config",
        "env_open_limit_config",
    }
)
ORG_CONFIG_COMPARE_BLOCKS = (
    "browser_config",
    "data_sync_config",
    "bookmark_config",
    "env_data_sync",
    "proxy_detect_config",
    "access_limit",
    "local_data_config",
    "env_page_config",
    "env_sort_config",
    "env_title_config",
)
ORG_CONFIG_READ_ONLY_BLOCKS = frozenset(
    {
        "org_id",
        "personal_config",
        "debug_mode",
        "del_package",
        "role_id",
        "white_list",
    }
)


GLOBAL_SETTINGS_UI_SNAPSHOT_BASELINE: dict[str, object] = {
    "schema_version": 2,
    "simple_checkboxes": {
        "禁止查看网站密码": True,
        "禁止打开浏览器开发者工具": False,
        "禁止管理/移除扩展，以及从本地安装扩展至浏览器": False,
        "禁止成员访问谷歌扩展商店和扩展设置页面": False,
    },
    "website_restriction": {"enabled": False},
    "packet_capture_blocking": {"enabled": False},
    "bookmark_setting": {
        "enabled": False,
        "restore_supported": True,
    },
    "environment_field_display_limit": {"enabled": False},
    "environment_list_pagination": {"enabled": False},
    "environment_list_sort": {"enabled": False},
    "data_sync": {
        "cookie": True,
        "local_storage": True,
        "indexeddb": True,
        "one_way_enabled": False,
        "whitelist_groups": [],
    },
    "clear_local_cache": {"clear_method": "不清除"},
    "extension_tamper_protection": {"enabled": False},
    "proxy_check_failure_block_open": {"enabled": False},
    "country_mismatch_block_open": {"enabled": False},
}


def current_global_settings_ui_baseline() -> dict[str, object]:
    return copy.deepcopy(GLOBAL_SETTINGS_UI_SNAPSHOT_BASELINE)


def load_org_config_baseline(path: Path | str = ORG_CONFIG_BASELINE_PATH) -> dict[str, object]:
    baseline_path = Path(path)
    with baseline_path.open("r", encoding="utf-8") as file_obj:
        baseline = json.load(file_obj)
    if not isinstance(baseline, dict):
        raise TypeError(f"org config baseline must be an object: {type(baseline)!r}")

    actual_blocks = set(baseline)
    missing = sorted(ORG_CONFIG_EXPECTED_BLOCKS - actual_blocks)
    unexpected = sorted(actual_blocks - ORG_CONFIG_EXPECTED_BLOCKS)
    if missing or unexpected:
        raise ValueError(
            "org config baseline schema mismatch: "
            f"missing={missing}, unexpected={unexpected}"
        )
    forbidden = sorted(actual_blocks & ORG_CONFIG_READ_ONLY_BLOCKS)
    if forbidden:
        raise ValueError(f"org config baseline contains read-only blocks: {forbidden}")
    return copy.deepcopy(baseline)
