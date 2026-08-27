from __future__ import annotations

import copy
import unittest
from unittest import mock

from core.global_settings_baseline import current_global_settings_ui_baseline
from pages.global_settings_page import GlobalSettingsPage


class TestGlobalSettingsSnapshot(unittest.TestCase):
    def setUp(self) -> None:
        self.cdp = mock.MagicMock()
        self.page = GlobalSettingsPage(cdp_driver=self.cdp, config={})

    def test_capture_snapshot_matches_current_ui_baseline_schema(self) -> None:
        baseline = current_global_settings_ui_baseline()
        self.page._wait_global_setting_states_stable = mock.MagicMock()
        self.page._simple_checkbox_snapshot = mock.MagicMock(
            return_value=copy.deepcopy(baseline["simple_checkboxes"])
        )
        self.page.website_restriction_state = mock.MagicMock(
            return_value={"enabled": False, "urls": ["ignored while disabled"]}
        )
        self.page.packet_capture_blocking_state = mock.MagicMock(
            return_value={"enabled": False, "process_name": "ignored.exe"}
        )
        self.page.bookmark_setting_state = mock.MagicMock(
            return_value={"enabled": False, "restore_supported": True, "text": "ignored"}
        )
        self.page.environment_field_display_limit_state = mock.MagicMock(
            return_value={"enabled": False, "fields": ["ignored"]}
        )
        self.page.environment_list_pagination_setting_state = mock.MagicMock(
            return_value={"enabled": False, "page_size": "100"}
        )
        self.page.environment_list_sort_state = mock.MagicMock(
            return_value={"enabled": False, "field": "环境序号", "direction": "降序"}
        )
        self.page.data_sync_one_way_state = mock.MagicMock(
            return_value=copy.deepcopy(baseline["data_sync"])
        )
        self.page.clear_local_cache_state = mock.MagicMock(
            return_value={"clear_method": "不清除"}
        )
        self.page.extension_tamper_protection_state = mock.MagicMock(
            return_value={"enabled": False}
        )
        self.page.proxy_check_failure_block_open_enabled = mock.MagicMock(return_value=False)
        self.page.country_mismatch_block_open_enabled = mock.MagicMock(return_value=False)

        snapshot = self.page.capture_global_settings_snapshot()

        self.assertEqual(snapshot["schema_version"], 2)
        self.assertEqual(snapshot["proxy_check_failure_block_open"], {"enabled": False})
        self.assertEqual(snapshot["country_mismatch_block_open"], {"enabled": False})
        self.assertTrue(self.page._global_settings_snapshot_matches(baseline, snapshot))

    def test_assert_current_ui_baseline_returns_actual_snapshot(self) -> None:
        baseline = current_global_settings_ui_baseline()
        self.page.capture_global_settings_snapshot = mock.MagicMock(return_value=baseline)

        actual = self.page.assert_current_global_settings_ui_baseline()

        self.assertEqual(actual, baseline)

    def test_assert_current_ui_baseline_reports_mismatch_without_restore(self) -> None:
        actual = current_global_settings_ui_baseline()
        actual["proxy_check_failure_block_open"] = {"enabled": True}
        self.page.capture_global_settings_snapshot = mock.MagicMock(return_value=actual)
        self.page.restore_global_settings_snapshot = mock.MagicMock()

        with self.assertRaisesRegex(
            AssertionError,
            "current global settings UI baseline mismatch",
        ):
            self.page.assert_current_global_settings_ui_baseline()

        self.page.restore_global_settings_snapshot.assert_not_called()

    def test_ui_baseline_factory_returns_independent_copy(self) -> None:
        first = current_global_settings_ui_baseline()
        second = current_global_settings_ui_baseline()

        first["simple_checkboxes"]["禁止查看网站密码"] = False

        self.assertTrue(second["simple_checkboxes"]["禁止查看网站密码"])

    def test_new_security_switch_states_support_explicit_ui_restore(self) -> None:
        self.page._set_proxy_check_failure_block_open_enabled = mock.MagicMock()
        self.page._set_country_mismatch_block_open_enabled = mock.MagicMock()

        self.page.restore_proxy_check_failure_block_open_state({"enabled": False})
        self.page.restore_country_mismatch_block_open_state({"enabled": True})

        self.page._set_proxy_check_failure_block_open_enabled.assert_called_once_with(False)
        self.page._set_country_mismatch_block_open_enabled.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
