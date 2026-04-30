from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when the automation config cannot be loaded or validated."""


DEFAULT_CONFIG: dict[str, Any] = {
    "app": {
        "exe_path": "",
        "work_dir": "",
        "startup_args": [
            "--remote-debugging-port=9222",
            "--remote-allow-origins=*",
        ],
        "process_name": "DICloak.exe",
        "close_existing_before_start": True,
        "process_check_timeout": 30,
        "startup_timeout": 60,
        "shutdown_timeout": 20,
    },
    "cdp": {
        "host": "127.0.0.1",
        "port": 9222,
        "driver": "playwright",
        "fallback_driver": "websocket",
        "connect_timeout": 30,
        "default_page_url_keyword": "",
    },
    "account": {
        "username": "",
        "password": "",
        "team_name": "",
        "team_switch_timeout": 20,
    },
    "feishu": {
        "enabled": True,
        "webhook_url": "",
        "at_open_id": "",
        "at_name": "",
        "notify_on_success": False,
        "notify_on_failure": True,
        "timeout": 10,
    },
    "report": {"enabled": False, "html_file": "test_report.html", "port": 9091},
    "timeouts": {
        "element_seconds": 10,
        "script_element_seconds": 10,
        "request_seconds": 30,
        "page_seconds": 10,
        "login_marker_seconds": 3,
        "search_result_seconds": 10,
        "settings_cache_dir_seconds": 15,
        "environment_open_seconds": 90,
        "environment_close_seconds": 90,
        "kernel_process_seconds": 90,
        "kernel_cdp_seconds": 30,
        "kernel_cdp_probe_seconds": 3,
        "http_probe_seconds": 2,
        "kernel_download_seconds": 300,
        "batch_import_seconds": 120,
    },
    "test_data": {
        "environment_name_prefix": "auto_env",
        "kernel_142_environment_name": "",
        "kernel_134_environment_name": "",
        "kernel_integrity": {
            "environment_name": "142内核环境-4",
            "fallback_search_keyword": "142",
            "browser_process_name": "GinsBrowser.exe",
            "kernel_process_name": "GinsBrowser",
            "expected_kernel_prefix": "142",
            "expected_134_kernel_prefix": "134",
            "kernel_134_search_keyword": "134内核",
            "kernel_134_download_major": "134",
            "cache_subdir_name": "browsers",
        },
        "environment_create_default": {
            "environment_name": "自动化-创建环境",
        },
        "environment_create_134_kernel": {
            "environment_name": "自动化-创建134内核环境",
            "kernel_label": "ChromeBrowser 134",
            "expected_kernel_prefix": "134",
        },
        "environment_edit_name": {
            "temporary_name": "自动化-编辑环境名称",
        },
        "environment_quick_edit_name": {
            "temporary_name": "自动化-列表快捷修改环境名称",
        },
        "environment_edit_fixed_open_url": {
            "environment_name": "自动化编辑打开网址",
            "fixed_url": "https://bilibili.com",
            "url_keyword": "bilibili.com",
        },
        "environment_filter_group": {
            "group_name": "自动化分组",
        },
        "environment_filter_remark": {
            "remark_keyword": "备注UI自动化",
        },
        "environment_batch_create": {
            "environment_name_prefix": "自动化-批量创建环境",
            "create_count": 5,
        },
        "environment_batch_create_134_kernel": {
            "environment_name_prefix": "自动化-批量创建134内核环境",
            "create_count": 3,
            "kernel_label": "ChromeBrowser 134",
            "expected_kernel_prefix": "134",
        },
        "bookmark": {
            "storage_dir": "",
            "overwrite_file_name": "",
            "append_file_name": "",
            "overwrite_rows": [],
            "append_rows": [],
        },
        "member_export": {
            "expected_file_full_path": "",
            "export_dir": "",
            "export_file_name": "",
            "export_file_regex": r"^导出成员列表 - \d{12}\.xlsx$",
        },
        "batch_import": {"file_dir": "", "file_name": ""},
        "batch_export": {"export_dir": "", "export_file_name": ""},
        "packet_capture": {
            "process_name": "",
            "startup_path": "",
        },
        "local_extension": {"package_name": "", "package_path": ""},
    },
    "run": {
        "case_level": "P0",
        "default_parallel": False,
        "enable_launcher_ui": False,
        "retry_times": 1,
        "retry_interval_seconds": 3,
        "precheck_before_run": True,
        "stop_on_login_failed": True,
        "screenshot_on_failure": True,
        "collect_log_on_failure": True,
    },
    "log": {"level": "INFO", "dir": "logs", "keep_days": 14},
}


REQUIRED_SECTIONS = (
    "app",
    "cdp",
    "account",
    "feishu",
    "timeouts",
    "test_data",
    "run",
    "log",
)


def load_config(path: Path) -> dict[str, Any]:
    config_path = path.expanduser()
    if not config_path.exists():
        raise ConfigError(f"config file does not exist: {config_path}")
    if not config_path.is_file():
        raise ConfigError(f"config path is not a file: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as file_obj:
            loaded = yaml.safe_load(file_obj) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read config file {config_path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ConfigError("config root must be a YAML mapping")

    validate_required_sections(loaded)
    merged = deep_merge(DEFAULT_CONFIG, loaded)
    validate_config(merged)
    merged["_config_file"] = str(config_path.resolve())
    merged["_project_root"] = str(Path.cwd().resolve())
    return merged


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def validate_config(config: dict[str, Any]) -> None:
    if not isinstance(config["app"].get("startup_args"), list):
        raise ConfigError("app.startup_args must be a list")

    cdp_port = config["cdp"].get("port")
    if not isinstance(cdp_port, int) or not 1 <= cdp_port <= 65535:
        raise ConfigError("cdp.port must be an integer between 1 and 65535")

    process_timeout = config["app"].get("process_check_timeout")
    if not isinstance(process_timeout, int) or process_timeout <= 0:
        raise ConfigError("app.process_check_timeout must be a positive integer")

    team_switch_timeout = config["account"].get("team_switch_timeout")
    if not isinstance(team_switch_timeout, int) or team_switch_timeout <= 0:
        raise ConfigError("account.team_switch_timeout must be a positive integer")

    for key, value in config.get("timeouts", {}).items():
        if not isinstance(value, int) or value <= 0:
            raise ConfigError(f"timeouts.{key} must be a positive integer")

    bookmark = config["test_data"]["bookmark"]
    if not isinstance(bookmark.get("overwrite_rows", []), list):
        raise ConfigError("test_data.bookmark.overwrite_rows must be a list")
    if not isinstance(bookmark.get("append_rows", []), list):
        raise ConfigError("test_data.bookmark.append_rows must be a list")


def validate_required_sections(config: dict[str, Any]) -> None:
    missing_sections = [section for section in REQUIRED_SECTIONS if section not in config]
    if missing_sections:
        raise ConfigError(f"missing required config section(s): {', '.join(missing_sections)}")


def get_value(config: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    current: Any = config
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def require_value(config: dict[str, Any], dotted_key: str) -> Any:
    value = get_value(config, dotted_key)
    if value in (None, ""):
        raise ConfigError(f"missing required config value: {dotted_key}")
    return value


def timeout_seconds(config: dict[str, Any], key: str, default: int) -> int:
    value = get_value(config, f"timeouts.{key}", default)
    if not isinstance(value, int) or value <= 0:
        return default
    return value


def timeout_ms(config: dict[str, Any], key: str, default_seconds: int) -> int:
    return timeout_seconds(config, key, default_seconds) * 1000


def build_path(*parts: str | Path | None) -> Path:
    clean_parts = [str(part) for part in parts if part not in (None, "")]
    if not clean_parts:
        return Path("")
    return Path(clean_parts[0]).joinpath(*clean_parts[1:])
