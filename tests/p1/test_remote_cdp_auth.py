from __future__ import annotations

import copy
import errno
import io
import os
import posixpath
import queue
import stat
import tarfile
import tempfile
import threading
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml
import paramiko
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from core.app_config import resolve_app_config
from core.config import ConfigError, load_config
from core.remote_runner import RemoteHost, RemoteRunError
from core.remote_sync import build_local_manifest, create_local_sync_bundle


def _private_key_bytes() -> bytes:
    """A new disposable test key; never reads a user's signing key."""
    return ed25519.Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _minimal_config() -> dict:
    return {
        "app": {"cdp_auth": {"private_key_path": "local-placeholder.pem", "ttl_seconds": 120}},
        "cdp": {},
        "account": {"username": "test-only", "password": "test-password"},
        "feishu": {},
        "timeouts": {},
        "run": {},
        "log": {},
    }


class RemoteCdpSidecarTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="dicloak-cdp-sidecar-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config_path = self.root / "runtime.yaml"
        self.sidecar = self.root / "runtime.yaml.cdp-auth.local.yaml"
        self.base = _minimal_config()
        self.environment = mock.patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def _load(self, override: dict | None) -> dict:
        self.config_path.write_text(yaml.safe_dump(self.base), encoding="utf-8")
        if override is not None:
            self.sidecar.write_text(yaml.safe_dump(override), encoding="utf-8")
        return load_config(self.config_path)

    def test_sidecar_paths_override_base_and_preserve_runtime_settings(self) -> None:
        self.base["app"]["cdp_auth"].update(
            script_path="C:/test-only/token.py", enabled=True, timeout_seconds=17
        )
        result = self._load({
            "private_key_path": "/home/tester/.dicloak/cdp-keys/project/private.pem",
            "script_path": "",
        })

        self.assertEqual(result["app"]["cdp_auth"]["script_path"], "")
        self.assertEqual(result["app"]["cdp_auth"]["private_key_path"],
                         "/home/tester/.dicloak/cdp-keys/project/private.pem")
        self.assertEqual(result["app"]["cdp_auth"]["ttl_seconds"], 120)
        self.assertEqual(result["app"]["cdp_auth"]["timeout_seconds"], 17)
        self.assertTrue(result["app"]["cdp_auth"]["enabled"])
        for key, value in self.base["account"].items():
            self.assertEqual(result["account"][key], value)

    def test_sidecar_has_priority_over_old_and_nested_platform_paths(self) -> None:
        self.base["platforms"] = {
            "macos": {"cdp_auth": {
                "private_key_path": "/old-platform.pem", "script_path": "/old-mac.py",
                "ttl_seconds": 105, "enabled": False,
            }},
            "windows": {"app": {"cdp_auth": {
                "private_key_path": "C:/old.pem", "script_path": "C:/old.py",
                "ttl_seconds": 111, "timeout_seconds": 19,
            }}},
        }
        result = self._load({
            "private_key_path": "/remote-key.pem", "script_path": "",
        })

        mac = resolve_app_config(result, "macos").cdp_auth
        windows = resolve_app_config(result, "windows").cdp_auth
        for settings in (mac, windows):
            self.assertEqual(settings["private_key_path"], "/remote-key.pem")
            self.assertEqual(settings["script_path"], "")
        self.assertFalse(mac["enabled"])
        self.assertEqual(mac["ttl_seconds"], 105)
        self.assertEqual(windows["ttl_seconds"], 111)
        self.assertEqual(windows["timeout_seconds"], 19)

    def test_missing_sidecar_keeps_existing_configuration(self) -> None:
        result = self._load(None)
        self.assertEqual(result["app"]["cdp_auth"]["private_key_path"], "local-placeholder.pem")
        self.assertEqual(result["app"]["cdp_auth"]["ttl_seconds"], 120)

    def test_omitted_script_in_sidecar_selects_bundled_issuer(self) -> None:
        self.base["app"]["cdp_auth"]["script_path"] = "C:/local/issuer.py"
        result = self._load({"private_key_path": "/remote-key.pem"})
        self.assertEqual(result["app"]["cdp_auth"]["script_path"], "")
        self.assertEqual(result["_app_cdp_auth_override_file"], str(self.sidecar.resolve()))

    def test_sidecar_cannot_override_credentials_or_ttl(self) -> None:
        for override in (
            {"account": {"password": "unexpected-secret"}},
            {"private_key_path": "/remote-key.pem", "ttl_seconds": 3600},
            {"private_key_path": "/remote-key.pem", "enabled": False},
        ):
            with self.subTest(override=override), self.assertRaises(ConfigError):
                self._load(override)

    def test_private_key_and_sidecar_are_excluded_even_by_custom_include(self) -> None:
        config_dir = self.root / "config"
        config_dir.mkdir()
        (self.root / "run.py").write_text("pass\n", encoding="utf-8")
        (config_dir / "runtime.yaml").write_text("{}\n", encoding="utf-8")
        (config_dir / "runtime.yaml.cdp-auth.local.yaml").write_text(
            "private_key_path: /not-for-snapshot.pem\n", encoding="utf-8"
        )
        (config_dir / "SIGNING.PEM").write_bytes(_private_key_bytes())
        (config_dir / "private.key").write_bytes(_private_key_bytes())
        (config_dir / "remote_sync.yaml").write_text(
            yaml.safe_dump({"include": ["**", "run.py"], "exclude": []}), encoding="utf-8"
        )

        _, files = build_local_manifest(self.root)
        names = {name for name, _ in files}
        self.assertIn("config/runtime.yaml", names)
        self.assertNotIn("config/runtime.yaml.cdp-auth.local.yaml", names)
        self.assertNotIn("config/SIGNING.PEM", names)
        self.assertNotIn("config/private.key", names)
        bundle = create_local_sync_bundle(self.root)
        try:
            with tarfile.open(bundle.archive_path, "r:gz") as archive:
                archive_names = archive.getnames()
            self.assertFalse(any(name.endswith(".cdp-auth.local.yaml") for name in archive_names))
            self.assertFalse(any(name.lower().endswith((".pem", ".key")) for name in archive_names))
        finally:
            bundle.archive_path.unlink(missing_ok=True)

    def test_configured_non_pem_key_and_hardlink_alias_never_enter_default_snapshot(self) -> None:
        config_dir = self.root / "config"
        config_dir.mkdir()
        key_path = config_dir / "signing.dat"
        alias_path = config_dir / "innocent-looking.dat"
        key_path.write_bytes(_private_key_bytes())
        os.link(key_path, alias_path)
        configured = _minimal_config()
        configured["app"]["cdp_auth"]["private_key_path"] = str(key_path)
        (config_dir / "config.yaml").write_text(yaml.safe_dump(configured), encoding="utf-8")
        (config_dir / "remote_sync.yaml").write_text(
            yaml.safe_dump({"include": ["**"], "exclude": []}), encoding="utf-8"
        )

        _, files = build_local_manifest(self.root)
        self.assertNotIn("config/signing.dat", {name for name, _ in files})
        self.assertNotIn("config/innocent-looking.dat", {name for name, _ in files})
        bundle = create_local_sync_bundle(self.root)
        try:
            with tarfile.open(bundle.archive_path, "r:gz") as archive:
                names = archive.getnames()
            self.assertNotIn("config/signing.dat", names)
            self.assertNotIn("config/innocent-looking.dat", names)
        finally:
            bundle.archive_path.unlink(missing_ok=True)

    def test_explicit_protected_non_pem_path_and_hardlink_alias_are_excluded(self) -> None:
        config_dir = self.root / "config"
        config_dir.mkdir()
        key_path = config_dir / "custom-signing.data"
        alias_path = config_dir / "alternate-name.txt"
        key_path.write_bytes(_private_key_bytes())
        os.link(key_path, alias_path)
        (config_dir / "ordinary.txt").write_text("non-secret fixture", encoding="utf-8")
        (config_dir / "remote_sync.yaml").write_text(
            yaml.safe_dump({"include": ["config/**"], "exclude": []}), encoding="utf-8"
        )
        _, files = build_local_manifest(self.root, protected_paths=(key_path,))
        self.assertEqual({name for name, _ in files}, {"config/ordinary.txt"})
        bundle = create_local_sync_bundle(self.root, protected_paths=(key_path,))
        try:
            with tarfile.open(bundle.archive_path, "r:gz") as archive:
                names = archive.getnames()
            self.assertIn("config/ordinary.txt", names)
            self.assertNotIn("config/custom-signing.data", names)
            self.assertNotIn("config/alternate-name.txt", names)
        finally:
            bundle.archive_path.unlink(missing_ok=True)

    def test_explicit_protected_non_pem_key_symlink_alias_is_excluded(self) -> None:
        config_dir = self.root / "config"
        config_dir.mkdir()
        key_path = config_dir / "signing.dat"
        alias_path = config_dir / "symlink.txt"
        key_path.write_bytes(_private_key_bytes())
        try:
            alias_path.symlink_to(key_path)
        except OSError:
            self.skipTest("This Windows account cannot create symlinks")
        (config_dir / "remote_sync.yaml").write_text(
            yaml.safe_dump({"include": ["config/**"], "exclude": []}), encoding="utf-8"
        )
        _, files = build_local_manifest(self.root, protected_paths=(key_path,))
        self.assertNotIn("config/signing.dat", {name for name, _ in files})
        self.assertNotIn("config/symlink.txt", {name for name, _ in files})


class RemoteCdpPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="dicloak-cdp-key-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.key = self.root / "temporary-signing.pem"
        self.key_bytes = _private_key_bytes()
        self.key.write_bytes(self.key_bytes)
        self.config = _minimal_config()
        self.config["_project_root"] = str(self.root)
        self.config["app"]["cdp_auth"]["private_key_path"] = str(self.key)
        patcher = mock.patch.dict(os.environ, {}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_prepares_disposable_ed25519_pkcs8_key(self) -> None:
        from core.remote_cdp_auth import prepare_cdp_private_key

        self.assertEqual(prepare_cdp_private_key(self.config), self.key_bytes)

    def test_disabled_auth_never_reads_a_key(self) -> None:
        from core.remote_cdp_auth import prepare_cdp_private_key

        self.config["app"]["cdp_auth"].update(enabled=False, private_key_path="")
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("must not read")):
            self.assertIsNone(prepare_cdp_private_key(self.config))

    def test_key_path_can_come_from_private_environment(self) -> None:
        from core.remote_cdp_auth import prepare_cdp_private_key

        self.config["app"]["cdp_auth"]["private_key_path"] = ""
        with mock.patch.dict(os.environ, {"DICLOAK_CDP_PRIVATE_KEY_PATH": str(self.key)}):
            self.assertEqual(prepare_cdp_private_key(self.config), self.key_bytes)

    def test_rejects_missing_oversized_invalid_and_wrong_algorithm_without_disclosure(self) -> None:
        from core.remote_cdp_auth import prepare_cdp_private_key

        rsa_bytes = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        cases = (b"not-a-key-SENSITIVE-MARKER", b"x" * (16 * 1024 + 1), rsa_bytes)
        for data in cases:
            with self.subTest(size=len(data)):
                self.key.write_bytes(data)
                try:
                    prepare_cdp_private_key(self.config)
                except Exception:
                    rendered = traceback.format_exc()
                else:
                    self.fail("invalid signing key must not be accepted")
                self.assertNotIn(data.decode("ascii"), rendered)
                self.assertNotIn("SENSITIVE-MARKER", rendered)

        self.key.unlink()
        with self.assertRaises(Exception):
            prepare_cdp_private_key(self.config)


