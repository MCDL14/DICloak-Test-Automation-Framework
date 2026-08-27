from __future__ import annotations

import json
import os
import shutil
import stat
import time
import unittest
from pathlib import Path

from core.app_config import resolve_app_config
from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.logger import setup_logger
from core.process import main_process_ids, wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.global_settings_page import GlobalSettingsPage
from pages.login_page import LoginPage
from pages.personal_settings_page import PersonalSettingsPage


CASE_MODULE = "全局设置"
ENVIRONMENT_SEARCH_KEYWORD = "142内核环境"
EXTENSION_RELATIVE_DIR = Path("expansion") / "hlkenndednhfkekhgcdicdfddnkalmdm"
MANIFEST_FILE_NAME = "manifest.json"
EXPECTED_FAILURE_TEXT = "检测到扩展有异常"
MAX_OPEN_RETRIES = 3


class TestGlobalSettingsExtensionTamperProtection(unittest.TestCase):
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

    def test_enable_extension_encryption_and_tamper_protection(self) -> None:
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        browser_process_name = resolve_app_config(self.config).browser_process_name

        global_settings_page = GlobalSettingsPage(cdp_driver=self.cdp, config=self.config)
        global_settings_page.prepare_api_recovery(
            affected_blocks={"browser_config"},
            bitmask_blocks={"browser_config"},
        )
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        personal_settings_page = PersonalSettingsPage(cdp_driver=self.cdp, config=self.config)

        global_extension_tamper_reset = False
        environment_name = ""
        opened_kernel_pid = 0
        original_manifest_bytes: bytes | None = None
        manifest_path: Path | None = None

        try:
            global_settings_page.open(force_reentry=True)
            global_settings_page.ensure_extension_tamper_protection_enabled()

            environment_page.open_list()
            environment_page.search_environment(self._environment_search_keyword())
            environment_name = environment_page.first_environment_name()
            assert_true(bool(environment_name), "142 内核环境筛选结果为空")
            self._close_environment_if_open(
                environment_page,
                environment_name,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
            )

            opened_kernel_pid = environment_page.open_environment_and_capture_pid(environment_name)
            assert_true(
                wait_for_pid_running(opened_kernel_pid, timeout_seconds=kernel_process_timeout),
                f"开启扩展防篡改后首次打开 142 内核环境失败: pid={opened_kernel_pid}",
            )
            environment_page.wait_environment_action_text(
                environment_name,
                "关闭",
                timeout_seconds=environment_open_timeout,
            )
            self._close_environment_if_open(
                environment_page,
                environment_name,
                environment_close_timeout=environment_close_timeout,
                kernel_pid=opened_kernel_pid,
                kernel_process_timeout=kernel_process_timeout,
            )
            opened_kernel_pid = 0
            assert_equal(
                environment_page.environment_action_text(environment_name),
                "打开",
                f"首次关闭环境后按钮未恢复为打开: {environment_name}",
            )

            personal_settings_page.open_from_avatar()
            personal_settings_page.open_basic_settings()
            cache_dir = personal_settings_page.environment_cache_dir()
            extension_dir = self._extension_dir(cache_dir)
            manifest_path = extension_dir / MANIFEST_FILE_NAME
            original_manifest_bytes = self._tamper_manifest_update_url(manifest_path)

            environment_page.open_list()
            environment_page.search_environment(self._environment_search_keyword())
            failure_text = self._open_until_failure_dialog(
                environment_page,
                environment_name,
                browser_process_name=browser_process_name,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
            )
            assert_true(
                EXPECTED_FAILURE_TEXT in failure_text,
                f"打开环境失败弹窗未包含预期文案: expected={EXPECTED_FAILURE_TEXT}, actual={failure_text}",
            )
            environment_page.close_open_environment_failure_dialog()

            self._delete_extension_dir(extension_dir, cache_dir)
            opened_kernel_pid = self._open_until_kernel_process(
                environment_page,
                environment_name,
                browser_process_name=browser_process_name,
            )
            if opened_kernel_pid:
                assert_true(
                    wait_for_pid_running(opened_kernel_pid, timeout_seconds=kernel_process_timeout),
                    f"删除异常扩展目录后内核进程未保持运行: pid={opened_kernel_pid}",
                )
            environment_page.wait_environment_action_text(
                environment_name,
                "关闭",
                timeout_seconds=environment_open_timeout,
            )
            self._close_environment_if_open(
                environment_page,
                environment_name,
                environment_close_timeout=environment_close_timeout,
                kernel_pid=opened_kernel_pid,
                kernel_process_timeout=kernel_process_timeout,
            )
            opened_kernel_pid = 0
            assert_equal(
                environment_page.environment_action_text(environment_name),
                "打开",
                f"删除异常扩展目录后关闭环境按钮未恢复为打开: {environment_name}",
            )

            environment_page.clear_search()
            global_settings_page.restore_api_recovery_if_needed()
            global_extension_tamper_reset = True
        finally:
            try:
                if manifest_path and original_manifest_bytes and manifest_path.exists():
                    manifest_path.write_bytes(original_manifest_bytes)
            except Exception:
                self.logger.exception("failed to restore tampered extension manifest")
            try:
                if environment_name:
                    environment_page.open_list()
                    environment_page.search_environment(self._environment_search_keyword())
                    self._close_environment_if_open(
                        environment_page,
                        environment_name,
                        environment_close_timeout=environment_close_timeout,
                        kernel_pid=opened_kernel_pid,
                        kernel_process_timeout=kernel_process_timeout,
                    )
            except Exception:
                pass
            try:
                if environment_page.open_environment_failure_dialog_visible():
                    environment_page.close_open_environment_failure_dialog()
            except Exception:
                pass
            try:
                environment_page.clear_search()
            except Exception:
                pass
            if not global_extension_tamper_reset:
                try:
                    global_settings_page.restore_api_recovery_if_needed()
                except Exception:
                    self.logger.exception("failed to disable global extension tamper protection")

    def _environment_search_keyword(self) -> str:
        data = self.config.get("test_data", {})
        if isinstance(data, dict):
            extension_data = data.get("extension_tamper_protection", {})
            if isinstance(extension_data, dict) and str(extension_data.get("environment_search_keyword", "")).strip():
                return str(extension_data["environment_search_keyword"]).strip()
        return ENVIRONMENT_SEARCH_KEYWORD

    def _tamper_manifest_update_url(self, manifest_path: Path) -> bytes:
        assert_true(manifest_path.exists(), f"扩展 manifest 文件不存在: {manifest_path}")
        original = manifest_path.read_bytes()
        data = json.loads(original.decode("utf-8-sig"))
        update_url = str(data.get("update_url", ""))
        assert_true(bool(update_url), f"manifest 中 update_url 字段为空或不存在: {manifest_path}")
        data["update_url"] = update_url + " "
        manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert_equal(
            saved.get("update_url"),
            update_url + " ",
            f"manifest update_url 字段篡改未保存成功: {manifest_path}",
        )
        return original

    def _delete_extension_dir(self, extension_dir: Path, cache_dir: Path) -> None:
        cache_root = self._safe_existing_directory(cache_dir, "环境缓存根目录")
        target = self._safe_existing_directory(extension_dir, "扩展缓存目录")
        expected_target = cache_root / EXTENSION_RELATIVE_DIR

        assert_true(target != cache_root, f"拒绝删除缓存根目录本身: {target}")
        assert_true(
            self._path_is_under(target, cache_root),
            f"拒绝删除非缓存目录下的扩展目录: target={target}, cache_dir={cache_root}",
        )
        assert_equal(
            target,
            expected_target,
            f"扩展缓存目录不是本用例允许删除的固定目录: target={target}, expected={expected_target}",
        )
        shutil.rmtree(target)
        assert_true(not target.exists(), f"扩展缓存目录删除失败: {target}")

    def _extension_dir(self, cache_dir: Path) -> Path:
        cache_root = self._safe_existing_directory(cache_dir, "环境缓存根目录")
        extension_dir = cache_root / EXTENSION_RELATIVE_DIR
        assert_true(
            self._path_is_under(extension_dir, cache_root),
            f"扩展目录不在缓存目录下: target={extension_dir}, cache_dir={cache_root}",
        )
        return extension_dir

    def _open_until_failure_dialog(
        self,
        environment_page: EnvironmentPage,
        environment_name: str,
        *,
        browser_process_name: str,
        environment_close_timeout: int,
        kernel_process_timeout: int,
    ) -> str:
        last_outcome = ""
        for attempt in range(1, MAX_OPEN_RETRIES + 1):
            existing_pids = set(main_process_ids(browser_process_name))
            environment_page.click_environment_action(environment_name, "打开")
            outcome, pid = self._wait_for_failure_dialog_or_kernel(
                environment_page,
                environment_name,
                browser_process_name=browser_process_name,
                existing_pids=existing_pids,
            )
            last_outcome = outcome
            if outcome == "failure_dialog":
                return environment_page.open_environment_failure_dialog_text()
            if outcome == "kernel":
                self._close_environment_if_open(
                    environment_page,
                    environment_name,
                    environment_close_timeout=environment_close_timeout,
                    kernel_pid=pid,
                    kernel_process_timeout=kernel_process_timeout,
                )
                raise AssertionError(
                    "篡改扩展 manifest 后环境仍然打开成功: "
                    f"environment={environment_name}, pid={pid}, attempt={attempt}"
                )
        raise AssertionError(
            "篡改扩展 manifest 后连续三次打开均未出现失败弹窗，也未检测到内核进程: "
            f"environment={environment_name}, last_outcome={last_outcome}"
        )

    def _open_until_kernel_process(
        self,
        environment_page: EnvironmentPage,
        environment_name: str,
        *,
        browser_process_name: str,
    ) -> int:
        last_outcome = ""
        for _ in range(1, MAX_OPEN_RETRIES + 1):
            existing_pids = set(main_process_ids(browser_process_name))
            environment_page.click_environment_action(environment_name, "打开")
            outcome, pid = self._wait_for_failure_dialog_or_kernel(
                environment_page,
                environment_name,
                browser_process_name=browser_process_name,
                existing_pids=existing_pids,
            )
            last_outcome = outcome
            if outcome == "kernel":
                return pid
            if outcome == "failure_dialog":
                text = environment_page.open_environment_failure_dialog_text()
                environment_page.close_open_environment_failure_dialog()
                raise AssertionError(f"删除异常扩展目录后仍出现打开失败弹窗: {text}")
        raise AssertionError(
            "删除异常扩展目录后连续三次打开均未检测到内核进程，也未出现失败弹窗: "
            f"environment={environment_name}, last_outcome={last_outcome}"
        )

    def _wait_for_failure_dialog_or_kernel(
        self,
        environment_page: EnvironmentPage,
        environment_name: str,
        *,
        browser_process_name: str,
        existing_pids: set[int],
    ) -> tuple[str, int]:
        deadline = time.time() + timeout_seconds(self.config, "environment_open_seconds", 90)
        while time.time() < deadline:
            if environment_page.open_environment_failure_dialog_visible():
                return "failure_dialog", 0
            new_pids = [pid for pid in main_process_ids(browser_process_name) if pid not in existing_pids]
            if new_pids:
                return "kernel", new_pids[0]
            try:
                if environment_page.environment_action_text(environment_name) == "关闭":
                    return "kernel", 0
            except Exception:
                pass
            time.sleep(0.5)
        return "none", 0

    def _close_environment_if_open(
        self,
        environment_page: EnvironmentPage,
        environment_name: str,
        *,
        environment_close_timeout: int,
        kernel_pid: int = 0,
        kernel_process_timeout: int,
    ) -> None:
        if not environment_name or not environment_page.environment_visible_in_current_list(environment_name):
            return
        if environment_page.environment_action_text(environment_name) != "关闭":
            return
        environment_page.click_environment_action(environment_name, "关闭")
        if kernel_pid:
            assert_true(
                wait_for_pid_stopped(kernel_pid, timeout_seconds=kernel_process_timeout),
                f"关闭环境后内核进程未退出: pid={kernel_pid}",
            )
        environment_page.wait_environment_action_text(
            environment_name,
            "打开",
            timeout_seconds=environment_close_timeout,
        )

    def _path_is_under(self, child: Path, parent: Path) -> bool:
        normalized_child = os.path.normcase(os.path.abspath(str(child)))
        normalized_parent = os.path.normcase(os.path.abspath(str(parent)))
        return normalized_child == normalized_parent or normalized_child.startswith(normalized_parent + os.sep)

    def _safe_existing_directory(self, path: Path, label: str) -> Path:
        assert_true(path.is_absolute(), f"{label} 必须是绝对路径: {path}")
        assert_true(path.exists(), f"{label} 不存在: {path}")
        assert_true(path.is_dir(), f"{label} 不是目录: {path}")
        assert_true(not path.is_symlink(), f"{label} 不能是符号链接: {path}")
        assert_true(not self._is_reparse_point(path), f"{label} 不能是重解析点: {path}")
        resolved = path.resolve(strict=True)
        assert_true(resolved.anchor != str(resolved), f"{label} 不能是磁盘根目录: {resolved}")
        return resolved

    def _is_reparse_point(self, path: Path) -> bool:
        try:
            attributes = getattr(path.stat(), "st_file_attributes", 0)
        except OSError:
            return False
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


if __name__ == "__main__":
    unittest.main()
