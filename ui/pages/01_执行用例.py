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
from collections import defaultdict
import inspect
from pathlib import Path

# 确保项目根目录在 sys.path 中（ui/pages/ 的上上级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from streamlit_runner import (
    check_remote_host,
    check_remote_code,
    discover_cases,
    discover_remote_hosts,
    load_remote_connection_cache,
    preview_remote_command,
    remote_capability_matrix,
    reset_stale_ui_task_lock,
    run_remote_cli,
    run_selected_tests,
    save_remote_connection_cache,
    sync_remote_code,
    ui_task_status,
)

_LOG_IDLE_WARNING_SECONDS = 300
_LOG_DISPLAY_LINES = 200
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
_CASE_ERROR_BLOCK_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}.*?CASE (?:FAIL|ERROR).*?)(?="
    r"\n\d{4}-\d{2}-\d{2}.*?CASE START|\n\d{4}-\d{2}-\d{2}.*?Final test summary:|"
    r"\n远程执行完成|\Z)",
    re.DOTALL,
)
_UNITTEST_ERROR_BLOCK_RE = re.compile(
    r"(=+\n(?:ERROR|FAIL): .*?)(?=\n-+\nRan \d+ test|\Z)",
    re.DOTALL,
)

_REMOTE_RUN_TYPE_OPTIONS = ("远程预检", "执行用例")

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

try:
    cases = _load_cases()
except Exception as exc:
    st.error(f"用例发现失败：{exc}")
    st.caption("请确认 `config/config.yaml` 存在且格式正确；必要时先运行 `python run.py --config config/config.yaml --precheck`。")
    st.stop()

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


def _case_matches_keyword(case: dict, keyword: str) -> bool:
    if not keyword:
        return True
    haystack = " ".join(
        str(case.get(field, ""))
        for field in ("id", "module", "class_name", "method_name")
    ).lower()
    return keyword.lower() in haystack


def _summary_missing_message(log_text: str) -> tuple[str, str]:
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


def _failure_detail_text(log_text: str) -> str:
    blocks: list[str] = []
    for pattern in (_CASE_ERROR_BLOCK_RE, _UNITTEST_ERROR_BLOCK_RE):
        for match in pattern.finditer(log_text):
            block = match.group(1).strip()
            if block and block not in blocks:
                blocks.append(block)

    if blocks:
        return "\n\n".join(blocks)

    focused_lines = [
        line
        for line in log_text.splitlines()
        if "CASE FAIL" in line
        or "CASE ERROR" in line
        or line.startswith("FAIL: ")
        or line.startswith("ERROR: ")
    ]
    return "\n".join(focused_lines)


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
selected_count = len(selected_ids)

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
health_clicked = False
code_status_clicked = False
code_sync_clicked = False

with st.sidebar:
    st.header("显示设置")
    show_modules = st.multiselect(
        "显示模块（不影响执行）",
        options=module_names,
        default=module_names,
        help="只控制页面上显示哪些模块；不会取消勾选，也不会改变本机执行范围。",
    )
    case_keyword = st.text_input(
        "搜索显示",
        placeholder="输入模块、类名、方法名或 test_id",
        help="只缩小下方列表显示；不会清空已勾选状态，也不会改变本机执行范围。",
    ).strip()
    hidden_module_count = len(set(module_names) - set(show_modules))
    if hidden_module_count:
        st.caption(f"已隐藏 {hidden_module_count} 个模块；隐藏不等于取消执行。")

    st.divider()
    st.header("执行状态")
    task_status_container = st.empty()
    task_status = _render_execution_status(task_status_container, allow_reset_button=True)

    st.divider()
    st.header("用例选择")
    st.caption(f"当前已勾选 {selected_count}/{len(cases)} 条")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("✅ 全选", use_container_width=True):
            _set_all_cases_selected(True)
            st.rerun()
    with col_b:
        if st.button("⬜ 取消全选", use_container_width=True):
            _set_all_cases_selected(False)
            st.rerun()

    st.divider()
    st.header("运行位置")
    execution_mode = st.radio(
        "执行位置",
        options=["本机", "远程节点"],
        horizontal=True,
        help="本机模式按当前勾选用例执行；远程节点模式通过 SSH 在目标机器执行 CLI 命令。",
    )

    if execution_mode == "本机":
        attach_existing = st.checkbox(
            "连接已打开的 APP",
            value=True,
            help="勾选：连接已手动启动的 DICloak APP。\n取消：框架自动启动新 APP。",
        )
        st.caption("本机模式执行全部已勾选用例。")
    else:
        attach_existing = True
        st.caption("远程模式选择“执行用例”时，会按下方已勾选用例执行。")

    st.divider()
    st.caption(f"共 {len(cases)} 条用例 / {len(module_names)} 个模块")

