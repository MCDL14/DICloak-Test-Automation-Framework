from __future__ import annotations

import queue
import tempfile
import unittest
from pathlib import Path

import yaml

from core.remote_runner import RemoteRunError
from core.remote_sync import _exec_checked, build_local_manifest


class _FakeChannel:
    def __init__(self, exit_code: int) -> None:
        self._exit_code = exit_code

    def recv_exit_status(self) -> int:
        return self._exit_code


class _FakeStream:
    def __init__(self, text: str, exit_code: int = 0) -> None:
        self._text = text
        self.channel = _FakeChannel(exit_code)

    def read(self) -> bytes:
        return self._text.encode("utf-8")


class _FakeClient:
    def __init__(self, *, stdout: str = "", stderr: str = "", exit_code: int = 0) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self._exit_code = exit_code

    def exec_command(self, command: str):  # noqa: ANN001
        return (
            None,
            _FakeStream(self._stdout, self._exit_code),
            _FakeStream(self._stderr, self._exit_code),
        )


class RemoteSyncSafetyTests(unittest.TestCase):
    def test_custom_rules_cannot_include_protected_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            config_dir = root / "config"
            config_dir.mkdir()
            (root / "run.py").write_text("print('ok')\n", encoding="utf-8")
            (config_dir / "config.yaml").write_text("password: real\n", encoding="utf-8")
            (config_dir / "test_data.yaml").write_text("token: real\n", encoding="utf-8")
            (config_dir / "remote_hosts.yaml").write_text("hosts: []\n", encoding="utf-8")
            (config_dir / "remote_connection_cache.yaml").write_text("hosts: {}\n", encoding="utf-8")
            (config_dir / "remote_sync.yaml").write_text(
                yaml.safe_dump({"include": ["config/*.yaml", "run.py"], "exclude": []}),
                encoding="utf-8",
            )

            _, files = build_local_manifest(root)
            synced_paths = {rel for rel, _ in files}

        self.assertIn("run.py", synced_paths)
        self.assertNotIn("config/config.yaml", synced_paths)
        self.assertNotIn("config/test_data.yaml", synced_paths)
        self.assertNotIn("config/remote_hosts.yaml", synced_paths)
        self.assertNotIn("config/remote_connection_cache.yaml", synced_paths)
        self.assertNotIn("config/remote_sync.yaml", synced_paths)

    def test_remote_sync_logs_and_errors_are_sanitized(self) -> None:
        log_queue: queue.Queue[str] = queue.Queue()
        client = _FakeClient(
            stdout='{"password": "abc123"}\n',
            stderr="token=secret-token\n",
            exit_code=1,
        )

        with self.assertRaises(RemoteRunError) as context:
            _exec_checked(client, "ignored", log_queue)

        queued = []
        while not log_queue.empty():
            queued.append(log_queue.get_nowait())

        combined_logs = "\n".join(queued)
        self.assertIn("<redacted>", combined_logs)
        self.assertNotIn("abc123", combined_logs)
        self.assertNotIn("secret-token", combined_logs)
        self.assertIn("<redacted>", str(context.exception))
        self.assertNotIn("secret-token", str(context.exception))


if __name__ == "__main__":
    unittest.main()
