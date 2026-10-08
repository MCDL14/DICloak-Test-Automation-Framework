from __future__ import annotations

import re

from core.ui_error_localization import summarize_ui_issue


CASE_ERROR_BLOCK_RE = re.compile(
    r"(^[^\n]*CASE (?:FAIL|ERROR).*?)(?="
    r"^(?:\[[^\]]+\]\s+)?\d{4}-\d{2}-\d{2}.*?CASE START|"
    r"^(?:\[[^\]]+\]\s+)?\d{4}-\d{2}-\d{2}.*?Final test summary:|"
    r"^远程执行完成|\Z)",
    re.DOTALL | re.MULTILINE,
)
UNITTEST_ERROR_BLOCK_RE = re.compile(
    r"(=+\n(?:ERROR|FAIL): .*?)(?=\n-+\nRan \d+ test|\Z)",
    re.DOTALL,
)
CASE_HEADER_RE = re.compile(r"CASE (?P<event>FAIL|ERROR)\s+(?P<case_id>\S+)")
UNITTEST_HEADER_RE = re.compile(r"^(?P<event>FAIL|ERROR):\s+(?P<case_name>[^\n]+)", re.MULTILINE)

FOCUSED_ERROR_MARKERS = (
    "CASE FAIL",
    "CASE ERROR",
    "Traceback",
    "AssertionError",
    "Exception",
    "[FAIL]",
    "[ERROR]",
    "FAIL:",
    "ERROR:",
    "执行器内部异常",
    "执行器启动失败",
    "执行失败",
    "执行错误",
    "远程执行失败",
    "远程执行器错误",
    "远程执行器内部异常",
    "环境预检失败",
    "APP 启动或 CDP 连接失败",
    "失败截图",
    "截图失败",
)


def failure_detail_text(log_text: str) -> str:
    blocks = _failure_blocks(log_text)

    if blocks:
        return "\n\n".join(blocks)

    focused_lines = [
        line
        for line in log_text.splitlines()
        if _is_unsuccessful_log_line(line)
    ]
    return "\n".join(focused_lines)


def localized_failure_overview_text(log_text: str) -> str:
    summaries: list[str] = []
    blocks = _failure_blocks(log_text)
    for index, block in enumerate(blocks, start=1):
        case_header = CASE_HEADER_RE.search(block)
        unittest_header = UNITTEST_HEADER_RE.search(block)
        event = ""
        case_name = ""
        if case_header:
            event = case_header.group("event")
            case_name = case_header.group("case_id")
        elif unittest_header:
            event = unittest_header.group("event")
            case_name = unittest_header.group("case_name").strip()
        status = "failed" if event == "FAIL" else "error"
        issue = summarize_ui_issue(block, status)
        title = f"{index}. {issue.error_type}"
        if issue.exception_class:
            title += f"（{issue.exception_class}）"
        if case_name:
            title += f"｜{case_name}"
        lines = [title, f"   中文说明：{issue.chinese_reason}"]
        if issue.original_error:
            lines.append(f"   原始错误：{issue.original_error}")
        summaries.append("\n".join(lines))
    return "\n\n".join(summaries)


def unsuccessful_log_text(
    log_text: str,
    *,
    empty_message: str = "本次执行没有失败、错误或异常日志。",
) -> str:
    detail = failure_detail_text(log_text)
    if not detail:
        return empty_message
    overview = localized_failure_overview_text(log_text)
    if not overview:
        return detail
    return f"中文失败摘要\n{overview}\n\n原始失败日志\n{detail}"


def _failure_blocks(log_text: str) -> list[str]:
    blocks: list[str] = []
    for pattern in (CASE_ERROR_BLOCK_RE, UNITTEST_ERROR_BLOCK_RE):
        for match in pattern.finditer(log_text):
            block = match.group(1).strip()
            if block and block not in blocks:
                blocks.append(block)
    return blocks


def _is_unsuccessful_log_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(marker in stripped for marker in FOCUSED_ERROR_MARKERS)
