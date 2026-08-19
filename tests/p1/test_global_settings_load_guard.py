from __future__ import annotations

import unittest
from unittest import mock

from pages.global_settings_page import GlobalSettingsPage


class TestGlobalSettingsLoadGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.cdp = mock.MagicMock()
        self.cdp.evaluate.return_value = False
        self.page = GlobalSettingsPage(cdp_driver=self.cdp, config={})
        self.page.locators = {
            "global_settings_menu_candidates": ".menu-item",
            "message_box": ".el-message-box",
            "dialog_or_message_box": ".el-dialog, .el-message-box",
        }
        self.page._dismiss_blocking_overlays = mock.MagicMock()
        self.page._global_settings_route_active = mock.MagicMock(return_value=False)
        self.page._wait_for_global_settings_page = mock.MagicMock()
        self.page._wait_for_global_settings_rendered = mock.MagicMock()
        self.page._wait_checkbox_states_stable = mock.MagicMock()
        self.page._open_environment_management_for_retry = mock.MagicMock()

    @staticmethod
    def _states(checked_count: int, unchecked_count: int = 0) -> dict[str, bool]:
        states = {f"checked-{index}": True for index in range(checked_count)}
        states.update({f"unchecked-{index}": False for index in range(unchecked_count)})
        return states

    def test_first_loaded_page_with_three_checked_checkboxes_is_accepted(self) -> None:
        self.page._wait_checkbox_states_stable.return_value = self._states(3, 2)

        self.page.open()

        self.page._open_environment_management_for_retry.assert_not_called()
        self.cdp.click_element_by_script.assert_called_once()
        self.page._wait_for_global_settings_rendered.assert_called_once_with()

    def test_current_global_settings_page_is_checked_without_reclicking_menu(self) -> None:
        self.page._global_settings_route_active.return_value = True
        self.page._wait_checkbox_states_stable.return_value = self._states(4)

        self.page.open()

        self.cdp.click_element_by_script.assert_not_called()
        self.page._open_environment_management_for_retry.assert_not_called()

    def test_retry_navigation_explicitly_opens_environment_management(self) -> None:
        self.page._wait_for_environment_management_page = mock.MagicMock()

        GlobalSettingsPage._open_environment_management_for_retry(self.page)

        click_script = self.cdp.click_element_by_script.call_args.args[0]
        self.assertIn("环境管理", click_script)
        self.page._wait_for_environment_management_page.assert_called_once_with()

    def test_one_bad_load_reenters_through_environment_management_then_passes(self) -> None:
        self.page._wait_checkbox_states_stable.side_effect = [self._states(2), self._states(3)]

        self.page.open()

        self.page._open_environment_management_for_retry.assert_called_once_with()
        self.assertEqual(self.cdp.click_element_by_script.call_count, 2)
        self.assertEqual(self.page._wait_for_global_settings_rendered.call_count, 2)

    def test_second_reentry_is_the_last_allowed_retry(self) -> None:
        self.page._wait_checkbox_states_stable.side_effect = [
            self._states(0, 3),
            self._states(1, 2),
            self._states(3),
        ]

        self.page.open()

        self.assertEqual(self.page._open_environment_management_for_retry.call_count, 2)
        self.assertEqual(self.cdp.click_element_by_script.call_count, 3)

    def test_fewer_than_three_checked_after_two_retries_fails_as_assertion(self) -> None:
        self.page._wait_checkbox_states_stable.side_effect = [
            self._states(0, 4),
            self._states(1, 3),
            self._states(2, 2),
        ]

        with self.assertRaisesRegex(
            AssertionError,
            "expected at least 3 checked checkboxes",
        ):
            self.page.open()

        self.assertEqual(self.page._open_environment_management_for_retry.call_count, 2)
        self.assertEqual(self.cdp.click_element_by_script.call_count, 3)


if __name__ == "__main__":
    unittest.main()
