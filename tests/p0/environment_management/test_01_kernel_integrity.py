from __future__ import annotations

import os
import shutil
import unittest
from pathlib import Path
from typing import Callable, TypeVar

from core.assertions import assert_equal, assert_true
from core.app_config import resolve_app_config
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.kernel_cache import resolve_kernel_browsers_dir, wait_for_kernel_executable_dir, wait_for_kernel_version_dir
from core.kernel_process import kernel_version_from_cdp, kernel_version_from_command_line, resolve_kernel_runtime
from core.logger import setup_logger
from core.process import process_executable_path_by_pid, wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage
from pages.personal_settings_page import PersonalSettingsPage


CASE_MODULE = "环境管理"
KERNEL_142_PREFIX = "142"
KERNEL_134_PREFIX = "134"
KERNEL_134_DOWNLOAD_MAJOR = "134"
KERNEL_CACHE_SUBDIR = "browsers"
StageResult = TypeVar("StageResult")


class TestKernelIntegrity(unittest.TestCase):
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

    def test_142_kernel_integrity(self) -> None:
        data = self.config["test_data"]["kernel_integrity"]
        environment_name = str(data.get("environment_name", "142内核环境-4"))
        fallback_keyword = str(data.get("fallback_search_keyword", "142"))
        kernel_134_search_keyword = str(data.get("kernel_134_search_keyword", "134内核"))
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)
        kernel_download_timeout = timeout_seconds(self.config, "kernel_download_seconds", 300)
        failures: list[str] = []

        settings_page = PersonalSettingsPage(cdp_driver=self.cdp, config=self.config)
        settings_page.open_from_avatar()
        settings_page.open_basic_settings()
        cache_dir = settings_page.environment_cache_dir()
        browsers_dir = resolve_kernel_browsers_dir(cache_dir, KERNEL_CACHE_SUBDIR)
        self._run_validation_stage(
            failures,
            "清空内核缓存",
            lambda: self._clear_cache_subdir(cache_dir, KERNEL_CACHE_SUBDIR),
        )

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        try:
            self._run_validation_stage(
                failures,
                "首次打开并校验 142 内核",
                lambda: self._open_kernel_environment_from_list(
                    environment_page=environment_page,
                    search_keyword=fallback_keyword,
                    environment_name=environment_name,
                    expected_kernel_prefix=KERNEL_142_PREFIX,
                    environment_open_timeout=environment_open_timeout,
                    environment_close_timeout=environment_close_timeout,
                    kernel_process_timeout=kernel_process_timeout,
                    kernel_cdp_timeout=kernel_cdp_timeout,
                    kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                    http_probe_timeout=http_probe_timeout,
                ),
            )

            self._run_validation_stage(
                failures,
                "刷新 APP 登录状态",
                lambda: self._reload_and_restore_login(),
            )

            kernel_142_dir = self._run_validation_stage(
                failures,
                "等待 142 内核拷贝到缓存",
                lambda: wait_for_kernel_version_dir(
                    browsers_dir,
                    KERNEL_142_PREFIX,
                    timeout_seconds=kernel_download_timeout,
                ),
            )

            if kernel_142_dir is not None:
                self._run_validation_stage(
                    failures,
                    "使用缓存目录再次校验 142 内核",
                    lambda: self._open_kernel_environment_from_list(
                        environment_page=environment_page,
                        search_keyword=fallback_keyword,
                        environment_name=environment_name,
                        expected_kernel_prefix=KERNEL_142_PREFIX,
                        environment_open_timeout=environment_open_timeout,
                        environment_close_timeout=environment_close_timeout,
                        kernel_process_timeout=kernel_process_timeout,
                        kernel_cdp_timeout=kernel_cdp_timeout,
                        kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                        http_probe_timeout=http_probe_timeout,
                        expected_executable_parent=kernel_142_dir,
                    ),
                )

            self._run_validation_stage(
                failures,
                "触发 134 内核下载",
                lambda: self._download_kernel_134(settings_page),
            )

            self._run_validation_stage(
                failures,
                "等待 134 内核下载完成",
                lambda: wait_for_kernel_executable_dir(
                    browsers_dir,
                    KERNEL_134_PREFIX,
                    executable_name=resolve_app_config(self.config).browser_process_name,
                    timeout_seconds=kernel_download_timeout,
                ),
            )

            self._run_validation_stage(
                failures,
                "打开并校验 134 内核",
                lambda: self._open_first_matching_kernel_environment(
                    environment_page=environment_page,
                    search_keyword=kernel_134_search_keyword,
                    expected_kernel_prefix=KERNEL_134_PREFIX,
                    environment_open_timeout=environment_open_timeout,
                    environment_close_timeout=environment_close_timeout,
                    kernel_process_timeout=kernel_process_timeout,
                    kernel_cdp_timeout=kernel_cdp_timeout,
                    kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                    http_probe_timeout=http_probe_timeout,
                ),
            )
        finally:
            try:
                environment_page.clear_search()
            except Exception:
                pass
        assert_true(
            not failures,
            "kernel integrity validation failed:\n- " + "\n- ".join(failures),
        )

    def _run_validation_stage(
        self,
        failures: list[str],
        stage_name: str,
        action: Callable[[], StageResult],
    ) -> StageResult | None:
        try:
            return action()
        except Exception as exc:
            message = f"{stage_name}: {type(exc).__name__}: {exc}"
            failures.append(message)
            self.logger.exception("Kernel integrity stage failed: %s", stage_name)
            return None

    def _reload_and_restore_login(self) -> None:
        self.cdp.reload()
        LoginPage(cdp_driver=self.cdp, config=self.config).ensure_logged_in_as_config_account()

    def _download_kernel_134(self, settings_page: PersonalSettingsPage) -> None:
        settings_page.open_from_avatar()
        settings_page.open_basic_settings()
        settings_page.delete_download_record_kernels_except_first()
        settings_page.download_latest_kernel(KERNEL_134_DOWNLOAD_MAJOR)

    def _open_kernel_environment_from_list(
        self,
        *,
        environment_page: EnvironmentPage,
        search_keyword: str,
        environment_name: str,
        expected_kernel_prefix: str,
        environment_open_timeout: int,
        environment_close_timeout: int,
        kernel_process_timeout: int,
        kernel_cdp_timeout: int,
        kernel_cdp_probe_timeout: int,
        http_probe_timeout: int,
        expected_executable_parent: Path | None = None,
    ) -> None:
        environment_page.open_list()
        if environment_page.first_environment_name() != environment_name:
            environment_page.search_environment(search_keyword)
        self._open_environment_assert_kernel_and_close(
            environment_page=environment_page,
            environment_name=environment_name,
            expected_kernel_prefix=expected_kernel_prefix,
            environment_open_timeout=environment_open_timeout,
            environment_close_timeout=environment_close_timeout,
            kernel_process_timeout=kernel_process_timeout,
            kernel_cdp_timeout=kernel_cdp_timeout,
            kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
            http_probe_timeout=http_probe_timeout,
            expected_executable_parent=expected_executable_parent,
        )

    def _open_first_matching_kernel_environment(
        self,
        *,
        environment_page: EnvironmentPage,
        search_keyword: str,
        expected_kernel_prefix: str,
        environment_open_timeout: int,
        environment_close_timeout: int,
        kernel_process_timeout: int,
        kernel_cdp_timeout: int,
        kernel_cdp_probe_timeout: int,
        http_probe_timeout: int,
    ) -> None:
        environment_page.open_list()
        environment_page.search_environment(search_keyword)
        environment_name = environment_page.first_environment_name()
        self._open_environment_assert_kernel_and_close(
            environment_page=environment_page,
            environment_name=environment_name,
            expected_kernel_prefix=expected_kernel_prefix,
            environment_open_timeout=environment_open_timeout,
            environment_close_timeout=environment_close_timeout,
            kernel_process_timeout=kernel_process_timeout,
            kernel_cdp_timeout=kernel_cdp_timeout,
            kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
            http_probe_timeout=http_probe_timeout,
        )

    def _open_environment_assert_kernel_and_close(
        self,
        environment_page: EnvironmentPage,
        environment_name: str,
        expected_kernel_prefix: str,
        environment_open_timeout: int,
        environment_close_timeout: int,
        kernel_process_timeout: int,
        kernel_cdp_timeout: int,
        kernel_cdp_probe_timeout: int,
        http_probe_timeout: int,
        expected_executable_parent: Path | None = None,
    ) -> None:
        if environment_page.environment_action_text(environment_name) == "关闭":
            environment_page.click_environment_action(environment_name, "关闭")
            environment_page.wait_environment_action_text(
                environment_name,
                "打开",
                timeout_seconds=environment_close_timeout,
            )

        assert_equal(
            environment_page.environment_action_text(environment_name),
            "打开",
            f"environment is not ready to open: {environment_name}",
        )
        kernel_pid = 0
        environment_opened = False
        try:
            kernel_pid = environment_page.open_environment_and_capture_pid(environment_name)
            assert_true(
                wait_for_pid_running(kernel_pid, timeout_seconds=kernel_process_timeout),
                f"kernel process did not start: pid={kernel_pid}",
            )
            environment_page.wait_environment_action_text(
                environment_name,
                "关闭",
                timeout_seconds=environment_open_timeout,
            )
            environment_opened = True

            kernel_runtime = resolve_kernel_runtime(
                environment_name,
                kernel_pid,
                timeout_seconds=kernel_cdp_timeout,
                probe_timeout_seconds=kernel_cdp_probe_timeout,
                http_timeout_seconds=http_probe_timeout,
            )
            kernel_version = kernel_version_from_cdp(kernel_runtime.cdp_port, timeout_seconds=http_probe_timeout)
            if not kernel_version:
                kernel_version = kernel_version_from_command_line(kernel_runtime.command_line)
            assert_true(
                kernel_version.startswith(expected_kernel_prefix),
                f"kernel version should start with {expected_kernel_prefix}, actual={kernel_version}",
            )
            if expected_executable_parent:
                executable_path = process_executable_path_by_pid(kernel_pid)
                assert_true(
                    self._path_is_under(executable_path, expected_executable_parent),
                    "kernel executable path is not under expected cache dir: "
                    f"pid={kernel_pid}, executable={executable_path}, expected_parent={expected_executable_parent}",
                )
        finally:
            if environment_opened and environment_page.environment_action_text(environment_name) == "关闭":
                environment_page.click_environment_action(environment_name, "关闭")
                if kernel_pid:
                    assert_true(
                        wait_for_pid_stopped(kernel_pid, timeout_seconds=kernel_process_timeout),
                        f"kernel process did not stop: pid={kernel_pid}",
                    )
                environment_page.wait_environment_action_text(
                    environment_name,
                    "打开",
                    timeout_seconds=environment_close_timeout,
                )

    def _clear_cache_subdir(self, cache_dir: Path, subdir_name: str) -> Path:
        target_dir = resolve_kernel_browsers_dir(cache_dir, subdir_name)
        if target_dir.name.lower() != "browsers":
            raise AssertionError(f"refuse to clear unexpected cache subdir: {target_dir}")
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in target_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        remaining_items = list(target_dir.iterdir())
        if remaining_items:
            remaining_text = ", ".join(str(item) for item in remaining_items[:10])
            raise AssertionError(f"cache subdir was not cleared: {target_dir}; remaining={remaining_text}")
        return target_dir

    def _path_is_under(self, child: str, parent: Path) -> bool:
        if not child:
            return False
        normalized_child = os.path.normcase(os.path.abspath(child))
        normalized_parent = os.path.normcase(os.path.abspath(str(parent)))
        return normalized_child == normalized_parent or normalized_child.startswith(normalized_parent + os.sep)


if __name__ == "__main__":
    unittest.main()
