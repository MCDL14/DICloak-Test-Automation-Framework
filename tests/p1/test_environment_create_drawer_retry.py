from __future__ import annotations

import unittest

from pages.environment_page import EnvironmentPage, _CreateEnvironmentSubmitNotStarted


class _DrawerFlowProbe(EnvironmentPage):
    def __init__(self, *, group_ready: list[bool], submit_states: list[str]):
        self.group_ready = list(group_ready)
        self.submit_states = list(submit_states)
        self.dismiss_count = 0
        self.table_wait_count = 0
        self.group_wait_count = 0
        self.submit_count = 0

    def dismiss_blocking_overlays(self) -> None:
        self.dismiss_count += 1

    def _wait_create_environment_default_group_selected(self, timeout_seconds: int) -> None:
        self.group_wait_count += 1
        ready = self.group_ready.pop(0) if self.group_ready else False
        if not ready:
            raise TimeoutError("default group missing")

    def _submit_active_create_environment_drawer(self, context: str) -> None:
        self.submit_count += 1
        state = self.submit_states.pop(0) if self.submit_states else "retry"
        if state == "retry":
            raise _CreateEnvironmentSubmitNotStarted("submit did not start")

    def _wait_for_table_not_loading(self, timeout_seconds: int | None = None) -> None:
        self.table_wait_count += 1


class _ListLoadingProbe(EnvironmentPage):
    def __init__(self, *, wait_results: list[str]):
        self.wait_results = list(wait_results)
        self.wait_timeouts: list[int | None] = []
        self.refresh_count = 0

    def _wait_for_table_not_loading(self, timeout_seconds: int | None = None) -> None:
        self.wait_timeouts.append(timeout_seconds)
        result = self.wait_results.pop(0) if self.wait_results else "timeout"
        if result == "timeout":
            raise TimeoutError("table still loading")

    def _trigger_environment_list_refresh(self) -> None:
        self.refresh_count += 1


class _ClickRecorder:
    def __init__(self) -> None:
        self.clicks: list[str] = []

    def click_element_by_script(self, script: str) -> None:
        self.clicks.append(script)


class _SubmitProbe(EnvironmentPage):
    CREATE_ENVIRONMENT_SECOND_SUBMIT_DELAY_SECONDS = 0

    def __init__(self, *, submit_states: list[str]):
        self.cdp = _ClickRecorder()
        self.submit_states = list(submit_states)
        self.closed_wait_count = 0
        self.submit_state_timeouts: list[int] = []

    def _close_select_dropdowns(self) -> None:
        return None

    def _create_environment_submit_button_script(self) -> str:
        return "button:create-submit"

    def _wait_create_environment_submit_state(self, timeout_seconds: int) -> str:
        self.submit_state_timeouts.append(timeout_seconds)
        return self.submit_states.pop(0) if self.submit_states else "idle"

    def _wait_for_overlay_closed(self) -> None:
        self.closed_wait_count += 1

    def _create_environment_submit_button_state(self) -> dict:
        return {"visible": True, "text": "创建环境", "loading": False, "disabled": False}


class _SubmitStateProbe(EnvironmentPage):
    def __init__(self, *, drawer_visible: bool, button_state: dict):
        self.drawer_visible = drawer_visible
        self.button_state = dict(button_state)
        self.state_read_count = 0

    def _create_environment_drawer_visible(self) -> bool:
        return self.drawer_visible

    def _create_environment_submit_button_state(self) -> dict:
        self.state_read_count += 1
        return dict(self.button_state)


class _DataSyncOptionsProbe(EnvironmentPage):
    CREATE_ENVIRONMENT_DATA_SYNC_OPTIONS = ("Cookie", "Local Storage", "IndexedDB")

    def __init__(self, *, checked_options: set[str]):
        self.checked_options = set(checked_options)
        self.clicked_options: list[str] = []
        self.cdp = self

    def click_element_by_script(self, script: str) -> None:
        option = script.removeprefix("checkbox:")
        self.clicked_options.append(option)
        if option in self.checked_options:
            self.checked_options.remove(option)
        else:
            self.checked_options.add(option)

    def _active_drawer_form_checkbox_script(self, label: str, option: str) -> str:
        return f"checkbox:{option}"

    def _create_environment_data_sync_option_checked(self, option: str) -> bool:
        return option in self.checked_options

    def _wait_create_environment_data_sync_option_checked(self, option: str, expected: bool) -> None:
        if self._create_environment_data_sync_option_checked(option) != expected:
            raise TimeoutError(f"option did not become expected: {option}={expected}")

    def create_environment_selected_data_sync_options(self) -> list[str]:
        return [option for option in self.CREATE_ENVIRONMENT_DATA_SYNC_OPTIONS if option in self.checked_options]


