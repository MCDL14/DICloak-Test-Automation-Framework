from __future__ import annotations

import unittest
from pathlib import Path

from core.assertions import assert_true
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from pages.login_page import LoginPage
from pages.member_page import MemberPage


CASE_MODULE = "成员管理"


class TestBatchEditMemberRemark(unittest.TestCase):
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

    def test_batch_edit_member_remark(self) -> None:
        original_remark = "自动化数据专用【勿删！！！】"
        override_remark = "自动化-批量设置成员备注"
        append_remark = "自动化-追加备注"
        member_page = MemberPage(cdp_driver=self.cdp, config=self.config)
        member_ids: list[str] = []

        try:
            member_page.open_list()
            member_page.clear_filters()

            # Step 1: 找到并记录备注为"自动化数据专用【勿删！！！】"的成员ID
            member_ids = member_page.member_ids_by_remark(original_remark)
            assert_true(member_ids, f"no members found with remark: {original_remark}")

            # Step 2-7: 覆盖备注
            member_page.select_members_by_ids(member_ids)
            member_page.batch_edit_remark("覆盖", override_remark)
            member_page.wait_member_remarks_by_ids(member_ids, override_remark)

            # Step 8-11: 追加备注
            member_page.select_members_by_ids(member_ids)
            member_page.batch_edit_remark("追加", append_remark)
            # 追加后：备注应同时包含覆盖值和追加值
            remark_values = member_page.member_remark_values_by_ids(member_ids)
            for mid, remark in remark_values.items():
                assert_true(
                    override_remark in remark and append_remark in remark,
                    "member remark append failed: "
                    f"member={mid}, expected to contain '{override_remark}' and '{append_remark}', actual='{remark}'",
                )

            # Step 12-15: 还原备注
            member_page.select_members_by_ids(member_ids)
            member_page.batch_edit_remark("覆盖", original_remark)
            member_page.wait_member_remarks_by_ids(member_ids, original_remark)

        finally:
            try:
                member_page.open_list()
                member_page.clear_filters()
                if member_ids:
                    member_page.select_members_by_ids(member_ids)
                    member_page.batch_edit_remark("覆盖", original_remark)
                    member_page.wait_member_remarks_by_ids(member_ids, original_remark)
                    member_page.clear_selected_members()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
