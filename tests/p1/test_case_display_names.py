from __future__ import annotations

import unittest
from unittest import mock

import streamlit_runner
from core.case_display import case_display_name


class _FakeTest:
    def __init__(self, test_id: str):
        self._test_id = test_id

    def id(self) -> str:
        return self._test_id


class _FakeRunner:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

    def _build_suite(self, level=None, module=None, case=None):
        return object()

    def _iter_tests(self, suite):
        yield _FakeTest(
            "tests.p0.environment_management.test_02_create_default_environment."
            "TestCreateDefaultEnvironment.test_create_open_close_delete_default_environment"
        )


class CaseDisplayNameTests(unittest.TestCase):
    def test_known_case_method_maps_to_chinese_name(self) -> None:
        display_name = case_display_name(
            "tests.p0.extension_management.test_04_hide_extension."
            "TestHideExtension.test_hide_extension_from_chrome_extensions_page"
        )

        self.assertEqual(display_name, "隐藏扩展并验证扩展页不可见")

    def test_unknown_method_has_readable_fallback(self) -> None:
        display_name = case_display_name(
            "tests.p0.proxy_management.test_99_probe."
            "TestProbe.test_create_proxy_and_delete"
        )

        self.assertEqual(display_name, "创建 代理 并 删除")

    def test_global_setting_open_block_cases_have_chinese_names(self) -> None:
        expected_names = {
            "test_proxy_check_failure_not_open_environment": "代理检测失败时阻止打开环境",
            "test_country_mismatch_not_open_browser": "国家或地区不一致时阻止打开浏览器",
        }

        for method_name, expected_name in expected_names.items():
            with self.subTest(method_name=method_name):
                self.assertEqual(case_display_name(method_name), expected_name)

    def test_custom_proxy_case_name_mentions_connectivity(self) -> None:
        self.assertEqual(
            case_display_name("test_create_custom_proxy_environment_open_close_delete"),
            "创建自定义代理环境并验证 Chrome 商店连通性",
        )

    def test_existing_proxy_case_name_mentions_connectivity(self) -> None:
        self.assertEqual(
            case_display_name("test_create_environment_with_existing_proxy_open_close_delete"),
            "创建已有代理环境并验证 Chrome 商店连通性",
        )

    def test_discover_cases_includes_display_name_without_changing_id(self) -> None:
        with mock.patch("streamlit_runner._build_config", return_value={}), mock.patch(
            "streamlit_runner.AutomationRunner",
            _FakeRunner,
        ), mock.patch("streamlit_runner.get_test_case_module", return_value="环境管理"):
            cases = streamlit_runner.discover_cases()

        self.assertEqual(len(cases), 1)
        self.assertEqual(
            cases[0]["id"],
            "tests.p0.environment_management.test_02_create_default_environment."
            "TestCreateDefaultEnvironment.test_create_open_close_delete_default_environment",
        )
        self.assertEqual(cases[0]["module"], "环境管理")
        self.assertEqual(cases[0]["class_name"], "TestCreateDefaultEnvironment")
        self.assertEqual(cases[0]["method_name"], "test_create_open_close_delete_default_environment")
        self.assertEqual(cases[0]["display_name"], "创建默认环境并打开关闭删除")


if __name__ == "__main__":
    unittest.main()