class _EditClearCacheProbe(EnvironmentPage):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.cdp = self

    def click_environment_more(self, name: str) -> None:
        self.calls.append(("more", (name,)))

    def click_visible_dropdown_item(self, text: str) -> None:
        self.calls.append(("dropdown", (text,)))

    def _wait_edit_environment_drawer_visible(self) -> None:
        self.calls.append(("wait-drawer", ()))

    def _expand_edit_environment_advanced_settings(self) -> None:
        self.calls.append(("expand-advanced", ()))

    def _select_edit_environment_clear_local_cache_mode(self, mode: str) -> None:
        self.calls.append(("cache-mode", (mode,)))

    def _select_active_drawer_form_select_option(self, label: str, option: str) -> None:
        self.calls.append(("select", (label, option)))

    def _set_active_drawer_switch_by_text(self, text: str, enabled: bool) -> None:
        self.calls.append(("switch", (text, str(enabled))))

    def _close_select_dropdowns(self) -> None:
        self.calls.append(("close-selects", ()))

    def click_element_by_script(self, script: str) -> None:
        self.calls.append(("click", (script,)))

    def _active_overlay_button_script(self, text: str) -> str:
        return f"button:{text}"

    def _confirm_edit_save_message_if_present(self) -> None:
        self.calls.append(("confirm-edit-message", ()))

    def _wait_for_overlay_closed(self) -> None:
        self.calls.append(("wait-closed", ()))

    def _wait_for_environment_list_not_loading_with_refresh_retry(self) -> None:
        self.calls.append(("wait-list", ()))


