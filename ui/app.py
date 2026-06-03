"""Dicloak Streamlit UI 主入口 — 仪表盘概览.

==== 模块化设计 ====
- 本文件仅为 Streamlit 多页面入口，不包含执行/历史等业务逻辑。
- 业务逻辑分别在 ui/pages/ 下各文件，通过 streamlit_runner.py 共享执行器。
- 所有 UI 代码均为纯 Python，无 HTML/CSS/JS，修改布局只需调整 st.* 调用顺序。
- UI 代码放在 ui/ 子目录，与项目原有的 pages/（Page Object）完全隔离。

==== 如何添加新页面 ====
1. 在 ui/pages/ 目录新建 .py 文件（如 ui/pages/03_scheduler.py）
2. 文件开头写 st.set_page_config(...)
3. 在本文件添加 st.page_link(...) 导航入口
4. 重启 streamlit run ui/app.py

==== 如何调整 UI 排布 ====
- 调整卡片位置：修改 st.columns() 参数，交换 with 块顺序
- 添加侧边栏内容：在 with st.sidebar: 块内追加
- 修改主题/布局：修改 st.set_page_config 的 layout/initial_sidebar_state

==== 依赖关系 ====
  ui/app.py                     # 入口（本文件）
    └─ ui/pages/01_执行用例.py  # 执行用例页
    │    └─ streamlit_runner.py  # 共享执行器（项目根目录）
    │         ├─ core.runner      # 用例发现/排序/执行
    │         ├─ core.result      # AutomationTextRunner + RunResult
    │         └─ core.feishu      # 飞书通知
    └─ ui/pages/02_运行历史.py   # 运行历史页
         └─ logs/*.log          # 直接读取 log 文件
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中（无论从哪个目录启动 streamlit）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from core.config import load_config
from streamlit_runner import discover_cases

st.set_page_config(
    page_title="Dicloak 自动化测试",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════
# 侧边栏：项目配置信息
# ═══════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("⚙️ 配置")
    config_path = _PROJECT_ROOT / "config" / "config.yaml"
    try:
        config = load_config(config_path)
        st.success(f"配置加载成功: `{config_path}`")
        account = config.get("account", {})
        username = account.get("username", "—")
        st.metric("当前账号", username)
    except Exception as exc:
        st.error(f"配置加载失败: {exc}")

    st.divider()
    st.caption("Streamlit 多页面架构 | 纯 Python 组件 | 天然模块化")

# ═══════════════════════════════════════════════════════════════════
# 主页：仪表盘
# ═══════════════════════════════════════════════════════════════════

st.title("🧪 Dicloak 自动化测试平台")
st.caption("执行用例 · 查看结果 · 浏览历史")

@st.cache_data(ttl=30, show_spinner="正在统计用例...")
def _case_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in discover_cases():
        module_name = case.get("module") or "未知"
        counts[module_name] = counts.get(module_name, 0) + 1
    return counts


case_counts = _case_counts()
summary_modules = ["环境管理", "全局设置", "环境分组管理", "成员管理"]
cols = st.columns(len(summary_modules) + 1)
for index, module_name in enumerate(summary_modules):
    cols[index].metric(module_name, str(case_counts.get(module_name, 0)))
cols[-1].metric("总用例", str(sum(case_counts.values())))

st.divider()

# ── 快速入口：链接到各子页面 ──
st.subheader("📌 快速入口")
c1, c2, c3 = st.columns(3)
with c1:
    st.page_link("ui/pages/01_执行用例.py", label="▶ 执行用例", icon="🧪")
    st.caption("选择模块/用例 → 运行 → 实时查看日志和结果")
with c2:
    st.page_link("ui/pages/02_运行历史.py", label="📋 运行历史", icon="📂")
    st.caption("浏览历史 log 文件，回顾每次运行统计")
with c3:
    st.info("💡 更多页面：在 `ui/pages/` 目录新增 `.py` 文件即可自动注册")
