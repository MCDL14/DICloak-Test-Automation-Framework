from __future__ import annotations

import os
import plistlib
import tempfile
from copy import deepcopy
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

import yaml

from core.platform import current_platform


APP_PROFILE_ENV = "DICLOAK_APP_PROFILE_FILE"
TEST_PACKAGE_SETTINGS_PATH = Path("config/test_app_package.yaml")
TEST_ACCOUNT_GROUPS_PATH = Path("config/account_groups.test.yaml")
MACOS_APPLICATIONS_DIR = Path("/Applications")
MACOS_TEST_APP_NAMES = ("DICloak", "DICloak2")
_SETTINGS_FIELDS = frozenset({"windows_exe_path", "macos_app_name", "api_base_url", "cdp_port"})
_PRODUCTION_API_HOSTS = frozenset({"gin-server.dicloak.com", "gin-server.dicloak.net", "app.dicloak.com"})
_COPIED_PATH_MARKS = frozenset("\u200b\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff")


class AppPackageError(ValueError):
    """Safe-to-display test-package configuration error."""


def default_test_package_settings() -> dict[str, Any]:
    return {
        "windows_exe_path": "",
        "macos_app_name": "DICloak2",
        "api_base_url": "http://gin-server-test.dicloak.com",
        "cdp_port": 9223,
    }


