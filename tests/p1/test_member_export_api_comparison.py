from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import Workbook

from core.member_export import (
    MEMBER_EXPORT_HEADERS,
    assert_member_export_matches_api,
    expected_export_row_from_member,
    extract_target_member_records,
    read_member_export_rows,
)
from pages.member_page import MemberPage


def _member_record(
    *,
    member_id: str,
    name: str,
    email: str,
    authority: str = "MEMBER",
    status: str = "ENABLED",
) -> dict:
    return {
        "create_by_name": "建勋",
        "id": member_id,
        "create_time": "2026-07-27 16:04:36",
        "name": name,
        "email": email,
        "all_env_group": False,
        "env_group_list": [
            {
                "group_id": "1849736955234795522",
                "env_group_name": "未分组",
                "member_id": member_id,
                "member_name": name,
            }
        ],
        "role_name": "管理组",
        "authority": authority,
        "status": status,
        "remark": "必要数据（且必须处于第二位）",
        "disuse_enable": False,
        "time_zone": "Etc/GMT",
        "disuse_time": None,
        "last_login_time": None,
    }


class MemberExportApiComparisonTests(unittest.TestCase):
    def test_member_page_captures_clear_filter_get_response(self) -> None:
        member = _member_record(member_id="2", name="自动化成员1", email="mcdl003")
        response_body = json.dumps({"code": 0, "data": {"list": [member]}}, ensure_ascii=False)
        cdp = mock.MagicMock()
        cdp.evaluate.side_effect = [False, True]
        cdp.click_element_by_script_and_wait_for_response.return_value = {
            "status": 200,
            "url": "https://gin-server.dicloak.com/gin/v1/member?page_no=1",
            "response_body": response_body,
        }
        page = MemberPage(cdp_driver=cdp, config={})

        with (
            mock.patch.object(page, "filter_by_member_name_or_id") as apply_filter,
            mock.patch.object(page, "wait_member_filters_cleared") as wait_cleared,
        ):
            captured = page.capture_members_from_clear_filter_response(["自动化成员1"])

        apply_filter.assert_called_once_with("自动化成员1")
        wait_cleared.assert_called_once()
        cdp.click_element_by_script_and_wait_for_response.assert_called_once_with(
            page._clear_filter_button_script(),
            "/gin/v1/member",
            method="GET",
            exact_path=True,
        )
        self.assertEqual(captured[0]["id"], "2")

    def test_extracts_two_named_members_from_member_list_response(self) -> None:
        rows = [
            _member_record(member_id="1", name="其他成员", email="other"),
            _member_record(member_id="2", name="自动化成员1", email="mcdl003"),
            _member_record(member_id="3", name="外部成员1", email="external@example.com"),
        ]
        response_body = json.dumps({"code": 0, "data": {"list": rows}}, ensure_ascii=False)

        selected = extract_target_member_records(response_body, ["自动化成员1", "外部成员1"])

        self.assertEqual([member["id"] for member in selected], ["2", "3"])

    def test_maps_all_api_fields_to_export_columns(self) -> None:
        member = _member_record(member_id="2", name="自动化成员1", email="mcdl003")

        row = expected_export_row_from_member(member)

        self.assertEqual(list(row), list(MEMBER_EXPORT_HEADERS))
        self.assertEqual(row["成员ID"], "2")
        self.assertEqual(row["授权环境分组"], "未分组")
        self.assertEqual(row["成员身份"], "员工")
        self.assertEqual(row["状态"], "启用中")
        self.assertEqual(row["开启到期停用"], "已关闭")
        self.assertEqual(row["过期时间"], "")
        self.assertEqual(row["最近登录时间"], "尚未登录")
        self.assertEqual(row["创建时间"], "2026-07-27 16:04:36")

    def test_maps_authority_status_disuse_and_time_values(self) -> None:
        authority_labels = {
            "MANAGER": "经理",
            "ADMIN": "管理员",
            "MEMBER": "员工",
        }
        for authority, expected_label in authority_labels.items():
            with self.subTest(authority=authority):
                member = _member_record(
                    member_id="2",
                    name="自动化成员1",
                    email="mcdl003",
                    authority=authority,
                )
                self.assertEqual(
                    expected_export_row_from_member(member)["成员身份"],
                    expected_label,
                )

        member = _member_record(
            member_id="2",
            name="自动化成员1",
            email="mcdl003",
            status="DISABLED",
        )
        member["disuse_enable"] = True
        member["disuse_time"] = "2026-07-31 12:00:00"
        member["last_login_time"] = "2026-07-28 08:30:00"
        row = expected_export_row_from_member(member)
        self.assertEqual(row["状态"], "已停用")
        self.assertEqual(row["开启到期停用"], "已开启")
        self.assertEqual(row["过期时间"], "2026-07-31 12:00:00")
        self.assertEqual(row["最近登录时间"], "2026-07-28 08:30:00")

    def test_all_environment_groups_ignores_group_list(self) -> None:
        member = _member_record(member_id="2", name="自动化成员1", email="mcdl003")
        member["all_env_group"] = True
        member["env_group_list"] = [{"env_group_name": "不应使用"}]

        row = expected_export_row_from_member(member)

        self.assertEqual(row["授权环境分组"], "全部分组")

    def test_compares_every_export_field_including_dynamic_fields(self) -> None:
        members = [
            _member_record(member_id="2", name="自动化成员1", email="mcdl003"),
            _member_record(member_id="3", name="外部成员1", email="external@example.com"),
        ]
        rows = [expected_export_row_from_member(member) for member in members]

        assert_member_export_matches_api(list(MEMBER_EXPORT_HEADERS), rows, members)

        for field in MEMBER_EXPORT_HEADERS:
            changed_rows = [dict(row) for row in rows]
            changed_rows[0][field] = "不一致"
            with self.subTest(all_fields=field):
                with self.assertRaises(AssertionError):
                    assert_member_export_matches_api(
                        list(MEMBER_EXPORT_HEADERS),
                        changed_rows,
                        members,
                    )

        for field in ("成员ID", "最近登录时间", "创建时间"):
            changed_rows = [dict(row) for row in rows]
            changed_rows[0][field] = "不一致"
            with self.subTest(field=field):
                with self.assertRaisesRegex(AssertionError, f"field={field}"):
                    assert_member_export_matches_api(
                        list(MEMBER_EXPORT_HEADERS),
                        changed_rows,
                        members,
                    )

    def test_multiple_environment_group_separators_are_semantically_equal(self) -> None:
        member = _member_record(member_id="2", name="自动化成员1", email="mcdl003")
        member["env_group_list"] = [
            {"env_group_name": "未分组"},
            {"env_group_name": "运营环境"},
        ]
        row = expected_export_row_from_member(member)
        row["授权环境分组"] = "运营环境, 未分组"

        assert_member_export_matches_api(list(MEMBER_EXPORT_HEADERS), [row], [member])

    def test_reads_export_workbook_values(self) -> None:
        member = _member_record(member_id="2", name="自动化成员1", email="mcdl003")
        expected_row = expected_export_row_from_member(member)
        with tempfile.TemporaryDirectory() as temp_dir:
            export_file = Path(temp_dir) / "members.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(list(MEMBER_EXPORT_HEADERS))
            sheet.append([expected_row[header] for header in MEMBER_EXPORT_HEADERS])
            workbook.save(export_file)
            workbook.close()

            headers, rows = read_member_export_rows(export_file)

        assert_member_export_matches_api(headers, rows, [member])


if __name__ == "__main__":
    unittest.main()
