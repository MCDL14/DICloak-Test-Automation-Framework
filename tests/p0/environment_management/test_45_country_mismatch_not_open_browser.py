from __future__ import annotations

import os
import signal
import subprocess
import unittest
from pathlib import Path

from core.app_config import resolve_app_config
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from core.platform.detect import is_windows
from core.process import main_process_ids, wait_for_process_stopped
from pages.environment_page import EnvironmentPage
from pages.global_settings_page import GlobalSettingsPage
from pages.login_page import LoginPage

try:
    import psutil
except ImportError:
    psutil = None


CASE_MODULE = "环境管理"
ENVIRONMENT_NAME = "国家不一致，不打开环境"
EXPECTED_FAILURE_TEXT = "不一致"
FAILURE_DIALOG_TIMEOUT_SECONDS = 30
MAX_OPEN_ATTEMPTS = 3
PROCESS_STOP_TIMEOUT_SECONDS = 15


class TestCountryMismatchNotOpenBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(Path("config/config.yaml"))
        cls.logger = setup_logger(cls.config)
        cls.cdp = CDPDriver(cls.config, cls.logger)
        cls.cdp.connect()
        LoginPage(cdp_driver=cls.cdp, config=cls.config).ensure_logged_in_as_config_account()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cdp.close()

    def test_country_mismatch_not_open_browser(self) -> None:
        browser_process_name = resolve_app_config(self.config).browser_process_name.strip()
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        delayed_assertion: AssertionError | None = None
        cleanup_error: Exception | None = None

        try:
            global_settings_page.open(force_reentry=True)
            global_settings_page.ensure_country_mismatch_block_open_enabled()
            if not global_settings_page.country_mismatch_block_open_enabled():
                raise RuntimeError("国家/地区与上一次打开时不一致，不打开浏览器 未保持勾选状态")

            environment_page.open_list()
            environment_page.search_environment_without_assert(ENVIRONMENT_NAME)
            if not environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME):
                raise RuntimeError(f"未找到目标环境: {ENVIRONMENT_NAME}")
            action_text = environment_page.environment_action_text(ENVIRONMENT_NAME)
            if action_text != "打开":
                raise RuntimeError(f"目标环境未处于已关闭/可打开状态: action={action_text!r}")

            self._open_until_failure_dialog(environment_page, browser_process_name)
            failure_text = environment_page.wait_open_environment_failure_dialog_text_contains(
                EXPECTED_FAILURE_TEXT,
                timeout_seconds=FAILURE_DIALOG_TIMEOUT_SECONDS,
            )
            if EXPECTED_FAILURE_TEXT not in failure_text:
                delayed_assertion = AssertionError(
                    "业务弹窗未包含预期文案: "
                    f"expected={EXPECTED_FAILURE_TEXT}, actual={failure_text}"
                )
        finally:
            try:
                if environment_page.open_environment_failure_dialog_visible():
                    environment_page.close_open_environment_failure_dialog()
            except Exception as exc:
                cleanup_error = cleanup_error or exc
                self.logger.warning("close business dialog failed: %s", exc)
            try:
                environment_page.open_list()
                if environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME):
                    action_text = environment_page.environment_action_text(ENVIRONMENT_NAME)
                    if action_text != "打开":
                        cleanup_error = cleanup_error or RuntimeError(
                            f"目标环境状态未保持已关闭/可打开: action={action_text!r}"
                        )
                environment_page.clear_search()
            except Exception as exc:
                cleanup_error = cleanup_error or exc
                self.logger.warning("clear environment search failed: %s", exc)
            try:
                global_settings_page.open(force_reentry=True)
                global_settings_page.ensure_country_mismatch_block_open_disabled()
            except Exception as exc:
                cleanup_error = cleanup_error or exc
                self.logger.warning("disable country mismatch blocking setting failed: %s", exc)

        if delayed_assertion is not None:
            if cleanup_error is not None:
                delayed_assertion.add_note(f"cleanup also failed: {cleanup_error}")
            raise delayed_assertion
        if cleanup_error is not None:
            raise cleanup_error

    def _open_until_failure_dialog(
        self,
        environment_page: EnvironmentPage,
        browser_process_name: str,
    ) -> None:
        for attempt in range(1, MAX_OPEN_ATTEMPTS + 1):
            environment_page.click_environment_action(ENVIRONMENT_NAME, "打开")
            if environment_page.wait_open_environment_failure_dialog(
                timeout_seconds=FAILURE_DIALOG_TIMEOUT_SECONDS
            ):
                return

            browser_pids = set(main_process_ids(browser_process_name))
            if browser_pids:
                self._terminate_browser_processes(browser_process_name, browser_pids)
                raise AssertionError(
                    "国家/地区不一致时不应启动浏览器进程: "
                    f"process={browser_process_name}, pids={sorted(browser_pids)}"
                )

            action_text = environment_page.environment_action_text(ENVIRONMENT_NAME)
            if action_text == "关闭":
                raise AssertionError(
                    f"未出现业务弹窗时环境按钮变为关闭: {ENVIRONMENT_NAME}"
                )
            if action_text != "打开":
                raise RuntimeError(
                    "业务弹窗未出现，且环境按钮状态异常: "
                    f"attempt={attempt}, action={action_text!r}"
                )

        raise RuntimeError(
            "Blocked/Error: 连续点击 3 次仍未出现业务弹窗，"
            "未检测到浏览器进程，且环境按钮仍为打开"
        )

    def _terminate_browser_processes(self, process_name: str, pids: set[int]) -> None:
        if is_windows():
            for pid in sorted(pids):
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    text=True,
                    encoding="mbcs",
                    errors="ignore",
                    timeout=10,
                    check=False,
                )
            if not wait_for_process_stopped(process_name, timeout_seconds=PROCESS_STOP_TIMEOUT_SECONDS):
                subprocess.run(
                    ["taskkill", "/F", "/T", "/IM", process_name],
                    capture_output=True,
                    text=True,
                    encoding="mbcs",
                    errors="ignore",
                    timeout=10,
                    check=False,
                )
            return

        if psutil is not None:
            targets = []
            for pid in sorted(pids):
                try:
                    process = psutil.Process(pid)
                    targets.extend(process.children(recursive=True))
                    targets.append(process)
                except (psutil.Error, OSError):
                    continue
            for process in targets:
                try:
                    process.terminate()
                except (psutil.Error, OSError):
                    pass
            _, alive = psutil.wait_procs(targets, timeout=PROCESS_STOP_TIMEOUT_SECONDS)
            for process in alive:
                try:
                    process.kill()
                except (psutil.Error, OSError):
                    pass
            return

        for pid in sorted(pids):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
