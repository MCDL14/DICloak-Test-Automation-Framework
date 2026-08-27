from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

from core.global_settings_baseline import load_org_config_baseline
from core.org_config_api import OrgConfigIdentity, OrgConfigRequestError
from pages.global_settings_page import GlobalSettingsPage


class TestGlobalSettingsApiSave(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = load_org_config_baseline()
        self.cdp = mock.MagicMock()
        self.page = GlobalSettingsPage(cdp_driver=self.cdp, config={})
        self.client = mock.MagicMock()
        self.client.identity.return_value = OrgConfigIdentity(
            org_id="1849736955067023361",
            app_version="2.9.17",
        )
        self.client.get_org_config.return_value = copy.deepcopy(self.baseline)
        self.page._org_config_client = self.client
        self.page._recovery_session = mock.MagicMock()
        self.page._wait_until_not_loading = mock.MagicMock()
        self.page._visible_button_by_text_script = mock.MagicMock(
            return_value="SAVE_BUTTON_SCRIPT"
        )

    def _response(self, *, status: int = 200) -> dict[str, object]:
        return {
            "url": (
                "https://gin-server.dicloak.net/gin/v1/organization/"
                "1849736955067023361/org_config"
            ),
            "method": "POST",
            "post_data": json.dumps(self.baseline, ensure_ascii=False),
            "status": status,
            "response_body": json.dumps(
                {"code": 0, "msg": "成功", "data": None},
                ensure_ascii=False,
            ),
        }

    def test_wait_save_finished_records_post_and_verifies_get(self) -> None:
        self.page._wait_org_config_save_response = mock.MagicMock(
            return_value=self._response()
        )

        saved = self.page._wait_save_finished(timeout_seconds=1)

        self.assertTrue(saved)
        self.page._recovery_session.mark_write_attempted.assert_called_once_with()
        self.page._recovery_session.record_successful_post.assert_called_once_with(
            self.baseline
        )
        self.client.get_org_config.assert_called_once_with()
        self.cdp.click_element_by_script.assert_not_called()

    @mock.patch("pages.global_settings_page.time.sleep", return_value=None)
    def test_http_error_retries_by_clicking_save_again(self, _sleep: mock.MagicMock) -> None:
        self.page._wait_org_config_save_response = mock.MagicMock(
            side_effect=[self._response(status=500), self._response()]
        )

        saved = self.page._wait_save_finished(timeout_seconds=1)

        self.assertTrue(saved)
        self.cdp.click_element_by_script.assert_called_once_with("SAVE_BUTTON_SCRIPT")
        self.assertEqual(self.page._wait_org_config_save_response.call_count, 2)
        self.page._recovery_session.record_successful_post.assert_called_once_with(
            self.baseline
        )

    @mock.patch("pages.global_settings_page.time.sleep", return_value=None)
    def test_get_semantic_mismatch_is_not_reported_as_save_success(
        self,
        _sleep: mock.MagicMock,
    ) -> None:
        mismatched = copy.deepcopy(self.baseline)
        mismatched["env_page_config"]["status"] = True
        self.client.get_org_config.return_value = mismatched
        self.page._wait_org_config_save_response = mock.MagicMock(
            return_value=self._response()
        )

        with self.assertRaisesRegex(
            AssertionError,
            "global settings UI save GET verification mismatch",
        ):
            self.page._wait_save_finished(timeout_seconds=1)

        self.assertEqual(self.client.get_org_config.call_count, 3)
        self.cdp.click_element_by_script.assert_not_called()

    def test_exhausted_transport_errors_raise_request_error(self) -> None:
        self.page.SAVE_ATTEMPTS = 1
        self.page._wait_org_config_save_response = mock.MagicMock(
            side_effect=TimeoutError("capture timeout")
        )

        with self.assertRaisesRegex(
            OrgConfigRequestError,
            "global settings UI save failed after 1 attempts",
        ):
            self.page._wait_save_finished(timeout_seconds=1)


if __name__ == "__main__":
    unittest.main()