class _MemoryFile:
    def __init__(self, sftp, path: str) -> None:
        self.sftp = sftp
        self.path = path

    def write(self, data) -> None:
        data = data.encode("utf-8") if isinstance(data, str) else data
        self.sftp.events.append(("write", self.path))
        if self.sftp.fail_write:
            raise OSError("simulated failed private transfer")
        self.sftp.files[self.path] += data

    def flush(self) -> None:
        self.sftp.events.append(("flush", self.path))

    def close(self) -> None:
        self.sftp.events.append(("file_close", self.path))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class _MemorySftp:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.modes: dict[str, int] = {}
        self.events: list[tuple] = []
        self.fail_write = False
        self.fail_rename = False
        self.closed = False
        self.add_directory("/")
        self.add_directory("/home/tester")
        self.add_directory("/srv/project_releases/new-release/config")

    def add_directory(self, path: str) -> None:
        if path != "/":
            parent = posixpath.dirname(path)
            if parent not in self.modes:
                self.add_directory(parent)
        self.modes[path] = stat.S_IFDIR | 0o700

    def normalize(self, path: str) -> str:
        return "/home/tester" if path in (".", "") else posixpath.normpath(path)

    def lstat(self, path: str):
        self.events.append(("lstat", path))
        if path not in self.modes:
            raise FileNotFoundError(errno.ENOENT, "not found", path)
        return SimpleNamespace(st_mode=self.modes[path], st_size=len(self.files.get(path, b"")))

    def stat(self, path: str):
        return self.lstat(path)

    def mkdir(self, path: str, mode: int = 0o777) -> None:
        self.events.append(("mkdir", path, mode))
        if path in self.modes:
            raise FileExistsError(errno.EEXIST, "exists", path)
        if posixpath.dirname(path) not in self.modes:
            raise FileNotFoundError(errno.ENOENT, "parent missing", path)
        self.modes[path] = stat.S_IFDIR | mode

    def chmod(self, path: str, mode: int) -> None:
        self.events.append(("chmod", path, mode))
        self.modes[path] = stat.S_IFMT(self.modes[path]) | mode

    def open(self, path: str, mode: str = "r"):
        self.events.append(("open", path, mode))
        if "x" in mode and path in self.modes:
            raise FileExistsError(errno.EEXIST, "already exists", path)
        if posixpath.dirname(path) not in self.modes:
            raise FileNotFoundError(errno.ENOENT, "parent missing", path)
        self.modes[path] = stat.S_IFREG | 0o666
        self.files[path] = b""
        return _MemoryFile(self, path)

    file = open

    def posix_rename(self, source: str, destination: str) -> None:
        self.events.append(("posix_rename", source, destination))
        if self.fail_rename:
            raise OSError("simulated unsupported atomic rename")
        self.files[destination] = self.files.pop(source)
        self.modes[destination] = self.modes.pop(source)

    def remove(self, path: str) -> None:
        self.events.append(("remove", path))
        self.files.pop(path, None)
        self.modes.pop(path, None)

    def close(self) -> None:
        self.events.append(("sftp_close",))
        self.closed = True


