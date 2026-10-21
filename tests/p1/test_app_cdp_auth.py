from __future__ import annotations

import base64
import copy
import io
import json
import logging
import subprocess
import sys
import tempfile
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core.app import AppManager, AppStartupError
from core import app_cdp_token
from core.app_cdp_auth import (
    AppCdpAuthError,
    auth_enabled,
    generate_app_cdp_token,
    normalized_app_startup_args,
    redact_app_startup_args,
    validate_cdp_auth_setup,
)
from core.app_config import resolve_app_config
from core.app_cdp_token import issue_token
from core.precheck import EnvironmentPrechecker, is_cdp_port_open, is_local_cdp_host
from core.cdp_driver import CDPConnectionError
from core.remote_runner import RemoteHost, RemoteRunRequest, build_remote_command
from core.remote_sync import build_local_manifest
from core.runner import AutomationRunner, ExitCode


_NOW = 1_700_000_000


def _encoded_token(*, payload=None, signature=b"s" * 64) -> str:
    if payload is None:
        payload = {
            "v": 1,
            "aud": "dicloak-app-cdp",
            "iat": _NOW,
            "exp": _NOW + 3600,
            "port": 9222,
        }

    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    return f"{encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))}.{encode(signature)}"


class TestAppCdpAuth(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="dicloak-cdp-auth-test-")
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.script = self.root / "fake token issuer.py"
        self.private_key = self.root / "private placeholder.pem"
        # Only placeholder files are used. The subprocess is mocked in every issuance test.
        self.script.touch()
        self.private_key.touch()
        self.config = {
            "app": {
                "cdp_auth": {
                    "enabled": True,
                    "script_path": str(self.script),
                    "private_key_path": str(self.private_key),
                    "private_key_env": "DICLOAK_CDP_PRIVATE_KEY_PATH",
                    "ttl_seconds": 3600,
                    "timeout_seconds": 10,
                },
                "startup_args": [],
            },
            "cdp": {"port": 9222},
        }
        self.environment = mock.patch.dict("os.environ", {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.platform = mock.patch("core.app_config.current_platform", return_value="windows")
        self.platform.start()
        self.addCleanup(self.platform.stop)

    def _issue(self, output: str | None = None, *, returncode: int = 0, stderr: str = ""):
        completed = subprocess.CompletedProcess(
            args=["issuer"],
            returncode=returncode,
            stdout=_encoded_token() + "\n" if output is None else output,
            stderr=stderr,
        )
        with (
            mock.patch("core.app_cdp_auth.subprocess.run", return_value=completed) as run,
            mock.patch("core.app_cdp_auth.time.time", return_value=_NOW),
        ):
            token = generate_app_cdp_token(self.config)
        return token, run

    def test_explicit_auth_configuration_can_be_enabled_and_disabled(self) -> None:
        self.assertTrue(auth_enabled(self.config))
        self.config["app"]["cdp_auth"]["enabled"] = False
        self.assertFalse(auth_enabled(self.config))

    def test_auth_defaults_enabled_and_rejects_ambiguous_string_flags(self) -> None:
        self.assertTrue(auth_enabled({"app": {}, "cdp": {"port": 9222}}))
        self.config["app"]["cdp_auth"]["enabled"] = "false"
        with self.assertRaises(AppCdpAuthError):
            auth_enabled(self.config)

    def test_platform_auth_configuration_overrides_global_values(self) -> None:
        self.config["platforms"] = {
            "macos": {"app": {"cdp_auth": {"private_key_path": "/local/mac/private.pem", "ttl_seconds": 1800}}}
        }
        resolved = resolve_app_config(self.config, "macos")
        self.assertEqual(resolved.cdp_auth["private_key_path"], "/local/mac/private.pem")
        self.assertEqual(resolved.cdp_auth["ttl_seconds"], 1800)
        self.assertTrue(resolved.cdp_auth["enabled"])
        self.assertEqual(resolved.cdp_auth["script_path"], str(self.script))

    def test_normalization_replaces_stale_port_and_token_options(self) -> None:
        original = [
            "--remote-debugging-port=9333",
            "--dicloak-debug-port",
            "9444",
            "--dicloak-debug-token=stale-secret",
            "--dicloak-debug-token",
            "other-stale-secret",
            "--remote-allow-origins=*",
            "--disable-gpu",
        ]
        normalized = normalized_app_startup_args(self.config, original)
        self.assertEqual(normalized.count("--dicloak-debug-port=9222"), 1)
        self.assertEqual(normalized.count("--remote-allow-origins=*"), 1)
        self.assertIn("--disable-gpu", normalized)
        self.assertFalse(any("remote-debugging-port" in item for item in normalized))
        self.assertFalse(any("stale-secret" in item for item in normalized))
        self.assertNotIn("9444", normalized)
        self.assertIn("--dicloak-debug-token=stale-secret", original)

    def test_disabled_auth_keeps_legacy_arguments_unchanged(self) -> None:
        self.config["app"]["cdp_auth"]["enabled"] = False
        original = ["--remote-debugging-port=9333", "--remote-allow-origins=*", "--disable-gpu"]
        self.assertEqual(normalized_app_startup_args(self.config, original), original)

    def test_redacts_inline_and_split_token_without_mutating_original(self) -> None:
        original = [
            "--dicloak-debug-token=secret-one",
            "--dicloak-debug-token",
            "secret-two",
            "--dicloak-debug-port=9222",
            "--disable-gpu",
        ]
        redacted = redact_app_startup_args(original)
        self.assertNotIn("secret-one", " ".join(redacted))
        self.assertNotIn("secret-two", " ".join(redacted))
        self.assertIn("--dicloak-debug-port=9222", redacted)
        self.assertIn("--disable-gpu", redacted)
        self.assertEqual(original[0], "--dicloak-debug-token=secret-one")

    def test_validation_checks_files_without_reading_or_executing_them(self) -> None:
        with (
            mock.patch("core.app_cdp_auth.subprocess.run") as run,
            mock.patch.object(Path, "read_bytes", side_effect=AssertionError("must not read private key")),
            mock.patch.object(Path, "open", side_effect=AssertionError("must not open private key")),
            mock.patch("core.app_cdp_token.issue_token") as issue,
        ):
            validate_cdp_auth_setup(self.config)
        run.assert_not_called()
        issue.assert_not_called()

    def test_validation_imports_required_signing_dependencies_without_using_them(self) -> None:
        serialization = SimpleNamespace(load_pem_private_key=mock.Mock())
        ed25519 = SimpleNamespace(Ed25519PrivateKey=mock.Mock())
        with (
            mock.patch(
                "core.app_cdp_auth.import_module",
                side_effect=[SimpleNamespace(), serialization, ed25519],
            ) as importer,
            mock.patch("core.app_cdp_auth.subprocess.run") as run,
        ):
            validate_cdp_auth_setup(self.config)
        self.assertEqual(
            importer.call_args_list,
            [
                mock.call("cryptography"),
                mock.call("cryptography.hazmat.primitives.serialization"),
                mock.call("cryptography.hazmat.primitives.asymmetric.ed25519"),
            ],
        )
        serialization.load_pem_private_key.assert_not_called()
        ed25519.Ed25519PrivateKey.assert_not_called()
        run.assert_not_called()

    def test_validation_reports_missing_and_broken_signing_dependencies_safely(self) -> None:
        secret = "NEVER_ECHO_DEPENDENCY_IMPORT_SECRET"
        module_names = (
            "cryptography",
            "cryptography.hazmat.primitives.serialization",
            "cryptography.hazmat.primitives.asymmetric.ed25519",
        )
        modules = {
            "cryptography": SimpleNamespace(),
            "cryptography.hazmat.primitives.serialization": SimpleNamespace(load_pem_private_key=lambda: None),
            "cryptography.hazmat.primitives.asymmetric.ed25519": SimpleNamespace(Ed25519PrivateKey=lambda: None),
        }
        for module_name in module_names:
            for failure_type in (ModuleNotFoundError, ImportError, OSError, RuntimeError):
                with self.subTest(module_name=module_name, error_type=failure_type.__name__):
                    def import_dependency(name):
                        if name == module_name:
                            raise failure_type(secret)
                        return modules[name]

                    with (
                        mock.patch("core.app_cdp_auth.import_module", side_effect=import_dependency),
                        mock.patch("core.app_cdp_auth.subprocess.run") as run,
                        mock.patch.object(Path, "read_bytes", side_effect=AssertionError("must not read private key")),
                    ):
                        with self.assertRaises(AppCdpAuthError) as captured:
                            validate_cdp_auth_setup(self.config)
                    message = str(captured.exception)
                    self.assertIn("cryptography 缺失或无法加载", message)
                    self.assertIn("当前执行框架的 Python 虚拟环境", message)
                    self.assertIn('python -m pip install "cryptography>=41.0.0"', message)
                    self.assertNotIn(secret, "".join(traceback.format_exception(captured.exception)))
                    run.assert_not_called()

    def test_validation_rejects_incomplete_dependency_modules(self) -> None:
        for serialization, ed25519 in (
            (SimpleNamespace(), SimpleNamespace(Ed25519PrivateKey=lambda: None)),
            (SimpleNamespace(load_pem_private_key=lambda: None), SimpleNamespace()),
        ):
            with self.subTest(serialization=hasattr(serialization, "load_pem_private_key")):
                with mock.patch(
                    "core.app_cdp_auth.import_module",
                    side_effect=[SimpleNamespace(), serialization, ed25519],
                ):
                    with self.assertRaisesRegex(AppCdpAuthError, "cryptography 缺失或无法加载"):
                        validate_cdp_auth_setup(self.config)

    def test_validation_requires_existing_script_and_key(self) -> None:
        for field in ("script_path", "private_key_path"):
            with self.subTest(field=field):
                config = copy.deepcopy(self.config)
                config["app"]["cdp_auth"][field] = str(self.root / "missing-file")
                with mock.patch("core.app_cdp_auth.import_module") as importer:
                    with self.assertRaises(AppCdpAuthError):
                        validate_cdp_auth_setup(config)
                importer.assert_not_called()

    def test_private_key_environment_variable_is_supported(self) -> None:
        self.config["app"]["cdp_auth"]["private_key_path"] = ""
        with mock.patch.dict("os.environ", {"DICLOAK_CDP_PRIVATE_KEY_PATH": str(self.private_key)}):
            validate_cdp_auth_setup(self.config)
            _, run = self._issue()
        self.assertIn(str(self.private_key), run.call_args.args[0])

    def test_disabled_auth_does_not_require_private_key_or_script(self) -> None:
        self.config["app"]["cdp_auth"].update(enabled=False, script_path="missing.py", private_key_path="missing.pem")
        with mock.patch("core.app_cdp_auth.import_module", side_effect=ImportError("not installed")) as importer:
            validate_cdp_auth_setup(self.config)
        importer.assert_not_called()

    def test_validation_rejects_invalid_ttl(self) -> None:
        for value in (0, -1, 86401, True, 1.5, "bad"):
            with self.subTest(value=value):
                config = copy.deepcopy(self.config)
                config["app"]["cdp_auth"]["ttl_seconds"] = value
                with self.assertRaises(AppCdpAuthError):
                    validate_cdp_auth_setup(config)

    def test_validation_rejects_invalid_timeout(self) -> None:
        for value in (0, -1, True, "bad"):
            with self.subTest(value=value):
                config = copy.deepcopy(self.config)
                config["app"]["cdp_auth"]["timeout_seconds"] = value
                with self.assertRaises(AppCdpAuthError):
                    validate_cdp_auth_setup(config)

    def test_validation_rejects_invalid_debug_port(self) -> None:
        for value in (0, -1, 65536, True, 9222.5, "9222"):
            with self.subTest(value=value):
                config = copy.deepcopy(self.config)
                config["cdp"]["port"] = value
                with self.assertRaises(AppCdpAuthError):
                    validate_cdp_auth_setup(config)

    def test_generation_uses_current_python_and_argument_list_without_shell(self) -> None:
        token, run = self._issue()
        self.assertEqual(token, _encoded_token())
        command = run.call_args.args[0]
        self.assertIsInstance(command, list)
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1], str(self.script))
        self.assertEqual(command[command.index("--private-key") + 1], str(self.private_key))
        self.assertEqual(command[command.index("--port") + 1], "9222")
        self.assertEqual(command[command.index("--ttl-seconds") + 1], "3600")
        self.assertEqual(run.call_args.kwargs["timeout"], 10)
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_generation_defaults_to_two_minutes_when_ttl_is_omitted(self) -> None:
        del self.config["app"]["cdp_auth"]["ttl_seconds"]
        token = _encoded_token(payload={"v": 1, "aud": "dicloak-app-cdp", "iat": _NOW, "exp": _NOW + 120, "port": 9222})
        generated, run = self._issue(token)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--ttl-seconds") + 1], "120")
        self.assertEqual(generated, token)

    def test_default_ttl_rejects_stale_one_hour_issuer_contract(self) -> None:
        del self.config["app"]["cdp_auth"]["ttl_seconds"]
        with self.assertRaises(AppCdpAuthError):
            self._issue(_encoded_token())

    def test_generation_does_not_cache_tokens_across_launch_attempts(self) -> None:
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=_encoded_token(), stderr="")
        with (
            mock.patch("core.app_cdp_auth.subprocess.run", return_value=completed) as run,
            mock.patch("core.app_cdp_auth.time.time", return_value=_NOW),
        ):
            generate_app_cdp_token(self.config)
            generate_app_cdp_token(self.config)
        self.assertEqual(run.call_count, 2)

    def test_generation_rejects_empty_multiline_and_malformed_stdout(self) -> None:
        for output in ("", " \n", "not-a-token", _encoded_token() + "\nnoise", "noise\n" + _encoded_token(), "{}"):
            with self.subTest(output_length=len(output)):
                with self.assertRaises(AppCdpAuthError):
                    self._issue(output)

    def test_generation_rejects_invalid_payload_contract(self) -> None:
        original = {"v": 1, "aud": "dicloak-app-cdp", "iat": _NOW, "exp": _NOW + 3600, "port": 9222}
        for field, value in (
            ("v", 2),
            ("v", True),
            ("aud", "other-app"),
            ("port", 9333),
            ("port", True),
            ("iat", "bad"),
            ("iat", True),
            ("exp", "bad"),
            ("exp", True),
            ("exp", _NOW - 1),
            ("exp", _NOW + 1800),
        ):
            with self.subTest(field=field, value=value):
                payload = {**original, field: value}
                with self.assertRaises(AppCdpAuthError):
                    self._issue(_encoded_token(payload=payload))

    def test_generation_rejects_non_object_payload(self) -> None:
        for payload in ([], [1, 2], "payload", 42, None):
            with self.subTest(payload=payload):
                # None is the helper's default, so explicitly encode JSON null here.
                if payload is None:
                    output = "bnVsbA." + base64.urlsafe_b64encode(b"s" * 64).rstrip(b"=").decode("ascii")
                else:
                    output = _encoded_token(payload=payload)
                with self.assertRaises(AppCdpAuthError):
                    self._issue(output)

    def test_generation_rejects_short_or_long_signature(self) -> None:
        for signature in (b"", b"s" * 63, b"s" * 65):
            with self.subTest(signature_length=len(signature)):
                with self.assertRaises(AppCdpAuthError):
                    self._issue(_encoded_token(signature=signature))

    def test_generation_rejects_expired_and_nearly_expired_token(self) -> None:
        for expires in (_NOW - 1, _NOW + 1):
            payload = {"v": 1, "aud": "dicloak-app-cdp", "iat": expires - 3600, "exp": expires, "port": 9222}
            with self.subTest(expires=expires):
                with self.assertRaises(AppCdpAuthError):
                    self._issue(_encoded_token(payload=payload))

    def test_generation_accepts_exact_remaining_lifetime_boundary(self) -> None:
        payload = {"v": 1, "aud": "dicloak-app-cdp", "iat": _NOW - 3570, "exp": _NOW + 30, "port": 9222}
        token, _ = self._issue(_encoded_token(payload=payload))
        self.assertEqual(token, _encoded_token(payload=payload))

    def test_generation_accepts_short_valid_ttl_without_forcing_thirty_seconds(self) -> None:
        self.config["app"]["cdp_auth"]["ttl_seconds"] = 1
        payload = {"v": 1, "aud": "dicloak-app-cdp", "iat": _NOW, "exp": _NOW + 1, "port": 9222}
        token, _ = self._issue(_encoded_token(payload=payload))
        self.assertEqual(token, _encoded_token(payload=payload))

    def test_generation_allows_small_clock_skew_but_rejects_future_issue_time(self) -> None:
        for seconds_ahead in (5, 6):
            with self.subTest(seconds_ahead=seconds_ahead):
                issued = _NOW + seconds_ahead
                payload = {"v": 1, "aud": "dicloak-app-cdp", "iat": issued, "exp": issued + 3600, "port": 9222}
                if seconds_ahead == 5:
                    self._issue(_encoded_token(payload=payload))
                else:
                    with self.assertRaises(AppCdpAuthError):
                        self._issue(_encoded_token(payload=payload))

    def test_nonzero_exit_never_exposes_stdout_stderr_or_traceback_secret(self) -> None:
        secret = "NEVER_ECHO_ISSUER_SECRET"
        with self.assertRaises(AppCdpAuthError) as captured:
            self._issue(secret, returncode=1, stderr=secret)
        formatted = "".join(traceback.format_exception(captured.exception))
        self.assertNotIn(secret, formatted)

    def test_subprocess_timeout_or_failure_is_sanitized(self) -> None:
        secret = "NEVER_ECHO_SUBPROCESS_SECRET"
        failures = (
            subprocess.TimeoutExpired(["issuer", secret], timeout=10, output=secret, stderr=secret),
            OSError(secret),
            subprocess.CalledProcessError(1, ["issuer", secret], output=secret, stderr=secret),
        )
        for failure in failures:
            with self.subTest(error_type=type(failure).__name__):
                with mock.patch("core.app_cdp_auth.subprocess.run", side_effect=failure):
                    with self.assertRaises(AppCdpAuthError) as captured:
                        generate_app_cdp_token(self.config)
                formatted = "".join(traceback.format_exception(captured.exception))
                self.assertNotIn(secret, formatted)

    def _manager(self) -> AppManager:
        self.config["app"].update(exe_path=str(self.script), work_dir=str(self.root))
        clock = mock.patch("core.app_cdp_auth.time.time", return_value=_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        return AppManager(self.config, mock.MagicMock(spec=logging.Logger))

    def test_start_injects_fresh_token_and_only_logs_redacted_command(self) -> None:
        manager = self._manager()
        secret = _encoded_token()
        with (
            mock.patch("core.app.generate_app_cdp_token", return_value=secret) as generate,
            mock.patch("core.app.subprocess.Popen") as popen,
            mock.patch.object(manager, "_launch_environment", return_value={}),
        ):
            manager.start()
        generate.assert_called_once_with(self.config)
        command = popen.call_args.args[0]
        self.assertIn("--dicloak-debug-port=9222", command)
        self.assertIn(f"--dicloak-debug-token={secret}", command)
        self.assertIn("--remote-allow-origins=*", command)
        self.assertNotIn(secret, str(manager.logger.mock_calls))

    def test_fresh_launch_generates_before_closing_existing_app(self) -> None:
        manager = self._manager()
        events = []
        with (
            mock.patch("core.app.generate_app_cdp_token", side_effect=lambda _config: events.append("sign") or _encoded_token()),
            mock.patch.object(manager, "close_existing_if_needed", side_effect=lambda: events.append("close")),
            mock.patch("core.app.subprocess.Popen", side_effect=lambda *_args, **_kwargs: events.append("start")),
            mock.patch.object(manager, "_launch_environment", return_value={}),
            mock.patch.object(manager, "wait_until_running", return_value=True),
        ):
            self.assertTrue(manager.launch_fresh())
        self.assertEqual(events, ["sign", "close", "start"])

    def test_fresh_launch_does_not_close_existing_app_when_issuance_fails(self) -> None:
        manager = self._manager()
        with (
            mock.patch("core.app.generate_app_cdp_token", side_effect=AppCdpAuthError("安全签发错误")),
            mock.patch.object(manager, "close_existing_if_needed") as close,
            mock.patch("core.app.subprocess.Popen") as popen,
        ):
            with self.assertRaises(AppStartupError):
                manager.launch_fresh()
        close.assert_not_called()
        popen.assert_not_called()

    def test_fallback_launch_forces_close_even_when_normal_close_policy_is_disabled(self) -> None:
        manager = self._manager()
        self.config["app"]["close_existing_before_start"] = False
        events = []
        with (
            mock.patch("core.app.generate_app_cdp_token", side_effect=lambda _config: events.append("sign") or _encoded_token()),
            mock.patch.object(manager, "is_running", side_effect=[True, False]),
            mock.patch.object(manager, "close", side_effect=lambda: events.append("close")),
            mock.patch("core.app.subprocess.Popen", side_effect=lambda *_args, **_kwargs: events.append("start")),
            mock.patch("core.app.is_windows", return_value=True),
            mock.patch.object(manager, "_launch_environment", return_value={}),
            mock.patch.object(manager, "wait_until_running", return_value=True),
        ):
            self.assertTrue(manager.launch_fresh(force_close_existing=True))
        self.assertEqual(events, ["sign", "close", "start"])

    def test_fallback_launch_does_not_close_existing_app_when_issuance_fails(self) -> None:
        manager = self._manager()
        self.config["app"]["close_existing_before_start"] = False
        with (
            mock.patch("core.app.generate_app_cdp_token", side_effect=AppCdpAuthError("安全签发错误")),
            mock.patch.object(manager, "close") as close,
            mock.patch("core.app.subprocess.Popen") as popen,
        ):
            with self.assertRaises(AppStartupError):
                manager.launch_fresh(force_close_existing=True)
        close.assert_not_called()
        popen.assert_not_called()

    def test_windows_fallback_detaches_stdio_and_uses_independent_process_group(self) -> None:
        manager = self._manager()
        with (
            mock.patch("core.app.generate_app_cdp_token", return_value=_encoded_token()),
            mock.patch.object(manager, "close_existing_if_needed"),
            mock.patch("core.app.subprocess.Popen") as popen,
            mock.patch.object(manager, "_launch_environment", return_value={}),
            mock.patch.object(manager, "wait_until_running", return_value=True),
            mock.patch("core.app.is_windows", return_value=True),
            mock.patch("core.app.subprocess.CREATE_NEW_PROCESS_GROUP", 512, create=True),
        ):
            self.assertTrue(manager.launch_fresh(force_close_existing=True))
        options = popen.call_args.kwargs
        for stream in ("stdin", "stdout", "stderr"):
            self.assertEqual(options[stream], subprocess.DEVNULL)
        self.assertEqual(options["creationflags"] & 512, 512)
        self.assertNotIn("start_new_session", options)

    def test_posix_fallback_detaches_stdio_and_starts_new_session(self) -> None:
        manager = self._manager()
        with (
            mock.patch("core.app.generate_app_cdp_token", return_value=_encoded_token()),
            mock.patch.object(manager, "close_existing_if_needed"),
            mock.patch("core.app.subprocess.Popen") as popen,
            mock.patch.object(manager, "_launch_environment", return_value={}),
            mock.patch.object(manager, "wait_until_running", return_value=True),
            mock.patch("core.app.is_windows", return_value=False),
        ):
            self.assertTrue(manager.launch_fresh(force_close_existing=True))
        options = popen.call_args.kwargs
        for stream in ("stdin", "stdout", "stderr"):
            self.assertEqual(options[stream], subprocess.DEVNULL)
        self.assertIs(options["start_new_session"], True)
        self.assertNotIn("creationflags", options)

    def test_normal_managed_launch_does_not_change_stdio_or_process_group(self) -> None:
        manager = self._manager()
        with (
            mock.patch("core.app.generate_app_cdp_token", return_value=_encoded_token()),
            mock.patch.object(manager, "close_existing_if_needed"),
            mock.patch("core.app.subprocess.Popen") as popen,
            mock.patch.object(manager, "_launch_environment", return_value={}),
            mock.patch.object(manager, "wait_until_running", return_value=True),
        ):
            self.assertTrue(manager.launch_fresh())
        options = popen.call_args.kwargs
        for option in ("stdin", "stdout", "stderr", "creationflags", "start_new_session"):
            self.assertNotIn(option, options)

    def test_fresh_launch_revalidates_expiry_after_waiting_for_existing_app_to_close(self) -> None:
        manager = self._manager()
        self.config["app"]["cdp_auth"]["ttl_seconds"] = 1
        token = _encoded_token(payload={"v": 1, "aud": "dicloak-app-cdp", "iat": _NOW, "exp": _NOW + 1, "port": 9222})
        with (
            mock.patch("core.app_cdp_auth.time.time", return_value=_NOW) as clock,
            mock.patch("core.app.generate_app_cdp_token", return_value=token) as generate,
            mock.patch.object(
                manager,
                "close_existing_if_needed",
                side_effect=lambda: setattr(clock, "return_value", _NOW + 2),
            ) as close,
            mock.patch("core.app.subprocess.Popen") as popen,
            mock.patch.object(manager, "_launch_environment", return_value={}),
        ):
            with self.assertRaises(AppStartupError) as captured:
                manager.launch_fresh()
        generate.assert_called_once()
        close.assert_called_once()
        popen.assert_not_called()
        self.assertNotIn(token, "".join(traceback.format_exception(captured.exception)))
        self.assertNotIn(token, str(manager.logger.mock_calls))

    def test_disabled_auth_launch_avoids_signing_and_preserves_legacy_port(self) -> None:
        manager = self._manager()
        self.config["app"]["cdp_auth"]["enabled"] = False
        self.config["app"]["startup_args"] = ["--remote-debugging-port=9222", "--remote-allow-origins=*"]
        with (
            mock.patch("core.app.generate_app_cdp_token") as generate,
            mock.patch("core.app.subprocess.Popen") as popen,
            mock.patch.object(manager, "_launch_environment", return_value={}),
        ):
            manager.start()
        generate.assert_not_called()
        self.assertEqual(popen.call_args.args[0][1:], self.config["app"]["startup_args"])

    def test_launch_error_traceback_never_echoes_token(self) -> None:
        manager = self._manager()
        secret = _encoded_token()
        with (
            mock.patch("core.app.generate_app_cdp_token", return_value=secret),
            mock.patch("core.app.subprocess.Popen", side_effect=OSError(f"could not start --dicloak-debug-token={secret}")),
            mock.patch.object(manager, "_launch_environment", return_value={}),
        ):
            with self.assertRaises(AppStartupError) as captured:
                manager.start()
        self.assertNotIn(secret, "".join(traceback.format_exception(captured.exception)))
        self.assertNotIn(secret, str(manager.logger.mock_calls))

    def test_attach_precheck_skips_startup_arguments_and_private_key_validation(self) -> None:
        self._manager()
        self.config["app"]["cdp_auth"]["private_key_path"] = "missing-private-key.pem"
        self.config["app"]["startup_args"] = ["--dicloak-debug-token=never-log-attached-secret"]
        prechecker = EnvironmentPrechecker(self.config, mock.MagicMock(spec=logging.Logger))
        with (
            mock.patch.object(prechecker, "_check_test_data"),
            mock.patch.object(prechecker, "_check_cdp"),
            mock.patch.object(prechecker, "_check_feishu"),
            mock.patch("core.precheck.validate_cdp_auth_setup") as validate,
            mock.patch("core.precheck.normalized_app_startup_args") as normalize,
            mock.patch("core.app_cdp_auth.subprocess.run") as run,
            mock.patch("core.app_cdp_auth.import_module", side_effect=ImportError("not installed")) as importer,
        ):
            result = prechecker.run(attach_existing_app=True)
        self.assertTrue(result.passed)
        validate.assert_not_called()
        normalize.assert_not_called()
        run.assert_not_called()
        importer.assert_not_called()
        self.assertNotIn("never-log-attached-secret", str(prechecker.logger.mock_calls))

    def test_startup_precheck_reports_unavailable_signing_dependency_before_launch(self) -> None:
        self._manager()
        prechecker = EnvironmentPrechecker(self.config, mock.MagicMock(spec=logging.Logger))
        secret = "NEVER_ECHO_PRECHECK_DEPENDENCY_SECRET"
        with (
            mock.patch.object(prechecker, "_check_test_data"),
            mock.patch.object(prechecker, "_check_cdp"),
            mock.patch.object(prechecker, "_check_feishu"),
            mock.patch("core.app_cdp_auth.import_module", side_effect=ImportError(secret)),
            mock.patch("core.app_cdp_auth.subprocess.run") as run,
            mock.patch.object(Path, "read_bytes", side_effect=AssertionError("must not read private key")),
        ):
            result = prechecker.run()
        self.assertFalse(result.passed)
        self.assertEqual(len(result.failed_items), 1)
        self.assertEqual(result.failed_items[0].name, "APP startup credential configuration")
        self.assertIn("cryptography 缺失或无法加载", result.failed_items[0].message)
        self.assertIn("当前执行框架的 Python 虚拟环境", result.failed_items[0].message)
        self.assertNotIn(secret, str(prechecker.logger.mock_calls))
        run.assert_not_called()

    def test_startup_precheck_checks_configuration_without_issuing_token(self) -> None:
        self._manager()
        self.config["app"]["startup_args"] = ["--dicloak-debug-token=never-log-precheck-secret"]
        prechecker = EnvironmentPrechecker(self.config, mock.MagicMock(spec=logging.Logger))
        with (
            mock.patch.object(prechecker, "_check_test_data"),
            mock.patch.object(prechecker, "_check_cdp"),
            mock.patch.object(prechecker, "_check_feishu"),
            mock.patch("core.app_cdp_auth.subprocess.run") as run,
        ):
            result = prechecker.run()
        self.assertTrue(result.passed)
        credential_item = next(item for item in result.items if item.name == "APP startup credential configuration")
        self.assertIn("cryptography", credential_item.message)
        self.assertIn("未读取私钥或签发凭证", credential_item.message)
        run.assert_not_called()
        self.assertNotIn("never-log-precheck-secret", str(prechecker.logger.mock_calls))


class TestAppCdpIssuerContract(unittest.TestCase):
    def test_direct_issuer_omitted_ttl_expires_in_two_minutes(self) -> None:
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            self.skipTest("cryptography is not installed")
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        token = issue_token(pem, 9222, now_seconds=_NOW)
        encoded = token.split(".")[0]
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        self.assertEqual(payload["exp"] - payload["iat"], 120)

    def test_cli_and_issuer_defaults_are_two_minutes(self) -> None:
        self.assertEqual(app_cdp_token.DEFAULT_TTL_SECONDS, 120)
        stdout = io.StringIO()
        with (
            mock.patch("core.app_cdp_token.Path.read_bytes", return_value=b"placeholder-key"),
            mock.patch("core.app_cdp_token.issue_token", return_value="safe-placeholder-token") as issue,
            mock.patch("core.app_cdp_token.sys.stdout", stdout),
            mock.patch("core.app_cdp_token.sys.stderr", io.StringIO()),
        ):
            result = app_cdp_token.main(["--private-key", "placeholder.pem", "--port", "9222"])
        self.assertEqual(result, 0)
        issue.assert_called_once_with(b"placeholder-key", 9222, 120)
        self.assertEqual(stdout.getvalue(), "safe-placeholder-token\n")

    def test_cli_explicit_ttl_remains_configurable(self) -> None:
        with (
            mock.patch("core.app_cdp_token.Path.read_bytes", return_value=b"placeholder-key"),
            mock.patch("core.app_cdp_token.issue_token", return_value="safe-placeholder-token") as issue,
            mock.patch("core.app_cdp_token.sys.stdout", io.StringIO()),
            mock.patch("core.app_cdp_token.sys.stderr", io.StringIO()),
        ):
            result = app_cdp_token.main(["--private-key", "placeholder.pem", "--port", "9222", "--ttl-seconds", "3600"])
        self.assertEqual(result, 0)
        issue.assert_called_once_with(b"placeholder-key", 9222, 3600)

    def test_ed25519_signature_covers_encoded_payload_using_ephemeral_key(self) -> None:
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            self.skipTest("cryptography is not installed")
        # A new in-memory key is generated solely for this isolated unit test.
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        token = issue_token(pem, 9222, 3600, now_seconds=_NOW)
        encoded, signature = token.split(".")
        key.public_key().verify(base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)), encoded.encode("ascii"))
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        self.assertEqual(payload, {"v": 1, "aud": "dicloak-app-cdp", "iat": _NOW, "exp": _NOW + 3600, "port": 9222})

    def test_issuer_rejects_invalid_port_ttl_and_time_without_reading_private_key(self) -> None:
        for kwargs in (
            {"port": True},
            {"port": 0},
            {"port": 65536},
            {"port": 9222, "ttl_seconds": True},
            {"port": 9222, "ttl_seconds": 86401},
            {"port": 9222, "now_seconds": -1},
            {"port": 9222, "now_seconds": True},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    issue_token(b"not-a-private-key", **kwargs)

    def test_issuer_rejects_public_or_encrypted_key_without_echoing_it(self) -> None:
        for pem in (b"-----BEGIN PUBLIC KEY-----\nSECRET", b"-----BEGIN ENCRYPTED PRIVATE KEY-----\nSECRET"):
            with self.subTest(header=pem.splitlines()[0]):
                with self.assertRaises(ValueError) as captured:
                    issue_token(pem, 9222, now_seconds=_NOW)
                self.assertNotIn("SECRET", str(captured.exception))


class TestAppCdpExecutionBoundaries(unittest.TestCase):
    def _run_with_dependencies(
        self,
        *,
        port_open=True,
        attach=True,
        precheck_passed=True,
        precheck_enabled=True,
        empty_suite=False,
        launch_error=None,
        connect_error=None,
        host="127.0.0.1",
    ):
        config = {
            "run": {"precheck_before_run": precheck_enabled},
            "feishu": {"enabled": False},
            "app": {"close_existing_before_start": False},
            "cdp": {"host": host, "port": 9222},
        }
        probe_options = {"return_value": port_open} if isinstance(port_open, bool) else {"side_effect": port_open}
        with (
            mock.patch("core.runner.FeishuNotifier"),
            mock.patch("core.runner.EnvironmentPrechecker") as checker_type,
            mock.patch("core.runner.is_cdp_port_open", **probe_options) as probe,
            mock.patch("core.runner.AppManager") as app_type,
            mock.patch("core.runner.CDPDriver") as driver_type,
        ):
            checker_type.return_value.run.return_value = SimpleNamespace(passed=precheck_passed, failed_items=[])
            app_type.return_value.launch_fresh.return_value = True
            if launch_error is not None:
                app_type.return_value.launch_fresh.side_effect = launch_error
            if connect_error is not None:
                driver_type.return_value.connect.side_effect = connect_error
            runner = AutomationRunner(config, mock.MagicMock(spec=logging.Logger))
            suite = unittest.TestSuite([] if empty_suite else [unittest.FunctionTestCase(lambda: None)])
            with (
                mock.patch.object(runner, "_build_suite", return_value=suite),
                mock.patch.object(runner, "_run_suite", return_value=SimpleNamespace(success=True)) as run_suite,
            ):
                result = runner.run(attach_existing_app=attach)
        return SimpleNamespace(
            result=result,
            checker=checker_type.return_value,
            app=app_type.return_value,
            app_type=app_type,
            driver=driver_type.return_value,
            probe=probe,
            run_suite=run_suite,
        )

    def test_runner_attach_mode_never_starts_or_stops_user_app(self) -> None:
        config = {"run": {"precheck_before_run": True}, "feishu": {"enabled": False}}
        with (
            mock.patch("core.runner.FeishuNotifier"),
            mock.patch("core.runner.EnvironmentPrechecker") as checker_type,
            mock.patch("core.runner.is_cdp_port_open", return_value=True),
            mock.patch("core.runner.AppManager") as app_type,
            mock.patch("core.runner.CDPDriver") as driver_type,
            mock.patch("core.app.generate_app_cdp_token") as generate,
        ):
            checker_type.return_value.run.return_value = SimpleNamespace(passed=True)
            runner = AutomationRunner(config, mock.MagicMock(spec=logging.Logger))
            suite = unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
            with (
                mock.patch.object(runner, "_build_suite", return_value=suite),
                mock.patch.object(runner, "_run_suite", return_value=SimpleNamespace(success=True)),
            ):
                result = runner.run(attach_existing_app=True)
        self.assertEqual(result, ExitCode.SUCCESS)
        checker_type.return_value.run.assert_called_once_with(attach_existing_app=True)
        app_type.return_value.launch_fresh.assert_not_called()
        app_type.return_value.close.assert_not_called()
        generate.assert_not_called()
        driver_type.return_value.connect.assert_called_once()

    def test_runner_attach_missing_port_forces_fresh_launch_but_keeps_app_after_tests(self) -> None:
        execution = self._run_with_dependencies(port_open=False)
        self.assertEqual(execution.result, ExitCode.SUCCESS)
        execution.checker.run.assert_called_once_with(attach_existing_app=False)
        execution.app.launch_fresh.assert_called_once_with(force_close_existing=True)
        execution.app.close.assert_not_called()
        execution.driver.connect.assert_called_once()
        execution.run_suite.assert_called_once()
        execution.probe.assert_called_once()

    def test_runner_attach_missing_port_runs_fallback_even_with_precheck_disabled(self) -> None:
        execution = self._run_with_dependencies(port_open=False, precheck_enabled=False)
        self.assertEqual(execution.result, ExitCode.SUCCESS)
        execution.checker.run.assert_not_called()
        execution.app.launch_fresh.assert_called_once_with(force_close_existing=True)
        execution.app.close.assert_not_called()

    def test_runner_missing_port_failed_precheck_does_not_start_or_close_app(self) -> None:
        execution = self._run_with_dependencies(port_open=False, precheck_passed=False)
        self.assertEqual(execution.result, ExitCode.CONFIG_OR_PRECHECK_ERROR)
        execution.app_type.assert_not_called()
        execution.run_suite.assert_not_called()

    def test_runner_missing_port_failed_signing_does_not_attempt_cdp_or_tests(self) -> None:
        execution = self._run_with_dependencies(port_open=False, launch_error=AppStartupError("安全签发错误"))
        self.assertEqual(execution.result, ExitCode.APP_OR_CDP_ERROR)
        execution.app.launch_fresh.assert_called_once_with(force_close_existing=True)
        execution.app.close.assert_not_called()
        execution.driver.connect.assert_not_called()
        execution.run_suite.assert_not_called()

    def test_runner_listening_port_with_failed_cdp_never_restarts_app(self) -> None:
        execution = self._run_with_dependencies(port_open=True, connect_error=CDPConnectionError("CDP 握手失败"))
        self.assertEqual(execution.result, ExitCode.APP_OR_CDP_ERROR)
        execution.app.launch_fresh.assert_not_called()
        execution.app.close.assert_not_called()
        execution.run_suite.assert_not_called()

    def test_runner_reuse_decision_is_not_changed_by_a_second_port_probe(self) -> None:
        execution = self._run_with_dependencies(port_open=[True, False])
        self.assertEqual(execution.result, ExitCode.SUCCESS)
        execution.probe.assert_called_once()
        execution.checker.run.assert_called_once_with(attach_existing_app=True)
        execution.app.launch_fresh.assert_not_called()
        execution.app.close.assert_not_called()

    def test_runner_missing_remote_cdp_port_never_restarts_local_app(self) -> None:
        execution = self._run_with_dependencies(port_open=False, host="192.0.2.10")
        self.assertEqual(execution.result, ExitCode.APP_OR_CDP_ERROR)
        execution.app.launch_fresh.assert_not_called()
        execution.app.close.assert_not_called()
        execution.driver.connect.assert_not_called()
        execution.run_suite.assert_not_called()

    def test_runner_fallback_accepts_localhost_and_ipv6_loopback(self) -> None:
        for host in ("localhost", "::1"):
            with self.subTest(host=host):
                execution = self._run_with_dependencies(port_open=False, host=host)
                self.assertEqual(execution.result, ExitCode.SUCCESS)
                execution.app.launch_fresh.assert_called_once_with(force_close_existing=True)
                execution.app.close.assert_not_called()

    def test_runner_normal_mode_keeps_existing_managed_launch_policy(self) -> None:
        execution = self._run_with_dependencies(attach=False)
        self.assertEqual(execution.result, ExitCode.SUCCESS)
        execution.probe.assert_not_called()
        execution.checker.run.assert_called_once_with(attach_existing_app=False)
        execution.app.launch_fresh.assert_called_once_with()
        execution.app.close.assert_called_once_with()

    def test_runner_empty_suite_does_not_fallback_start_or_close_app(self) -> None:
        execution = self._run_with_dependencies(port_open=False, empty_suite=True)
        self.assertEqual(execution.result, ExitCode.SUCCESS)
        execution.app_type.assert_not_called()
        execution.run_suite.assert_not_called()

    def test_precheck_only_forwards_attach_mode(self) -> None:
        with (
            mock.patch("core.runner.FeishuNotifier"),
            mock.patch("core.runner.EnvironmentPrechecker") as checker_type,
            mock.patch("core.runner.is_cdp_port_open", return_value=True),
        ):
            checker_type.return_value.run.return_value = SimpleNamespace(passed=True)
            runner = AutomationRunner({"feishu": {"enabled": False}}, mock.MagicMock(spec=logging.Logger))
            result = runner.run_precheck_only(attach_existing_app=True)
        self.assertEqual(result, ExitCode.SUCCESS)
        checker_type.return_value.run.assert_called_once_with(attach_existing_app=True)

    def test_precheck_only_missing_port_checks_fallback_config_without_touching_app(self) -> None:
        with (
            mock.patch("core.runner.FeishuNotifier"),
            mock.patch("core.runner.EnvironmentPrechecker") as checker_type,
            mock.patch("core.runner.is_cdp_port_open", return_value=False),
            mock.patch("core.runner.AppManager") as app_type,
            mock.patch("core.app.generate_app_cdp_token") as generate,
        ):
            checker_type.return_value.run.return_value = SimpleNamespace(passed=True)
            runner = AutomationRunner({"feishu": {"enabled": False}}, mock.MagicMock(spec=logging.Logger))
            result = runner.run_precheck_only(attach_existing_app=True)
        self.assertEqual(result, ExitCode.SUCCESS)
        checker_type.return_value.run.assert_called_once_with(attach_existing_app=False)
        app_type.assert_not_called()
        generate.assert_not_called()

    def test_port_probe_uses_configured_host_and_port(self) -> None:
        config = {"cdp": {"host": "localhost", "port": 9333}}
        with mock.patch("core.precheck._is_port_open", return_value=True) as probe:
            self.assertTrue(is_cdp_port_open(config))
        probe.assert_called_once_with("localhost", 9333)
        with mock.patch("core.precheck._is_port_open", return_value=False) as probe:
            self.assertFalse(is_cdp_port_open({}))
        probe.assert_called_once_with("127.0.0.1", 9222)

    def test_fallback_host_policy_only_accepts_loopback_addresses(self) -> None:
        for host in ("127.0.0.1", "127.0.0.2", "localhost", "LOCALHOST.", "::1"):
            with self.subTest(host=host):
                self.assertTrue(is_local_cdp_host({"cdp": {"host": host}}))
        for host in ("0.0.0.0", "192.0.2.10", "remote.example", "::"):
            with self.subTest(host=host):
                self.assertFalse(is_local_cdp_host({"cdp": {"host": host}}))

    def test_remote_precheck_command_preserves_attach_existing_app_flag(self) -> None:
        host = RemoteHost(name="local-test", host="127.0.0.1", username="tester", project_dir="/tmp/dicloak-test")
        command = build_remote_command(host, RemoteRunRequest(scope="precheck", attach_existing_app=True))
        self.assertIn("--precheck", command)
        self.assertIn("--attach-existing-app", command)

    def test_private_key_files_are_excluded_even_with_custom_sync_rules(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dicloak-key-sync-test-") as raw_directory:
            root = Path(raw_directory)
            (root / "config").mkdir()
            (root / "nested").mkdir()
            (root / "config" / "remote_sync.yaml").write_text("include: ['**']\nexclude: []\n", encoding="utf-8")
            (root / "run.py").touch()
            private_files = ("private.pem", "private.KEY", "nested/private.PeM", "config/signing.kEy")
            for relative in private_files:
                (root / relative).touch()
            with mock.patch("core.remote_sync._git_info", return_value={}):
                _, files = build_local_manifest(root)
            synced = {relative for relative, _ in files}
        self.assertIn("run.py", synced)
        self.assertFalse(set(private_files) & synced)


if __name__ == "__main__":
    unittest.main()
