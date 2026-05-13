from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_group_page import EnvironmentGroupPage
from pages.login_page import LoginPage
from pages.member_page import MemberPage


CASE_MODULE = "环境分组管理"


class TestGroupAuthorizedMember(unittest.TestCase):
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

    def test_group_authorized_member(self) -> None:
        group_name = "自动化-授权成员的分组"
        member_name = "自动化成员1"
        group_page = EnvironmentGroupPage(cdp_driver=self.cdp, config=self.config)
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)
        group_created = False
        member_original_groups: list[str] = []
        member_updated = False

        try:
            group_page.open_list()
            try:
                group_page.clear_filters()
            except Exception:
                pass
            if group_page.group_visible(group_name):
                group_page.delete_group(group_name)

            group_page.create_group(group_name)
            group_created = True
            assert_true(group_page.group_visible(group_name), f"environment group was not created: {group_name}")

            member_page.open_list()
            member_original_groups = member_page.assign_environment_group_to_member(member_name, group_name)
            member_updated = True

            group_page.open_list()
            popover_text = group_page.authorized_member_popover_text(group_name)
            assert_true(
                member_name in popover_text,
                "authorized member popover did not contain edited member: "
                f"group={group_name}, member={member_name}, popover={popover_text}",
            )

            group_page.filter_by_authorized_member(member_name)
            filtered_rows = group_page.group_rows_in_current_list()
            filtered_text = "\n".join(row["text"] for row in filtered_rows)
            assert_true(
                group_name in filtered_text,
                "authorized-member filter did not return newly authorized group: "
                f"group={group_name}, member={member_name}, rows={filtered_rows}",
            )
            for original_group in self._groups_expected_in_group_list(member_original_groups):
                assert_true(
                    original_group in filtered_text,
                    "authorized-member filter did not return original authorized group: "
                    f"original={original_group}, member={member_name}, rows={filtered_rows}",
                )

            group_page.clear_filters()
            group_page.delete_group(group_name)
            group_created = False

            member_page.open_list()
            member_page.wait_member_environment_groups_equal(member_name, member_original_groups)
            member_updated = False

            group_page.open_list()
        finally:
            cleanup_error: Exception | None = None
            try:
                if group_created:
                    group_page.open_list()
                    try:
                        group_page.clear_filters()
                    except Exception:
                        pass
                    group_page.delete_group_if_exists(group_name)
                    group_created = False
            except Exception as exc:
                cleanup_error = cleanup_error or exc
            try:
                if member_updated and member_original_groups:
                    member_page.open_list()
                    member_page.wait_member_environment_groups_equal(member_name, member_original_groups)
            except Exception as exc:
                cleanup_error = cleanup_error or exc
            try:
                group_page.open_list()
            except Exception:
                pass
            if cleanup_error:
                raise cleanup_error

    def _groups_expected_in_group_list(self, group_names: list[str]) -> list[str]:
        return [group for group in group_names if group and group != "全部分组"]


if __name__ == "__main__":
    unittest.main()
