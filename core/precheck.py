from __future__ import annotations

import logging
import ipaddress
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.app_config import resolve_app_config
from core.app_cdp_auth import (
    AppCdpAuthError,
    auth_enabled,
    normalized_app_startup_args,
    redact_app_startup_args,
    validate_cdp_auth_setup,
)
from core.files import batch_import_file, local_extension_file, member_export_file_regex


@dataclass
class PrecheckItem:
    name: str
    passed: bool
    message: str = ""


@dataclass
class PrecheckResult:
    items: list[PrecheckItem] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.items)

    @property
    def failed_items(self) -> list[PrecheckItem]:
        return [item for item in self.items if not item.passed]

    def add(self, name: str, passed: bool, message: str = "") -> None:
        self.items.append(PrecheckItem(name, passed, message))


class EnvironmentPrechecker:
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger

    def run(self, *, attach_existing_app: bool = False) -> PrecheckResult:
        result = PrecheckResult()
        self._check_python(result)
        self._check_app(result, attach_existing_app=attach_existing_app)
        self._check_test_data(result)
        self._check_cdp(result)
        self._check_feishu(result)
        self._log_result(result)
        return result

    def _check_python(self, result: PrecheckResult) -> None:
        version = sys.version_info
        passed = (version.major, version.minor) in ((3, 10), (3, 11)) or version >= (3, 10)
        result.add(
            "Python version",
            passed,
            f"current={version.major}.{version.minor}.{version.micro}, expected>=3.10",
        )

    def _check_app(self, result: PrecheckResult, *, attach_existing_app: bool = False) -> None:
        # The runner passes True only after confirming a listening CDP port.
        if attach_existing_app:
            result.add("APP startup credential check", True, "CDP 端口已存在：复用 APP，跳过启动路径、参数及签发私钥检查")
            return
        app_config = resolve_app_config(self.config)
        exe_path = app_config.exe_path
        work_dir = app_config.work_dir
        startup_args = app_config.startup_args

        result.add("APP exe_path exists", exe_path.is_file(), str(exe_path))
        result.add("APP work_dir exists", work_dir.is_dir(), str(work_dir))
        try:
            enabled = auth_enabled(self.config)
            startup_args = normalized_app_startup_args(self.config, startup_args)
            validate_cdp_auth_setup(self.config)
        except AppCdpAuthError as exc:
            result.add("APP startup credential configuration", False, str(exc))
            return
        safe_args = ", ".join(redact_app_startup_args(startup_args))
        port_flag = "--dicloak-debug-port=" if enabled else "--remote-debugging-port="
        result.add(
            "APP startup arg " + port_flag[2:-1],
            any(str(arg).startswith(port_flag) for arg in startup_args),
            safe_args,
        )
        result.add(
            "APP startup arg remote-allow-origins",
            "--remote-allow-origins=*" in startup_args,
            safe_args,
        )
        if enabled:
            result.add("APP startup credential configuration", True, "签发脚本、私钥路径与 cryptography 依赖已检查；本次预检未读取私钥或签发凭证，实际签发仅在启动前进行")

    def _check_test_data(self, result: PrecheckResult) -> None:
        test_data = self.config["test_data"]
        bookmark = test_data["bookmark"]
        member_export = test_data["member_export"]
        batch_export = test_data["batch_export"]
        packet_capture = test_data["packet_capture"]
        local_extension = test_data["local_extension"]

        import_file = batch_import_file(self.config)
        result.add("Batch import file exists", import_file.is_file(), str(import_file))
        result.add(
            "Bookmark storage dir exists",
            Path(bookmark.get("storage_dir", "")).is_dir(),
            str(bookmark.get("storage_dir", "")),
        )
        member_export_dir = Path(member_export.get("export_dir", ""))
        result.add("Member export dir exists", member_export_dir.is_dir(), str(member_export_dir))
        try:
            regex = member_export_file_regex(self.config)
            result.add("Member export filename regex valid", True, regex.pattern)
        except Exception as exc:
            result.add("Member export filename regex valid", False, str(exc))

        export_dir = Path(batch_export.get("export_dir", ""))
        result.add("Batch export dir exists", export_dir.is_dir(), str(export_dir))

        packet_tool = Path(packet_capture.get("startup_path", ""))
        result.add("Packet capture startup path exists", packet_tool.is_file(), str(packet_tool))
        extension_path = local_extension_file(self.config)
        result.add("Local extension package exists", extension_path.is_file(), str(extension_path))

    def _check_cdp(self, result: PrecheckResult) -> None:
        cdp = self.config["cdp"]
        host = cdp.get("host", "127.0.0.1")
        port = int(cdp.get("port", 9222))
        occupied = _is_port_open(host, port)
        result.add("CDP port status checked", True, f"{host}:{port} occupied={occupied}")

    def _check_feishu(self, result: PrecheckResult) -> None:
        feishu = self.config["feishu"]
        if not feishu.get("enabled", True):
            result.add("Feishu webhook configured", True, "feishu disabled")
            return
        webhook = str(feishu.get("webhook_url", "")).strip()
        result.add("Feishu webhook configured", bool(webhook), "configured" if webhook else "empty")

    def _log_result(self, result: PrecheckResult) -> None:
        for item in result.items:
            level = self.logger.info if item.passed else self.logger.error
            level("Precheck %-38s %s %s", item.name, "PASS" if item.passed else "FAIL", item.message)


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def is_cdp_port_open(config: dict[str, Any]) -> bool:
    """Probe the configured TCP listener, not Playwright or APP authentication."""
    cdp = config.get("cdp", {})
    return _is_port_open(str(cdp.get("host", "127.0.0.1")), int(cdp.get("port", 9222)))


def is_local_cdp_host(config: dict[str, Any]) -> bool:
    host = str(config.get("cdp", {}).get("host", "127.0.0.1")).strip().lower()
    if host.rstrip(".") == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
