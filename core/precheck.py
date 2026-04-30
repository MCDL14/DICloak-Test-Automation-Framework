from __future__ import annotations

import logging
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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

    def run(self) -> PrecheckResult:
        result = PrecheckResult()
        self._check_python(result)
        self._check_app(result)
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

    def _check_app(self, result: PrecheckResult) -> None:
        app = self.config["app"]
        exe_path = Path(app.get("exe_path", ""))
        work_dir = Path(app.get("work_dir", ""))
        startup_args = app.get("startup_args", [])

        result.add("APP exe_path exists", exe_path.is_file(), str(exe_path))
        result.add("APP work_dir exists", work_dir.is_dir(), str(work_dir))
        result.add(
            "APP startup arg remote-debugging-port",
            any(str(arg).startswith("--remote-debugging-port=") for arg in startup_args),
            ", ".join(map(str, startup_args)),
        )
        result.add(
            "APP startup arg remote-allow-origins",
            "--remote-allow-origins=*" in startup_args,
            ", ".join(map(str, startup_args)),
        )

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
        expected_member = Path(member_export.get("expected_file_full_path", ""))
        result.add("Expected member export file exists", expected_member.is_file(), str(expected_member))
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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0
