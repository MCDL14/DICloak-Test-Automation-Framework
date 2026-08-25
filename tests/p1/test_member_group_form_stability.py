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


if __name__ == "__main__":
    unittest.main()
