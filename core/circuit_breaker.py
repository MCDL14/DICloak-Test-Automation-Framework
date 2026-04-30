from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BreakerName(str, Enum):
    LOGIN = "login"
    APP_STARTUP = "app_startup"
    CDP_CONNECT = "cdp_connect"
    ENVIRONMENT = "environment"
    KERNEL = "kernel"
    BATCH_IMPORT = "batch_import"


@dataclass
class CircuitBreaker:
    name: str
    open: bool = False
    reason: str = ""

    def trip(self, reason: str) -> None:
        self.open = True
        self.reason = reason

    def reset(self) -> None:
        self.open = False
        self.reason = ""


@dataclass
class CircuitBreakerRegistry:
    breakers: dict[str, CircuitBreaker] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in BreakerName:
            self.breakers.setdefault(name.value, CircuitBreaker(name.value))

    def trip(self, name: BreakerName | str, reason: str) -> None:
        key = name.value if isinstance(name, BreakerName) else name
        self.breakers.setdefault(key, CircuitBreaker(key)).trip(reason)

    def reset(self, name: BreakerName | str) -> None:
        key = name.value if isinstance(name, BreakerName) else name
        self.breakers.setdefault(key, CircuitBreaker(key)).reset()

    def is_open(self, name: BreakerName | str) -> bool:
        key = name.value if isinstance(name, BreakerName) else name
        return self.breakers.get(key, CircuitBreaker(key)).open

    def reason(self, name: BreakerName | str) -> str:
        key = name.value if isinstance(name, BreakerName) else name
        return self.breakers.get(key, CircuitBreaker(key)).reason
