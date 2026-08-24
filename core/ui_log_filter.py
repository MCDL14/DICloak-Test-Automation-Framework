from __future__ import annotations

import re


CASE_ERROR_BLOCK_RE = re.compile(
    r"(^[^\n]*CASE (?:FAIL|ERROR).*?)(?="
    r"^\d{4}-\d{2}-\d{2}.*?CASE START|^\d{4}-\d{2}-\d{2}.*?Final test summary:|"
    r"^远程执行完成|\Z)",
    re.DOTALL | re.MULTILINE,
)
UNITTEST_ERROR_BLOCK_RE = re.compile(
    r"(=+\n(?:ERROR|FAIL): .*?)(?=\n-+\nRan \d+ test|\Z)",
    re.DOTALL,
)

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
    blocks: list[str] = []
    for pattern in (CASE_ERROR_BLOCK_RE, UNITTEST_ERROR_BLOCK_RE):
        for match in pattern.finditer(log_text):
            block = match.group(1).strip()
            if block and block not in blocks:
                blocks.append(block)

    if blocks:
        return "\n\n".join(blocks)

    focused_lines = [
        line
        for line in log_text.splitlines()
        if _is_unsuccessful_log_line(line)
    ]
    return "\n".join(focused_lines)


def unsuccessful_log_text(
    log_text: str,
    *,
    empty_message: str = "本次执行没有失败、错误或异常日志。",
) -> str:
    detail = failure_detail_text(log_text)
    return detail or empty_message


def _is_unsuccessful_log_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(marker in stripped for marker in FOCUSED_ERROR_MARKERS)
