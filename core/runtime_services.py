from __future__ import annotations

import logging
import unittest
from typing import Any, Iterable

from core.local_auth_lab.precheck import LocalAuthLabPrechecker
from core.local_auth_lab.server import LocalAuthLabServer, LocalAuthLabServerError
from core.local_auth_lab.settings import LocalAuthLabSettings


LOCAL_AUTH_LAB = "local_auth_lab"
SUPPORTED_RUNTIME_SERVICES = frozenset({LOCAL_AUTH_LAB})


class RuntimeServiceError(RuntimeError):
    pass


def collect_required_runtime_services(suite: unittest.TestSuite) -> frozenset[str]:
    required: set[str] = set()
    for test in _iter_tests(suite):
        declared = getattr(test, "REQUIRED_RUNTIME_SERVICES", ())
        if isinstance(declared, str):
            if declared.strip():
                required.add(declared.strip())
        else:
            try:
                required.update(str(item).strip() for item in declared if str(item).strip())
            except TypeError as exc:
                raise RuntimeServiceError(
                    f"invalid REQUIRED_RUNTIME_SERVICES on {test.id()}: expected iterable of names"
                ) from exc
    unsupported = sorted(required - SUPPORTED_RUNTIME_SERVICES)
    if unsupported:
        raise RuntimeServiceError(f"unsupported runtime service(s): {', '.join(unsupported)}")
    return frozenset(required)


class RuntimeServiceManager:
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.local_auth_lab: LocalAuthLabServer | None = None

    def start(self, required: Iterable[str]) -> None:
        names = frozenset(required)
        if not names:
            return
        if LOCAL_AUTH_LAB in names:
            try:
                settings = LocalAuthLabSettings.from_config(
                    self.config
                ).ensure_persistent_credentials()
            except ValueError as exc:
                raise RuntimeServiceError(str(exc)) from exc
            existing = LocalAuthLabServer(settings, self.logger)
            if settings.enabled and settings.credentials_persistent and existing.try_reuse_existing():
                self.local_auth_lab = existing
                return
            precheck = LocalAuthLabPrechecker(self.config, settings=settings).run()
            if not precheck.passed:
                raise RuntimeServiceError("; ".join(precheck.messages))
            try:
                self.local_auth_lab = LocalAuthLabServer(settings, self.logger).start()
            except LocalAuthLabServerError as exc:
                raise RuntimeServiceError(str(exc)) from exc

    def stop(self) -> None:
        if self.local_auth_lab is not None:
            try:
                self.local_auth_lab.stop()
            except Exception as exc:
                self.logger.warning("Failed to stop local auth lab cleanly: %s", exc, exc_info=True)
            finally:
                self.local_auth_lab = None


def _iter_tests(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_tests(item)
        else:
            yield item
