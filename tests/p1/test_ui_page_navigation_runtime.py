from __future__ import annotations

import queue
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.ui_execution_runtime import (
    ACTIVE_EXECUTION_SESSION_KEY,
    create_execution_runtime,
    drain_execution_runtime,
    execution_runtime_running,
    watch_native_ui_stop,
)


class UiPageNavigationRuntimeTests(unittest.TestCase):
    def test_runtime_preserves_logs_added_while_execution_page_is_not_rendering(self) -> None:
        log_queue: queue.Queue = queue.Queue()
        worker = threading.Thread(target=lambda: None)
        runtime = create_execution_runtime(
            thread=worker,
            log_queue=log_queue,
            stop_event=threading.Event(),
            started_at=100.0,
            metadata={"selected_cases": [{"id": "case.one"}]},
        )

        log_queue.put("CASE START case.one")
        self.assertEqual(drain_execution_runtime(runtime), ["CASE START case.one"])

        # Simulate logs produced while the user is viewing another Streamlit page.
        log_queue.put("CASE PASS case.one")
        log_queue.put(None)
        self.assertEqual(drain_execution_runtime(runtime), ["CASE PASS case.one"])

        self.assertEqual(
            runtime["log_lines"],
            ["CASE START case.one", "CASE PASS case.one"],
        )
        self.assertTrue(runtime["received_sentinel"])

    def test_runtime_running_reflects_worker_lifecycle_without_setting_stop_event(self) -> None:
        release = threading.Event()
        worker = threading.Thread(target=release.wait, daemon=True)
        stop_event = threading.Event()
        runtime = create_execution_runtime(
            thread=worker,
            log_queue=queue.Queue(),
            stop_event=stop_event,
            started_at=100.0,
            metadata={},
        )

        worker.start()
        self.assertTrue(execution_runtime_running(runtime))
        self.assertFalse(stop_event.is_set())
        release.set()
        worker.join(timeout=2)
        self.assertFalse(execution_runtime_running(runtime))
        self.assertFalse(stop_event.is_set())

    def test_execution_page_persists_runtime_and_does_not_cancel_on_page_interruption(self) -> None:
        source = (Path("ui") / "pages" / "01_执行用例.py").read_text(encoding="utf-8")

        self.assertIn("ACTIVE_EXECUTION_SESSION_KEY", source)
        self.assertIn("create_execution_runtime(", source)
        self.assertIn("drain_execution_runtime(active_execution)", source)
        self.assertIn("or active_execution is not None", source)
        self.assertNotIn("request_ui_task_stop(stop_event)", source)

    def test_execution_monitor_keeps_sidebar_widgets_stable_without_automatic_full_reruns(self) -> None:
        source = (Path("ui") / "pages" / "01_执行用例.py").read_text(encoding="utf-8")
        monitor_source = source.split(
            "    # 每次页面重跑只做一次非阻塞队列排空。",
            1,
        )[1].split(
            "    # 后台线程已结束时再排空一次尾部消息",
            1,
        )[0]

        self.assertIn("while runtime_running:", monitor_source)
        self.assertNotIn("st.rerun()", monitor_source)
        self.assertIn("allow_stop_button=True", source)

    def test_runtime_session_key_is_stable(self) -> None:
        self.assertEqual(ACTIVE_EXECUTION_SESSION_KEY, "execute_cases_active_execution")

    def test_native_stop_cancels_worker_and_schedules_final_page_refresh(self) -> None:
        from streamlit.proto.ClientState_pb2 import ClientState
        from streamlit.runtime.scriptrunner import StopException

        stop_event = threading.Event()
        runtime = {"stop_event": stop_event, "log_queue": queue.Queue()}
        original_runner = object()
        original_client_state = ClientState(page_script_hash="previous-page", query_string="previous=1")
        original_client_state.widget_states.widgets.add(id="run-button", trigger_value=True)
        session = SimpleNamespace(
            _scriptrunner=original_runner,
            _client_state=original_client_state,
            _event_loop=SimpleNamespace(call_soon_threadsafe=Mock(), call_later=Mock()),
            request_rerun=Mock(),
        )
        request_stop = Mock(return_value=True)

        with (
            patch("core.ui_execution_runtime._current_ui_session", return_value=session),
            patch(
                "streamlit.runtime.scriptrunner.get_script_run_ctx",
                return_value=SimpleNamespace(page_script_hash="execute-page", query_string="filter=env"),
            ),
        ):
            with self.assertRaises(StopException):
                with watch_native_ui_stop(runtime, request_stop):
                    raise StopException()

        self.assertTrue(stop_event.is_set())
        self.assertTrue(runtime["stop_requested"])
        request_stop.assert_called_once_with(stop_event)
        refresh = session._event_loop.call_soon_threadsafe.call_args.args[0]
        refresh()
        session.request_rerun.assert_not_called()
        session._event_loop.call_later.assert_called_once_with(0.05, refresh)

        session._scriptrunner = None
        refresh()
        refreshed_client_state = session.request_rerun.call_args.args[0]
        self.assertEqual(refreshed_client_state.page_script_hash, "execute-page")
        self.assertEqual(refreshed_client_state.query_string, "filter=env")
        self.assertFalse(refreshed_client_state.HasField("widget_states"))
        # Snapshotting must not alter the previous client state in place.
        self.assertEqual(original_client_state.page_script_hash, "previous-page")
        self.assertTrue(original_client_state.widget_states.widgets[0].trigger_value)

        # A newer page must not be replaced by the stopped page's late refresh.
        session.request_rerun.reset_mock()
        session._scriptrunner = object()
        refresh()
        session.request_rerun.assert_not_called()

    def test_menu_rerun_does_not_cancel_worker(self) -> None:
        from streamlit.runtime.scriptrunner import RerunException
        from streamlit.runtime.scriptrunner_utils.script_requests import RerunData

        stop_event = threading.Event()
        runtime = {"stop_event": stop_event, "log_queue": queue.Queue()}
        request_stop = Mock()
        with self.assertRaises(RerunException):
            with watch_native_ui_stop(runtime, request_stop):
                raise RerunException(RerunData(page_name="运行历史"))

        self.assertFalse(stop_event.is_set())
        request_stop.assert_not_called()

    def test_fast_rerun_of_replaced_script_does_not_cancel_worker(self) -> None:
        from streamlit.runtime.scriptrunner import StopException

        stop_event = threading.Event()
        runtime = {"stop_event": stop_event, "log_queue": queue.Queue()}
        request_stop = Mock()
        with (
            patch("core.ui_execution_runtime._current_ui_session", return_value=None),
            patch("streamlit.config.get_option", return_value=True),
            self.assertRaises(StopException),
        ):
            with watch_native_ui_stop(runtime, request_stop):
                raise StopException()

        self.assertFalse(stop_event.is_set())
        request_stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
