from __future__ import annotations

import unittest
from unittest.mock import patch

from core.kernel_cdp import _click_bilibili_login_entry, _open_bilibili_password_login_if_needed


class TestKernelBilibiliLogin(unittest.TestCase):
    @patch("core.kernel_cdp.time.sleep")
    @patch("core.kernel_cdp._evaluate_value")
    def test_login_entry_prefers_current_unlogin_avatar_selector(self, evaluate_value, _sleep) -> None:
        evaluate_value.return_value = True

        _click_bilibili_login_entry(object(), 9_999_999_999)

        expression = evaluate_value.call_args.args[1]
        self.assertIn('".header-avatar-unlogin-entry"', expression)
        self.assertIn('".header-avatar-unlogin-inner"', expression)
        self.assertIn("preferred.click()", expression)

    @patch("core.kernel_cdp.time.sleep")
    @patch("core.kernel_cdp._evaluate_value")
    def test_password_login_opens_through_new_intermediate_popover(self, evaluate_value, _sleep) -> None:
        evaluate_value.side_effect = [False, True, True]

        _open_bilibili_password_login_if_needed(object(), 9_999_999_999)

        click_expression = evaluate_value.call_args_list[1].args[1]
        self.assertIn(".login-panel-popover .login-btn", click_expression)
        self.assertIn('"立即登录"', click_expression)
        self.assertIn("popoverLogin.click()", click_expression)


if __name__ == "__main__":
    unittest.main()
