"""运行历史页面 — 浏览 logs/ 目录中的历史运行记录.

功能：
  1. 自动解析 CLI 格式（Final test summary）和 UI 格式（运行完成 →）日志
  2. 按时间倒序展示，默认最近 50 条，支持加载更多
  3. 每条记录可展开查看指标卡片和完整日志

设计说明：
  - 纯 Python 实现，无 HTML/CSS/JS 依赖
  - 分页加载避免 700+ 日志文件一次性渲染导致卡顿
  - 侧边栏支持按失败状态、关键词、来源和日期范围筛选
"""

from __future__ import annotations

from datetime import date, datetime
import re
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中（ui/pages/ 的上上级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
from core.run_metadata import parse_run_metadata, run_scope_label

st.set_page_config(page_title="运行历史", page_icon="📋", layout="wide")
st.title("📋 运行历史")

# ── 常量 ──

LOGS_DIR = _PROJECT_ROOT / "logs"
_PAGE_SIZE = 50  # 每页显示条数
_LOG_PREVIEW_CHARS = 5000

# ── 日志解析 ──

# 两种格式均需匹配（CLI 输出 Final test summary，UI 输出 运行完成 →）
_SUMMARY_RE_CLI = re.compile(
    r"Final test summary:\s*total=(\d+)\s+passed=(\d+)\s+failed=(\d+)"
    r"\s+errors=(\d+)\s+skipped=(\d+)\s+flaky=(\d+)"
)
_SUMMARY_RE_UI = re.compile(
    r"运行完成 → 总计=(\d+)\s+通过=(\d+)\s+失败=(\d+)"
    r"\s+错误=(\d+)\s+跳过=(\d+)\s+flaky=(\d+)\s+通过率=([\d.]+)%"
)
_TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _parse_log_summary(log_path: Path) -> dict | None:
    """从 log 文件提取运行摘要，解析失败返回 None.

    支持两种摘要格式：
      - CLI:  Final test summary: total=X passed=X failed=X errors=X skipped=X flaky=X
      - UI :  运行完成 → 总计=X 通过=X 失败=X 错误=X 跳过=X flaky=X 通过率=X%

    均不匹配时尝试兜底（Ran N tests ... OK/FAILED）。
    """
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    info: dict = {}
    metadata = parse_run_metadata(text)
    if metadata:
        info["metadata"] = metadata
        start_metadata = metadata.get("start", {})
        end_metadata = metadata.get("end", {})
        if start_metadata.get("source"):
            info["run_source"] = start_metadata.get("source")
        scope_label = run_scope_label(start_metadata)
        if scope_label:
            info["run_scope"] = scope_label
        if end_metadata.get("exit_code") is not None:
            info["exit_code"] = end_metadata.get("exit_code")

    # ── 时间 ──
    m_time = _TIME_RE.search(text)
    if m_time:
        info["time"] = m_time.group(1)

    # ── 优先匹配 UI 格式（更丰富，含通过率） ──
    m_ui = _SUMMARY_RE_UI.search(text)
    if m_ui:
        info["total"] = int(m_ui.group(1))
        info["passed"] = int(m_ui.group(2))
        info["failed"] = int(m_ui.group(3))
        info["errors"] = int(m_ui.group(4))
        info["skipped"] = int(m_ui.group(5))
        info["flaky"] = int(m_ui.group(6))
        info["pass_rate"] = float(m_ui.group(7))
        info["success"] = info["failed"] == 0 and info["errors"] == 0
        info["source"] = "UI"
        return info

    # ── 其次匹配 CLI 格式 ──
    m_cli = _SUMMARY_RE_CLI.search(text)
    if m_cli:
        info["total"] = int(m_cli.group(1))
        info["passed"] = int(m_cli.group(2))
        info["failed"] = int(m_cli.group(3))
        info["errors"] = int(m_cli.group(4))
        info["skipped"] = int(m_cli.group(5))
        info["flaky"] = int(m_cli.group(6))
        info["success"] = info["failed"] == 0 and info["errors"] == 0
        info["pass_rate"] = (
            round(info["passed"] / info["total"] * 100, 2) if info["total"] > 0 else 0.0
        )
        info["source"] = "CLI"
        return info

    # ── 兜底：单条用例或无摘要 ──
    m_fallback = re.search(r"Ran (\d+) test.*?\n\s*(OK|FAILED)", text, re.DOTALL)
    if m_fallback:
        info["total"] = int(m_fallback.group(1))
        info["success"] = m_fallback.group(2) == "OK"
        info["passed"] = len(re.findall(r"\.\.\. ok", text))
        info["failed"] = info["total"] - info["passed"]
        info["errors"] = 0
        info["skipped"] = 0
        info["flaky"] = 0
        if info["total"] > 0:
            info["pass_rate"] = round(info["passed"] / info["total"] * 100, 2)
        else:
            info["pass_rate"] = 0.0
        info["source"] = "兜底"
        return info

    if metadata:
        end_metadata = metadata.get("end", {})
        run_source = str(info.get("run_source") or "").upper()
        info["total"] = int(end_metadata.get("total") or 0)
        info["passed"] = int(end_metadata.get("passed") or 0)
        info["failed"] = int(end_metadata.get("failed") or 0)
        info["errors"] = int(end_metadata.get("errors") or 0)
        info["skipped"] = int(end_metadata.get("skipped") or 0)
        info["flaky"] = int(end_metadata.get("flaky") or 0)
        info["success"] = bool(end_metadata.get("success", end_metadata.get("exit_code") == 0))
        info["pass_rate"] = round(info["passed"] / info["total"] * 100, 2) if info["total"] > 0 else 0.0
        info["source"] = "UI" if run_source.startswith("UI") else "CLI"
        return info

    return None


