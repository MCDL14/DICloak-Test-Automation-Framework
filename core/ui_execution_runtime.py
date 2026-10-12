from __future__ import annotations

import queue
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator


ACTIVE_EXECUTION_SESSION_KEY = "execute_cases_active_execution"


def create_execution_runtime(
    *,
    thread: Any,
    log_queue: queue.Queue,
    stop_event: Any,
    started_at: float,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Create the page-independent runtime stored in Streamlit session state."""
    return {
        "thread": thread,
        "log_queue": log_queue,
        "stop_event": stop_event,
        "started_at": float(started_at),
        "log_lines": [],
        "received_sentinel": False,
        "last_log_time": float(started_at),
        "render_sequence": 0,
        **metadata,
    }


def drain_execution_runtime(runtime: dict[str, Any]) -> list[str]:
    """Drain available messages while preserving all logs for page restoration."""
    log_queue = runtime.get("log_queue")
    if not isinstance(log_queue, queue.Queue):
        return []
    log_lines = runtime.setdefault("log_lines", [])
    new_lines: list[str] = []
    while True:
        try:
            message = log_queue.get_nowait()
        except queue.Empty:
            break
        if message is None:
            runtime["received_sentinel"] = True
            continue
        line = str(message)
        log_lines.append(line)
        new_lines.append(line)
        runtime["last_log_time"] = time.time()
    return new_lines


def execution_runtime_running(runtime: dict[str, Any]) -> bool:
    thread = runtime.get("thread")
    return bool(thread is not None and callable(getattr(thread, "is_alive", None)) and thread.is_alive())


def _current_ui_session() -> Any:
    """Find the session only if it still owns this rendering script."""
    from streamlit.runtime import exists, get_instance
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    context = get_script_run_ctx(suppress_warning=True)
    if context is None or not exists():
        return None
    session_info = get_instance()._session_mgr.get_session_info(context.session_id)
    if session_info is None:
        return None
    session = session_info.session
    script_runner = getattr(session, "_scriptrunner", None)
    if getattr(script_runner, "_requests", None) is not context.script_requests:
        return None
    return session


def cancel_native_ui_stop(
    runtime: dict[str, Any],
    request_stop: Callable[..., bool],
) -> bool:
    """Cancel a toolbar Stop without treating a replaced page script as a Stop."""
    from streamlit import config

    session = _current_ui_session()
    # With fastReruns, navigation also stops the old script, but replaces its
    # session runner. The project config disables this optimization; this guard
    # still protects launches made from another working directory.
    if config.get_option("runner.fastReruns") and session is None:
        return False

    runtime["stop_requested"] = True
    runtime["stop_event"].set()
    runtime["log_queue"].put("收到页面右上角 Stop 请求，正在停止当前任务...")
    request_stop(runtime["stop_event"])

    if session is not None:
        original_runner = session._scriptrunner
        from streamlit.proto.ClientState_pb2 import ClientState
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        client_state = ClientState()
        client_state.CopyFrom(session._client_state)
        context = get_script_run_ctx(suppress_warning=True)
        if context is not None:
            client_state.page_script_hash = context.page_script_hash
            client_state.query_string = context.query_string
        # Preserve the current page, but never replay the Run button's old click.
        client_state.ClearField("widget_states")
        client_state.fragment_id = ""

        def refresh_stopped_page() -> None:
            # Do not navigate the user back if they switched pages while the
            # cancellation callback was waiting for the process to exit.
            if session._scriptrunner is original_runner:
                # Let the stopped script finish resetting button triggers and
                # saving its state before creating the replacement script.
                session._event_loop.call_later(0.05, refresh_stopped_page)
            elif session._scriptrunner is None:
                session.request_rerun(client_state)

        # A stopped script cannot use st.rerun(): its STOP request is permanent.
        # Schedule a new rendering on the owning session's event loop instead.
        session._event_loop.call_soon_threadsafe(refresh_stopped_page)
    return True


@contextmanager
def watch_native_ui_stop(
    runtime: dict[str, Any],
    request_stop: Callable[..., bool],
) -> Iterator[None]:
    from streamlit.runtime.scriptrunner import StopException

    try:
        yield
    except StopException:
        cancel_native_ui_stop(runtime, request_stop)
        raise
