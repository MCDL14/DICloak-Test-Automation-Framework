"""Streamlit UI 专用执行器。

==== 设计原则 ====
- 尽量复用 AutomationRunner 的用例发现、优先级排序、APP 生命周期、CDP 校验能力。
- 通过 AutomationRunner._run_suite() 复用 CLI 的恢复钩子、失败截图、重试、flaky 统计。
- 通过自定义 IO 流 + logging Handler 将输出实时推送到 UI。
- 执行结束后调用 FeishuNotifier.send_summary() 保持飞书通知不变。
- UI 执行在进程内串行化，避免多个 Streamlit 会话同时抢占同一个 APP/CDP 和全局 logger。

==== 使用方式 ====
    from streamlit_runner import discover_cases, run_selected_tests

    cases = discover_cases()
    # ... 用户在 UI 中选择 test_ids ...
    run_selected_tests(test_ids, log_queue, attach_existing_app=True)
"""

from __future__ import annotations

import io
import logging
import queue
import sys
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from core.app import AppManager, AppStartupError
from core.case_module import get_test_case_module
from core.cdp_driver import CDPConnectionError, CDPDriver
from core.config import ConfigError, load_config
from core.logger import setup_logger
from core.remote_runner import (
    RemoteConfigError,
    RemoteHost,
    RemoteRunError,
    RemoteRunRequest,
    build_remote_command,
    collect_remote_artifacts,
    load_remote_hosts,
    run_remote_health_check,
    run_remote_tests,
)
from core.remote_sync import (
    check_remote_code_status,
    remote_release_root,
    sync_remote_project,
)
from core.result import RunResult
from core.run_metadata import log_run_end, log_run_start
from core.runner import AutomationRunner

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
REMOTE_HOSTS_PATH = PROJECT_ROOT / "config" / "remote_hosts.yaml"
REMOTE_CONNECTION_CACHE_PATH = PROJECT_ROOT / "config" / "remote_connection_cache.yaml"
_RUN_LOCK = threading.Lock()
_RUN_STATE_LOCK = threading.Lock()
_RUN_STATE: dict[str, Any] = {
    "active": False,
    "task": "",
    "started_at": "",
    "thread_ident": None,
}


def _mark_task_started(task: str) -> None:
    with _RUN_STATE_LOCK:
        _RUN_STATE.update(
            {
                "active": True,
                "task": task,
                "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "thread_ident": threading.get_ident(),
            }
        )


def _mark_task_finished() -> None:
    with _RUN_STATE_LOCK:
        _RUN_STATE.update(
            {
                "active": False,
                "task": "",
                "started_at": "",
                "thread_ident": None,
            }
        )


def _state_snapshot() -> dict[str, Any]:
    with _RUN_STATE_LOCK:
        return dict(_RUN_STATE)


def _thread_alive(thread_ident: int | None) -> bool:
    if thread_ident is None:
        return False
    return any(thread.ident == thread_ident and thread.is_alive() for thread in threading.enumerate())


def ui_task_status() -> dict[str, Any]:
    """Return current in-process UI execution lock state for Streamlit display."""
    state = _state_snapshot()
    state["locked"] = _RUN_LOCK.locked()
    state["thread_alive"] = _thread_alive(state.get("thread_ident"))
    return state


def reset_stale_ui_task_lock() -> bool:
    """Release only a stale UI lock whose recorded worker thread is no longer alive."""
    state = ui_task_status()
    if not state.get("locked"):
        _mark_task_finished()
        return True
    if state.get("active") and state.get("thread_alive"):
        return False
    try:
        _RUN_LOCK.release()
    except RuntimeError:
        pass
    _mark_task_finished()
    return True


def _acquire_run_lock(log_queue: queue.Queue, busy_message: str, task: str) -> bool:
    if not _RUN_LOCK.acquire(blocking=False):
        status = ui_task_status()
        detail = ""
        if status.get("task") or status.get("started_at"):
            detail = f" 当前任务={status.get('task') or '-'} 开始={status.get('started_at') or '-'}"
        log_queue.put(f"{busy_message}{detail}")
        log_queue.put(None)
        return False
    _mark_task_started(task)
    return True


