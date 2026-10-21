from __future__ import annotations

import io
import logging
import unittest
from types import SimpleNamespace
from unittest import mock

from core.app import AppStartupError
from core.cdp_driver import CDPConnectionError
from core.circuit_breaker import BreakerName
from core.runner import AutomationRunner, ExitCode


class TestStartupFailureLogging(unittest.TestCase):
    def _run_failure(self, error: Exception, *, feishu: dict, phase: str = "startup"):
        output = io.StringIO()
        logger = logging.Logger("isolated-startup-failure-test", level=logging.DEBUG)
        logger.addHandler(logging.StreamHandler(output))
        config = {"run": {"precheck_before_run": False}, "feishu": feishu}
        runner = AutomationRunner(config, logger)
        suite = unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
        with (
            mock.patch.object(runner, "_build_suite", return_value=suite),
            mock.patch.object(runner, "_run_suite") as run_suite,
            mock.patch("core.runner.collect_required_runtime_services", return_value=[]),
            mock.patch("core.runner.AppManager") as app_type,
            mock.patch("core.runner.CDPDriver") as driver_type,
            mock.patch.object(runner.notifier, "send_text", wraps=runner.notifier.send_text) as send_text,
        ):
            app_type.return_value.launch_fresh.return_value = True
            if phase == "startup":
                app_type.return_value.launch_fresh.side_effect = error
            elif phase == "connect":
                driver_type.return_value.connect.side_effect = error
            else:
                driver_type.return_value.wait_for_app_ready.side_effect = error
            with mock.patch.object(logger, "error", wraps=logger.error) as log_error:
                result = runner.run()
        return SimpleNamespace(
            result=result,
            output=output.getvalue(),
            runner=runner,
            run_suite=run_suite,
            send_text=send_text,
            log_error=log_error,
        )

    def test_disabled_feishu_still_logs_actionable_signing_failure_and_returns_three(self):
        detail = "CDP 凭证生成失败（退出码 1），请检查私钥及 cryptography 依赖；脚本输出已隐藏"
        execution = self._run_failure(AppStartupError(detail), feishu={"enabled": False})
        self.assertEqual(execution.result, ExitCode.APP_OR_CDP_ERROR)
        self.assertIn("Dicloak APP 启动或 CDP 连接失败", execution.output)
        self.assertIn(detail, execution.output)
        self.assertIn("AppStartupError", execution.output)
        self.assertTrue(execution.runner.breakers.is_open(BreakerName.APP_STARTUP))
        self.assertIn(detail, execution.runner.breakers.reason(BreakerName.APP_STARTUP))
        execution.run_suite.assert_not_called()
        execution.log_error.assert_called_once()
        self.assertNotIn("exc_info", execution.log_error.call_args.kwargs)
        self.assertNotIn("Traceback", execution.output)

    def test_failure_notification_disabled_still_logs_without_sending(self):
        execution = self._run_failure(
            AppStartupError("APP 启动失败，请检查可执行文件、权限与工作目录；启动凭证已隐藏"),
            feishu={"enabled": True, "notify_on_failure": False, "webhook_url": "https://unused.invalid"},
        )
        self.assertEqual(execution.result, ExitCode.APP_OR_CDP_ERROR)
        self.assertIn("APP 启动失败", execution.output)
        execution.log_error.assert_called_once()
        execution.send_text.assert_not_called()

    def test_cdp_connection_and_frontend_failures_log_without_traceback(self):
        for phase in ("connect", "ready"):
            with self.subTest(phase=phase):
                detail = "Playwright CDP connect timeout after 30s: connection refused"
                execution = self._run_failure(
                    CDPConnectionError(detail), feishu={"enabled": False}, phase=phase,
                )
                self.assertEqual(execution.result, ExitCode.APP_OR_CDP_ERROR)
                self.assertIn("CDPConnectionError", execution.output)
                self.assertIn("connection refused", execution.output)
                self.assertNotIn("Traceback", execution.output)
                execution.run_suite.assert_not_called()

    def test_sensitive_startup_cdp_errors_hidden_in_logs_breaker_and_notification(self):
        secret = "do-not-log-sensitive-value"
        messages = (
            f"command --dicloak-debug-token={secret} failed",
            f"command --dicloak-debug-token {secret} failed",
            f"request token={secret} failed",
            f"request 'token': '{secret}' failed",
            f"command --private-key=/secret/{secret}.pem failed",
            f"-----BEGIN PRIVATE KEY-----\n{secret}\n-----END PRIVATE KEY-----",
            "a" * 40 + "." + "s" * 86,
        )
        for error_type in (AppStartupError, CDPConnectionError):
            for message in messages:
                with self.subTest(error_type=error_type.__name__, message_index=messages.index(message)):
                    execution = self._run_failure(
                        error_type(message), feishu={"enabled": False},
                        phase="connect" if error_type is CDPConnectionError else "startup",
                    )
                    self.assertEqual(execution.result, ExitCode.APP_OR_CDP_ERROR)
                    self.assertIn("已隐藏", execution.output)
                    surfaces = (
                        execution.output,
                        execution.runner.breakers.reason(BreakerName.APP_STARTUP),
                        str(execution.send_text.call_args),
                    )
                    for surface in surfaces:
                        self.assertNotIn(secret, surface)
                        self.assertNotIn("s" * 86, surface)
                    self.assertNotIn("Traceback", execution.output)

    def test_os_errors_hide_all_original_text_but_keep_type_and_errno(self):
        for message in (
            "cannot start --dicloak-debug-token=system-secret",
            "cannot start token=system-secret",
            "system-secret without a recognizable credential marker",
        ):
            with self.subTest(message=message):
                execution = self._run_failure(
                    PermissionError(13, message, "/secret/system-secret.pem"),
                    feishu={"enabled": False},
                )
                self.assertEqual(execution.result, ExitCode.APP_OR_CDP_ERROR)
                self.assertIn("PermissionError", execution.output)
                self.assertIn("系统错误码 13", execution.output)
                self.assertNotIn("system-secret", execution.output)
                self.assertNotIn("system-secret", execution.runner.breakers.reason(BreakerName.APP_STARTUP))
                self.assertNotIn("system-secret", str(execution.send_text.call_args))
                self.assertNotIn("Traceback", execution.output)

    def test_safe_error_text_is_one_bounded_line(self):
        execution = self._run_failure(
            AppStartupError("safe reason\n" + "x" * 2000), feishu={"enabled": False},
        )
        detail = execution.runner.breakers.reason(BreakerName.APP_STARTUP)
        self.assertNotIn("\n", detail)
        self.assertLess(len(detail), 1230)


if __name__ == "__main__":
    unittest.main()
