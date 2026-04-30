from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from core.config import timeout_ms


class CDPConnectionError(RuntimeError):
    pass


@dataclass
class CDPTarget:
    id: str
    title: str
    url: str
    websocket_url: str = ""


class CDPDriver:
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.playwright = None
        self.browser = None
        self.page = None
        self.websocket = None

    @property
    def endpoint(self) -> str:
        cdp = self.config["cdp"]
        return f"http://{cdp.get('host', '127.0.0.1')}:{cdp.get('port', 9222)}"

    def list_targets(self) -> list[CDPTarget]:
        url = f"{self.endpoint}/json"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise CDPConnectionError(f"cannot read CDP targets from {url}: {exc}") from exc

        targets: list[CDPTarget] = []
        for item in payload:
            targets.append(
                CDPTarget(
                    id=str(item.get("id", "")),
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    websocket_url=str(item.get("webSocketDebuggerUrl", "")),
                )
            )
        return targets

    def connect(self) -> None:
        driver = str(self.config["cdp"].get("driver", "playwright")).lower()
        fallback = str(self.config["cdp"].get("fallback_driver", "websocket")).lower()
        try:
            if driver == "playwright":
                self.connect_playwright()
            elif driver == "websocket":
                self.connect_websocket()
            else:
                raise CDPConnectionError(f"unsupported CDP driver: {driver}")
        except Exception as exc:
            self.logger.error("Primary CDP driver failed: %s", exc)
            if fallback and fallback != driver:
                self.logger.info("Trying fallback CDP driver: %s", fallback)
                if fallback == "websocket":
                    self.connect_websocket()
                    return
                if fallback == "playwright":
                    self.connect_playwright()
                    return
            raise

    def connect_playwright(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise CDPConnectionError("playwright is not installed") from exc

        connect_timeout = int(self.config["cdp"].get("connect_timeout", 30))
        deadline = time.time() + connect_timeout
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                self.playwright = sync_playwright().start()
                self.browser = self.playwright.chromium.connect_over_cdp(self.endpoint)
                context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
                self.page = self._select_default_page(context.pages) if context.pages else context.new_page()
                self.logger.info("Connected to APP through Playwright CDP: %s", self.endpoint)
                return
            except Exception as exc:
                last_error = exc
                self.close()
                time.sleep(1)
        raise CDPConnectionError(f"Playwright CDP connect timeout: {last_error}")

    def connect_websocket(self) -> None:
        try:
            import websocket
        except ImportError as exc:
            raise CDPConnectionError("websocket-client is not installed") from exc

        targets = self.list_targets()
        target = next((item for item in targets if item.websocket_url), None)
        if not target:
            raise CDPConnectionError("no websocket CDP target was found")
        self.websocket = websocket.create_connection(target.websocket_url, timeout=5)
        self.logger.info("Connected to APP through raw WebSocket CDP: %s", target.websocket_url)

    def select_page(
        self,
        url_keyword: str | None = None,
        title_keyword: str | None = None,
        required_selector: str | None = None,
    ):
        if not self.page:
            raise CDPConnectionError("Playwright page is not connected")
        pages = self.page.context.pages
        for page in pages:
            if url_keyword and url_keyword not in page.url:
                continue
            if title_keyword and title_keyword not in page.title():
                continue
            if required_selector and page.locator(required_selector).count() == 0:
                continue
            self.page = page
            return page
        raise CDPConnectionError("no matching page was found")

    def health_check(self) -> bool:
        if self.page:
            return not self.page.is_closed()
        if self.websocket:
            return self.websocket.connected
        return False

    def wait_for_selector(self, selector: str, timeout: int | None = None):
        timeout = timeout if timeout is not None else self._element_timeout_ms()
        return self._page().wait_for_selector(selector, state="visible", timeout=timeout)

    def click(self, selector: str, timeout: int | None = None) -> None:
        timeout = timeout if timeout is not None else self._element_timeout_ms()
        locator = self._page().locator(selector)
        locator.wait_for(state="visible", timeout=timeout)
        if not locator.is_enabled(timeout=timeout):
            raise TimeoutError(f"selector is not enabled before click: {selector}")
        locator.click(timeout=timeout)

    def click_at(self, x: float, y: float) -> None:
        self._page().mouse.click(x, y)

    def press(self, key: str) -> None:
        self._page().keyboard.press(key)

    def click_element_by_script(self, script: str, timeout: int | None = None) -> None:
        # 用 JS 返回具体 DOM 元素，再交给 Playwright 点击；用于表格行内按钮等动态定位场景。
        timeout = timeout if timeout is not None else self._script_element_timeout_ms()
        element = self._wait_for_element_by_script(script, timeout=timeout)
        element.click(timeout=timeout)

    def fill_element_by_script(self, script: str, text: str, timeout: int | None = None) -> None:
        # 用 JS 定位动态表单输入框，再交给 Playwright fill，保证 Vue/Element Plus 能收到真实输入事件。
        timeout = timeout if timeout is not None else self._script_element_timeout_ms()
        element = self._wait_for_element_by_script(script, timeout=timeout)
        element.fill(text, timeout=timeout)

    def hover_element_by_script(self, script: str, timeout: int | None = None) -> None:
        # 用真实 hover 触发 Element Plus 菜单；仅派发 JS mouseenter 时部分菜单不会展开。
        timeout = timeout if timeout is not None else self._script_element_timeout_ms()
        element = self._wait_for_element_by_script(script, timeout=timeout)
        element.hover(timeout=timeout)

    def click_element_by_script_and_wait_for_request(
        self,
        script: str,
        url_contains: str,
        method: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, str]:
        # 点击元素的同时监听请求，避免先点后监听导致错过 /open_env 这类瞬时请求。
        timeout = timeout if timeout is not None else self._request_timeout_ms()
        page = self._page()
        expected_method = method.upper() if method else None

        def matches(request) -> bool:
            if url_contains not in request.url:
                return False
            if expected_method and request.method.upper() != expected_method:
                return False
            return True

        element = self._wait_for_element_by_script(script, timeout=timeout)
        with page.expect_request(matches, timeout=timeout) as request_info:
            element.click(timeout=timeout)

        request = request_info.value
        return {
            "url": request.url,
            "method": request.method,
            "post_data": request.post_data or "",
        }

    def click_element_by_script_and_collect_requests(
        self,
        script: str,
        url_contains: str,
        method: str | None = None,
        expected_count: int = 1,
        timeout: int | None = None,
        raise_on_timeout: bool = True,
    ) -> list[dict[str, str]]:
        # 批量打开环境会串行发起多个 /open_env 请求；先注册监听再点击，持续收集到期望数量。
        timeout = timeout if timeout is not None else self._request_timeout_ms()
        page = self._page()
        context = page.context
        expected_method = method.upper() if method else None
        collected: list[dict[str, str]] = []
        seen_requests: set[tuple[str, str, str]] = set()
        cdp_sessions = []

        def append_request(url: str, request_method: str, post_data: str) -> None:
            key = (url, request_method.upper(), post_data)
            if key in seen_requests:
                return
            seen_requests.add(key)
            collected.append(
                {
                    "url": url,
                    "method": request_method,
                    "post_data": post_data,
                }
            )

        def handler(request) -> None:
            if url_contains not in request.url:
                return
            if expected_method and request.method.upper() != expected_method:
                return
            append_request(request.url, request.method, request.post_data or "")

        def cdp_handler(params: dict[str, Any]) -> None:
            request = params.get("request", {})
            request_url = str(request.get("url", ""))
            request_method = str(request.get("method", ""))
            if url_contains not in request_url:
                return
            if expected_method and request_method.upper() != expected_method:
                return
            append_request(request_url, request_method, str(request.get("postData", "") or ""))

        page.on("request", handler)
        context.on("request", handler)
        try:
            self._install_request_capture_hook()
            for candidate_page in context.pages:
                try:
                    session = context.new_cdp_session(candidate_page)
                    session.on("Network.requestWillBeSent", cdp_handler)
                    session.send("Network.enable")
                    cdp_sessions.append(session)
                except Exception as exc:
                    self.logger.debug(
                        "CDP Network listener was not enabled for page %s; continuing: %s",
                        getattr(candidate_page, "url", ""),
                        exc,
                    )

            element = self._wait_for_element_by_script(script, timeout=timeout)
            element.click(timeout=timeout)
            deadline = time.time() + timeout / 1000
            while time.time() < deadline:
                for request in self._captured_requests_from_page(url_contains, expected_method):
                    append_request(request["url"], request["method"], request["post_data"])
                if len(collected) >= expected_count:
                    return collected[:expected_count]
                time.sleep(0.2)
            if not raise_on_timeout:
                return collected
            raise TimeoutError(
                "request count did not reach expected count: "
                f"url_contains={url_contains}, expected={expected_count}, actual={len(collected)}"
            )
        finally:
            page.remove_listener("request", handler)
            context.remove_listener("request", handler)
            for session in cdp_sessions:
                try:
                    session.remove_listener("Network.requestWillBeSent", cdp_handler)
                    session.detach()
                except Exception:
                    pass

    def _install_request_capture_hook(self) -> None:
        self._page().evaluate(
            """
            () => {
                window.__dicloakCapturedRequests = [];
                if (window.__dicloakRequestCaptureInstalled) return;
                window.__dicloakRequestCaptureInstalled = true;

                const bodyToText = (body) => {
                    if (typeof body === "string") return body;
                    if (body == null) return "";
                    try {
                        if (body instanceof URLSearchParams) return body.toString();
                    } catch (_) {}
                    return "";
                };

                const record = (url, method, body) => {
                    try {
                        window.__dicloakCapturedRequests.push({
                            url: String(url || ""),
                            method: String(method || "GET"),
                            post_data: bodyToText(body),
                        });
                    } catch (_) {}
                };

                const originalFetch = window.fetch;
                if (typeof originalFetch === "function") {
                    window.fetch = function(input, init) {
                        try {
                            const url = typeof input === "string" ? input : input && input.url;
                            const method = (init && init.method) || (input && input.method) || "GET";
                            const body = init && Object.prototype.hasOwnProperty.call(init, "body") ? init.body : "";
                            record(url, method, body);
                        } catch (_) {}
                        return originalFetch.apply(this, arguments);
                    };
                }

                const originalOpen = XMLHttpRequest.prototype.open;
                const originalSend = XMLHttpRequest.prototype.send;
                XMLHttpRequest.prototype.open = function(method, url) {
                    this.__dicloakCaptureMethod = method;
                    this.__dicloakCaptureUrl = url;
                    return originalOpen.apply(this, arguments);
                };
                XMLHttpRequest.prototype.send = function(body) {
                    try {
                        record(this.__dicloakCaptureUrl, this.__dicloakCaptureMethod, body);
                    } catch (_) {}
                    return originalSend.apply(this, arguments);
                };
            }
            """
        )

    def _captured_requests_from_page(self, url_contains: str, expected_method: str | None) -> list[dict[str, str]]:
        value = self._page().evaluate(
            """
            ([urlContains, expectedMethod]) => {
                const requests = Array.isArray(window.__dicloakCapturedRequests)
                    ? window.__dicloakCapturedRequests
                    : [];
                return requests
                    .filter((request) => String(request.url || "").includes(urlContains))
                    .filter((request) => !expectedMethod || String(request.method || "").toUpperCase() === expectedMethod)
                    .map((request) => ({
                        url: String(request.url || ""),
                        method: String(request.method || ""),
                        post_data: String(request.post_data || ""),
                    }));
            }
            """,
            [url_contains, expected_method],
        )
        return value if isinstance(value, list) else []

    def click_element_by_script_and_wait_for_response(
        self,
        script: str,
        url_contains: str,
        method: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, str | int]:
        timeout = timeout if timeout is not None else self._request_timeout_ms()
        page = self._page()
        expected_method = method.upper() if method else None

        def matches(response) -> bool:
            request = response.request
            if url_contains not in request.url:
                return False
            if expected_method and request.method.upper() != expected_method:
                return False
            return True

        element = self._wait_for_element_by_script(script, timeout=timeout)
        with page.expect_response(matches, timeout=timeout) as response_info:
            element.click(timeout=timeout)

        response = response_info.value
        request = response.request
        try:
            body = response.text()
        except Exception:
            body = ""
        return {
            "url": request.url,
            "method": request.method,
            "post_data": request.post_data or "",
            "status": response.status,
            "response_body": body,
        }

    def click_at_and_wait_for_request(
        self,
        x: float,
        y: float,
        url_contains: str,
        method: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, str]:
        timeout = timeout if timeout is not None else self._request_timeout_ms()
        page = self._page()
        expected_method = method.upper() if method else None

        def matches(request) -> bool:
            if url_contains not in request.url:
                return False
            if expected_method and request.method.upper() != expected_method:
                return False
            return True

        with page.expect_request(matches, timeout=timeout) as request_info:
            self.click_at(x, y)

        request = request_info.value
        return {
            "url": request.url,
            "method": request.method,
            "post_data": request.post_data or "",
        }

    def fill(self, selector: str, text: str, timeout: int | None = None) -> None:
        timeout = timeout if timeout is not None else self._element_timeout_ms()
        locator = self._page().locator(selector)
        locator.wait_for(state="visible", timeout=timeout)
        if not locator.is_enabled(timeout=timeout):
            raise TimeoutError(f"selector is not enabled before fill: {selector}")
        locator.fill(text, timeout=timeout)

    def text(self, selector: str, timeout: int | None = None) -> str:
        timeout = timeout if timeout is not None else self._element_timeout_ms()
        locator = self._page().locator(selector)
        locator.wait_for(state="visible", timeout=timeout)
        return locator.inner_text(timeout=timeout)

    def evaluate(self, expression: str):
        return self._page().evaluate(expression)

    def reload(self, timeout: int | None = None) -> None:
        # 刷新 Electron 主页面，用于模拟用户在 APP 内刷新当前页面。
        timeout = timeout if timeout is not None else self._element_timeout_ms()
        page = self._page()
        page.reload(wait_until="domcontentloaded", timeout=timeout)
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            self.logger.debug("networkidle was not reached after reload; continuing after domcontentloaded")

    def wait_for_text(self, selector: str, expected_text: str, timeout: int | None = None) -> None:
        timeout = timeout if timeout is not None else self._element_timeout_ms()
        locator = self._page().locator(selector)
        deadline = time.time() + timeout / 1000
        while time.time() < deadline:
            if expected_text in locator.inner_text(timeout=1000):
                return
            time.sleep(0.5)
        raise TimeoutError(f"text did not appear in selector {selector}: {expected_text}")

    def wait_until_clickable(self, selector: str, timeout: int | None = None) -> None:
        timeout = timeout if timeout is not None else self._element_timeout_ms()
        locator = self._page().locator(selector)
        locator.wait_for(state="visible", timeout=timeout)
        if not locator.is_enabled(timeout=timeout):
            raise TimeoutError(f"selector is not clickable: {selector}")

    def screenshot(self, path: str) -> None:
        self._page().screenshot(path=path, full_page=True)

    def close(self) -> None:
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
        if self.websocket:
            try:
                self.websocket.close()
            except Exception:
                pass
        self.playwright = None
        self.browser = None
        self.page = None
        self.websocket = None

    def _page(self):
        if not self.page:
            raise CDPConnectionError("Playwright page is not connected")
        return self.page

    def _wait_for_element_by_script(self, script: str, timeout: int | None = None):
        timeout = timeout if timeout is not None else self._script_element_timeout_ms()
        deadline = time.time() + timeout / 1000
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                handle = self._page().evaluate_handle(script)
                element = handle.as_element()
                if element:
                    element.scroll_into_view_if_needed(timeout=timeout)
                    element.wait_for_element_state("visible", timeout=timeout)
                    element.wait_for_element_state("enabled", timeout=timeout)
                    return element
            except Exception as exc:
                last_error = exc
            time.sleep(0.2)
        if last_error:
            raise TimeoutError(f"script did not return a visible enabled element before timeout: {last_error}")
        raise TimeoutError("script did not return a visible enabled element before timeout")

    def _element_timeout_ms(self) -> int:
        return timeout_ms(self.config, "element_seconds", 10)

    def _script_element_timeout_ms(self) -> int:
        return timeout_ms(self.config, "script_element_seconds", 10)

    def _request_timeout_ms(self) -> int:
        return timeout_ms(self.config, "request_seconds", 30)

    def _select_default_page(self, pages: list):
        # APP 打开控制台后 pages[0] 可能是 devtools://，默认必须跳过 DevTools 选择 Dicloak 主页面。
        for page in pages:
            if page.url.startswith("devtools://"):
                continue
            if "/resources/app.asar.unpacked/dist/index.html" in page.url:
                return page
        for page in pages:
            if page.url.startswith("devtools://"):
                continue
            return page
        return pages[0]
