from __future__ import annotations

import unittest
from unittest import mock

from pages.global_settings_page import GlobalSettingsPage


class TestGlobalSettingsDataSync(unittest.TestCase):
    def setUp(self) -> None:
        self.cdp = mock.MagicMock()
        self.page = GlobalSettingsPage(cdp_driver=self.cdp, config={})
        self.page._wait_for_cookie_data_sync = mock.MagicMock()
        self.page.cookie_data_sync_enabled = mock.MagicMock()
        self.page._cookie_data_sync_checkbox_script = mock.MagicMock(
            return_value="COOKIE_CHECKBOX_SCRIPT"
        )
        self.page._wait_cookie_data_sync_enabled = mock.MagicMock()
        self.page._wait_for_local_storage_data_sync = mock.MagicMock()
        self.page._wait_checkbox_states_stable = mock.MagicMock()
        self.page.local_storage_data_sync_enabled = mock.MagicMock()
        self.page._local_storage_data_sync_checkbox_script = mock.MagicMock(
            return_value="LOCAL_STORAGE_CHECKBOX_SCRIPT"
        )
        self.page._wait_local_storage_data_sync_enabled = mock.MagicMock()
        self.page._wait_for_indexeddb_data_sync = mock.MagicMock()
        self.page.indexeddb_data_sync_enabled = mock.MagicMock()
        self.page._indexeddb_data_sync_checkbox_script = mock.MagicMock(
            return_value="INDEXEDDB_CHECKBOX_SCRIPT"
        )
        self.page._wait_indexeddb_data_sync_enabled = mock.MagicMock()
        self.page.checkbox_states = mock.MagicMock()
        self.page._visible_button_by_text_script = mock.MagicMock(return_value="SAVE_BUTTON_SCRIPT")
        self.page._wait_save_finished = mock.MagicMock(return_value=False)
        self.page.open = mock.MagicMock()
        self.page._wait_for_clear_local_cache_settings = mock.MagicMock()
        self.page.clear_local_cache_state = mock.MagicMock(return_value={"clear_method": "其他"})
        self.page._wait_global_setting_states_stable = mock.MagicMock(return_value=({}, {}))
        self.page._select_global_settings_form_select_option = mock.MagicMock()
        self.page._set_clear_local_cache_sync_cloud_enabled = mock.MagicMock()
        self.page._wait_global_settings_form_select_value = mock.MagicMock()
        self.page._wait_clear_local_cache_sync_cloud_enabled = mock.MagicMock()
        self.page._close_select_dropdowns = mock.MagicMock()
        self.page._assert_no_unexpected_existing_state_changes = mock.MagicMock()

    def test_cookie_already_disabled_does_not_modify_or_save(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": False,
            "Local Storage": True,
            "IndexedDB": True,
        }
        self.page.cookie_data_sync_enabled.return_value = False

        changed = self.page.ensure_cookie_data_sync_disabled()

        self.assertFalse(changed)
        self.cdp.click_element_by_script.assert_not_called()
        self.page.open.assert_not_called()

    def test_cookie_enabled_changes_only_target_then_saves_and_reopens(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": True,
        }
        self.page.cookie_data_sync_enabled.return_value = True
        self.page.checkbox_states.return_value = {
            "Cookie": False,
            "Local Storage": True,
            "IndexedDB": True,
        }

        changed = self.page.ensure_cookie_data_sync_disabled()

        self.assertTrue(changed)
        self.assertEqual(
            self.cdp.click_element_by_script.call_args_list,
            [
                mock.call("COOKIE_CHECKBOX_SCRIPT"),
                mock.call("SAVE_BUTTON_SCRIPT"),
            ],
        )
        self.page._wait_save_finished.assert_called_once_with()
        self.page.open.assert_called_once_with()
        self.assertEqual(self.page._wait_for_cookie_data_sync.call_count, 2)
        self.assertEqual(
            self.page._wait_cookie_data_sync_enabled.call_args_list,
            [mock.call(False), mock.call(False)],
        )

    def test_cookie_disable_save_success_skips_reopen(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": True,
        }
        self.page.cookie_data_sync_enabled.return_value = True
        self.page.checkbox_states.return_value = {
            "Cookie": False,
            "Local Storage": True,
            "IndexedDB": True,
        }
        self.page._wait_save_finished.return_value = True

        changed = self.page.ensure_cookie_data_sync_disabled()

        self.assertTrue(changed)
        self.page._wait_save_finished.assert_called_once_with()
        self.page.open.assert_not_called()
        self.assertEqual(
            self.page._wait_cookie_data_sync_enabled.call_args_list,
            [mock.call(False)],
        )

    def test_cookie_disable_unexpected_other_checkbox_change_fails_before_save(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": True,
        }
        self.page.cookie_data_sync_enabled.return_value = True
        self.page.checkbox_states.return_value = {
            "Cookie": False,
            "Local Storage": False,
            "IndexedDB": True,
        }

        with self.assertRaisesRegex(AssertionError, "unexpected global settings checkbox changes"):
            self.page.ensure_cookie_data_sync_disabled()

        self.cdp.click_element_by_script.assert_called_once_with("COOKIE_CHECKBOX_SCRIPT")
        self.page._wait_save_finished.assert_not_called()
        self.page.open.assert_not_called()

    def test_local_storage_already_enabled_does_not_modify_or_save(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": True,
        }
        self.page.local_storage_data_sync_enabled.return_value = True

        changed = self.page.ensure_local_storage_data_sync_enabled()

        self.assertFalse(changed)
        self.cdp.click_element_by_script.assert_not_called()
        self.page.open.assert_not_called()

    def test_local_storage_disabled_changes_only_target_then_saves_and_reopens(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": False,
            "IndexedDB": True,
        }
        self.page.local_storage_data_sync_enabled.return_value = False
        self.page.checkbox_states.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": True,
        }

        changed = self.page.ensure_local_storage_data_sync_enabled()

        self.assertTrue(changed)
        self.assertEqual(
            self.cdp.click_element_by_script.call_args_list,
            [
                mock.call("LOCAL_STORAGE_CHECKBOX_SCRIPT"),
                mock.call("SAVE_BUTTON_SCRIPT"),
            ],
        )
        self.page._wait_save_finished.assert_called_once_with()
        self.page.open.assert_called_once_with()
        self.assertEqual(self.page._wait_for_local_storage_data_sync.call_count, 2)
        self.assertEqual(
            self.page._wait_local_storage_data_sync_enabled.call_args_list,
            [mock.call(True), mock.call(True)],
        )

    def test_unexpected_other_checkbox_change_fails_before_save(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": False,
            "IndexedDB": True,
        }
        self.page.local_storage_data_sync_enabled.return_value = False
        self.page.checkbox_states.return_value = {
            "Cookie": False,
            "Local Storage": True,
            "IndexedDB": True,
        }

        with self.assertRaisesRegex(AssertionError, "unexpected global settings checkbox changes"):
            self.page.ensure_local_storage_data_sync_enabled()

        self.cdp.click_element_by_script.assert_called_once_with("LOCAL_STORAGE_CHECKBOX_SCRIPT")
        self.page._wait_save_finished.assert_not_called()
        self.page.open.assert_not_called()

    def test_local_storage_already_disabled_does_not_modify_or_save(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": False,
            "IndexedDB": True,
        }
        self.page.local_storage_data_sync_enabled.return_value = False

        changed = self.page.ensure_local_storage_data_sync_disabled()

        self.assertFalse(changed)
        self.cdp.click_element_by_script.assert_not_called()
        self.page.open.assert_not_called()

    def test_local_storage_enabled_changes_only_target_then_saves_and_reopens(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": True,
        }
        self.page.local_storage_data_sync_enabled.return_value = True
        self.page.checkbox_states.return_value = {
            "Cookie": True,
            "Local Storage": False,
            "IndexedDB": True,
        }

        changed = self.page.ensure_local_storage_data_sync_disabled()

        self.assertTrue(changed)
        self.assertEqual(
            self.cdp.click_element_by_script.call_args_list,
            [
                mock.call("LOCAL_STORAGE_CHECKBOX_SCRIPT"),
                mock.call("SAVE_BUTTON_SCRIPT"),
            ],
        )
        self.page._wait_save_finished.assert_called_once_with()
        self.page.open.assert_called_once_with()
        self.assertEqual(self.page._wait_for_local_storage_data_sync.call_count, 2)
        self.assertEqual(
            self.page._wait_local_storage_data_sync_enabled.call_args_list,
            [mock.call(False), mock.call(False)],
        )

    def test_local_storage_disable_unexpected_other_checkbox_change_fails_before_save(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": True,
        }
        self.page.local_storage_data_sync_enabled.return_value = True
        self.page.checkbox_states.return_value = {
            "Cookie": False,
            "Local Storage": False,
            "IndexedDB": True,
        }

        with self.assertRaisesRegex(AssertionError, "unexpected global settings checkbox changes"):
            self.page.ensure_local_storage_data_sync_disabled()

        self.cdp.click_element_by_script.assert_called_once_with("LOCAL_STORAGE_CHECKBOX_SCRIPT")
        self.page._wait_save_finished.assert_not_called()
        self.page.open.assert_not_called()

    def test_indexeddb_already_enabled_does_not_modify_or_save(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": True,
        }
        self.page.indexeddb_data_sync_enabled.return_value = True

        changed = self.page.ensure_indexeddb_data_sync_enabled()

        self.assertFalse(changed)
        self.cdp.click_element_by_script.assert_not_called()
        self.page.open.assert_not_called()

    def test_indexeddb_disabled_changes_only_target_then_saves_and_reopens(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": False,
        }
        self.page.indexeddb_data_sync_enabled.return_value = False
        self.page.checkbox_states.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": True,
        }

        changed = self.page.ensure_indexeddb_data_sync_enabled()

        self.assertTrue(changed)
        self.assertEqual(
            self.cdp.click_element_by_script.call_args_list,
            [
                mock.call("INDEXEDDB_CHECKBOX_SCRIPT"),
                mock.call("SAVE_BUTTON_SCRIPT"),
            ],
        )
        self.page._wait_save_finished.assert_called_once_with()
        self.page.open.assert_called_once_with()
        self.assertEqual(self.page._wait_for_indexeddb_data_sync.call_count, 2)
        self.assertEqual(
            self.page._wait_indexeddb_data_sync_enabled.call_args_list,
            [mock.call(True), mock.call(True)],
        )

    def test_indexeddb_unexpected_other_checkbox_change_fails_before_save(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": False,
        }
        self.page.indexeddb_data_sync_enabled.return_value = False
        self.page.checkbox_states.return_value = {
            "Cookie": True,
            "Local Storage": False,
            "IndexedDB": True,
        }

        with self.assertRaisesRegex(AssertionError, "unexpected global settings checkbox changes"):
            self.page.ensure_indexeddb_data_sync_enabled()

        self.cdp.click_element_by_script.assert_called_once_with("INDEXEDDB_CHECKBOX_SCRIPT")
        self.page._wait_save_finished.assert_not_called()
        self.page.open.assert_not_called()

    def test_indexeddb_already_disabled_does_not_modify_or_save(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": False,
        }
        self.page.indexeddb_data_sync_enabled.return_value = False

        changed = self.page.ensure_indexeddb_data_sync_disabled()

        self.assertFalse(changed)
        self.cdp.click_element_by_script.assert_not_called()
        self.page.open.assert_not_called()

    def test_indexeddb_enabled_changes_only_target_then_saves_and_reopens(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": True,
        }
        self.page.indexeddb_data_sync_enabled.return_value = True
        self.page.checkbox_states.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": False,
        }

        changed = self.page.ensure_indexeddb_data_sync_disabled()

        self.assertTrue(changed)
        self.assertEqual(
            self.cdp.click_element_by_script.call_args_list,
            [
                mock.call("INDEXEDDB_CHECKBOX_SCRIPT"),
                mock.call("SAVE_BUTTON_SCRIPT"),
            ],
        )
        self.page._wait_save_finished.assert_called_once_with()
        self.page.open.assert_called_once_with()
        self.assertEqual(self.page._wait_for_indexeddb_data_sync.call_count, 2)
        self.assertEqual(
            self.page._wait_indexeddb_data_sync_enabled.call_args_list,
            [mock.call(False), mock.call(False)],
        )

    def test_indexeddb_disable_unexpected_other_checkbox_change_fails_before_save(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = {
            "Cookie": True,
            "Local Storage": True,
            "IndexedDB": True,
        }
        self.page.indexeddb_data_sync_enabled.return_value = True
        self.page.checkbox_states.return_value = {
            "Cookie": True,
            "Local Storage": False,
            "IndexedDB": False,
        }

        with self.assertRaisesRegex(AssertionError, "unexpected global settings checkbox changes"):
            self.page.ensure_indexeddb_data_sync_disabled()

        self.cdp.click_element_by_script.assert_called_once_with("INDEXEDDB_CHECKBOX_SCRIPT")
        self.page._wait_save_finished.assert_not_called()
        self.page.open.assert_not_called()

    def test_configure_clear_all_cache_every_open_sync_cloud_saves_and_reopens(self) -> None:
        self.page.configure_clear_all_local_cache_every_open_sync_cloud_data()

        self.page._wait_for_clear_local_cache_settings.assert_called_once_with()
        self.assertEqual(
            self.page._select_global_settings_form_select_option.call_args_list,
            [
                mock.call("清除方式", "清除本地全部缓存"),
                mock.call("清除频率", "每次打开环境时都清除"),
            ],
        )
        self.page._set_clear_local_cache_sync_cloud_enabled.assert_called_once_with(True)
        self.page._close_select_dropdowns.assert_called_once_with()
        self.cdp.click_element_by_script.assert_called_once_with("SAVE_BUTTON_SCRIPT")
        self.page._wait_save_finished.assert_called_once_with()
        self.page.open.assert_called_once_with(force_reentry=True)
        self.assertEqual(
            self.page._wait_global_settings_form_select_value.call_args_list,
            [
                mock.call("清除方式", "清除本地全部缓存"),
                mock.call("清除频率", "每次打开环境时都清除"),
            ],
        )
        self.page._wait_clear_local_cache_sync_cloud_enabled.assert_called_once_with(True)

    def test_configure_clear_all_cache_every_open_sync_cloud_already_target_skips_save(self) -> None:
        self.page.clear_local_cache_state.return_value = {
            "clear_method": "清除本地全部缓存",
            "clear_frequency": "每次打开环境时都清除",
            "sync_cloud_data": True,
        }

        self.page.configure_clear_all_local_cache_every_open_sync_cloud_data()

        self.page._wait_for_clear_local_cache_settings.assert_called_once_with()
        self.page._select_global_settings_form_select_option.assert_not_called()
        self.page._set_clear_local_cache_sync_cloud_enabled.assert_not_called()
        self.cdp.click_element_by_script.assert_not_called()
        self.page._wait_save_finished.assert_not_called()
        self.page.open.assert_not_called()

    def test_configure_clear_all_cache_every_open_no_cloud_sync_saves_and_reopens(self) -> None:
        self.page.configure_clear_all_local_cache_every_open_no_cloud_sync_data()

        self.page._wait_for_clear_local_cache_settings.assert_called_once_with()
        self.assertEqual(
            self.page._select_global_settings_form_select_option.call_args_list,
            [
                mock.call("清除方式", "清除本地全部缓存"),
                mock.call("清除频率", "每次打开环境时都清除"),
            ],
        )
        self.page._set_clear_local_cache_sync_cloud_enabled.assert_called_once_with(False)
        self.page._close_select_dropdowns.assert_called_once_with()
        self.cdp.click_element_by_script.assert_called_once_with("SAVE_BUTTON_SCRIPT")
        self.page._wait_save_finished.assert_called_once_with()
        self.page.open.assert_called_once_with(force_reentry=True)
        self.assertEqual(
            self.page._wait_global_settings_form_select_value.call_args_list,
            [
                mock.call("清除方式", "清除本地全部缓存"),
                mock.call("清除频率", "每次打开环境时都清除"),
            ],
        )
        self.page._wait_clear_local_cache_sync_cloud_enabled.assert_called_once_with(False)

    def test_configure_clear_local_cache_no_clear_saves_and_reopens(self) -> None:
        self.page.configure_clear_local_cache_no_clear()

        self.page._wait_for_clear_local_cache_settings.assert_called_once_with()
        self.page._select_global_settings_form_select_option.assert_called_once_with("清除方式", "不清除")
        self.page._close_select_dropdowns.assert_called_once_with()
        self.cdp.click_element_by_script.assert_called_once_with("SAVE_BUTTON_SCRIPT")
        self.page._wait_save_finished.assert_called_once_with()
        self.page.open.assert_called_once_with(force_reentry=True)
        self.page._wait_global_settings_form_select_value.assert_called_once_with("清除方式", "不清除")
        self.page._wait_clear_local_cache_sync_cloud_enabled.assert_not_called()

    def test_configure_clear_local_cache_no_clear_save_success_skips_reopen(self) -> None:
        self.page._wait_save_finished.return_value = True

        self.page.configure_clear_local_cache_no_clear()

        self.page._wait_for_clear_local_cache_settings.assert_called_once_with()
        self.page._select_global_settings_form_select_option.assert_called_once_with("清除方式", "不清除")
        self.page._close_select_dropdowns.assert_called_once_with()
        self.cdp.click_element_by_script.assert_called_once_with("SAVE_BUTTON_SCRIPT")
        self.page._wait_save_finished.assert_called_once_with()
        self.page.open.assert_not_called()
        self.page._wait_global_settings_form_select_value.assert_not_called()
        self.page._wait_clear_local_cache_sync_cloud_enabled.assert_not_called()

    def test_configure_clear_local_cache_no_clear_already_target_skips_save(self) -> None:
        self.page.clear_local_cache_state.return_value = {"clear_method": "不清除"}

        self.page.configure_clear_local_cache_no_clear()

        self.page._wait_for_clear_local_cache_settings.assert_called_once_with()
        self.page._select_global_settings_form_select_option.assert_not_called()
        self.page._close_select_dropdowns.assert_not_called()
        self.cdp.click_element_by_script.assert_not_called()
        self.page._wait_save_finished.assert_not_called()
        self.page.open.assert_not_called()

    def test_restore_clear_local_cache_already_target_skips_save(self) -> None:
        self.page.clear_local_cache_state.return_value = {
            "clear_method": "清除本地全部缓存",
            "clear_frequency": "每次打开环境时都清除",
            "sync_cloud_data": False,
        }
        self.cdp.evaluate.return_value = False

        self.page.restore_clear_local_cache_state(
            {
                "clear_method": "清除本地全部缓存",
                "clear_frequency": "每次打开环境时都清除",
                "sync_cloud_data": False,
            }
        )

        self.page._wait_for_clear_local_cache_settings.assert_called_once_with()
        self.page._select_global_settings_form_select_option.assert_not_called()
        self.page._set_clear_local_cache_sync_cloud_enabled.assert_not_called()
        self.cdp.click_element_by_script.assert_not_called()
        self.page._wait_save_finished.assert_not_called()
        self.page.open.assert_not_called()

    def test_restore_global_settings_snapshot_already_target_skips_restore_steps(self) -> None:
        snapshot = {
            "schema_version": 1,
            "simple_checkboxes": {"禁止查看网站密码": True},
            "website_restriction": {"enabled": False},
            "packet_capture_blocking": {"enabled": False},
            "bookmark_setting": {"enabled": False, "restore_supported": True},
            "environment_field_display_limit": {"enabled": False},
            "environment_list_pagination": {"enabled": False},
            "environment_list_sort": {"enabled": False},
            "data_sync": {"cookie": True, "local_storage": True, "indexeddb": True, "one_way_enabled": False},
            "clear_local_cache": {"clear_method": "不清除"},
            "extension_tamper_protection": {"enabled": False},
        }
        self.page.capture_global_settings_snapshot = mock.MagicMock(return_value=snapshot)
        self.page.restore_extension_tamper_protection_state = mock.MagicMock()
        self.page._restore_simple_checkbox_snapshot = mock.MagicMock()
        self.page.restore_website_restriction_state = mock.MagicMock()
        self.page.restore_packet_capture_blocking_state = mock.MagicMock()
        self.page.restore_bookmark_setting_state = mock.MagicMock()
        self.page.restore_environment_field_display_limit_state = mock.MagicMock()
        self.page.restore_environment_list_pagination_setting_state = mock.MagicMock()
        self.page.restore_environment_list_sort_state = mock.MagicMock()
        self.page.restore_data_sync_one_way_state = mock.MagicMock()
        self.page.restore_clear_local_cache_state = mock.MagicMock()

        self.page.restore_global_settings_snapshot(snapshot)

        self.page.capture_global_settings_snapshot.assert_called_once_with()
        self.page.restore_extension_tamper_protection_state.assert_not_called()
        self.page._restore_simple_checkbox_snapshot.assert_not_called()
        self.page.restore_website_restriction_state.assert_not_called()
        self.page.restore_packet_capture_blocking_state.assert_not_called()
        self.page.restore_bookmark_setting_state.assert_not_called()
        self.page.restore_environment_field_display_limit_state.assert_not_called()
        self.page.restore_environment_list_pagination_setting_state.assert_not_called()
        self.page.restore_environment_list_sort_state.assert_not_called()
        self.page.restore_data_sync_one_way_state.assert_not_called()
        self.page.restore_clear_local_cache_state.assert_not_called()
        self.page.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
