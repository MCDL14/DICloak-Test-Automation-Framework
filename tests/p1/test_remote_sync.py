from __future__ import annotations

import queue
import json
import tarfile
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from core.local_auth_lab.database import LocalAuthDatabase
from core.local_auth_lab.state_sync import STATE_MANIFEST_NAME, create_state_bundle
from core.remote_runner import RemoteHost, RemoteRunError
from core.remote_sync import _exec_checked, _remote_auth_state_install_script, build_local_manifest


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
    def test_custom_rules_sync_runtime_config_but_keep_remote_connection_files_protected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            config_dir = root / "config"
            config_dir.mkdir()
            (root / "run.py").write_text("print('ok')\n", encoding="utf-8")
            (config_dir / "config.yaml").write_text("password: real\n", encoding="utf-8")
            (config_dir / "test_data.yaml").write_text("token: real\n", encoding="utf-8")
            (config_dir / "remote_hosts.yaml").write_text("hosts: []\n", encoding="utf-8")
            (config_dir / "remote_connection_cache.yaml").write_text("hosts: {}\n", encoding="utf-8")
            (config_dir / "account_groups.yaml").write_text("groups: {}\n", encoding="utf-8")
            (config_dir / ".ui_account_profile_secret.yaml").write_text("password: secret\n", encoding="utf-8")
            (config_dir / "local_auth_lab.yaml").write_text("admin_key: secret\n", encoding="utf-8")
            auth_data = root / "test_data" / "local_auth_lab"
            auth_data.mkdir(parents=True)
            (auth_data / "auth.db").write_bytes(b"private sqlite data")
            (config_dir / "remote_sync.yaml").write_text(
                yaml.safe_dump(
                    {"include": ["config/*.yaml", "test_data/**", "run.py"], "exclude": []}
                ),
                encoding="utf-8",
            )

            _, files = build_local_manifest(root)
            synced_paths = {rel for rel, _ in files}

        self.assertIn("run.py", synced_paths)
        self.assertIn("config/config.yaml", synced_paths)
        self.assertIn("config/test_data.yaml", synced_paths)
        self.assertNotIn("config/remote_hosts.yaml", synced_paths)
        self.assertNotIn("config/remote_connection_cache.yaml", synced_paths)
        self.assertNotIn("config/account_groups.yaml", synced_paths)
        self.assertNotIn("config/.ui_account_profile_secret.yaml", synced_paths)
        self.assertNotIn("config/local_auth_lab.yaml", synced_paths)
        self.assertNotIn("config/remote_sync.yaml", synced_paths)
        self.assertNotIn("test_data/local_auth_lab/auth.db", synced_paths)

    def test_auth_state_uses_dedicated_bundle_with_consistent_database_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            config_dir = root / "config"
            config_dir.mkdir()
            (config_dir / "config.yaml").write_text("{}\n", encoding="utf-8")
            (config_dir / "local_auth_lab.yaml").write_text(
                yaml.safe_dump(
                    {
                        "local_auth_lab": {
                            "enabled": True,
                            "database_path": "test_data/local_auth_lab/auth.db",
                            "credentials_path": "test_data/local_auth_lab/credentials.json",
                            "template_dir": str(
                                Path.cwd() / "web_templates" / "local_auth_lab"
                            ),
                            "session": {"ttl_seconds": 15552000},
                        }
                    }
                ),
                encoding="utf-8",
            )
            config = {"_project_root": str(root)}
            database = LocalAuthDatabase(root / "test_data" / "local_auth_lab" / "auth.db")
            database.initialize()
            database.register_user("cookie", "bundle_user", "password123")

            bundle = create_state_bundle(config, root)
            try:
                with tarfile.open(bundle.archive_path, "r:gz") as archive:
                    names = set(archive.getnames())
                    manifest_file = archive.extractfile(STATE_MANIFEST_NAME)
                    self.assertIsNotNone(manifest_file)
                    manifest = json.loads(manifest_file.read().decode("utf-8"))
                self.assertIn("config/local_auth_lab.yaml", names)
                self.assertIn("test_data/local_auth_lab/credentials.json", names)
                self.assertIn("test_data/local_auth_lab/auth.db", names)
                self.assertEqual(manifest["signing_key_id"], bundle.signing_key_id)
                self.assertEqual(manifest["database_sha256"], bundle.database_sha256)
                self.assertEqual(bundle.users, 1)
                self.assertEqual(bundle.sessions, 0)
            finally:
                bundle.archive_path.unlink(missing_ok=True)

    def test_remote_auth_state_install_validates_key_database_and_running_service(self) -> None:
        host = RemoteHost(
            name="mac",
            host="127.0.0.1",
            username="tester",
            project_dir="/Users/tester/project",
            config="config/config.macos.yaml",
        )
        script = _remote_auth_state_install_script(
            host=host,
            remote_archive="/tmp/dicloak_auth_state_key_1.tar.gz",
            signing_key_id="key-id",
            database_sha256="db-hash",
            override_path="config/local_auth_lab.yaml",
            credentials_path="test_data/local_auth_lab/credentials.json",
            database_path="test_data/local_auth_lab/auth.db",
        )

        self.assertIn("ensure_persistent_credentials", script)
        self.assertIn("AUTH_STATE_KEY_MISMATCH", script)
        self.assertIn("AUTH_STATE_DATABASE_HASH_MISMATCH", script)
        self.assertIn("AUTH_STATE_SERVICE_RUNNING", script)
        self.assertIn("install -m 600", script)

    def test_execute_before_sync_orders_code_then_auth_state_then_remote_run(self) -> None:
        import streamlit_runner

        host = RemoteHost(
            name="mac",
            host="127.0.0.1",
            username="tester",
            project_dir="/Users/tester/project",
        )
        order: list[str] = []
        result = SimpleNamespace(
            host_name="mac",
            exit_code=0,
            started_at=1.0,
            finished_at=2.0,
        )
        with patch("streamlit_runner._remote_host_by_name", return_value=host), patch(
            "streamlit_runner.sync_remote_project",
            side_effect=lambda *_args, **_kwargs: order.append("code"),
        ), patch(
            "streamlit_runner.sync_remote_local_auth_lab_state",
            side_effect=lambda *_args, **_kwargs: order.append("auth_state"),
        ), patch(
            "streamlit_runner.run_remote_tests",
            side_effect=lambda *_args, **_kwargs: (order.append("run") or result),
        ):
            exit_code = streamlit_runner._run_remote_cli_unlocked(
                "mac",
                "level",
                "P0",
                queue.Queue(),
                attach_existing_app=False,
                collect_artifacts=False,
                sync_before_run=True,
                ssh_host="",
                ssh_port=None,
                ssh_username="",
                ssh_password="",
                case_ids=None,
                account_profile=None,
                stop_event=threading.Event(),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(order, ["code", "auth_state", "run"])

    def test_execute_before_sync_also_syncs_auth_state_for_unrelated_selection(self) -> None:
        import streamlit_runner

        host = RemoteHost(
            name="mac",
            host="127.0.0.1",
            username="tester",
            project_dir="/Users/tester/project",
        )
        order: list[str] = []
        result = SimpleNamespace(
            host_name="mac",
            exit_code=0,
            started_at=1.0,
            finished_at=2.0,
        )
        unrelated_case = (
            "tests.p1.test_remote_sync.RemoteSyncSafetyTests."
            "test_remote_sync_logs_and_errors_are_sanitized"
        )
        with patch("streamlit_runner._remote_host_by_name", return_value=host), patch(
            "streamlit_runner.sync_remote_project",
            side_effect=lambda *_args, **_kwargs: order.append("code"),
        ), patch(
            "streamlit_runner.sync_remote_local_auth_lab_state",
            side_effect=lambda *_args, **_kwargs: order.append("auth_state"),
        ), patch(
            "streamlit_runner.run_remote_tests",
            side_effect=lambda *_args, **_kwargs: (order.append("run") or result),
        ):
            exit_code = streamlit_runner._run_remote_cli_unlocked(
                "mac",
                "cases",
                "",
                queue.Queue(),
                attach_existing_app=False,
                collect_artifacts=False,
                sync_before_run=True,
                ssh_host="",
                ssh_port=None,
                ssh_username="",
                ssh_password="",
                case_ids=[unrelated_case],
                account_profile=None,
                stop_event=threading.Event(),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(order, ["code", "auth_state", "run"])

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
