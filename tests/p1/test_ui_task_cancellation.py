from __future__ import annotations

import queue
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import streamlit_runner
from core.remote_runner import RemoteRunCancelled, _stream_channel
from run import _run_source_from_environment


class _FakeSSHChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    def send(self, value: str) -> None:
        self.sent.append(value)

    def close(self) -> None:
        self.closed = True


class UITaskCancellationTests(unittest.TestCase):
    def tearDown(self) -> None:
        if streamlit_runner.ui_task_status().get("locked"):
            streamlit_runner._release_run_lock()

    def test_request_stop_sets_event_and_invokes_active_callback(self) -> None:
        log_queue: queue.Queue = queue.Queue()
        stop_event = streamlit_runner.create_ui_stop_event()
        callback_called = threading.Event()
        acquired = streamlit_runner._acquire_run_lock(
            log_queue,
            "busy",
            "test task",
            stop_event,
        )
        self.assertIs(acquired, stop_event)
        streamlit_runner._set_cancel_callback(stop_event, callback_called.set)

        self.assertTrue(streamlit_runner.request_ui_task_stop(stop_event))

        self.assertTrue(stop_event.is_set())
        self.assertTrue(callback_called.is_set())
        self.assertTrue(streamlit_runner.ui_task_status()["stop_requested"])

    def test_streaming_subprocess_is_terminated_and_releases_lock(self) -> None:
        log_queue: queue.Queue = queue.Queue()
        stop_event = streamlit_runner.create_ui_stop_event()
        acquired = streamlit_runner._acquire_run_lock(
            log_queue,
            "busy",
            "subprocess test",
            stop_event,
        )
        self.assertIs(acquired, stop_event)
        result: list[int] = []

        def run_child() -> None:
            try:
                result.append(
                    streamlit_runner._run_streaming_subprocess(
                        [
                            sys.executable,
                            "-u",
                            "-c",
                            "import time; print('child-started', flush=True); time.sleep(60)",
                        ],
                        log_queue,
                        stop_event,
                        cwd=Path.cwd(),
                    )
                )
            finally:
                streamlit_runner._release_run_lock()

        worker = threading.Thread(target=run_child, daemon=True)
        worker.start()
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                if log_queue.get(timeout=0.2) == "child-started":
                    break
            except queue.Empty:
                continue
        else:
            self.fail("child process did not start")

        self.assertTrue(streamlit_runner.request_ui_task_stop(stop_event))
        worker.join(timeout=10)

        self.assertFalse(worker.is_alive())
        self.assertTrue(result)
        self.assertNotEqual(result[0], 0)
        self.assertFalse(streamlit_runner.ui_task_status()["locked"])

    def test_remote_channel_receives_ctrl_c_when_cancelled(self) -> None:
        log_queue: queue.Queue = queue.Queue()
        stop_event = threading.Event()
        stop_event.set()
        channel = _FakeSSHChannel()

        with self.assertRaises(RemoteRunCancelled):
            _stream_channel(channel, log_queue, stop_event=stop_event)

        self.assertEqual(channel.sent, ["\x03"])
        self.assertTrue(channel.closed)

    def test_ui_child_run_source_is_explicit_and_cli_default_is_preserved(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_run_source_from_environment(), "CLI")
        with patch.dict("os.environ", {"DICLOAK_RUN_SOURCE": "UI_LOCAL"}, clear=True):
            self.assertEqual(_run_source_from_environment(), "UI_LOCAL")
        with patch.dict("os.environ", {"DICLOAK_RUN_SOURCE": "unexpected"}, clear=True):
            self.assertEqual(_run_source_from_environment(), "CLI")


if __name__ == "__main__":
    unittest.main()
