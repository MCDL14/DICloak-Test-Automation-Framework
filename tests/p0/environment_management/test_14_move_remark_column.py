from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_equal
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage


CASE_MODULE = "环境管理"


class TestMoveRemarkColumn(unittest.TestCase):
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

    def test_move_remark_column_to_first_and_restore(self) -> None:
        environment_page = EnvironmentPage(cdp_driver=self.cdp, config=self.config)
        moved_to_first = False

        try:
            environment_page.open_list()
            environment_page.clear_search()

            environment_page.open_column_settings()
            environment_page.move_column_before("备注", "环境序号")
            environment_page.confirm_column_settings()
            moved_to_first = True

            environment_page.wait_header_order(["备注"])
            assert_equal(
                environment_page.environment_header_texts()[0],
                "备注",
                "remark column was not moved to first visible column",
            )

            environment_page.open_column_settings()
            environment_page.move_column_after("备注", "环境名称")
            environment_page.confirm_column_settings()
            moved_to_first = False

            environment_page.wait_header_order(["环境序号", "环境名称", "备注"])
            assert_equal(
                environment_page.environment_header_texts()[:3],
                ["环境序号", "环境名称", "备注"],
                "remark column was not restored after environment name",
            )
        finally:
            if moved_to_first:
                try:
                    environment_page.open_column_settings()
                    environment_page.move_column_after("备注", "环境名称")
                    environment_page.confirm_column_settings()
                    environment_page.wait_header_order(["环境序号", "环境名称", "备注"])
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