class _MemorySsh:
    def __init__(self, sftp: _MemorySftp, server_key=None) -> None:
        self.sftp = sftp
        self.server_key = server_key
        self.active = True
        self.authenticated = True
        self.has_transport = True
        self.sftp_opened = 0
        self.commands: list[str] = []

    def get_transport(self):
        if not self.has_transport:
            return None
        return SimpleNamespace(
            get_remote_server_key=lambda: self.server_key,
            is_active=lambda: self.active,
            is_authenticated=lambda: self.authenticated,
        )

    def open_sftp(self):
        self.sftp_opened += 1
        return self.sftp

    def exec_command(self, command: str):
        self.commands.append(command)
        raise AssertionError("Private deployment must not put key data into shell commands")


class RemoteCdpDeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key_bytes = _private_key_bytes()
        self.sftp = _MemorySftp()
        self.client = _MemorySsh(self.sftp)
        self.host = RemoteHost(
            name="test-only", host="example.invalid", username="tester",
            project_dir="/srv/project", config="config/config.yaml",
        )
        self.release = "/srv/project_releases/new-release"
        self.logs: queue.Queue = queue.Queue()

    def _deploy(self):
        from core.remote_cdp_auth import deploy_remote_cdp_private_key

        return deploy_remote_cdp_private_key(
            self.client, self.host, self.key_bytes,
            release_dir=self.release, log_queue=self.logs,
        )

    def test_deploys_key_outside_repository_with_private_modes_and_atomic_replace(self) -> None:
        result = self._deploy()

        self.assertTrue(result.remote_key_path.startswith("/home/tester/.dicloak/cdp-keys/"))
        self.assertEqual(self.sftp.files[result.remote_key_path], self.key_bytes)
        self.assertEqual(stat.S_IMODE(self.sftp.modes[result.remote_key_path]), 0o600)
        self.assertEqual(result.override_path,
                         self.release + "/config/config.yaml.cdp-auth.local.yaml")
        sidecar = yaml.safe_load(self.sftp.files[result.override_path])
        self.assertEqual(sidecar, {"private_key_path": result.remote_key_path, "script_path": ""})
        self.assertEqual(stat.S_IMODE(self.sftp.modes[result.override_path]), 0o600)
        self.assertTrue(self.sftp.closed)
        self.assertEqual(self.client.commands, [])

        for index, event in enumerate(self.sftp.events):
            if event[0] == "mkdir":
                self.assertEqual(event[2], 0o700)
            if event[0] == "write":
                self.assertIn(("chmod", event[1], 0o600), self.sftp.events[:index])
                opens = [entry for entry in self.sftp.events[:index]
                         if entry[0] == "open" and entry[1] == event[1]]
                self.assertIn("x", opens[-1][2])
        renames = [event for event in self.sftp.events if event[0] == "posix_rename"]
        self.assertEqual(len(renames), 2)
        self.assertEqual(set(self.sftp.files), {result.remote_key_path, result.override_path})
        log_text = "\n".join(list(self.logs.queue))
        self.assertNotIn(self.key_bytes.decode("ascii"), log_text)
        self.assertNotIn("BEGIN PRIVATE KEY", log_text)

    def test_repeated_deployment_reuses_per_project_key_path(self) -> None:
        first = self._deploy()
        self.key_bytes = _private_key_bytes()
        second = self._deploy()
        self.assertEqual(first.remote_key_path, second.remote_key_path)
        self.assertEqual(self.sftp.files[second.remote_key_path], self.key_bytes)

    def test_failed_transfer_preserves_existing_key_and_removes_temporary_file(self) -> None:
        result = self._deploy()
        before = dict(self.sftp.files)
        self.sftp.fail_write = True
        self.key_bytes = _private_key_bytes()
        with self.assertRaises(RemoteRunError):
            self._deploy()
        self.assertEqual(self.sftp.files, before)
        self.assertEqual(self.sftp.files[result.remote_key_path], before[result.remote_key_path])
        self.assertTrue(any(event[0] == "remove" for event in self.sftp.events))

    def test_failed_atomic_rename_preserves_existing_key_and_removes_temporary_file(self) -> None:
        self._deploy()
        before = dict(self.sftp.files)
        self.sftp.fail_rename = True
        self.key_bytes = _private_key_bytes()
        with self.assertRaises(RemoteRunError):
            self._deploy()
        self.assertEqual(self.sftp.files, before)

    def test_rejects_symlink_directory_or_destination_before_key_write(self) -> None:
        for target in ("/home/tester/.dicloak", "key", "sidecar"):
            with self.subTest(target=target):
                self.sftp = _MemorySftp()
                self.client = _MemorySsh(self.sftp)
                if target == "/home/tester/.dicloak":
                    self.sftp.modes[target] = stat.S_IFLNK | 0o777
                else:
                    deployed = self._deploy()
                    self.sftp.events.clear()
                    target_path = deployed.remote_key_path if target == "key" else deployed.override_path
                    self.sftp.modes[target_path] = stat.S_IFLNK | 0o777
                with self.assertRaises(RemoteRunError):
                    self._deploy()
                self.assertFalse(any(event[0] == "write" for event in self.sftp.events))

    def test_absolute_config_inside_active_project_maps_into_new_release(self) -> None:
        self.host = copy.copy(self.host)
        object.__setattr__(self.host, "config", "/srv/project/config/config.yaml")
        result = self._deploy()
        self.assertEqual(result.override_path,
                         self.release + "/config/config.yaml.cdp-auth.local.yaml")

    def test_absolute_config_outside_project_keeps_its_own_sidecar_location(self) -> None:
        object.__setattr__(self.host, "config", "/etc/dicloak/runtime.yaml")
        result = self._deploy()
        self.assertEqual(result.override_path, "/etc/dicloak/runtime.yaml.cdp-auth.local.yaml")

    def test_unsafe_config_path_is_rejected_before_sftp_upload(self) -> None:
        for config_path in ("../outside.yaml", "config/../../outside.yaml", "C:\\config.yaml"):
            with self.subTest(config_path=config_path):
                object.__setattr__(self.host, "config", config_path)
                with self.assertRaises(RemoteRunError):
                    self._deploy()
                self.assertEqual(self.client.sftp_opened, 0)

    def test_invalid_key_is_rejected_before_opening_sftp(self) -> None:
        self.key_bytes = b"invalid-key-SENSITIVE-MARKER"
        with self.assertRaises(RemoteRunError) as context:
            self._deploy()
        self.assertEqual(self.client.sftp_opened, 0)
        self.assertNotIn("SENSITIVE-MARKER", str(context.exception))


class RemoteCdpConnectionStateTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="dicloak-cdp-known-hosts-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / ".ssh").mkdir()
        self.key_bytes = _private_key_bytes()
        self.server_key = paramiko.RSAKey.generate(1024)
        self.sftp = _MemorySftp()
        self.client = _MemorySsh(self.sftp, self.server_key)
        self.host = RemoteHost(
            name="test-only", host="example.invalid", username="tester", project_dir="/srv/project"
        )

    def _write_old_host_key(self, key, name="example.invalid") -> None:
        keys = paramiko.HostKeys()
        keys.add(name, key.get_name(), key)
        keys.save(str(self.root / ".ssh" / "known_hosts"))

    def _deploy(self):
        from core.remote_cdp_auth import deploy_remote_cdp_private_key

        with (
            mock.patch("pathlib.Path.home", return_value=self.root),
            mock.patch.object(paramiko.HostKeys, "load", side_effect=AssertionError("must not load known_hosts")),
            mock.patch.object(paramiko.HostKeys, "save", side_effect=AssertionError("must not save known_hosts")),
        ):
            return deploy_remote_cdp_private_key(
                self.client, self.host, self.key_bytes, release_dir="/srv/project_releases/new-release"
            )

    def test_first_deployment_does_not_need_or_create_known_hosts(self) -> None:
        known_hosts = self.root / ".ssh" / "known_hosts"
        self.assertFalse(known_hosts.exists())
        result = self._deploy()
        self.assertEqual(self.sftp.files[result.remote_key_path], self.key_bytes)
        self.assertEqual(self.client.sftp_opened, 1)
        self.assertFalse(known_hosts.exists())

    def test_replaced_mac_host_key_is_not_compared_with_local_known_hosts(self) -> None:
        self._write_old_host_key(paramiko.RSAKey.generate(1024))
        known_hosts = self.root / ".ssh" / "known_hosts"
        before = known_hosts.read_bytes()
        result = self._deploy()
        self.assertEqual(self.sftp.files[result.remote_key_path], self.key_bytes)
        self.assertEqual(known_hosts.read_bytes(), before)

    def test_missing_transport_is_rejected_before_opening_sftp(self) -> None:
        self.client.has_transport = False
        with self.assertRaises(RemoteRunError):
            self._deploy()
        self.assertEqual(self.client.sftp_opened, 0)
        self.assertEqual(self.sftp.files, {})

    def test_nonstandard_port_does_not_require_known_hosts_entry(self) -> None:
        object.__setattr__(self.host, "port", 2222)
        result = self._deploy()
        self.assertEqual(self.sftp.files[result.remote_key_path], self.key_bytes)

    def test_disconnected_transport_is_rejected_before_opening_sftp(self) -> None:
        self.client.active = False
        with self.assertRaises(RemoteRunError):
            self._deploy()
        self.assertEqual(self.client.sftp_opened, 0)
        self.assertEqual(self.sftp.files, {})

    def test_unauthenticated_transport_is_rejected_before_opening_sftp(self) -> None:
        self.client.authenticated = False
        with self.assertRaises(RemoteRunError):
            self._deploy()
        self.assertEqual(self.client.sftp_opened, 0)
        self.assertEqual(self.sftp.files, {})


