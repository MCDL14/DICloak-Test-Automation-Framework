from __future__ import annotations

import re
import unittest
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from core.account_groups import case_external_member_name
from core.assertions import assert_file_exists, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.files import wait_for_file
from core.logger import setup_logger
from core.member_export import assert_member_export_matches_api, read_member_export_rows
from core.platform.desktop import desktop_file_dialog_supported, unsupported_desktop_file_dialog_message
from pages.login_page import LoginPage
from pages.member_page import MemberPage


CASE_MODULE = "成员管理"


class TestExportMember(unittest.TestCase):
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

    def test_export_selected_members(self) -> None:
        target_member_names = ["自动化成员1", case_external_member_name(self.config)]
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)
        member_export_cfg = self.config["test_data"]["member_export"]
        export_dir = Path(member_export_cfg["export_dir"])
        export_timeout = timeout_seconds(self.config, "batch_export_seconds", 120)
        download_event_timeout = min(export_timeout, 30)
        exported_file: Path | None = None
        temp_download_path = export_dir / "_member_export_tmp.xlsx"

        try:
            # 进入成员列表，监听清除筛选触发的 GET /gin/v1/member，
            # 并只在当前用例内保留两个目标成员的接口快照。
            member_page.open_list()
            target_members = member_page.capture_members_from_clear_filter_response(target_member_names)
            member_page.select_members_by_ids(
                [str(member.get("id") or "").strip() for member in target_members]
            )

            export_dir.mkdir(parents=True, exist_ok=True)
            if temp_download_path.exists():
                temp_download_path.unlink()

            suggested_filename = ""
            try:
                suggested_filename = member_page.export_selected_members_and_save_download(
                    temp_download_path,
                    timeout_seconds=download_event_timeout,
                )
            except PlaywrightTimeoutError:
                if not desktop_file_dialog_supported():
                    self.skipTest(unsupported_desktop_file_dialog_message())
                member_page.export_selected_members_via_save_dialog(temp_download_path)

            if suggested_filename:
                filename_regex = str(member_export_cfg.get("export_file_regex") or "").strip()
                if filename_regex:
                    assert_true(
                        re.fullmatch(filename_regex, suggested_filename) is not None,
                        f"export filename mismatch: actual={suggested_filename}, regex={filename_regex}",
                    )

            generated_file = wait_for_file(temp_download_path, timeout_seconds=export_timeout)
            assert_file_exists(generated_file, f"export file was not generated: {generated_file}")
            assert_true(generated_file.stat().st_size > 0, f"export file is empty: {generated_file}")
            exported_file = generated_file

            headers, exported_rows = read_member_export_rows(exported_file)
            assert_member_export_matches_api(headers, exported_rows, target_members)

        finally:
            try:
                member_page.clear_selected_members()
            except Exception:
                pass
            if exported_file and exported_file.exists():
                try:
                    exported_file.unlink()
                except Exception:
                    pass
            if temp_download_path.exists():
                try:
                    temp_download_path.unlink()
                except Exception:
                    pass
            try:
                member_page.open_list()
                member_page.clear_filters()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
