"""Streamlit UI 专用执行器。

==== 设计原则 ====
- 用例发现复用 AutomationRunner；本机执行通过 run.py 子进程复用完整 CLI 链路。
- 子进程 stdout/stderr 实时推送到 UI，并允许 Streamlit Stop 安全中断当前任务。
- UI 执行在进程内串行化，避免多个 Streamlit 会话同时抢占同一个 APP/CDP。

==== 使用方式 ====
    from streamlit_runner import discover_cases, run_selected_tests

    cases = discover_cases()
    # ... 用户在 UI 中选择 test_ids ...
    run_selected_tests(test_ids, log_queue, attach_existing_app=True)
"""

from __future__ import annotations

import logging
import os
import queue
import signal
import subprocess
import sys
import threading
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from core.app import AppManager
from core.case_module import get_test_case_module
from core.config import ConfigError, load_config
from core.remote_runner import (
    RemoteConfigError,
    RemoteHost,
    RemoteRunCancelled,
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
    sync_remote_local_auth_lab_state,
    sync_remote_project,
)
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
    "stop_requested": False,
    "stop_event": None,
    "cancel_callback": None,
}


def _mark_task_started(task: str, stop_event: threading.Event) -> None:
    with _RUN_STATE_LOCK:
        _RUN_STATE.update(
            {
                "active": True,
                "task": task,
                "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "thread_ident": threading.get_ident(),
                "stop_requested": False,
                "stop_event": stop_event,
                "cancel_callback": None,
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
                "stop_requested": False,
                "stop_event": None,
                "cancel_callback": None,
            }
        )


def _state_snapshot() -> dict[str, Any]:
    with _RUN_STATE_LOCK:
        return {
            key: value
            for key, value in _RUN_STATE.items()
            if key not in {"stop_event", "cancel_callback"}
        }


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


def create_ui_stop_event() -> threading.Event:
    """Create one cancellation token shared by the page and its worker."""
    return threading.Event()


def request_ui_task_stop(stop_event: threading.Event | None = None) -> bool:
    """Request cancellation of the active UI task and interrupt its current transport."""
    callback: Callable[[], None] | None = None
    with _RUN_STATE_LOCK:
        active_event = _RUN_STATE.get("stop_event")
        if active_event is None:
            target_event = stop_event
        elif stop_event is None or stop_event is active_event:
            target_event = active_event
        else:
            return False
        if target_event is None:
            return False
        target_event.set()
        if active_event is target_event:
            _RUN_STATE["stop_requested"] = True
            callback = _RUN_STATE.get("cancel_callback")
    if callback is not None:
        try:
            callback()
        except Exception:
            pass
    return True


def _set_cancel_callback(stop_event: threading.Event, callback: Callable[[], None] | None) -> None:
    invoke_now = False
    with _RUN_STATE_LOCK:
        if _RUN_STATE.get("stop_event") is not stop_event:
            return
        _RUN_STATE["cancel_callback"] = callback
        invoke_now = callback is not None and stop_event.is_set()
    if invoke_now:
        callback()


def _acquire_run_lock(
    log_queue: queue.Queue,
    busy_message: str,
    task: str,
    stop_event: threading.Event | None = None,
) -> threading.Event | None:
    if not _RUN_LOCK.acquire(blocking=False):
        status = ui_task_status()
        detail = ""
        if status.get("task") or status.get("started_at"):
            detail = f" 当前任务={status.get('task') or '-'} 开始={status.get('started_at') or '-'}"
        log_queue.put(f"{busy_message}{detail}")
        log_queue.put(None)
        return None
    active_stop_event = stop_event or create_ui_stop_event()
    _mark_task_started(task, active_stop_event)
    return active_stop_event


