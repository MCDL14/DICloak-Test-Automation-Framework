from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from core.app_config import resolve_app_config
from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.kernel_cache import (
    kernel_browsers_dir_candidates,
    resolve_kernel_browsers_dir,
    wait_for_kernel_executable_dir,
)
from core.kernel_process import (
    kernel_version_from_cdp,
    kernel_version_from_command_line,
    resolve_kernel_runtime,
)
from core.logger import setup_logger
from core.process import process_executable_path_by_pid, wait_for_pid_running, wait_for_pid_stopped
from core.test_names import test_name
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage
from pages.personal_settings_page import PersonalSettingsPage


class KernelDownloadCaseMixin:
    """Download and launch one kernel without relying on a bundled APP kernel."""

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

    def _download_kernel_and_verify_environment(self, major_version: str) -> None:
        download_timeout = timeout_seconds(self.config, "kernel_download_seconds", 300)
        delete_timeout = timeout_seconds(self.config, "kernel_delete_seconds", 30)
        open_timeout = timeout_seconds(self.config, "environment_open_seconds", 90)
        close_timeout = timeout_seconds(self.config, "environment_close_seconds", 90)
        process_timeout = timeout_seconds(self.config, "kernel_process_seconds", 90)
        cdp_timeout = timeout_seconds(self.config, "kernel_cdp_seconds", 30)
        cdp_probe_timeout = timeout_seconds(self.config, "kernel_cdp_probe_seconds", 3)
        http_probe_timeout = timeout_seconds(self.config, "http_probe_seconds", 2)
        environment_name = test_name(self.config, f"download-kernel-{major_version}")
        settings_page = PersonalSettingsPage(cdp_driver=self.cdp, config=self.config)
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        environment_attempted = False
        environment_list_opened = False
        kernel_pid = 0

        try:
            settings_page.open_from_avatar()
            settings_page.open_basic_settings()
            cache_dir = settings_page.environment_cache_dir()

            deleted_versions = settings_page.delete_downloaded_kernels(major_version)
            if deleted_versions:
                self.logger.info("通过 APP 实际删除的内核完整版本: %s", deleted_versions)
                remaining = settings_page.download_record_kernel_versions(major_version)
                assert_equal(remaining, [], f"{major_version} 内核下载记录删除后仍有残留: {remaining}")
                self._assert_kernel_directories_deleted(cache_dir, deleted_versions, delete_timeout)
            else:
                self.logger.info("未找到已下载的 %s 内核，跳过删除与删除结果校验", major_version)

            version = settings_page.download_latest_kernel(major_version)
            assert_true(
                version.startswith(f"{major_version}."),
                f"下载目标内核版本不正确: expected={major_version}, actual={version}",
            )
            settings_page.wait_kernel_download_completed(
                major_version, version, timeout_seconds=download_timeout
            )
            # macOS 的内核目录可能与环境缓存目录分开，下载完成后重新定位。
            browsers_dir = resolve_kernel_browsers_dir(cache_dir, version=version)
            executable_name = resolve_app_config(self.config).browser_process_name
            downloaded_dir = wait_for_kernel_executable_dir(
                browsers_dir,
                major_version,
                executable_name=executable_name,
                timeout_seconds=download_timeout,
                version=version,
            )
            assert_equal(
                downloaded_dir.name,
                version,
                f"下载记录版本与实际内核目录不一致: expected={version}, actual={downloaded_dir.name}",
            )
            executables = [
                path
                for path in downloaded_dir.rglob(executable_name)
                if path.is_file() and path.stat().st_size > 0
            ]
            assert_true(
                bool(executables),
                f"{major_version} 内核下载后未找到非空可执行文件: directory={downloaded_dir}",
            )
            self.logger.info("内核下载校验成功: major=%s version=%s", major_version, version)

            environment_page.open_list()
            environment_list_opened = True
            environment_page.clear_search()
            # 提交失败也可能已经创建数据，finally 仍按本次唯一名称检查并清理。
            environment_attempted = True
            environment_page.create_environment_with_kernel(
                environment_name, f"ChromeBrowser {major_version}"
            )
            environment_page.wait_environment_visible_in_current_list(environment_name)
            assert_equal(
                environment_page.environment_action_text(environment_name),
                "打开",
                f"新建 {major_version} 内核环境未处于可打开状态: {environment_name}",
            )
            kernel_pid = environment_page.open_environment_and_capture_pid(environment_name)
            assert_true(
                wait_for_pid_running(kernel_pid, timeout_seconds=process_timeout),
                f"{major_version} 内核进程未启动: pid={kernel_pid}",
            )
            environment_page.wait_environment_action_text(
                environment_name, "关闭", timeout_seconds=open_timeout
            )
            runtime = resolve_kernel_runtime(
                environment_name,
                kernel_pid,
                timeout_seconds=cdp_timeout,
                probe_timeout_seconds=cdp_probe_timeout,
                http_timeout_seconds=http_probe_timeout,
            )
            actual_version = kernel_version_from_cdp(runtime.cdp_port, timeout_seconds=http_probe_timeout)
            if not actual_version:
                actual_version = kernel_version_from_command_line(runtime.command_line)
            assert_true(
                actual_version.startswith(f"{major_version}."),
                f"实际启动内核版本不正确: expected={major_version}, actual={actual_version}",
            )
            executable_path = process_executable_path_by_pid(kernel_pid)
            assert_true(
                self._executable_is_under(executable_path, downloaded_dir),
                f"启动进程未使用本次下载的内核: executable={executable_path}, downloaded={downloaded_dir}",
            )

            self._close_download_environment(
                environment_page, environment_name, kernel_pid, close_timeout, process_timeout
            )
            kernel_pid = 0
            environment_page.delete_environment_from_current_list(environment_name)
            environment_page.search_environment_without_assert(environment_name)
            assert_true(
                not environment_page.environment_visible_in_current_list(environment_name),
                f"下载内核验证环境删除后仍然存在: {environment_name}",
            )
            environment_attempted = False
        finally:
            failed = sys.exc_info()[0] is not None
            cleanup_errors: list[Exception] = []
            if environment_attempted:
                try:
                    environment_page.open_list()
                    environment_list_opened = True
                    environment_page.search_environment_without_assert(environment_name)
                    if environment_page.environment_visible_in_current_list(environment_name):
                        self._close_download_environment(
                            environment_page, environment_name, kernel_pid, close_timeout, process_timeout
                        )
                        environment_page.delete_environment_from_current_list(environment_name)
                        environment_page.wait_environment_absent_in_current_list(environment_name)
                except Exception as exc:
                    cleanup_errors.append(exc)
                    self.logger.warning("下载内核用例清理环境失败: name=%s error=%s", environment_name, exc)
            if environment_list_opened:
                try:
                    environment_page.clear_search()
                except Exception as exc:
                    cleanup_errors.append(exc)
                    self.logger.warning("下载内核用例清空环境筛选失败: %s", exc)
            if cleanup_errors and not failed:
                raise cleanup_errors[0]

    def _assert_kernel_directories_deleted(
        self, cache_dir: Path, deleted_versions: list[str], timeout: int
    ) -> None:
        # 删除前后缓存布局可能变化，不能只检查下载定位函数选中的一个目录。
        candidates = kernel_browsers_dir_candidates(cache_dir)

        def remaining_entries() -> list[Path]:
            # 仅检查通过 APP 实际执行了删除的完整版本；未被 APP 识别的
            # 损坏缓存不属于本次删除操作，不能按整个主版本误报。
            return [
                entry
                for browsers_dir in candidates
                for version in deleted_versions
                if (entry := browsers_dir / version).exists() or entry.is_symlink()
            ]

        deadline = time.monotonic() + timeout
        remaining = remaining_entries()
        while remaining and time.monotonic() < deadline:
            time.sleep(0.2)
            remaining = remaining_entries()
        assert_true(
            not remaining,
            f"内核删除后本地缓存仍有残留: versions={deleted_versions}, paths={[str(path) for path in remaining]}",
        )
        self.logger.info(
            "内核删除校验成功: deleted_versions=%s cache_directories=%s",
            deleted_versions,
            [str(path) for path in candidates],
        )

    def _close_download_environment(
        self,
        page: EnvironmentPage,
        name: str,
        kernel_pid: int,
        close_timeout: int,
        process_timeout: int,
    ) -> None:
        if not page.environment_visible_in_current_list(name):
            return
        if page.environment_action_text(name) == "关闭":
            page.click_environment_action(name, "关闭")
        if kernel_pid:
            assert_true(
                wait_for_pid_stopped(kernel_pid, timeout_seconds=process_timeout),
                f"下载验证环境内核进程未停止: pid={kernel_pid}",
            )
        page.wait_environment_action_text(name, "打开", timeout_seconds=close_timeout)

    @staticmethod
    def _executable_is_under(executable: str, downloaded_dir: Path) -> bool:
        if not executable:
            return False
        parent = os.path.normcase(str(downloaded_dir.resolve()))
        child = os.path.normcase(str(Path(executable).resolve()))
        return child.startswith(parent + os.sep)
