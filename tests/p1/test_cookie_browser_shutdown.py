from __future__ import annotations

import importlib
import logging
import unittest
from unittest.mock import patch


COOKIE_CASES = (
    (
        "tests.p0.environment_management.test_26_cookie_data_validation",
        "TestCookieDataValidation",
    ),
    (
        "tests.p0.environment_management.test_29_new_environment_cookie_persistence",
        "TestNewEnvironmentCookiePersistence",
    ),
    (
        "tests.p0.environment_management.test_32_individual_environment_cookie_sync",
        "TestIndividualEnvironmentCookieSync",
    ),
    (
        "tests.p0.environment_management.test_35_individual_environment_one_way_sync_forbid_current_account",
        "TestIndividualEnvironmentOneWaySyncForbidCurrentAccount",
    ),
    (
        "tests.p0.environment_management.test_36_individual_environment_one_way_sync_allow_current_account",
        "TestIndividualEnvironmentOneWaySyncAllowCurrentAccount",
    ),
    (
        "tests.p0.environment_management.test_37_individual_environment_disable_cookie_sync",
        "TestIndividualEnvironmentDisableCookieSync",
    ),
    (
        "tests.p0.environment_management.test_40_individual_environment_clear_all_cache_every_open_sync_cloud",
        "TestIndividualEnvironmentClearAllCacheEveryOpenSyncCloud",
    ),
    (
        "tests.p0.environment_management.test_41_individual_environment_clear_all_cache_every_open_no_cloud_sync",
        "TestIndividualEnvironmentClearAllCacheEveryOpenNoCloudSync",
    ),
    (
        "tests.p0.global_settings.test_13_global_settings_one_way_sync_disallow_current_account",
        "TestGlobalSettingsOneWaySyncDisallowCurrentAccount",
    ),
    (
        "tests.p0.global_settings.test_14_global_settings_one_way_sync_allow_current_account",
        "TestGlobalSettingsOneWaySyncAllowCurrentAccount",
    ),
    (
        "tests.p0.global_settings.test_15_disable_cookie_data_sync",
        "TestDisableCookieDataSync",
    ),
    (
        "tests.p0.global_settings.test_18_clear_all_cache_every_open_sync_cloud",
        "TestGlobalSettingsClearAllCacheEveryOpenSyncCloud",
    ),
    (
        "tests.p0.global_settings.test_19_clear_all_cache_every_open_no_cloud_sync",
        "TestGlobalSettingsClearAllCacheEveryOpenNoCloudSync",
    ),
)


class _EnvironmentPage:
    def __init__(self, events: list, *, visible: bool = True, action: str = "关闭"):
        self.events = events
        self.visible = visible
        self.action = action

    def environment_visible_in_current_list(self, name: str) -> bool:
        return self.visible

    def environment_action_text(self, name: str) -> str:
        return self.action

    def click_environment_action(self, name: str, action: str) -> None:
        self.events.append(("app_close", name, action))

    def wait_environment_action_text(self, name: str, action: str, *, timeout_seconds: int) -> None:
        self.events.append(("app_ready", name, action, timeout_seconds))


