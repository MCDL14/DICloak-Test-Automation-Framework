from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator


def _field_text(fields: dict[str, object]) -> str:
    clean_fields = {
        key: value
        for key, value in fields.items()
        if value is not None and value != ""
    }
    if not clean_fields:
        return ""
    return " " + " ".join(f"{key}={value!r}" for key, value in clean_fields.items())


@contextmanager
def phase_timing(logger, phase: str, **fields: object) -> Iterator[None]:
    """Log elapsed time for a phase without changing the wrapped flow."""
    started_at = time.perf_counter()
    try:
        yield
    except Exception:
        elapsed = time.perf_counter() - started_at
        if logger is not None:
            logger.info("PHASE failed phase=%s elapsed=%.2fs%s", phase, elapsed, _field_text(fields))
        raise
    else:
        elapsed = time.perf_counter() - started_at
        if logger is not None:
            logger.info("PHASE elapsed phase=%s elapsed=%.2fs%s", phase, elapsed, _field_text(fields))
