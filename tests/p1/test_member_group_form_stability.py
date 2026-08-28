from __future__ import annotations

import unittest
from unittest import mock

from pages.member_group_page import MemberGroupPage


class MemberGroupFormStabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cdp = mock.MagicMock()
        self.page = MemberGroupPage(cdp_driver=self.cdp, config={})

    def test_dialog_readiness_waits_for_stable_permission_controls(self) -> None:
        self.cdp.evaluate.side_effect = [
            {"ready": False, "loading": True, "permission_count": 0},
            {"ready": True, "loading": False, "permission_count": 4},
            {"ready": True, "loading": False, "permission_count": 7},
            {"ready": True, "loading": False, "permission_count": 7},
            {"ready": True, "loading": False, "permission_count": 7},
        ]

        self.page._wait_for_create_member_group_dialog_ready(
            timeout_seconds=1,
            stable_seconds=0.001,
            poll_seconds=0.001,
        )

        self.assertEqual(self.cdp.evaluate.call_count, 4)

    def test_fields_are_refilled_when_async_initialization_clears_name(self) -> None:
        values = {"成员分组名称": "", "备注": ""}
        name_was_reset = False

        def field_value(field_label: str) -> str:
            nonlocal name_was_reset
            if values["成员分组名称"] and values["备注"] and not name_was_reset:
                values["成员分组名称"] = ""
                name_was_reset = True
            return values[field_label]

        def fill_field(field_label: str, value: str) -> None:
            values[field_label] = value

        with (
            mock.patch.object(self.page, "_dialog_field_value", side_effect=field_value),
            mock.patch.object(self.page, "_fill_dialog_field", side_effect=fill_field) as fill_mock,
        ):
            self.page._fill_create_dialog_fields_stably(
                name="自动化-创建成员分组",
                remark="自动化-成员分组备注",
                timeout_seconds=1,
                stable_seconds=0.001,
                poll_seconds=0.001,
            )

        self.assertTrue(name_was_reset)
        self.assertEqual(values["成员分组名称"], "自动化-创建成员分组")
        self.assertEqual(values["备注"], "自动化-成员分组备注")
        self.assertEqual(
            fill_mock.call_args_list,
            [
                mock.call("成员分组名称", "自动化-创建成员分组"),
                mock.call("备注", "自动化-成员分组备注"),
                mock.call("成员分组名称", "自动化-创建成员分组"),
            ],
        )

    def test_edit_dialog_waits_for_original_name_and_loading_to_finish(self) -> None:
        self.cdp.evaluate.side_effect = [
            {"title": "编辑成员分组", "name": "", "remark": "", "loading": True},
            {"title": "编辑成员分组", "name": "原分组", "remark": "原备注", "loading": False},
            {"title": "编辑成员分组", "name": "原分组", "remark": "原备注", "loading": False},
            {"title": "编辑成员分组", "name": "原分组", "remark": "原备注", "loading": False},
        ]

        self.page._wait_for_edit_member_group_dialog(
            "原分组",
            timeout_seconds=1,
            stable_seconds=0.001,
            poll_seconds=0.001,
        )

        self.assertGreaterEqual(self.cdp.evaluate.call_count, 3)

    def test_first_member_group_requires_editable_row(self) -> None:
        self.cdp.evaluate.return_value = [
            {
                "name": "管理组",
                "remark": "--",
                "created_at": "2024-10-25 16:57:11",
                "editable": False,
            }
        ]

        with self.assertRaisesRegex(RuntimeError, "first member group is not editable"):
            self.page.first_member_group()

    def test_member_group_identity_rejects_ambiguous_rows(self) -> None:
        self.cdp.evaluate.return_value = [
            {"name": "分组一", "remark": "--", "created_at": "2024-10-25", "editable": True},
            {"name": "分组二", "remark": "--", "created_at": "2024-10-25", "editable": True},
        ]

        with self.assertRaisesRegex(RuntimeError, "matches=2"):
            self.page.member_group_by_identity("--", "2024-10-25")

    def test_edit_member_group_name_uses_stable_identity_and_waits_for_refresh(self) -> None:
        current = {
            "name": "原分组",
            "remark": "原备注",
            "created_at": "2026-08-27 16:00:00",
            "editable": True,
        }
        with (
            mock.patch.object(self.page, "member_group_by_identity", return_value=current),
            mock.patch.object(self.page, "dismiss_blocking_overlays") as dismiss_mock,
            mock.patch.object(self.page, "_wait_for_edit_member_group_dialog") as dialog_mock,
            mock.patch.object(self.page, "_wait_for_dialog_field_value") as field_mock,
            mock.patch.object(self.page, "_click_overlay_button_wait_loading_then_closed") as submit_mock,
            mock.patch.object(self.page, "_wait_for_member_group_table_not_loading") as table_mock,
            mock.patch.object(self.page, "wait_member_group_name_by_identity") as name_mock,
        ):
            self.page.edit_member_group_name_by_identity(
                remark="原备注",
                created_at="2026-08-27 16:00:00",
                new_name="自动化-编辑成员分组名称",
                expected_current_name="原分组",
            )

        dismiss_mock.assert_called_once_with()
        self.cdp.click_element_by_script.assert_called_once()
        dialog_mock.assert_called_once_with("原分组")
        self.cdp.fill_element_by_script.assert_called_once()
        field_mock.assert_called_once_with("成员分组名称", "自动化-编辑成员分组名称")
        submit_mock.assert_called_once_with("确定")
        table_mock.assert_called_once_with()
        name_mock.assert_called_once_with(
            "原备注",
            "2026-08-27 16:00:00",
            "自动化-编辑成员分组名称",
        )


if __name__ == "__main__":
    unittest.main()
