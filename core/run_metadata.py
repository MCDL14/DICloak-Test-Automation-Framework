from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any


RUN_START_MARKER = "RUN START "
RUN_END_MARKER = "RUN END "


def cli_run_start_fields(args: Any) -> dict[str, Any]:
    """Build non-invasive metadata for a CLI run from parsed argparse args."""
    fields: dict[str, Any] = {
        "source": "CLI",
        "attach_existing_app": bool(getattr(args, "attach_existing_app", False)),
    }
    if getattr(args, "precheck", False):
        fields.update({"scope": "precheck"})
    elif getattr(args, "case", None):
        cases = [str(item) for item in getattr(args, "case") if str(item).strip()]
        fields.update({"scope": "cases", "selected_count": len(cases), "cases": cases})
    elif getattr(args, "module", None):
        fields.update({"scope": "module", "value": str(getattr(args, "module"))})
    elif getattr(args, "business_module", None):
        fields.update({"scope": "business_module", "value": str(getattr(args, "business_module"))})
    elif getattr(args, "level", None):
        fields.update({"scope": "level", "value": str(getattr(args, "level"))})
    else:
        fields.update({"scope": "default"})
    return fields


def log_run_start(logger: logging.Logger, **fields: Any) -> None:
    payload = {
        "schema": 1,
        "event": "start",
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **_clean_fields(fields),
    }
    logger.info("%s%s", RUN_START_MARKER, _to_json(payload))


def log_run_end(logger: logging.Logger, **fields: Any) -> None:
    payload = {
        "schema": 1,
        "event": "end",
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **_clean_fields(fields),
    }
    logger.info("%s%s", RUN_END_MARKER, _to_json(payload))


def parse_run_metadata(text: str) -> dict[str, dict[str, Any]]:
    """Return the first RUN START and last RUN END payloads found in log text."""
    metadata: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        if RUN_START_MARKER in line:
            payload = _payload_after_marker(line, RUN_START_MARKER)
            if payload:
                metadata["start"] = payload
        if RUN_END_MARKER in line:
            payload = _payload_after_marker(line, RUN_END_MARKER)
            if payload:
                metadata["end"] = payload
    return metadata


def run_scope_label(metadata: dict[str, Any]) -> str:
    scope = str(metadata.get("scope", "") or "").strip()
    value = str(metadata.get("value", "") or "").strip()
    selected_count = metadata.get("selected_count")
    if scope == "cases":
        try:
            count = int(selected_count)
        except (TypeError, ValueError):
            count = len(metadata.get("cases", []) or [])
        return f"cases:{count}" if count else "cases"
    if value:
        return f"{scope}:{value}" if scope else value
    return scope


def _payload_after_marker(line: str, marker: str) -> dict[str, Any]:
    _, _, raw_payload = line.partition(marker)
    if not raw_payload:
        return {}
    try:
        payload = json.loads(raw_payload.strip())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in (None, "", [])}


def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