class TestCookieBrowserShutdown(unittest.TestCase):
    def _case(self, module_name: str, class_name: str, *, app_port: int = 9222):
        module = importlib.import_module(module_name)
        case = getattr(module, class_name)("runTest")
        # Instantiate the existing case without running its APP/login fixtures.
        case.config = {"cdp": {"port": app_port}}
        case.logger = logging.getLogger("cookie-shutdown-integration-test")
        return module, case

    def test_all_cookie_cases_close_kernel_then_wait_for_process_and_app(self) -> None:
        for module_name, class_name in COOKIE_CASES:
            for app_port in (9222, 9223):
                with self.subTest(case=class_name, app_port=app_port):
                    module, case = self._case(module_name, class_name, app_port=app_port)
                    events = []
                    page = _EnvironmentPage(events)
                    with (
                        patch.object(
                            module,
                            "close_kernel_browser",
                            side_effect=lambda *args, **kwargs: events.append(("browser_close",)),
                        ) as close_browser,
                        patch.object(
                            module,
                            "wait_for_pid_stopped",
                            side_effect=lambda *args, **kwargs: events.append(("pid_stopped",)) or True,
                        ) as wait_pid,
                    ):
                        case._close_environment_if_open(
                            page,
                            environment_close_timeout=17,
                            kernel_process_timeout=19,
                            kernel_pid=4321,
                            kernel_cdp_port=18888,
                        )

                    close_browser.assert_called_once_with(
                        18888, timeout_seconds=17, app_cdp_port=app_port
                    )
                    wait_pid.assert_called_once_with(4321, timeout_seconds=19)
                    self.assertEqual(
                        events,
                        [
                            ("browser_close",),
                            ("pid_stopped",),
                            ("app_ready", module.ENVIRONMENT_NAME, "打开", 17),
                        ],
                    )

    def test_cleanup_without_kernel_endpoint_uses_app_close(self) -> None:
        for module_name, class_name in COOKIE_CASES:
            for kernel_pid in (0, 4321):
                with self.subTest(case=class_name, kernel_pid=kernel_pid):
                    module, case = self._case(module_name, class_name)
                    events = []
                    page = _EnvironmentPage(events)
                    with (
                        patch.object(module, "close_kernel_browser") as close_browser,
                        patch.object(
                            module,
                            "wait_for_pid_stopped",
                            side_effect=lambda *args, **kwargs: events.append(("pid_stopped",)) or True,
                        ) as wait_pid,
                    ):
                        case._close_environment_if_open(
                            page,
                            environment_close_timeout=17,
                            kernel_process_timeout=19,
                            kernel_pid=kernel_pid,
                        )

                    close_browser.assert_not_called()
                    expected = [("app_close", module.ENVIRONMENT_NAME, "关闭")]
                    if kernel_pid:
                        wait_pid.assert_called_once_with(4321, timeout_seconds=19)
                        expected.append(("pid_stopped",))
                    else:
                        wait_pid.assert_not_called()
                    expected.append(("app_ready", module.ENVIRONMENT_NAME, "打开", 17))
                    self.assertEqual(events, expected)

    def test_browser_close_failure_is_not_replaced_by_app_close(self) -> None:
        for module_name, class_name in COOKIE_CASES:
            with self.subTest(case=class_name):
                module, case = self._case(module_name, class_name)
                events = []
                page = _EnvironmentPage(events)
                failure = RuntimeError("browser shutdown failed")
                with (
                    patch.object(module, "close_kernel_browser", side_effect=failure) as close_browser,
                    patch.object(module, "wait_for_pid_stopped") as wait_pid,
                ):
                    with self.assertRaises(RuntimeError) as raised:
                        case._close_environment_if_open(
                            page,
                            environment_close_timeout=17,
                            kernel_process_timeout=19,
                            kernel_pid=4321,
                            kernel_cdp_port=18888,
                        )

                self.assertIs(raised.exception, failure)
                close_browser.assert_called_once()
                wait_pid.assert_not_called()
                self.assertEqual(events, [])

    def test_process_exit_timeout_stops_before_app_ready_check(self) -> None:
        for module_name, class_name in COOKIE_CASES:
            with self.subTest(case=class_name):
                module, case = self._case(module_name, class_name)
                events = []
                page = _EnvironmentPage(events)
                with (
                    patch.object(module, "close_kernel_browser") as close_browser,
                    patch.object(module, "wait_for_pid_stopped", return_value=False),
                ):
                    with self.assertRaises(AssertionError):
                        case._close_environment_if_open(
                            page,
                            environment_close_timeout=17,
                            kernel_process_timeout=19,
                            kernel_pid=4321,
                            kernel_cdp_port=18888,
                        )

                close_browser.assert_called_once()
                self.assertEqual(events, [])

    def test_absent_or_closed_environment_is_left_alone(self) -> None:
        for module_name, class_name in COOKIE_CASES:
            for visible, action in ((False, "关闭"), (True, "打开")):
                with self.subTest(case=class_name, visible=visible, action=action):
                    module, case = self._case(module_name, class_name)
                    events = []
                    page = _EnvironmentPage(events, visible=visible, action=action)
                    with (
                        patch.object(module, "close_kernel_browser") as close_browser,
                        patch.object(module, "wait_for_pid_stopped") as wait_pid,
                    ):
                        case._close_environment_if_open(
                            page,
                            environment_close_timeout=17,
                            kernel_process_timeout=19,
                            kernel_pid=4321,
                            kernel_cdp_port=18888,
                        )

                    close_browser.assert_not_called()
                    wait_pid.assert_not_called()
                    self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