if execution_mode == "远程节点":
    st.subheader("远程节点执行")
    try:
        remote_hosts = _load_remote_hosts()
    except Exception as exc:
        remote_hosts = []
        st.error(f"远程节点配置读取失败：{exc}")

    host_labels = [
        f"{host['name']} ({host.get('platform') or 'unknown'})"
        for host in remote_hosts
    ]
    if not remote_hosts:
        st.warning("未发现启用的远程节点；请根据 `config/remote_hosts.example.yaml` 创建 `config/remote_hosts.yaml`。")

    st.markdown("**选择节点**")
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

        remote_ssh_host = default_ssh_host
        remote_ssh_port = default_ssh_port
        remote_ssh_username = default_ssh_username

        st.markdown("**连接信息**")
        connection_caption = f"{remote_ssh_username or '-'}@{remote_ssh_host or '-'}:{remote_ssh_port}"
        if cached_connection.get("updated_at"):
            connection_caption += f" · 已加载本机缓存 {cached_connection['updated_at']}"
        else:
            connection_caption += " · 使用节点默认连接"
        st.caption(connection_caption)

        pass_col, edit_col = st.columns([2, 1])
        with pass_col:
            remote_ssh_password = st.text_input(
                "SSH 密码（本次 UI 会话）",
                value="",
                type="password",
                key=f"remote_ssh_password_{remote_host_name}",
                help="密码只保存在当前 Streamlit 会话内存里，不写入 YAML、不写入连接缓存、不进入日志。",
            )
        with edit_col:
            st.write("")
            st.caption("IP、端口和用户名可在下方修改。")

        with st.expander("修改 SSH 连接", expanded=not bool(default_ssh_host and default_ssh_username)):
            conn_host_col, conn_port_col, conn_user_col = st.columns([2, 1, 2])
            with conn_host_col:
                remote_ssh_host = st.text_input(
                    "SSH IP / 主机",
                    value=default_ssh_host,
                    key=f"remote_ssh_host_{remote_host_name}",
                    placeholder="例如 192.168.20.160",
                    help="用于本次 UI 远程操作的 SSH 地址；可缓存到本机，但不会写入仓库。",
                ).strip()
            with conn_port_col:
                remote_ssh_port = int(st.number_input(
                    "端口",
                    min_value=1,
                    max_value=65535,
                    value=default_ssh_port,
                    step=1,
                    key=f"remote_ssh_port_{remote_host_name}",
                ))
            with conn_user_col:
                remote_ssh_username = st.text_input(
                    "用户名",
                    value=default_ssh_username,
                    key=f"remote_ssh_username_{remote_host_name}",
                    placeholder="例如 dic / tianji",
                    help="用于本次 UI 远程操作的 SSH 用户名。",
                ).strip()

            cache_col, save_col = st.columns([2, 1])
            with cache_col:
                remote_cache_enabled = st.checkbox(
                    "缓存 IP、端口和用户名到本机",
                    value=True,
                    key=f"remote_cache_enabled_{remote_host_name}",
                    help="缓存文件为 config/remote_connection_cache.yaml，已加入 .gitignore；不会保存密码。",
                )
            remote_connection_ready = bool(remote_host_name and remote_ssh_host and remote_ssh_username)
            with save_col:
                if st.button(
                    "保存缓存",
                    use_container_width=True,
                    disabled=not remote_connection_ready,
                    help="只保存 IP、端口和用户名；密码不会保存。",
                ):
                    try:
                        save_remote_connection_cache(
                            remote_host_name,
                            ssh_host=remote_ssh_host,
                            ssh_port=remote_ssh_port,
                            ssh_username=remote_ssh_username,
                        )
                        st.success("连接缓存已保存。")
                    except Exception as exc:
                        st.error(f"连接缓存保存失败：{exc}")
        remote_connection_ready = bool(remote_host_name and remote_ssh_host and remote_ssh_username)
        if not remote_connection_ready:
            st.warning("请填写 SSH IP / 主机和用户名。")

        st.markdown("**运行类型**")
        type_col, info_col = st.columns([1, 2])
        with type_col:
            remote_run_type = st.selectbox(
                "运行类型",
                options=list(_REMOTE_RUN_TYPE_OPTIONS),
                help="远程预检只检查环境；执行用例才会运行测试。",
            )
        if remote_run_type == "远程预检":
            remote_scope_label = "远程预检"
            remote_scope = "precheck"
            remote_value = ""
            with info_col:
                st.info("当前只检查远端环境，不运行任何用例。")
        else:
            remote_scope_label = "执行用例"
            remote_scope = "cases"
            remote_value = ""
            with info_col:
                st.info(f"将远程执行下方已勾选的 {len(selected_ids)} 条用例。")
                if not _remote_selected_cases_supported():
                    st.error("远程按勾选用例执行需要重启 Streamlit 后端，请重启 UI 后再运行。")

        st.markdown("**执行选项**")
        option_attach_col, option_artifact_col, option_sync_col = st.columns(3)
        with option_attach_col:
            remote_attach_existing = st.checkbox(
                "使用远端已打开 APP",
                value=False,
                disabled=remote_scope == "precheck",
                help="勾选后给远端 run.py 追加 --attach-existing-app；预检不使用该选项。",
            )
        with option_artifact_col:
            remote_collect_artifacts = st.checkbox(
                "远程执行后拉取产物",
                value=True,
                help="执行结束后拉取远端本次新增或修改的 logs、screenshots、reports 到本机 remote_artifacts。",
            )
        with option_sync_col:
            remote_sync_before_run = st.checkbox(
                "执行前同步当前代码",
                value=False,
                help="执行用例前先发布本地当前工作区到远端快照；默认关闭，避免误同步。",
            )

        with st.expander("检查和同步", expanded=False):
            col_health, col_code_status, col_code_sync = st.columns(3)
            with col_health:
                health_clicked = st.button(
                    "检查远程节点",
                    use_container_width=True,
                    disabled=not remote_connection_ready,
                    help="只读检查远端项目目录、run.py、配置、venv、Python 依赖和 APP 路径，不启动 APP、不跑用例。",
                )
            with col_code_status:
                code_status_clicked = st.button(
                    "检查远端代码",
                    use_container_width=True,
                    disabled=not remote_connection_ready,
                    help="比较远端当前快照和本地当前工作区，检查是否会跑旧代码。",
                )
            with col_code_sync:
                code_sync_clicked = st.button(
                    "同步当前代码",
                    use_container_width=True,
                    disabled=not remote_connection_ready,
                    help="通过 SFTP 发布本地当前工作区到远端新快照，保留远端配置和旧快照。",
                )
            st.caption("日常执行一般只需要选择运行类型后点击底部运行按钮；这里用于排查环境或手动发布当前代码。")

        with st.expander("高级信息", expanded=False):
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

    st.caption("远程模式选择“执行用例”时，会按下方已勾选用例执行。")

