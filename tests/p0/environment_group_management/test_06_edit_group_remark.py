from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal, assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_group_page import EnvironmentGroupPage
from pages.login_page import LoginPage


CASE_MODULE = "环境分组管理"


class TestEditGroupRemark(unittest.TestCase):
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

    def test_edit_group_remark_and_restore(self) -> None:
        temporary_remark = "自动化-修改环境分组备注"
        group_page = EnvironmentGroupPage(cdp_driver=self.cdp, config=self.config)
        target_group: dict[str, str] = {}
        changed = False
        restored = False

        try:
            group_page.open_list()
            try:
                group_page.clear_filters()
            except Exception:
                pass

            target_group = group_page.first_editable_group(excluded_remarks={temporary_remark})
            group_id = target_group["id"]
            original_remark = target_group["remark"]
            original_remark_input = "" if original_remark == "--" else original_remark

            assert_true(bool(group_id), f"editable environment group id was empty: {target_group}")
            assert_true("remark" in target_group, f"editable environment group remark was not recorded: {target_group}")

            group_page.edit_group_remark_by_id(group_id, temporary_remark)
            changed = True
            assert_equal(
                group_page.group_remark_by_id(group_id),
                temporary_remark,
                f"environment group remark was not changed by id: id={group_id}",
            )

            group_page.edit_group_remark_by_id(group_id, original_remark_input)
            changed = False
            restored = True
            assert_equal(
                group_page.group_remark_by_id(group_id),
                original_remark,
                f"environment group remark was not restored by id: id={group_id}",
            )
        finally:
            if target_group and changed and not restored:
                try:
                    group_page.open_list()
                    restore_remark = "" if target_group["remark"] == "--" else target_group["remark"]
                    group_page.edit_group_remark_by_id(target_group["id"], restore_remark)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
