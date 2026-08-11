from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any

from core.local_auth_lab.server import LocalAuthLabServer
from core.local_auth_lab.settings import LocalAuthLabSettings


@dataclass(frozen=True)
class LocalAuthLabPrecheckResult:
    passed: bool
    messages: tuple[str, ...]


class LocalAuthLabPrechecker:
    """Run checks only when a selected suite explicitly needs the auth lab."""

    def __init__(
        self,
        config: dict[str, Any],
        settings: LocalAuthLabSettings | None = None,
    ):
        self.settings = settings or LocalAuthLabSettings.from_config(config)

    def run(self) -> LocalAuthLabPrecheckResult:
        messages: list[str] = []
        try:
            self.settings = self.settings.ensure_persistent_credentials()
            self.settings.validate_for_start()
        except ValueError as exc:
            return LocalAuthLabPrecheckResult(False, (str(exc),))

        if self.settings.origin_mode == "custom_domains":
            for site_id, domain in self.settings.domains.items():
                try:
                    addresses = {
                        item[4][0]
                        for item in socket.getaddrinfo(
                            domain,
                            self.settings.port,
                            type=socket.SOCK_STREAM,
                        )
                    }
                except OSError as exc:
                    messages.append(f"domain resolution failed: {site_id}={domain}: {exc}")
                    continue
                if not addresses or any(not _is_loopback(address) for address in addresses):
                    messages.append(
                        "domain must resolve only to loopback: "
                        f"{site_id}={domain}, addresses={sorted(addresses)}"
                    )

        probe = LocalAuthLabServer(self.settings)
        existing = probe._existing_health()
        if existing and not probe._health_is_compatible(existing):
            messages.append(f"port {self.settings.port} is occupied by an incompatible auth lab")
        elif not existing and _port_open(self.settings.host, self.settings.port):
            messages.append(f"port {self.settings.port} is occupied by another service")

        return LocalAuthLabPrecheckResult(not messages, tuple(messages))


def _is_loopback(address: str) -> bool:
    return address == "::1" or address.startswith("127.")


def _port_open(host: str, port: int) -> bool:
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0
