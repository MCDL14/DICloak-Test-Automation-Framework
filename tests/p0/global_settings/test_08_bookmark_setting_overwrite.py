from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, require_value, timeout_seconds
from core.kernel_cdp import create_kernel_bookmark_and_verify, verify_kernel_bookmarks
from core.kernel_process import resolve_kernel_runtime
from core.logger import setup_logger
from core.process import wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.global_settings_page import GlobalSettingsPage
from pages.login_page import LoginPage


CASE_MODULE = "全局设置"

ENVIRONMENT_SEARCH_KEYWORD = "142"
TEMP_BOOKMARK_NAME = "淘宝"
TEMP_BOOKMARK_URL = "https://www.taobao.com/"


class TestBookmarkSettingOverwrite(unittest.TestCase):
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

    def test_bookmark_setting_overwrite(self) -> None:
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)

        bookmark_file = self._bookmark_overwrite_file()
        expected_bookmark_names = self._bookmark_overwrite_names()

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        environment_name = ""
        kernel_pid = 0
        environment_opened = False
        bookmark_setting_saved = False
        cleanup_error: Exception | None = None

        try:
            environment_page.open_list()
            environment_page.search_environment(ENVIRONMENT_SEARCH_KEYWORD)
            environment_name = environment_page.environment_name_at_position(1)
            assert_true(
                bool(environment_name),
                f"first environment was not found by keyword: {ENVIRONMENT_SEARCH_KEYWORD}",
            )

            self._close_environment_if_open(
                environment_page,
                environment_name,
                timeout_seconds=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
            )

            kernel_pid = environment_page.open_environment_and_capture_pid(environment_name)
            environment_opened = True
            assert_true(
                wait_for_pid_running(kernel_pid, timeout_seconds=kernel_process_timeout),
                f"kernel process did not start before creating temporary bookmark: pid={kernel_pid}",
            )
            environment_page.wait_environment_action_text(
                environment_name,
                "关闭",
                timeout_seconds=environment_open_timeout,
            )

            kernel_runtime = resolve_kernel_runtime(
                environment_name,
                kernel_pid,
                timeout_seconds=kernel_cdp_timeout,
                probe_timeout_seconds=kernel_cdp_probe_timeout,
                http_timeout_seconds=http_probe_timeout,
            )
            created_bookmark = create_kernel_bookmark_and_verify(
                kernel_runtime.cdp_port,
                name=TEMP_BOOKMARK_NAME,
                url=TEMP_BOOKMARK_URL,
                timeout_seconds=30,
                http_timeout_seconds=http_probe_timeout,
            )
            assert_true(
                created_bookmark.expected_present,
                "temporary bookmark was not created before overwrite verification: "
                f"expected={TEMP_BOOKMARK_NAME}, evidence={created_bookmark.evidence}",
            )

            self._close_environment_if_open(
                environment_page,
                environment_name,
                timeout_seconds=environment_close_timeout,
                kernel_pid=kernel_pid,
                kernel_process_timeout=kernel_process_timeout,
            )
            environment_opened = False
            kernel_pid = 0
            assert_true(
                environment_page.environment_action_text(environment_name) == "打开",
                f"environment action text was not restored to open after creating bookmark: {environment_name}",
            )

            global_settings_page.open()
            global_settings_page.configure_bookmark_overwrite(bookmark_file)
            bookmark_setting_saved = True

            environment_page.open_list()
            environment_page.search_environment(ENVIRONMENT_SEARCH_KEYWORD)
            assert_true(
                environment_page.environment_visible_in_current_list(environment_name),
                f"environment was not found after returning from global settings: {environment_name}",
            )

            kernel_pid = environment_page.open_environment_and_capture_pid(environment_name)
            environment_opened = True
            assert_true(
                wait_for_pid_running(kernel_pid, timeout_seconds=kernel_process_timeout),
                f"kernel process did not start after bookmark overwrite was configured: pid={kernel_pid}",
            )
            environment_page.wait_environment_action_text(
                environment_name,
                "关闭",
                timeout_seconds=environment_open_timeout,
            )

            kernel_runtime = resolve_kernel_runtime(
                environment_name,
                kernel_pid,
                timeout_seconds=kernel_cdp_timeout,
                probe_timeout_seconds=kernel_cdp_probe_timeout,
                http_timeout_seconds=http_probe_timeout,
            )
            overwritten_bookmarks = verify_kernel_bookmarks(
                kernel_runtime.cdp_port,
                expected_names=expected_bookmark_names,
                forbidden_names=[TEMP_BOOKMARK_NAME],
                timeout_seconds=45,
                http_timeout_seconds=http_probe_timeout,
            )
            assert_true(
                overwritten_bookmarks.expected_present,
                "uploaded bookmark file content was not found after overwrite: "
                f"expected={expected_bookmark_names}, actual={overwritten_bookmarks.names}, "
                f"evidence={overwritten_bookmarks.evidence}",
            )
            assert_true(
                overwritten_bookmarks.forbidden_absent,
                "temporary bookmark still exists after overwrite: "
                f"forbidden={TEMP_BOOKMARK_NAME}, actual={overwritten_bookmarks.names}, "
                f"evidence={overwritten_bookmarks.evidence}",
            )

            self._close_environment_if_open(
                environment_page,
                environment_name,
                timeout_seconds=environment_close_timeout,
                kernel_pid=kernel_pid,
                kernel_process_timeout=kernel_process_timeout,
            )
            environment_opened = False
            kernel_pid = 0
            assert_true(
                environment_page.environment_action_text(environment_name) == "打开",
                f"environment action text was not restored to open after overwrite verification: {environment_name}",
            )
        finally:
            try:
                if environment_opened and environment_name:
                    self._close_environment_if_open(
                        environment_page,
                        environment_name,
                        timeout_seconds=environment_close_timeout,
                        kernel_pid=kernel_pid,
                        kernel_process_timeout=kernel_process_timeout,
                    )
            except Exception:
                pass
            try:
                environment_page.clear_search()
            except Exception:
                pass
            try:
                if bookmark_setting_saved:
                    global_settings_page.open()
                    global_settings_page.disable_bookmark_setting()
                    global_settings_page.open()
                    global_settings_page._wait_global_setting_states_stable()
                    assert_true(
                        not global_settings_page.bookmark_setting_enabled(),
                        "书签设置功能开关在用例清理后仍未关闭",
                    )
                else:
                    self.cdp.reload()
            except Exception as exc:
                cleanup_error = cleanup_error or exc
            try:
                environment_page.open_list()
            except Exception:
                pass
            if cleanup_error:
                raise cleanup_error

    def _bookmark_overwrite_file(self) -> Path:
        storage_dir = str(require_value(self.config, "test_data.bookmark.storage_dir")).strip()
        file_name = str(require_value(self.config, "test_data.bookmark.overwrite_file_name")).strip()
        path = self._resolve_project_path(storage_dir).joinpath(file_name)
        assert_true(path.is_file(), f"bookmark overwrite file does not exist: {path}")
        return path

    def _bookmark_overwrite_names(self) -> list[str]:
        rows = require_value(self.config, "test_data.bookmark.overwrite_rows")
        if not isinstance(rows, list):
            raise AssertionError("test_data.bookmark.overwrite_rows must be a list")

        names: list[str] = []
        for row in rows:
            name = self._bookmark_row_name(row)
            if name:
                names.append(name)

        assert_true(bool(names), "test_data.bookmark.overwrite_rows must contain at least one bookmark name")
        return names

    def _bookmark_row_name(self, row: Any) -> str:
        if isinstance(row, dict):
            for key in ("name", "title", "名称", "书签名称"):
                value = str(row.get(key, "")).strip()
                if value:
                    return value
            return ""
        return str(row or "").strip()

    def _resolve_project_path(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path
        return Path(str(self.config.get("_project_root", Path.cwd()))).joinpath(path).resolve()

    def _close_environment_if_open(
        self,
        environment_page: EnvironmentPage,
        environment_name: str,
        timeout_seconds: int,
        kernel_pid: int = 0,
        kernel_process_timeout: int = 90,
    ) -> None:
        if not environment_name:
            return
        if not environment_page.environment_visible_in_current_list(environment_name):
            return
        if environment_page.environment_action_text(environment_name) != "关闭":
            return
        environment_page.click_environment_action(environment_name, "关闭")
        if kernel_pid:
            wait_for_pid_stopped(kernel_pid, timeout_seconds=kernel_process_timeout)
        environment_page.wait_environment_action_text(
            environment_name,
            "打开",
            timeout_seconds=timeout_seconds,
        )


if __name__ == "__main__":
    unittest.main()