def _release_run_lock() -> None:
    _mark_task_finished()
    try:
        _RUN_LOCK.release()
    except RuntimeError:
        pass


# ═══════════════════════════════════════════════════════════════════
# 自定义 IO 流：截获 unittest 输出 → 推送到 UI 的 queue
# ═══════════════════════════════════════════════════════════════════

class _QueueStream(io.StringIO):
    """写入时同时推送到 queue 的字符串流。

    unittest.TextTestRunner 默认输出到 stream，此类在 write() 时
    额外将非空行推送到 log_queue，供 UI 实时读取。
    """

    def __init__(self, log_queue: queue.Queue) -> None:
        super().__init__()
        self._log_queue = log_queue

    def write(self, s: str) -> int:
        text = s.rstrip()
        if text:
            self._log_queue.put(text)
        return super().write(s)


# ═══════════════════════════════════════════════════════════════════
# logging Handler：截获框架日志 → 推送到 UI 的 queue
# ═══════════════════════════════════════════════════════════════════

class _QueueLogHandler(logging.Handler):
    """将日志记录格式化后推送到 queue，供 UI 实时展示."""

    def __init__(self, log_queue: queue.Queue) -> None:
        super().__init__()
        self._log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        self._log_queue.put(self.format(record))


# ═══════════════════════════════════════════════════════════════════
# 公共 API
# ═══════════════════════════════════════════════════════════════════

def _build_config() -> dict[str, Any]:
    """加载项目配置，异常时抛出 RuntimeError."""
    try:
        return load_config(CONFIG_PATH)
    except ConfigError as exc:
        raise RuntimeError(f"配置加载失败: {exc}") from exc


def discover_cases() -> list[dict[str, str]]:
    """发现全部可执行用例，返回结构化列表。

    每条记录包含：
        id:      完整 test_id（如 tests.p0.xxx.TestClass.test_method）
        module:  业务模块名（如 成员管理）
        class_name: 测试类名
        method_name: 测试方法名
    """
    config = _build_config()
    logger = _discovery_logger()
    runner = AutomationRunner(config=config, logger=logger)
    suite = runner._build_suite(level=None, module=None, case=None)

    cases: list[dict[str, str]] = []
    for test in runner._iter_tests(suite):
        tid = test.id()
        parts = tid.split(".")
        cases.append({
            "id": tid,
            "module": get_test_case_module(test) or "未知",
            "class_name": parts[-2] if len(parts) >= 2 else "",
            "method_name": parts[-1] if parts else "",
        })
    return cases


def discover_remote_hosts() -> list[dict[str, str]]:
    """读取可用远程节点，供 Streamlit 页面展示."""
    hosts = load_remote_hosts(REMOTE_HOSTS_PATH)
    return [
        {
            "name": host.name,
            "platform": host.platform,
            "host": host.host,
            "port": str(host.port),
            "username": host.username,
            "project_dir": host.project_dir,
            "python": host.python,
            "config": host.config,
            "venv_activate": host.venv_activate,
            "command_prefix": host.command_prefix,
            "auth": _remote_auth_label(host),
            "sync_enabled": "是" if host.sync_enabled else "否",
            "sync_release_root": remote_release_root(host),
            "sync_keep_releases": str(host.sync_keep_releases),
        }
        for host in hosts
    ]


def load_remote_connection_cache() -> dict[str, dict[str, str]]:
    """读取本机远程连接缓存；只包含 host/port/username，不保存密码."""
    if not REMOTE_CONNECTION_CACHE_PATH.exists():
        return {}
    try:
        with REMOTE_CONNECTION_CACHE_PATH.open("r", encoding="utf-8") as file_obj:
            loaded = yaml.safe_load(file_obj) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(f"远程连接缓存读取失败：{exc}") from exc

    hosts = loaded.get("hosts", {})
    if not isinstance(hosts, dict):
        return {}

    result: dict[str, dict[str, str]] = {}
    for name, item in hosts.items():
        if not isinstance(item, dict):
            continue
        host_name = str(name).strip()
        if not host_name:
            continue
        result[host_name] = {
            "host": str(item.get("host", "")).strip(),
            "port": str(item.get("port", "")).strip(),
            "username": str(item.get("username", "")).strip(),
            "updated_at": str(item.get("updated_at", "")).strip(),
        }
    return result