def _api_base_url(value: str, *, test_package: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        if (
            not value
            or any(character.isspace() or ord(character) < 32 for character in value)
            or "\\" in value
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or "%" in parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or "?" in value
            or "#" in value
        ):
            raise ValueError
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
        if test_package and parsed.hostname.casefold().rstrip(".") in _PRODUCTION_API_HOSTS:
            raise AppPackageError("测试 APP 包不能使用已知生产 API 地址，请填写测试服务端根地址")
    except AppPackageError:
        raise
    except Exception:
        raise AppPackageError("API 地址必须为 HTTP(S) 根地址，不能包含账号、密码、路径、查询或片段") from None
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _normalize_copied_windows_path(value: str) -> str:
    # Explorer / rich-text copying can wrap an otherwise absolute path in
    # invisible direction marks. Remove only wrappers, preserving the filename.
    def trim_wrappers(text: str) -> str:
        start, end = 0, len(text)
        while start < end and (text[start].isspace() or text[start] in _COPIED_PATH_MARKS):
            start += 1
        while end > start and (text[end - 1].isspace() or text[end - 1] in _COPIED_PATH_MARKS):
            end -= 1
        return text[start:end]

    value = trim_wrappers(value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        value = trim_wrappers(value[1:-1])
    return value


def normalize_test_package_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(settings, Mapping) or set(settings) - _SETTINGS_FIELDS:
        raise AppPackageError("测试 APP 包配置只允许 Windows 路径、Mac 包名、API 根地址和 CDP 端口")
    result = default_test_package_settings()
    result.update(settings)
    for field in ("windows_exe_path", "macos_app_name", "api_base_url"):
        if not isinstance(result[field], str):
            raise AppPackageError("测试 APP 包路径、包名与 API 地址必须是文本")
        result[field] = result[field].strip()
    result["windows_exe_path"] = _normalize_copied_windows_path(result["windows_exe_path"])
    if result["macos_app_name"] not in MACOS_TEST_APP_NAMES:
        raise AppPackageError("Mac 测试 APP 包只能选择 DICloak 或 DICloak2")
    port = result["cdp_port"]
    if type(port) is not int or not 1 <= port <= 65535:
        raise AppPackageError("测试 APP 包 CDP 端口必须为 1 到 65535 的整数")
    if result["api_base_url"]:
        result["api_base_url"] = _api_base_url(result["api_base_url"], test_package=True)
    return result


def load_test_package_settings(path: Path | str = TEST_PACKAGE_SETTINGS_PATH) -> dict[str, Any]:
    settings_path = Path(path).expanduser()
    if not settings_path.exists():
        return default_test_package_settings()
    try:
        with settings_path.open("r", encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError):
        raise AppPackageError("测试 APP 包配置无法读取，请检查 YAML 格式及文件权限") from None
    return normalize_test_package_settings(loaded)


def save_test_package_settings(path: Path | str, settings: Mapping[str, Any]) -> None:
    normalized = normalize_test_package_settings(settings)
    settings_path = Path(path).expanduser()
    temporary: Path | None = None
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=settings_path.parent,
            prefix=".test_app_package_", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            if os.name != "nt":
                temporary.chmod(0o600)
            yaml.safe_dump(normalized, stream, allow_unicode=True, sort_keys=False)
        os.replace(temporary, settings_path)
        temporary = None
    except OSError:
        raise AppPackageError("测试 APP 包配置保存失败，请检查目录与写入权限") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def runtime_app_profile(settings: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(settings, Mapping) and "settings" in settings:
        if set(settings) != {"version", "package_kind", "settings"}:
            raise AppPackageError("测试 APP 包运行配置字段不合法")
        if type(settings["version"]) is not int or settings["version"] != 1 or settings["package_kind"] != "test":
            raise AppPackageError("测试 APP 包运行配置版本或包类型不合法")
        settings = settings["settings"]
    return {"version": 1, "package_kind": "test", "settings": normalize_test_package_settings(settings)}


def load_runtime_app_profile(path: Path | str) -> dict[str, Any]:
    try:
        with Path(path).expanduser().open("r", encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError):
        raise AppPackageError("测试 APP 包运行配置无法读取，请检查临时文件与权限") from None
    if not isinstance(loaded, Mapping) or "settings" not in loaded:
        raise AppPackageError("测试 APP 包运行配置结构不合法")
    return runtime_app_profile(loaded)


def test_package_missing_fields(settings: Mapping[str, Any], platform_name: str) -> list[str]:
    normalized = normalize_test_package_settings(settings)
    missing = []
    if platform_name == "windows" and not normalized["windows_exe_path"]:
        missing.append("Windows 测试 APP 可执行文件路径")
    if platform_name == "macos" and not normalized["macos_app_name"]:
        missing.append("Mac 测试 APP 包名")
    if not normalized["api_base_url"]:
        missing.append("测试服务端 API 根地址")
    return missing


def _macos_executable(app_name: str) -> Path:
    bundle = MACOS_APPLICATIONS_DIR / f"{app_name}.app"
    try:
        with (bundle / "Contents" / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        executable_name = info.get("CFBundleExecutable") if isinstance(info, dict) else None
        if (
            not isinstance(executable_name, str) or not executable_name.strip()
            or executable_name in {".", ".."}
            or any(character in executable_name for character in ("/", "\\", "\x00"))
        ):
            raise ValueError
        executable = bundle / "Contents" / "MacOS" / executable_name
        if not executable.is_file() or bundle.resolve() not in executable.resolve().parents:
            raise ValueError
        return executable
    except Exception:
        raise AppPackageError("无法确定所选 Mac 测试 APP 的可执行文件，请检查 /Applications 下的包及 Info.plist") from None


def apply_runtime_app_profile(
    config: dict[str, Any], profile: Mapping[str, Any], *, profile_file: Path | str = "",
    platform_name: str | None = None,
) -> dict[str, Any]:
    normalized = runtime_app_profile(profile)
    settings = normalized["settings"]
    platform_key = platform_name or current_platform()
    if platform_key not in {"windows", "macos"}:
        raise AppPackageError("测试 APP 包执行仅支持 Windows 本机和 macOS 远程")
    missing = test_package_missing_fields(settings, platform_key)
    if missing:
        raise AppPackageError("测试 APP 包缺少配置：" + "、".join(missing))
    if platform_key == "windows":
        executable = PureWindowsPath(settings["windows_exe_path"])
        if not executable.is_absolute() or not executable.name or executable.suffix.casefold() != ".exe":
            raise AppPackageError("Windows 测试 APP 必须填写 .exe 文件的绝对路径，不能回退生产路径")
    else:
        executable = _macos_executable(settings["macos_app_name"])
    paths = {
        "exe_path": str(executable), "executable_path": str(executable),
        "work_dir": str(executable.parent), "process_name": executable.name,
    }
    merged = deepcopy(config)
    for section in ("app", "platforms", "cdp", "api", "account", "test_data"):
        if section in merged and not isinstance(merged[section], dict):
            raise AppPackageError("测试 APP 运行配置节必须是对象，请检查基础配置结构")
    existing_platform = merged.get("platforms", {}).get(platform_key, {})
    if not isinstance(existing_platform, dict) or (
        "app" in existing_platform and not isinstance(existing_platform["app"], dict)
    ):
        raise AppPackageError("测试 APP 平台配置必须是对象")
    merged.setdefault("app", {}).update(paths)
    merged["app"]["isolation"] = "executable_path"
    platforms = merged.setdefault("platforms", {})
    platform = platforms.setdefault(platform_key, {})
    platform_app = platform.get("app", platform)
    platform_app.update(paths)
    platform_app["isolation"] = "executable_path"
    merged.setdefault("cdp", {}).update(host="127.0.0.1", port=settings["cdp_port"])
    merged.setdefault("api", {})["base_url"] = settings["api_base_url"]
    merged["_app_package_kind"] = "test"
    merged["_app_package_label"] = "测试 APP 包"
    merged["_app_package_settings"] = deepcopy(settings)
    if profile_file:
        merged["_app_profile_file"] = str(Path(profile_file).expanduser().resolve())
    # An APP profile alone must never silently reuse the base production login.
    if merged.get("_account_package_kind") != "test":
        account = merged.setdefault("account", {})
        account.update(username="", password="", team_name="", http_api_key="")
        data = merged.setdefault("test_data", {})
        api_data = data.setdefault("api_member_edit", {})
        if not isinstance(api_data, dict):
            raise AppPackageError("测试 APP 成员 API 配置必须是对象")
        api_data.update(token="", member_id="", external_member_id="", internal_member={
            "username": "", "password": "", "member_id": "",
        })
        data["case_external_member"] = {"name": "", "email": ""}
        merged["_test_package_account_profile_missing"] = True
    else:
        merged.pop("_test_package_account_profile_missing", None)
    return merged


def resolve_api_url(config: Mapping[str, Any] | None, default_url: str) -> str:
    cfg = config if isinstance(config, Mapping) else {}
    api = cfg.get("api", {})
    base_url = api.get("base_url", "") if isinstance(api, Mapping) else ""
    is_test = cfg.get("_app_package_kind") == "test"
    if not base_url:
        if is_test:
            raise AppPackageError("测试 APP 包缺少 API 根地址，已拒绝回退生产接口")
        return default_url
    if not isinstance(base_url, str):
        raise AppPackageError("API 根地址必须是文本")
    base = urlsplit(_api_base_url(base_url.strip(), test_package=is_test))
    target = urlsplit(default_url)
    if target.scheme not in {"http", "https"} or not target.netloc or not target.path.startswith("/gin/"):
        raise AppPackageError("APP API 请求路径不合法，已拒绝发送")
    return urlunsplit((base.scheme, base.netloc, target.path, target.query, target.fragment))
