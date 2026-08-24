from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import streamlit_runner


@unittest.skipUnless(streamlit_runner.sys.platform == "win32", "本机密码缓存使用 Windows DPAPI")
class RemoteConnectionCacheTests(unittest.TestCase):
    def test_password_is_encrypted_and_can_be_loaded_again(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            cache_path = Path(raw_dir) / "remote_connection_cache.yaml"
            with patch.object(streamlit_runner, "REMOTE_CONNECTION_CACHE_PATH", cache_path):
                streamlit_runner.save_remote_connection_cache(
                    "macos-arm64",
                    ssh_host="192.0.2.10",
                    ssh_port=22,
                    ssh_username="tester",
                    ssh_password="private-password",
                )

                raw_cache = cache_path.read_text(encoding="utf-8")
                loaded = streamlit_runner.load_remote_connection_cache()["macos-arm64"]

        self.assertNotIn("private-password", raw_cache)
        self.assertIn("password_protected: dpapi:", raw_cache)
        self.assertEqual(loaded["password"], "private-password")

    def test_connection_update_preserves_password_when_argument_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            cache_path = Path(raw_dir) / "remote_connection_cache.yaml"
            with patch.object(streamlit_runner, "REMOTE_CONNECTION_CACHE_PATH", cache_path):
                streamlit_runner.save_remote_connection_cache(
                    "macos-arm64",
                    ssh_host="192.0.2.10",
                    ssh_port=22,
                    ssh_username="tester",
                    ssh_password="private-password",
                )
                streamlit_runner.save_remote_connection_cache(
                    "macos-arm64",
                    ssh_host="192.0.2.11",
                    ssh_port=2222,
                    ssh_username="tester-2",
                )
                loaded = streamlit_runner.load_remote_connection_cache()["macos-arm64"]

        self.assertEqual(loaded["host"], "192.0.2.11")
        self.assertEqual(loaded["port"], "2222")
        self.assertEqual(loaded["password"], "private-password")

    def test_empty_password_removes_saved_credential(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            cache_path = Path(raw_dir) / "remote_connection_cache.yaml"
            with patch.object(streamlit_runner, "REMOTE_CONNECTION_CACHE_PATH", cache_path):
                streamlit_runner.save_remote_connection_cache(
                    "macos-arm64",
                    ssh_host="192.0.2.10",
                    ssh_port=22,
                    ssh_username="tester",
                    ssh_password="private-password",
                )
                streamlit_runner.save_remote_connection_cache(
                    "macos-arm64",
                    ssh_host="192.0.2.10",
                    ssh_port=22,
                    ssh_username="tester",
                    ssh_password="",
                )
                raw_cache = yaml.safe_load(cache_path.read_text(encoding="utf-8"))
                loaded = streamlit_runner.load_remote_connection_cache()["macos-arm64"]

        self.assertNotIn("password_protected", raw_cache["hosts"]["macos-arm64"])
        self.assertEqual(loaded["password"], "")

    def test_invalid_encrypted_password_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            cache_path = Path(raw_dir) / "remote_connection_cache.yaml"
            cache_path.write_text(
                yaml.safe_dump(
                    {
                        "hosts": {
                            "macos-arm64": {
                                "host": "192.0.2.10",
                                "port": "22",
                                "username": "tester",
                                "password_protected": "dpapi:not-base64",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(streamlit_runner, "REMOTE_CONNECTION_CACHE_PATH", cache_path):
                loaded = streamlit_runner.load_remote_connection_cache()["macos-arm64"]

        self.assertEqual(loaded["password"], "")


if __name__ == "__main__":
    unittest.main()
