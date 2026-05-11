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


@dataclass
class DevtoolsBlockResult:
    requested_url: str
    target_id: str
    target_url: str
    title: str
    devtools_opened: bool
    opened_targets: list[dict[str, str]]
    attempts: list[str]
    evidence: str = ""


@dataclass
class ExtensionInstallBlockResult:
    extensions_requested_url: str
    extensions_target_url: str
    extensions_blocked: bool
    extensions_evidence: str
    webstore_requested_url: str
    webstore_target_url: str
    install_button_clicked: bool
    install_error_visible: bool
    install_error_text: str
    target_id: str
    title: str
    kernel_window_maximized: bool = False
    extension_status_before_click: str = ""
    extension_status_after_click: str = ""
    webstore_switch_chrome_prompt_visible: bool = False
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


def verify_extension_management_and_install_blocked(
    port: int,
    extensions_url: str = "chrome://extensions/",
    webstore_url: str = "",
    expected_install_error: str = "下载时出错: Invalid manifest",
    timeout_seconds: int = 75,
    http_timeout_seconds: int = 2,
) -> ExtensionInstallBlockResult:
    if port <= 0:
        raise ValueError(f"kernel CDP port must be positive: {port}")
    if not webstore_url:
        raise ValueError("webstore_url is required")

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
        kernel_window_maximized = _maximize_target_window(ws, target_id, deadline)

        extension_nav = _send_and_wait(ws, "Page.navigate", {"url": extensions_url}, deadline)
        extension_error = str(extension_nav.get("result", {}).get("errorText", "") or "")
        extensions_snapshot = _wait_page_evidence(
            ws,
            expected_text="ERR_BLOCKED_BY_CLIENT",
            deadline=deadline,
            fallback_wait_seconds=6,
        )
        extensions_evidence = "\n".join(
            [
                extension_error,
                str(extensions_snapshot.get("title", "")),
                str(extensions_snapshot.get("url", "")),
                str(extensions_snapshot.get("text", "")),
            ]
        )
        extensions_blocked = "ERR_BLOCKED_BY_CLIENT" in extensions_evidence

        _send_and_wait(ws, "Page.navigate", {"url": webstore_url}, deadline)
        _wait_chrome_webstore_ready(ws, deadline)
        prompt_dismissed = _dismiss_chrome_webstore_switch_prompt(ws, deadline)
        extension_id = _extension_id_from_webstore_url(webstore_url)
        extension_status_before = _chrome_webstore_extension_status(ws, extension_id, deadline)
        install_button = _click_chrome_webstore_add_button(ws, deadline)
        install_error_deadline = min(deadline, time.time() + 30)
        install_error = _wait_text_in_page(ws, expected_install_error, install_error_deadline)
        extension_status_after = _chrome_webstore_extension_status(ws, extension_id, min(deadline, time.time() + 5))
        final_snapshot = _safe_evaluate_page_snapshot(ws, min(deadline, time.time() + 5))
        final_text = str(final_snapshot.get("text", ""))
        switch_chrome_prompt_visible = "切换到 Chrome 即可安装扩展程序和主题背景" in final_text

        return ExtensionInstallBlockResult(
            extensions_requested_url=extensions_url,
            extensions_target_url=str(extensions_snapshot.get("url", "")),
            extensions_blocked=extensions_blocked,
            extensions_evidence=extensions_evidence,
            webstore_requested_url=webstore_url,
            webstore_target_url=str(final_snapshot.get("url", "")),
            install_button_clicked=bool(install_button),
            install_error_visible=bool(install_error),
            install_error_text=expected_install_error if install_error else "",
            target_id=target_id,
            title=str(final_snapshot.get("title", "")),
            kernel_window_maximized=kernel_window_maximized,
            extension_status_before_click=extension_status_before,
            extension_status_after_click=extension_status_after,
            webstore_switch_chrome_prompt_visible=switch_chrome_prompt_visible,
            evidence=(
                f"extensions={extensions_evidence[:1000]}, kernel_window_maximized={kernel_window_maximized}, "
                f"prompt_dismissed={prompt_dismissed}, "
                f"extension_status_before={extension_status_before}, extension_status_after={extension_status_after}, "
                f"switch_chrome_prompt_visible={switch_chrome_prompt_visible}, add_button={install_button}, "
                f"final_text={final_text[:1000]}"
            ),
        )
    finally:
        try:
            ws.close()
        finally:
            _close_target(port, target_id, timeout_seconds=http_timeout_seconds)


