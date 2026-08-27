from __future__ import annotations

import copy
import unittest
from unittest import mock

from core.global_settings_baseline import (
    ORG_CONFIG_COMPARE_BLOCKS,
    ORG_CONFIG_EXPECTED_BLOCKS,
    load_org_config_baseline,
)
from core.global_settings_recovery import (
    GlobalSettingsRecoverySession,
    build_complete_restore_payload,
)
from core.org_config_api import (
    OrgConfigApiClient,
    OrgConfigRequestError,
    parse_org_config_post_data,
    validate_org_config_response,
)
from core.org_config_semantics import semantic_org_config_diff


class OrgConfigSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = load_org_config_baseline()

    def test_complete_baseline_keeps_21_blocks_and_compare_scope_keeps_10(self) -> None:
        self.assertEqual(set(self.baseline), set(ORG_CONFIG_EXPECTED_BLOCKS))
        self.assertEqual(len(self.baseline), 21)
        self.assertEqual(len(ORG_CONFIG_COMPARE_BLOCKS), 10)

    def test_disabled_status_ignores_inactive_content(self) -> None:
        actual = copy.deepcopy(self.baseline)
        actual["access_limit"]["url_list"] = "https://ignored.example"
        actual["access_limit"]["quick_selection_option"] = [99]

        self.assertEqual(semantic_org_config_diff(self.baseline, actual), [])

    def test_enabled_status_compares_active_content(self) -> None:
        expected = copy.deepcopy(self.baseline)
        actual = copy.deepcopy(self.baseline)
        expected["access_limit"]["status"] = True
        actual["access_limit"]["status"] = True
        expected["access_limit"]["url_list"] = "https://expected.example"
        actual["access_limit"]["url_list"] = "https://actual.example"

        paths = [diff.path for diff in semantic_org_config_diff(expected, actual)]

        self.assertIn("access_limit.url_list", paths)

    def test_local_data_no_clear_only_compares_type(self) -> None:
        actual = copy.deepcopy(self.baseline)
        actual["local_data_config"].update(
            {
                "browser_type": "other",
                "data_type": 99,
                "synchronize": True,
                "frequency": 99,
                "interval": 99,
            }
        )

        self.assertEqual(semantic_org_config_diff(self.baseline, actual), [])

    def test_bitmask_scope_only_compares_affected_bits(self) -> None:
        expected = copy.deepcopy(self.baseline)
        actual = copy.deepcopy(self.baseline)
        actual["browser_config"]["type"] ^= 0b1100

        self.assertEqual(
            semantic_org_config_diff(
                expected,
                actual,
                blocks=("browser_config",),
                bit_masks={"browser_config.type": 0b0010},
            ),
            [],
        )
        self.assertTrue(
            semantic_org_config_diff(
                expected,
                actual,
                blocks=("browser_config",),
                bit_masks={"browser_config.type": 0b0100},
            )
        )


class OrgConfigRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = load_org_config_baseline()

    def test_complete_restore_payload_preserves_unaffected_and_merges_mask(self) -> None:
        current = copy.deepcopy(self.baseline)
        current["env_config"]["remote_inspector_type"] = False
        current["browser_config"]["type"] = 0b1111
        baseline = copy.deepcopy(self.baseline)
        baseline["browser_config"]["type"] = 0b0001

        payload = build_complete_restore_payload(
            current=current,
            baseline=baseline,
            restore_blocks=("browser_config",),
            bit_masks={"browser_config": 0b0100},
        )

        self.assertEqual(set(payload), set(ORG_CONFIG_EXPECTED_BLOCKS))
        self.assertFalse(payload["env_config"]["remote_inspector_type"])
        self.assertEqual(payload["browser_config"]["type"], 0b1011)

    def test_preflight_posts_complete_baseline_only_when_mismatched(self) -> None:
        mismatched = copy.deepcopy(self.baseline)
        mismatched["env_page_config"]["status"] = True
        client = mock.MagicMock()
        client.get_org_config.side_effect = [mismatched, copy.deepcopy(self.baseline)]
        cdp = mock.MagicMock()

        session = GlobalSettingsRecoverySession(
            cdp,
            affected_blocks={"env_page_config"},
            api_client=client,
            baseline=self.baseline,
        )
        session.ensure_baseline_before_case()

        client.post_org_config.assert_called_once_with(self.baseline)

    def test_restore_skips_post_when_case_flow_already_restored(self) -> None:
        client = mock.MagicMock()
        client.get_org_config.return_value = copy.deepcopy(self.baseline)
        session = GlobalSettingsRecoverySession(
            mock.MagicMock(),
            affected_blocks={"browser_config"},
            bitmask_blocks={"browser_config"},
            api_client=client,
            baseline=self.baseline,
        )
        changed = copy.deepcopy(self.baseline)
        changed["browser_config"]["type"] ^= 0b100
        session.record_successful_post(changed)

        session.restore_if_needed()

        client.post_org_config.assert_not_called()


class OrgConfigProtocolTests(unittest.TestCase):
    def test_parse_post_data_requires_json_object(self) -> None:
        self.assertEqual(parse_org_config_post_data('{"browser_config":{"type":1}}')["browser_config"], {"type": 1})
        with self.assertRaises(OrgConfigRequestError):
            parse_org_config_post_data("[]")

    def test_response_requires_http_200_and_business_code_zero(self) -> None:
        self.assertEqual(
            validate_org_config_response(status=200, response_body='{"code":0,"data":null}')["code"],
            0,
        )
        with self.assertRaises(OrgConfigRequestError):
            validate_org_config_response(status=500, response_body='{"code":0}')
        with self.assertRaises(OrgConfigRequestError):
            validate_org_config_response(status=200, response_body='{"code":1,"msg":"failed"}')

    @mock.patch("core.org_config_api.time.sleep", return_value=None)
    def test_client_retries_http_errors_and_omits_device_id(
        self,
        _sleep: mock.MagicMock,
    ) -> None:
        cdp = mock.MagicMock()
        cdp.evaluate.return_value = {
            "has_token": True,
            "org_id": "1849736955067023361",
            "app_version": "2.9.17",
        }
        cdp.evaluate_with_args.side_effect = [
            {"status": 500, "response_body": '{"code":0}', "error": ""},
            {
                "status": 200,
                "response_body": '{"code":0,"msg":"成功","data":null}',
                "error": "",
            },
        ]
        client = OrgConfigApiClient(cdp, attempts=3)

        client.post_org_config({"browser_config": {"type": 32769}})

        self.assertEqual(cdp.evaluate_with_args.call_count, 2)
        request_script = cdp.evaluate_with_args.call_args.args[0]
        request_args = cdp.evaluate_with_args.call_args.args[1]
        self.assertNotIn("X-Device-Id", request_script)
        self.assertNotIn("token", request_args)

    @mock.patch("core.org_config_api.time.sleep", return_value=None)
    def test_client_stops_after_three_failed_attempts(
        self,
        _sleep: mock.MagicMock,
    ) -> None:
        cdp = mock.MagicMock()
        cdp.evaluate.return_value = {
            "has_token": True,
            "org_id": "1849736955067023361",
            "app_version": "2.9.17",
        }
        cdp.evaluate_with_args.return_value = {
            "status": 503,
            "response_body": '{"code":0}',
            "error": "",
        }
        client = OrgConfigApiClient(cdp, attempts=3)

        with self.assertRaisesRegex(OrgConfigRequestError, "failed after 3 attempts"):
            client.post_org_config({"browser_config": {"type": 32769}})

        self.assertEqual(cdp.evaluate_with_args.call_count, 3)


if __name__ == "__main__":
    unittest.main()