def _list_logs() -> list[dict]:
    """扫描 logs/ 目录，返回按时间倒序排列的日志列表."""
    logs: list[dict] = []
    if not LOGS_DIR.exists():
        return logs

    for f in sorted(LOGS_DIR.glob("run_*.log"), key=lambda item: item.stat().st_mtime, reverse=True):
        info = _parse_log_summary(f)
        if info is None:
            continue
        logs.append({
            "name": f.name,
            "path": str(f),
            "size_kb": round(f.stat().st_size / 1024, 1),
            **info,
        })
    return logs


def _entry_matches_keyword(entry: dict, keyword: str) -> bool:
    if not keyword:
        return True
    haystack = " ".join(
        str(entry.get(field, ""))
        for field in ("name", "time", "source", "path")
    ).lower()
    return keyword.lower() in haystack


def _entry_matches_date_range(entry: dict, selected_range) -> bool:
    if not selected_range:
        return True
    if isinstance(selected_range, date):
        start_date = end_date = selected_range
    elif len(selected_range) == 1:
        start_date = end_date = selected_range[0]
    else:
        start_date, end_date = selected_range[0], selected_range[1]

    entry_time = entry.get("time")
    if not entry_time:
        return True
    try:
        entry_date = datetime.strptime(entry_time, "%Y-%m-%d %H:%M:%S").date()
    except ValueError:
        return True
    return start_date <= entry_date <= end_date


# ═══════════════════════════════════════════════════════════════════
# 侧边栏：筛选
# ═══════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🔍 筛选")
    show_only_failures = st.checkbox(
        "只显示失败的运行",
        value=False,
        help="勾选后仅列出存在失败或错误用例的运行记录",
    )
    keyword = st.text_input(
        "关键词",
        placeholder="日志文件名 / 时间 / 来源",
        help="按日志文件名、运行时间或来源标签筛选。",
    ).strip()
    source_filter = st.multiselect(
        "来源",
        options=["CLI", "UI", "兜底"],
        default=["CLI", "UI", "兜底"],
        help="按历史记录解析来源筛选。",
    )
    selected_dates = st.date_input(
        "日期范围",
        value=(),
        help="可选择单日或起止日期；不选则不过滤日期。",
    )
    st.divider()
    st.caption("💡 历史记录来自 `logs/run_*.log`，只展示能解析出摘要的日志。")

# ═══════════════════════════════════════════════════════════════════
# 主体：日志列表
# ═══════════════════════════════════════════════════════════════════

all_logs = _list_logs()

if not all_logs:
    st.info("暂无运行历史记录（`logs/` 目录下未找到含摘要的 `run_*.log` 文件）")
    st.stop()