def verify_kernel_devtools_blocked(
    port: int,
    url: str = "https://www.bilibili.com",
    timeout_seconds: int = 35,
    http_timeout_seconds: int = 2,
) -> DevtoolsBlockResult:
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

    baseline_targets = _list_targets(port, timeout_seconds=http_timeout_seconds)
    baseline_ids = {str(item.get("id", "")) for item in baseline_targets}
    attempts: list[str] = []
    ws = websocket.create_connection(websocket_url, timeout=http_timeout_seconds, suppress_origin=True)
    try:
        deadline = time.time() + timeout_seconds
        _send_and_wait(ws, "Page.enable", {}, deadline)
        _send_and_wait(ws, "Runtime.enable", {}, deadline)
        _send_and_wait(ws, "Page.bringToFront", {}, deadline)
        _send_and_wait(ws, "Page.navigate", {"url": url}, deadline)
        _wait_document_interactive(ws, deadline)
        _wait_bilibili_body_ready(ws, deadline)

        attempts.append("F12")
        _dispatch_key_press(ws, key="F12", code="F12", windows_virtual_key_code=123, deadline=deadline)
        time.sleep(1.5)

        attempts.append("Ctrl+Shift+I")
        _dispatch_key_shortcut(ws, key="I", code="KeyI", windows_virtual_key_code=73, deadline=deadline)
        time.sleep(1.5)

        attempts.append("right-click-context-inspect-shortcut")
        _dispatch_right_click_and_inspect_shortcut(ws, deadline)
        time.sleep(1.5)

        snapshot = _evaluate_page_snapshot(ws, deadline)
        after_targets = _list_targets(port, timeout_seconds=http_timeout_seconds)
        opened_targets = [
            _target_summary(item)
            for item in after_targets
            if _target_is_devtools(item) or (
                str(item.get("id", "")) not in baseline_ids and _target_looks_like_devtools(item)
            )
        ]
        devtools_opened = bool(opened_targets)
        return DevtoolsBlockResult(
            requested_url=url,
            target_id=target_id,
            target_url=str(snapshot.get("url", "")),
            title=str(snapshot.get("title", "")),
            devtools_opened=devtools_opened,
            opened_targets=opened_targets,
            attempts=attempts,
            evidence=f"baseline={[_target_summary(item) for item in baseline_targets]}, after={[_target_summary(item) for item in after_targets]}",
        )
    finally:
        try:
            ws.close()
        finally:
            for item in _list_targets(port, timeout_seconds=http_timeout_seconds):
                if _target_is_devtools(item):
                    _close_target(port, str(item.get("id", "")), timeout_seconds=http_timeout_seconds)
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


def _list_targets(port: int, timeout_seconds: int = 2) -> list[dict[str, Any]]:
    if port <= 0:
        return []
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _target_summary(target: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(target.get("id", "")),
        "type": str(target.get("type", "")),
        "title": str(target.get("title", "")),
        "url": str(target.get("url", "")),
    }


def _target_is_devtools(target: dict[str, Any]) -> bool:
    url = str(target.get("url", "")).lower()
    target_type = str(target.get("type", "")).lower()
    title = str(target.get("title", "")).lower()
    return url.startswith("devtools://") or target_type == "devtools" or "devtools" in title


def _target_looks_like_devtools(target: dict[str, Any]) -> bool:
    url = str(target.get("url", "")).lower()
    title = str(target.get("title", "")).lower()
    return "devtools" in url or "developer tools" in title or "开发者工具" in title


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
        const visit = (root) => {
            if (!root) return;
            for (const el of Array.from(root.querySelectorAll("*"))) {
                push(el.innerText);
                push(el.textContent);
                if (el.shadowRoot) visit(el.shadowRoot);
            }
        };
        push(document.title);
        push(document.body ? document.body.innerText : "");
        push(document.documentElement ? document.documentElement.innerText : "");
        push(document.documentElement ? document.documentElement.outerHTML : "");
        visit(document);
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


def _safe_evaluate_page_snapshot(ws, deadline: float) -> dict[str, str]:
    try:
        return _evaluate_page_snapshot(ws, deadline)
    except Exception as exc:
        return {"title": "", "url": "", "text": f"snapshot failed: {exc}"}


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


