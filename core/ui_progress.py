from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from time import time
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
LOG_TIMESTAMP_RE = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:[,.]\d+)?"
)
ELAPSED_RE = re.compile(r"\belapsed=(?P<elapsed>\d+(?:\.\d+)?)s\b")
SKIP_REASON_RE = re.compile(r"\breason=(?P<reason>.*?)(?:\r?\n|$)")

STATUS_LABELS = {
    "pending": "待执行",
    "running": "运行中",
    "retrying": "重试中",
    "passed": "通过",
    "flaky_passed": "重试通过",
    "failed": "断言失败",
    "error": "执行错误",
    "skipped": "跳过",
}
FINISHED_STATUSES = {"passed", "flaky_passed", "failed", "error", "skipped"}


def case_progress_snapshot(
    selected_cases: list[dict[str, Any]],
    log_lines: list[str],
    *,
    platforms: list[str] | tuple[str, ...] = ("本机",),
    default_platform: str = "本机",
    observed_at: float | None = None,
) -> dict[str, Any]:
    records: dict[tuple[str, str], dict[str, Any]] = {}
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
                "详情": "等待前序用例完成后执行。",
                "_累计用时秒": 0.0,
                "_活动开始时间": None,
            }

    observed_timestamps: list[float] = []
    for line in log_lines:
        event_timestamp = _line_timestamp(line)
        if event_timestamp is not None:
            observed_timestamps.append(event_timestamp)
        retry_pass = RETRY_PASS_RE.match(line)
        if retry_pass:
            _update_record(
                records,
                known_case_ids,
                retry_pass.group("case_id"),
                retry_pass.group("platform") or default_platform,
                "flaky_passed",
                detail="第 2 次执行通过，首次失败已保留在完整日志中。",
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
                detail="首次执行未通过，正在进行下一次尝试。",
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
            event_timestamp=event_timestamp,
            elapsed_seconds=_line_elapsed_seconds(line),
            detail=_event_detail(line, status),
        )

    reference_time = observed_at
    if reference_time is None:
        reference_time = max(observed_timestamps, default=time())
    rows = [_public_record(record, reference_time) for record in records.values()]
    counts = Counter(row["状态码"] for row in rows)
    total = len(rows)
    finished = sum(counts.get(status, 0) for status in FINISHED_STATUSES)
    active = counts.get("running", 0) + counts.get("retrying", 0)
    problem = counts.get("failed", 0) + counts.get("error", 0)
    return {
        "rows": rows,
        "counts": dict(counts),
        "total": total,
        "finished": finished,
        "active": active,
        "pending": counts.get("pending", 0),
        "problem": problem,
        "progress": (finished / total) if total else 0.0,
    }


def _update_record(
    records: dict[tuple[str, str], dict[str, Any]],
    known_case_ids: set[str],
    case_id: str,
    platform: str,
    status: str,
    *,
    event_timestamp: float | None = None,
    elapsed_seconds: float | None = None,
    detail: str = "",
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
    if status == "running":
        active_started_at = record.get("_活动开始时间")
        if record.get("状态码") == "retrying" and active_started_at is not None and event_timestamp is not None:
            record["_累计用时秒"] = float(record.get("_累计用时秒") or 0.0) + max(
                0.0,
                event_timestamp - float(active_started_at),
            )
        record["_活动开始时间"] = event_timestamp
    elif status == "retrying":
        record["_活动开始时间"] = event_timestamp
    elif status in FINISHED_STATUSES:
        duration = elapsed_seconds
        active_started_at = record.get("_活动开始时间")
        if duration is None and event_timestamp is not None and active_started_at is not None:
            duration = max(0.0, event_timestamp - float(active_started_at))
        if duration is not None:
            record["_累计用时秒"] = float(record.get("_累计用时秒") or 0.0) + max(0.0, duration)
        record["_活动开始时间"] = None
    record["状态码"] = status
    record["状态"] = STATUS_LABELS[status]
    if detail:
        record["详情"] = detail


def _public_record(record: dict[str, Any], observed_at: float) -> dict[str, Any]:
    status = str(record["状态码"])
    elapsed_seconds = float(record.get("_累计用时秒") or 0.0)
    active_started_at = record.get("_活动开始时间")
    if status in {"running", "retrying"} and active_started_at is not None:
        elapsed_seconds += max(0.0, observed_at - float(active_started_at))
    return {
        key: value
        for key, value in {
            **record,
            "用时秒": round(elapsed_seconds, 2),
            "是否计时": status in {"running", "retrying"},
        }.items()
        if not key.startswith("_")
    }


def _line_timestamp(line: str) -> float | None:
    match = LOG_TIMESTAMP_RE.search(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group("timestamp"), "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def _line_elapsed_seconds(line: str) -> float | None:
    match = ELAPSED_RE.search(line)
    return float(match.group("elapsed")) if match else None


def _event_detail(line: str, status: str) -> str:
    if status == "skipped":
        reason = SKIP_REASON_RE.search(line)
        return f"跳过原因：{reason.group('reason').strip()}" if reason else "用例被跳过。"
    if status not in {"failed", "error"}:
        return "执行完成，所有断言通过。" if status == "passed" else ""
    detail_lines = [item.strip() for item in line.splitlines()[1:] if item.strip()]
    detail = detail_lines[-1] if detail_lines else "详情请查看执行日志。"
    prefix = "断言失败" if status == "failed" else "执行错误"
    return f"{prefix}：{detail}"


def _status_from_case_event(event: str) -> str:
    return {
        "START": "running",
        "PASS": "passed",
        "FAIL": "failed",
        "ERROR": "error",
        "SKIP": "skipped",
    }[event]
