from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any


_RUN_ID = os.environ.get("DICLOAK_RUN_ID") or datetime.now().strftime("%Y%m%d%H%M%S")


def run_id() -> str:
    return _RUN_ID


def test_name(config: dict[str, Any], case_key: str, *, kind: str = "env", max_length: int = 80) -> str:
    prefix = _configured_prefix(config)
    token = _slug(case_key)
    kind_token = _slug(kind)
    name = f"{prefix}-{kind_token}-{token}-{_RUN_ID}"
    return name[:max_length].rstrip("-_")


def test_prefix(config: dict[str, Any], case_key: str, *, kind: str = "env", max_length: int = 64) -> str:
    prefix = _configured_prefix(config)
    token = _slug(case_key)
    kind_token = _slug(kind)
    name_prefix = f"{prefix}-{kind_token}-{token}-{_RUN_ID}"
    return name_prefix[:max_length].rstrip("-_")


def cleanup_prefix(config: dict[str, Any], case_key: str, *, kind: str = "env", max_length: int = 48) -> str:
    prefix = _configured_prefix(config)
    token = _slug(case_key)
    kind_token = _slug(kind)
    name_prefix = f"{prefix}-{kind_token}-{token}-"
    return name_prefix[:max_length].rstrip("-_")


def _configured_prefix(config: dict[str, Any]) -> str:
    value = (
        config.get("test_data", {})
        .get("naming", {})
        .get("prefix", "auto")
    )
    prefix = _slug(str(value or "auto"))
    return prefix or "auto"


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "-", value.strip().lower())
    return slug.strip("-")
