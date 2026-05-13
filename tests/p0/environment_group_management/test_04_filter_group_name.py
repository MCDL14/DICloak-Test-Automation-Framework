from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_group_page import EnvironmentGroupPage
from pages.login_page import LoginPage


CASE_MODULE = "环境分组管理"


class TestFilterGroupName(unittest.TestCase):
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

    def test_filter_group_name(self) -> None:
        remark = "勿动！！！"
        group_page = EnvironmentGroupPage(cdp_driver=self.cdp, config=self.config)

        try:
            group_page.open_list()
            try:
                group_page.clear_filters()
            except Exception:
                pass

            group_page.filter_by_group_remark(remark)
            filtered_rows = group_page.group_rows_in_current_list()
            assert_true(filtered_rows, f"group-remark filter returned no rows: {remark}")
            assert_true(
                all(remark in row["remark"] for row in filtered_rows),
                f"group-remark filter returned rows not matching target remark: remark={remark}, rows={filtered_rows}",
            )

            group_page.switch_group_text_filter_mode("分组名称")
        finally:
            try:
                group_page.switch_group_text_filter_mode("分组名称")
                group_page.clear_filters()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
