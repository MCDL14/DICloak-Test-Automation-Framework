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
from collections import defaultdict
from pathlib import Path

# 确保项目根目录在 sys.path 中（ui/pages/ 的上上级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from streamlit_runner import discover_cases, run_selected_tests

# ═══════════════════════════════════════════════════════════════════
# 页面配置
# ═══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="执行用例", page_icon="🧪", layout="wide")
st.title("🧪 执行用例")

# ═══════════════════════════════════════════════════════════════════
# 加载用例（缓存 30 秒，避免每次交互都重新发现）
# ═══════════════════════════════════════════════════════════════════

@st.cache_data(ttl=30, show_spinner="正在发现用例...")
def _load_cases() -> list[dict]:
    return discover_cases()

cases = _load_cases()

# 按模块分组
by_module: dict[str, list[dict]] = defaultdict(list)
for c in cases:
    by_module[c["module"]].append(c)
module_names = sorted(by_module.keys())


def _case_key(case_id: str) -> str:
    return f"sel_{case_id}"


def _set_case_selected(case_list: list[dict], selected: bool) -> None:
    for case in case_list:
        st.session_state[_case_key(case["id"])] = selected


def _set_all_cases_selected(selected: bool) -> None:
    _set_case_selected(cases, selected)


for c in cases:
    st.session_state.setdefault(_case_key(c["id"]), True)

# ═══════════════════════════════════════════════════════════════════
# 侧边栏：筛选 & 批量操作
# ═══════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🔍 筛选模块")
    show_modules = st.multiselect(
        "只显示以下模块",
        options=module_names,
        default=module_names,
        help="取消勾选可隐藏对应模块的用例",
    )

    st.divider()

    # 批量选择按钮
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("✅ 全选", use_container_width=True):
            _set_all_cases_selected(True)
            st.rerun()
    with col_b:
        if st.button("⬜ 取消全选", use_container_width=True):
            _set_all_cases_selected(False)
            st.rerun()

    # 运行模式
    st.divider()
    st.header("⚙️ 运行模式")
    attach_existing = st.checkbox(
        "连接已打开的 APP",
        value=True,
        help="勾选：连接已手动启动的 DICloak APP。\n取消：框架自动启动新 APP。",
    )

    st.divider()
    st.caption(f"共 {len(cases)} 条用例 / {len(module_names)} 个模块")

# ═══════════════════════════════════════════════════════════════════
# 主体：用例选择列表
# ═══════════════════════════════════════════════════════════════════

selected_ids: list[str] = []

for mod in module_names:
    if mod not in show_modules:
        continue

    mod_cases = by_module[mod]
    # 模块折叠面板：用例数 ≤ 3 时默认展开
    with st.expander(
        f"📁 {mod}（{len(mod_cases)} 条）",
        expanded=len(mod_cases) <= 3,
    ):
        mod_selected_count = sum(
            1 for c in mod_cases
            if bool(st.session_state.get(_case_key(c["id"]), True))
        )
        col_select, col_clear, col_count = st.columns([1, 1, 4])
        with col_select:
            if st.button("选中本模块", key=f"select_mod_{mod}", use_container_width=True):
                _set_case_selected(mod_cases, True)
                st.rerun()
        with col_clear:
            if st.button("取消本模块", key=f"clear_mod_{mod}", use_container_width=True):
                _set_case_selected(mod_cases, False)
                st.rerun()
        with col_count:
            st.caption(f"已选 {mod_selected_count}/{len(mod_cases)} 条")

        # 逐条用例 checkbox
        for c in mod_cases:
            key = _case_key(c["id"])
            checked = st.checkbox(
                f"`{c['class_name']}.{c['method_name']}`",
                key=key,
                help=c["id"],
            )
            if checked:
                selected_ids.append(c["id"])

# ═══════════════════════════════════════════════════════════════════
# 运行按钮
# ═══════════════════════════════════════════════════════════════════

st.divider()
col_btn, col_info = st.columns([1, 3])
with col_btn:
    run_clicked = st.button(
        f"▶ 运行选中（{len(selected_ids)} 条）",
        type="primary",
        use_container_width=True,
        disabled=len(selected_ids) == 0,
    )

# ═══════════════════════════════════════════════════════════════════
# 执行逻辑：后台线程 + 前台轮询日志
# ═══════════════════════════════════════════════════════════════════

if run_clicked:
    # ── 占位容器（运行中动态更新） ──
    log_placeholder = st.empty()
    status_placeholder = st.empty()

    log_queue: queue.Queue = queue.Queue()

    # 启动后台执行线程
    thread = threading.Thread(
        target=run_selected_tests,
        args=(selected_ids, log_queue),
        kwargs={"attach_existing_app": attach_existing},
        daemon=True,
    )
    thread.start()

    # 前台轮询 queue，实时刷新日志
    log_lines: list[str] = []
    status_placeholder.info("⏳ 正在执行...")

    while True:
        try:
            msg = log_queue.get(timeout=1)
            if msg is None:          # 哨兵：执行结束
                break
            log_lines.append(msg)
            # 只保留最近 200 行避免 UI 卡顿
            display = "\n".join(log_lines[-200:])
            log_placeholder.code(display, language="text")
        except queue.Empty:
            # 超时无新日志，继续等待
            pass

    # ═══════════════════════════════════════════════════════════════
    # 结果解析与展示
    # ═══════════════════════════════════════════════════════════════

    full_text = "\n".join(log_lines)

    # 用正则从最终总结行提取统计
    m = re.search(
        r"运行完成 → 总计=(\d+) 通过=(\d+) 失败=(\d+) 错误=(\d+) 跳过=(\d+) flaky=(\d+) 通过率=([\d.]+)%",
        full_text,
    )
    if m:
        total, passed, failed, errors, skipped, flaky, rate = m.groups()
        total, passed, failed, errors, skipped, flaky = (
            int(total), int(passed), int(failed), int(errors), int(skipped), int(flaky)
        )

        # 指标卡片栏
        cols = st.columns(6)
        cols[0].metric("📊 总计", total)
        cols[1].metric("✅ 通过", passed)
        cols[2].metric("❌ 失败", failed, delta=None if failed == 0 else f"-{failed}")
        cols[3].metric("⚠️ 错误", errors)
        cols[4].metric("⏭️ 跳过", skipped)
        cols[5].metric("📈 通过率", f"{rate}%")

        # 失败详情
        if failed > 0 or errors > 0:
            with st.expander("🔍 失败/错误详情", expanded=True):
                # 提取 FAIL/ERROR 行
                fail_lines = [
                    line for line in log_lines
                    if "FAIL:" in line or "ERROR:" in line or "failed:" in line.lower()
                ]
                if fail_lines:
                    st.code("\n".join(fail_lines), language="text")
                else:
                    st.caption("详情请查看上方完整日志中的 FAIL/ERROR 行")

        status_placeholder.success("✅ 执行完成")
    else:
        status_placeholder.warning("⚠️ 执行完成，未能解析结果统计。请查看上方日志。")
