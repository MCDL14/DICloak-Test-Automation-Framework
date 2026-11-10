from __future__ import annotations

import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import websocket

from core.kernel_cdp_session import KernelCDPSessionError, close_kernel_browser


class TestKernelBrowserClose(unittest.TestCase):
    PORT = 43127
    APP_PORT = 9222

    def setUp(self) -> None:
        self.opener_patch = patch("core.kernel_cdp_session.urllib.request.build_opener")
        self.build_opener = self.opener_patch.start()
        self.addCleanup(self.opener_patch.stop)
        self.websocket_patch = patch("websocket.create_connection")
        self.connect = self.websocket_patch.start()
        self.addCleanup(self.websocket_patch.stop)
        self.ws = self.connect.return_value
        self.version_url = f"ws://127.0.0.1:{self.PORT}/devtools/browser/kernel-identity"
        self.version_payload({"webSocketDebuggerUrl": self.version_url})
        self.ws.recv.return_value = json.dumps({"id": 1, "result": {}})

    def version_payload(self, payload) -> None:
        self.build_opener.return_value.open.return_value = io.BytesIO(json.dumps(payload).encode())

    def close_browser(self, **kwargs) -> None:
        close_kernel_browser(self.PORT, app_cdp_port=self.APP_PORT, **kwargs)

    def test_uses_browser_target_and_ignores_unrelated_events(self) -> None:
        self.ws.recv.side_effect = [
            json.dumps({"method": "Target.targetDestroyed", "params": {}}),
            json.dumps({"id": 99, "result": {}}),
            json.dumps({"id": 1, "result": {}}),
        ]

        self.close_browser(timeout_seconds=3)

        self.assertEqual(
            self.build_opener.return_value.open.call_args.args[0],
            f"http://127.0.0.1:{self.PORT}/json/version",
        )
        self.assertEqual(self.connect.call_args.args[0], self.version_url)
        self.assertTrue(self.connect.call_args.kwargs["suppress_origin"])
        self.assertEqual(json.loads(self.ws.send.call_args.args[0]), {"id": 1, "method": "Browser.close"})
        self.ws.close.assert_called_once()

    def test_refuses_app_port_before_any_connection(self) -> None:
        with self.assertRaisesRegex(KernelCDPSessionError, "与 APP 相同"):
            close_kernel_browser(self.APP_PORT, app_cdp_port=self.APP_PORT)

        self.build_opener.assert_not_called()
        self.connect.assert_not_called()

    def test_rejects_invalid_ports_and_timeout(self) -> None:
        for port in (0, -1, 65536, True, "43127"):
            with self.subTest(port=port), self.assertRaises(ValueError):
                close_kernel_browser(port, app_cdp_port=self.APP_PORT)
        for timeout in (0, -1, True, float("nan"), float("inf"), "3"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.close_browser(timeout_seconds=timeout)

        self.connect.assert_not_called()

    def test_version_cannot_redirect_websocket_to_another_target(self) -> None:
        unsafe_urls = (
            f"ws://example.invalid:{self.PORT}/devtools/browser/kernel",
            f"ws://127.0.0.1:{self.APP_PORT}/devtools/browser/app",
            f"ws://127.0.0.1:{self.PORT}/devtools/page/tab",
            f"ws://user:password@127.0.0.1:{self.PORT}/devtools/browser/kernel",
            f"ws://127.0.0.1:{self.PORT}/devtools/browser/kernel?token=secret",
            f"ws://127.0.0.1:{self.PORT}/devtools/browser/kernel#fragment",
            f"http://127.0.0.1:{self.PORT}/devtools/browser/kernel",
            f"ws://127.0.0.1:{self.PORT}/devtools/browser/../page/tab",
        )
        for url in unsafe_urls:
            with self.subTest(url=url):
                self.version_payload({"webSocketDebuggerUrl": url})
                with self.assertRaises(KernelCDPSessionError):
                    self.close_browser()

        self.connect.assert_not_called()

    def test_localhost_browser_target_is_supported(self) -> None:
        self.version_payload({"webSocketDebuggerUrl": f"ws://localhost:{self.PORT}/devtools/browser/kernel"})

        self.close_browser()

        self.ws.close.assert_called_once()

    def test_disconnect_after_successful_send_is_expected(self) -> None:
        for outcome in ("", b"", websocket.WebSocketConnectionClosedException(), ConnectionResetError(), EOFError()):
            with self.subTest(outcome=type(outcome).__name__):
                self.ws.reset_mock()
                self.version_payload({"webSocketDebuggerUrl": self.version_url})
                self.ws.recv.side_effect = outcome if isinstance(outcome, Exception) else None
                self.ws.recv.return_value = outcome

                self.close_browser()

                self.ws.send.assert_called_once()
                self.ws.close.assert_called_once()

    def test_send_failure_is_not_treated_as_a_successful_shutdown(self) -> None:
        self.ws.send.side_effect = websocket.WebSocketConnectionClosedException()

        with self.assertRaisesRegex(KernelCDPSessionError, "发送 Browser.close 失败"):
            self.close_browser()

        self.ws.recv.assert_not_called()
        self.ws.close.assert_called_once()

    def test_receive_timeout_is_not_treated_as_a_successful_shutdown(self) -> None:
        self.ws.recv.side_effect = websocket.WebSocketTimeoutException()

        with self.assertRaisesRegex(KernelCDPSessionError, "响应失败"):
            self.close_browser()

        self.ws.close.assert_called_once()

    def test_total_deadline_can_expire_after_sending_the_command(self) -> None:
        with patch("core.kernel_cdp_session.time.monotonic", side_effect=[0, 0.1, 4.1]):
            with self.assertRaisesRegex(KernelCDPSessionError, "响应超时"):
                self.close_browser(timeout_seconds=3)

        self.ws.send.assert_called_once()
        self.ws.recv.assert_not_called()
        self.ws.close.assert_called_once()

    def test_malformed_or_rejected_response_is_reported(self) -> None:
        responses = (
            "invalid json",
            "[]",
            json.dumps({"id": 1, "error": {"code": -32601, "message": "unsupported"}}),
            json.dumps({"id": 1}),
        )
        for response in responses:
            with self.subTest(response=response):
                self.ws.reset_mock()
                self.version_payload({"webSocketDebuggerUrl": self.version_url})
                self.ws.recv.return_value = response
                with self.assertRaises(KernelCDPSessionError):
                    self.close_browser()
                self.ws.close.assert_called_once()

    def test_releases_socket_even_if_socket_close_itself_fails(self) -> None:
        self.ws.close.side_effect = OSError("closed already")

        self.close_browser()

        self.ws.close.assert_called_once()


class TestKernelBrowserCloseRedirects(unittest.TestCase):
    def test_version_http_redirect_is_not_followed(self) -> None:
        requested_paths = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requested_paths.append(self.path)
                if self.path == "/json/version":
                    self.send_response(302)
                    self.send_header("Location", "/unexpected-target")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"{}")

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            app_port = 9222 if port != 9222 else 9223
            with patch("websocket.create_connection") as connect:
                with self.assertRaises(KernelCDPSessionError):
                    close_kernel_browser(port, app_cdp_port=app_port)
                connect.assert_not_called()
            self.assertEqual(requested_paths, ["/json/version"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
