from __future__ import annotations

import json
import unittest
from unittest import mock

from core.environment_create_api import (
    ENVIRONMENT_BATCH_DELETE_API_URL,
    ENVIRONMENT_CREATE_API_URL,
    ENVIRONMENT_LIST_API_URL,
    EnvironmentCreateApiClient,
    EnvironmentCreateRequestError,
    build_environment_create_payload,
    build_environment_delete_payload,
    build_environment_list_payload,
    environment_id_from_create_response,
    environment_records_from_list_response,
    load_environment_create_payload_template,
    validate_environment_create_response,
    validate_environment_delete_response,
    validate_environment_list_response,
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

    def test_build_delete_payload_normalizes_and_deduplicates_ids(self) -> None:
        self.assertEqual(
            build_environment_delete_payload(
                [" environment-01 ", "environment-02", "environment-01"]
            ),
            {"ids": ["environment-01", "environment-02"]},
        )
        self.assertEqual(
            build_environment_delete_payload("environment-01"),
            {"ids": ["environment-01"]},
        )

    def test_build_delete_payload_rejects_empty_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "environment ids are empty"):
            build_environment_delete_payload([])
        with self.assertRaisesRegex(ValueError, "environment id is empty"):
            build_environment_delete_payload(["environment-01", " "])

    def test_build_list_payload_defaults_and_variable_fields(self) -> None:
        self.assertEqual(
            build_environment_list_payload(),
            {
                "page_size": 10,
                "page_no": 1,
                "env_tag_list_type": "CONTAIN",
                "order_by": "ENV_SERIAL_NUM",
                "sort": "DESC",
                "detail": True,
            },
        )
        self.assertNotIn("value", build_environment_list_payload(value="   "))
        self.assertEqual(
            build_environment_list_payload(
                page_size=50,
                page_no=3,
                env_tag_list_type=" NOT_CONTAIN ",
                order_by=" CREATE_TIME ",
                sort=" ASC ",
                detail=False,
                value=" 自动化-接口环境 ",
            ),
            {
                "page_size": 50,
                "page_no": 3,
                "env_tag_list_type": "NOT_CONTAIN",
                "order_by": "CREATE_TIME",
                "sort": "ASC",
                "detail": False,
                "value": "自动化-接口环境",
            },
        )

    def test_build_list_payload_rejects_invalid_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "page_size must be a positive integer"):
            build_environment_list_payload(page_size=0)
        with self.assertRaisesRegex(ValueError, "page_no must be a positive integer"):
            build_environment_list_payload(page_no="invalid")
        with self.assertRaisesRegex(ValueError, "order_by is empty"):
            build_environment_list_payload(order_by=" ")
        with self.assertRaisesRegex(ValueError, "detail must be a boolean"):
            build_environment_list_payload(detail="true")  # type: ignore[arg-type]


class EnvironmentCreateApiClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cdp = mock.MagicMock()
        self.cdp.evaluate.return_value = {
            "has_token": True,
            "app_version": "2.9.21",
        }

    def test_identity_requires_current_token_and_app_version(self) -> None:
        client = EnvironmentCreateApiClient(self.cdp, device_id="current-device-id")
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
        client = EnvironmentCreateApiClient(self.cdp, device_id="current-device-id")

        response = client.create_environment(
            name="自动化-接口创建环境",
            browser_version_id="142",
            remark=None,
        )

        self.assertEqual(response["data"]["id"], "environment-id")
        self.assertEqual(client.last_created_environment_id, "environment-id")
        self.assertEqual(client.created_environment_ids, ["environment-id"])
        request_script = self.cdp.evaluate_with_args.call_args.args[0]
        request_args = self.cdp.evaluate_with_args.call_args.args[1]
        self.assertIn('"x-token": token', request_script)
        self.assertIn('"x-version": version', request_script)
        self.assertIn('headers["x-device-id"] = deviceId', request_script)
        self.assertIn('mode: "cors"', request_script)
        self.assertIn('credentials: "omit"', request_script)
        self.assertIn('referrerPolicy: "strict-origin-when-cross-origin"', request_script)
        self.assertEqual(request_args["apiUrl"], ENVIRONMENT_CREATE_API_URL)
        self.assertEqual(request_args["version"], "2.9.21")
        self.assertEqual(request_args["deviceId"], "current-device-id")
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
                "response_body": '{"code":0,"msg":"成功","data":{"id":"environment-id"}}',
                "error": "",
            },
        ]
        client = EnvironmentCreateApiClient(self.cdp, attempts=3)

        client.create_environment(name="自动化-接口重试环境")

        self.assertEqual(self.cdp.evaluate_with_args.call_count, 2)

    def test_create_requires_and_saves_response_data_id(self) -> None:
        self.assertEqual(
            environment_id_from_create_response({"data": {"id": " environment-id "}}),
            "environment-id",
        )
        with self.assertRaisesRegex(EnvironmentCreateRequestError, "data.id is unavailable"):
            environment_id_from_create_response({"data": {}})
        with self.assertRaisesRegex(EnvironmentCreateRequestError, "data is not an object"):
            environment_id_from_create_response({"data": None})

    def test_batch_delete_uses_current_identity_delete_method_url_and_ids_body(
        self,
    ) -> None:
        self.cdp.evaluate_with_args.return_value = {
            "status": 200,
            "response_body": '{"code":0,"msg":"成功","data":null}',
            "error": "",
        }
        client = EnvironmentCreateApiClient(self.cdp, device_id="current-device-id")

        response = client.delete_environments(["environment-01", "environment-02"])

        self.assertEqual(response["code"], 0)
        request_script = self.cdp.evaluate_with_args.call_args.args[0]
        request_args = self.cdp.evaluate_with_args.call_args.args[1]
        self.assertIn('"x-token": token', request_script)
        self.assertIn('"x-version": version', request_script)
        self.assertIn('headers["x-device-id"] = deviceId', request_script)
        self.assertEqual(request_args["method"], "DELETE")
        self.assertEqual(request_args["apiUrl"], ENVIRONMENT_BATCH_DELETE_API_URL)
        self.assertEqual(request_args["version"], "2.9.21")
        self.assertEqual(request_args["deviceId"], "current-device-id")
        self.assertEqual(
            request_args["payload"],
            {"ids": ["environment-01", "environment-02"]},
        )
        self.assertNotIn("token", request_args)

    def test_successful_delete_removes_saved_created_ids(self) -> None:
        self.cdp.evaluate_with_args.return_value = {
            "status": 200,
            "response_body": '{"code":0,"msg":"成功","data":null}',
            "error": "",
        }
        client = EnvironmentCreateApiClient(self.cdp, device_id="current-device-id")
        client.created_environment_ids = ["environment-01", "environment-02"]
        client.last_created_environment_id = "environment-02"

        client.delete_environments(["environment-02"])

        self.assertEqual(client.created_environment_ids, ["environment-01"])
        self.assertEqual(client.last_created_environment_id, "")

    def test_list_uses_current_identity_post_method_url_and_payload(self) -> None:
        self.cdp.evaluate_with_args.return_value = {
            "status": 200,
            "response_body": '{"code":0,"msg":"成功","data":{"list":[]}}',
            "error": "",
        }
        client = EnvironmentCreateApiClient(self.cdp, device_id="current-device-id")

        response = client.list_environments(
            page_size=20,
            page_no=2,
            detail=False,
            value="自动化-筛选环境",
        )

        self.assertEqual(response["data"], {"list": []})
        request_script = self.cdp.evaluate_with_args.call_args.args[0]
        request_args = self.cdp.evaluate_with_args.call_args.args[1]
        self.assertIn('"x-token": token', request_script)
        self.assertIn('"x-version": version', request_script)
        self.assertIn('headers["x-device-id"] = deviceId', request_script)
        self.assertEqual(request_args["method"], "POST")
        self.assertEqual(request_args["apiUrl"], ENVIRONMENT_LIST_API_URL)
        self.assertEqual(request_args["version"], "2.9.21")
        self.assertEqual(request_args["deviceId"], "current-device-id")
        self.assertEqual(
            request_args["payload"],
            {
                "page_size": 20,
                "page_no": 2,
                "env_tag_list_type": "CONTAIN",
                "order_by": "ENV_SERIAL_NUM",
                "sort": "DESC",
                "detail": False,
                "value": "自动化-筛选环境",
            },
        )
        self.assertNotIn("token", request_args)

    def test_environment_ids_by_name_uses_exact_name_and_supported_id_fields(self) -> None:
        self.cdp.evaluate_with_args.return_value = {
            "status": 200,
            "response_body": json.dumps(
                {
                    "code": 0,
                    "data": {
                        "list": [
                            {"id": "environment-01", "name": "目标环境"},
                            {"env_id": "environment-02", "env_name": "目标环境"},
                            {"id": "environment-03", "name": "目标环境-相似名称"},
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            "error": "",
        }
        client = EnvironmentCreateApiClient(self.cdp)

        self.assertEqual(
            client.environment_ids_by_name("目标环境"),
            ["environment-01", "environment-02"],
        )
        request_args = self.cdp.evaluate_with_args.call_args.args[1]
        self.assertEqual(request_args["payload"]["value"], "目标环境")


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

    def test_delete_response_uses_same_http_and_business_contract(self) -> None:
        self.assertEqual(
            validate_environment_delete_response(
                status=200,
                response_body='{"code":0,"msg":"成功","data":null}',
            )["code"],
            0,
        )
        with self.assertRaisesRegex(
            EnvironmentCreateRequestError,
            "batch delete business response failed",
        ):
            validate_environment_delete_response(
                status=200,
                response_body='{"code":1,"msg":"failed"}',
            )

    def test_list_response_uses_same_http_and_business_contract(self) -> None:
        self.assertEqual(
            validate_environment_list_response(
                status=200,
                response_body='{"code":0,"msg":"成功","data":{"list":[]}}',
            )["data"],
            {"list": []},
        )
        with self.assertRaisesRegex(
            EnvironmentCreateRequestError,
            "list business response failed",
        ):
            validate_environment_list_response(
                status=200,
                response_body='{"code":1,"msg":"failed"}',
            )

    def test_list_record_extraction_accepts_common_containers_and_rejects_missing_list(
        self,
    ) -> None:
        self.assertEqual(
            environment_records_from_list_response(
                {"data": {"list": [{"id": "environment-01"}]}}
            ),
            [{"id": "environment-01"}],
        )
        self.assertEqual(
            environment_records_from_list_response(
                {"data": [{"id": "environment-02"}]}
            ),
            [{"id": "environment-02"}],
        )
        with self.assertRaisesRegex(
            EnvironmentCreateRequestError,
            "does not contain a record list",
        ):
            environment_records_from_list_response({"data": {"total": 0}})


if __name__ == "__main__":
    unittest.main()
