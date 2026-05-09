from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class KernelPageResult:
    requested_url: str
    target_id: str
    target_url: str
    title: str
    text: str
    error_text: str = ""


@dataclass
class PasswordEyeResult:
    requested_url: str
    target_id: str
    target_url: str
    title: str
    password_value: str
    password_input_type: str
    password_text_security: str
    password_visible: bool
    eye_click_target: str = ""
    evidence: str = ""


def open_kernel_url_and_read_page(
    port: int,
    url: str,
    timeout_seconds: int = 20,
    http_timeout_seconds: int = 2,
) -> KernelPageResult:
    if port <= 0:
        raise ValueError(f"kernel CDP port must be positive: {port}")

    target = _create_target(port, "about:blank", timeout_seconds=http_timeout_seconds)
    target_id = str(target.get("id", ""))
    websocket_url = str(target.get("webSocketDebuggerUrl", ""))
    if not target_id or not websocket_url:
        raise RuntimeError(f"kernel CDP target was not created correctly: {target}")

    try:
        import websocket
    except ImportError as exc:
        _close_target(port, target_id, timeout_seconds=http_timeout_seconds)
        raise RuntimeError("websocket-client is required to operate kernel CDP pages") from exc

    ws = websocket.create_connection(websocket_url, timeout=http_timeout_seconds, suppress_origin=True)
    try:
        deadline = time.time() + timeout_seconds
        _send_and_wait(ws, "Page.enable", {}, deadline)
        _send_and_wait(ws, "Runtime.enable", {}, deadline)
        navigate_response = _send_and_wait(ws, "Page.navigate", {"url": url}, deadline)
        error_text = str(navigate_response.get("result", {}).get("errorText", "") or "")

        text = ""
        title = ""
        target_url = ""
        while time.time() < deadline:
            evaluated = _evaluate_page_snapshot(ws, deadline)
            title = str(evaluated.get("title", ""))
            target_url = str(evaluated.get("url", ""))
            text = str(evaluated.get("text", ""))
            if "ERR_BLOCKED_BY_CLIENT" in "\n".join([error_text, title, target_url, text]):
                break
            if _document_ready(ws, deadline) and text:
                break
            time.sleep(0.3)

        return KernelPageResult(
            requested_url=url,
            target_id=target_id,
            target_url=target_url,
            title=title,
            text=text,
            error_text=error_text,
        )
    finally:
        try:
            ws.close()
        finally:
            _close_target(port, target_id, timeout_seconds=http_timeout_seconds)


def verify_bilibili_password_eye_blocked(
    port: int,
    password: str = "12345678",
    url: str = "https://www.bilibili.com",
    timeout_seconds: int = 45,
    http_timeout_seconds: int = 2,
) -> PasswordEyeResult:
    if port <= 0:
        raise ValueError(f"kernel CDP port must be positive: {port}")

    target = _create_target(port, "about:blank", timeout_seconds=http_timeout_seconds)
    target_id = str(target.get("id", ""))
    websocket_url = str(target.get("webSocketDebuggerUrl", ""))
    if not target_id or not websocket_url:
        raise RuntimeError(f"kernel CDP target was not created correctly: {target}")

    try:
        import websocket
    except ImportError as exc:
        _close_target(port, target_id, timeout_seconds=http_timeout_seconds)
        raise RuntimeError("websocket-client is required to operate kernel CDP pages") from exc

    ws = websocket.create_connection(websocket_url, timeout=http_timeout_seconds, suppress_origin=True)
    try:
        deadline = time.time() + timeout_seconds
        _send_and_wait(ws, "Page.enable", {}, deadline)
        _send_and_wait(ws, "Runtime.enable", {}, deadline)
        _send_and_wait(ws, "Page.bringToFront", {}, deadline)
        _send_and_wait(ws, "Page.navigate", {"url": url}, deadline)
        _wait_document_interactive(ws, deadline)
        _wait_bilibili_body_ready(ws, deadline)
        _click_bilibili_login_entry(ws, deadline)
        _open_bilibili_password_login_if_needed(ws, deadline)
        _fill_bilibili_password(ws, password, deadline)
        before = _bilibili_password_input_state(ws, password, deadline)
        eye_target = _click_bilibili_password_eye(ws, password, deadline)
        time.sleep(1.2)
        after = _bilibili_password_input_state(ws, password, deadline)
        snapshot = _evaluate_page_snapshot(ws, deadline)

        input_type = str(after.get("type", "")).lower()
        text_security = str(after.get("textSecurity", "")).lower()
        password_visible = input_type == "text" and text_security in {"", "none"}
        return PasswordEyeResult(
            requested_url=url,
            target_id=target_id,
            target_url=str(snapshot.get("url", "")),
            title=str(snapshot.get("title", "")),
            password_value=str(after.get("value", "")),
            password_input_type=input_type,
            password_text_security=text_security,
            password_visible=password_visible,
            eye_click_target=str(eye_target),
            evidence=f"eye_target={eye_target}, before={before}, after={after}",
        )
    finally:
        try:
            ws.close()
        finally:
            _close_target(port, target_id, timeout_seconds=http_timeout_seconds)


