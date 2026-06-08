from __future__ import annotations

import time

from core.config import timeout_seconds as config_timeout_seconds
from pages.base_page import BasePage


class AppPage(BasePage):
    """Application-level recovery helpers.

    This layer stays business-neutral: it closes blocking UI chrome, waits for
    the app to be operable, and never navigates to a business module.
    """

    def recover_to_stable_state(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        self._select_active_app_page()
        self._dismiss_transient_layers()
        self._wait_until_not_loading(timeout_seconds)
        self._wait_for_app_shell(timeout_seconds)

    def click_app_refresh_button(self) -> None:
        self._select_active_app_page()
        self.cdp.click_element_by_script(self._app_refresh_button_script())
        time.sleep(0.5)

    def reload_app_page(self) -> None:
        self._select_active_app_page()
        self.cdp.reload()

    def _select_active_app_page(self) -> None:
        page = getattr(self.cdp, "page", None)
        if not page:
            return

        try:
            if page.is_closed():
                page = None
        except Exception:
            page = None

        context = None
        if page:
            try:
                context = page.context
            except Exception:
                context = None
        if not context:
            browser = getattr(self.cdp, "browser", None)
            contexts = getattr(browser, "contexts", []) if browser else []
            context = contexts[0] if contexts else None
        if not context:
            return

        candidates = []
        for candidate in context.pages:
            try:
                if candidate.is_closed() or candidate.url.startswith("devtools://"):
                    continue
                candidates.append(candidate)
            except Exception:
                continue
        if not candidates:
            return

        selected = next(
            (
                candidate
                for candidate in candidates
                if "/resources/app.asar.unpacked/dist/index.html" in candidate.url
            ),
            candidates[0],
        )
        self.cdp.page = selected
        try:
            selected.bring_to_front()
        except Exception:
            pass

    def _dismiss_transient_layers(self) -> None:
        for _ in range(5):
            clicked = bool(self.cdp.evaluate(self._safe_close_overlay_script()))
            if not clicked:
                try:
                    self.cdp.press("Escape")
                except Exception:
                    pass
            time.sleep(0.25)
            if not self._has_blocking_overlay():
                break

    def _has_blocking_overlay(self) -> bool:
        try:
            return bool(
                self.cdp.evaluate(
                    """
                    () => {
                        const visible = (el) => {
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== "none"
                                && style.visibility !== "hidden"
                                && rect.width > 0
                                && rect.height > 0;
                        };
                        return Array.from(document.querySelectorAll(
                            ".el-message-box, .el-dialog, .el-drawer, .el-popover, .el-popper"
                        )).some(visible);
                    }
                    """
                )
            )
        except Exception:
            return False

    def _safe_close_overlay_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clickFirst = (selectors) => {
                for (const selector of selectors) {
                    const target = Array.from(document.querySelectorAll(selector)).find(visible);
                    if (target) {
                        target.click();
                        return true;
                    }
                }
                return false;
            };

            const messageBox = Array.from(document.querySelectorAll(".el-message-box")).find(visible);
            if (messageBox) {
                const closeButton = messageBox.querySelector(".el-message-box__headerbtn");
                if (closeButton && visible(closeButton)) {
                    closeButton.click();
                    return true;
                }
                const cancelButton = Array.from(messageBox.querySelectorAll("button"))
                    .filter(visible)
                    .find((button) => {
                        const text = (button.innerText || button.textContent || "").trim();
                        return text.includes("取消") || !button.classList.contains("el-button--primary");
                    });
                if (cancelButton) {
                    cancelButton.click();
                    return true;
                }
            }

            if (clickFirst([
                ".el-drawer__close-btn",
                ".el-dialog__headerbtn",
                ".el-overlay button[aria-label='Close']",
                ".el-popover button[aria-label='Close']",
            ])) {
                return true;
            }
            return false;
        }
        """

    def _app_refresh_button_script(self) -> str:
        return """
        () => {
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const icons = Array.from(document.querySelectorAll("i.icon-refresh, .icon-refresh"))
                .filter(visible)
                .map((el) => {
                    const clickable = el.closest("button, [role='button'], a, div") || el;
                    const rect = clickable.getBoundingClientRect();
                    return { el: clickable, x: rect.x, y: rect.y, area: rect.width * rect.height };
                })
                .filter((item) => item.y < 120 && item.area > 0)
                .sort((left, right) => left.x - right.x);
            return icons[0]?.el || null;
        }
        """

    def _wait_until_not_loading(self, timeout_seconds: int) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            loading = bool(
                self.cdp.evaluate(
                    """
                    () => {
                        const visible = (el) => {
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== "none"
                                && style.visibility !== "hidden"
                                && rect.width > 0
                                && rect.height > 0;
                        };
                        return Array.from(document.querySelectorAll(
                            ".el-loading-mask, .el-loading-spinner"
                        )).some(visible);
                    }
                    """
                )
            )
            if not loading:
                return
            time.sleep(0.2)
        raise TimeoutError("APP still has visible loading mask after recovery timeout")

    def _wait_for_app_shell(self, timeout_seconds: int) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._app_shell_visible():
                return
            time.sleep(0.2)
        raise TimeoutError("APP shell was not visible after recovery")

    def _app_shell_visible(self) -> bool:
        try:
            return bool(
                self.cdp.evaluate(
                    """
                    () => {
                        const text = document.body ? (document.body.innerText || "") : "";
                        const moduleTexts = [
                            "环境管理",
                            "代理管理",
                            "扩展管理",
                            "环境分组",
                            "成员管理",
                            "全局设置",
                        ];
                        return moduleTexts.some((item) => text.includes(item))
                            || Boolean(document.querySelector(".el-menu, aside, nav"));
                    }
                    """
                )
            )
        except Exception:
            return False
