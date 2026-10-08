from __future__ import annotations

import unittest
from pathlib import Path


class UiRetryControlsTests(unittest.TestCase):
    def test_case_progress_component_exposes_all_group_and_single_retry_actions(self) -> None:
        component_html = (
            Path("ui") / "components" / "case_progress" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn("全部重试失败/异常", component_html)
        self.assertIn("本组全部重试", component_html)
        self.assertIn('scope: "case"', component_html)
        self.assertIn('scope: "group"', component_html)
        self.assertIn('scope: "all"', component_html)
        self.assertIn('post("streamlit:setComponentValue"', component_html)

    def test_case_progress_component_displays_chinese_issue_summary(self) -> None:
        component_html = (
            Path("ui") / "components" / "case_progress" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn('row["中文原因"]', component_html)
        self.assertIn('row["错误类型"]', component_html)
        self.assertIn('row["异常类"]', component_html)
        self.assertIn('row["原始错误"]', component_html)
        self.assertIn("英文原文：", component_html)
        self.assertIn("issue-summary", component_html)


if __name__ == "__main__":
    unittest.main()