def _release_run_lock() -> None:
    _mark_task_finished()
    try:
        _RUN_LOCK.release()
    except RuntimeError:
        pass


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
    account_profile: dict[str, Any] | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """Run selected cases in a cancellable CLI child process for the Streamlit UI."""
    active_stop_event = _acquire_run_lock(
        log_queue,
        "已有 UI 执行任务正在运行，请等待当前任务结束后再启动新的执行。",
        "本机用例执行",
        stop_event,
    )
    if active_stop_event is None:
        return

    try:
        _run_selected_tests_unlocked(
            test_ids,
            log_queue,
            attach_existing_app=attach_existing_app,
            account_profile=account_profile,
            stop_event=active_stop_event,
        )
    except Exception as exc:
        log_queue.put(f"执行器内部异常：{exc}")
    finally:
        _set_cancel_callback(active_stop_event, None)
        _release_run_lock()
        log_queue.put(None)


def _run_selected_tests_unlocked(
    test_ids: list[str],
    log_queue: Any,
    *,
    attach_existing_app: bool,
    account_profile: dict[str, Any] | None,
    stop_event: threading.Event,
) -> int:
    if stop_event.is_set():
        log_queue.put("本机用例执行已停止（尚未启动）")
        return 130
    if not test_ids:
        log_queue.put("没有匹配到任何用例")
        return 0

    profile_path: Path | None = None
    try:
        command = [
            sys.executable,
            "-u",
            str(PROJECT_ROOT / "run.py"),
            "--config",
            str(CONFIG_PATH),
        ]
        if account_profile:
            profile_path = _write_local_account_profile(account_profile)
            command.extend(["--account-profile", str(profile_path)])
            log_queue.put(f"本机账号组：{account_profile.get('group_name', '-')}")
        for test_id in test_ids:
            command.extend(["--case", test_id])
        if attach_existing_app:
            command.append("--attach-existing-app")
        log_queue.put(f"已选择 {len(test_ids)} 条用例，开始执行")
        exit_code = _run_streaming_subprocess(
            command,
            log_queue,
            stop_event,
            cwd=PROJECT_ROOT,
        )
        if stop_event.is_set():
            if not attach_existing_app:
                _close_managed_app_after_cancel(log_queue)
            log_queue.put("本机用例执行已停止")
        elif exit_code != 0:
            log_queue.put(f"本机用例执行失败：退出码={exit_code}")
        return exit_code
    finally:
        if profile_path is not None:
            try:
                profile_path.unlink(missing_ok=True)
                log_queue.put("本机账号组临时配置已清理")
            except OSError as exc:
                log_queue.put(f"本机账号组临时配置清理失败：{exc}")


def _write_local_account_profile(profile: dict[str, Any]) -> Path:
    profile_path = CONFIG_PATH.parent / f".ui_account_profile_{uuid.uuid4().hex}.yaml"
    try:
        with profile_path.open("w", encoding="utf-8") as file_obj:
            yaml.safe_dump(profile, file_obj, allow_unicode=True, sort_keys=False)
        if os.name != "nt":
            profile_path.chmod(0o600)
        return profile_path
    except Exception:
        profile_path.unlink(missing_ok=True)
        raise


def _run_streaming_subprocess(
    command: list[str],
    log_queue: queue.Queue,
    stop_event: threading.Event,
    *,
    cwd: Path,
) -> int:
    output_queue: queue.Queue[str | None] = queue.Queue()
    popen_kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
        "env": {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "DICLOAK_RUN_SOURCE": "UI_LOCAL",
        },
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(command, **popen_kwargs)

    def read_output() -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                text = line.rstrip()
                if text:
                    output_queue.put(text)
        finally:
            process.stdout.close()
            output_queue.put(None)

    reader = threading.Thread(target=read_output, name="ui-local-output-reader", daemon=True)
    reader.start()
    _set_cancel_callback(stop_event, lambda: _signal_process_interrupt(process))

    output_finished = False
    stop_handled = False
    while process.poll() is None or not output_finished:
        if stop_event.is_set() and process.poll() is None and not stop_handled:
            stop_handled = True
            log_queue.put("收到停止请求，正在终止本机用例执行...")
            _stop_process_tree(process)
        try:
            line = output_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if line is None:
            output_finished = True
        else:
            log_queue.put(line)

    reader.join(timeout=1)
    return int(process.returncode or 0)