# ═══════════════════════════════════════════════════════════════════
# 主体：用例选择列表
# ═══════════════════════════════════════════════════════════════════

visible_case_count = 0
show_case_list = not (execution_mode == "远程节点" and remote_scope == "precheck")

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
        all_mod_cases = by_module[mod]
        mod_selected_count = sum(
            1 for c in all_mod_cases
            if bool(st.session_state.get(_case_key(c["id"]), True))
        )

        col_name, col_count, col_select, col_clear = st.columns(
            [4, 1.2, 1.2, 1.2],
            vertical_alignment="center",
        )
        with col_name:
            st.markdown(f"**{mod}**")
        with col_count:
            st.markdown(f"已选 {mod_selected_count}/{len(all_mod_cases)}")
        with col_select:
            if st.button("选中模块", key=f"select_mod_{mod}", use_container_width=True):
                _set_case_selected(all_mod_cases, True)
                st.rerun()
        with col_clear:
            if st.button("取消模块", key=f"clear_mod_{mod}", use_container_width=True):
                _set_case_selected(all_mod_cases, False)
                st.rerun()

        with st.expander(
            f"查看用例（{len(mod_cases)} 条）",
            expanded=len(mod_cases) <= 3,
        ):
            for c in mod_cases:
                key = _case_key(c["id"])
                st.checkbox(
                    f"`{c['class_name']}.{c['method_name']}`",
                    key=key,
                    help=c["id"],
                )

    if visible_case_count == 0:
        st.info("当前筛选条件下没有可显示的用例。")