def save_remote_connection_cache(
    host_name: str,
    *,
    ssh_host: str,
    ssh_port: int,
    ssh_username: str,
) -> None:
    """保存本机远程连接缓存；不会保存 SSH 密码."""
    host_name = host_name.strip()
    ssh_host = ssh_host.strip()
    ssh_username = ssh_username.strip()
    if not host_name or not ssh_host or not ssh_username:
        return
    try:
        normalized_port = int(ssh_port)
    except (TypeError, ValueError):
        return
    if not 1 <= normalized_port <= 65535:
        return

    cache = load_remote_connection_cache()
    cache[host_name] = {
        "host": ssh_host,
        "port": str(normalized_port),
        "username": ssh_username,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    REMOTE_CONNECTION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REMOTE_CONNECTION_CACHE_PATH.open("w", encoding="utf-8") as file_obj:
        yaml.safe_dump({"hosts": cache}, file_obj, allow_unicode=True, sort_keys=True)


def preview_remote_command(
    host_name: str,
    scope: str,
    value: str,
    *,
    attach_existing_app: bool = False,
    case_ids: list[str] | tuple[str, ...] | None = None,
) -> str:
    """返回远程执行命令预览，供 UI 展示；不会连接 SSH 或读取密码."""
    host = _remote_host_by_name(host_name)
    if host is None:
        raise RuntimeError(f"远程节点不存在或未启用：{host_name}")
    request = RemoteRunRequest(
        scope=scope,
        value=value,
        values=tuple(case_ids or ()),
        attach_existing_app=attach_existing_app,
    )
    return build_remote_command(host, request)


def remote_capability_matrix() -> list[dict[str, str]]:
    """远程执行 UI 展示用的平台能力矩阵."""
    return [
        {
            "平台": "Windows",
            "远程/本地执行": "支持",
            "CDP 自动化": "支持",
            "APP 托管启动": "支持",
            "系统代理": "支持启停和恢复",
            "原生文件选择器": "支持 Windows UIAutomation 兜底",
            "产物拉取": "本机产物直接保留；远程节点可拉取",
            "已验证范围": "Windows P0 主链路，代理检测受外部代理连通性影响",
        },
        {
            "平台": "Linux",
            "远程/本地执行": "支持 SSH 远程 CLI",
            "CDP 自动化": "支持",
            "APP 托管启动": "已验证",
            "系统代理": "暂不支持自动启停；代理管理继续执行业务流程",
            "原生文件选择器": "暂不支持",
            "产物拉取": "支持 logs/screenshots/reports",
            "已验证范围": "precheck、environment_group_management、member_management、global_settings 主流程；Web Store 安装检查仍受外部网络影响",
        },
        {
            "平台": "macOS",
            "远程/本地执行": "支持 SSH 远程 CLI",
            "CDP 自动化": "支持",
            "APP 托管启动": "按远端配置和图形会话分层验证",
            "系统代理": "暂不支持自动启停；代理管理不跳过",
            "原生文件选择器": "暂不支持",
            "产物拉取": "支持 logs/screenshots/reports",
            "已验证范围": "P0 全量、environment_group_management、代理管理业务流程",
        },
    ]


def _remote_auth_label(host: RemoteHost) -> str:
    if host.key_filename:
        return "SSH key"
    if host.password_env:
        return f"password_env:{host.password_env}"
    return "SSH agent/key"


def _remote_host_by_name(
    host_name: str,
    *,
    ssh_host: str = "",
    ssh_port: int | None = None,
    ssh_username: str = "",
    ssh_password: str = "",
) -> RemoteHost | None:
    hosts = load_remote_hosts(REMOTE_HOSTS_PATH)
    host = next((item for item in hosts if item.name == host_name), None)
    if host is None:
        return None
    return _apply_remote_connection_override(
        host,
        ssh_host=ssh_host,
        ssh_port=ssh_port,
        ssh_username=ssh_username,
        ssh_password=ssh_password,
    )


def _apply_remote_connection_override(
    host: RemoteHost,
    *,
    ssh_host: str = "",
    ssh_port: int | None = None,
    ssh_username: str = "",
    ssh_password: str = "",
) -> RemoteHost:
    resolved_port = host.port
    if ssh_port is not None:
        try:
            resolved_port = int(ssh_port)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("SSH 端口必须是数字") from exc
        if not 1 <= resolved_port <= 65535:
            raise RuntimeError("SSH 端口必须在 1 到 65535 之间")

    return replace(
        host,
        host=ssh_host.strip() or host.host,
        port=resolved_port,
        username=ssh_username.strip() or host.username,
        password=ssh_password,
    )


def _discovery_logger() -> logging.Logger:
    """用例发现使用独立 logger，避免刷新 UI 时清空正在执行的运行日志 handler。"""
    logger = logging.getLogger("dicloak_automation.ui.discovery")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def run_selected_tests(
    test_ids: list[str],
    log_queue: queue.Queue,
    *,
    attach_existing_app: bool = True,
) -> None:
    """后台执行选中用例（供 threading.Thread 调用）。

    执行流程（对齐 AutomationRunner.run()）：
    1. 环境预检
    2. APP 生命周期（启动 or 连接已有）
    3. CDP 连通性校验 → 释放
    4. 构建 suite → 过滤选中用例 → 优先级排序
    5. 通过 AutomationRunner._run_suite() 执行（含恢复/截图/重试/flaky 统计）
    6. FeishuNotifier.send_summary() 飞书通知
    7. 关闭 APP / 释放 CDP

    参数：
        test_ids: 要执行的 test_id 列表。
        log_queue: 实时日志推送队列，结束时放入 None 作为哨兵。
        attach_existing_app: True=连接已打开 APP，False=自动启动新 APP。
    """
    if not _acquire_run_lock(log_queue, "已有 UI 执行任务正在运行，请等待当前任务结束后再启动新的执行。", "本机用例执行"):
        return

    logger: logging.Logger | None = None
    ui_handler: _QueueLogHandler | None = None

    try:
        config = _build_config()
        logger = setup_logger(config, reset=True)
        log_run_start(
            logger,
            source="UI_LOCAL",
            scope="cases",
            selected_count=len(test_ids),
            attach_existing_app=attach_existing_app,
        )

        # ── 挂载 UI 日志 Handler ──
        ui_handler = _QueueLogHandler(log_queue)
        ui_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(ui_handler)

        # ── 1. 环境预检 ──
        from core.precheck import EnvironmentPrechecker

        if config.get("run", {}).get("precheck_before_run", True):
            precheck = EnvironmentPrechecker(config, logger).run()
            if not precheck.passed:
                failed_items = "\n".join(
                    f"  - {item.name}: {item.message}" for item in precheck.failed_items
                )
                logger.error("环境预检失败:\n%s", failed_items)
                log_run_end(logger, source="UI_LOCAL", exit_code=2, success=False)
                return

        # ── 2. 构建 filtered suite ──
        runner = AutomationRunner(config=config, logger=logger)
        suite = runner._build_suite(level=None, module=None, case=None)
        import unittest

        selected_ids = set(test_ids)
        filtered = unittest.TestSuite()
        for test in runner._iter_tests(suite):
            if test.id() in selected_ids:
                filtered.addTest(test)

        filtered = runner._prioritize_suite(filtered)
        case_count = filtered.countTestCases()
        logger.info("已选择 %s 条用例，开始执行", case_count)

        if case_count == 0:
            logger.warning("没有匹配到任何用例")
            log_run_end(logger, source="UI_LOCAL", exit_code=0, success=True, total=0)
            return

        # ── 3. APP 生命周期 + CDP 校验 ──
        app_manager = AppManager(config, logger)
        cdp_driver = CDPDriver(config, logger)
        app_started = False
        try:
            if attach_existing_app:
                logger.info("调试模式：连接已打开的 APP")
            else:
                app_started = app_manager.launch_fresh()
                if not app_started:
                    runner.notifier.send_failure(
                        "Dicloak APP 进程检测失败",
                        "启动后 30 秒内未检测到 APP 进程，将继续尝试 CDP 连接。",
                    )
            cdp_driver.connect()
            cdp_driver.close()
            logger.info("CDP 连通性校验通过，连接已释放")
        except (AppStartupError, CDPConnectionError, OSError) as exc:
            logger.error("APP 启动或 CDP 连接失败: %s", exc)
            runner.notifier.send_failure("Dicloak APP 启动或 CDP 连接失败", str(exc))
            log_run_end(logger, source="UI_LOCAL", exit_code=3, success=False)
            return

        # ── 4. 执行 suite ──
        try:
            stream = _QueueStream(log_queue)
            run_result: RunResult = runner._run_suite(filtered, stream=stream)

            # ── 5. 飞书通知 ──
            runner.notifier.send_summary(run_result)

            # ── 6. 结构化总结日志（UI 用正则解析） ──
            logger.info(
                "运行完成 → 总计=%s 通过=%s 失败=%s 错误=%s 跳过=%s flaky=%s 通过率=%s%%",
                run_result.total,
                run_result.passed,
                run_result.failed,
                run_result.errors,
                run_result.skipped,
                run_result.flaky,
                run_result.pass_rate,
            )
            if run_result.failures:
                logger.warning("失败详情:\n%s", run_result.failed_summary())
            log_run_end(
                logger,
                source="UI_LOCAL",
                exit_code=0 if run_result.success else 1,
                success=run_result.success,
                total=run_result.total,
                passed=run_result.passed,
                failed=run_result.failed,
                errors=run_result.errors,
                skipped=run_result.skipped,
                flaky=run_result.flaky,
            )
        finally:
            cdp_driver.close()
            if not attach_existing_app:
                app_manager.close()
    except Exception as exc:
        if logger:
            log_run_end(logger, source="UI_LOCAL", exit_code=1, success=False, error="internal_exception")
            logger.error("执行器内部异常: %s", exc, exc_info=True)
        else:
            log_queue.put(f"执行器启动失败: {exc}")
    finally:
        if logger and ui_handler:
            logger.removeHandler(ui_handler)
        _release_run_lock()
        log_queue.put(None)  # 哨兵：通知 UI 执行结束


def run_remote_cli(
    host_name: str,
    scope: str,
    value: str,
    log_queue: queue.Queue,
    *,
    attach_existing_app: bool = False,
    collect_artifacts: bool = True,
    sync_before_run: bool = False,
    ssh_host: str = "",
    ssh_port: int | None = None,
    ssh_username: str = "",
    ssh_password: str = "",
    case_ids: list[str] | None = None,
) -> None:
    """后台通过 SSH 在远程节点执行 run.py，并把远程日志推送到 UI."""
    if not _acquire_run_lock(log_queue, "已有 UI 执行任务正在运行，请等待当前任务结束后再启动新的执行。", "远程用例执行"):
        return

    try:
        host = _remote_host_by_name(
            host_name,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_username=ssh_username,
            ssh_password=ssh_password,
        )
        if host is None:
            log_queue.put(f"远程节点不存在或未启用：{host_name}")
            return

        if sync_before_run:
            sync_remote_project(host, log_queue, project_root=PROJECT_ROOT)

        request = RemoteRunRequest(
            scope=scope,
            value=value,
            values=tuple(case_ids or ()),
            attach_existing_app=attach_existing_app,
        )
        result = run_remote_tests(host, request, log_queue)
        duration = round(result.finished_at - result.started_at, 2)
        log_queue.put(f"远程执行完成 → 节点={result.host_name} 退出码={result.exit_code} 耗时={duration}s")
        if collect_artifacts:
            try:
                artifact_result = collect_remote_artifacts(host, result.started_at, log_queue)
                log_queue.put(
                    "远程产物归档 → "
                    f"文件数={artifact_result.files_copied} "
                    f"本地目录={artifact_result.local_dir}"
                )
            except RemoteRunError as exc:
                log_queue.put(f"远程产物拉取失败：{exc}")
        if result.exit_code != 0:
            log_queue.put(f"远程执行失败：退出码={result.exit_code}")
    except (RemoteConfigError, RemoteRunError) as exc:
        log_queue.put(f"远程执行器错误：{exc}")
    except Exception as exc:
        log_queue.put(f"远程执行器内部异常：{exc}")
    finally:
        _release_run_lock()
        log_queue.put(None)


def check_remote_code(
    host_name: str,
    log_queue: queue.Queue,
    *,
    ssh_host: str = "",
    ssh_port: int | None = None,
    ssh_username: str = "",
    ssh_password: str = "",
) -> None:
    """后台检查远端当前代码快照是否和本地工作区一致."""
    if not _acquire_run_lock(log_queue, "已有 UI 执行任务正在运行，请等待当前任务结束后再检查远程代码。", "检查远端代码"):
        return

    try:
        host = _remote_host_by_name(
            host_name,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_username=ssh_username,
            ssh_password=ssh_password,
        )
        if host is None:
            log_queue.put(f"远程节点不存在或未启用：{host_name}")
            return
        check_remote_code_status(host, log_queue, project_root=PROJECT_ROOT)
    except (RemoteConfigError, RemoteRunError) as exc:
        log_queue.put(f"远程代码检查错误：{exc}")
    except Exception as exc:
        log_queue.put(f"远程代码检查内部异常：{exc}")
    finally:
        _release_run_lock()
        log_queue.put(None)


def sync_remote_code(
    host_name: str,
    log_queue: queue.Queue,
    *,
    ssh_host: str = "",
    ssh_port: int | None = None,
    ssh_username: str = "",
    ssh_password: str = "",
) -> None:
    """后台把本地当前工作区同步为远端新的可回退快照."""
    if not _acquire_run_lock(log_queue, "已有 UI 执行任务正在运行，请等待当前任务结束后再同步远程代码。", "同步远端代码"):
        return

    try:
        host = _remote_host_by_name(
            host_name,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_username=ssh_username,
            ssh_password=ssh_password,
        )
        if host is None:
            log_queue.put(f"远程节点不存在或未启用：{host_name}")
            return
        sync_remote_project(host, log_queue, project_root=PROJECT_ROOT)
    except (RemoteConfigError, RemoteRunError) as exc:
        log_queue.put(f"远程代码同步错误：{exc}")
    except Exception as exc:
        log_queue.put(f"远程代码同步内部异常：{exc}")
    finally:
        _release_run_lock()
        log_queue.put(None)


def check_remote_host(
    host_name: str,
    log_queue: queue.Queue,
    *,
    ssh_host: str = "",
    ssh_port: int | None = None,
    ssh_username: str = "",
    ssh_password: str = "",
) -> None:
    """后台通过 SSH 检查远程节点是否具备执行自动化的基础条件."""
    if not _acquire_run_lock(log_queue, "已有 UI 执行任务正在运行，请等待当前任务结束后再检查远程节点。", "检查远程节点"):
        return

    try:
        host = _remote_host_by_name(
            host_name,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_username=ssh_username,
            ssh_password=ssh_password,
        )
        if host is None:
            log_queue.put(f"远程节点不存在或未启用：{host_name}")
            return

        result = run_remote_health_check(host, log_queue)
        duration = round(result.finished_at - result.started_at, 2)
        log_queue.put(f"远程健康检查结束 → 节点={result.host_name} 退出码={result.exit_code} 耗时={duration}s")
        if result.exit_code != 0:
            log_queue.put(f"远程健康检查未通过：失败项数量={result.exit_code}")
    except (RemoteConfigError, RemoteRunError) as exc:
        log_queue.put(f"远程健康检查错误：{exc}")
    except Exception as exc:
        log_queue.put(f"远程健康检查内部异常：{exc}")
    finally:
        _release_run_lock()
        log_queue.put(None)