# 筛选
filtered_logs = [
    log
    for log in all_logs
    if (not show_only_failures or not log.get("success", True))
    and log.get("source") in source_filter
    and _entry_matches_keyword(log, keyword)
    and _entry_matches_date_range(log, selected_dates)
]

# ── 分页状态 ──
if "history_page" not in st.session_state:
    st.session_state.history_page = _PAGE_SIZE
if "history_filter_failures" not in st.session_state:
    st.session_state.history_filter_failures = None
current_filter_state = (show_only_failures, keyword, tuple(source_filter), str(selected_dates))
if st.session_state.history_filter_failures != current_filter_state:
    st.session_state.history_page = _PAGE_SIZE
    st.session_state.history_filter_failures = current_filter_state

visible_logs = filtered_logs[: st.session_state.history_page]

total_str = f"共 {len(filtered_logs)} 条" if not show_only_failures else f"共 {len(filtered_logs)} 条（仅失败）"
st.caption(f"{total_str}（按时间倒序，显示前 {len(visible_logs)} 条）")

if not filtered_logs:
    st.info("当前筛选条件下没有匹配的运行历史。")
    st.stop()

# ── 每条记录一个 expander ──
for i, entry in enumerate(visible_logs):
    total = entry.get("total", "?")
    passed = entry.get("passed", "?")
    failed = entry.get("failed", "?")
    errors = entry.get("errors", "?")
    skipped = entry.get("skipped", "?")
    flaky = entry.get("flaky", "?")
    pass_rate = entry.get("pass_rate", None)
    success = entry.get("success")
    source = entry.get("source", "?")
    run_source = entry.get("run_source", "")
    run_scope = entry.get("run_scope", "")

    # 状态图标
    icon = "✅" if success else ("❌" if success is False else "❓")
    time_str = entry.get("time", entry["name"])

    # expander 标题：状态 + 时间 + 关键指标 + 来源标签
    title = f"{icon} {time_str} — total={total}  passed={passed}  failed={failed}"
    if pass_rate is not None:
        title += f"  ({pass_rate}%)"
    title += f"  [{source}]"
    if run_source or run_scope:
        title += f"  {run_source or '-'}"
        if run_scope:
            title += f" / {run_scope}"

    with st.expander(title):
        # 指标卡片
        if total and isinstance(total, int) and total > 0:
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("📊 总计", total)
            c2.metric("✅ 通过", passed)
            c3.metric("❌ 失败", failed)
            c4.metric("⚠️ 错误", errors)
            c5.metric("⏭️ 跳过", skipped)
            c6.metric("🔁 Flaky", flaky)

            if pass_rate is not None:
                scope_text = f"  |  运行: {run_source or '-'} {run_scope or ''}" if (run_source or run_scope) else ""
                st.caption(
                    f"通过率: {pass_rate}%  |  来源: {source}{scope_text}  |  "
                    f"文件: `{entry['name']}` ({entry['size_kb']} KB)"
                )
        else:
            st.caption(f"文件: `{entry['name']}` ({entry['size_kb']} KB)  |  来源: {source}")

        # 查看完整日志按钮（使用唯一 key 避免 Streamlit 冲突）
        preview_label = (
            "📄 查看完整日志"
            if entry.get("size_kb", 0) * 1024 <= _LOG_PREVIEW_CHARS
            else f"📄 查看日志末尾 {_LOG_PREVIEW_CHARS} 字符"
        )
        if st.button(preview_label, key=f"view_log_{i}"):
            try:
                content = Path(entry["path"]).read_text(encoding="utf-8", errors="replace")
                if len(content) > _LOG_PREVIEW_CHARS:
                    st.caption(
                        f"日志共 {len(content)} 个字符，当前展示末尾 {_LOG_PREVIEW_CHARS} 个字符。"
                    )
                st.code(content[-_LOG_PREVIEW_CHARS:], language="text")
            except Exception as exc:
                st.error(f"读取失败: {exc}")

# ── 加载更多按钮 ──
if st.session_state.history_page < len(filtered_logs):
    remaining = len(filtered_logs) - st.session_state.history_page
    if st.button(f"📥 加载更多（还有 {remaining} 条）", use_container_width=True):
        st.session_state.history_page += _PAGE_SIZE
        st.rerun()