# ═══════════════════════════════════════════════════════════════════
# 运行按钮
# ═══════════════════════════════════════════════════════════════════

st.divider()
col_btn, col_info = st.columns([1, 3])
with col_btn:
    if execution_mode == "本机":
        run_label = f"▶ 运行选中（{len(selected_ids)} 条）"
        run_disabled = len(selected_ids) == 0
    else:
        run_label = _remote_run_button_label(remote_scope_label, remote_value, case_count=len(selected_ids))
        run_disabled = (
            not remote_connection_ready
            or (remote_scope == "cases" and len(selected_ids) == 0)
            or (remote_scope == "cases" and not _remote_selected_cases_supported())
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
    if execution_mode == "本机":
        st.caption("本机执行全部已勾选用例；显示模块和搜索显示只影响列表可见性。")
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

    log_queue: queue.Queue = queue.Queue()

    if execution_mode == "远程节点" and remote_cache_enabled and remote_connection_ready:
        try:
            save_remote_connection_cache(
                remote_host_name,
                ssh_host=remote_ssh_host,
                ssh_port=remote_ssh_port,
                ssh_username=remote_ssh_username,
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
            },
            daemon=True,
        )
    elif execution_mode == "本机":
        thread = threading.Thread(
            target=run_selected_tests,
            args=(selected_ids, log_queue),
            kwargs={"attach_existing_app": attach_existing},
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
            },
            daemon=True,
        )
    thread.start()
    _refresh_execution_status(task_status_container, thread=thread)

    # 前台轮询 queue，实时刷新日志
    log_lines: list[str] = []
    last_log_time = time.time()
    idle_warning_shown = False
    if health_clicked:
        status_placeholder.info("⏳ 正在检查远程节点...")
    elif code_status_clicked:
        status_placeholder.info("⏳ 正在检查远端代码...")
    elif code_sync_clicked:
        status_placeholder.info("⏳ 正在同步远端代码...")
    else:
        status_placeholder.info("⏳ 正在执行...")

    while True:
        try:
            msg = log_queue.get(timeout=1)
            if msg is None:          # 哨兵：执行结束
                break
            log_lines.append(msg)
            last_log_time = time.time()
            idle_warning_shown = False
            _refresh_execution_status(task_status_container, thread=thread)
            # 只保留最近日志行避免 UI 卡顿
            display = "\n".join(log_lines[-_LOG_DISPLAY_LINES:])
            log_placeholder.code(display, language="text", height=_LOG_DISPLAY_HEIGHT)
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
    _refresh_execution_status(task_status_container)

    # ═══════════════════════════════════════════════════════════════
    # 结果解析与展示
    # ═══════════════════════════════════════════════════════════════

    full_text = "\n".join(log_lines)

    if health_clicked or code_status_clicked or code_sync_clicked or execution_mode == "远程节点":
        _render_remote_result_summary(log_lines)

    # 用正则从最终总结行提取统计
    summary = _parse_result_summary(full_text)
    if summary:
        total, passed, failed, errors, skipped, flaky, rate = summary

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
                failure_details = _failure_detail_text(full_text)
                if failure_details:
                    st.code(failure_details, language="text")
                else:
                    st.caption("详情请查看上方完整日志中的 CASE FAIL/CASE ERROR 行")

        status_placeholder.success("✅ 执行完成")
    else:
        level, message = _summary_missing_message(full_text)
        if level == "error":
            status_placeholder.error(f"❌ {message}")
        elif level == "success":
            status_placeholder.success(f"✅ {message}")
        else:
            status_placeholder.warning(f"⚠️ {message}")
