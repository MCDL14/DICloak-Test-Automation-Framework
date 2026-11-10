from __future__ import annotations

import copy
import io
import json
import os
import plistlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

from core.account_groups import ACCOUNT_PROFILE_ENV, apply_runtime_account_profile, runtime_account_profile
from core.app_config import resolve_app_config
from core.app_packages import (
    APP_PROFILE_ENV, AppPackageError, TEST_ACCOUNT_GROUPS_PATH, TEST_PACKAGE_SETTINGS_PATH,
    apply_runtime_app_profile, default_test_package_settings, load_runtime_app_profile,
    load_test_package_settings, normalize_test_package_settings, resolve_api_url,
    runtime_app_profile, save_test_package_settings, test_package_missing_fields as package_missing_fields,
)
from core.config import ConfigError, DEFAULT_CONFIG, load_config
from core.environment_create_api import EnvironmentCreateApiClient
from core.org_config_api import OrgConfigApiClient, OrgConfigIdentity
from pages.member_page import MemberPage
from tests.p0.member_management.member_open_api import (
    MemberEditApiClient, external_member_id, internal_member_id,
    internal_member_username, internal_member_password,
)
from run import main, parse_args


class AppPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="dicloak-app-package-test-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.environment = mock.patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.platform = mock.patch("core.app_packages.current_platform", return_value="windows")
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.settings = {**default_test_package_settings(), "windows_exe_path": "C:/test-only/DICloak.exe"}
        self.base = copy.deepcopy(DEFAULT_CONFIG)
        self.base["app"].update(exe_path="C:/production/old.exe", executable_path="C:/production/old.exe")
        self.base["account"].update(username="production-placeholder", password="production-placeholder",
                                    team_name="production-team", http_api_key="production-key")

    def _apply(self, settings=None, config=None, *, platform="windows"):
        return apply_runtime_app_profile(
            self.base if config is None else config,
            runtime_app_profile(self.settings if settings is None else settings),
            platform_name=platform,
        )

    def _bundle(self, name="DICloak2", executable="ActualTestExecutable") -> Path:
        bundle = self.root / f"{name}.app"
        (bundle / "Contents" / "MacOS").mkdir(parents=True)
        (bundle / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": executable}))
        target = bundle / "Contents" / "MacOS" / executable
        target.touch()
        return target

    def _write_profiles(self, *, account_kind="test") -> tuple[Path, Path, Path]:
        config_file = self.root / "base.yaml"
        config_file.write_text(yaml.safe_dump(self.base), encoding="utf-8")
        app_file = self.root / "app-profile.yaml"
        app_file.write_text(yaml.safe_dump(runtime_app_profile(self.settings)), encoding="utf-8")
        account_file = self.root / "account-profile.yaml"
        account_file.write_text(yaml.safe_dump(runtime_account_profile({
            "name": "synthetic-test-group", "automation_account": {
                "username": "test-account", "password": "synthetic-test-password", "team_name": "test-team",
            }, "http_api_key": "test-key",
        }, package_kind=account_kind)), encoding="utf-8")
        return config_file, app_file, account_file

    def test_default_settings_have_no_windows_or_account_fallback(self):
        first = default_test_package_settings()
        self.assertEqual(first, {
            "windows_exe_path": "", "macos_app_name": "DICloak2",
            "api_base_url": "http://gin-server-test.dicloak.com", "cdp_port": 9223,
        })
        first["windows_exe_path"] = "changed"
        self.assertEqual(default_test_package_settings()["windows_exe_path"], "")
        self.assertNotEqual(TEST_PACKAGE_SETTINGS_PATH, TEST_ACCOUNT_GROUPS_PATH)

    def test_missing_settings_file_uses_only_test_defaults(self):
        self.assertEqual(load_test_package_settings(self.root / "missing.yaml"), default_test_package_settings())

    def test_settings_round_trip_allows_blank_windows_for_mac_only(self):
        path = self.root / "settings.yaml"
        save_test_package_settings(path, default_test_package_settings())
        self.assertEqual(load_test_package_settings(path), default_test_package_settings())
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_unknown_sensitive_settings_are_rejected_without_echo(self):
        for field in ("private_key_path", "account", "token", "startup_args"):
            with self.subTest(field=field), self.assertRaises(AppPackageError) as caught:
                normalize_test_package_settings({field: "sensitive-marker"})
            self.assertNotIn("sensitive-marker", str(caught.exception))

    def test_settings_reject_non_mapping_or_malformed_yaml(self):
        path = self.root / "settings.yaml"
        for content in ("[not-a-mapping]", "[broken", "", "null"):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(AppPackageError):
                    load_test_package_settings(path)

    def test_only_two_named_mac_packages_are_allowed(self):
        for name in ("Other", "../DICloak", "DICloak3", "", None):
            with self.subTest(name=name), self.assertRaises(AppPackageError):
                normalize_test_package_settings({"macos_app_name": name})

    def test_settings_validate_port_and_text_types(self):
        for port in (0, 65536, True, "9223", 1.5):
            with self.subTest(port=port), self.assertRaises(AppPackageError):
                normalize_test_package_settings({"cdp_port": port})
        with self.assertRaises(AppPackageError):
            normalize_test_package_settings({"windows_exe_path": []})

    def test_test_api_must_be_root_http_url_without_credentials_or_query(self):
        for url in ("ftp://test.example", "https://user:secret@test.example", "https://test.example/gin",
                    "https://test.example?a=b", "https://test.example?", "https://test.example#fragment",
                    "https://test.example#", "https://test.example:bad", "https://test example", "//test.example",
                    "http://gin-server.dicloak.com\\", "http://gin-server%2edicloak.com"):
            with self.subTest(url=url), self.assertRaises(AppPackageError):
                normalize_test_package_settings({"api_base_url": url})

    def test_known_production_api_hosts_are_rejected_in_test_settings(self):
        for host in ("gin-server.dicloak.com", "gin-server.dicloak.net", "app.dicloak.com",
                     "GIN-SERVER.DICLOAK.COM."):
            with self.subTest(host=host), self.assertRaisesRegex(AppPackageError, "生产"):
                normalize_test_package_settings({"api_base_url": "http://" + host})

    def test_settings_normalize_strings_and_trailing_root_slash(self):
        settings = normalize_test_package_settings({"windows_exe_path": "  C:/test/app.exe ",
                                                    "api_base_url": " https://test.example/ "})
        self.assertEqual(settings["windows_exe_path"], "C:/test/app.exe")
        self.assertEqual(settings["api_base_url"], "https://test.example")

    def test_copied_windows_path_removes_only_outer_direction_marks_and_quotes(self):
        expected = "C:/测试包目录/win-unpacked/DICloak.exe"
        for value in ("\u202a" + expected, "\u202a" + expected + "\u202c",
                      '\u200e "' + expected + '" \u200f', "'" + expected + "'",
                      '\ufeff"\u2066' + expected + '\u2069"'):
            with self.subTest(value=repr(value)):
                settings = normalize_test_package_settings({"windows_exe_path": value})
                self.assertEqual(settings["windows_exe_path"], expected)
                applied = self._apply(settings)
                self.assertEqual(applied["app"]["exe_path"].replace("\\", "/"), expected)
        interior = "C:/test\u202apackage/DICloak.exe"
        self.assertEqual(normalize_test_package_settings({"windows_exe_path": interior})["windows_exe_path"], interior)

    def test_copied_path_wrappers_do_not_make_relative_paths_valid(self):
        for value in ("\u202aDICloak.exe\u202c", '\u202a"C:relative.exe"', "\u202a\u202c"):
            with self.subTest(value=repr(value)), self.assertRaises(AppPackageError):
                self._apply({**self.settings, "windows_exe_path": value})

    def test_missing_fields_are_specific_to_selected_platform(self):
        self.assertIn("Windows 测试 APP 可执行文件路径", package_missing_fields(default_test_package_settings(), "windows"))
        self.assertEqual(package_missing_fields(default_test_package_settings(), "macos"), [])
        missing = package_missing_fields({"api_base_url": ""}, "macos")
        self.assertEqual(missing, ["测试服务端 API 根地址"])

    def test_runtime_profile_is_idempotent_and_copies_settings(self):
        first = runtime_app_profile(self.settings)
        self.assertEqual(runtime_app_profile(first), first)
        first["settings"]["cdp_port"] = 9333
        self.assertEqual(self.settings["cdp_port"], 9223)

    def test_runtime_profile_rejects_wrong_kind_version_and_extra_fields(self):
        for updates in ({"version": True}, {"version": 2}, {"package_kind": "production"}, {"token": "secret"}):
            with self.subTest(updates=updates), self.assertRaises(AppPackageError):
                runtime_app_profile({**runtime_app_profile(self.settings), **updates})

    def test_runtime_profile_file_round_trip_and_rejects_plain_settings(self):
        path = self.root / "profile.yaml"
        profile = runtime_app_profile(self.settings)
        path.write_text(yaml.safe_dump(profile), encoding="utf-8")
        self.assertEqual(load_runtime_app_profile(path), profile)
        path.write_text(yaml.safe_dump(self.settings), encoding="utf-8")
        with self.assertRaises(AppPackageError):
            load_runtime_app_profile(path)

    def test_windows_profile_overrides_both_legacy_path_aliases_and_metadata(self):
        self.base["platforms"] = {"windows": {"app": {
            "executable_path": "C:/production/priority.exe", "exe_path": "C:/production/other.exe",
            "work_dir": "C:/production", "process_name": "production.exe", "cdp_auth": {"timeout_seconds": 17},
        }}}
        before = copy.deepcopy(self.base)
        applied = self._apply()
        resolved = resolve_app_config(applied, "windows")
        self.assertEqual(str(resolved.exe_path).replace("\\", "/"), "C:/test-only/DICloak.exe")
        self.assertEqual(resolved.process_name, "DICloak.exe")
        self.assertEqual(applied["app"]["isolation"], "executable_path")
        self.assertEqual(applied["cdp"]["port"], 9223)
        self.assertEqual(applied["cdp"]["host"], "127.0.0.1")
        self.assertEqual(applied["_app_package_kind"], "test")
        self.assertEqual(applied["_app_package_label"], "测试 APP 包")
        self.assertEqual(resolved.cdp_auth["ttl_seconds"], 120)
        self.assertEqual(resolved.cdp_auth["timeout_seconds"], 17)
        self.assertEqual(self.base, before)

    def test_windows_profile_overrides_legacy_platform_shape(self):
        self.base["platforms"] = {"windows": {"executable_path": "C:/prod.exe"}}
        applied = self._apply()
        self.assertEqual(applied["platforms"]["windows"]["exe_path"], applied["app"]["exe_path"])

    def test_blank_windows_path_never_falls_back_to_production(self):
        with self.assertRaisesRegex(AppPackageError, "Windows"):
            self._apply(default_test_package_settings())

    def test_windows_requires_absolute_executable_file_path(self):
        for value in ("DICloak.exe", "C:/test/folder", "C:/test/script.bat", "C:relative.exe"):
            with self.subTest(value=value), self.assertRaises(AppPackageError):
                self._apply({**self.settings, "windows_exe_path": value})

    def test_mac_uses_bundle_executable_metadata_not_guessed_binary_name(self):
        expected = self._bundle(executable="DifferentExecutable")
        with mock.patch("core.app_packages.MACOS_APPLICATIONS_DIR", self.root):
            applied = self._apply(platform="macos")
        self.assertEqual(applied["app"]["exe_path"], str(expected))
        self.assertEqual(applied["app"]["process_name"], "DifferentExecutable")
        self.assertEqual(resolve_app_config(applied, "macos").exe_path, expected)

    def test_mac_can_choose_dicloak_instead_of_dicloak2(self):
        expected = self._bundle(name="DICloak", executable="RealDICloak")
        self._bundle(name="DICloak2", executable="OtherBinary")
        with mock.patch("core.app_packages.MACOS_APPLICATIONS_DIR", self.root):
            applied = self._apply({**self.settings, "macos_app_name": "DICloak"}, platform="macos")
        self.assertEqual(applied["app"]["exe_path"], str(expected))

    def test_mac_missing_bundle_fails_without_using_production_path(self):
        with mock.patch("core.app_packages.MACOS_APPLICATIONS_DIR", self.root):
            with self.assertRaisesRegex(AppPackageError, "Info.plist"):
                self._apply(platform="macos")

    def test_mac_rejects_missing_or_traversing_bundle_executable(self):
        executable = self._bundle()
        plist_file = executable.parent.parent / "Info.plist"
        with mock.patch("core.app_packages.MACOS_APPLICATIONS_DIR", self.root):
            for value in ("../outside", "/absolute", "bad\\file", "", None):
                plist_file.write_bytes(plistlib.dumps({} if value is None else {"CFBundleExecutable": value}))
                with self.subTest(value=value), self.assertRaises(AppPackageError):
                    self._apply(platform="macos")

    def test_unsupported_platform_fails_closed(self):
        with self.assertRaisesRegex(AppPackageError, "Windows"):
            self._apply(platform="linux")

    def test_malformed_base_config_sections_fail_with_safe_error(self):
        for section in ("app", "platforms", "cdp", "api", "account", "test_data"):
            cfg = copy.deepcopy(self.base)
            cfg[section] = "sensitive-marker"
            with self.subTest(section=section), self.assertRaises(AppPackageError) as caught:
                self._apply(config=cfg)
            self.assertNotIn("sensitive-marker", str(caught.exception))

    def test_missing_or_production_account_profile_is_cleared_in_test_mode(self):
        for marker in (None, "production"):
            cfg = copy.deepcopy(self.base)
            cfg["_account_profile_file"] = "synthetic-production-profile.yaml"
            cfg["_account_package_kind"] = marker
            applied = self._apply(config=cfg)
            self.assertTrue(applied["_test_package_account_profile_missing"])
            for name in ("username", "password", "team_name", "http_api_key"):
                self.assertEqual(applied["account"][name], "")
            self.assertEqual(applied["test_data"]["api_member_edit"]["token"], "")
            self.assertEqual(applied["test_data"]["case_external_member"], {"name": "", "email": ""})

    def test_explicit_test_account_marker_preserves_only_selected_test_accounts(self):
        self.base["_account_package_kind"] = "test"
        self.base["account"].update(username="selected-test-user")
        applied = self._apply()
        self.assertNotIn("_test_package_account_profile_missing", applied)
        self.assertEqual(applied["account"]["username"], "selected-test-user")

    def test_reloading_config_always_applies_both_runtime_profiles(self):
        cfg, app_file, account_file = self._write_profiles()
        with mock.patch.dict(os.environ, {APP_PROFILE_ENV: str(app_file), ACCOUNT_PROFILE_ENV: str(account_file)}):
            first = load_config(cfg)
            second = load_config(cfg)
        self.assertEqual(first["account"]["username"], "test-account")
        self.assertEqual(second["account"]["http_api_key"], "test-key")
        self.assertEqual(second["_account_package_kind"], "test")
        self.assertEqual(second["_app_package_kind"], "test")
        self.assertEqual(second["_app_profile_file"], str(app_file.resolve()))
        self.assertEqual(second["cdp"]["port"], 9223)

    def test_cli_loads_existing_profile_with_copied_windows_path_before_running(self):
        self.settings["windows_exe_path"] = "\u202aC:/测试包目录/win-unpacked/DICloak.exe"
        cfg, app_file, account_file = self._write_profiles()
        # Simulate a temporary profile written by the previous UI version.
        app_file.write_text(yaml.safe_dump({
            "version": 1, "package_kind": "test", "settings": self.settings,
        }), encoding="utf-8")
        with mock.patch("run.setup_logger"), mock.patch("run.AutomationRunner") as runner:
            runner.return_value.run.return_value = 0
            result = main(["--config", str(cfg), "--app-profile", str(app_file),
                           "--account-profile", str(account_file), "--case", "synthetic.case"])
        self.assertEqual(result, 0)
        config = runner.call_args.kwargs["config"]
        self.assertEqual(config["app"]["exe_path"].replace("\\", "/"), "C:/测试包目录/win-unpacked/DICloak.exe")
        self.assertEqual(config["_account_package_kind"], "test")
        runner.return_value.run.assert_called_once()

    def test_cli_config_error_is_visible_to_failure_log_filter(self):
        from core.ui_log_filter import unsuccessful_log_text

        output = io.StringIO()
        with mock.patch("run.load_config", side_effect=ConfigError("Windows 测试 APP 必须填写 .exe 文件的绝对路径")), \
                mock.patch("run.setup_logger") as logger, mock.patch("sys.stdout", output):
            self.assertEqual(main([]), 2)
        logger.assert_not_called()
        visible = unsuccessful_log_text(output.getvalue())
        self.assertIn("配置加载失败", visible)
        self.assertIn("绝对路径", visible)

    def test_config_test_profile_applies_after_private_key_sidecar_without_reading_key(self):
        cfg, app_file, _account_file = self._write_profiles()
        cfg.with_name(cfg.name + ".cdp-auth.local.yaml").write_text(
            yaml.safe_dump({"private_key_path": "/remote-only/signing.pem", "script_path": ""}), encoding="utf-8",
        )
        with mock.patch.dict(os.environ, {APP_PROFILE_ENV: str(app_file)}), mock.patch.object(
            Path, "read_bytes", side_effect=AssertionError("must not read a signing key"),
        ):
            applied = load_config(cfg)
        self.assertEqual(resolve_app_config(applied, "windows").cdp_auth["private_key_path"], "/remote-only/signing.pem")

    def test_production_config_without_profile_keeps_existing_paths_and_api(self):
        cfg, _app, _account = self._write_profiles()
        loaded = load_config(cfg)
        self.assertEqual(loaded["app"]["exe_path"], self.base["app"]["exe_path"])
        self.assertEqual(loaded["api"]["base_url"], "")
        self.assertNotIn("_app_package_kind", loaded)
        self.assertEqual(loaded["account"]["username"], "production-placeholder")

    def test_invalid_runtime_profile_is_a_safe_config_error(self):
        cfg, app_file, _ = self._write_profiles()
        app_file.write_text("settings: sensitive-marker\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {APP_PROFILE_ENV: str(app_file)}):
            with self.assertRaises(ConfigError) as caught:
                load_config(cfg)
        self.assertNotIn("sensitive-marker", str(caught.exception))

    def test_cli_accepts_app_profile_and_blocks_test_run_without_test_accounts(self):
        args = parse_args(["--app-profile", "temporary.yaml"])
        self.assertEqual(args.app_profile, "temporary.yaml")
        output = io.StringIO()
        with mock.patch("run.load_config", return_value={"_test_package_account_profile_missing": True}), \
                mock.patch("run.setup_logger") as logger, mock.patch("sys.stdout", output):
            self.assertEqual(main(["--app-profile", "temporary.yaml"]), 2)
        logger.assert_not_called()
        self.assertIn("拒绝复用生产账号", output.getvalue())

    def test_precheck_is_allowed_without_test_accounts_and_does_not_run_cases(self):
        cfg = {"_test_package_account_profile_missing": True, "_app_package_kind": "test"}
        with mock.patch("run.load_config", return_value=cfg), mock.patch("run.setup_logger"), \
                mock.patch("run.AutomationRunner") as runner:
            runner.return_value.run_precheck_only.return_value = 0
            self.assertEqual(main(["--precheck"]), 0)
            runner.return_value.run.assert_not_called()

    def test_api_resolver_keeps_production_defaults_byte_for_byte(self):
        for url in ("https://gin-server.dicloak.com/gin/v1/env", "https://gin-server.dicloak.net/gin/v1/organization",
                    "https://app.dicloak.com/gin/v1/api/member/open/edit?"):
            self.assertEqual(resolve_api_url({}, url), url)

    def test_api_resolver_changes_only_origin_and_preserves_path_and_query(self):
        cfg = {"_app_package_kind": "test", "api": {"base_url": "http://test.example:8080"}}
        self.assertEqual(resolve_api_url(cfg, "https://app.dicloak.com/gin/v1/member?page_no=2"),
                         "http://test.example:8080/gin/v1/member?page_no=2")

    def test_test_api_resolver_never_falls_back_to_missing_or_production_base(self):
        for base in ("", "https://gin-server.dicloak.com"):
            with self.subTest(base=base), self.assertRaises(AppPackageError):
                resolve_api_url({"_app_package_kind": "test", "api": {"base_url": base}},
                                "https://gin-server.dicloak.com/gin/v1/env")

    def test_environment_create_delete_list_all_use_test_origin(self):
        cdp = mock.Mock()
        cdp.config = {"_app_package_kind": "test", "api": {"base_url": "http://test.example"},
                      "account": {"http_api_key": "synthetic-key"}}
        cdp.evaluate.return_value = {"has_token": True, "app_version": "3.0.6"}
        cdp.evaluate_with_args.return_value = {"status": 200, "response_body": json.dumps({"code": 0, "data": {"id": "synthetic-id", "list": []}})}
        client = EnvironmentCreateApiClient(cdp, attempts=1)
        client.create_environment(name="synthetic-name")
        client.delete_environments("synthetic-id")
        client.list_environments(value="synthetic-name")
        args = [call.args[1] for call in cdp.evaluate_with_args.call_args_list]
        self.assertEqual([item["apiUrl"] for item in args], [
            "http://test.example/gin/v1/env", "http://test.example/gin/v1/env/batch",
            "http://test.example/gin/v1/api/request/env",
        ])
        self.assertEqual(args[-1]["httpKey"], "synthetic-key")
        self.assertTrue(all(item["testPackage"] for item in args))
        self.assertIn('redirect: testPackage ? "error" : "follow"', cdp.evaluate_with_args.call_args.args[0])

    def test_organization_get_and_post_use_test_origin(self):
        cdp = mock.Mock()
        cdp.config = {"_app_package_kind": "test", "api": {"base_url": "http://test.example"}}
        cdp.evaluate_with_args.return_value = {"status": 200, "response_body": "{}"}
        client = OrgConfigApiClient(cdp)
        for method in ("GET", "POST"):
            client._request_once(method, OrgConfigIdentity("synthetic-org", "3.0.6"), {})
        for call in cdp.evaluate_with_args.call_args_list:
            self.assertEqual(call.args[1]["apiBase"], "http://test.example/gin/v1/organization")
            self.assertTrue(call.args[1]["testPackage"])

    def test_member_list_script_uses_test_root_and_preserves_filters(self):
        page = MemberPage(None, config={"_app_package_kind": "test", "api": {"base_url": "http://test.example"}})
        script = page._member_api_records_script()
        self.assertIn("http://test.example/gin/v1/member?page_size=200&page_no=1&not_logged=false&detail=true", script)
        self.assertNotIn("gin-server.dicloak.com", script)
        self.assertIn('redirect: "error"', script)

    def test_member_edit_test_mode_never_uses_production_environment_credentials(self):
        cfg = {"_app_package_kind": "test", "api": {"base_url": "http://test.example"}}
        with mock.patch.dict(os.environ, {"DICLOAK_API_MEMBER_EDIT_TOKEN": "production-placeholder",
                                         "DICLOAK_API_MEMBER_EDIT_MEMBER_ID": "production-id"}):
            with self.assertRaisesRegex(AssertionError, "token is empty"):
                MemberEditApiClient(cfg)
            cfg["test_data"] = {"api_member_edit": {"token": "synthetic-test-token"}}
            with self.assertRaisesRegex(AssertionError, "member_id is empty"):
                MemberEditApiClient(cfg)

    def test_test_member_api_rejects_inherited_flat_member_id(self):
        cfg = {
            "_app_package_kind": "test", "api": {"base_url": "http://test.example"},
            "test_data": {"api_member_edit": {"token": "test-token", "external_member_id": "",
                                                "member_id": "production-legacy-id"}},
        }
        with self.assertRaisesRegex(AssertionError, "member_id is empty"):
            MemberEditApiClient(cfg)

    def test_test_member_helpers_never_fall_back_to_flat_or_historical_values(self):
        for explicit in ({}, {"external_member_id": None, "internal_member": {}},
                         {"external_member_id": "", "internal_member": {
                             "member_id": "", "username": "", "password": "",
                         }}):
            with self.subTest(explicit=explicit):
                cfg = {"_app_package_kind": "test", "test_data": {"api_member_edit": {
                    "member_id": "production-legacy-id", "internal_member_id": "production-internal-id",
                    "internal_username": "production-user", "internal_password": "production-password",
                    **explicit,
                }}}
                self.assertEqual(external_member_id(cfg), "")
                self.assertEqual(internal_member_id(cfg), "")
                self.assertEqual(internal_member_username(cfg), "")
                self.assertEqual(internal_member_password(cfg), "")

    def test_selected_test_profile_clears_old_flat_member_alias(self):
        cfg = copy.deepcopy(self.base)
        cfg["test_data"]["api_member_edit"]["member_id"] = "production-legacy-id"
        selected = apply_runtime_account_profile(cfg, runtime_account_profile({
            "automation_account": {"member_id": ""}, "internal_member": {},
        }, package_kind="test"))
        selected["_app_package_kind"] = "test"
        self.assertEqual(selected["test_data"]["api_member_edit"]["member_id"], "")
        self.assertEqual(external_member_id(selected), "")
        self.assertEqual(internal_member_id(selected), "")

    def test_member_edit_uses_test_endpoint_and_explicit_test_credentials(self):
        client = MemberEditApiClient({"_app_package_kind": "test", "api": {"base_url": "http://test.example"},
                                     "test_data": {"api_member_edit": {"token": "synthetic", "external_member_id": "test-id"}}})
        self.assertEqual(client.api_config.base_url, "http://test.example/gin/v1/api/member/open/edit")
        self.assertEqual(client.api_config.member_id, "test-id")

    def test_test_member_api_does_not_follow_redirect_to_other_server(self):
        client = MemberEditApiClient({
            "_app_package_kind": "test", "api": {"base_url": "http://test.example"},
            "test_data": {"api_member_edit": {"token": "synthetic", "external_member_id": "test-id",
                                                "status_retry": {"times": 0}}},
        })
        response = mock.Mock(status_code=302)
        with mock.patch("tests.p0.member_management.member_open_api.requests.get", return_value=response) as get:
            self.assertIs(client._get_with_status_retry("http://test.example/gin/v1/member", 5), response)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])


if __name__ == "__main__":
    unittest.main()
