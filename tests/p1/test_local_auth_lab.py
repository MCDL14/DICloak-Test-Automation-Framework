from __future__ import annotations

import json
import os
import socket
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from http import HTTPStatus
from http.cookies import SimpleCookie
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from core.local_auth_lab.client import LocalAuthLabClient
from core.local_auth_lab.credentials import (
    local_auth_lab_login_credentials,
    local_auth_lab_login_credentials_by_site,
)
from core.local_auth_lab.precheck import LocalAuthLabPrechecker
from core.local_auth_lab.security import issue_token, validate_token
from core.local_auth_lab.server import LocalAuthLabServer
from core.local_auth_lab.settings import DEFAULT_DOMAINS, LocalAuthLabSettings


class LocalAuthLabLoginCredentialTests(unittest.TestCase):
    def test_reads_shared_login_credentials_for_all_sites(self) -> None:
        config = _shared_login_config()

        self.assertEqual(
            local_auth_lab_login_credentials_by_site(config),
            {
                "cookie": ("MCDL004", "M12345678"),
                "localstorage": ("MCDL005", "M12345678"),
                "indexeddb": ("MCDL006", "M12345678"),
            },
        )

    def test_rejects_old_or_mismatched_site_credentials(self) -> None:
        config = _shared_login_config()
        config["test_data"]["local_auth_lab_login"]["cookie"]["username"] = "MCDL005"

        with self.assertRaisesRegex(AssertionError, "cookie 账号配置错误"):
            local_auth_lab_login_credentials(config, "cookie")

    def test_rejects_mismatched_password(self) -> None:
        config = _shared_login_config()
        config["test_data"]["local_auth_lab_login"]["indexeddb"]["password"] = "other"

        with self.assertRaisesRegex(AssertionError, "indexeddb 密码配置错误"):
            local_auth_lab_login_credentials(config, "indexeddb")


class LocalAuthLabComponentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.port = _available_port()
        self.settings = LocalAuthLabSettings(
            enabled=True,
            port=self.port,
            database_path=Path(self.temp_dir.name) / "auth.db",
            template_dir=Path.cwd() / "web_templates" / "local_auth_lab",
            signing_secret="unit-test-signing-secret-1234567890",
            admin_key="unit-test-admin-key-1234567890",
            credentials_persistent=True,
        )
        self.server = LocalAuthLabServer(self.settings).start()

    def tearDown(self) -> None:
        self.server.stop()
        self.temp_dir.cleanup()

    def test_health_and_control_page_expose_three_sites_without_hardcoded_port(self) -> None:
        health = LocalAuthLabClient(self.settings).health()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["originMode"], "localhost")
        self.assertEqual(set(health["sites"]), {"cookie", "localstorage", "indexeddb"})
        self.assertEqual(health["domains"], DEFAULT_DOMAINS)

        status, _, body = self._request("control", "GET", "/")
        self.assertEqual(status, HTTPStatus.OK)
        text = body.decode("utf-8")
        self.assertIn(f"cookie.dicloak.localhost:{self.port}", text)
        self.assertNotIn("{{COOKIE_URL}}", text)

        css_status, _, _ = self._request("control", "GET", "/static/styles.css")
        self.assertEqual(css_status, HTTPStatus.OK)

        config = {
            "_project_root": self.temp_dir.name,
            "local_auth_lab": {
                "enabled": True,
                "origin_mode": "localhost",
                "port": self.port,
                "database_path": str(self.settings.database_path),
                "template_dir": str(self.settings.template_dir),
                "credentials_path": str(Path(self.temp_dir.name) / "precheck-credentials.json"),
            },
        }
        env = {
            "DICLOAK_AUTH_LAB_SIGNING_SECRET": self.settings.signing_secret,
            "DICLOAK_AUTH_LAB_ADMIN_KEY": self.settings.admin_key,
        }
        real_getaddrinfo = socket.getaddrinfo

        def reject_domain_lookup(host: str, *args: object, **kwargs: object) -> object:
            self.assertNotIn(host, DEFAULT_DOMAINS.values())
            return real_getaddrinfo(host, *args, **kwargs)

        with patch.dict(os.environ, env), patch(
            "core.local_auth_lab.precheck.socket.getaddrinfo",
            side_effect=reject_domain_lookup,
        ):
            self.assertTrue(LocalAuthLabPrechecker(config).run().passed)

    def test_persistent_credentials_survive_reload_and_ignore_later_env_rotation(self) -> None:
        root = Path(self.temp_dir.name) / "persistent"
        config = {
            "_project_root": str(root),
            "local_auth_lab": {
                "enabled": True,
                "template_dir": str(self.settings.template_dir),
                "database_path": "test_data/local_auth_lab/auth.db",
                "credentials_path": "test_data/local_auth_lab/credentials.json",
            },
        }
        first_env = {
            "DICLOAK_AUTH_LAB_SIGNING_SECRET": "first-persistent-signing-secret-1234567890",
            "DICLOAK_AUTH_LAB_ADMIN_KEY": "first-persistent-admin-key-1234567890",
        }
        second_env = {
            "DICLOAK_AUTH_LAB_SIGNING_SECRET": "different-signing-secret-1234567890",
            "DICLOAK_AUTH_LAB_ADMIN_KEY": "different-admin-key-1234567890",
        }
        with patch.dict(os.environ, first_env):
            first = LocalAuthLabSettings.from_config(config).ensure_persistent_credentials()
        with patch.dict(os.environ, second_env):
            second = LocalAuthLabSettings.from_config(config).ensure_persistent_credentials()

        self.assertEqual(first.signing_secret, second.signing_secret)
        self.assertEqual(first.admin_key, second.admin_key)
        self.assertTrue(second.credentials_persistent)
        self.assertEqual(second.session_ttl_seconds, 15552000)
        self.assertNotIn(first.signing_secret, repr(first))

    def test_registration_persists_but_does_not_create_login_state(self) -> None:
        status, headers, payload = self._json_request(
            "cookie",
            "POST",
            "/api/register",
            {"username": "persist_user", "password": "password123", "confirmPassword": "password123"},
        )
        self.assertEqual(status, HTTPStatus.CREATED)
        self.assertEqual(payload["code"], "REGISTERED")
        self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(self.server.database.state_summary(), {"users": 1, "sessions": 0, "activeSessions": 0})

        self.server.stop()
        self.server = LocalAuthLabServer(self.settings).start()
        login_status, _, login = self._json_request(
            "cookie", "POST", "/api/login", {"username": "persist_user", "password": "password123"}
        )
        self.assertEqual(login_status, HTTPStatus.OK)
        self.assertEqual(login["username"], "persist_user")

    def test_each_site_issues_only_the_expected_transport(self) -> None:
        for site_id in ("cookie", "localstorage", "indexeddb"):
            username = f"user_{site_id}"
            LocalAuthLabClient(self.settings).ensure_user(site_id, username, "password123")
            status, headers, payload = self._json_request(
                site_id,
                "POST",
                "/api/login",
                {"username": username, "password": "password123", "runId": "component-run"},
            )
            self.assertEqual(status, HTTPStatus.OK)
            self.assertEqual(payload["siteId"], site_id)
            self.assertEqual(payload["runId"], "component-run")
            self.assertEqual(
                payload["storageType"],
                {"cookie": "cookie", "localstorage": "localStorage", "indexeddb": "indexedDB"}[site_id],
            )
            if site_id == "cookie":
                self.assertNotIn("token", payload)
                self.assertIn("HttpOnly", headers["Set-Cookie"])
                cookie = SimpleCookie()
                cookie.load(headers["Set-Cookie"])
                token = cookie[self.settings.cookie_name].value
                token_payload = validate_token(token, self.settings.signing_secret, "cookie")
                self.assertTrue(
                    LocalAuthLabClient(self.settings).revoke_session("cookie", token_payload["jti"])["revoked"]
                )
                dropped_status, dropped_headers, dropped = self._json_request(
                    "cookie",
                    "GET",
                    "/api/session",
                    headers={"Cookie": f"{self.settings.cookie_name}={token}"},
                )
                self.assertEqual(dropped_status, HTTPStatus.UNAUTHORIZED)
                self.assertEqual(dropped["reason"], "TOKEN_REVOKED")
                self.assertIn("Max-Age=0", dropped_headers["Set-Cookie"])
            else:
                self.assertTrue(payload["token"])
                self.assertNotIn("Set-Cookie", headers)

    def test_session_endpoint_rejects_cross_site_token(self) -> None:
        client = LocalAuthLabClient(self.settings)
        client.ensure_user("localstorage", "cross_user", "password123")
        _, _, login = self._json_request(
            "localstorage",
            "POST",
            "/api/login",
            {"username": "cross_user", "password": "password123"},
        )
        status, _, payload = self._json_request(
            "indexeddb",
            "GET",
            "/api/session",
            headers={"Authorization": f"Bearer {login['token']}"},
        )
        self.assertEqual(status, HTTPStatus.UNAUTHORIZED)
        self.assertEqual(payload["reason"], "TOKEN_SITE_MISMATCH")

        token_payload = validate_token(login["token"], self.settings.signing_secret, "localstorage")
        self.assertTrue(client.revoke_session("localstorage", token_payload["jti"])["revoked"])
        revoked_status, _, revoked = self._json_request(
            "localstorage",
            "GET",
            "/api/session",
            headers={"Authorization": f"Bearer {login['token']}"},
        )
        self.assertEqual(revoked_status, HTTPStatus.UNAUTHORIZED)
        self.assertEqual(revoked["reason"], "TOKEN_REVOKED")

    def test_existing_session_is_migrated_to_persistent_key_and_six_month_ttl(self) -> None:
        client = LocalAuthLabClient(self.settings)
        client.ensure_user("localstorage", "legacy_user", "password123")
        _, _, login = self._json_request(
            "localstorage",
            "POST",
            "/api/login",
            {"username": "legacy_user", "password": "password123", "runId": "legacy-run"},
        )
        legacy_token = login["token"]

        self.server.stop()
        migrated_settings = replace(
            self.settings,
            signing_secret="new-persistent-signing-secret-1234567890",
            session_ttl_seconds=15552000,
        )
        self.server = LocalAuthLabServer(migrated_settings).start()
        status, _, migrated = self._json_request(
            "localstorage",
            "GET",
            "/api/session",
            headers={"Authorization": f"Bearer {legacy_token}"},
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(migrated["sessionMigrated"])
        self.assertNotEqual(migrated["token"], legacy_token)
        payload = validate_token(
            migrated["token"],
            migrated_settings.signing_secret,
            "localstorage",
        )
        self.assertGreaterEqual(int(payload["expiresAt"]) - int(time.time()), 15551990)

    def test_admin_cleanup_requires_a_filter_and_never_returns_secrets(self) -> None:
        client = LocalAuthLabClient(self.settings)
        client.ensure_user("indexeddb", "cleanup_user", "password123")
        status, _, payload = self._json_request(
            "control",
            "POST",
            "/__automation__/cleanup",
            {},
            headers={"X-Auth-Lab-Admin-Key": self.settings.admin_key},
        )
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload["code"], "VALIDATION_ERROR")
        self.assertNotIn(self.settings.admin_key, json.dumps(payload))
        result = client.cleanup(site_id="indexeddb", username="cleanup_user")
        self.assertEqual(result["users"], 1)
        self.assertNotIn(self.settings.signing_secret, repr(self.settings))
        self.assertNotIn(self.settings.admin_key, repr(self.settings))
        self.assertEqual(self.settings.origin_mode, "localhost")
        self.assertTrue(all(domain.endswith(".localhost") for domain in self.settings.domains.values()))
        issued = issue_token("do-not-log-token-secret", "cookie", "user", 60)
        self.assertNotIn(issued.token, repr(issued))

    def _json_request(
        self,
        site_id: str,
        method: str,
        path: str,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], dict]:
        status, response_headers, body = self._request(site_id, method, path, payload, headers)
        return status, response_headers, json.loads(body.decode("utf-8"))

    def _request(
        self,
        site_id: str,
        method: str,
        path: str,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        request_headers = {"Host": DEFAULT_DOMAINS[site_id], **(headers or {})}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, headers=request_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            result = (exc.code, dict(exc.headers), body)
            exc.close()
            return result


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _shared_login_config() -> dict:
    return {
        "test_data": {
            "local_auth_lab_login": {
                "cookie": {
                    "username": "MCDL004",
                    "password": "M12345678",
                },
                "localstorage": {
                    "username": "MCDL005",
                    "password": "M12345678",
                },
                "indexeddb": {
                    "username": "MCDL006",
                    "password": "M12345678",
                },
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
