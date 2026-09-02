from __future__ import annotations

import json
import unittest
from unittest import mock

from core.environment_create_api import (
    ENVIRONMENT_CREATE_API_URL,
    EnvironmentCreateApiClient,
    EnvironmentCreateRequestError,
    build_environment_create_payload,
    load_environment_create_payload_template,
    validate_environment_create_response,
)


class EnvironmentCreatePayloadTests(unittest.TestCase):
    def test_template_keeps_reference_request_fixed_fields_only(self) -> None:
        template = load_environment_create_payload_template()

        self.assertEqual(len(template), 40)
        self.assertNotIn("browser_version_id", template)
        self.assertNotIn("name", template)
        self.assertNotIn("remark", template)
        self.assertEqual(template["browser"], "CHROME")
        self.assertEqual(template["proxy_type"], "NON_USE")
        self.assertIn("config", template)

    def test_build_payload_overrides_version_name_and_adds_remark(self) -> None:
        payload = build_environment_create_payload(
            name="自动化-接口创建环境",
            browser_version_id="142",
            remark="自动化-接口创建环境备注",
        )

        self.assertEqual(payload["browser_version_id"], "142")
        self.assertEqual(payload["name"], "自动化-接口创建环境")
        self.assertEqual(payload["remark"], "自动化-接口创建环境备注")
        self.assertEqual(len(payload), 43)

    def test_build_payload_omits_blank_remark(self) -> None:
        payload = build_environment_create_payload(
            name="自动化-无备注接口环境",
            browser_version_id="134",
            remark="   ",
        )

        self.assertEqual(payload["browser_version_id"], "134")
        self.assertNotIn("remark", payload)
        self.assertEqual(len(payload), 42)

    def test_build_payload_rejects_empty_variable_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "environment name is empty"):
            build_environment_create_payload(name="", browser_version_id="142")
        with self.assertRaisesRegex(ValueError, "browser_version_id is empty"):
            build_environment_create_payload(name="环境", browser_version_id="")


class EnvironmentCreateApiClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cdp = mock.MagicMock()
        self.cdp.evaluate.return_value = {
            "has_token": True,
            "app_version": "2.9.21",
        }

    def test_identity_requires_current_token_and_app_version(self) -> None:
        client = EnvironmentCreateApiClient(self.cdp)
        self.assertEqual(client.identity().app_version, "2.9.21")

        self.cdp.evaluate.return_value = {"has_token": False, "app_version": "2.9.21"}
        with self.assertRaisesRegex(EnvironmentCreateRequestError, "token is unavailable"):
            client.identity()

        self.cdp.evaluate.return_value = {"has_token": True, "app_version": ""}
        with self.assertRaisesRegex(EnvironmentCreateRequestError, "version is unavailable"):
            client.identity()

    def test_create_uses_app_token_in_page_context_and_version_in_header(self) -> None:
        self.cdp.evaluate_with_args.return_value = {
            "status": 200,
            "response_body": json.dumps(
                {"code": 0, "msg": "成功", "data": {"id": "environment-id"}},
                ensure_ascii=False,
            ),
            "error": "",
        }
        client = EnvironmentCreateApiClient(self.cdp)

        response = client.create_environment(
            name="自动化-接口创建环境",
            browser_version_id="142",
            remark=None,
        )

        self.assertEqual(response["data"]["id"], "environment-id")
        request_script = self.cdp.evaluate_with_args.call_args.args[0]
        request_args = self.cdp.evaluate_with_args.call_args.args[1]
        self.assertIn('"x-token": token', request_script)
        self.assertIn('"x-version": version', request_script)
        self.assertEqual(request_args["apiUrl"], ENVIRONMENT_CREATE_API_URL)
        self.assertEqual(request_args["version"], "2.9.21")
        self.assertEqual(request_args["payload"]["browser_version_id"], "142")
        self.assertEqual(request_args["payload"]["name"], "自动化-接口创建环境")
        self.assertNotIn("remark", request_args["payload"])
        self.assertNotIn("token", request_args)

    @mock.patch("core.environment_create_api.time.sleep", return_value=None)
    def test_create_retries_transport_or_http_errors(self, _sleep: mock.MagicMock) -> None:
        self.cdp.evaluate_with_args.side_effect = [
            {"status": 503, "response_body": '{"code":0}', "error": ""},
            {
                "status": 200,
                "response_body": '{"code":0,"msg":"成功","data":null}',
                "error": "",
            },
        ]
        client = EnvironmentCreateApiClient(self.cdp, attempts=3)

        client.create_environment(name="自动化-接口重试环境")

        self.assertEqual(self.cdp.evaluate_with_args.call_count, 2)


class EnvironmentCreateResponseTests(unittest.TestCase):
    def test_response_requires_http_200_json_object_and_business_code_zero(self) -> None:
        self.assertEqual(
            validate_environment_create_response(
                status=200,
                response_body='{"code":0,"msg":"成功","data":null}',
            )["code"],
            0,
        )
        with self.assertRaisesRegex(EnvironmentCreateRequestError, "HTTP status"):
            validate_environment_create_response(status=500, response_body='{"code":0}')
        with self.assertRaisesRegex(EnvironmentCreateRequestError, "not valid JSON"):
            validate_environment_create_response(status=200, response_body="not-json")
        with self.assertRaisesRegex(EnvironmentCreateRequestError, "business response failed"):
            validate_environment_create_response(
                status=200,
                response_body='{"code":1,"msg":"failed"}',
            )


if __name__ == "__main__":
    unittest.main()
