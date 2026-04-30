from __future__ import annotations

import functools
import logging
import time
from typing import Callable, TypeVar


F = TypeVar("F", bound=Callable)


def retry(times: int = 1, interval_seconds: float = 0, logger: logging.Logger | None = None):
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempts = max(1, times + 1)
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_error = exc
                    if attempt >= attempts:
                        break
                    if logger:
                        logger.warning(
                            "Retrying %s after error (%s/%s): %s",
                            func.__name__,
                            attempt,
                            attempts - 1,
                            exc,
                        )
                    if interval_seconds > 0:
                        time.sleep(interval_seconds)
            raise last_error  # type: ignore[misc]

        wrapper.is_flaky = times > 0  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def mark_flaky(func: F) -> F:
    setattr(func, "is_flaky", True)
    return func