def _wait_page_evidence(
    ws,
    expected_text: str,
    deadline: float,
    fallback_wait_seconds: int = 6,
) -> dict[str, str]:
    fallback_deadline = min(deadline, time.time() + fallback_wait_seconds)
    last_snapshot: dict[str, str] = {}
    while time.time() < fallback_deadline:
        last_snapshot = _evaluate_page_snapshot(ws, deadline)
        if expected_text in "\n".join(
            [
                str(last_snapshot.get("title", "")),
                str(last_snapshot.get("url", "")),
                str(last_snapshot.get("text", "")),
            ]
        ):
            return last_snapshot
        time.sleep(0.3)
    return last_snapshot


def _maximize_target_window(ws, target_id: str, deadline: float) -> bool:
    if not target_id:
        return False
    try:
        response = _send_and_wait(ws, "Browser.getWindowForTarget", {"targetId": target_id}, deadline)
        window_id = response.get("result", {}).get("windowId")
        if window_id is None:
            return False
        _send_and_wait(
            ws,
            "Browser.setWindowBounds",
            {"windowId": window_id, "bounds": {"windowState": "maximized"}},
            deadline,
        )
        time.sleep(0.8)
        return True
    except Exception:
        return False


def _wait_chrome_webstore_ready(ws, deadline: float) -> None:
    while time.time() < deadline:
        ready = _evaluate_value(
            ws,
            """
            (() => {
                const text = document.body ? (document.body.innerText || "") : "";
                return location.href.includes("chromewebstore.google.com")
                    && (text.includes("添加至 Chrome") || text.includes("Add to Chrome") || text.includes("Chrome"));
            })()
            """,
            deadline,
        )
        if ready:
            return
        time.sleep(0.5)
    raise TimeoutError("chrome web store page did not become ready")


def _click_chrome_webstore_add_button(ws, deadline: float) -> dict[str, Any]:
    while time.time() < deadline:
        target = _evaluate_value(
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
                const all = [];
                const visit = (root) => {
                    for (const el of Array.from(root.querySelectorAll("*"))) {
                        all.push(el);
                        if (el.shadowRoot) visit(el.shadowRoot);
                    }
                };
                visit(document);
                const candidates = all
                    .filter(visible)
                    .map((el) => ({ el, text: clean(el.innerText || el.textContent), rect: el.getBoundingClientRect() }))
                    .filter((item) => item.text === "添加至 Chrome" || item.text === "Add to Chrome" || item.text.includes("添加至 Chrome"))
                    .sort((left, right) => {
                        const leftArea = left.rect.width * left.rect.height;
                        const rightArea = right.rect.width * right.rect.height;
                        return leftArea - rightArea;
                    });
                const item = candidates[0] || null;
                if (!item) return null;
                return {
                    text: item.text,
                    x: item.rect.x + item.rect.width / 2,
                    y: item.rect.y + item.rect.height / 2,
                    rect: {
                        x: item.rect.x,
                        y: item.rect.y,
                        width: item.rect.width,
                        height: item.rect.height,
                    },
                };
            })()
            """,
            deadline,
        )
        if isinstance(target, dict) and target.get("x") is not None and target.get("y") is not None:
            _dispatch_mouse_click(ws, float(target["x"]), float(target["y"]), deadline)
            return target
        time.sleep(0.5)
    raise TimeoutError("chrome web store add button was not found")


def _dismiss_chrome_webstore_switch_prompt(ws, deadline: float) -> bool:
    prompt_deadline = min(deadline, time.time() + 8)
    while time.time() < prompt_deadline:
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
                const all = [];
                const visit = (root) => {
                    for (const el of Array.from(root.querySelectorAll("*"))) {
                        all.push(el);
                        if (el.shadowRoot) visit(el.shadowRoot);
                    }
                };
                visit(document);
                const candidates = all
                    .filter(visible)
                    .map((el) => ({ el, text: clean(el.innerText || el.textContent), rect: el.getBoundingClientRect() }))
                    .filter((item) => ["不了，谢谢", "No thanks", "不用了，谢谢"].includes(item.text))
                    .sort((left, right) => {
                        const leftArea = left.rect.width * left.rect.height;
                        const rightArea = right.rect.width * right.rect.height;
                        return leftArea - rightArea;
                    });
                const item = candidates[0] || null;
                if (!item) return false;
                const button = item.el.closest("button,[role='button'],a") || item.el;
                button.click();
                return {
                    text: item.text,
                    tagName: button.tagName,
                    rect: {
                        x: item.rect.x,
                        y: item.rect.y,
                        width: item.rect.width,
                        height: item.rect.height,
                    },
                };
            })()
            """,
            deadline,
        )
        if clicked:
            wait_deadline = min(deadline, time.time() + 3)
            while time.time() < wait_deadline:
                still_visible = _evaluate_value(
                    ws,
                    """
                    (() => {
                        const text = document.body ? (document.body.innerText || "") : "";
                        return text.includes("不了，谢谢") || text.includes("No thanks") || text.includes("不用了，谢谢");
                    })()
                    """,
                    deadline,
                )
                if not still_visible:
                    return True
                time.sleep(0.2)
            return True
        time.sleep(0.5)
    return False


