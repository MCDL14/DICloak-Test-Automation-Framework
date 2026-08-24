from __future__ import annotations

import re
from collections import Counter
from typing import Any


CASE_EVENT_RE = re.compile(
    r"^(?:\[(?P<platform>[^\]]+)\]\s+)?"
    r".*?CASE\s+(?P<event>START|PASS|FAIL|ERROR|SKIP)\s+"
    r"(?:#\d+\s+)?(?P<case_id>\S+)"
)
RETRYING_RE = re.compile(
    r"^(?:\[(?P<platform>[^\]]+)\]\s+)?"
    r".*?Retrying\s+(?P<case_id>\S+)\s+after"
)
RETRY_PASS_RE = re.compile(
    r"^(?:\[(?P<platform>[^\]]+)\]\s+)?"
    r".*?Test passed after retry:\s+(?P<case_id>[^,\s]+)"
)

STATUS_LABELS = {
    "pending": "待执行",
    "running": "运行中",
    "retrying": "重试中",
    "passed": "通过",
    "flaky_passed": "重试通过",
    "failed": "失败",
    "error": "错误",
    "skipped": "跳过",
}
FINISHED_STATUSES = {"passed", "flaky_passed", "failed", "error", "skipped"}


def case_progress_snapshot(
    selected_cases: list[dict[str, Any]],
    log_lines: list[str],
    *,
    platforms: list[str] | tuple[str, ...] = ("本机",),
    default_platform: str = "本机",
) -> dict[str, Any]:
    records: dict[tuple[str, str], dict[str, str]] = {}
    known_case_ids = {str(case.get("id", "")) for case in selected_cases}
    for platform in platforms:
        for index, case in enumerate(selected_cases, start=1):
            case_id = str(case.get("id", ""))
            records[(platform, case_id)] = {
                "执行端": platform,
                "序号": str(index),
                "状态": STATUS_LABELS["pending"],
                "状态码": "pending",
                "用例": str(case.get("display_name") or case.get("method_name") or case_id),
                "模块": str(case.get("module") or ""),
                "原始用例": case_id,
            }

    for line in log_lines:
        retry_pass = RETRY_PASS_RE.match(line)
        if retry_pass:
            _update_record(
                records,
                known_case_ids,
                retry_pass.group("case_id"),
                retry_pass.group("platform") or default_platform,
                "flaky_passed",
            )
            continue

        retrying = RETRYING_RE.match(line)
        if retrying:
            _update_record(
                records,
                known_case_ids,
                retrying.group("case_id"),
                retrying.group("platform") or default_platform,
                "retrying",
            )
            continue

        event = CASE_EVENT_RE.match(line)
        if not event:
            continue
        status = _status_from_case_event(event.group("event"))
        _update_record(
            records,
            known_case_ids,
            event.group("case_id"),
            event.group("platform") or default_platform,
            status,
        )

    rows = list(records.values())
    counts = Counter(row["状态码"] for row in rows)
    total = len(rows)
    finished = sum(counts.get(status, 0) for status in FINISHED_STATUSES)
    active = counts.get("running", 0) + counts.get("retrying", 0)
    problem = counts.get("failed", 0) + counts.get("error", 0)
    return {
        "rows": [
            {key: value for key, value in row.items() if key != "状态码"}
            for row in rows
        ],
        "counts": dict(counts),
        "total": total,
        "finished": finished,
        "active": active,
        "pending": counts.get("pending", 0),
        "problem": problem,
        "progress": (finished / total) if total else 0.0,
    }


def _update_record(
    records: dict[tuple[str, str], dict[str, str]],
    known_case_ids: set[str],
    case_id: str,
    platform: str,
    status: str,
) -> None:
    case_id = str(case_id or "")
    if case_id not in known_case_ids:
        return
    key = (platform, case_id)
    if key not in records:
        key = next((candidate for candidate in records if candidate[1] == case_id), key)
    record = records.get(key)
    if not record:
        return
    record["状态码"] = status
    record["状态"] = STATUS_LABELS[status]


def _status_from_case_event(event: str) -> str:
    return {
        "START": "running",
        "PASS": "passed",
        "FAIL": "failed",
        "ERROR": "error",
        "SKIP": "skipped",
    }[event]