class EnvironmentCreateDrawerRetryTests(unittest.TestCase):
    def test_reopens_until_default_group_is_selected(self) -> None:
        page = _DrawerFlowProbe(group_ready=[False, False, True], submit_states=["ok"])
        opened: list[int] = []
        populated: list[int] = []

        result = page._run_create_environment_drawer_flow(
            lambda: opened.append(1),
            lambda: populated.append(1) or "created",
            context="probe default group",
        )

        self.assertEqual(result, "created")
        self.assertEqual(len(opened), 3)
        self.assertEqual(len(populated), 1)
        self.assertEqual(page.submit_count, 1)
        self.assertEqual(page.table_wait_count, 1)

    def test_raises_after_default_group_retry_budget_is_exhausted(self) -> None:
        page = _DrawerFlowProbe(group_ready=[False, False, False], submit_states=[])
        opened: list[int] = []
        populated: list[int] = []

        with self.assertRaisesRegex(TimeoutError, "default group missing"):
            page._run_create_environment_drawer_flow(
                lambda: opened.append(1),
                lambda: populated.append(1),
                context="probe missing default group",
            )

        self.assertEqual(len(opened), 3)
        self.assertEqual(len(populated), 0)
        self.assertEqual(page.submit_count, 0)

    def test_reopens_when_submit_does_not_enter_loading(self) -> None:
        page = _DrawerFlowProbe(group_ready=[True, True, True], submit_states=["retry", "retry", "ok"])
        opened: list[int] = []
        populated: list[int] = []

        result = page._run_create_environment_drawer_flow(
            lambda: opened.append(1),
            lambda: populated.append(1) or "created",
            context="probe submit retry",
        )

        self.assertEqual(result, "created")
        self.assertEqual(len(opened), 3)
        self.assertEqual(len(populated), 3)
        self.assertEqual(page.submit_count, 3)
        self.assertEqual(page.table_wait_count, 1)

    def test_raises_after_submit_retry_budget_is_exhausted(self) -> None:
        page = _DrawerFlowProbe(group_ready=[True, True, True], submit_states=["retry", "retry", "retry"])
        opened: list[int] = []
        populated: list[int] = []

        with self.assertRaisesRegex(TimeoutError, "submit did not start"):
            page._run_create_environment_drawer_flow(
                lambda: opened.append(1),
                lambda: populated.append(1),
                context="probe submit exhausted",
            )

        self.assertEqual(len(opened), 3)
        self.assertEqual(len(populated), 3)
        self.assertEqual(page.submit_count, 3)
        self.assertEqual(page.table_wait_count, 0)

    def test_submit_clicks_confirm_again_when_first_click_stays_idle(self) -> None:
        page = _SubmitProbe(submit_states=["idle", "idle", "loading"])

        page._submit_active_create_environment_drawer("probe second click")

        self.assertEqual(page.cdp.clicks, ["button:create-submit", "button:create-submit"])
        self.assertEqual(page.closed_wait_count, 1)
        self.assertEqual(page.submit_state_timeouts[1], 0)

    def test_submit_raises_when_second_confirm_click_still_stays_idle(self) -> None:
        page = _SubmitProbe(submit_states=["idle", "idle", "idle"])

        with self.assertRaisesRegex(_CreateEnvironmentSubmitNotStarted, "second confirm click"):
            page._submit_active_create_environment_drawer("probe second click exhausted")

        self.assertEqual(page.cdp.clicks, ["button:create-submit", "button:create-submit"])
        self.assertEqual(page.closed_wait_count, 0)

    def test_submit_does_not_click_twice_when_loading_starts_immediately(self) -> None:
        page = _SubmitProbe(submit_states=["loading"])

        page._submit_active_create_environment_drawer("probe immediate loading")

        self.assertEqual(page.cdp.clicks, ["button:create-submit"])
        self.assertEqual(page.closed_wait_count, 1)

    def test_submit_does_not_click_twice_when_drawer_closes_immediately(self) -> None:
        page = _SubmitProbe(submit_states=["closed"])

        page._submit_active_create_environment_drawer("probe immediate close")

        self.assertEqual(page.cdp.clicks, ["button:create-submit"])
        self.assertEqual(page.closed_wait_count, 0)

    def test_submit_rechecks_delayed_loading_before_second_click(self) -> None:
        page = _SubmitProbe(submit_states=["idle", "loading"])

        page._submit_active_create_environment_drawer("probe delayed loading")

        self.assertEqual(page.cdp.clicks, ["button:create-submit"])
        self.assertEqual(page.closed_wait_count, 1)
        self.assertEqual(page.submit_state_timeouts[1], 0)

    def test_submit_rechecks_delayed_close_before_second_click(self) -> None:
        page = _SubmitProbe(submit_states=["idle", "closed"])

        page._submit_active_create_environment_drawer("probe delayed close")

        self.assertEqual(page.cdp.clicks, ["button:create-submit"])
        self.assertEqual(page.closed_wait_count, 0)
        self.assertEqual(page.submit_state_timeouts[1], 0)

    def test_submit_state_reads_new_create_button_loading(self) -> None:
        page = _SubmitStateProbe(drawer_visible=True, button_state={"loading": True, "disabled": True})

        self.assertEqual(page._wait_create_environment_submit_state(timeout_seconds=0), "loading")
        self.assertEqual(page.state_read_count, 1)

    def test_submit_state_closed_does_not_read_a_stale_button(self) -> None:
        page = _SubmitStateProbe(drawer_visible=False, button_state={"loading": True})

        self.assertEqual(page._wait_create_environment_submit_state(timeout_seconds=0), "closed")
        self.assertEqual(page.state_read_count, 0)

    def test_submit_state_disabled_without_loading_does_not_mean_started(self) -> None:
        page = _SubmitStateProbe(drawer_visible=True, button_state={"loading": False, "disabled": True})

        self.assertEqual(page._wait_create_environment_submit_state(timeout_seconds=0), "idle")
        self.assertEqual(page.state_read_count, 1)

    def test_list_loading_wait_retries_by_triggering_search_refresh(self) -> None:
        page = _ListLoadingProbe(wait_results=["timeout", "timeout", "ok"])

        page._wait_for_environment_list_not_loading_with_refresh_retry()

        self.assertEqual(page.refresh_count, 2)
        self.assertEqual(page.wait_timeouts, [20, 20, 20])

    def test_list_loading_wait_raises_after_refresh_retry_budget_is_exhausted(self) -> None:
        page = _ListLoadingProbe(wait_results=["timeout", "timeout", "timeout"])

        with self.assertRaisesRegex(TimeoutError, "search refresh retries"):
            page._wait_for_environment_list_not_loading_with_refresh_retry()

        self.assertEqual(page.refresh_count, 2)
        self.assertEqual(page.wait_timeouts, [20, 20, 20])

    def test_disables_only_requested_create_environment_data_sync_options(self) -> None:
        page = _DataSyncOptionsProbe(checked_options={"Cookie", "Local Storage"})

        page._disable_create_environment_data_sync_options(["Cookie"])

        self.assertEqual(page.clicked_options, ["Cookie"])
        self.assertEqual(page.create_environment_selected_data_sync_options(), ["Local Storage"])

    def test_disabling_unknown_create_environment_data_sync_option_fails(self) -> None:
        page = _DataSyncOptionsProbe(checked_options=set())

        with self.assertRaisesRegex(ValueError, "unsupported create environment data sync options"):
            page._disable_create_environment_data_sync_options(["Session Storage"])

    def test_edit_clear_all_cache_every_open_sync_cloud_data_uses_expected_controls(self) -> None:
        page = _EditClearCacheProbe()

        page.edit_environment_clear_all_local_cache_every_open_sync_cloud_data("env-a")

        self.assertEqual(
            page.calls,
            [
                ("more", ("env-a",)),
                ("dropdown", ("编辑",)),
                ("wait-drawer", ()),
                ("expand-advanced", ()),
                ("cache-mode", ("自定义",)),
                ("select", ("清除方式", "清除本地全部缓存")),
                ("select", ("清除频率", "每次打开环境时都清除")),
                ("switch", ("清除后，再同步云端数据", "True")),
                ("close-selects", ()),
                ("click", ("button:确定",)),
                ("confirm-edit-message", ()),
                ("wait-closed", ()),
                ("wait-list", ()),
            ],
        )

    def test_edit_clear_all_cache_every_open_no_cloud_sync_data_turns_switch_off(self) -> None:
        page = _EditClearCacheProbe()

        page.edit_environment_clear_all_local_cache_every_open_no_cloud_sync_data("env-a")

        self.assertIn(("switch", ("清除后，再同步云端数据", "False")), page.calls)
        self.assertEqual(page.calls[-1], ("wait-list", ()))


if __name__ == "__main__":
    unittest.main()