def _extension_id_from_webstore_url(url: str) -> str:
    match = urllib.parse.urlparse(url)
    parts = [part for part in match.path.split("/") if part]
    return parts[-1] if parts else ""


def _chrome_webstore_extension_status(ws, extension_id: str, deadline: float) -> str:
    if not extension_id:
        return ""
    value = _evaluate_value(
        ws,
        f"""
        (() => new Promise((resolve) => {{
            const extensionId = {json.dumps(extension_id)};
            if (!window.chrome || !chrome.webstorePrivate || !chrome.webstorePrivate.getExtensionStatus) {{
                resolve("");
                return;
            }}
            try {{
                chrome.webstorePrivate.getExtensionStatus(extensionId, (status) => resolve(String(status || "")));
            }} catch (error) {{
                resolve(`exception:${{String(error && error.message || error)}}`);
            }}
        }}))()
        """,
        deadline,
    )
    return str(value or "")


def _wait_text_in_page(ws, expected_text: str, deadline: float) -> bool:
    while time.time() < deadline:
        found = _evaluate_value(
            ws,
            f"""
            (() => {{
                const expectedText = {json.dumps(expected_text)};
                const textParts = [];
                const push = (value) => {{
                    const text = String(value || "");
                    if (text) textParts.push(text);
                }};
                const visit = (root) => {{
                    if (!root) return;
                    for (const el of Array.from(root.querySelectorAll("*"))) {{
                        push(el.innerText);
                        push(el.textContent);
                        if (el.shadowRoot) visit(el.shadowRoot);
                    }}
                }};
                push(document.body ? document.body.innerText : "");
                push(document.documentElement ? document.documentElement.innerText : "");
                visit(document);
                return textParts.join("\\n").includes(expectedText);
            }})()
            """,
            deadline,
        )
        if found:
            return True
        time.sleep(0.5)
    return False


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


def _dispatch_key_press(
    ws,
    key: str,
    code: str,
    windows_virtual_key_code: int,
    deadline: float,
) -> None:
    params = {
        "key": key,
        "code": code,
        "windowsVirtualKeyCode": windows_virtual_key_code,
        "nativeVirtualKeyCode": windows_virtual_key_code,
    }
    _send_and_wait(ws, "Input.dispatchKeyEvent", {"type": "rawKeyDown", **params}, deadline)
    _send_and_wait(ws, "Input.dispatchKeyEvent", {"type": "keyUp", **params}, deadline)


def _dispatch_key_shortcut(
    ws,
    key: str,
    code: str,
    windows_virtual_key_code: int,
    deadline: float,
) -> None:
    modifiers = 2 | 8
    params = {
        "key": key,
        "code": code,
        "windowsVirtualKeyCode": windows_virtual_key_code,
        "nativeVirtualKeyCode": windows_virtual_key_code,
        "modifiers": modifiers,
    }
    _send_and_wait(ws, "Input.dispatchKeyEvent", {"type": "rawKeyDown", **params}, deadline)
    _send_and_wait(ws, "Input.dispatchKeyEvent", {"type": "keyUp", **params}, deadline)


def _dispatch_right_click_and_inspect_shortcut(ws, deadline: float) -> None:
    viewport = _evaluate_value(
        ws,
        """
        (() => ({
            x: Math.max(80, Math.floor(window.innerWidth / 2)),
            y: Math.max(80, Math.floor(window.innerHeight / 2))
        }))()
        """,
        deadline,
    )
    x = float(viewport.get("x", 300)) if isinstance(viewport, dict) else 300.0
    y = float(viewport.get("y", 300)) if isinstance(viewport, dict) else 300.0
    _send_and_wait(
        ws,
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "right", "clickCount": 1},
        deadline,
    )
    _send_and_wait(
        ws,
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "right", "clickCount": 1},
        deadline,
    )
    time.sleep(0.3)
    _dispatch_key_press(ws, key="I", code="KeyI", windows_virtual_key_code=73, deadline=deadline)
