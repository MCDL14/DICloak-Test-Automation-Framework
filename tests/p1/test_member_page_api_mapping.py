from __future__ import annotations

import unittest
from unittest import mock

from pages.member_page import MemberPage


class MemberPageApiMappingTests(unittest.TestCase):
    def test_current_account_marker_maps_dom_row_to_api_id(self) -> None:
        cdp = mock.MagicMock()
        cdp.evaluate.side_effect = [
            [
                {
                    "id": "",
                    "name": "外部成员1(本账号)",
                    "raw": "外部成员1(本账号)",
                    "remark": "必要数据",
                    "created_time": "",
                    "text": "外部成员1(本账号) 必要数据",
                    "row_index": "0",
                    "is_current_account": True,
                }
            ],
            [
                {
                    "id": "other-id",
                    "name": "外部成员1",
                    "email": "other@example.com",
                    "remark": "必要数据",
                },
                {
                    "id": "current-id",
                    "name": "外部成员1",
                    "email": "current@example.com",
                    "remark": "必要数据",
                },
            ],
        ]
        page = MemberPage(
            cdp_driver=cdp,
            config={"account": {"username": "current@example.com"}},
        )

        records = page._member_records_in_current_list()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "current-id")
        self.assertEqual(records[0]["name"], "外部成员1")
        self.assertEqual(records[0]["is_current_account"], "true")

    def test_duplicate_member_names_fall_back_to_api_list_index(self) -> None:
        page = MemberPage(cdp_driver=mock.MagicMock(), config={})
        visible_record = {
            "id": "",
            "name": "同名成员",
            "raw": "同名成员",
            "remark": "",
            "created_time": "",
            "text": "同名成员",
            "row_index": "1",
            "is_current_account": "false",
        }
        api_records = page._normalize_member_api_records(
            [
                {"id": "first-id", "name": "同名成员"},
                {"id": "second-id", "name": "同名成员"},
            ]
        )

        matched = page._match_member_api_record(visible_record, api_records)

        self.assertIsNotNone(matched)
        self.assertEqual(matched["id"], "second-id")

    def test_all_environment_group_is_normalized_to_chinese_label(self) -> None:
        cdp = mock.MagicMock()
        cdp.evaluate.return_value = ["all", "自动化分组", "ALL"]
        page = MemberPage(cdp_driver=cdp, config={})

        groups = page.selected_environment_groups_in_edit_dialog()

        self.assertEqual(groups, ["全部分组", "自动化分组"])

    def test_empty_environment_group_placeholders_are_ignored(self) -> None:
        cdp = mock.MagicMock()
        cdp.evaluate.return_value = ["请选择环境分组", "需要指定环境分组", "--"]
        page = MemberPage(cdp_driver=cdp, config={})

        groups = page.selected_environment_groups_in_edit_dialog()

        self.assertEqual(groups, [])

    def test_rename_member_selects_fallback_environment_group_when_empty(self) -> None:
        page = MemberPage(cdp_driver=mock.MagicMock(), config={})
        page.open_member_edit_dialog = mock.MagicMock()
        page.selected_environment_groups_in_edit_dialog = mock.MagicMock(return_value=[])
        page._select_environment_group_in_edit_dialog = mock.MagicMock()
        page._wait_edit_dialog_environment_group_selected = mock.MagicMock()
        page._wait_for_overlay_closed = mock.MagicMock()
        page._wait_for_member_table_not_loading = mock.MagicMock()
        page.wait_member_visible = mock.MagicMock()
        page.wait_member_absent = mock.MagicMock()

        page.rename_member(
            "内部成员003",
            "自动化-编辑内部成员名称",
            environment_group_if_empty="未分组",
        )

        page._select_environment_group_in_edit_dialog.assert_called_once_with("未分组")
        page._wait_edit_dialog_environment_group_selected.assert_called_once_with("未分组")

    def test_rename_member_preserves_existing_environment_group(self) -> None:
        page = MemberPage(cdp_driver=mock.MagicMock(), config={})
        page.open_member_edit_dialog = mock.MagicMock()
        page.selected_environment_groups_in_edit_dialog = mock.MagicMock(return_value=["自动化分组"])
        page._select_environment_group_in_edit_dialog = mock.MagicMock()
        page._wait_edit_dialog_environment_group_selected = mock.MagicMock()
        page._wait_for_overlay_closed = mock.MagicMock()
        page._wait_for_member_table_not_loading = mock.MagicMock()
        page.wait_member_visible = mock.MagicMock()
        page.wait_member_absent = mock.MagicMock()

        page.rename_member(
            "内部成员003",
            "自动化-编辑内部成员名称",
            environment_group_if_empty="未分组",
        )

        page._select_environment_group_in_edit_dialog.assert_not_called()
        page._wait_edit_dialog_environment_group_selected.assert_not_called()

    def test_member_environment_groups_are_read_from_api_record(self) -> None:
        cdp = mock.MagicMock()
        cdp.evaluate.return_value = [
            {
                "id": "automation-member-id",
                "name": "自动化成员1",
                "all_env_group": False,
                "env_group_list": [
                    {"env_group_name": "未分组"},
                    {"env_group_name": "分组二"},
                ],
            }
        ]
        page = MemberPage(cdp_driver=cdp, config={})

        groups = page.member_environment_groups_from_api("automation-member-id")

        self.assertEqual(groups, ["未分组", "分组二"])

    def test_member_environment_groups_from_api_supports_all(self) -> None:
        cdp = mock.MagicMock()
        cdp.evaluate.return_value = [
            {
                "id": "automation-member-id",
                "name": "自动化成员1",
                "all_env_group": True,
                "env_group_list": [],
            }
        ]
        page = MemberPage(cdp_driver=cdp, config={})

        groups = page.member_environment_groups_from_api("automation-member-id")

        self.assertEqual(groups, ["全部分组"])

    def test_assign_environment_group_uses_api_original_groups(self) -> None:
        page = MemberPage(cdp_driver=mock.MagicMock(), config={})
        page.member_environment_groups_from_api = mock.MagicMock(return_value=["未分组"])
        page.open_member_edit_dialog = mock.MagicMock()
        page._select_environment_group_in_edit_dialog = mock.MagicMock()
        page._wait_edit_dialog_environment_group_selected = mock.MagicMock()
        page._wait_for_overlay_closed = mock.MagicMock()
        page._wait_for_member_table_not_loading = mock.MagicMock()
        page.wait_member_environment_groups_contain = mock.MagicMock()

        original_groups = page.assign_environment_group_to_member(
            "自动化成员1",
            "自动化-授权成员的分组",
            member_id="automation-member-id",
        )

        self.assertEqual(original_groups, ["未分组"])
        page.member_environment_groups_from_api.assert_called_once_with("automation-member-id")
        page._select_environment_group_in_edit_dialog.assert_called_once_with(
            "自动化-授权成员的分组"
        )

    def test_member_id_by_exact_name_uses_current_api_mapped_row(self) -> None:
        page = MemberPage(cdp_driver=mock.MagicMock(), config={})
        page.filter_by_member_name_or_id = mock.MagicMock()
        page.member_name_id_values_in_current_list = mock.MagicMock(
            return_value=[
                {"id": "automation-member-id", "name": "自动化成员1"},
                {"id": "other-member-id", "name": "其他成员"},
            ]
        )

        member_id = page.member_id_by_exact_name("自动化成员1")

        self.assertEqual(member_id, "automation-member-id")
        page.filter_by_member_name_or_id.assert_called_once_with("自动化成员1")

    def test_member_name_by_id_uses_current_api_mapped_row(self) -> None:
        page = MemberPage(cdp_driver=mock.MagicMock(), config={})
        page.filter_by_member_name_or_id = mock.MagicMock()
        page._member_record_by_id_in_current_list = mock.MagicMock(
            return_value={"id": "automation-member-id", "name": "自动化成员1"}
        )

        member_name = page.member_name_by_id("automation-member-id")

        self.assertEqual(member_name, "自动化成员1")
        page.filter_by_member_name_or_id.assert_not_called()


if __name__ == "__main__":
    unittest.main()
