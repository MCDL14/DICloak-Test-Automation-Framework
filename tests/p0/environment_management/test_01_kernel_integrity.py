from __future__ import annotations

import os
import shutil
import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.kernel_cache import wait_for_kernel_executable_dir, wait_for_kernel_version_dir
from core.kernel_process import kernel_version_from_cdp, kernel_version_from_command_line, resolve_kernel_runtime
from core.logger import setup_logger
from core.process import process_executable_path_by_pid, wait_for_pid_running, wait_for_pid_stopped
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage
from pages.personal_settings_page import PersonalSettingsPage


CASE_MODULE = "环境管理"


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
        expected_kernel_prefix = str(data.get("expected_kernel_prefix", "142"))
        expected_134_kernel_prefix = str(data.get("expected_134_kernel_prefix", "134"))
        kernel_134_search_keyword = str(data.get("kernel_134_search_keyword", "134内核"))
        kernel_134_download_major = str(data.get("kernel_134_download_major", "134"))
        cache_subdir_name = str(data.get("cache_subdir_name", "browsers"))
        browser_process_name = str(data.get("browser_process_name", "GinsBrowser.exe"))
        environment_open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        environment_close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        kernel_process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        kernel_cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        kernel_cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)
        kernel_download_timeout = timeout_seconds(self.config, "kernel_download_seconds", 300)

        settings_page = PersonalSettingsPage(cdp_driver=self.cdp, config=self.config)
        settings_page.open_from_avatar()
        settings_page.open_basic_settings()
        cache_dir = settings_page.environment_cache_dir()
        browsers_dir = self._clear_cache_subdir(cache_dir, cache_subdir_name)

        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        try:
            environment_page.open_list()
            if environment_page.first_environment_name() != environment_name:
                environment_page.search_environment(fallback_keyword)

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

            self.cdp.reload()
            LoginPage(cdp_driver=self.cdp, config=self.config).ensure_logged_in_as_config_account()

            kernel_142_dir = wait_for_kernel_version_dir(
                browsers_dir,
                expected_kernel_prefix,
                timeout_seconds=kernel_download_timeout,
            )

            environment_page.open_list()
            environment_page.search_environment(fallback_keyword)
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
                expected_executable_parent=kernel_142_dir,
            )

            settings_page.open_from_avatar()
            settings_page.open_basic_settings()
            settings_page.delete_download_record_kernels_except_first()
            settings_page.download_latest_kernel(kernel_134_download_major)
            wait_for_kernel_executable_dir(
                browsers_dir,
                expected_134_kernel_prefix,
                executable_name=browser_process_name,
                timeout_seconds=kernel_download_timeout,
            )

            environment_page.open_list()
            environment_page.search_environment(kernel_134_search_keyword)
            environment_134_name = environment_page.first_environment_name()
            self._open_environment_assert_kernel_and_close(
                environment_page=environment_page,
                environment_name=environment_134_name,
                expected_kernel_prefix=expected_134_kernel_prefix,
                environment_open_timeout=environment_open_timeout,
                environment_close_timeout=environment_close_timeout,
                kernel_process_timeout=kernel_process_timeout,
                kernel_cdp_timeout=kernel_cdp_timeout,
                kernel_cdp_probe_timeout=kernel_cdp_probe_timeout,
                http_probe_timeout=http_probe_timeout,
            )
        finally:
            try:
                environment_page.clear_search()
            except Exception:
                pass

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
        target_dir = cache_dir / subdir_name
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
