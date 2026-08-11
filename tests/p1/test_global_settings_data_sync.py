from __future__ import annotations

import unittest
from unittest import mock

from pages.global_settings_page import GlobalSettingsPage


class TestGlobalSettingsDataSync(unittest.TestCase):
    def setUp(self) -> None:
        self.cdp = mock.MagicMock()
        self.page = GlobalSettingsPage(cdp_driver=self.cdp, config={})
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
        self.page._wait_save_finished = mock.MagicMock()
        self.page.open = mock.MagicMock()

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


if __name__ == "__main__":
    unittest.main()
