from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class KernelCDPSessionError(RuntimeError):
    pass


class KernelCDPSession:
    """A self-contained CDP page session for GinsBrowser test pages.

    This deliberately does not alter the validated function-style helpers in
    ``core.kernel_cdp``. One instance owns one temporary target and closes only
    that target.
    """

    def __init__(self, port: int, host: str = "127.0.0.1", timeout_seconds: float = 20):
        if port <= 0:
            raise ValueError("kernel CDP port must be positive")
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.target_id = ""
        self.websocket_url = ""
        self._ws = None
        self._command_id = 0

    def connect(self, initial_url: str = "about:blank") -> "KernelCDPSession":
        if self._ws is not None:
            return self
        target = self._create_target(initial_url)
        self.target_id = str(target.get("id", ""))
        self.websocket_url = str(target.get("webSocketDebuggerUrl", ""))
        if not self.target_id or not self.websocket_url:
            raise KernelCDPSessionError(f"kernel CDP returned an invalid target: {target}")
        try:
            import websocket
        except ImportError as exc:
            self._close_target()
            raise KernelCDPSessionError("websocket-client is required for kernel CDP") from exc
        try:
            self._ws = websocket.create_connection(
                self.websocket_url,
                timeout=min(self.timeout_seconds, 5),
                suppress_origin=True,
            )
            self.command("Page.enable")
            self.command("Runtime.enable")
            self.command("Network.enable")
        except Exception:
            self.close()
            raise
        return self

    def __enter__(self) -> "KernelCDPSession":
        return self.connect()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        self._close_target()

    def command(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if self._ws is None:
            raise KernelCDPSessionError("kernel CDP session is not connected")
        self._command_id += 1
        command_id = self._command_id
        deadline = time.time() + (timeout_seconds or self.timeout_seconds)
        self._ws.send(json.dumps({"id": command_id, "method": method, "params": params or {}}))
        while time.time() < deadline:
            try:
                message = json.loads(self._ws.recv())
            except Exception as exc:
                raise KernelCDPSessionError(f"kernel CDP receive failed for {method}: {exc}") from exc
            if message.get("id") != command_id:
                continue
            if "error" in message:
                raise KernelCDPSessionError(f"kernel CDP command failed: {method}: {message['error']}")
            return message.get("result", {})
        raise KernelCDPSessionError(f"kernel CDP command timed out: {method}")

    def navigate(self, url: str, timeout_seconds: float | None = None) -> None:
        timeout = timeout_seconds or self.timeout_seconds
        result = self.command("Page.navigate", {"url": url}, timeout)
        if result.get("errorText"):
            raise KernelCDPSessionError(f"navigation failed: {url}: {result['errorText']}")
        self.wait_until(
            "document.readyState === 'complete' || document.readyState === 'interactive'",
            timeout_seconds=timeout,
            message=f"document did not become ready: {url}",
        )

    def evaluate(self, expression: str, timeout_seconds: float | None = None) -> Any:
        result = self.command(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout_seconds,
        )
        if result.get("exceptionDetails"):
            description = result.get("result", {}).get("description", "JavaScript evaluation failed")
            raise KernelCDPSessionError(str(description))
        return result.get("result", {}).get("value")

    def wait_until(
        self,
        expression: str,
        timeout_seconds: float | None = None,
        message: str = "condition was not satisfied",
    ) -> Any:
        deadline = time.time() + (timeout_seconds or self.timeout_seconds)
        last_value: Any = None
        while time.time() < deadline:
            last_value = self.evaluate(expression, timeout_seconds=max(0.2, deadline - time.time()))
            if last_value:
                return last_value
            time.sleep(0.1)
        raise KernelCDPSessionError(f"{message}; last_value={last_value!r}")

    def wait_for_selector(self, selector: str, timeout_seconds: float | None = None) -> None:
        encoded = json.dumps(selector)
        self.wait_until(
            """
            (() => {
              const element = document.querySelector(%s);
              if (!element || element.hidden) return false;
              const style = getComputedStyle(element);
              return style.display !== 'none' && style.visibility !== 'hidden';
            })()
            """ % encoded,
            timeout_seconds,
            f"selector not visible: {selector}",
        )

    def fill(self, selector: str, value: str) -> None:
        result = self.evaluate(
            """
            (() => {
              const element = document.querySelector(%s);
              if (!element) return {ok: false, reason: 'NOT_FOUND'};
              const setter = Object.getOwnPropertyDescriptor(
                element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
                'value'
              ).set;
              setter.call(element, %s);
              element.dispatchEvent(new Event('input', {bubbles: true}));
              element.dispatchEvent(new Event('change', {bubbles: true}));
              return {ok: true};
            })()
            """ % (json.dumps(selector), json.dumps(value))
        )
        if not isinstance(result, dict) or not result.get("ok"):
            raise KernelCDPSessionError(f"cannot fill selector {selector}: {result}")

    def click(self, selector: str) -> None:
        result = self.evaluate(
            """
            (() => {
              const element = document.querySelector(%s);
              if (!element) return {ok: false, reason: 'NOT_FOUND'};
              element.click();
              return {ok: true};
            })()
            """ % json.dumps(selector)
        )
        if not isinstance(result, dict) or not result.get("ok"):
            raise KernelCDPSessionError(f"cannot click selector {selector}: {result}")

    def text(self, selector: str) -> str:
        value = self.evaluate(
            """
            (() => {
              const element = document.querySelector(%s);
              return element ? (element.textContent || '').trim() : null;
            })()
            """ % json.dumps(selector)
        )
        if value is None:
            raise KernelCDPSessionError(f"cannot read selector: {selector}")
        return str(value)

    def screenshot(self, path: Path | str) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = self.command("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        data = str(result.get("data", ""))
        if not data:
            raise KernelCDPSessionError("Page.captureScreenshot returned no image")
        destination.write_bytes(base64.b64decode(data))
        return destination

    @property
    def current_url(self) -> str:
        return str(self.evaluate("location.href") or "")

    def _endpoint(self, path: str) -> str:
        return f"http://{self.host}:{self.port}{path}"

    def _create_target(self, url: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(url, safe="")
        request = urllib.request.Request(self._endpoint(f"/json/new?{encoded}"), method="PUT")
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout_seconds, 5)) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise KernelCDPSessionError(f"cannot create kernel CDP target: {exc}") from exc
        if not isinstance(payload, dict):
            raise KernelCDPSessionError(f"unexpected kernel CDP target payload: {payload}")
        return payload

    def _close_target(self) -> None:
        target_id = self.target_id
        self.target_id = ""
        self.websocket_url = ""
        if not target_id:
            return
        try:
            with urllib.request.urlopen(
                self._endpoint(f"/json/close/{urllib.parse.quote(target_id, safe='')}"),
                timeout=min(self.timeout_seconds, 3),
            ):
                pass
        except Exception:
            pass
