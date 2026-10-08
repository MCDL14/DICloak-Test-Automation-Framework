from __future__ import annotations

import unittest

from core.ui_error_localization import is_exception_summary_line, summarize_ui_issue


class UiErrorLocalizationTests(unittest.TestCase):
    def test_assertion_expected_and_actual_are_rendered_in_chinese(self) -> None:
        issue = summarize_ui_issue("AssertionError: expected enabled, got disabled", "failed")

        self.assertEqual(issue.error_type, "断言失败")
        self.assertEqual(issue.exception_class, "AssertionError")
        self.assertEqual(issue.chinese_reason, "期望值为 enabled，实际值为 disabled。")

    def test_existing_chinese_assertion_message_is_preserved(self) -> None:
        issue = summarize_ui_issue("AssertionError: 环境名称没有修改成功", "failed")

        self.assertEqual(issue.chinese_reason, "环境名称没有修改成功")

    def test_missing_element_exception_has_specific_chinese_type(self) -> None:
        issue = summarize_ui_issue(
            "selenium.common.exceptions.NoSuchElementException: login button missing",
            "error",
        )

        self.assertEqual(issue.error_type, "元素未找到")
        self.assertIn("未找到", issue.chinese_reason)

    def test_element_wait_timeout_has_specific_chinese_type(self) -> None:
        issue = summarize_ui_issue(
            "TimeoutError: script did not return a visible enabled element before timeout",
            "error",
        )

        self.assertEqual(issue.error_type, "元素等待超时")
        self.assertIn("可见、可操作状态超时", issue.chinese_reason)

    def test_connection_refused_is_rendered_as_connection_failure(self) -> None:
        issue = summarize_ui_issue(
            "ConnectionRefusedError: [WinError 10061] target machine refused it",
            "error",
        )

        self.assertEqual(issue.error_type, "连接失败")
        self.assertIn("连接", issue.chinese_reason)

    def test_business_assertion_extracts_localized_key_facts(self) -> None:
        issue = summarize_ui_issue(
            "AssertionError: chrome web store install was not blocked or prevented: "
            "expected_error=Invalid manifest, status_before=installable, status_after=installable",
            "failed",
        )

        self.assertIn("扩展安装应被阻止", issue.chinese_reason)
        self.assertIn("期望错误=Invalid manifest", issue.chinese_reason)
        self.assertIn("操作后状态=可安装", issue.chinese_reason)

    def test_kernel_cache_assertion_translates_semantics_and_fields(self) -> None:
        original = (
            "AssertionError: kernel executable path is not under expected cache dir: "
            "pid=63397, executable=/Applications/GinsBrowser, "
            "expected_parent=/Users/test/Library/Application Support/DICloak/browsers/142.1.19"
        )

        issue = summarize_ui_issue(original, "failed")

        self.assertIn("内核可执行文件路径不在预期缓存目录下", issue.chinese_reason)
        self.assertIn("进程 ID=63397", issue.chinese_reason)
        self.assertIn("可执行文件=/Applications/GinsBrowser", issue.chinese_reason)
        self.assertIn("预期父目录=/Users/test/Library", issue.chinese_reason)
        self.assertEqual(issue.original_error, original)

    def test_common_assertion_template_translates_object_action_and_value(self) -> None:
        issue = summarize_ui_issue(
            "AssertionError: environment group was not created: 自动化分组",
            "failed",
        )

        self.assertEqual(issue.chinese_reason, "环境分组未创建成功。 相关值：自动化分组。")
        self.assertIn("environment group was not created", issue.original_error)

    def test_unknown_assertion_uses_chinese_fallback_and_keeps_english_separately(self) -> None:
        english = "frobnicator phase contradicted expected topology"
        issue = summarize_ui_issue(f"AssertionError: {english}", "failed")

        self.assertEqual(issue.chinese_reason, "该断言的实际结果不符合预期，具体业务信息见英文原文。")
        self.assertNotIn(english, issue.chinese_reason)
        self.assertIn(english, issue.original_error)

    def test_multiline_assertion_keeps_all_original_lines(self) -> None:
        issue = summarize_ui_issue(
            "Traceback (most recent call last):\nAssertionError:\n"
            "environment group was not created: group-01\n"
            "member name did not match in list: member-01",
            "failed",
        )

        self.assertIn("环境分组未创建成功", issue.chinese_reason)
        self.assertIn("成员名称与预期不一致", issue.chinese_reason)
        self.assertIn("environment group was not created", issue.original_error)
        self.assertIn("member name did not match", issue.original_error)

    def test_exception_summary_line_accepts_prefixed_remote_traceback(self) -> None:
        self.assertTrue(is_exception_summary_line("[macOS] TimeoutError: element did not appear"))
        self.assertFalse(is_exception_summary_line("[macOS] File /tmp/example.py, line 1"))


if __name__ == "__main__":
    unittest.main()
