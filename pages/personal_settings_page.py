from __future__ import annotations

import json
import re
import time
from pathlib import Path

from core.config import timeout_ms, timeout_seconds
from pages.base_page import BasePage


class PersonalSettingsPage(BasePage):
    DOWNLOAD_RECORD_KERNEL_TAB_TEXTS = ("浏览器内核", "内核")

    def open_from_avatar(self) -> None:
        # 个人设置入口在顶部头像菜单里；如果头像 DOM 变动，优先检查这个 selector。
        self._dismiss_blocking_overlays()
        self.cdp.click("header.el-header .tool-bar-ri .avatar")
        self._click_visible_text("个人设置", within_selector=".userInfo-popover")
        self._wait_for_hash("#/personalInfo")

    def open_basic_settings(self) -> None:
        # 新版个人设置使用自绘分段按钮，旧版曾有 #tab-basicSetting；这里按真实可见 tab 文案定位。
        try:
            self.cdp.click("#tab-basicSetting", timeout=2000)
        except Exception:
            self.cdp.click_element_by_script(self._personal_settings_tab_script("基础设置"))
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
        # 下载记录里的内核 tab 是自绘 tab，不是 Element Plus tab，需要限定在 #DownloadLog 内点击。
        self.cdp.click_element_by_script(self._download_record_tab_script(self.DOWNLOAD_RECORD_KERNEL_TAB_TEXTS))
        self._wait_for_download_record_kernel_tab()

    def download_latest_kernel(self, major_version: str) -> str:
        # 内核版本区域按主版本分组，只点击目标分组内的下载按钮。
        major_version = self._kernel_major(major_version)
        latest_version = self.latest_kernel_version(major_version)
        self.cdp.click_element_by_script(self._kernel_download_button_script(major_version))
        return latest_version

    @staticmethod
    def _kernel_major(major_version: str) -> str:
        major = str(major_version).strip()
        if not re.fullmatch(r"[1-9][0-9]{1,3}", major):
            raise ValueError("浏览器内核主版本必须是有效数字")
        return major

    def _download_record_kernel_states(self) -> list[dict]:
        states = self.cdp.evaluate(
            """
            () => {
                const root = document.querySelector('#DownloadLog');
                if (!root) return [];
                const visible = el => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.display !== 'none'
                        && s.visibility !== 'hidden';
                };
                return Array.from(root.querySelectorAll('ul li')).filter(visible)
                    .map(row => {
                        const text = row.innerText || row.textContent || '';
                        const match = text.match(/Chrome\\s+([0-9]+\\.[0-9]+(?:\\.[0-9]+)+)/);
                        const button = Array.from(row.querySelectorAll('button'))
                            .find(b => visible(b) && b.querySelector('.icon-fail'));
                        const busy = /下载中|正在下载|解压中|正在解压|安装中/.test(text)
                            || Array.from(row.querySelectorAll('.el-progress, [role=progressbar], .is-loading'))
                                .some(visible);
                        return {
                            version: match ? match[1] : '',
                            deletable: Boolean(button && !button.disabled),
                            busy,
                            failed: /下载失败|解压失败|安装失败|已取消/.test(text),
                        };
                    }).filter(row => row.version);
            }
            """
        )
        return [item for item in states if isinstance(item, dict)] if isinstance(states, list) else []

    def download_record_kernel_versions(self, major_version: str | None = None) -> list[str]:
        major = self._kernel_major(major_version) if major_version is not None else None
        return [
            str(item["version"])
            for item in self._download_record_kernel_states()
            if major is None or str(item.get("version", "")).split(".", 1)[0] == major
        ]

    def delete_downloaded_kernels(self, major_version: str) -> list[str]:
        """逐一删除目标主版本的记录，返回实际删除成功的完整版本号。"""
        major = self._kernel_major(major_version)
        self.open_download_record_kernel_tab()
        self.refresh_download_record_kernels()
        removed: list[str] = []
        deadline = time.monotonic() + timeout_seconds(self.config, "kernel_download_seconds", 300)
        while time.monotonic() < deadline:
            records = [
                item for item in self._download_record_kernel_states()
                if str(item.get("version", "")).split(".", 1)[0] == major
            ]
            if not records:
                return removed
            version = str(records[0]["version"])
            if records[0].get("busy") or not records[0].get("deletable"):
                raise RuntimeError(f"目标内核当前不可删除: {version}，请确认未被环境占用")
            self.cdp.click_element_by_script(self._kernel_delete_button_script(version))
            while time.monotonic() < deadline:
                if version not in self.download_record_kernel_versions(major):
                    # 删除会异步重绘列表；必须重新扫描本地版本，不能将短暂空态
                    # 或其他行减少当作该主版本已经全部删除。
                    self.refresh_download_record_kernels()
                    if version not in self.download_record_kernel_versions(major):
                        if version not in removed:
                            removed.append(version)
                        break
                self._confirm_kernel_deletion_if_visible()
                time.sleep(0.2)
            else:
                raise TimeoutError(f"目标内核删除后仍出现在下载记录中: {version}")
        raise TimeoutError(f"删除 {major} 内核超时")

    def refresh_download_record_kernels(self) -> None:
        """使用 APP 下载记录的刷新入口重新扫描，等待刷新结束后再读列表。"""
        button_script = self._download_record_refresh_button_script()
        self.cdp.click_element_by_script(button_script)
        idle_script = f"""
        () => {{
            const button = ({button_script})();
            return Boolean(button && !button.classList.contains('tw-animate-spin'));
        }}
        """
        deadline = time.monotonic() + timeout_seconds(self.config, "page_seconds", 10)
        while time.monotonic() < deadline:
            if self.cdp.evaluate(idle_script) is True:
                return
            time.sleep(0.1)
        raise TimeoutError("等待内核下载记录刷新完成超时")

    @staticmethod
    def _download_record_refresh_button_script() -> str:
        return """
        () => {
            const root = document.querySelector('#DownloadLog');
            if (!root) return null;
            return Array.from(root.querySelectorAll('.el-icon.tw-cursor-pointer'))
                .find(el => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return !el.closest('ul') && r.width > 0 && r.height > 0
                        && s.display !== 'none' && s.visibility !== 'hidden';
                }) || null;
        }
        """

    def _kernel_delete_button_script(self, version: str) -> str:
        return """
        () => {
            const expectedVersion = __VERSION__;
            const root = document.querySelector('#DownloadLog');
            if (!root) return null;
            const visible = el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            };
            for (const row of Array.from(root.querySelectorAll('ul li')).filter(visible)) {
                const match = (row.innerText || row.textContent || '')
                    .match(/Chrome\\s+([0-9]+\\.[0-9]+(?:\\.[0-9]+)+)/);
                if (!match || match[1] !== expectedVersion) continue;
                return Array.from(row.querySelectorAll('button'))
                    .find(b => visible(b) && !b.disabled && b.querySelector('.icon-fail')) || null;
            }
            return null;
        }
        """.replace("__VERSION__", json.dumps(version))

    def _confirm_kernel_deletion_if_visible(self) -> None:
        self.cdp.evaluate(
            """
            () => {
                const visible = el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                };
                for (const box of Array.from(document.querySelectorAll('.el-message-box, .el-dialog')).filter(visible)) {
                    const text = box.innerText || '';
                    if (!text.includes('删除') || !text.includes('内核')) continue;
                    const button = Array.from(box.querySelectorAll('button'))
                        .find(b => visible(b) && !b.disabled && ['确定', '确认'].includes(b.innerText.trim()));
                    if (button) { button.click(); return true; }
                }
                return false;
            }
            """
        )

    def wait_kernel_download_completed(
        self, major_version: str, version: str, timeout_seconds: int
    ) -> None:
        major = self._kernel_major(major_version)
        if not re.fullmatch(rf"{re.escape(major)}\.[0-9]+(?:\.[0-9]+)+", version):
            raise ValueError("下载版本不属于目标内核主版本")
        self.open_download_record_kernel_tab()
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for item in self._download_record_kernel_states():
                if item.get("version") != version:
                    continue
                if item.get("failed"):
                    raise AssertionError(f"内核下载失败: {version}")
                if item.get("deletable") and not item.get("busy"):
                    return
            time.sleep(0.5)
        raise TimeoutError(f"等待内核下载完成超时: {version}")

    def latest_kernel_version(self, major_version: str) -> str:
        # 从目标主版本分组的“最新为 Chrome ...”中提取完整版本。
        major_version = self._kernel_major(major_version)
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
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const activeTab = document.querySelector("#tab-basicSetting.is-active")
                || Array.from(document.querySelectorAll(".env-segmented-tabs__item.is-active, [role='tab'].is-active"))
                    .filter(visible)
                    .find((el) => clean(el.innerText || el.textContent) === "基础设置");
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

    def _personal_settings_tab_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const candidates = Array.from(document.querySelectorAll(
                ".env-segmented-tabs__item, #tab-basicSetting, [role='tab'], button"
            ))
                .filter((el) => visible(el) && clean(el.innerText || el.textContent) === expectedText)
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    return {{
                        el,
                        exactClass: String(el.className || "").includes("env-segmented-tabs__item") ? 0 : 1,
                        area: rect.width * rect.height,
                    }};
                }})
                .sort((left, right) => left.exactClass - right.exactClass || left.area - right.area);
            return candidates[0]?.el || null;
        }}
        """

    def _download_record_tab_script(self, texts: tuple[str, ...]) -> str:
        return f"""
        () => {{
            const root = document.querySelector("#DownloadLog");
            if (!root) return null;
            const expectedTexts = {list(texts)!r};
            return Array.from(root.querySelectorAll("p,span,button,div"))
                .find((el) => {{
                    const rect = el.getBoundingClientRect();
                    const text = (el.innerText || el.textContent || "").trim();
                    return rect.width > 0 && rect.height > 0
                        && expectedTexts.includes(text);
                }}) || null;
        }}
        """

    def _wait_for_download_record_kernel_tab(self) -> None:
        deadline = time.time() + timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            script = """
                () => {
                    const root = document.querySelector("#DownloadLog");
                    if (!root) return false;
                    const expectedTexts = __EXPECTED_TEXTS__;
                    const tab = Array.from(root.querySelectorAll("p,span,button,div"))
                        .find((el) => expectedTexts.includes((el.innerText || el.textContent || "").trim()));
                    return Boolean(tab && String(tab.className || "").includes("tw-text-black"));
                }
                """.replace("__EXPECTED_TEXTS__", repr(list(self.DOWNLOAD_RECORD_KERNEL_TAB_TEXTS)))
            active = self.cdp.evaluate(script)
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
        major_version = self._kernel_major(major_version)
        return f"""
        () => {{
            const section = document.querySelector("#CoreVersion");
            if (!section) return null;
            const expectedTitle = {f"{major_version} 版本"!r};
            const visible = (el) => {{
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const clean = value => String(value || '').replace(/\\s+/g, ' ').trim();
            const headings = Array.from(section.querySelectorAll('div,p,span,h3,h4'))
                .filter(el => visible(el) && clean(el.innerText || el.textContent) === expectedTitle);
            for (const heading of headings) {{
                let block = heading;
                while (block && block !== section) {{
                    const titles = Array.from(block.querySelectorAll('div,p,span,h3,h4'))
                        .filter(visible).map(el => clean(el.innerText || el.textContent))
                        .filter(text => /^[0-9]+ 版本$/.test(text));
                    // 不向上匹配包含其它主版本的容器，避免误点其它版本的下载。
                    if (titles.some(text => text !== expectedTitle)) break;
                    const button = Array.from(block.querySelectorAll('button,p,span'))
                        .find(el => visible(el) && !el.disabled && clean(el.innerText || el.textContent) === '下载');
                    if (button) return button;
                    block = block.parentElement;
                }}
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
