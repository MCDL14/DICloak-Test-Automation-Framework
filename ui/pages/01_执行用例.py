"""执行用例页面 — 选择用例 → 运行 → 实时日志 → 结果统计.

依赖 streamlit_runner.py 提供用例发现与后台执行能力。
执行时完整复用核心框架的恢复钩子、失败截图、飞书通知。

==== 设计要点 ====
- 用例发现使用 @st.cache_data(ttl=30) 缓存，避免每次交互都重新扫描
- 勾选状态使用 st.session_state 持久化，切换 expander 不会丢失
- 后台线程执行 + 前台 queue 轮询实现实时日志流
- 结果通过正则解析 "运行完成 → 总计=..." 结构化摘要行
- 失败/错误的飞书通知由 streamlit_runner 内部自动发送，本页无需处理

==== 如何调整 UI 排布 ====
- 侧边栏顺序：直接调整 with st.sidebar: 内的 st.* 调用顺序
- 指标卡片布局：修改 st.columns(6) 参数并交换 with 块顺序
- 模块折叠面板：调整 expander 的 expanded 条件（当前是 len ≤ 3 展开）
"""

from __future__ import annotations

import queue
import re
import sys
import threading
import time
import hashlib
from collections import defaultdict
import inspect
from pathlib import Path

# 确保项目根目录在 sys.path 中（ui/pages/ 的上上级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from core.account_groups import (
    ACCOUNT_GROUP_SLOTS,
    AccountGroupError,
    account_group_label,
    account_group_missing_fields,
    concurrent_account_group_conflicts,
    load_account_groups,
    runtime_account_profile,
)
from core.config import ConfigError, load_config
from core.ui_log_filter import (
    failure_detail_text as _failure_detail_text,
    unsuccessful_log_text as _unsuccessful_log_text,
)
from core.ui_progress import case_progress_snapshot
from ui.components.case_selector import render_case_selector
from streamlit_runner import (
    check_remote_host,
    check_remote_code,
    create_ui_stop_event,
    discover_cases,
    discover_remote_hosts,
    load_remote_connection_cache,
    preview_remote_command,
    remote_capability_matrix,
    request_ui_task_stop,
    reset_stale_ui_task_lock,
    run_local_and_remote,
    run_remote_cli,
    run_selected_tests,
    save_remote_connection_cache,
    sync_remote_code,
    ui_task_status,
)

_LOG_IDLE_WARNING_SECONDS = 300
_LOG_DISPLAY_LINES = 50
_LOG_DISPLAY_HEIGHT = 420
_RESULT_SUMMARY_RE = re.compile(
    r"运行完成 → 总计=(\d+) 通过=(\d+) 失败=(\d+) 错误=(\d+) 跳过=(\d+) flaky=(\d+) 通过率=([\d.]+)%"
)
_CLI_SUMMARY_RE = re.compile(
    r"Final test summary:\s*total=(\d+)\s+passed=(\d+)\s+failed=(\d+)"
    r"\s+errors=(\d+)\s+skipped=(\d+)\s+flaky=(\d+)"
)
_REMOTE_EXIT_RE = re.compile(r"远程(?:执行完成|健康检查结束) → 节点=([^\s]+) 退出码=(\d+) 耗时=([\d.]+)s")
_REMOTE_HEALTH_DONE_RE = re.compile(r"远程健康检查完成 → 失败=(\d+)")
_REMOTE_ARTIFACT_RE = re.compile(r"远程产物归档 → 文件数=(\d+) 本地目录=(.+)")

_ACCOUNT_GROUPS_PATH = _PROJECT_ROOT / "config" / "account_groups.yaml"
_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"
_MEMBER_API_CASE_MARKERS = (
    ".test_12_api_disable_external_member.",
    ".test_13_api_disuse_external_member.",
    ".test_14_api_disable_internal_member.",
    ".test_15_api_disuse_internal_member.",
)
_INTERNAL_ACCOUNT_CASE_MARKERS = (
    ".test_08_filter_member_login_account_email.",
    ".test_11_no_edit_permission_member.",
    ".test_14_api_disable_internal_member.",
    ".test_15_api_disuse_internal_member.",
)
_MEMBER_ID_CASE_MARKERS = (
    ".test_12_api_disable_external_member.",
    ".test_13_api_disuse_external_member.",
    ".test_14_api_disable_internal_member.",
    ".test_15_api_disuse_internal_member.",
)
_CASE_EXTERNAL_MEMBER_CASE_MARKERS = (
    ".test_01_create_external_member.",
    ".test_02_edit_external_member_name.",
    ".test_03_create_internal_member.",
    ".test_05_filter_member_group.",
    ".test_08_filter_member_login_account_email.",
    ".test_10_export_member.",
)


def _stable_widget_key(prefix: str, identity: str) -> str:
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"