def _close_managed_app_after_cancel(log_queue: queue.Queue) -> None:
    try:
        config = _build_config()
        logger = logging.getLogger("dicloak_automation.ui.cancel")
        AppManager(config, logger).close()
    except Exception as exc:
        log_queue.put(f"停止后清理 APP 失败：{exc}")


def _signal_process_interrupt(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGINT)
    except (OSError, ProcessLookupError):
        pass


def _stop_process_tree(process: subprocess.Popen, graceful_timeout: float = 5.0) -> None:
    _signal_process_interrupt(process)
    try:
        process.wait(timeout=graceful_timeout)
        return
    except subprocess.TimeoutExpired:
        pass

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


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
    account_profile: dict[str, Any] | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """后台通过 SSH 在远程节点执行 run.py，并把远程日志推送到 UI."""
    active_stop_event = _acquire_run_lock(
        log_queue,
        "已有 UI 执行任务正在运行，请等待当前任务结束后再启动新的执行。",
        "远程用例执行",
        stop_event,
    )
    if active_stop_event is None:
        return

    try:
        _run_remote_cli_unlocked(
            host_name,
            scope,
            value,
            log_queue,
            attach_existing_app=attach_existing_app,
            collect_artifacts=collect_artifacts,
            sync_before_run=sync_before_run,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_username=ssh_username,
            ssh_password=ssh_password,
            case_ids=case_ids,
            account_profile=account_profile,
            stop_event=active_stop_event,
        )
    except RemoteRunCancelled:
        log_queue.put("远程用例执行已停止")
    except (RemoteConfigError, RemoteRunError) as exc:
        log_queue.put(f"远程执行器错误：{exc}")
    except Exception as exc:
        log_queue.put(f"远程执行器内部异常：{exc}")
    finally:
        _release_run_lock()
        log_queue.put(None)


def _run_remote_cli_unlocked(
    host_name: str,
    scope: str,
    value: str,
    log_queue: Any,
    *,
    attach_existing_app: bool,
    collect_artifacts: bool,
    sync_before_run: bool,
    ssh_host: str,
    ssh_port: int | None,
    ssh_username: str,
    ssh_password: str,
    case_ids: list[str] | None,
    account_profile: dict[str, Any] | None,
    stop_event: threading.Event,
) -> int:
    if stop_event.is_set():
        log_queue.put("远程用例执行已停止（尚未启动）")
        return 130
    host = _remote_host_by_name(
        host_name,
        ssh_host=ssh_host,
        ssh_port=ssh_port,
        ssh_username=ssh_username,
        ssh_password=ssh_password,
    )
    if host is None:
        log_queue.put(f"远程节点不存在或未启用：{host_name}")
        return 2

    if sync_before_run:
        sync_remote_project(host, log_queue, project_root=PROJECT_ROOT)
        sync_remote_local_auth_lab_state(host, log_queue, project_root=PROJECT_ROOT)

    request = RemoteRunRequest(
        scope=scope,
        value=value,
        values=tuple(case_ids or ()),
        attach_existing_app=attach_existing_app,
        account_profile=account_profile,
    )
    result = run_remote_tests(host, request, log_queue, stop_event=stop_event)
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
    return result.exit_code


class _PrefixedLogQueue:
    def __init__(self, target: queue.Queue, label: str):
        self.target = target
        self.label = label

    def put(self, value: Any) -> None:
        if value is not None:
            self.target.put(f"[{self.label}] {value}")