def _create_target(port: int, url: str, timeout_seconds: int) -> dict[str, Any]:
    quoted_url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")
    endpoint = f"http://127.0.0.1:{port}/json/new?{quoted_url}"
    request = urllib.request.Request(endpoint, method="PUT")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError:
        with urllib.request.urlopen(endpoint, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected kernel CDP new target payload: {payload}")
    return payload


def _close_target(port: int, target_id: str, timeout_seconds: int) -> bool:
    if not target_id:
        return False
    quoted_id = urllib.parse.quote(target_id, safe="")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{quoted_id}", timeout=timeout_seconds):
            return True
    except (OSError, urllib.error.URLError):
        return False


def _send_and_wait(ws, method: str, params: dict[str, Any], deadline: float) -> dict[str, Any]:
    command_id = _next_command_id(ws)
    ws.send(json.dumps({"id": command_id, "method": method, "params": params}))
    return _wait_for_response(ws, command_id, deadline)


def _next_command_id(ws) -> int:
    current = int(getattr(ws, "_dicloak_command_id", 0)) + 1
    setattr(ws, "_dicloak_command_id", current)
    return current


def _wait_for_response(ws, command_id: int, deadline: float) -> dict[str, Any]:
    last_payload: dict[str, Any] = {}
    while time.time() < deadline:
        remaining = max(0.1, min(1.0, deadline - time.time()))
        ws.settimeout(remaining)
        try:
            payload = json.loads(ws.recv())
        except TimeoutError:
            continue
        except Exception:
            continue
        if isinstance(payload, dict):
            last_payload = payload
            if payload.get("id") == command_id:
                if "error" in payload:
                    raise RuntimeError(f"kernel CDP command failed: {payload['error']}")
                return payload
    raise TimeoutError(f"kernel CDP command response timeout: command_id={command_id}, last={last_payload}")


def _evaluate_page_snapshot(ws, deadline: float) -> dict[str, str]:
    expression = """
    (() => {
        const textParts = [];
        const push = (value) => {
            const text = String(value || "").trim();
            if (text) textParts.push(text);
        };
        push(document.title);
        push(document.body ? document.body.innerText : "");
        push(document.documentElement ? document.documentElement.innerText : "");
        push(document.documentElement ? document.documentElement.outerHTML : "");
        return {
            title: String(document.title || ""),
            url: String(location.href || ""),
            text: textParts.join("\\n")
        };
    })()
    """
    response = _send_and_wait(
        ws,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
        deadline,
    )
    value = response.get("result", {}).get("result", {}).get("value", {})
    return value if isinstance(value, dict) else {}


def _wait_document_interactive(ws, deadline: float) -> None:
    while time.time() < deadline:
        if _document_ready(ws, deadline):
            return
        time.sleep(0.3)
    raise TimeoutError("kernel page document did not become interactive")


def _document_ready(ws, deadline: float) -> bool:
    response = _send_and_wait(
        ws,
        "Runtime.evaluate",
        {
            "expression": "document.readyState === 'complete' || document.readyState === 'interactive'",
            "returnByValue": True,
        },
        deadline,
    )
    return bool(response.get("result", {}).get("result", {}).get("value"))


def _wait_bilibili_body_ready(ws, deadline: float) -> None:
    while time.time() < deadline:
        ready = _evaluate_value(
            ws,
            """
            (() => {
                const text = document.body ? (document.body.innerText || "") : "";
                return location.href.includes("bilibili.com") && text.length > 20;
            })()
            """,
            deadline,
        )
        if ready:
            return
        time.sleep(0.5)
    raise TimeoutError("bilibili page did not become ready")


def _click_bilibili_login_entry(ws, deadline: float) -> None:
    while time.time() < deadline:
        clicked = _evaluate_value(
            ws,
            """
            (() => {
                const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                };
                const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const candidates = Array.from(document.querySelectorAll("button,a,span,div"))
                    .filter(visible)
                    .map((el) => ({ el, text: clean(el.innerText || el.textContent), rect: el.getBoundingClientRect() }))
                    .filter((item) => item.text === "登录" || item.text === "立即登录")
                    .filter((item) => item.rect.y < 220)
                    .sort((left, right) => (left.rect.y - right.rect.y) || (right.rect.x - left.rect.x));
                const target = candidates[0]?.el || null;
                if (!target) return false;
                target.click();
                return true;
            })()
            """,
            deadline,
        )
        if clicked:
            return
        time.sleep(0.5)
    raise TimeoutError("bilibili login entry was not found")


def _open_bilibili_password_login_if_needed(ws, deadline: float) -> None:
    while time.time() < deadline:
        has_password_input = _evaluate_value(
            ws,
            """
            (() => Array.from(document.querySelectorAll("input"))
                .some((input) => {
                    const rect = input.getBoundingClientRect();
                    const placeholder = String(input.getAttribute("placeholder") || "");
                    return rect.width > 0
                        && rect.height > 0
                        && (input.type === "password" || placeholder.includes("密码"));
                }))()
            """,
            deadline,
        )
        if has_password_input:
            return

        _evaluate_value(
            ws,
            """
            (() => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                };
                const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const target = Array.from(document.querySelectorAll("button,a,span,div"))
                    .filter(visible)
                    .find((el) => ["密码登录", "账号登录", "其他方式登录"].includes(clean(el.innerText || el.textContent)));
                if (!target) return false;
                target.click();
                return true;
            })()
            """,
            deadline,
        )
        time.sleep(0.5)
    raise TimeoutError("bilibili password login form was not found")


def _fill_bilibili_password(ws, password: str, deadline: float) -> None:
    quoted_password = json.dumps(password)
    while time.time() < deadline:
        filled = _evaluate_value(
            ws,
            f"""
            (() => {{
                const password = {quoted_password};
                const visible = (el) => {{
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                }};
                const inputs = Array.from(document.querySelectorAll("input"))
                    .filter(visible)
                    .filter((input) => input.type === "password" || String(input.placeholder || "").includes("密码"));
                const input = inputs[inputs.length - 1] || null;
                if (!input) return false;
                input.focus();
                input.value = password;
                input.dispatchEvent(new Event("input", {{ bubbles: true }}));
                input.dispatchEvent(new Event("change", {{ bubbles: true }}));
                return input.value === password;
            }})()
            """,
            deadline,
        )
        if filled:
            return
        time.sleep(0.5)
    raise TimeoutError("bilibili password input was not filled")


def _click_bilibili_password_eye(ws, password: str, deadline: float) -> dict[str, Any]:
    quoted_password = json.dumps(password)
    while time.time() < deadline:
        target = _evaluate_value(
            ws,
            """
            (() => {
                const expectedPassword = __PASSWORD__;
                const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                };
                const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const passwordInput = Array.from(document.querySelectorAll("input"))
                    .filter(visible)
                    .find((input) => input.value === expectedPassword || input.type === "password" || String(input.placeholder || "").includes("密码"));
                const passwordRect = passwordInput ? passwordInput.getBoundingClientRect() : null;
                if (!passwordRect) return null;
                const forget = Array.from(document.querySelectorAll("button,a,span,div"))
                    .filter(visible)
                    .map((el) => ({ el, text: clean(el.innerText || el.textContent), rect: el.getBoundingClientRect() }))
                    .filter((item) => item.text === "忘记密码" || item.text.includes("忘记密码"))
                    .sort((left, right) => left.rect.y - right.rect.y)[0];

                const describe = (item, reason) => ({
                    reason,
                    text: clean(item.el.innerText || item.el.textContent),
                    className: String(item.el.className || ""),
                    tagName: String(item.el.tagName || ""),
                    x: item.rect.x + item.rect.width / 2,
                    y: item.rect.y + item.rect.height / 2,
                    rect: {
                        x: item.rect.x,
                        y: item.rect.y,
                        width: item.rect.width,
                        height: item.rect.height,
                    },
                });

                const nearPasswordRow = (item) => {
                    const centerY = item.rect.y + item.rect.height / 2;
                    return Math.abs(centerY - (passwordRect.y + passwordRect.height / 2)) < 35
                        && item.rect.x >= passwordRect.x
                        && item.rect.x <= passwordRect.x + passwordRect.width + 80;
                };

                const classCandidates = Array.from(document.querySelectorAll("button,a,span,div,i,svg,use"))
                    .filter(visible)
                    .map((el) => ({ el, text: clean(el.innerText || el.textContent), rect: el.getBoundingClientRect(), cls: String(el.className || "") }))
                    .filter((item) => {
                        const classText = item.cls.toLowerCase();
                        return classText.includes("eye")
                            || classText.includes("password")
                            || classText.includes("pwd")
                            || classText.includes("visible")
                            || classText.includes("visibility");
                    })
                    .filter((item) => nearPasswordRow(item))
                    .filter((item) => item.el !== passwordInput);
                if (classCandidates.length) {
                    classCandidates.sort((left, right) => right.rect.x - left.rect.x);
                    return describe(classCandidates[0], "class-near-password-row");
                }
                if (forget && passwordRect) {
                    const forgetCenterY = forget.rect.y + forget.rect.height / 2;
                    const candidates = Array.from(document.querySelectorAll("button,a,span,div,i,svg"))
                        .filter(visible)
                        .map((el) => ({ el, rect: el.getBoundingClientRect(), text: clean(el.innerText || el.textContent) }))
                        .filter((item) => !item.text || item.text.length <= 4)
                        .filter((item) => item.rect.x < forget.rect.x)
                        .filter((item) => item.rect.x > passwordRect.x)
                        .filter((item) => Math.abs((item.rect.y + item.rect.height / 2) - forgetCenterY) < 35)
                        .sort((left, right) => right.rect.x - left.rect.x);
                    if (candidates.length) {
                        return describe(candidates[0], "left-of-forget-password");
                    }
                }
                if (passwordRect) {
                    const x = passwordRect.x + passwordRect.width - 18;
                    const y = passwordRect.y + passwordRect.height / 2;
                    const target = document.elementFromPoint(x, y);
                    if (target) {
                        return {
                            reason: "password-input-right-edge",
                            text: clean(target.innerText || target.textContent),
                            className: String(target.className || ""),
                            tagName: String(target.tagName || ""),
                            x,
                            y,
                            rect: {
                                x: passwordRect.x,
                                y: passwordRect.y,
                                width: passwordRect.width,
                                height: passwordRect.height,
                            },
                        };
                    }
                }
                return null;
            })()
            """.replace("__PASSWORD__", quoted_password),
            deadline,
        )
        if isinstance(target, dict) and target.get("x") is not None and target.get("y") is not None:
            _dispatch_mouse_click(ws, float(target["x"]), float(target["y"]), deadline)
            return target
        time.sleep(0.5)
    raise TimeoutError("bilibili password eye button was not found")


def _bilibili_password_input_state(ws, password: str, deadline: float) -> dict[str, str]:
    quoted_password = json.dumps(password)
    state = _evaluate_value(
        ws,
        f"""
        (() => {{
            const password = {quoted_password};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const inputs = Array.from(document.querySelectorAll("input"))
                .filter(visible)
                .filter((input) => input.value === password || input.type === "password" || String(input.placeholder || "").includes("密码"));
            const input = inputs[inputs.length - 1] || null;
            if (!input) return {{}};
            const style = window.getComputedStyle(input);
            return {{
                value: String(input.value || ""),
                type: String(input.type || ""),
                textSecurity: String(style.webkitTextSecurity || ""),
                placeholder: String(input.placeholder || ""),
                outerHTML: String(input.outerHTML || "").slice(0, 500),
            }};
        }})()
        """,
        deadline,
    )
    if not isinstance(state, dict) or not state:
        raise RuntimeError("bilibili password input state was not found")
    return {str(key): str(value) for key, value in state.items()}


def _evaluate_value(ws, expression: str, deadline: float):
    response = _send_and_wait(
        ws,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
        deadline,
    )
    return response.get("result", {}).get("result", {}).get("value")


def _dispatch_mouse_click(ws, x: float, y: float, deadline: float) -> None:
    _send_and_wait(
        ws,
        "Input.dispatchMouseEvent",
        {"type": "mouseMoved", "x": x, "y": y, "button": "none"},
        deadline,
    )
    _send_and_wait(
        ws,
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
        deadline,
    )
    _send_and_wait(
        ws,
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
        deadline,
    )