class RemoteCdpSshConnectionPolicyTests(unittest.TestCase):
    def test_ssh_connection_accepts_unknown_hosts_without_loading_or_saving_host_files(self) -> None:
        from core.remote_runner import _connect_ssh_client

        host = RemoteHost(
            name="test-only", host="example.invalid", username="tester", project_dir="/srv/project"
        )
        client = mock.MagicMock()
        with mock.patch("paramiko.SSHClient", return_value=client):
            result = _connect_ssh_client(host)

        self.assertIs(result, client)
        policy = client.set_missing_host_key_policy.call_args.args[0]
        self.assertIsInstance(policy, paramiko.AutoAddPolicy)
        client.load_system_host_keys.assert_not_called()
        client.load_host_keys.assert_not_called()
        client.save_host_keys.assert_not_called()
        calls = [call[0] for call in client.mock_calls]
        self.assertLess(calls.index("set_missing_host_key_policy"), calls.index("connect"))

    def test_replacement_mac_at_same_address_gets_fresh_in_memory_host_key(self) -> None:
        from core.remote_runner import _connect_ssh_client

        host = RemoteHost(
            name="test-only", host="example.invalid", username="tester", project_dir="/srv/project"
        )
        first, replacement = paramiko.SSHClient(), paramiko.SSHClient()
        first_key, replacement_key = paramiko.RSAKey.generate(1024), paramiko.RSAKey.generate(1024)
        for client, key in ((first, first_key), (replacement, replacement_key)):
            client._log = mock.Mock()
            client.connect = mock.Mock(side_effect=lambda client=client, key=key, **_kwargs:
                                       client._policy.missing_host_key(client, host.host, key))
        with (
            mock.patch("paramiko.SSHClient", side_effect=[first, replacement]),
            mock.patch.object(paramiko.HostKeys, "load", side_effect=AssertionError("must not load known_hosts")),
            mock.patch.object(paramiko.HostKeys, "save", side_effect=AssertionError("must not save known_hosts")),
        ):
            self.assertIs(_connect_ssh_client(host), first)
            self.assertIs(_connect_ssh_client(host), replacement)

        self.assertEqual(first.get_host_keys()[host.host][first_key.get_name()], first_key)
        self.assertEqual(replacement.get_host_keys()[host.host][replacement_key.get_name()], replacement_key)
        self.assertNotEqual(first_key, replacement_key)
        self.assertIsNone(first._host_keys_filename)
        self.assertIsNone(replacement._host_keys_filename)


class RemoteCdpSyncPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="dicloak-cdp-pipeline-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.archive = self.root / "disposable-code-snapshot.tar.gz"
        self.archive.write_bytes(b"test-only-code-archive")
        self.bundle = SimpleNamespace(
            archive_path=self.archive, manifest={"content_hash": "testhash", "file_count": 1}
        )
        self.host = RemoteHost(
            name="test-only", host="example.invalid", username="tester", project_dir="/srv/project"
        )
        self.client = mock.MagicMock()
        self.key_bytes = _private_key_bytes()
        self.config = _minimal_config()
        self.config["_project_root"] = str(self.root.resolve())
        self.config["app"]["cdp_auth"]["private_key_path"] = str(self.root / "config" / "custom-signing.data")

    def test_sync_deploys_separately_before_archive_setup_and_switch(self) -> None:
        from core.remote_sync import sync_remote_project

        order = []
        logs = queue.Queue()
        self.client.open_sftp.return_value.put.side_effect = lambda *_args: order.append("archive")
        with (
            mock.patch("core.remote_sync.load_config", return_value=self.config) as load,
            mock.patch("core.remote_sync.prepare_cdp_private_key", return_value=self.key_bytes),
            mock.patch("core.remote_sync.create_local_sync_bundle", return_value=self.bundle) as bundle,
            mock.patch("core.remote_sync._connect_ssh_client", return_value=self.client) as connect,
            mock.patch("core.remote_sync.deploy_remote_cdp_private_key",
                       side_effect=lambda *_args, **_kwargs: order.append("key")) as deploy,
            mock.patch("core.remote_sync._remote_setup_script", return_value="SETUP_TEST_ONLY"),
            mock.patch("core.remote_sync._exec_checked",
                       side_effect=lambda _client, command, _logs:
                       (order.append("switch") or "") if command == "SETUP_TEST_ONLY" else ""),
        ):
            sync_remote_project(
                self.host, logs, project_root=self.root, local_config_path="config/custom-source.yaml"
            )

        self.assertEqual(order, ["key", "archive", "switch"])
        connect.assert_called_once_with(self.host)
        load.assert_called_once_with(self.root.resolve() / "config" / "custom-source.yaml")
        self.assertEqual(deploy.call_args.args[2], self.key_bytes)
        self.assertEqual(
            tuple(Path(path).resolve() for path in bundle.call_args.kwargs["protected_paths"]),
            (Path(self.config["app"]["cdp_auth"]["private_key_path"]).resolve(),),
        )
        self.assertNotIn(self.key_bytes.decode("ascii"), str(self.client.mock_calls))
        self.assertNotIn(self.key_bytes.decode("ascii"), "\n".join(list(logs.queue)))
        self.client.close.assert_called_once()
        self.assertFalse(self.archive.exists())

    def test_missing_key_fails_before_network_or_creating_archive(self) -> None:
        from core.remote_sync import sync_remote_project

        with (
            mock.patch("core.remote_sync.load_config", return_value=self.config),
            mock.patch("core.remote_sync.prepare_cdp_private_key", side_effect=RemoteRunError("invalid key")),
            mock.patch("core.remote_sync.create_local_sync_bundle") as bundle,
            mock.patch("core.remote_sync._connect_ssh_client") as connect,
        ):
            with self.assertRaises(RemoteRunError):
                sync_remote_project(self.host, project_root=self.root)
        bundle.assert_not_called()
        connect.assert_not_called()

    def test_deployment_failure_prevents_code_upload_or_active_release_switch(self) -> None:
        from core.remote_sync import sync_remote_project

        with (
            mock.patch("core.remote_sync.load_config", return_value=self.config),
            mock.patch("core.remote_sync.prepare_cdp_private_key", return_value=self.key_bytes),
            mock.patch("core.remote_sync.create_local_sync_bundle", return_value=self.bundle),
            mock.patch("core.remote_sync._connect_ssh_client", return_value=self.client),
            mock.patch("core.remote_sync.deploy_remote_cdp_private_key", side_effect=RemoteRunError("private transfer failed")),
            mock.patch("core.remote_sync._exec_checked") as execute,
        ):
            with self.assertRaises(RemoteRunError):
                sync_remote_project(self.host, project_root=self.root)
        execute.assert_not_called()
        self.client.open_sftp.assert_not_called()
        self.client.close.assert_called_once()
        self.assertFalse(self.archive.exists())

    def test_failed_ssh_connection_still_removes_local_code_archive(self) -> None:
        from core.remote_sync import sync_remote_project

        with (
            mock.patch("core.remote_sync.load_config", return_value=self.config),
            mock.patch("core.remote_sync.prepare_cdp_private_key", return_value=self.key_bytes),
            mock.patch("core.remote_sync.create_local_sync_bundle", return_value=self.bundle),
            mock.patch("core.remote_sync._connect_ssh_client", side_effect=RemoteRunError("cannot connect")),
        ):
            with self.assertRaises(RemoteRunError):
                sync_remote_project(self.host, project_root=self.root)
        self.assertFalse(self.archive.exists())

    def test_relative_source_config_is_resolved_under_explicit_project_root(self) -> None:
        from core.remote_sync import sync_remote_project

        with (
            mock.patch("core.remote_sync.load_config", return_value=self.config) as load,
            mock.patch("core.remote_sync.prepare_cdp_private_key", side_effect=RemoteRunError("stop here")),
        ):
            with self.assertRaises(RemoteRunError):
                sync_remote_project(self.host, project_root=self.root, local_config_path="config/custom.yaml")
        load.assert_called_once_with(self.root.resolve() / "config" / "custom.yaml")

    def test_absolute_source_config_is_not_rebased_to_project(self) -> None:
        from core.remote_sync import sync_remote_project

        config_path = self.root / "outside-root.yaml"
        with (
            mock.patch("core.remote_sync.load_config", return_value=self.config) as load,
            mock.patch("core.remote_sync.prepare_cdp_private_key", side_effect=RemoteRunError("stop here")),
        ):
            with self.assertRaises(RemoteRunError):
                sync_remote_project(self.host, project_root=self.root / "project", local_config_path=config_path)
        load.assert_called_once_with(config_path)

    def test_disabled_auth_syncs_code_without_private_key_deployment(self) -> None:
        from core.remote_sync import sync_remote_project

        with (
            mock.patch("core.remote_sync.load_config", return_value=self.config),
            mock.patch("core.remote_sync.prepare_cdp_private_key", return_value=None),
            mock.patch("core.remote_sync.create_local_sync_bundle", return_value=self.bundle),
            mock.patch("core.remote_sync._connect_ssh_client", return_value=self.client) as connect,
            mock.patch("core.remote_sync.deploy_remote_cdp_private_key") as deploy,
            mock.patch("core.remote_sync._remote_setup_script", return_value="SETUP_TEST_ONLY"),
            mock.patch("core.remote_sync._exec_checked", return_value=""),
        ):
            sync_remote_project(self.host, project_root=self.root)
        deploy.assert_not_called()
        connect.assert_called_once_with(self.host)
        self.client.open_sftp.return_value.put.assert_called_once()

    def test_manual_ui_sync_uses_same_private_key_enabled_pipeline(self) -> None:
        import streamlit_runner

        with (
            mock.patch("streamlit_runner._acquire_run_lock", return_value=threading.Event()),
            mock.patch("streamlit_runner._release_run_lock"),
            mock.patch("streamlit_runner._remote_host_by_name", return_value=self.host),
            mock.patch("streamlit_runner.sync_remote_project") as sync,
        ):
            streamlit_runner.sync_remote_code("test-only", queue.Queue())
        sync.assert_called_once()
        self.assertEqual(sync.call_args.args[0], self.host)

    def test_setup_keeps_predeployed_sidecar_before_switching_active_release(self) -> None:
        from core.remote_sync import _remote_setup_script

        script = _remote_setup_script(
            host=self.host,
            remote_archive="/tmp/test-code-archive.tar.gz",
            release_root="/srv/project_releases",
            release_dir="/srv/project_releases/new-release",
            release_name="new-release",
            keep_releases=5,
            compile_check=False,
        )
        preserve_guard = 'if [ -f "$RELEASE_DIR/config/$base" ]; then\n      continue\n    fi'
        self.assertIn(preserve_guard, script)
        self.assertLess(script.index(preserve_guard), script.index('cp "$cfg"'))
        self.assertLess(script.index('cp "$cfg"'), script.index('ln -sfn "$RELEASE_DIR"'))
        self.assertNotIn("BEGIN PRIVATE KEY", script)


if __name__ == "__main__":
    unittest.main()