def run_local_and_remote(
    test_ids: list[str],
    log_queue: queue.Queue,
    *,
    local_attach_existing_app: bool,
    local_account_profile: dict[str, Any],
    remote_host_name: str,
    remote_attach_existing_app: bool,
    remote_collect_artifacts: bool,
    remote_sync_before_run: bool,
    remote_ssh_host: str,
    remote_ssh_port: int | None,
    remote_ssh_username: str,
    remote_ssh_password: str,
    remote_account_profile: dict[str, Any],
    stop_event: threading.Event | None = None,
) -> None:
    active_stop_event = _acquire_run_lock(
        log_queue,
        "已有 UI 执行任务正在运行，请等待当前任务结束后再启动同步执行。",
        "Windows 本机 + macOS 远程同步执行",
        stop_event,
    )
    if active_stop_event is None:
        return

    local_log = _PrefixedLogQueue(log_queue, "Windows")
    remote_log = _PrefixedLogQueue(log_queue, "macOS")
    errors: list[tuple[str, Exception]] = []

    def run_local() -> None:
        try:
            _run_selected_tests_unlocked(
                test_ids,
                local_log,
                attach_existing_app=local_attach_existing_app,
                account_profile=local_account_profile,
                stop_event=active_stop_event,
            )
        except Exception as exc:
            errors.append(("Windows", exc))
            local_log.put(f"执行器内部异常：{exc}")

    def run_remote() -> None:
        try:
            _run_remote_cli_unlocked(
                remote_host_name,
                "cases",
                "",
                remote_log,
                attach_existing_app=remote_attach_existing_app,
                collect_artifacts=remote_collect_artifacts,
                sync_before_run=remote_sync_before_run,
                ssh_host=remote_ssh_host,
                ssh_port=remote_ssh_port,
                ssh_username=remote_ssh_username,
                ssh_password=remote_ssh_password,
                case_ids=test_ids,
                account_profile=remote_account_profile,
                stop_event=active_stop_event,
            )
        except RemoteRunCancelled:
            remote_log.put("远程用例执行已停止")
        except Exception as exc:
            errors.append(("macOS", exc))
            remote_log.put(f"远程执行器异常：{exc}")

    try:
        local_thread = threading.Thread(target=run_local, name="ui-windows-run", daemon=True)
        remote_thread = threading.Thread(target=run_remote, name="ui-macos-run", daemon=True)
        log_queue.put("开始 Windows 本机与 macOS 远程同步执行")
        local_thread.start()
        remote_thread.start()
        local_thread.join()
        remote_thread.join()
        if errors:
            labels = "、".join(label for label, _ in errors)
            log_queue.put(f"同步执行结束，以下执行端发生异常：{labels}")
        elif active_stop_event.is_set():
            log_queue.put("Windows 本机与 macOS 远程同步执行已停止")
        else:
            log_queue.put("Windows 本机与 macOS 远程同步执行完成")
    finally:
        _set_cancel_callback(active_stop_event, None)
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
    stop_event: threading.Event | None = None,
) -> None:
    """后台检查远端当前代码快照是否和本地工作区一致."""
    active_stop_event = _acquire_run_lock(
        log_queue,
        "已有 UI 执行任务正在运行，请等待当前任务结束后再检查远程代码。",
        "检查远端代码",
        stop_event,
    )
    if active_stop_event is None:
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
    stop_event: threading.Event | None = None,
) -> None:
    """后台把本地当前工作区同步为远端新的可回退快照."""
    active_stop_event = _acquire_run_lock(
        log_queue,
        "已有 UI 执行任务正在运行，请等待当前任务结束后再同步远程代码。",
        "同步远端代码",
        stop_event,
    )
    if active_stop_event is None:
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
    stop_event: threading.Event | None = None,
) -> None:
    """后台通过 SSH 检查远程节点是否具备执行自动化的基础条件."""
    active_stop_event = _acquire_run_lock(
        log_queue,
        "已有 UI 执行任务正在运行，请等待当前任务结束后再检查远程节点。",
        "检查远程节点",
        stop_event,
    )
    if active_stop_event is None:
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

        result = run_remote_health_check(host, log_queue, stop_event=active_stop_event)
        duration = round(result.finished_at - result.started_at, 2)
        log_queue.put(f"远程健康检查结束 → 节点={result.host_name} 退出码={result.exit_code} 耗时={duration}s")
        if result.exit_code != 0:
            log_queue.put(f"远程健康检查未通过：失败项数量={result.exit_code}")
    except RemoteRunCancelled:
        log_queue.put("远程健康检查已停止")
    except (RemoteConfigError, RemoteRunError) as exc:
        log_queue.put(f"远程健康检查错误：{exc}")
    except Exception as exc:
        log_queue.put(f"远程健康检查内部异常：{exc}")
    finally:
        _release_run_lock()
        log_queue.put(None)