# ═══════════════════════════════════════════════════════════════════
# 页面配置
# ═══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="执行用例", page_icon="🧪", layout="wide")
st.markdown(
    """
    <style>
    div[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.85rem;
    }
    div.stButton > button {
        min-height: 2rem;
        padding: 0.18rem 0.65rem;
        border-radius: 6px;
        font-size: 0.9rem;
        font-weight: 400;
        line-height: 1.25;
    }
    div.stButton > button[kind="tertiary"] {
        color: inherit;
        padding-left: 0;
        padding-right: 0.25rem;
    }
    div.stButton > button[kind="tertiary"]:hover {
        color: inherit;
        background: transparent;
    }
    div[data-testid="stVerticalBlock"] {
        gap: 0.55rem;
    }
    div[data-testid="stHorizontalBlock"] {
        gap: 0.65rem;
    }
    div[data-testid="stProgress"] {
        margin: 0.15rem 0 0.35rem 0;
    }
    div[data-testid="stProgress"] div[role="progressbar"] {
        min-height: 0.42rem;
        height: 0.42rem;
    }
    .dicloak-section-title {
        font-size: 0.98rem;
        font-weight: 600;
        margin: 0.15rem 0 0.35rem 0;
    }
    .dicloak-page-title {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        font-size: 1.75rem;
        font-weight: 650;
        line-height: 1.15;
        margin: 0.25rem 0 1.05rem 0;
    }
    .dicloak-page-title span:first-child {
        font-size: 1.55rem;
    }
    div[class*="st-key-dicloak_selection_toolbar"] {
        border: 1px solid #d5dde8;
        border-radius: 6px;
        background: #f3f7fd;
        padding: 0.62rem 0.72rem;
        margin: 0.12rem 0 1rem 0;
    }
    div[class*="st-key-dicloak_selection_toolbar"] > div[data-testid="stVerticalBlock"] {
        gap: 0;
    }
    div[class*="st-key-dicloak_selection_toolbar"] div[data-testid="stProgress"] {
        margin: 0;
    }
    div[class*="st-key-dicloak_selection_toolbar"] div[data-testid="stProgressBarTrack"] > div {
        background: #138f97;
    }
    .dicloak-selection-count {
        font-size: 0.84rem;
        color: #334155;
        white-space: nowrap;
    }
    div[class*="st-key-dicloak_selection_toolbar"] div.stButton > button {
        min-height: 2.15rem;
        background: #ffffff;
        border-color: #c9d3e1;
    }
    .dicloak-remote-section-title {
        border-left: 3px solid #168c92;
        color: #1e293b;
        font-size: 1rem;
        font-weight: 650;
        line-height: 1.3;
        margin: 1.2rem 0 0.58rem 0;
        padding-left: 0.58rem;
    }
    .dicloak-remote-section-title.is-first {
        margin-top: 0.8rem;
    }
    div[class*="st-key-dicloak_remote_node_card"],
    div[class*="st-key-dicloak_remote_options"] {
        border-color: #cbd5e1;
        border-radius: 7px;
        background: color-mix(in srgb, #f8fafc 88%, transparent);
        padding: 0.82rem 0.95rem;
    }
    div[class*="st-key-dicloak_remote_connection_editor"] {
        border-color: #c8d5e3;
        border-radius: 7px;
        background: color-mix(in srgb, #f2f7fb 82%, transparent);
        padding: 0.8rem 0.9rem;
    }
    .dicloak-remote-node-name {
        font-size: 0.96rem;
        font-weight: 600;
        line-height: 1.35;
    }
    .dicloak-remote-node-meta {
        color: #64748b;
        font-size: 0.82rem;
        line-height: 1.4;
        margin-top: 0.1rem;
    }
    .dicloak-remote-status {
        color: #0f766e;
        font-size: 0.8rem;
        font-weight: 500;
    }
    div[class*="st-key-dicloak_remote_mode_"] {
        border: 1px solid #cbd5e1;
        border-radius: 7px;
        padding: 0.72rem 0.8rem;
        min-height: 5.55rem;
        background: color-mix(in srgb, #ffffff 92%, transparent);
        transition: border-color 120ms ease, background-color 120ms ease;
    }
    div[class*="st-key-dicloak_remote_mode_"]:has(button[kind="primary"]) {
        border-color: #168c92;
        background: color-mix(in srgb, #e8f8f7 82%, transparent);
        box-shadow: inset 3px 0 0 #168c92;
    }
    div[class*="st-key-dicloak_remote_mode_"] div.stButton > button {
        justify-content: flex-start;
        min-height: 1.85rem;
        padding-left: 0.55rem;
    }
    div[class*="st-key-dicloak_remote_mode_"] div.stButton > button[kind="primary"] {
        color: #0f5f64;
        background: #dff6f5;
        border-color: #178b91;
    }
    div[class*="st-key-dicloak_remote_mode_"] [data-testid="stCaptionContainer"] {
        margin-left: 0.1rem;
    }
    div[class*="st-key-dicloak_remote_options"] [data-testid="stCheckbox"] label {
        min-height: 1.7rem;
    }
    div[class*="st-key-dicloak_remote_options"] div[data-testid="column"] {
        padding: 0.08rem 0.7rem;
    }
    div[class*="st-key-dicloak_remote_options"] div[data-testid="column"] + div[data-testid="column"] {
        border-left: 1px solid #d9e1ea;
    }
    div[class*="st-key-dicloak_remote_tools"] details,
    div[class*="st-key-dicloak_remote_advanced"] details {
        border-color: #d7dee8;
        border-radius: 7px;
    }
    div[class*="st-key-dicloak_remote_tools"] {
        margin-top: 1rem;
    }
    div[class*="st-key-dicloak_remote_advanced"] {
        margin-top: 0.2rem;
    }
    .dicloak-runbar {
        border-top: 1px solid color-mix(in srgb, currentColor 14%, transparent);
        padding-top: 0.75rem;
        margin-top: 0.25rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="dicloak-page-title"><span>🧪</span><span>执行用例</span></div>',
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════════════════
# 加载用例（缓存 30 秒，避免每次交互都重新发现）
# ═══════════════════════════════════════════════════════════════════

@st.cache_data(ttl=30, show_spinner="正在发现用例...")
def _load_cases() -> list[dict]:
    return discover_cases()

try:
    cases = _load_cases()
except Exception as exc:
    st.error(f"用例发现失败：{exc}")
    st.caption("请确认 `config/config.yaml` 存在且格式正确；必要时先运行 `python run.py --config config/config.yaml --precheck`。")
    st.stop()

try:
    _base_config = load_config(_CONFIG_PATH)
    account_groups = load_account_groups(_ACCOUNT_GROUPS_PATH, base_config=_base_config)
except (ConfigError, AccountGroupError) as exc:
    st.error(f"账号组配置读取失败：{exc}")
    st.stop()


def _account_group_options() -> dict[str, str]:
    result: dict[str, str] = {}
    for index, slot in enumerate(ACCOUNT_GROUP_SLOTS, start=1):
        label = f"组 {index} · {account_group_label(slot, account_groups[slot])}"
        result[label] = slot
    return result


def _selected_account_requirements(case_ids: list[str]) -> tuple[bool, bool, bool, bool]:
    require_member_api = any(
        marker in case_id
        for case_id in case_ids
        for marker in _MEMBER_API_CASE_MARKERS
    )
    require_internal = require_member_api or any(
        marker in case_id
        for case_id in case_ids
        for marker in _INTERNAL_ACCOUNT_CASE_MARKERS
    )
    require_member_ids = require_member_api or any(
        marker in case_id
        for case_id in case_ids
        for marker in _MEMBER_ID_CASE_MARKERS
    )
    require_case_external = any(
        marker in case_id
        for case_id in case_ids
        for marker in _CASE_EXTERNAL_MEMBER_CASE_MARKERS
    )
    return require_internal, require_member_ids, require_member_api, require_case_external

# 按模块分组
by_module: dict[str, list[dict]] = defaultdict(list)
for c in cases:
    by_module[c["module"]].append(c)
module_names = sorted(by_module.keys())


def _case_key(case_id: str) -> str:
    return _stable_widget_key("case_selected", case_id)


def _set_case_selected(case_list: list[dict], selected: bool) -> None:
    for case in case_list:
        st.session_state[_case_key(case["id"])] = selected


def _set_all_cases_selected(selected: bool) -> None:
    _set_case_selected(cases, selected)


def _selected_count(case_list: list[dict]) -> int:
    return sum(
        1
        for case in case_list
        if bool(st.session_state.get(_case_key(case["id"]), True))
    )


def _module_summary(case_list: list[dict]) -> str:
    if not case_list:
        return ""
    sample_names = [
        str(case.get("display_name") or case.get("method_name") or "")
        for case in case_list[:3]
    ]
    return " / ".join(name for name in sample_names if name)


def _render_case_selection_panel(
    visible_modules: list[str],
    visible_cases_by_module: dict[str, list[dict]],
) -> None:
    visible_cases = [
        case
        for module_name in visible_modules
        for case in visible_cases_by_module[module_name]
    ]
    selected_case_count = _selected_count(cases)

    st.markdown('<div class="dicloak-section-title">用例选择</div>', unsafe_allow_html=True)
    with st.container(key="dicloak_selection_toolbar"):
        progress_col, count_col, select_col, clear_col = st.columns(
            [4.6, 1.15, 1.25, 1.25],
            vertical_alignment="center",
        )
        with progress_col:
            st.progress(
                selected_case_count / len(cases) if cases else 0.0,
            )
        with count_col:
            st.markdown(
                f'<div class="dicloak-selection-count">已选 {selected_case_count} / {len(cases)}</div>',
                unsafe_allow_html=True,
            )
        with select_col:
            st.button(
                "选择可见",
                key="select_visible_cases",
                use_container_width=True,
                on_click=_set_case_selected,
                args=(visible_cases, True),
                help="只选择当前筛选条件下显示出来的用例。",
                icon=":material/check_box:",
            )
        with clear_col:
            st.button(
                "清空选择",
                key="clear_all_cases",
                use_container_width=True,
                on_click=_set_all_cases_selected,
                args=(False,),
                icon=":material/check_box_outline_blank:",
            )

    st.markdown("**模块总览**")
    module_payload: list[dict] = []
    for module_name in visible_modules:
        all_module_cases = by_module[module_name]
        visible_module_cases = visible_cases_by_module[module_name]
        module_payload.append(
            {
                "name": module_name,
                "description": _module_summary(all_module_cases),
                "total_count": len(all_module_cases),
                "visible_count": len(visible_module_cases),
                "case_ids": [case["id"] for case in all_module_cases],
                "cases": [
                    {
                        "id": case["id"],
                        "name": str(
                            case.get("display_name")
                            or f"{case['class_name']}.{case['method_name']}"
                        ),
                    }
                    for case in visible_module_cases
                ],
            }
        )

    component_value = render_case_selector(
        modules=module_payload,
        selected_ids=[
            case["id"]
            for case in cases
            if bool(st.session_state.get(_case_key(case["id"]), True))
        ],
        expanded_modules=st.session_state.get("execute_cases_component_expanded", []),
        key="execute_case_selector_component",
        default=None,
    )
    if isinstance(component_value, dict):
        event_id = str(component_value.get("event_id", ""))
        if event_id and event_id != st.session_state.get("execute_cases_component_event"):
            selected_ids = {
                str(case_id)
                for case_id in component_value.get("selected_ids", [])
            }
            known_case_ids = {case["id"] for case in cases}
            selected_ids.intersection_update(known_case_ids)
            _set_case_selected(cases, False)
            for case in cases:
                if case["id"] in selected_ids:
                    st.session_state[_case_key(case["id"])] = True
            st.session_state["execute_cases_component_event"] = event_id
            st.session_state["execute_cases_component_expanded"] = [
                str(module_name)
                for module_name in component_value.get("expanded_modules", [])
                if str(module_name) in by_module
            ]
            st.rerun()


def _case_matches_keyword(case: dict, keyword: str) -> bool:
    if not keyword:
        return True
    haystack = " ".join(
        str(case.get(field, ""))
        for field in ("id", "module", "display_name", "class_name", "method_name")
    ).lower()
    return keyword.lower() in haystack


def _summary_missing_message(log_text: str) -> tuple[str, str]:
    if "执行已停止" in log_text or "收到停止请求" in log_text:
        return "warning", "执行已停止，后续用例不会继续启动。"
    if "已有 UI 执行任务正在运行" in log_text:
        return "warning", "已有 UI 执行任务正在运行，本次没有启动新的用例执行。"
    if "环境预检失败" in log_text:
        return "error", "环境预检失败，未进入用例执行阶段。请查看上方日志中的失败项。"
    if "APP 启动或 CDP 连接失败" in log_text:
        return "error", "APP 启动或 CDP 连接失败，未进入用例执行阶段。请检查 APP 状态和 CDP 端口。"
    if "没有匹配到任何用例" in log_text:
        return "warning", "没有匹配到任何用例，本次未执行。"
    if "执行器内部异常" in log_text or "执行器启动失败" in log_text:
        return "error", "执行器内部异常，未能生成结果统计。请查看上方异常日志。"
    if "远程执行器错误" in log_text or "远程执行器内部异常" in log_text or "远程执行失败" in log_text:
        return "error", "远程执行失败，未能生成结果统计。请查看上方远程日志。"
    if "远程健康检查错误" in log_text or "远程健康检查内部异常" in log_text or "远程健康检查未通过" in log_text:
        return "error", "远程健康检查未通过。请查看上方 [FAIL] 项并补齐远端环境。"
    if "远程代码检查错误" in log_text or "远程代码检查内部异常" in log_text:
        return "error", "远程代码检查失败。请查看上方日志。"
    if "远程代码同步错误" in log_text or "远程代码同步内部异常" in log_text:
        return "error", "远程代码同步失败。请查看上方日志，远端旧快照仍保留。"
    if "远程代码同步完成" in log_text:
        return "success", "远程代码同步完成。"
    if "远程代码检查完成" in log_text and "状态=synced" in log_text:
        return "success", "远端代码已与本地当前工作区一致。"
    if "远程代码检查完成" in log_text:
        return "warning", "远端代码状态已检查，请根据日志判断是否需要同步。"
    if "远程健康检查结束" in log_text and "退出码=0" in log_text:
        return "success", "远程健康检查通过。"
    if "远程执行完成" in log_text and "退出码=0" in log_text:
        return "success", "远程执行完成，当前任务没有生成用例统计。"
    return "warning", "执行完成，但未能解析结果统计。请查看上方日志。"


def _parse_result_summary(log_text: str) -> tuple[int, int, int, int, int, int, str] | None:
    ui_match = _RESULT_SUMMARY_RE.search(log_text)
    if ui_match:
        total, passed, failed, errors, skipped, flaky, rate = ui_match.groups()
        return int(total), int(passed), int(failed), int(errors), int(skipped), int(flaky), rate

    cli_match = _CLI_SUMMARY_RE.search(log_text)
    if cli_match:
        total, passed, failed, errors, skipped, flaky = [int(value) for value in cli_match.groups()]
        rate = f"{round(passed / total * 100, 2) if total else 0.0}"
        return total, passed, failed, errors, skipped, flaky, rate

    return None


def _parse_prefixed_result_summaries(
    log_lines: list[str],
) -> dict[str, tuple[int, int, int, int, int, int, str]]:
    result: dict[str, tuple[int, int, int, int, int, int, str]] = {}
    for label in ("Windows", "macOS"):
        prefix = f"[{label}] "
        target_text = "\n".join(
            line[len(prefix):]
            for line in log_lines
            if line.startswith(prefix)
        )
        summary = _parse_result_summary(target_text)
        if summary:
            result[label] = summary
    return result


def _render_metrics(summary: tuple[int, int, int, int, int, int, str]) -> None:
    total, passed, failed, errors, skipped, _flaky, rate = summary
    cols = st.columns(6)
    cols[0].metric("总计", total)
    cols[1].metric("通过", passed)
    cols[2].metric("失败", failed, delta=None if failed == 0 else f"-{failed}")
    cols[3].metric("错误", errors)
    cols[4].metric("跳过", skipped)
    cols[5].metric("通过率", f"{rate}%")


def _render_case_progress(
    container,
    *,
    selected_cases: list[dict],
    log_lines: list[str],
    platforms: list[str],
    default_platform: str,
) -> None:
    snapshot = case_progress_snapshot(
        selected_cases,
        log_lines,
        platforms=platforms,
        default_platform=default_platform,
    )
    with container.container():
        st.markdown("**执行进度**")
        total = int(snapshot["total"])
        finished = int(snapshot["finished"])
        st.progress(
            float(snapshot["progress"]),
            text=f"已完成 {finished}/{total} 条",
        )
        cols = st.columns(5)
        cols[0].metric("总计", total)
        cols[1].metric("已完成", finished)
        cols[2].metric("运行中", int(snapshot["active"]))
        cols[3].metric("待执行", int(snapshot["pending"]))
        cols[4].metric("失败/错误", int(snapshot["problem"]))
        rows = snapshot["rows"]
        if rows:
            display_rows = [
                {key: row.get(key, "") for key in ("执行端", "序号", "状态", "模块", "用例")}
                for row in rows
            ]
            st.dataframe(
                display_rows,
                hide_index=True,
                use_container_width=True,
                height=320,
            )


def _case_progress_log_relevant(line: str) -> bool:
    return (
        "CASE START" in line
        or "CASE PASS" in line
        or "CASE FAIL" in line
        or "CASE ERROR" in line
        or "CASE SKIP" in line
        or "Retrying " in line
        or "Test passed after retry:" in line
    )


def _progress_platforms_for_run(execution_mode: str, remote_scope: str) -> tuple[list[str], str, bool]:
    if execution_mode == "远程节点" and remote_scope == "precheck":
        return [], "远程", False
    if execution_mode == "本机 + Mac 远程":
        return ["Windows", "macOS"], "Windows", True
    if execution_mode == "远程节点":
        return ["远程"], "远程", True
    return ["本机"], "本机", True


def _remote_log_summary(log_lines: list[str]) -> dict[str, object]:
    log_text = "\n".join(log_lines)
    result_summary = _parse_result_summary(log_text)
    pass_lines = [line for line in log_lines if line.startswith("[PASS]")]
    fail_lines = [line for line in log_lines if line.startswith("[FAIL]")]
    exit_match = _REMOTE_EXIT_RE.search(log_text)
    health_match = _REMOTE_HEALTH_DONE_RE.search(log_text)
    artifact_match = _REMOTE_ARTIFACT_RE.search(log_text)
    return {
        "pass_count": len(pass_lines),
        "fail_count": len(fail_lines),
        "fail_lines": fail_lines,
        "exit": exit_match.groups() if exit_match else None,
        "health_fail_count": int(health_match.group(1)) if health_match else None,
        "artifact": artifact_match.groups() if artifact_match else None,
        "result_summary": result_summary,
    }


def _render_remote_result_summary(log_lines: list[str]) -> None:
    summary = _remote_log_summary(log_lines)
    has_remote_detail = any(summary.get(key) for key in ("pass_count", "fail_count", "exit", "artifact"))
    if not has_remote_detail:
        return

    with st.expander("远程执行摘要", expanded=True):
        col_pass, col_fail, col_exit = st.columns(3)
        result_summary = summary.get("result_summary")
        if result_summary:
            _, passed, failed, errors, _, _, _ = result_summary
            col_pass.metric("通过", passed)
            col_fail.metric("失败/错误", failed + errors)
        else:
            col_pass.metric("[PASS]", summary["pass_count"])
            col_fail.metric("[FAIL]", summary["fail_count"])
        exit_info = summary["exit"]
        if exit_info:
            _, exit_code, duration = exit_info
            col_exit.metric("退出码", exit_code, f"{duration}s")
        else:
            col_exit.metric("退出码", "-")

        health_fail_count = summary.get("health_fail_count")
        if health_fail_count is not None:
            if health_fail_count == 0:
                st.success("远程健康检查通过。")
            else:
                st.error(f"远程健康检查未通过：失败项数量={health_fail_count}")

        fail_lines = summary.get("fail_lines") or []
        if fail_lines:
            st.code("\n".join(fail_lines), language="text")

        artifact = summary.get("artifact")
        if artifact:
            file_count, local_dir = artifact
            st.info(f"远程产物已归档：文件数={file_count}，本地目录={local_dir}")


def _remote_host_details(
    host: dict[str, str],
    *,
    current_host: str = "",
    current_port: int | str = "",
    current_username: str = "",
    password_provided: bool = False,
    cache_enabled: bool = False,
) -> list[dict[str, str]]:
    current_connection = ""
    if current_host or current_username:
        current_connection = f"{current_username or '-'}@{current_host or '-'}:{current_port or '22'}"
    return [
        {"字段": "节点", "值": host.get("name", "")},
        {"字段": "平台", "值": host.get("platform") or "unknown"},
        {"字段": "配置默认 SSH", "值": f"{host.get('username', '')}@{host.get('host', '')}:{host.get('port', '22')}"},
        {"字段": "当前 UI 连接", "值": current_connection or "-"},
        {"字段": "临时密码", "值": "已填写（仅本次会话）" if password_provided else "未填写"},
        {"字段": "连接缓存", "值": "已启用（不含密码）" if cache_enabled else "未启用"},
        {"字段": "项目目录", "值": host.get("project_dir", "")},
        {"字段": "配置", "值": host.get("config", "")},
        {"字段": "Python", "值": host.get("python", "")},
        {"字段": "虚拟环境", "值": host.get("venv_activate") or "-"},
        {"字段": "认证", "值": host.get("auth", "")},
        {"字段": "代码同步", "值": host.get("sync_enabled", "")},
        {"字段": "发布目录", "值": host.get("sync_release_root", "")},
        {"字段": "保留快照", "值": host.get("sync_keep_releases", "")},
    ]


def _safe_port(value: object, default: int = 22) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return default
    return port if 1 <= port <= 65535 else default


def _remote_run_button_label(scope_label: str, value: str, *, case_count: int = 0) -> str:
    if scope_label == "远程预检":
        return "▶ 执行远程预检"
    if scope_label == "执行用例":
        return f"▶ 远程执行选中（{case_count} 条）"
    return "▶ 远程执行"


def _accepts_keyword(func: object, keyword: str) -> bool:
    try:
        return keyword in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def _remote_selected_cases_supported() -> bool:
    return _accepts_keyword(preview_remote_command, "case_ids") and _accepts_keyword(run_remote_cli, "case_ids")


def _render_execution_status(container, *, allow_reset_button: bool) -> dict[str, object]:
    task_status = ui_task_status()
    with container.container():
        if task_status.get("locked"):
            task_name = task_status.get("task") or "-"
            started_at = task_status.get("started_at") or "-"
            if task_status.get("active") and task_status.get("thread_alive"):
                st.warning(f"后台任务仍在运行：{task_name}")
                st.caption(f"开始时间：{started_at}")
                if task_status.get("stop_requested"):
                    st.info("已发送停止请求，正在清理当前任务...")
                elif allow_reset_button and st.button(
                    "停止当前任务",
                    type="secondary",
                    use_container_width=True,
                ):
                    if request_ui_task_stop():
                        st.info("已发送停止请求，正在清理当前任务...")
                        st.rerun()
                    else:
                        st.warning("当前任务已结束，无需停止。")
            else:
                st.warning("检测到残留执行锁，当前没有活动后台线程。")
                st.caption(f"上次任务：{task_name}；开始时间：{started_at}")
                if allow_reset_button and st.button("解除残留执行锁", use_container_width=True):
                    if reset_stale_ui_task_lock():
                        st.success("已解除残留执行锁，可以重新启动执行。")
                        st.rerun()
                    else:
                        st.error("后台任务仍在运行，暂不能解除执行锁。")
        else:
            st.success("空闲，可以启动执行。")
    return task_status


def _refresh_execution_status(container, *, thread: threading.Thread | None = None) -> dict[str, object]:
    if thread and thread.is_alive():
        deadline = time.time() + 1.0
        while time.time() < deadline:
            status = ui_task_status()
            if status.get("locked") or not thread.is_alive():
                break
            time.sleep(0.05)
    return _render_execution_status(container, allow_reset_button=False)


@st.cache_data(ttl=30, show_spinner="正在读取远程节点...")
def _load_remote_hosts() -> list[dict[str, str]]:
    return discover_remote_hosts()


@st.cache_data(ttl=30)
def _load_directory_modules() -> list[str]:
    tests_root = _PROJECT_ROOT / "tests" / "p0"
    if not tests_root.exists():
        return []
    return sorted(
        item.name
        for item in tests_root.iterdir()
        if item.is_dir() and item.name != "__pycache__"
    )


for c in cases:
    st.session_state.setdefault(_case_key(c["id"]), True)

selected_ids: list[str] = [
    case["id"]
    for case in cases
    if bool(st.session_state.get(_case_key(case["id"]), True))
]
case_by_id = {case["id"]: case for case in cases}
selected_cases: list[dict] = [case_by_id[case_id] for case_id in selected_ids if case_id in case_by_id]
selected_count = len(selected_ids)
(
    require_internal_account,
    require_member_ids,
    require_member_api,
    require_case_external,
) = _selected_account_requirements(selected_ids)
account_group_options = _account_group_options()
account_group_labels = list(account_group_options)

# ═══════════════════════════════════════════════════════════════════
# 侧边栏：筛选 & 批量操作
# ═══════════════════════════════════════════════════════════════════

remote_host_name = ""
remote_run_type = "远程预检"
remote_scope_label = "远程预检"
remote_scope = "precheck"
remote_value = ""
remote_attach_existing = False
remote_collect_artifacts = False
remote_sync_before_run = False
remote_ssh_host = ""
remote_ssh_port = 22
remote_ssh_username = ""
remote_ssh_password = ""
remote_cache_enabled = True
remote_connection_ready = False
selected_remote_host: dict[str, str] | None = None
local_account_group_slot = ACCOUNT_GROUP_SLOTS[0]
remote_account_group_slot = ACCOUNT_GROUP_SLOTS[1]
local_account_missing: list[str] = []
remote_account_missing: list[str] = []
concurrent_group_conflicts: list[str] = []
health_clicked = False
code_status_clicked = False
code_sync_clicked = False

with st.sidebar:
    st.header("执行状态")
    task_status_container = st.empty()
    task_status = _render_execution_status(task_status_container, allow_reset_button=True)

    st.divider()
    st.header("筛选")
    module_filter = st.selectbox(
        "业务模块",
        options=["全部模块", *module_names],
        help="只控制页面上显示哪些模块；不会取消勾选，也不会改变执行范围。",
    )
    case_keyword = st.text_input(
        "搜索用例",
        placeholder="输入模块、中文名、类名、方法名或 test_id",
        help="只缩小列表显示；不会清空已勾选状态，也不会改变执行范围。",
    ).strip()
    show_only_selected_modules = st.checkbox(
        "只看已选模块",
        value=False,
        help="仅隐藏当前未选择任何用例的模块，不会改变已勾选状态。",
    )
    if module_filter == "全部模块":
        show_modules = list(module_names)
    else:
        show_modules = [module_filter]
    if show_only_selected_modules:
        show_modules = [
            module_name
            for module_name in show_modules
            if _selected_count(by_module[module_name]) > 0
        ]
    hidden_module_count = len(set(module_names) - set(show_modules))
    if hidden_module_count:
        st.caption(f"已隐藏 {hidden_module_count} 个模块；隐藏不等于取消执行。")

    st.divider()
    st.header("运行位置")
    execution_mode = st.radio(
        "执行位置",
        options=["本机", "远程节点", "本机 + Mac 远程"],
        horizontal=True,
        help="同步模式会让 Windows 本机和 macOS 远程节点同时执行同一批已勾选用例。",
    )

    if execution_mode in {"本机", "本机 + Mac 远程"}:
        attach_existing = st.checkbox(
            "连接已打开的 APP",
            value=True,
            help="勾选：连接已手动启动的 DICloak APP。\n取消：框架自动启动新 APP。",
        )
        if execution_mode == "本机":
            st.caption("本机模式执行全部已勾选用例。")
        else:
            st.caption("同步模式会在两个独立团队中并行执行同一批用例。")
    else:
        attach_existing = True
        st.caption("远程模式选择“执行用例”时，会按下方已勾选用例执行。")

    st.markdown("**执行账号组**")
    if not _ACCOUNT_GROUPS_PATH.exists():
        st.warning("尚未保存账号组；当前组 1 从 config.yaml 临时迁移，组 2 为空。请先到“账号组”页面保存。")

    if execution_mode == "本机":
        local_group_label = st.selectbox(
            "本机账号组",
            options=account_group_labels,
            index=0,
            help="本机子进程只会收到当前选中组的账号数据。",
        )
        local_account_group_slot = account_group_options[local_group_label]
    elif execution_mode == "远程节点":
        remote_group_label = st.selectbox(
            "远程账号组",
            options=account_group_labels,
            index=1,
            help="选中组会通过临时配置安全传给远端，执行结束后删除。",
        )
        remote_account_group_slot = account_group_options[remote_group_label]
    else:
        local_group_label = st.selectbox(
            "Windows 本机账号组",
            options=account_group_labels,
            index=0,
        )
        remote_group_label = st.selectbox(
            "macOS 远程账号组",
            options=account_group_labels,
            index=1,
        )
        local_account_group_slot = account_group_options[local_group_label]
        remote_account_group_slot = account_group_options[remote_group_label]
        if local_account_group_slot == remote_account_group_slot:
            st.error("同步执行必须选择两个不同账号组，避免两个系统同时操作同一团队数据。")
        else:
            concurrent_group_conflicts = concurrent_account_group_conflicts(
                account_groups[local_account_group_slot],
                account_groups[remote_account_group_slot],
            )
            if concurrent_group_conflicts:
                st.error(
                    "两个账号组不能用于同步执行："
                    f"{'、'.join(concurrent_group_conflicts)}。请确认两组属于不同账号和不同团队。"
                )

    local_account_missing = account_group_missing_fields(
        account_groups[local_account_group_slot],
        require_internal=require_internal_account,
        require_member_ids=require_member_ids,
        require_member_api=require_member_api,
        require_case_external=require_case_external,
    )
    remote_account_missing = account_group_missing_fields(
        account_groups[remote_account_group_slot],
        require_internal=require_internal_account,
        require_member_ids=require_member_ids,
        require_member_api=require_member_api,
        require_case_external=require_case_external,
    )

    st.divider()
    st.caption(f"共 {len(cases)} 条用例 / {len(module_names)} 个模块")

local_account_profile = runtime_account_profile(account_groups[local_account_group_slot])
remote_account_profile = runtime_account_profile(account_groups[remote_account_group_slot])

if execution_mode in {"远程节点", "本机 + Mac 远程"}:
    st.subheader("远程节点执行")
    st.caption("选择节点和运行方式，确认选项后即可执行。连接维护与排障操作按需展开。")
    try:
        remote_hosts = _load_remote_hosts()
    except Exception as exc:
        remote_hosts = []
        st.error(f"远程节点配置读取失败：{exc}")
    if execution_mode == "本机 + Mac 远程":
        remote_hosts = [
            host
            for host in remote_hosts
            if str(host.get("platform", "")).strip().lower() in {"mac", "macos", "darwin", "macos-arm64"}
        ]

    host_labels = [
        f"{host['name']} ({host.get('platform') or 'unknown'})"
        for host in remote_hosts
    ]
    if not remote_hosts:
        st.warning("未发现启用的远程节点；请根据 `config/remote_hosts.example.yaml` 创建 `config/remote_hosts.yaml`。")

    st.markdown(
        '<div class="dicloak-remote-section-title is-first">执行节点</div>',
        unsafe_allow_html=True,
    )
    with st.container(border=True, key="dicloak_remote_node_card"):
        node_select_col, node_summary_col, node_action_col = st.columns(
            [1.65, 2.4, 0.8],
            vertical_alignment="center",
        )
        with node_select_col:
            selected_host_label = st.selectbox(
                "远程节点",
                options=host_labels,
                disabled=not host_labels,
                help="节点来自 config/remote_hosts.yaml；通常只需要选择要执行的系统。",
            )
        if selected_host_label and host_labels:
            selected_remote_host = remote_hosts[host_labels.index(selected_host_label)]
            remote_host_name = selected_remote_host["name"]

    if selected_remote_host:
        try:
            connection_cache = load_remote_connection_cache()
        except Exception as exc:
            connection_cache = {}
            st.warning(f"远程连接缓存读取失败：{exc}")

        cached_connection = connection_cache.get(remote_host_name, {})
        default_ssh_host = cached_connection.get("host") or selected_remote_host.get("host", "")
        default_ssh_port = _safe_port(cached_connection.get("port") or selected_remote_host.get("port", 22))
        default_ssh_username = cached_connection.get("username") or selected_remote_host.get("username", "")
        cached_ssh_password = cached_connection.get("password", "")
        host_key = f"remote_connection_host_{remote_host_name}"
        port_key = f"remote_connection_port_{remote_host_name}"
        username_key = f"remote_connection_username_{remote_host_name}"
        password_key = f"remote_connection_password_{remote_host_name}"
        remember_key = f"remote_connection_remember_password_{remote_host_name}"
        edit_key = f"remote_connection_editor_{remote_host_name}"
        st.session_state.setdefault(host_key, default_ssh_host)
        st.session_state.setdefault(port_key, default_ssh_port)
        st.session_state.setdefault(username_key, default_ssh_username)
        st.session_state.setdefault(password_key, cached_ssh_password)
        st.session_state.setdefault(remember_key, True)
        st.session_state.setdefault(edit_key, not bool(default_ssh_host and default_ssh_username))

        remote_ssh_host = str(st.session_state[host_key]).strip()
        remote_ssh_port = _safe_port(st.session_state[port_key])
        remote_ssh_username = str(st.session_state[username_key]).strip()
        remote_ssh_password = str(st.session_state[password_key])
        remote_cache_enabled = True

        with node_summary_col:
            password_status = "密码已保存到本机" if cached_ssh_password else "密码未保存"
            cache_status = cached_connection.get("updated_at") or "使用节点默认连接"
            st.markdown(
                f'<div class="dicloak-remote-node-name">{remote_host_name}</div>'
                f'<div class="dicloak-remote-node-meta">{selected_remote_host.get("platform") or "unknown"}'
                f' · {remote_ssh_username or "-"}@{remote_ssh_host or "-"}:{remote_ssh_port}</div>'
                f'<div class="dicloak-remote-status">{password_status} · {cache_status}</div>',
                unsafe_allow_html=True,
            )
        with node_action_col:
            if st.button(
                "编辑连接" if not st.session_state[edit_key] else "收起",
                icon=":material/edit:" if not st.session_state[edit_key] else ":material/expand_less:",
                use_container_width=True,
                key=f"toggle_{edit_key}",
            ):
                st.session_state[edit_key] = not st.session_state[edit_key]
                st.rerun()

        if st.session_state[edit_key]:
            with st.container(border=True, key="dicloak_remote_connection_editor"):
                conn_host_col, conn_port_col, conn_user_col = st.columns([2, 0.8, 1.5])
                with conn_host_col:
                    remote_ssh_host = st.text_input(
                        "SSH IP / 主机",
                        value=remote_ssh_host,
                        key=f"{host_key}_input",
                        placeholder="例如 192.168.20.160",
                    ).strip()
                    st.session_state[host_key] = remote_ssh_host
                with conn_port_col:
                    remote_ssh_port = int(st.number_input(
                        "端口",
                        min_value=1,
                        max_value=65535,
                        value=remote_ssh_port,
                        step=1,
                        key=f"{port_key}_input",
                    ))
                    st.session_state[port_key] = remote_ssh_port
                with conn_user_col:
                    remote_ssh_username = st.text_input(
                        "用户名",
                        value=remote_ssh_username,
                        key=f"{username_key}_input",
                        placeholder="例如 dic / tianji",
                    ).strip()
                    st.session_state[username_key] = remote_ssh_username

                password_col, remember_col, save_col = st.columns([2.8, 1.2, 0.9], vertical_alignment="bottom")
                with password_col:
                    remote_ssh_password = st.text_input(
                        "SSH 密码",
                        value=remote_ssh_password,
                        type="password",
                        key=f"{password_key}_input",
                        help="清空后保存即可删除本机密码。密码不会进入 Git、远端同步或日志。",
                    )
                    st.session_state[password_key] = remote_ssh_password
                with remember_col:
                    remember_password = st.checkbox(
                        "记住 SSH 密码",
                        value=bool(st.session_state[remember_key]),
                        key=f"{remember_key}_input",
                        help="使用当前 Windows 用户的 DPAPI 加密并保存到本机。",
                    )
                    st.session_state[remember_key] = remember_password
                remote_connection_ready = bool(remote_host_name and remote_ssh_host and remote_ssh_username)
                with save_col:
                    save_connection_clicked = st.button(
                        "保存连接",
                        icon=":material/save:",
                        use_container_width=True,
                        disabled=not remote_connection_ready,
                        key=f"save_remote_connection_{remote_host_name}",
                    )
                if save_connection_clicked:
                    try:
                        save_remote_connection_cache(
                            remote_host_name,
                            ssh_host=remote_ssh_host,
                            ssh_port=remote_ssh_port,
                            ssh_username=remote_ssh_username,
                            ssh_password=remote_ssh_password if remember_password else "",
                        )
                        st.success("连接信息已保存到本机。" if remember_password else "连接信息已保存，本机密码已清除。")
                    except Exception as exc:
                        st.error(f"连接信息保存失败：{exc}")

        remote_ssh_host = str(st.session_state[host_key]).strip()
        remote_ssh_port = _safe_port(st.session_state[port_key])
        remote_ssh_username = str(st.session_state[username_key]).strip()
        remote_ssh_password = str(st.session_state[password_key])
        remember_password = bool(st.session_state[remember_key])
        remote_connection_ready = bool(remote_host_name and remote_ssh_host and remote_ssh_username)
        if not remote_connection_ready:
            st.warning("请在“编辑连接”中填写 SSH IP / 主机和用户名。")

        st.markdown('<div class="dicloak-remote-section-title">运行模式</div>', unsafe_allow_html=True)
        if execution_mode == "本机 + Mac 远程":
            remote_run_type = "执行用例"
            remote_scope_label = "同步执行"
            remote_scope = "cases"
            remote_value = ""
            with st.container(border=True, key="dicloak_remote_mode_sync"):
                st.markdown("**Windows + macOS 同步执行**")
                st.caption(f"两个执行端将同时运行下方已勾选的 {len(selected_ids)} 条用例。")
        else:
            mode_key = "remote_run_type_choice"
            st.session_state.setdefault(mode_key, "远程预检")
            precheck_col, cases_col = st.columns(2)
            with precheck_col:
                with st.container(key="dicloak_remote_mode_precheck"):
                    precheck_clicked = st.button(
                        "远程预检",
                        icon=":material/monitor_heart:",
                        type="primary" if st.session_state[mode_key] == "远程预检" else "secondary",
                        use_container_width=True,
                    )
                    st.caption("检查远端环境、依赖和项目配置，不运行用例。")
            with cases_col:
                with st.container(key="dicloak_remote_mode_cases"):
                    cases_clicked = st.button(
                        "执行用例",
                        icon=":material/play_arrow:",
                        type="primary" if st.session_state[mode_key] == "执行用例" else "secondary",
                        use_container_width=True,
                    )
                    st.caption(f"运行下方已勾选的 {len(selected_ids)} 条用例，并生成执行结果。")
            if precheck_clicked:
                st.session_state[mode_key] = "远程预检"
                st.rerun()
            elif cases_clicked:
                st.session_state[mode_key] = "执行用例"
                st.rerun()
            remote_run_type = st.session_state[mode_key]
            if remote_run_type == "执行用例":
                remote_scope_label = "执行用例"
                remote_scope = "cases"
                remote_value = ""
                if not _remote_selected_cases_supported():
                    st.error("远程按勾选用例执行需要重启 Streamlit 后端，请重启 UI 后再运行。")
            else:
                remote_scope_label = "远程预检"
                remote_scope = "precheck"
                remote_value = ""

        st.markdown('<div class="dicloak-remote-section-title">执行选项</div>', unsafe_allow_html=True)
        with st.container(border=True, key="dicloak_remote_options"):
            option_attach_col, option_artifact_col, option_sync_col = st.columns(3)
            with option_attach_col:
                remote_attach_existing = st.checkbox(
                    "使用远端已打开 APP",
                    value=False,
                    disabled=remote_scope == "precheck",
                    help="勾选后给远端 run.py 追加 --attach-existing-app；预检不使用该选项。",
                )
                st.caption("直接连接远端当前运行中的 APP。")
            with option_artifact_col:
                remote_collect_artifacts = st.checkbox(
                    "执行后拉取产物",
                    value=True,
                    help="执行结束后拉取远端本次新增或修改的 logs、screenshots、reports 到本机 remote_artifacts。",
                )
                st.caption("收集日志、截图和测试报告。")
            with option_sync_col:
                remote_sync_before_run = st.checkbox(
                    "执行前同步当前代码",
                    value=False,
                    help="执行用例前先发布本地当前工作区到远端快照；默认关闭，避免误同步。",
                )
                st.caption("发布当前工作区后再启动任务。")

        with st.container(key="dicloak_remote_tools"):
            with st.expander("检查与同步", expanded=False, icon=":material/sync:"):
                col_health, col_code_status, col_code_sync = st.columns(3)
                with col_health:
                    health_clicked = st.button(
                        "检查节点",
                        icon=":material/monitor_heart:",
                        use_container_width=True,
                        disabled=not remote_connection_ready,
                        help="只读检查远端项目目录、run.py、配置、venv、Python 依赖和 APP 路径，不启动 APP、不跑用例。",
                    )
                with col_code_status:
                    code_status_clicked = st.button(
                        "检查代码",
                        icon=":material/difference:",
                        use_container_width=True,
                        disabled=not remote_connection_ready,
                        help="比较远端当前快照和本地当前工作区，检查是否会跑旧代码。",
                    )
                with col_code_sync:
                    code_sync_clicked = st.button(
                        "同步当前代码",
                        icon=":material/cloud_upload:",
                        use_container_width=True,
                        disabled=not remote_connection_ready,
                        help="通过 SFTP 发布本地当前工作区到远端新快照，保留远端配置和旧快照。",
                    )
                st.caption("用于执行前排查节点状态或手动发布代码。")

        with st.container(key="dicloak_remote_advanced"):
            with st.expander("高级信息", expanded=False, icon=":material/tune:"):
                if remote_scope == "cases" and not _remote_selected_cases_supported():
                    st.warning("当前 Streamlit 后端未加载支持按勾选用例执行的版本，重启 UI 后可查看远程命令预览。")
                else:
                    try:
                        command_preview = preview_remote_command(
                            remote_host_name,
                            remote_scope,
                            remote_value,
                            attach_existing_app=remote_attach_existing,
                            case_ids=selected_ids if remote_scope == "cases" else None,
                        )
                        st.markdown("**命令预览**")
                        st.code(command_preview, language="bash")
                    except Exception as exc:
                        st.warning(f"远程命令预览失败：{exc}")
                st.markdown("**节点配置**")
                st.table(_remote_host_details(
                    selected_remote_host,
                    current_host=remote_ssh_host,
                    current_port=remote_ssh_port,
                    current_username=remote_ssh_username,
                    password_provided=bool(remote_ssh_password),
                    cache_enabled=remote_cache_enabled,
                ))
                st.markdown("**平台能力**")
                st.table(remote_capability_matrix())

if execution_mode in {"本机", "本机 + Mac 远程"} and local_account_missing:
    st.error(f"Windows 本机账号组缺少：{'、'.join(local_account_missing)}。请到“账号组”页面补齐。")
if execution_mode in {"远程节点", "本机 + Mac 远程"} and remote_scope == "cases" and remote_account_missing:
    remote_account_label = "macOS 远程账号组" if execution_mode == "本机 + Mac 远程" else "远程账号组"
    st.error(f"{remote_account_label}缺少：{'、'.join(remote_account_missing)}。请到“账号组”页面补齐。")

# ═══════════════════════════════════════════════════════════════════
# 主体：用例选择列表
# ═══════════════════════════════════════════════════════════════════

visible_case_count = 0
show_case_list = not (execution_mode == "远程节点" and remote_scope == "precheck")
visible_modules: list[str] = []
visible_cases_by_module: dict[str, list[dict]] = {}

if not show_case_list:
    st.info("远程预检只检查远端环境，不运行用例，当前不展示用例列表。")
else:
    for mod in module_names:
        if mod not in show_modules:
            continue

        mod_cases = [
            case
            for case in by_module[mod]
            if _case_matches_keyword(case, case_keyword)
        ]
        if not mod_cases:
            continue
        visible_case_count += len(mod_cases)
        visible_modules.append(mod)
        visible_cases_by_module[mod] = mod_cases

    if visible_case_count == 0:
        st.info("当前筛选条件下没有可显示的用例。")
    else:
        _render_case_selection_panel(visible_modules, visible_cases_by_module)

# ═══════════════════════════════════════════════════════════════════
# 运行按钮
# ═══════════════════════════════════════════════════════════════════

st.markdown('<div class="dicloak-runbar"></div>', unsafe_allow_html=True)
col_info, col_btn = st.columns([3, 1], vertical_alignment="center")
with col_btn:
    if execution_mode == "本机":
        run_label = f"▶ 运行选中（{len(selected_ids)} 条）"
        run_disabled = len(selected_ids) == 0 or bool(local_account_missing)
    elif execution_mode == "本机 + Mac 远程":
        run_label = f"▶ Windows + macOS 同步运行（{len(selected_ids)} 条）"
        run_disabled = (
            len(selected_ids) == 0
            or not remote_connection_ready
            or bool(local_account_missing)
            or bool(remote_account_missing)
            or local_account_group_slot == remote_account_group_slot
            or bool(concurrent_group_conflicts)
            or not _remote_selected_cases_supported()
        )
    else:
        run_label = _remote_run_button_label(remote_scope_label, remote_value, case_count=len(selected_ids))
        run_disabled = (
            not remote_connection_ready
            or (remote_scope == "cases" and len(selected_ids) == 0)
            or (remote_scope == "cases" and not _remote_selected_cases_supported())
            or (remote_scope == "cases" and bool(remote_account_missing))
        )
    if task_status.get("locked"):
        run_disabled = True
    run_clicked = st.button(
        run_label,
        type="primary",
        use_container_width=True,
        disabled=run_disabled,
    )
with col_info:
    st.markdown(f"**准备执行：{len(selected_ids)} 条用例**")
    if execution_mode == "本机":
        st.caption("本机执行全部已勾选用例；显示模块和搜索显示只影响列表可见性。")
    elif execution_mode == "本机 + Mac 远程":
        st.caption("Windows 与 macOS 使用不同账号组并行执行相同用例；停止任务会同时中断两个执行端。")
    elif remote_scope == "precheck":
        st.caption("当前会执行远程预检，不会运行用例；如需跑用例，请把运行类型改为“执行用例”。")
    else:
        st.caption("远程执行会使用下方已勾选用例；显示模块和搜索显示只影响列表可见性。")

# ═══════════════════════════════════════════════════════════════════
# 执行逻辑：后台线程 + 前台轮询日志
# ═══════════════════════════════════════════════════════════════════

if run_clicked or health_clicked or code_status_clicked or code_sync_clicked:
    # ── 占位容器（运行中动态更新） ──
    log_placeholder = st.empty()
    status_placeholder = st.empty()
    progress_placeholder = st.empty()

    log_queue: queue.Queue = queue.Queue()
    stop_event = create_ui_stop_event()
    progress_platforms, progress_default_platform, show_case_progress = _progress_platforms_for_run(
        execution_mode,
        remote_scope,
    )
    show_case_progress = show_case_progress and bool(selected_cases) and bool(run_clicked)

    if execution_mode in {"远程节点", "本机 + Mac 远程"} and remote_cache_enabled and remote_connection_ready:
        try:
            save_remote_connection_cache(
                remote_host_name,
                ssh_host=remote_ssh_host,
                ssh_port=remote_ssh_port,
                ssh_username=remote_ssh_username,
                ssh_password=remote_ssh_password if remember_password else "",
            )
        except Exception as exc:
            st.warning(f"连接缓存保存失败：{exc}")

    # 启动后台执行线程
    if health_clicked:
        thread = threading.Thread(
            target=check_remote_host,
            args=(remote_host_name, log_queue),
            kwargs={
                "ssh_host": remote_ssh_host,
                "ssh_port": remote_ssh_port,
                "ssh_username": remote_ssh_username,
                "ssh_password": remote_ssh_password,
                "stop_event": stop_event,
            },
            daemon=True,
        )
    elif code_status_clicked:
        thread = threading.Thread(
            target=check_remote_code,
            args=(remote_host_name, log_queue),
            kwargs={
                "ssh_host": remote_ssh_host,
                "ssh_port": remote_ssh_port,
                "ssh_username": remote_ssh_username,
                "ssh_password": remote_ssh_password,
                "stop_event": stop_event,
            },
            daemon=True,
        )
    elif code_sync_clicked:
        thread = threading.Thread(
            target=sync_remote_code,
            args=(remote_host_name, log_queue),
            kwargs={
                "ssh_host": remote_ssh_host,
                "ssh_port": remote_ssh_port,
                "ssh_username": remote_ssh_username,
                "ssh_password": remote_ssh_password,
                "stop_event": stop_event,
            },
            daemon=True,
        )
    elif execution_mode == "本机":
        thread = threading.Thread(
            target=run_selected_tests,
            args=(selected_ids, log_queue),
            kwargs={
                "attach_existing_app": attach_existing,
                "account_profile": local_account_profile,
                "stop_event": stop_event,
            },
            daemon=True,
        )
    elif execution_mode == "本机 + Mac 远程":
        thread = threading.Thread(
            target=run_local_and_remote,
            args=(selected_ids, log_queue),
            kwargs={
                "local_attach_existing_app": attach_existing,
                "local_account_profile": local_account_profile,
                "remote_host_name": remote_host_name,
                "remote_attach_existing_app": remote_attach_existing,
                "remote_collect_artifacts": remote_collect_artifacts,
                "remote_sync_before_run": remote_sync_before_run,
                "remote_ssh_host": remote_ssh_host,
                "remote_ssh_port": remote_ssh_port,
                "remote_ssh_username": remote_ssh_username,
                "remote_ssh_password": remote_ssh_password,
                "remote_account_profile": remote_account_profile,
                "stop_event": stop_event,
            },
            daemon=True,
        )
    else:
        thread = threading.Thread(
            target=run_remote_cli,
            args=(remote_host_name, remote_scope, remote_value, log_queue),
            kwargs={
                "attach_existing_app": remote_attach_existing,
                "collect_artifacts": remote_collect_artifacts,
                "sync_before_run": remote_sync_before_run,
                "ssh_host": remote_ssh_host,
                "ssh_port": remote_ssh_port,
                "ssh_username": remote_ssh_username,
                "ssh_password": remote_ssh_password,
                "case_ids": selected_ids if remote_scope == "cases" else None,
                "account_profile": remote_account_profile if remote_scope == "cases" else None,
                "stop_event": stop_event,
            },
            daemon=True,
        )
    thread.start()
    _refresh_execution_status(task_status_container, thread=thread)

    # 前台轮询 queue，实时刷新日志
    log_lines: list[str] = []
    last_log_time = time.time()
    idle_warning_shown = False
    if show_case_progress:
        _render_case_progress(
            progress_placeholder,
            selected_cases=selected_cases,
            log_lines=log_lines,
            platforms=progress_platforms,
            default_platform=progress_default_platform,
        )
    if health_clicked:
        status_placeholder.info("⏳ 正在检查远程节点...")
    elif code_status_clicked:
        status_placeholder.info("⏳ 正在检查远端代码...")
    elif code_sync_clicked:
        status_placeholder.info("⏳ 正在同步远端代码...")
    else:
        status_placeholder.info("⏳ 正在执行...")

    received_sentinel = False
    try:
        while True:
            try:
                msg = log_queue.get(timeout=1)
                if msg is None:          # 哨兵：执行结束
                    received_sentinel = True
                    break
                log_lines.append(msg)
                last_log_time = time.time()
                idle_warning_shown = False
                _refresh_execution_status(task_status_container, thread=thread)
                # 只保留最近日志行避免 UI 卡顿
                display = "\n".join(log_lines[-_LOG_DISPLAY_LINES:])
                log_placeholder.code(display, language="text", height=_LOG_DISPLAY_HEIGHT)
                if show_case_progress and _case_progress_log_relevant(msg):
                    _render_case_progress(
                        progress_placeholder,
                        selected_cases=selected_cases,
                        log_lines=log_lines,
                        platforms=progress_platforms,
                        default_platform=progress_default_platform,
                    )
            except queue.Empty:
                _refresh_execution_status(task_status_container, thread=thread)
                if not thread.is_alive():
                    break
                idle_seconds = int(time.time() - last_log_time)
                if idle_seconds >= _LOG_IDLE_WARNING_SECONDS and not idle_warning_shown:
                    status_placeholder.warning(
                        f"⏳ 后台仍在执行，但已 {idle_seconds} 秒没有新日志。"
                        "如果 APP/CDP 或系统弹窗卡住，请到本机窗口检查当前状态。"
                    )
                    idle_warning_shown = True
    finally:
        # Streamlit 右上角 Stop/页面重跑会中断本脚本；同步取消后台任务。
        if not received_sentinel and thread.is_alive():
            request_ui_task_stop(stop_event)
    _refresh_execution_status(task_status_container)
    if show_case_progress:
        _render_case_progress(
            progress_placeholder,
            selected_cases=selected_cases,
            log_lines=log_lines,
            platforms=progress_platforms,
            default_platform=progress_default_platform,
        )

    # ═══════════════════════════════════════════════════════════════
    # 结果解析与展示
    # ═══════════════════════════════════════════════════════════════

    full_text = "\n".join(log_lines)
    log_placeholder.code(
        _unsuccessful_log_text(full_text),
        language="text",
        height=_LOG_DISPLAY_HEIGHT,
    )

    if health_clicked or code_status_clicked or code_sync_clicked or execution_mode in {"远程节点", "本机 + Mac 远程"}:
        _render_remote_result_summary(log_lines)

    combined_summaries = (
        _parse_prefixed_result_summaries(log_lines)
        if execution_mode == "本机 + Mac 远程" and run_clicked
        else {}
    )
    if combined_summaries:
        st.subheader("同步执行结果")
        result_tabs = st.tabs(["Windows 本机", "macOS 远程"])
        has_failure = False
        for result_tab, label in zip(result_tabs, ("Windows", "macOS")):
            with result_tab:
                target_summary = combined_summaries.get(label)
                if not target_summary:
                    st.warning(f"{label} 未生成可解析的结果统计，请查看上方日志。")
                    has_failure = True
                    continue
                _render_metrics(target_summary)
                _, _, target_failed, target_errors, _, _, _ = target_summary
                if target_failed or target_errors:
                    has_failure = True
                    prefix = f"[{label}] "
                    target_text = "\n".join(
                        line[len(prefix):]
                        for line in log_lines
                        if line.startswith(prefix)
                    )
                    with st.expander("失败/错误详情", expanded=True):
                        failure_details = _failure_detail_text(target_text)
                        st.code(failure_details or "详情请查看上方完整日志。", language="text")
        if has_failure:
            status_placeholder.warning("同步执行完成，至少一个执行端存在失败、错误或缺少结果。")
        else:
            status_placeholder.success("Windows 本机与 macOS 远程同步执行完成")
    else:
        # 用正则从最终总结行提取统计
        summary = _parse_result_summary(full_text)
        if summary:
            total, passed, failed, errors, skipped, flaky, rate = summary

            _render_metrics(summary)

            if failed > 0 or errors > 0:
                with st.expander("失败/错误详情", expanded=True):
                    failure_details = _failure_detail_text(full_text)
                    if failure_details:
                        st.code(failure_details, language="text")
                    else:
                        st.caption("详情请查看上方完整日志中的 CASE FAIL/CASE ERROR 行")

            status_placeholder.success("执行完成")
        else:
            level, message = _summary_missing_message(full_text)
            if level == "error":
                status_placeholder.error(message)
            elif level == "success":
                status_placeholder.success(message)
            else:
                status_placeholder.warning(message)
