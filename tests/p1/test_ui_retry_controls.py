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


if __name__ == "__main__":
    unittest.main()
