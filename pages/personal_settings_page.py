from __future__ import annotations

import time
from pathlib import Path

from core.config import timeout_ms, timeout_seconds
from pages.base_page import BasePage


class PersonalSettingsPage(BasePage):
    def open_from_avatar(self) -> None:
        # 个人设置入口在顶部头像菜单里；如果头像 DOM 变动，优先检查这个 selector。
        self._dismiss_blocking_overlays()
        self.cdp.click("header.el-header .tool-bar-ri .avatar")
        self._click_visible_text("个人设置", within_selector=".userInfo-popover")
        self._wait_for_hash("#/personalInfo")

    def open_basic_settings(self) -> None:
        # “基础设置”tab 的稳定 id 是 #tab-basicSetting，注意不要点到“环境偏好设置”。
        self.cdp.click("#tab-basicSetting")
        self._wait_for_basic_settings()

    def environment_cache_dir(self) -> Path:
        # 环境缓存目录输入框没有稳定 placeholder，当前按可见 input 的值包含 DICloak/Cache 兜底识别。
        script = """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const inputs = Array.from(document.querySelectorAll("input")).filter(visible);
            const input = inputs.find((el) => {
                const value = el.value || "";
                return value.includes("DICloakCache") || value.includes("DICloak") || value.includes("Cache");
            });
            return input ? input.value : "";
        }
        """
        deadline = time.time() + timeout_seconds(self.config, "settings_cache_dir_seconds", 15)
        while time.time() < deadline:
            value = str(self.cdp.evaluate(script) or "").strip()
            if value:
                return Path(value)
            time.sleep(0.5)
        raise RuntimeError("environment cache directory was not found on basic settings page")

    def open_download_record_kernel_tab(self) -> None:
        # 下载记录里的“内核”是自绘 tab，不是 Element Plus tab，需要限定在 #DownloadLog 内点击。
        self.cdp.click_element_by_script(self._download_record_tab_script("内核"))
        self._wait_for_download_record_kernel_tab()

    def download_latest_kernel(self, major_version: str) -> str:
        # 内核版本区域按“134 版本”这样的标题分组，在该分组里点击“下载”。
        latest_version = self.latest_kernel_version(major_version)
        self.cdp.click_element_by_script(self._kernel_download_button_script(major_version))
        return latest_version

    def latest_kernel_version(self, major_version: str) -> str:
        # 从“最新为 Chrome 134.1.26 (20260428)”中提取真实版本号。
        script = f"""
        () => {{
            const section = document.querySelector("#CoreVersion");
            if (!section) return "";
            const expectedTitle = {f"{major_version} 版本"!r};
            const blocks = Array.from(section.children).filter((el) => {{
                const text = el.innerText || el.textContent || "";
                return text.includes(expectedTitle);
            }});
            const block = blocks[0] || section;
            const text = block.innerText || block.textContent || "";
            const match = text.match(new RegExp("Chrome\\\\s+({major_version}\\\\.\\\\d+(?:\\\\.\\\\d+)+)"));
            return match ? match[1] : "";
        }}
        """
        deadline = time.time() + timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            version = str(self.cdp.evaluate(script) or "").strip()
            if version:
                return version
            time.sleep(0.5)
        raise RuntimeError(f"latest kernel version was not found: {major_version}")

    def delete_download_record_kernels_except_first(self) -> None:
        self.open_download_record_kernel_tab()
        while True:
            before = self.download_record_kernel_count()
            delete_button_count = self.download_record_kernel_delete_button_count()
            if before <= 1 or delete_button_count == 0:
                break
            self.cdp.click_element_by_script(self._download_record_kernel_delete_button_script())
            self._wait_download_record_kernel_count_less_than(before)

        after = self.download_record_kernel_count()
        if after > 1 and self.download_record_kernel_delete_button_count() > 0:
            raise AssertionError(f"download record kernel cleanup failed: remaining={after}")

    def download_record_kernel_count(self) -> int:
        value = self.cdp.evaluate(
            """
            () => {
                const root = document.querySelector("#DownloadLog");
                if (!root) return 0;
                return Array.from(root.querySelectorAll("ul li"))
                    .filter((li) => (li.innerText || li.textContent || "").includes("Chrome "))
                    .length;
            }
            """
        )
        return int(value or 0)

    def download_record_kernel_delete_button_count(self) -> int:
        value = self.cdp.evaluate(
            """
            () => {
                const root = document.querySelector("#DownloadLog");
                if (!root) return 0;
                return Array.from(root.querySelectorAll("ul li button"))
                    .filter((button) => button.querySelector(".icon-fail"))
                    .length;
            }
            """
        )
        return int(value or 0)

    def _wait_download_record_kernel_count_less_than(self, before_count: int) -> None:
        deadline = time.time() + timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.download_record_kernel_count() < before_count:
                return
            time.sleep(0.5)
        raise TimeoutError("download record kernel row was not deleted")

    def _dismiss_blocking_overlays(self) -> None:
        # 上次调试失败后可能残留 el-drawer/el-dialog，先用 Escape 关闭，避免挡住头像点击。
        for _ in range(3):
            has_overlay = self.cdp.evaluate(
                """
                () => Boolean(document.querySelector(".el-drawer, .el-dialog, .el-message-box"))
                """
            )
            if not has_overlay:
                return
            clicked = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    const selectors = [
                        ".el-drawer__close-btn",
                        ".el-dialog__headerbtn",
                        ".el-message-box__headerbtn",
                        ".el-overlay button[aria-label='Close']",
                    ];
                    for (const selector of selectors) {
                        const button = Array.from(document.querySelectorAll(selector)).find(visible);
                        if (button) {
                            button.click();
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
            if clicked:
                time.sleep(0.5)
                continue
            self.cdp.press("Escape")
            time.sleep(0.3)

    def _wait_for_basic_settings(self, timeout_seconds_value: int | None = None) -> None:
        timeout_seconds_value = timeout_seconds_value or timeout_seconds(self.config, "page_seconds", 10)
        script = """
        () => {
            const activeTab = document.querySelector("#tab-basicSetting.is-active");
            const bodyText = document.body.innerText || "";
            return Boolean(activeTab && bodyText.includes("环境缓存目录"));
        }
        """
        deadline = time.time() + timeout_seconds_value
        while time.time() < deadline:
            if self.cdp.evaluate(script):
                return
            time.sleep(0.5)
        raise TimeoutError("basic settings page did not become active")

    def _click_visible_text(self, text: str, within_selector: str = "body") -> None:
        script = f"""
        () => {{
            const root = document.querySelector({within_selector!r}) || document.body;
            const expectedText = {text!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const candidates = Array.from(root.querySelectorAll("li,button,div,span"))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").includes(expectedText))
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    const actualText = (el.innerText || el.textContent || "").trim();
                    return {{
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height,
                        exact: actualText === expectedText,
                        area: rect.width * rect.height,
                    }};
                }});
            candidates.sort((left, right) => {{
                if (left.exact !== right.exact) return left.exact ? -1 : 1;
                return left.area - right.area;
            }});
            return candidates[0] || null;
        }}
        """
        rect = self.cdp.evaluate(script)
        if not rect:
            raise RuntimeError(f"visible text was not found: {text}")
        self.cdp.click_at(float(rect["x"]) + float(rect["width"]) / 2, float(rect["y"]) + float(rect["height"]) / 2)

    def _download_record_tab_script(self, text: str) -> str:
        return f"""
        () => {{
            const root = document.querySelector("#DownloadLog");
            if (!root) return null;
            return Array.from(root.querySelectorAll("p,span,button,div"))
                .find((el) => {{
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0
                        && (el.innerText || el.textContent || "").trim() === {text!r};
                }}) || null;
        }}
        """

    def _wait_for_download_record_kernel_tab(self) -> None:
        deadline = time.time() + timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            active = self.cdp.evaluate(
                """
                () => {
                    const root = document.querySelector("#DownloadLog");
                    if (!root) return false;
                    const tab = Array.from(root.querySelectorAll("p"))
                        .find((el) => (el.innerText || el.textContent || "").trim() === "内核");
                    return Boolean(tab && String(tab.className || "").includes("tw-text-black"));
                }
                """
            )
            if active:
                return
            time.sleep(0.2)
        raise TimeoutError("download record kernel tab did not become active")

    def _download_record_kernel_delete_button_script(self) -> str:
        # 第一条记录没有删除按钮；这里始终点当前可删除记录里的第一个 x，删除后重新读取列表。
        return """
        () => {
            const root = document.querySelector("#DownloadLog");
            if (!root) return null;
            return Array.from(root.querySelectorAll("ul li button"))
                .find((button) => {
                    const rect = button.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 && button.querySelector(".icon-fail");
                }) || null;
        }
        """

    def _kernel_download_button_script(self, major_version: str) -> str:
        return f"""
        () => {{
            const section = document.querySelector("#CoreVersion");
            if (!section) return null;
            const expectedTitle = {f"{major_version} 版本"!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const candidates = Array.from(section.querySelectorAll("div"))
                .filter((el) => visible(el) && (el.innerText || el.textContent || "").includes(expectedTitle));
            candidates.sort((left, right) => {{
                const leftRect = left.getBoundingClientRect();
                const rightRect = right.getBoundingClientRect();
                return (leftRect.width * leftRect.height) - (rightRect.width * rightRect.height);
            }});
            for (const block of candidates) {{
                const button = Array.from(block.querySelectorAll("button,p,span"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === "下载");
                if (button) return button;
            }}
            return null;
        }}
        """

    def _wait_for_hash(self, expected_hash: str, timeout_ms_value: int | None = None) -> None:
        timeout_ms_value = timeout_ms_value or timeout_ms(self.config, "page_seconds", 10)
        script = f"""
        () => new Promise((resolve, reject) => {{
            const expectedHash = {expected_hash!r};
            const deadline = Date.now() + {timeout_ms_value};
            const timer = setInterval(() => {{
                if (location.hash === expectedHash) {{
                    clearInterval(timer);
                    resolve(true);
                    return;
                }}
                if (Date.now() > deadline) {{
                    clearInterval(timer);
                    reject(new Error(`hash did not become ${{expectedHash}}; actual=${{location.hash}}`));
                }}
            }}, 200);
        }})
        """
        self.cdp.evaluate(script)
