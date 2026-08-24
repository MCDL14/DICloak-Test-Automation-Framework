from __future__ import annotations

import copy
import re
import time
from pathlib import Path

from core.config import timeout_seconds as config_timeout_seconds
from pages.base_page import BasePage


class GlobalSettingsPage(BasePage):
    locator_file = "global_settings_locators.yaml"
    MINIMUM_CHECKED_CHECKBOXES = 3
    GLOBAL_SETTINGS_REENTRY_RETRIES = 2
    SAVE_SUCCESS_MESSAGE = "保存成功"
    SAVE_SUCCESS_MESSAGE_SECONDS = 10
    DATA_SYNC_COOKIE_LABEL = "Cookie"
    DATA_SYNC_LOCAL_STORAGE_LABEL = "Local Storage"
    DATA_SYNC_INDEXEDDB_LABEL = "IndexedDB"
    DATA_SYNC_ONE_WAY_SYNC_TEXT = "防止成员覆盖云端数据，导致环境内账号退出登录"
    DATA_SYNC_ONE_WAY_SYNC_STATE_NAME = "数据同步"
    DATA_SYNC_ONE_WAY_SYNC_WHITELIST_LABEL = "白名单"
    CLEAR_LOCAL_CACHE_METHOD_LABEL = "清除方式"
    CLEAR_LOCAL_CACHE_FREQUENCY_LABEL = "清除频率"
    CLEAR_LOCAL_CACHE_NO_CLEAR_TEXT = "不清除"
    CLEAR_LOCAL_CACHE_ALL_TEXT = "清除本地全部缓存"
    CLEAR_LOCAL_CACHE_EVERY_OPEN_TEXT = "每次打开环境时都清除"
    CLEAR_LOCAL_CACHE_SYNC_CLOUD_TEXT = "清除后，再同步云端数据"
    EXTENSION_TAMPER_PROTECTION_LABEL = "开启扩展加密并防止篡改"
    DISABLE_DEVTOOLS_LABELS = ("禁止打开浏览器开发者工具", "禁止打开浏览器开发者工具界面")
    EXTENSION_TAMPER_PROTECTION_CASCADE_LABELS = (
        DISABLE_DEVTOOLS_LABELS,
        "禁止管理/移除扩展，以及从本地安装扩展至浏览器",
        "禁止成员访问谷歌扩展商店和扩展设置页面",
    )
    ENVIRONMENT_FIELD_DISPLAY_LIMIT_LABELS = ("环境列表字段权限", "环境字段显示限制")
    ENVIRONMENT_FIELD_DISPLAY_LIMIT_DIALOG_TITLES = ("列表字段", "列表字段设置")
    GOOGLE_EXTENSION_SHORTCUT_LABELS = ("Chrome 应用商店", "谷歌应用商店")
    SNAPSHOT_SIMPLE_CHECKBOXES = (
        "禁止查看网站密码",
        DISABLE_DEVTOOLS_LABELS,
        "禁止管理/移除扩展，以及从本地安装扩展至浏览器",
        "禁止成员访问谷歌扩展商店和扩展设置页面",
    )
    _ENVIRONMENT_FIELD_ALIASES = {
        "环境序号": ("环境序号", "序号"),
        "环境名称": ("环境名称", "名称"),
        "环境分组": ("环境分组", "分组"),
        "备注": ("备注",),
        "标签": ("标签",),
        "升序": ("升序",),
        "降序": ("降序",),
    }

    def open(self, *, force_reentry: bool = False) -> None:
        """Open a fully loaded global-settings page, retrying through Environment Management."""
        with self.phase_timing("global_settings.open", force_reentry=force_reentry):
            self._open(force_reentry=force_reentry)

    def _open(self, *, force_reentry: bool = False) -> None:
        observations: list[dict[str, object]] = []
        total_attempts = self.GLOBAL_SETTINGS_REENTRY_RETRIES + 1
        for attempt_index in range(total_attempts):
            if force_reentry or attempt_index > 0:
                self._dismiss_blocking_overlays()
                self._open_environment_management_for_retry()

            self._dismiss_blocking_overlays()
            if not self._global_settings_route_active():
                self.cdp.click_element_by_script(
                    self._visible_text_element_script(
                        "global_settings_menu_candidates",
                        "全局设置",
                        exact=True,
                    )
                )
            self._wait_for_global_settings_page()
            self._wait_for_global_settings_rendered()
            checkbox_states = self._wait_checkbox_states_stable()
            checked_names = sorted(name for name, checked in checkbox_states.items() if checked)
            observations.append(
                {
                    "attempt": attempt_index + 1,
                    "checked_count": len(checked_names),
                    "checkbox_count": len(checkbox_states),
                    "checked_names": checked_names,
                }
            )
            if len(checked_names) >= self.MINIMUM_CHECKED_CHECKBOXES:
                return

        raise AssertionError(
            "global settings page remained abnormal after the initial entry and "
            f"{self.GLOBAL_SETTINGS_REENTRY_RETRIES} re-entry retries: "
            f"expected at least {self.MINIMUM_CHECKED_CHECKBOXES} checked checkboxes, "
            f"observations={observations}"
        )

    def capture_global_settings_snapshot(self) -> dict[str, object]:
        """Capture the global-setting fields that current P0 cases are allowed to mutate."""
        with self.phase_timing("global_settings.capture_snapshot"):
            self._wait_global_setting_states_stable()
            return {
                "schema_version": 1,
                "simple_checkboxes": self._simple_checkbox_snapshot(),
                "website_restriction": self.website_restriction_state(),
                "packet_capture_blocking": self.packet_capture_blocking_state(),
                "bookmark_setting": self.bookmark_setting_state(),
                "environment_field_display_limit": self.environment_field_display_limit_state(),
                "environment_list_pagination": self.environment_list_pagination_setting_state(),
                "environment_list_sort": self.environment_list_sort_state(),
                "data_sync": self.data_sync_one_way_state(),
                "clear_local_cache": self.clear_local_cache_state(),
                "extension_tamper_protection": self.extension_tamper_protection_state(),
            }

    def restore_global_settings_snapshot(self, snapshot: dict[str, object]) -> None:
        """Restore a snapshot through the real global-settings UI and verify strong fields."""
        if not isinstance(snapshot, dict):
            raise TypeError(f"global settings snapshot must be a dict: {type(snapshot)!r}")

        with self.phase_timing("global_settings.restore_snapshot"):
            current = self.capture_global_settings_snapshot()
            if self._global_settings_snapshot_matches(snapshot, current):
                self._log_noop_skip("global_settings.restore_snapshot")
                return

            self.restore_extension_tamper_protection_state(snapshot.get("extension_tamper_protection", {}))
            self._restore_simple_checkbox_snapshot(snapshot.get("simple_checkboxes", {}))
            self.restore_website_restriction_state(snapshot.get("website_restriction", {}))
            self.restore_packet_capture_blocking_state(snapshot.get("packet_capture_blocking", {}))
            self.restore_bookmark_setting_state(snapshot.get("bookmark_setting", {}))
            self.restore_environment_field_display_limit_state(snapshot.get("environment_field_display_limit", {}))
            self.restore_environment_list_pagination_setting_state(snapshot.get("environment_list_pagination", {}))
            self.restore_environment_list_sort_state(snapshot.get("environment_list_sort", {}))
            self.restore_data_sync_one_way_state(snapshot.get("data_sync", {}))
            self.restore_clear_local_cache_state(snapshot.get("clear_local_cache", {}))

            self.open(force_reentry=True)
            restored = self.capture_global_settings_snapshot()
            self._assert_global_settings_snapshot_matches(snapshot, restored)

    def _simple_checkbox_snapshot(self) -> dict[str, bool]:
        states: dict[str, bool] = {}
        for label_text in self.SNAPSHOT_SIMPLE_CHECKBOXES:
            label = self._resolve_visible_checkbox_label(label_text)
            states[label] = self.checkbox_checked(label)
        return states

    def _restore_simple_checkbox_snapshot(self, snapshot: object) -> None:
        if not isinstance(snapshot, dict):
            return
        for label, expected in snapshot.items():
            if bool(expected):
                self.ensure_checkbox_enabled(str(label))
            else:
                self.ensure_checkbox_disabled(str(label))

    def _assert_global_settings_snapshot_matches(
        self,
        expected: dict[str, object],
        actual: dict[str, object],
    ) -> None:
        if self._global_settings_snapshot_matches(expected, actual):
            return
        expected_compare = self._strong_global_settings_snapshot(expected)
        actual_compare = self._strong_global_settings_snapshot(actual)
        raise AssertionError(
            "global settings snapshot restore mismatch: "
            f"expected={expected_compare}, actual={actual_compare}"
        )

    def _global_settings_snapshot_matches(
        self,
        expected: dict[str, object],
        actual: dict[str, object],
    ) -> bool:
        expected_compare = self._strong_global_settings_snapshot(expected)
        actual_compare = self._strong_global_settings_snapshot(actual)
        return expected_compare == actual_compare

    def _log_noop_skip(self, context: str) -> None:
        logger = getattr(self.cdp, "logger", None)
        if logger is not None:
            logger.info("Skip no-op global settings save/restore: context=%s", context)

    def _strong_global_settings_snapshot(self, snapshot: dict[str, object]) -> dict[str, object]:
        strong = copy.deepcopy(snapshot)

        website_restriction = strong.get("website_restriction")
        if isinstance(website_restriction, dict) and not bool(website_restriction.get("enabled")):
            strong["website_restriction"] = {"enabled": False}

        packet_capture = strong.get("packet_capture_blocking")
        if isinstance(packet_capture, dict) and not bool(packet_capture.get("enabled")):
            strong["packet_capture_blocking"] = {"enabled": False}

        bookmark = strong.get("bookmark_setting")
        if isinstance(bookmark, dict):
            strong["bookmark_setting"] = {
                "enabled": bool(bookmark.get("enabled")),
                "restore_supported": bool(bookmark.get("restore_supported")),
            }

        field_limit = strong.get("environment_field_display_limit")
        if isinstance(field_limit, dict) and not bool(field_limit.get("enabled")):
            strong["environment_field_display_limit"] = {"enabled": False}

        pagination = strong.get("environment_list_pagination")
        if isinstance(pagination, dict) and not bool(pagination.get("enabled")):
            strong["environment_list_pagination"] = {"enabled": False}

        sort_limit = strong.get("environment_list_sort")
        if isinstance(sort_limit, dict) and not bool(sort_limit.get("enabled")):
            strong["environment_list_sort"] = {"enabled": False}

        clear_local_cache = strong.get("clear_local_cache")
        if isinstance(clear_local_cache, dict) and clear_local_cache.get("clear_method") == self.CLEAR_LOCAL_CACHE_NO_CLEAR_TEXT:
            strong["clear_local_cache"] = {"clear_method": self.CLEAR_LOCAL_CACHE_NO_CLEAR_TEXT}

        return strong

    def ensure_disable_view_password_enabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_enabled("禁止查看网站密码")

    def ensure_disable_view_password_disabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_disabled("禁止查看网站密码")

    def ensure_disable_devtools_enabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_enabled(self.DISABLE_DEVTOOLS_LABELS)

    def ensure_disable_devtools_disabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_disabled(self.DISABLE_DEVTOOLS_LABELS)

    def ensure_disable_extension_management_enabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_enabled("禁止管理/移除扩展，以及从本地安装扩展至浏览器")

    def ensure_disable_extension_management_disabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_disabled("禁止管理/移除扩展，以及从本地安装扩展至浏览器")

    def ensure_disable_member_google_extension_pages_enabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_enabled("禁止成员访问谷歌扩展商店和扩展设置页面")

    def ensure_disable_member_google_extension_pages_disabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_disabled("禁止成员访问谷歌扩展商店和扩展设置页面")

    def extension_tamper_protection_state(self) -> dict[str, bool]:
        return {"enabled": self.extension_tamper_protection_enabled()}

    def extension_tamper_protection_enabled(self) -> bool:
        label_text = self._resolve_visible_checkbox_label(self.EXTENSION_TAMPER_PROTECTION_LABEL)
        return self.checkbox_checked(label_text)

    def ensure_extension_tamper_protection_enabled(self) -> bool:
        """Enable 浏览器设置 → 开启扩展加密并防止篡改 through its confirmation dialog."""
        return self._set_extension_tamper_protection_enabled(True)

    def ensure_extension_tamper_protection_disabled(self) -> bool:
        """Disable 浏览器设置 → 开启扩展加密并防止篡改 through its confirmation dialog."""
        return self._set_extension_tamper_protection_enabled(False)

    def restore_extension_tamper_protection_state(self, state: object) -> None:
        if not isinstance(state, dict) or "enabled" not in state:
            return
        self._set_extension_tamper_protection_enabled(bool(state.get("enabled")))

    def _set_extension_tamper_protection_enabled(self, expected: bool) -> bool:
        label_text = self._resolve_visible_checkbox_label(self.EXTENSION_TAMPER_PROTECTION_LABEL)
        self._wait_for_checkbox(label_text)
        before_states = self._wait_checkbox_states_stable()
        if self.checkbox_checked(label_text) is expected:
            return False

        self.cdp.click_element_by_script(self._checkbox_script(label_text))
        self._wait_operation_prompt_visible()
        self.cdp.click_element_by_script(
            self._active_dialog_button_script("确定开启" if expected else "确定关闭")
        )
        self._wait_for_overlay_closed()
        self._wait_checkbox_checked(label_text, expected)
        after_states = self.checkbox_states()
        self._assert_extension_tamper_protection_checkbox_changes(label_text, before_states, after_states, expected)
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if not save_success:
            self.open(force_reentry=True)
            self._wait_for_checkbox(label_text)
            self._wait_checkbox_checked(label_text, expected)
        return True

    def _assert_extension_tamper_protection_checkbox_changes(
        self,
        label_text: str,
        before_states: dict[str, bool],
        after_states: dict[str, bool],
        expected: bool,
    ) -> None:
        if self.checkbox_checked(label_text) is not expected:
            raise AssertionError(
                "extension tamper protection checkbox did not reach expected state before save: "
                f"label={label_text}, expected={expected}"
            )

        allowed_label_fragments = {label_text, self.EXTENSION_TAMPER_PROTECTION_LABEL}
        for cascade_label in self.EXTENSION_TAMPER_PROTECTION_CASCADE_LABELS:
            for candidate in self._label_candidates(cascade_label):
                allowed_label_fragments.add(candidate)

        changed = {
            name: (before_states.get(name), after_states.get(name))
            for name in sorted(set(before_states) & set(after_states))
            if before_states.get(name) != after_states.get(name)
        }
        unexpected = {
            name: value
            for name, value in changed.items()
            if not any(fragment and fragment in name for fragment in allowed_label_fragments)
        }
        if unexpected:
            raise AssertionError(
                "unexpected checkbox changes when toggling extension tamper protection: "
                f"unexpected={unexpected}, allowed_fragments={sorted(allowed_label_fragments)}"
            )

    def ensure_cookie_data_sync_enabled(self) -> bool:
        """Enable and persist only the Cookie item under 数据设置 → 数据同步."""
        self._wait_for_cookie_data_sync()
        before_states = self._wait_checkbox_states_stable()
        if self.cookie_data_sync_enabled():
            return False

        self.cdp.click_element_by_script(self._cookie_data_sync_checkbox_script())
        self._wait_cookie_data_sync_enabled(True)
        after_states = self.checkbox_states()
        self._assert_only_checkbox_changed("Cookie", before_states, after_states)
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if not save_success:
            # Re-enter the page so the assertion reflects persisted server state, not only Vue local state.
            self.open()
            self._wait_for_cookie_data_sync()
            self._wait_cookie_data_sync_enabled(True)
        return True

    def cookie_data_sync_enabled(self) -> bool:
        value = self.cdp.evaluate(self._cookie_data_sync_enabled_script())
        if value is None:
            raise RuntimeError("数据同步 Cookie checkbox was not found")
        return bool(value)

    def ensure_cookie_data_sync_disabled(self) -> bool:
        """Disable and persist only the Cookie item under 数据设置 → 数据同步."""
        self._wait_for_cookie_data_sync()
        before_states = self._wait_checkbox_states_stable()
        if not self.cookie_data_sync_enabled():
            return False

        self.cdp.click_element_by_script(self._cookie_data_sync_checkbox_script())
        self._wait_cookie_data_sync_enabled(False)
        after_states = self.checkbox_states()
        self._assert_only_checkbox_changed("Cookie", before_states, after_states, expected_change=(True, False))
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if not save_success:
            self.open()
            self._wait_for_cookie_data_sync()
            self._wait_cookie_data_sync_enabled(False)
        return True

    def ensure_local_storage_data_sync_enabled(self) -> bool:
        """Enable and persist only the Local Storage item under 数据设置 → 数据同步."""
        self._wait_for_local_storage_data_sync()
        before_states = self._wait_checkbox_states_stable()
        if self.local_storage_data_sync_enabled():
            return False

        self.cdp.click_element_by_script(self._local_storage_data_sync_checkbox_script())
        self._wait_local_storage_data_sync_enabled(True)
        after_states = self.checkbox_states()
        self._assert_only_checkbox_changed("Local Storage", before_states, after_states)
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if not save_success:
            # Re-enter the page so the assertion reflects persisted server state, not only Vue local state.
            self.open()
            self._wait_for_local_storage_data_sync()
            self._wait_local_storage_data_sync_enabled(True)
        return True

    def local_storage_data_sync_enabled(self) -> bool:
        value = self.cdp.evaluate(self._local_storage_data_sync_enabled_script())
        if value is None:
            raise RuntimeError("数据同步 Local Storage checkbox was not found")
        return bool(value)

    def ensure_local_storage_data_sync_disabled(self) -> bool:
        """Disable and persist only the Local Storage item under 数据设置 → 数据同步."""
        self._wait_for_local_storage_data_sync()
        before_states = self._wait_checkbox_states_stable()
        if not self.local_storage_data_sync_enabled():
            return False

        self.cdp.click_element_by_script(self._local_storage_data_sync_checkbox_script())
        self._wait_local_storage_data_sync_enabled(False)
        after_states = self.checkbox_states()
        self._assert_only_checkbox_changed("Local Storage", before_states, after_states, expected_change=(True, False))
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if not save_success:
            self.open()
            self._wait_for_local_storage_data_sync()
            self._wait_local_storage_data_sync_enabled(False)
        return True

    def ensure_indexeddb_data_sync_enabled(self) -> bool:
        """Enable and persist only the IndexedDB item under 数据设置 → 数据同步."""
        self._wait_for_indexeddb_data_sync()
        before_states = self._wait_checkbox_states_stable()
        if self.indexeddb_data_sync_enabled():
            return False

        self.cdp.click_element_by_script(self._indexeddb_data_sync_checkbox_script())
        self._wait_indexeddb_data_sync_enabled(True)
        after_states = self.checkbox_states()
        self._assert_only_checkbox_changed("IndexedDB", before_states, after_states)
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if not save_success:
            # Re-enter the page so the assertion reflects persisted server state, not only Vue local state.
            self.open()
            self._wait_for_indexeddb_data_sync()
            self._wait_indexeddb_data_sync_enabled(True)
        return True

    def indexeddb_data_sync_enabled(self) -> bool:
        value = self.cdp.evaluate(self._indexeddb_data_sync_enabled_script())
        if value is None:
            raise RuntimeError("数据同步 IndexedDB checkbox was not found")
        return bool(value)

    def ensure_indexeddb_data_sync_disabled(self) -> bool:
        """Disable and persist only the IndexedDB item under 数据设置 → 数据同步."""
        self._wait_for_indexeddb_data_sync()
        before_states = self._wait_checkbox_states_stable()
        if not self.indexeddb_data_sync_enabled():
            return False

        self.cdp.click_element_by_script(self._indexeddb_data_sync_checkbox_script())
        self._wait_indexeddb_data_sync_enabled(False)
        after_states = self.checkbox_states()
        self._assert_only_checkbox_changed("IndexedDB", before_states, after_states, expected_change=(True, False))
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if not save_success:
            self.open()
            self._wait_for_indexeddb_data_sync()
            self._wait_indexeddb_data_sync_enabled(False)
        return True

    def data_sync_one_way_state(self) -> dict[str, object]:
        """Return persisted global 数据同步 state from the rendered page."""
        self._wait_for_data_sync_settings()
        whitelist_groups: list[str] = []
        if self.data_sync_one_way_enabled():
            self._wait_data_sync_one_way_whitelist_visible()
            whitelist_groups = self.data_sync_one_way_whitelist_values()
        return {
            "cookie": self.cookie_data_sync_enabled(),
            "local_storage": self.local_storage_data_sync_enabled(),
            "indexeddb": self.indexeddb_data_sync_enabled(),
            "one_way_enabled": self.data_sync_one_way_enabled(),
            "whitelist_groups": whitelist_groups,
        }

    def configure_data_sync_one_way(
        self,
        sync_items: list[str],
        whitelist_groups: list[str],
    ) -> dict[str, object]:
        """Configure global 数据同步 one-way sync and verify the saved state after re-entry."""
        expected_sync_items = self._unique_non_empty(sync_items)
        expected_whitelist = self._unique_non_empty(whitelist_groups)
        if not expected_sync_items:
            raise ValueError("global data sync items must not be empty")
        if not expected_whitelist:
            raise ValueError("global data sync one-way whitelist groups must not be empty")

        self._wait_for_data_sync_settings()
        current_state = self.data_sync_one_way_state()
        expected_state = {
            "cookie": self.DATA_SYNC_COOKIE_LABEL in expected_sync_items,
            "local_storage": self.DATA_SYNC_LOCAL_STORAGE_LABEL in expected_sync_items,
            "indexeddb": self.DATA_SYNC_INDEXEDDB_LABEL in expected_sync_items,
            "one_way_enabled": True,
            "whitelist_groups": expected_whitelist,
        }
        if self._data_sync_state_matches(expected_state, current_state):
            self._log_noop_skip("global_settings.configure_data_sync_one_way")
            return current_state

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        for item in expected_sync_items:
            self._set_data_sync_checked(item, True)
        self._set_data_sync_one_way_enabled(True)
        self._wait_data_sync_one_way_whitelist_visible()
        self._clear_data_sync_one_way_whitelist()
        self._select_data_sync_one_way_whitelist(expected_whitelist)
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(expected_sync_items),
            allowed_switch_names={
                self.DATA_SYNC_ONE_WAY_SYNC_TEXT,
                self.DATA_SYNC_ONE_WAY_SYNC_STATE_NAME,
            },
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if save_success:
            return self.data_sync_one_way_state()

        self.open(force_reentry=True)
        final_state = self.data_sync_one_way_state()
        missing_items = [
            item
            for item in expected_sync_items
            if not bool(final_state.get(self._data_sync_state_key(item)))
        ]
        if missing_items:
            raise AssertionError(f"global data sync items were not saved as checked: {missing_items}")
        if not bool(final_state.get("one_way_enabled")):
            raise AssertionError("global data sync one-way switch was not saved as enabled")
        actual_whitelist = self._unique_non_empty(final_state.get("whitelist_groups", []))
        if set(actual_whitelist) != set(expected_whitelist):
            raise AssertionError(
                "global data sync one-way whitelist was not saved as expected: "
                f"expected={expected_whitelist}, actual={actual_whitelist}"
            )
        return final_state

    def restore_data_sync_one_way_state(self, state: dict[str, object]) -> None:
        """Restore global 数据同步 state captured by data_sync_one_way_state()."""
        if not isinstance(state, dict):
            return
        self._wait_for_data_sync_settings()
        current_state = self.data_sync_one_way_state()
        if self._data_sync_state_matches(state, current_state):
            self._log_noop_skip("global_settings.restore_data_sync")
            return

        for item in (
            self.DATA_SYNC_COOKIE_LABEL,
            self.DATA_SYNC_LOCAL_STORAGE_LABEL,
            self.DATA_SYNC_INDEXEDDB_LABEL,
        ):
            key = self._data_sync_state_key(item)
            if key in state:
                self._set_data_sync_checked(item, bool(state.get(key)))

        expected_one_way = bool(state.get("one_way_enabled"))
        self._set_data_sync_one_way_enabled(expected_one_way)
        expected_whitelist = self._unique_non_empty(state.get("whitelist_groups", []))
        if expected_one_way:
            self._wait_data_sync_one_way_whitelist_visible()
            self._clear_data_sync_one_way_whitelist()
            if expected_whitelist:
                self._select_data_sync_one_way_whitelist(expected_whitelist)

        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if save_success:
            return
        self.open(force_reentry=True)

        final_state = self.data_sync_one_way_state()
        mismatched_items = {}
        for item in (
            self.DATA_SYNC_COOKIE_LABEL,
            self.DATA_SYNC_LOCAL_STORAGE_LABEL,
            self.DATA_SYNC_INDEXEDDB_LABEL,
        ):
            key = self._data_sync_state_key(item)
            if key in state and bool(final_state.get(key)) != bool(state.get(key)):
                mismatched_items[key] = (state.get(key), final_state.get(key))
        if mismatched_items:
            raise AssertionError(f"global data sync restore mismatch: {mismatched_items}")
        if bool(final_state.get("one_way_enabled")) != expected_one_way:
            raise AssertionError(
                "global data sync one-way restore mismatch: "
                f"expected={expected_one_way}, actual={final_state.get('one_way_enabled')}"
            )
        if expected_one_way:
            actual_whitelist = self._unique_non_empty(final_state.get("whitelist_groups", []))
            if set(actual_whitelist) != set(expected_whitelist):
                raise AssertionError(
                    "global data sync one-way whitelist restore mismatch: "
                    f"expected={expected_whitelist}, actual={actual_whitelist}"
                )

    def disable_data_sync_one_way(self) -> dict[str, object]:
        """Disable global 数据同步 one-way sync, save, and verify the page finished loading."""
        self._wait_for_data_sync_settings()
        current_state = self.data_sync_one_way_state()
        if not bool(current_state.get("one_way_enabled")):
            self._log_noop_skip("global_settings.disable_data_sync_one_way")
            return current_state

        self._set_data_sync_one_way_enabled(False)
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if save_success:
            return self.data_sync_one_way_state()
        self.open(force_reentry=True)

        final_state = self.data_sync_one_way_state()
        if bool(final_state.get("one_way_enabled")):
            raise AssertionError(
                "global data sync one-way switch was not disabled after save: "
                f"actual={final_state}"
            )
        return final_state

    def data_sync_one_way_enabled(self) -> bool:
        value = self.cdp.evaluate(self._data_sync_one_way_enabled_script())
        if value is None:
            raise RuntimeError("数据同步单向同步 switch was not found")
        return bool(value)

    def _data_sync_state_matches(self, expected: dict[str, object], actual: dict[str, object]) -> bool:
        for key in ("cookie", "local_storage", "indexeddb", "one_way_enabled"):
            if key in expected and bool(actual.get(key)) != bool(expected.get(key)):
                return False
        if bool(expected.get("one_way_enabled")):
            expected_whitelist = set(self._unique_non_empty(expected.get("whitelist_groups", [])))
            actual_whitelist = set(self._unique_non_empty(actual.get("whitelist_groups", [])))
            if expected_whitelist != actual_whitelist:
                return False
        return True

    def configure_clear_all_local_cache_every_open_sync_cloud_data(self) -> None:
        """Set 全局设置 → 清除本地缓存 to clear all cache every open and sync cloud data."""
        self._configure_clear_all_local_cache_every_open(sync_cloud_data=True)

    def configure_clear_all_local_cache_every_open_no_cloud_sync_data(self) -> None:
        """Set 全局设置 → 清除本地缓存 to clear all cache every open without cloud sync."""
        self._configure_clear_all_local_cache_every_open(sync_cloud_data=False)

    def _configure_clear_all_local_cache_every_open(self, *, sync_cloud_data: bool) -> None:
        self._wait_for_clear_local_cache_settings()
        expected_state = {
            "clear_method": self.CLEAR_LOCAL_CACHE_ALL_TEXT,
            "clear_frequency": self.CLEAR_LOCAL_CACHE_EVERY_OPEN_TEXT,
            "sync_cloud_data": bool(sync_cloud_data),
        }
        current_state = self.clear_local_cache_state()
        if self._clear_local_cache_state_matches(expected_state, current_state):
            self._log_noop_skip("global_settings.configure_clear_all_local_cache_every_open")
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        self._select_global_settings_form_select_option(
            self.CLEAR_LOCAL_CACHE_METHOD_LABEL,
            self.CLEAR_LOCAL_CACHE_ALL_TEXT,
        )
        self._select_global_settings_form_select_option(
            self.CLEAR_LOCAL_CACHE_FREQUENCY_LABEL,
            self.CLEAR_LOCAL_CACHE_EVERY_OPEN_TEXT,
        )
        self._set_clear_local_cache_sync_cloud_enabled(sync_cloud_data)
        self._close_select_dropdowns()
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={self.CLEAR_LOCAL_CACHE_SYNC_CLOUD_TEXT},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if not save_success:
            self.open(force_reentry=True)
            self._wait_global_settings_form_select_value(
                self.CLEAR_LOCAL_CACHE_METHOD_LABEL,
                self.CLEAR_LOCAL_CACHE_ALL_TEXT,
            )
            self._wait_global_settings_form_select_value(
                self.CLEAR_LOCAL_CACHE_FREQUENCY_LABEL,
                self.CLEAR_LOCAL_CACHE_EVERY_OPEN_TEXT,
            )
            self._wait_clear_local_cache_sync_cloud_enabled(sync_cloud_data)

    def configure_clear_local_cache_no_clear(self) -> None:
        """Set 全局设置 → 清除本地缓存 → 清除方式 to 不清除 and persist it."""
        self._wait_for_clear_local_cache_settings()
        expected_state = {"clear_method": self.CLEAR_LOCAL_CACHE_NO_CLEAR_TEXT}
        current_state = self.clear_local_cache_state()
        if self._clear_local_cache_state_matches(expected_state, current_state):
            self._log_noop_skip("global_settings.configure_clear_local_cache_no_clear")
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        self._select_global_settings_form_select_option(
            self.CLEAR_LOCAL_CACHE_METHOD_LABEL,
            self.CLEAR_LOCAL_CACHE_NO_CLEAR_TEXT,
        )
        self._close_select_dropdowns()
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names=set(),
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if not save_success:
            self.open(force_reentry=True)
            self._wait_global_settings_form_select_value(
                self.CLEAR_LOCAL_CACHE_METHOD_LABEL,
                self.CLEAR_LOCAL_CACHE_NO_CLEAR_TEXT,
            )

    def clear_local_cache_state(self) -> dict[str, object]:
        """Return persisted global 清除本地缓存 state from the rendered page."""
        self._wait_for_clear_local_cache_settings()
        state: dict[str, object] = {
            "clear_method": self._global_settings_form_select_value(self.CLEAR_LOCAL_CACHE_METHOD_LABEL),
        }
        if self.cdp.evaluate(self._global_settings_form_select_exists_script(self.CLEAR_LOCAL_CACHE_FREQUENCY_LABEL)):
            state["clear_frequency"] = self._global_settings_form_select_value(self.CLEAR_LOCAL_CACHE_FREQUENCY_LABEL)
        sync_cloud_data = self.cdp.evaluate(self._clear_local_cache_sync_cloud_enabled_script())
        if sync_cloud_data is not None:
            state["sync_cloud_data"] = bool(sync_cloud_data)
        return state

    def restore_clear_local_cache_state(self, state: object) -> None:
        """Restore global 清除本地缓存 state captured by clear_local_cache_state()."""
        if not isinstance(state, dict):
            return

        clear_method = str(state.get("clear_method") or "").strip()
        if not clear_method:
            clear_method = self.CLEAR_LOCAL_CACHE_NO_CLEAR_TEXT

        self._wait_for_clear_local_cache_settings()
        expected_state = {"clear_method": clear_method}
        clear_frequency = str(state.get("clear_frequency") or "").strip()
        if clear_frequency:
            expected_state["clear_frequency"] = clear_frequency
        if "sync_cloud_data" in state and self.cdp.evaluate(self._clear_local_cache_sync_cloud_enabled_script()) is not None:
            expected_state["sync_cloud_data"] = bool(state.get("sync_cloud_data"))
        current_state = self.clear_local_cache_state()
        if self._clear_local_cache_state_matches(expected_state, current_state):
            self._log_noop_skip("global_settings.restore_clear_local_cache")
            return

        self._select_global_settings_form_select_option(self.CLEAR_LOCAL_CACHE_METHOD_LABEL, clear_method)

        if clear_frequency and self.cdp.evaluate(
            self._global_settings_form_select_exists_script(self.CLEAR_LOCAL_CACHE_FREQUENCY_LABEL)
        ):
            self._select_global_settings_form_select_option(self.CLEAR_LOCAL_CACHE_FREQUENCY_LABEL, clear_frequency)

        if "sync_cloud_data" in state and self.cdp.evaluate(self._clear_local_cache_sync_cloud_enabled_script()) is not None:
            self._set_clear_local_cache_sync_cloud_enabled(bool(state.get("sync_cloud_data")))

        self._close_select_dropdowns()
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        save_success = self._wait_save_finished()
        if save_success:
            return
        self.open(force_reentry=True)
        final_state = self.clear_local_cache_state()
        mismatches = {
            key: (expected, final_state.get(key))
            for key, expected in expected_state.items()
            if final_state.get(key) != expected
        }
        if mismatches:
            raise AssertionError(f"global clear local cache restore mismatch: {mismatches}")

    def _clear_local_cache_state_matches(self, expected: dict[str, object], actual: dict[str, object]) -> bool:
        for key, expected_value in expected.items():
            if key not in actual:
                return False
            if str(actual.get(key) or "").strip() != str(expected_value or "").strip():
                return False
        return True

    def data_sync_one_way_whitelist_values(self) -> list[str]:
        value = self.cdp.evaluate(self._data_sync_one_way_whitelist_values_script())
        if not isinstance(value, list):
            return []
        return self._unique_non_empty([str(item).strip() for item in value])

    def configure_packet_capture_blocking(self, process_name: str) -> None:
        """Enable packet capture blocking and save the configured process name."""
        clean_process_name = str(process_name or "").strip()
        if not clean_process_name:
            raise ValueError("packet capture process name must not be empty")

        self._wait_for_packet_capture_blocking()
        current_state = self.packet_capture_blocking_state()
        if bool(current_state.get("enabled")) and str(current_state.get("process_name") or "").strip() == clean_process_name:
            self._log_noop_skip("global_settings.configure_packet_capture_blocking")
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        if not self.packet_capture_blocking_enabled():
            self._set_packet_capture_blocking_enabled(True)

        self.cdp.fill_element_by_script(self._packet_capture_process_input_script(), clean_process_name)
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"禁用抓包软件"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_packet_capture_blocking_enabled(True)
        self._wait_packet_capture_process_name(clean_process_name)

    def disable_packet_capture_blocking(self) -> bool:
        """Disable packet capture blocking and save. Return True when this method changed it."""
        changed = False
        for _ in range(3):
            self._wait_for_packet_capture_blocking()
            self._wait_global_setting_states_stable()
            if not self.packet_capture_blocking_enabled():
                return changed

            before_checkboxes, before_switches = self._wait_global_setting_states_stable()
            self._set_packet_capture_blocking_enabled(False)
            self._assert_no_unexpected_existing_state_changes(
                before_checkboxes=before_checkboxes,
                before_switches=before_switches,
                allowed_checkbox_names=set(),
                allowed_switch_names={"禁用抓包软件"},
            )
            self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
            save_success = self._wait_save_finished()
            if save_success:
                return True
            self._wait_packet_capture_blocking_enabled(False)
            changed = True

            time.sleep(1)
            self.open()
            self._wait_global_setting_states_stable()
            if not self.packet_capture_blocking_enabled():
                return changed

        raise AssertionError("禁用抓包软件功能开关关闭保存后仍然保持开启")

    def packet_capture_blocking_enabled(self) -> bool:
        value = self.cdp.evaluate(self._packet_capture_blocking_enabled_script())
        if value is None:
            raise RuntimeError("禁用抓包软件 switch was not found")
        return bool(value)

    def packet_capture_blocking_state(self) -> dict[str, object]:
        self._wait_for_packet_capture_blocking()
        process_name = self.cdp.evaluate(self._packet_capture_process_value_script())
        return {
            "enabled": self.packet_capture_blocking_enabled(),
            "process_name": str(process_name or "").strip(),
        }

    def restore_packet_capture_blocking_state(self, state: object) -> None:
        if not isinstance(state, dict):
            return
        expected_enabled = bool(state.get("enabled"))
        if not expected_enabled:
            self.disable_packet_capture_blocking()
            return

        process_name = str(state.get("process_name") or "").strip()
        self._wait_for_packet_capture_blocking()
        current_state = self.packet_capture_blocking_state()
        if bool(current_state.get("enabled")) and str(current_state.get("process_name") or "").strip() == process_name:
            self._log_noop_skip("global_settings.restore_packet_capture_blocking")
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        self._set_packet_capture_blocking_enabled(True)
        self.cdp.fill_element_by_script(self._packet_capture_process_input_script(), process_name)
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"禁用抓包软件"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_packet_capture_blocking_enabled(True)
        self._wait_packet_capture_process_name(process_name)

    def configure_bookmark_overwrite(self, file_path: str | Path) -> None:
        """Enable bookmark setting, upload a bookmark file, and save overwrite mode."""
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"bookmark file does not exist: {file_path}")

        self._wait_for_bookmark_setting()
        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        if not self.bookmark_setting_enabled():
            self._set_bookmark_setting_enabled(True)

        self._upload_bookmark_file(file_path)
        self._select_bookmark_effect_mode("覆盖")
        self._select_bookmark_overwrite_rule("覆盖为上传的书签")
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"书签设置"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_bookmark_setting_enabled(True)

    def configure_bookmark_append(self, file_path: str | Path) -> None:
        """Enable bookmark setting, upload a bookmark file, and save append mode."""
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"bookmark file does not exist: {file_path}")

        self._wait_for_bookmark_setting()
        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        if not self.bookmark_setting_enabled():
            self._set_bookmark_setting_enabled(True)

        self._upload_bookmark_file(file_path)
        self._select_bookmark_effect_mode("追加")
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"书签设置"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_bookmark_setting_enabled(True)

    def configure_bookmark_clear_existing(self) -> None:
        """Enable bookmark setting and save overwrite mode with clearing existing bookmarks."""
        self._wait_for_bookmark_setting()
        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        if not self.bookmark_setting_enabled():
            self._set_bookmark_setting_enabled(True)

        self._select_bookmark_effect_mode("覆盖")
        self._select_bookmark_overwrite_rule("清空原有书签")
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"书签设置"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_bookmark_setting_enabled(True)

    def disable_bookmark_setting(self) -> bool:
        """Disable bookmark setting and save. Return True when this method changed it."""
        changed = False
        for _ in range(3):
            self._wait_for_bookmark_setting()
            self._wait_global_setting_states_stable()
            if not self.bookmark_setting_enabled():
                return changed

            before_checkboxes, before_switches = self._wait_global_setting_states_stable()
            self._set_bookmark_setting_enabled(False)
            self._assert_no_unexpected_existing_state_changes(
                before_checkboxes=before_checkboxes,
                before_switches=before_switches,
                allowed_checkbox_names=set(),
                allowed_switch_names={"书签设置"},
            )
            self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
            save_success = self._wait_save_finished()
            if save_success:
                return True
            self._wait_bookmark_setting_enabled(False)
            changed = True

            time.sleep(1)
            self.open()
            self._wait_global_setting_states_stable()
            if not self.bookmark_setting_enabled():
                return changed

        raise AssertionError("书签设置功能开关关闭保存后仍然保持开启")

    def bookmark_setting_enabled(self) -> bool:
        value = self.cdp.evaluate(self._bookmark_setting_enabled_script())
        if value is None:
            raise RuntimeError("书签设置 switch was not found")
        return bool(value)

    def bookmark_setting_state(self) -> dict[str, object]:
        self._wait_for_bookmark_setting()
        enabled = self.bookmark_setting_enabled()
        return {
            "enabled": enabled,
            "effect_modes": {
                mode: bool(self.cdp.evaluate(self._bookmark_effect_mode_checked_script(mode)))
                for mode in ("覆盖", "追加", "清空已有书签")
            },
            "text": str(self.cdp.evaluate(self._bookmark_setting_text_script()) or ""),
            "restore_supported": not enabled,
            "restore_note": "" if not enabled else "书签设置开启时页面无法反推出原始上传文件路径，快照只强恢复开关状态。",
        }

    def restore_bookmark_setting_state(self, state: object) -> None:
        if not isinstance(state, dict):
            return
        expected_enabled = bool(state.get("enabled"))
        if not expected_enabled:
            self.disable_bookmark_setting()
            return

        self._wait_for_bookmark_setting()
        current_state = self.bookmark_setting_state()
        if bool(current_state.get("enabled")):
            self._log_noop_skip("global_settings.restore_bookmark_setting")
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        self._set_bookmark_setting_enabled(True)
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"书签设置"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_bookmark_setting_enabled(True)

    def configure_environment_field_display_limit(self, field_names: list[str]) -> None:
        """Enable environment field display limit, select exact fields, and save."""
        clean_fields = [str(item).strip() for item in field_names if str(item).strip()]
        if not clean_fields:
            raise ValueError("environment field display limit requires at least one field")

        self._wait_for_environment_field_display_limit()
        current_state = self.environment_field_display_limit_state()
        if bool(current_state.get("enabled")) and set(current_state.get("fields", [])) == set(clean_fields):
            self._log_noop_skip("global_settings.configure_environment_field_display_limit")
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        if not self.environment_field_display_limit_enabled():
            self._set_environment_field_display_limit_enabled(True)

        self._open_environment_field_display_limit_dialog()
        self._select_environment_field_display_limit_fields(clean_fields)
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names=set(self.ENVIRONMENT_FIELD_DISPLAY_LIMIT_LABELS),
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_environment_field_display_limit_enabled(True)
        self._wait_environment_field_display_limit_current_setting(clean_fields)

    def disable_environment_field_display_limit(self) -> bool:
        """Disable environment field display limit and save. Return True when changed."""
        changed = False
        for _ in range(3):
            self._wait_for_environment_field_display_limit()
            self._wait_global_setting_states_stable()
            if not self.environment_field_display_limit_enabled():
                return changed

            before_checkboxes, before_switches = self._wait_global_setting_states_stable()
            self._set_environment_field_display_limit_enabled(False)
            self._assert_no_unexpected_existing_state_changes(
                before_checkboxes=before_checkboxes,
                before_switches=before_switches,
                allowed_checkbox_names=set(),
                allowed_switch_names=set(self.ENVIRONMENT_FIELD_DISPLAY_LIMIT_LABELS),
            )
            self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
            save_success = self._wait_save_finished()
            if save_success:
                return True
            self._wait_environment_field_display_limit_enabled(False)
            changed = True

            time.sleep(1)
            self.open()
            self._wait_global_setting_states_stable()
            if not self.environment_field_display_limit_enabled():
                return changed

        raise AssertionError("环境列表字段权限功能开关关闭保存后仍然保持开启")

    def environment_field_display_limit_enabled(self) -> bool:
        value = self.cdp.evaluate(self._environment_field_display_limit_enabled_script())
        if value is None:
            raise RuntimeError("环境列表字段权限 switch was not found")
        return bool(value)

    def environment_field_display_limit_state(self) -> dict[str, object]:
        self._wait_for_environment_field_display_limit()
        return {
            "enabled": self.environment_field_display_limit_enabled(),
            "fields": self._environment_field_display_limit_current_fields(),
        }

    def restore_environment_field_display_limit_state(self, state: object) -> None:
        if not isinstance(state, dict):
            return
        expected_enabled = bool(state.get("enabled"))
        fields = [str(item) for item in state.get("fields", []) if str(item).strip()]
        if not expected_enabled:
            self.disable_environment_field_display_limit()
            return
        self._wait_for_environment_field_display_limit()
        current_state = self.environment_field_display_limit_state()
        if bool(current_state.get("enabled")) and (not fields or set(current_state.get("fields", [])) == set(fields)):
            self._log_noop_skip("global_settings.restore_environment_field_display_limit")
            return
        if fields:
            self.configure_environment_field_display_limit(fields)
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        self._set_environment_field_display_limit_enabled(True)
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names=set(self.ENVIRONMENT_FIELD_DISPLAY_LIMIT_LABELS),
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_environment_field_display_limit_enabled(True)

    def configure_environment_list_pagination_setting(self, page_size_text: str = "20 条/页") -> None:
        """Enable environment list pagination setting, select page size, and save."""
        clean_page_size = str(page_size_text or "").replace(" ", "").strip()
        if not clean_page_size:
            raise ValueError("environment list pagination setting requires a page size")

        self._wait_for_environment_list_pagination_setting()
        current_state = self.environment_list_pagination_setting_state()
        if bool(current_state.get("enabled")) and str(current_state.get("page_size") or "").replace(" ", "").strip() == clean_page_size:
            self._log_noop_skip("global_settings.configure_environment_list_pagination")
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        if not self.environment_list_pagination_setting_enabled():
            self._set_environment_list_pagination_setting_enabled(True)

        self._select_environment_list_pagination_page_size(clean_page_size)
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"环境列表分页设置"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_environment_list_pagination_setting_enabled(True)
        self._wait_environment_list_pagination_page_size(clean_page_size)

    def disable_environment_list_pagination_setting(self) -> bool:
        """Disable environment list pagination setting and save. Return True when changed."""
        changed = False
        for _ in range(3):
            self._wait_for_environment_list_pagination_setting()
            self._wait_global_setting_states_stable()
            if not self.environment_list_pagination_setting_enabled():
                return changed

            before_checkboxes, before_switches = self._wait_global_setting_states_stable()
            self._set_environment_list_pagination_setting_enabled(False)
            self._assert_no_unexpected_existing_state_changes(
                before_checkboxes=before_checkboxes,
                before_switches=before_switches,
                allowed_checkbox_names=set(),
                allowed_switch_names={"环境列表分页设置"},
            )
            self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
            save_success = self._wait_save_finished()
            if save_success:
                return True
            self._wait_environment_list_pagination_setting_enabled(False)
            changed = True

            time.sleep(1)
            self.open()
            self._wait_global_setting_states_stable()
            if not self.environment_list_pagination_setting_enabled():
                return changed

        raise AssertionError("环境列表分页设置功能开关关闭保存后仍然保持开启")

    def environment_list_pagination_setting_enabled(self) -> bool:
        value = self.cdp.evaluate(self._environment_list_pagination_setting_enabled_script())
        if value is None:
            raise RuntimeError("环境列表分页设置 switch was not found")
        return bool(value)

    def environment_list_pagination_setting_state(self) -> dict[str, object]:
        self._wait_for_environment_list_pagination_setting()
        return {
            "enabled": self.environment_list_pagination_setting_enabled(),
            "page_size": self._environment_list_pagination_page_size_value(),
        }

    def restore_environment_list_pagination_setting_state(self, state: object) -> None:
        if not isinstance(state, dict):
            return
        expected_enabled = bool(state.get("enabled"))
        page_size = str(state.get("page_size") or "").strip()
        if not expected_enabled:
            self.disable_environment_list_pagination_setting()
            return
        self._wait_for_environment_list_pagination_setting()
        current_state = self.environment_list_pagination_setting_state()
        current_page_size = str(current_state.get("page_size") or "").replace(" ", "").strip()
        expected_page_size = page_size.replace(" ", "").strip()
        if bool(current_state.get("enabled")) and (not expected_page_size or current_page_size == expected_page_size):
            self._log_noop_skip("global_settings.restore_environment_list_pagination")
            return
        if page_size:
            self.configure_environment_list_pagination_setting(page_size)
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        self._set_environment_list_pagination_setting_enabled(True)
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"环境列表分页设置"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_environment_list_pagination_setting_enabled(True)

    def configure_environment_list_sort(self, field_text: str, direction_text: str) -> None:
        """Enable environment list sort limit, choose field/direction, and save."""
        clean_field = str(field_text or "").strip()
        clean_direction = str(direction_text or "").strip()
        if not clean_field:
            raise ValueError("environment list sort requires a sort field")
        if clean_direction not in {"升序", "降序"}:
            raise ValueError(f"unsupported environment list sort direction: {clean_direction}")

        self._wait_for_environment_list_sort()
        current_state = self.environment_list_sort_state()
        if (
            bool(current_state.get("enabled"))
            and str(current_state.get("field") or "").strip() == clean_field
            and str(current_state.get("direction") or "").strip() == clean_direction
        ):
            self._log_noop_skip("global_settings.configure_environment_list_sort")
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        if not self.environment_list_sort_enabled():
            self._set_environment_list_sort_enabled(True)

        self._select_environment_list_sort_option("排序字段", clean_field)
        self._select_environment_list_sort_option("排序方式", clean_direction)
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"环境列表排序"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_environment_list_sort_enabled(True)
        self._wait_environment_list_sort_option("排序字段", clean_field)
        self._wait_environment_list_sort_option("排序方式", clean_direction)

    def disable_environment_list_sort(self) -> bool:
        """Disable environment list sort limit and save. Return True when changed."""
        changed = False
        for _ in range(3):
            self._wait_for_environment_list_sort()
            self._wait_global_setting_states_stable()
            if not self.environment_list_sort_enabled():
                return changed

            before_checkboxes, before_switches = self._wait_global_setting_states_stable()
            self._set_environment_list_sort_enabled(False)
            self._assert_no_unexpected_existing_state_changes(
                before_checkboxes=before_checkboxes,
                before_switches=before_switches,
                allowed_checkbox_names=set(),
                allowed_switch_names={"环境列表排序"},
            )
            self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
            save_success = self._wait_save_finished()
            if save_success:
                return True
            self._wait_environment_list_sort_enabled(False)
            changed = True

            time.sleep(1)
            self.open()
            self._wait_global_setting_states_stable()
            if not self.environment_list_sort_enabled():
                return changed

        raise AssertionError("环境列表排序功能开关关闭保存后仍然保持开启")

    def environment_list_sort_enabled(self) -> bool:
        value = self.cdp.evaluate(self._environment_list_sort_enabled_script())
        if value is None:
            raise RuntimeError("环境列表排序 switch was not found")
        return bool(value)

    def environment_list_sort_state(self) -> dict[str, object]:
        self._wait_for_environment_list_sort()
        return {
            "enabled": self.environment_list_sort_enabled(),
            "field": self._environment_list_sort_option_value("排序字段"),
            "direction": self._environment_list_sort_option_value("排序方式"),
        }

    def restore_environment_list_sort_state(self, state: object) -> None:
        if not isinstance(state, dict):
            return
        expected_enabled = bool(state.get("enabled"))
        field = str(state.get("field") or "").strip()
        direction = str(state.get("direction") or "").strip()
        if not expected_enabled:
            self.disable_environment_list_sort()
            return
        self._wait_for_environment_list_sort()
        current_state = self.environment_list_sort_state()
        if (
            bool(current_state.get("enabled"))
            and (not field or str(current_state.get("field") or "").strip() == field)
            and (not direction or str(current_state.get("direction") or "").strip() == direction)
        ):
            self._log_noop_skip("global_settings.restore_environment_list_sort")
            return
        if field and direction:
            self.configure_environment_list_sort(field, direction)
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        self._set_environment_list_sort_enabled(True)
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"环境列表排序"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_environment_list_sort_enabled(True)

    def configure_website_restriction_blocklist(
        self,
        urls: list[str],
        shortcut_name: str = "Chrome 应用商店",
    ) -> None:
        """Enable website restriction and save a blocklist with a shortcut option."""
        self._wait_for_website_restriction()
        shortcut_names = self._website_shortcut_candidates(shortcut_name)
        expected_state = {
            "enabled": True,
            "mode": "禁止访问指定网址",
            "urls": [str(item) for item in urls if str(item).strip()],
        }
        current_state = self.website_restriction_state()
        shortcut_states = current_state.get("shortcut_states", {})
        shortcut_matched = isinstance(shortcut_states, dict) and any(
            bool(shortcut_states.get(candidate)) for candidate in shortcut_names
        )
        if self._website_restriction_state_matches(expected_state, current_state) and shortcut_matched:
            self._log_noop_skip("global_settings.configure_website_restriction_blocklist")
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        if not self.website_restriction_enabled():
            self._set_website_restriction_enabled(True)

        self._select_website_restriction_mode("禁止访问指定网址")
        self._ensure_website_restriction_shortcut_checked(shortcut_name)
        self.cdp.fill_element_by_script(
            self._website_restriction_url_textarea_script(),
            "\n".join(urls),
        )
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(shortcut_names),
            allowed_switch_names={"访问网站限制"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_website_restriction_enabled(True)
        self._wait_website_restriction_urls(urls)

    def configure_website_restriction_allowlist(self, urls: list[str]) -> None:
        """Enable website restriction and save an allowlist."""
        self._wait_for_website_restriction()
        expected_state = {
            "enabled": True,
            "mode": "允许访问指定网址",
            "urls": [str(item) for item in urls if str(item).strip()],
        }
        current_state = self.website_restriction_state()
        if self._website_restriction_state_matches(expected_state, current_state):
            self._log_noop_skip("global_settings.configure_website_restriction_allowlist")
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        if not self.website_restriction_enabled():
            self._set_website_restriction_enabled(True)

        self._select_website_restriction_mode("允许访问指定网址")
        self.cdp.fill_element_by_script(
            self._website_restriction_url_textarea_script(),
            "\n".join(urls),
        )
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"访问网站限制"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_website_restriction_enabled(True)
        self._wait_website_restriction_mode("允许访问指定网址")
        self._wait_website_restriction_urls(urls)

    def validate_website_restriction_controls_without_saving(
        self,
        test_url: str,
        shortcut_name: str | None = "Chrome 应用商店",
        mode_text: str = "禁止访问指定网址",
    ) -> None:
        """Probe website restriction controls and restore UI state without saving."""
        self._wait_for_website_restriction()
        shortcut_names = self._website_shortcut_candidates(shortcut_name) if shortcut_name else tuple()
        baseline_checkboxes, baseline_switches = self._wait_global_setting_states_stable()
        baseline_enabled = self.website_restriction_enabled()

        if not baseline_enabled:
            self._set_website_restriction_enabled(True)

        after_toggle_checkboxes, after_toggle_switches = self._wait_global_setting_states_stable()
        self._assert_no_unexpected_existing_state_changes_from_states(
            before_checkboxes=baseline_checkboxes,
            before_switches=baseline_switches,
            after_checkboxes=after_toggle_checkboxes,
            after_switches=after_toggle_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names={"访问网站限制"},
        )

        original_url_value = self.cdp.evaluate(self._website_restriction_url_value_script())
        self._select_website_restriction_mode(mode_text)
        if shortcut_name:
            self._ensure_website_restriction_shortcut_checked(shortcut_name)
        self.cdp.fill_element_by_script(self._website_restriction_url_textarea_script(), test_url)

        after_content_checkboxes, after_content_switches = self._wait_global_setting_states_stable()
        self._assert_no_unexpected_existing_state_changes_from_states(
            before_checkboxes=baseline_checkboxes,
            before_switches=baseline_switches,
            after_checkboxes=after_content_checkboxes,
            after_switches=after_content_switches,
            allowed_checkbox_names=set(shortcut_names),
            allowed_switch_names={"访问网站限制"},
        )
        if self.cdp.evaluate(self._website_restriction_url_value_script()) != test_url:
            raise AssertionError("访问网站限制网址列表输入后未回显预期内容")
        if shortcut_name and not self.cdp.evaluate(self._website_restriction_shortcut_checked_script(shortcut_names)):
            raise AssertionError(f"访问网站限制快捷选择未保持勾选: {shortcut_name}")
        if not self.cdp.evaluate(self._website_restriction_radio_checked_script(mode_text)):
            raise AssertionError(f"访问网站限制方式未保持为：{mode_text}")

        self.cdp.fill_element_by_script(
            self._website_restriction_url_textarea_script(),
            str(original_url_value or ""),
        )
        if self.website_restriction_enabled() != baseline_enabled:
            self._set_website_restriction_enabled(baseline_enabled)

        final_checkboxes, final_switches = self._wait_global_setting_states_stable()
        self._assert_no_unexpected_existing_state_changes_from_states(
            before_checkboxes=baseline_checkboxes,
            before_switches=baseline_switches,
            after_checkboxes=final_checkboxes,
            after_switches=final_switches,
            allowed_checkbox_names=set(),
            allowed_switch_names=set(),
        )
        if self.website_restriction_enabled() != baseline_enabled:
            raise AssertionError("访问网站限制非保存探针结束后未恢复原始开关状态")

    def disable_website_restriction(self) -> bool:
        """Disable website restriction and save. Return True when this method changed it."""
        changed = False
        for _ in range(3):
            self._wait_for_website_restriction()
            self._wait_global_setting_states_stable()
            if not self.website_restriction_enabled():
                return changed

            before_checkboxes, before_switches = self._wait_global_setting_states_stable()
            self._set_website_restriction_enabled(False)
            self._assert_no_unexpected_existing_state_changes(
                before_checkboxes=before_checkboxes,
                before_switches=before_switches,
                allowed_checkbox_names=set(),
                allowed_switch_names={"访问网站限制"},
            )
            self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
            save_success = self._wait_save_finished()
            if save_success:
                return True
            self._wait_website_restriction_enabled(False)
            changed = True

            time.sleep(1)
            self.open()
            self._wait_global_setting_states_stable()
            if not self.website_restriction_enabled():
                return changed

        raise AssertionError("访问网站限制功能开关关闭保存后仍然保持开启")

    def website_restriction_enabled(self) -> bool:
        value = self.cdp.evaluate(self._website_restriction_enabled_script())
        if value is None:
            raise RuntimeError("访问网站限制 switch was not found")
        return bool(value)

    def website_restriction_state(self) -> dict[str, object]:
        self._wait_for_website_restriction()
        return {
            "enabled": self.website_restriction_enabled(),
            "mode": self._website_restriction_selected_mode(),
            "urls": self._website_restriction_url_lines(),
            "shortcut_states": self._website_restriction_shortcut_states(),
        }

    def restore_website_restriction_state(self, state: object) -> None:
        if not isinstance(state, dict):
            return
        expected_enabled = bool(state.get("enabled"))
        if not expected_enabled:
            self.disable_website_restriction()
            return

        mode = str(state.get("mode") or "").strip()
        urls = [str(item) for item in state.get("urls", []) if str(item).strip()]
        shortcut_states = state.get("shortcut_states", {})
        if not isinstance(shortcut_states, dict):
            shortcut_states = {}

        self._wait_for_website_restriction()
        current_state = self.website_restriction_state()
        if self._website_restriction_state_matches(
            {
                "enabled": True,
                "mode": mode,
                "urls": urls,
                "shortcut_states": shortcut_states,
            },
            current_state,
        ):
            self._log_noop_skip("global_settings.restore_website_restriction")
            return

        before_checkboxes, before_switches = self._wait_global_setting_states_stable()
        self._set_website_restriction_enabled(True)
        if mode:
            self._select_website_restriction_mode(mode)
        for shortcut_name, checked in shortcut_states.items():
            self._set_website_restriction_shortcut_checked(str(shortcut_name), bool(checked))
        self.cdp.fill_element_by_script(
            self._website_restriction_url_textarea_script(),
            "\n".join(urls),
        )
        self._assert_no_unexpected_existing_state_changes(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            allowed_checkbox_names=set(str(key) for key in shortcut_states),
            allowed_switch_names={"访问网站限制"},
        )
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_website_restriction_enabled(True)
        if mode:
            self._wait_website_restriction_mode(mode)
        self._wait_website_restriction_urls(urls)

    def _website_restriction_state_matches(self, expected: dict[str, object], actual: dict[str, object]) -> bool:
        if bool(actual.get("enabled")) != bool(expected.get("enabled")):
            return False
        if not bool(expected.get("enabled")):
            return True
        expected_mode = str(expected.get("mode") or "").strip()
        if expected_mode and str(actual.get("mode") or "").strip() != expected_mode:
            return False
        expected_urls = [str(item).strip() for item in expected.get("urls", []) if str(item).strip()]
        actual_urls = [str(item).strip() for item in actual.get("urls", []) if str(item).strip()]
        if expected_urls != actual_urls:
            return False
        expected_shortcuts = expected.get("shortcut_states")
        actual_shortcuts = actual.get("shortcut_states")
        if isinstance(expected_shortcuts, dict):
            if not isinstance(actual_shortcuts, dict):
                return False
            for shortcut_name, checked in expected_shortcuts.items():
                if bool(actual_shortcuts.get(str(shortcut_name))) != bool(checked):
                    return False
        return True

    @staticmethod
    def _label_candidates(label_text: str | tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(label_text, tuple):
            return tuple(str(item).strip() for item in label_text if str(item).strip())
        return (str(label_text).strip(),)

    def _resolve_visible_checkbox_label(self, label_text: str | tuple[str, ...]) -> str:
        for candidate in self._label_candidates(label_text):
            if self.cdp.evaluate(self._checkbox_exists_script(candidate)):
                return candidate
        candidates = self._label_candidates(label_text)
        raise TimeoutError(f"checkbox was not found: {candidates}")

    def ensure_checkbox_enabled(self, label_text: str | tuple[str, ...]) -> bool:
        """Enable one global setting checkbox without allowing other checkbox changes."""
        label_text = self._resolve_visible_checkbox_label(label_text)
        self._wait_for_checkbox(label_text)
        before_states = self._wait_checkbox_states_stable()
        if self.checkbox_checked(label_text):
            return False

        self.cdp.click_element_by_script(self._checkbox_script(label_text))
        self._wait_checkbox_checked(label_text, True)
        after_states = self.checkbox_states()
        self._assert_only_checkbox_changed(label_text, before_states, after_states)
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_checkbox_states_stable()
        self._wait_checkbox_checked(label_text, True)
        return True

    def ensure_checkbox_disabled(self, label_text: str | tuple[str, ...]) -> bool:
        """Disable one global setting checkbox without allowing other checkbox changes."""
        label_text = self._resolve_visible_checkbox_label(label_text)
        self._wait_for_checkbox(label_text)
        before_states = self._wait_checkbox_states_stable()
        if not self.checkbox_checked(label_text):
            return False

        self.cdp.click_element_by_script(self._checkbox_script(label_text))
        self._wait_checkbox_checked(label_text, False)
        after_states = self.checkbox_states()
        self._assert_only_checkbox_changed(label_text, before_states, after_states, expected_change=(True, False))
        self.cdp.click_element_by_script(self._visible_button_by_text_script("确定"))
        self._wait_save_finished()
        self._wait_checkbox_states_stable()
        self._wait_checkbox_checked(label_text, False)
        return True

    def disable_view_password_checked(self) -> bool:
        return self.checkbox_checked("禁止查看网站密码")

    def checkbox_checked(self, label_text: str) -> bool:
        value = self.cdp.evaluate(self._checkbox_checked_script(label_text))
        if value is None:
            raise RuntimeError(f"{label_text} checkbox was not found")
        return bool(value)

    def checkbox_states(self) -> dict[str, bool]:
        value = self.cdp.evaluate(
            """
            () => {
                const checkboxSelector = __CHECKBOX_SELECTOR__;
                const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                };
                const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const states = {};
                for (const checkbox of Array.from(document.querySelectorAll(checkboxSelector)).filter(visible)) {
                    if (!checkbox.classList.contains("el-checkbox")) continue;
                    const text = clean(checkbox.innerText || checkbox.textContent);
                    if (!text) continue;
                    const input = checkbox.querySelector(__CHECKBOX_INPUT_SELECTOR__);
                    const stateEl = checkbox.querySelector(__CHECKBOX_STATE_SELECTOR__) || checkbox;
                    states[text] = input ? Boolean(input.checked) : stateEl.classList.contains("is-checked");
                }
                return states;
            }
            """.replace("__CHECKBOX_SELECTOR__", repr(self.locator("checkbox_candidates")))
            .replace("__CHECKBOX_INPUT_SELECTOR__", repr(self.locator("checkbox_input")))
            .replace("__CHECKBOX_STATE_SELECTOR__", repr(self.locator("checkbox_state")))
        )
        if not isinstance(value, dict):
            return {}
        return {str(key): bool(item) for key, item in value.items()}

    def switch_states(self) -> dict[str, bool]:
        value = self.cdp.evaluate(
            """
            () => {
                const switchSelector = __SWITCH_SELECTOR__;
                const formItemSelector = __FORM_ITEM_SELECTOR__;
                const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                };
                const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const state = (switchEl) => {
                    const input = switchEl.querySelector("input");
                    const aria = input?.getAttribute("aria-checked") || switchEl.getAttribute("aria-checked") || "";
                    if (aria === "true") return true;
                    if (aria === "false") return false;
                    return switchEl.classList.contains("is-checked") || Boolean(input?.checked);
                };
                const states = {};
                for (const switchEl of Array.from(document.querySelectorAll(switchSelector)).filter(visible)) {
                    const item = switchEl.closest(formItemSelector) || switchEl.parentElement || switchEl;
                    let text = clean(item.innerText || item.textContent);
                    if (!text) {
                        const rect = switchEl.getBoundingClientRect();
                        const candidates = Array.from(document.querySelectorAll(formItemSelector))
                            .filter(visible)
                            .map((el) => ({ el, text: clean(el.innerText || el.textContent), rect: el.getBoundingClientRect() }))
                            .filter((item) => item.text)
                            .filter((item) => Math.abs(item.rect.y - rect.y) < 120)
                            .sort((left, right) => Math.abs(left.rect.y - rect.y) - Math.abs(right.rect.y - rect.y));
                        text = candidates[0]?.text || "";
                    }
                    if (!text) continue;
                    const name = text.split(" ")[0] || text;
                    states[name] = state(switchEl);
                }
                return states;
            }
            """.replace("__SWITCH_SELECTOR__", repr(self.locator("switch"))).replace(
                "__FORM_ITEM_SELECTOR__",
                repr(self.locator("form_item")),
            )
        )
        if not isinstance(value, dict):
            return {}
        return {str(key): bool(item) for key, item in value.items()}

    def _assert_no_unexpected_existing_state_changes(
        self,
        before_checkboxes: dict[str, bool],
        before_switches: dict[str, bool],
        allowed_checkbox_names: set[str],
        allowed_switch_names: set[str],
    ) -> None:
        after_checkboxes = self.checkbox_states()
        after_switches = self.switch_states()
        self._assert_no_unexpected_existing_state_changes_from_states(
            before_checkboxes=before_checkboxes,
            before_switches=before_switches,
            after_checkboxes=after_checkboxes,
            after_switches=after_switches,
            allowed_checkbox_names=allowed_checkbox_names,
            allowed_switch_names=allowed_switch_names,
        )

    def _assert_no_unexpected_existing_state_changes_from_states(
        self,
        before_checkboxes: dict[str, bool],
        before_switches: dict[str, bool],
        after_checkboxes: dict[str, bool],
        after_switches: dict[str, bool],
        allowed_checkbox_names: set[str],
        allowed_switch_names: set[str],
    ) -> None:
        changed_checkboxes = {
            name: (before_checkboxes[name], after_checkboxes.get(name))
            for name in before_checkboxes
            if name in after_checkboxes
            and before_checkboxes[name] != after_checkboxes.get(name)
            and name not in allowed_checkbox_names
        }
        changed_switches = {
            name: (before_switches[name], after_switches.get(name))
            for name in before_switches
            if name in after_switches
            and before_switches[name] != after_switches.get(name)
            and name not in allowed_switch_names
        }
        if changed_checkboxes or changed_switches:
            raise AssertionError(
                "unexpected global settings state changes before save: "
                f"checkboxes={changed_checkboxes}, switches={changed_switches}"
            )

    def _wait_global_setting_states_stable(
        self,
        timeout_seconds: int | None = None,
    ) -> tuple[dict[str, bool], dict[str, bool]]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        stable_since = 0.0
        previous: tuple[dict[str, bool], dict[str, bool]] | None = None
        last: tuple[dict[str, bool], dict[str, bool]] = ({}, {})
        while time.time() < deadline:
            self._wait_until_not_loading()
            current = (self.checkbox_states(), self.switch_states())
            if current[0] and current == previous:
                if stable_since == 0:
                    stable_since = time.time()
                if time.time() - stable_since >= 1.5:
                    return current
            else:
                stable_since = 0.0
                previous = current
            last = current
            time.sleep(0.3)
        raise TimeoutError(f"global settings states did not become stable: checkboxes={last[0]}, switches={last[1]}")

    def _wait_for_global_settings_page(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._global_settings_page_visible():
                return
            time.sleep(0.2)
        raise TimeoutError("global settings page did not appear")

    def _global_settings_page_visible(self) -> bool:
        return bool(
            self.cdp.evaluate(
                """
                () => {
                    const route = String(window.location.hash || "")
                        .split("?")[0]
                        .replace(/\\/+$/, "");
                    if (!(route === "#/setting" || route.startsWith("#/setting/"))) return false;
                    const marker = document.querySelector(__MARKER_SELECTOR__);
                    const text = marker ? (marker.innerText || marker.textContent || "") : "";
                    return text.includes("全局设置") && text.includes("禁止查看网站密码");
                }
                """.replace(
                    "__MARKER_SELECTOR__",
                    repr(self.locator("global_settings_page_marker")),
                )
            )
        )

    def _global_settings_route_active(self) -> bool:
        return bool(
            self.cdp.evaluate(
                """
                () => {
                    const route = String(window.location.hash || "")
                        .split("?")[0]
                        .replace(/\\/+$/, "");
                    return route === "#/setting" || route.startsWith("#/setting/");
                }
                """
            )
        )

    def _open_environment_management_for_retry(self) -> None:
        self._dismiss_blocking_overlays()
        self.cdp.click_element_by_script(
            self._visible_text_element_script(
                "global_settings_menu_candidates",
                "环境管理",
                exact=True,
            )
        )
        self._confirm_leave_unsaved_settings_if_present()
        self._wait_for_environment_management_page()

    def _confirm_leave_unsaved_settings_if_present(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            message_visible = bool(
                self.cdp.evaluate(
                    """
                    () => {
                        const visible = (el) => {
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== "none"
                                && style.visibility !== "hidden"
                                && rect.width > 0
                                && rect.height > 0;
                        };
                        const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                        return Array.from(document.querySelectorAll(__MESSAGE_BOX_SELECTOR__))
                            .filter(visible)
                            .some((item) => clean(item.innerText || item.textContent).includes("设置未保存"));
                    }
                    """.replace("__MESSAGE_BOX_SELECTOR__", repr(self.locator("message_box")))
                )
            )
            if not message_visible:
                return
            self.cdp.click_element_by_script(self._active_dialog_button_script("确定"))
            self._wait_for_overlay_closed()
            return

    def _wait_for_environment_management_page(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        stable_since = 0.0
        while time.time() < deadline:
            on_environment_route = bool(
                self.cdp.evaluate(
                    """
                    () => {
                        const route = String(window.location.hash || "")
                            .split("?")[0]
                            .replace(/\\/+$/, "");
                        return route === "#/environment/envList"
                            || route.startsWith("#/environment/envList/");
                    }
                    """
                )
            )
            if on_environment_route and not self._has_visible_loading():
                if stable_since == 0:
                    stable_since = time.time()
                if time.time() - stable_since >= 0.5:
                    return
            else:
                stable_since = 0.0
            time.sleep(0.1)
        raise TimeoutError("environment management page did not become ready for global-settings retry")

    def _wait_for_overlay_closed(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            visible_overlay_count = self.cdp.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== "none"
                            && style.visibility !== "hidden"
                            && rect.width > 0
                            && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(__OVERLAY_SELECTOR__))
                        .filter(visible).length;
                }
                """.replace("__OVERLAY_SELECTOR__", repr(self.locator("blocking_overlay")))
            )
            if int(visible_overlay_count or 0) == 0:
                return
            time.sleep(0.3)
        raise TimeoutError("overlay did not close")

    def _wait_operation_prompt_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_text = ""
        while time.time() < deadline:
            last_text = str(
                self.cdp.evaluate(
                    """
                    () => {
                        const visible = (el) => {
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== "none"
                                && style.visibility !== "hidden"
                                && rect.width > 0
                                && rect.height > 0;
                        };
                        const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                        return Array.from(document.querySelectorAll(__DIALOG_OR_MESSAGE_BOX_SELECTOR__))
                            .filter(visible)
                            .map((overlay) => clean(overlay.innerText || overlay.textContent))
                            .join("\\n");
                    }
                    """.replace(
                        "__DIALOG_OR_MESSAGE_BOX_SELECTOR__",
                        repr(self.locator("dialog_or_message_box")),
                    )
                )
                or ""
            )
            if "操作提示" in last_text:
                return
            time.sleep(0.2)
        raise TimeoutError(f"操作提示 dialog did not appear: last_text={last_text}")

    def _wait_for_checkbox(self, label_text: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._checkbox_exists_script(label_text)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"{label_text} checkbox did not appear")

    def _wait_for_cookie_data_sync(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._cookie_data_sync_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("数据同步 Cookie checkbox did not appear")

    def _wait_cookie_data_sync_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._cookie_data_sync_enabled_script()) is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"数据同步 Cookie checkbox state did not become expected: {expected}")

    def _wait_for_local_storage_data_sync(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._local_storage_data_sync_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("数据同步 Local Storage checkbox did not appear")

    def _wait_local_storage_data_sync_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._local_storage_data_sync_enabled_script()) is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"数据同步 Local Storage checkbox state did not become expected: {expected}")

    def _wait_for_indexeddb_data_sync(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._indexeddb_data_sync_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("数据同步 IndexedDB checkbox did not appear")

    def _wait_indexeddb_data_sync_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._indexeddb_data_sync_enabled_script()) is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"数据同步 IndexedDB checkbox state did not become expected: {expected}")

    def _wait_for_data_sync_settings(self) -> None:
        self._wait_for_cookie_data_sync()
        self._wait_for_local_storage_data_sync()
        self._wait_for_indexeddb_data_sync()
        self._wait_for_data_sync_one_way_sync()

    def _wait_for_data_sync_one_way_sync(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._data_sync_one_way_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("数据同步单向同步 switch did not appear")

    def _wait_data_sync_checked(
        self,
        item_text: str,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._data_sync_enabled_script(item_text)) is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"数据同步 {item_text} checkbox state did not become expected: {expected}")

    def _wait_data_sync_one_way_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._data_sync_one_way_enabled_script()) is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"数据同步单向同步 switch state did not become expected: {expected}")

    def _wait_data_sync_one_way_whitelist_visible(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._data_sync_one_way_whitelist_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("数据同步单向同步白名单 did not appear")

    def _set_data_sync_checked(self, item_text: str, expected: bool) -> None:
        current = self.cdp.evaluate(self._data_sync_enabled_script(item_text))
        if current is None:
            raise RuntimeError(f"数据同步 {item_text} checkbox was not found")
        if bool(current) is expected:
            return
        self.cdp.click_element_by_script(self._data_sync_checkbox_script(item_text))
        self._wait_data_sync_checked(item_text, expected)

    def _set_data_sync_one_way_enabled(self, expected: bool) -> None:
        current = self.cdp.evaluate(self._data_sync_one_way_enabled_script())
        if current is None:
            raise RuntimeError("数据同步单向同步 switch was not found")
        if bool(current) is expected:
            return
        self.cdp.click_element_by_script(self._data_sync_one_way_switch_script())
        self._wait_data_sync_one_way_enabled(expected)

    def _clear_data_sync_one_way_whitelist(self) -> None:
        self._close_select_dropdowns()
        for _ in range(12):
            selected_groups = self.data_sync_one_way_whitelist_values()
            if not selected_groups:
                return
            clicked = bool(self.cdp.evaluate(self._click_first_data_sync_one_way_whitelist_close_script()))
            if not clicked:
                raise TimeoutError(
                    "数据同步单向同步白名单 close button was not found: "
                    f"selected={selected_groups}"
                )
            time.sleep(0.3)
            self._close_select_dropdowns()
        remaining_groups = self.data_sync_one_way_whitelist_values()
        if remaining_groups:
            raise TimeoutError(f"数据同步单向同步白名单 was not cleared: actual={remaining_groups}")

    def _select_data_sync_one_way_whitelist(self, group_names: list[str]) -> None:
        expected_groups = self._unique_non_empty(group_names)
        for group_name in expected_groups:
            if group_name in self.data_sync_one_way_whitelist_values():
                continue
            selected = False
            for _ in range(3):
                if not self._dropdown_option_visible(group_name):
                    self.cdp.click_element_by_script(self._data_sync_one_way_whitelist_select_script())
                    time.sleep(0.3)
                try:
                    self.cdp.click_element_by_script(self._select_dropdown_option_script(group_name), timeout=3000)
                    self._wait_data_sync_one_way_whitelist_selected([group_name])
                    selected = True
                    break
                except TimeoutError:
                    time.sleep(0.3)
            if not selected:
                raise TimeoutError(f"数据同步单向同步白名单 group was not selected: {group_name}")
        self._wait_data_sync_one_way_whitelist_exact(expected_groups)

    def _wait_data_sync_one_way_whitelist_selected(self, expected_groups: list[str]) -> None:
        timeout_seconds = config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        expected = set(self._unique_non_empty(expected_groups))
        last_groups: list[str] = []
        while time.time() < deadline:
            last_groups = self.data_sync_one_way_whitelist_values()
            if expected.issubset(set(last_groups)):
                return
            time.sleep(0.2)
        raise TimeoutError(
            "数据同步单向同步白名单 groups were not selected: "
            f"expected={sorted(expected)}, actual={last_groups}"
        )

    def _wait_data_sync_one_way_whitelist_exact(self, expected_groups: list[str]) -> None:
        timeout_seconds = config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        expected = set(self._unique_non_empty(expected_groups))
        last_groups: list[str] = []
        while time.time() < deadline:
            last_groups = self.data_sync_one_way_whitelist_values()
            if set(last_groups) == expected:
                return
            time.sleep(0.2)
        raise TimeoutError(
            "数据同步单向同步白名单 was not exact: "
            f"expected={sorted(expected)}, actual={last_groups}"
        )

    def _wait_for_website_restriction(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._website_restriction_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("访问网站限制 switch did not appear")

    def _wait_for_bookmark_setting(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._bookmark_setting_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("书签设置 switch did not appear")

    def _wait_for_environment_field_display_limit(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._environment_field_display_limit_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("环境列表字段权限 switch did not appear")

    def _wait_for_environment_list_pagination_setting(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._environment_list_pagination_setting_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("环境列表分页设置 switch did not appear")

    def _wait_for_environment_list_sort(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._environment_list_sort_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("环境列表排序 switch did not appear")

    def _wait_for_packet_capture_blocking(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._packet_capture_blocking_exists_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("禁用抓包软件 switch did not appear")

    def _wait_checkbox_checked(
        self,
        label_text: str,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._checkbox_checked_script(label_text))
            if value is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"{label_text} checkbox state did not become expected: {expected}")

    def _wait_website_restriction_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._website_restriction_enabled_script())
            if value is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"访问网站限制 switch state did not become expected: {expected}")

    def _set_website_restriction_enabled(self, expected: bool) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        last_state = None
        while time.time() < deadline:
            current = self.cdp.evaluate(self._website_restriction_enabled_script())
            last_state = current
            if current is expected:
                return

            clicked = bool(self.cdp.evaluate(self._website_restriction_switch_dom_click_script()))
            time.sleep(0.4)
            if self.cdp.evaluate(self._website_restriction_enabled_script()) is expected:
                return

            if not clicked:
                point = self.cdp.evaluate(self._website_restriction_switch_center_script())
                if not isinstance(point, dict):
                    raise RuntimeError(f"访问网站限制 switch center was not found: {point}")
                x = float(point.get("x", 0))
                y = float(point.get("y", 0))
                if x <= 0 or y <= 0:
                    raise RuntimeError(f"访问网站限制 switch center is invalid: {point}")
                self.cdp.click_at(x, y)
                time.sleep(0.5)

        raise TimeoutError(
            f"访问网站限制 switch state did not become expected: expected={expected}, last={last_state}"
        )

    def _set_packet_capture_blocking_enabled(self, expected: bool) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        last_state = None
        while time.time() < deadline:
            current = self.cdp.evaluate(self._packet_capture_blocking_enabled_script())
            last_state = current
            if current is expected:
                return

            clicked = bool(self.cdp.evaluate(self._packet_capture_blocking_switch_dom_click_script()))
            time.sleep(0.4)
            if self.cdp.evaluate(self._packet_capture_blocking_enabled_script()) is expected:
                return

            if not clicked:
                point = self.cdp.evaluate(self._packet_capture_blocking_switch_center_script())
                if not isinstance(point, dict):
                    raise RuntimeError(f"禁用抓包软件 switch center was not found: {point}")
                x = float(point.get("x", 0))
                y = float(point.get("y", 0))
                if x <= 0 or y <= 0:
                    raise RuntimeError(f"禁用抓包软件 switch center is invalid: {point}")
                self.cdp.click_at(x, y)
                time.sleep(0.5)

        raise TimeoutError(
            f"禁用抓包软件 switch state did not become expected: expected={expected}, last={last_state}"
        )

    def _wait_bookmark_setting_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._bookmark_setting_enabled_script())
            if value is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"书签设置 switch state did not become expected: {expected}")

    def _set_bookmark_setting_enabled(self, expected: bool) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        last_state = None
        while time.time() < deadline:
            current = self.cdp.evaluate(self._bookmark_setting_enabled_script())
            last_state = current
            if current is expected:
                return

            clicked = bool(self.cdp.evaluate(self._bookmark_setting_switch_dom_click_script()))
            time.sleep(0.4)
            if self.cdp.evaluate(self._bookmark_setting_enabled_script()) is expected:
                return

            if not clicked:
                center = self.cdp.evaluate(self._bookmark_setting_switch_center_script())
                if isinstance(center, dict) and center.get("x") is not None and center.get("y") is not None:
                    self.cdp.click_at(float(center["x"]), float(center["y"]))
                    time.sleep(0.4)
                    if self.cdp.evaluate(self._bookmark_setting_enabled_script()) is expected:
                        return
            time.sleep(0.2)

        raise TimeoutError(f"书签设置 switch state did not become {expected}: last={last_state}")

    def _wait_environment_field_display_limit_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._environment_field_display_limit_enabled_script())
            if value is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"环境列表字段权限 switch state did not become expected: {expected}")

    def _set_environment_field_display_limit_enabled(self, expected: bool) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        last_state = None
        while time.time() < deadline:
            current = self.cdp.evaluate(self._environment_field_display_limit_enabled_script())
            last_state = current
            if current is expected:
                return

            clicked = bool(self.cdp.evaluate(self._environment_field_display_limit_switch_dom_click_script()))
            time.sleep(0.4)
            if self.cdp.evaluate(self._environment_field_display_limit_enabled_script()) is expected:
                return

            if not clicked:
                center = self.cdp.evaluate(self._environment_field_display_limit_switch_center_script())
                if isinstance(center, dict) and center.get("x") is not None and center.get("y") is not None:
                    self.cdp.click_at(float(center["x"]), float(center["y"]))
                    time.sleep(0.4)
                    if self.cdp.evaluate(self._environment_field_display_limit_enabled_script()) is expected:
                        return
            time.sleep(0.2)

        raise TimeoutError(f"环境列表字段权限 switch state did not become {expected}: last={last_state}")

    def _wait_environment_list_pagination_setting_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._environment_list_pagination_setting_enabled_script())
            if value is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"环境列表分页设置 switch state did not become expected: {expected}")

    def _set_environment_list_pagination_setting_enabled(self, expected: bool) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        last_state = None
        while time.time() < deadline:
            current = self.cdp.evaluate(self._environment_list_pagination_setting_enabled_script())
            last_state = current
            if current is expected:
                return

            clicked = bool(self.cdp.evaluate(self._environment_list_pagination_setting_switch_dom_click_script()))
            time.sleep(0.4)
            if self.cdp.evaluate(self._environment_list_pagination_setting_enabled_script()) is expected:
                return

            if not clicked:
                center = self.cdp.evaluate(self._environment_list_pagination_setting_switch_center_script())
                if isinstance(center, dict) and center.get("x") is not None and center.get("y") is not None:
                    self.cdp.click_at(float(center["x"]), float(center["y"]))
                    time.sleep(0.4)
                    if self.cdp.evaluate(self._environment_list_pagination_setting_enabled_script()) is expected:
                        return
            time.sleep(0.2)

        raise TimeoutError(f"环境列表分页设置 switch state did not become {expected}: last={last_state}")

    def _select_environment_list_pagination_page_size(self, page_size_text: str) -> None:
        normalized = str(page_size_text or "").replace(" ", "").strip()
        if self.cdp.evaluate(self._environment_list_pagination_page_size_selected_script(normalized)):
            return
        self.cdp.click_element_by_script(self._environment_list_pagination_page_size_select_script())
        self.cdp.click_element_by_script(self._visible_dropdown_item_by_normalized_text_script(normalized))
        self._wait_environment_list_pagination_page_size(normalized)

    def _wait_environment_list_pagination_page_size(
        self,
        page_size_text: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        normalized = str(page_size_text or "").replace(" ", "").strip()
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._environment_list_pagination_page_size_selected_script(normalized)):
                return
            time.sleep(0.2)
        actual = self.cdp.evaluate(self._environment_list_pagination_page_size_text_script())
        raise TimeoutError(f"环境列表分页条数未保存为预期值: expected={normalized}, actual={actual}")

    def _environment_list_pagination_page_size_value(self) -> str:
        text = str(self.cdp.evaluate(self._environment_list_pagination_page_size_text_script()) or "")
        match = re.search(r"(\d+\s*条\s*/\s*页)", text)
        if not match:
            return ""
        return match.group(1).replace(" ", "")

    def _wait_for_clear_local_cache_settings(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._global_settings_form_select_exists_script(self.CLEAR_LOCAL_CACHE_METHOD_LABEL)):
                return
            time.sleep(0.2)
        raise TimeoutError("全局设置清除本地缓存清除方式 select did not appear")

    def _select_global_settings_form_select_option(self, label_text: str, option_text: str) -> None:
        if option_text in self._global_settings_form_select_value(label_text):
            return

        last_error: TimeoutError | None = None
        for _ in range(3):
            self.cdp.click_element_by_script(self._global_settings_form_select_script(label_text))
            time.sleep(0.3)
            try:
                self.cdp.click_element_by_script(self._select_dropdown_option_script(option_text), timeout=3000)
                self._close_select_dropdowns()
                self._wait_global_settings_form_select_value(label_text, option_text)
                return
            except TimeoutError as exc:
                last_error = exc
                self.cdp.press("Escape")
                time.sleep(0.2)
        raise TimeoutError(
            f"global settings select option was not selected: label={label_text}, option={option_text}"
        ) from last_error

    def _global_settings_form_select_value(self, label_text: str) -> str:
        return str(self.cdp.evaluate(self._global_settings_form_select_value_script(label_text)) or "").strip()

    def _wait_global_settings_form_select_value(
        self,
        label_text: str,
        expected_value: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        last_value = ""
        while time.time() < deadline:
            last_value = self._global_settings_form_select_value(label_text)
            if expected_value in last_value:
                return
            time.sleep(0.2)
        raise TimeoutError(
            "global settings select value did not become expected: "
            f"label={label_text}, expected={expected_value}, actual={last_value}"
        )

    def _set_clear_local_cache_sync_cloud_enabled(self, expected: bool) -> None:
        current = self.cdp.evaluate(self._clear_local_cache_sync_cloud_enabled_script())
        if current is None:
            raise RuntimeError("清除后，再同步云端数据 switch was not found")
        if bool(current) is expected:
            return
        self.cdp.click_element_by_script(self._clear_local_cache_sync_cloud_switch_script())
        self._wait_clear_local_cache_sync_cloud_enabled(expected)

    def _wait_clear_local_cache_sync_cloud_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._clear_local_cache_sync_cloud_enabled_script()) is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"清除后，再同步云端数据 switch state did not become expected: {expected}")

    def _wait_environment_list_sort_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._environment_list_sort_enabled_script())
            if value is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"环境列表排序 switch state did not become expected: {expected}")

    def _set_environment_list_sort_enabled(self, expected: bool) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        last_state = None
        while time.time() < deadline:
            current = self.cdp.evaluate(self._environment_list_sort_enabled_script())
            last_state = current
            if current is expected:
                return

            clicked = bool(self.cdp.evaluate(self._environment_list_sort_switch_dom_click_script()))
            time.sleep(0.4)
            if self.cdp.evaluate(self._environment_list_sort_enabled_script()) is expected:
                return

            if not clicked:
                center = self.cdp.evaluate(self._environment_list_sort_switch_center_script())
                if isinstance(center, dict) and center.get("x") is not None and center.get("y") is not None:
                    self.cdp.click_at(float(center["x"]), float(center["y"]))
                    time.sleep(0.4)
                    if self.cdp.evaluate(self._environment_list_sort_enabled_script()) is expected:
                        return
            time.sleep(0.2)

        raise TimeoutError(f"环境列表排序 switch state did not become {expected}: last={last_state}")

    def _select_environment_list_sort_option(self, label_text: str, option_text: str) -> None:
        if self.cdp.evaluate(self._environment_list_sort_option_selected_script(label_text, option_text)):
            return

        if self.cdp.evaluate(self._environment_list_sort_radio_exists_script(label_text, option_text)):
            self.cdp.click_element_by_script(self._environment_list_sort_radio_script(label_text, option_text))
        else:
            self.cdp.click_element_by_script(self._environment_list_sort_select_script(label_text))
            self.cdp.click_element_by_script(self._environment_list_sort_dropdown_item_script(option_text))
        self._wait_environment_list_sort_option(label_text, option_text)

    def _wait_environment_list_sort_option(
        self,
        label_text: str,
        option_text: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._environment_list_sort_option_selected_script(label_text, option_text)):
                return
            time.sleep(0.2)
        actual = self.cdp.evaluate(self._environment_list_sort_option_text_script(label_text))
        raise TimeoutError(f"环境列表排序选项未保存为预期值: label={label_text}, expected={option_text}, actual={actual}")

    def _environment_list_sort_option_value(self, label_text: str) -> str:
        text = str(self.cdp.evaluate(self._environment_list_sort_option_text_script(label_text)) or "")
        if label_text == "排序方式":
            if "升序" in text:
                return "升序"
            if "降序" in text:
                return "降序"
            return ""
        for candidate in self._ENVIRONMENT_FIELD_ALIASES:
            if candidate in {"升序", "降序"}:
                continue
            if self._canonical_environment_field(text) == candidate or candidate in text:
                return candidate
        return self._canonical_environment_field(text)

    def _open_environment_field_display_limit_dialog(self) -> None:
        self.cdp.click_element_by_script(self._environment_field_display_limit_edit_button_script())
        self._wait_environment_field_display_limit_dialog_visible()

    def _select_environment_field_display_limit_fields(self, field_names: list[str]) -> None:
        self.cdp.click_element_by_script(self._environment_field_display_limit_dialog_checkbox_script("全选"))
        self._wait_environment_field_display_limit_all_checkbox_checked(True)
        self.cdp.click_element_by_script(self._environment_field_display_limit_dialog_checkbox_script("全选"))
        self._wait_environment_field_display_limit_all_checkbox_checked(False)

        for field_name in field_names:
            self.cdp.click_element_by_script(self._environment_field_display_limit_dialog_checkbox_script(field_name))
            self._wait_environment_field_display_limit_dialog_checkbox_checked(field_name, True)

        self.cdp.click_element_by_script(self._active_dialog_button_script("确定"))
        self._wait_for_overlay_closed()
        self._wait_environment_field_display_limit_current_setting(field_names)

    def _wait_environment_field_display_limit_dialog_visible(self) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._environment_field_display_limit_dialog_visible_script()):
                return
            time.sleep(0.2)
        raise TimeoutError("环境列表字段权限字段设置弹窗未出现")

    def _wait_environment_field_display_limit_dialog_checkbox_checked(
        self,
        text: str,
        expected: bool,
    ) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            value = self.cdp.evaluate(self._environment_field_display_limit_dialog_checkbox_checked_script(text))
            if value is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"环境列表字段权限弹窗字段勾选状态未达到预期: field={text}, expected={expected}")

    def _wait_environment_field_display_limit_all_checkbox_checked(self, expected: bool) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            states = self.cdp.evaluate(self._environment_field_display_limit_dialog_checkbox_states_script())
            if not isinstance(states, dict):
                time.sleep(0.2)
                continue
            selectable_states = {
                str(key): bool(value)
                for key, value in states.items()
                if str(key) != "全选"
            }
            if selectable_states and all(value is expected for value in selectable_states.values()):
                return
            time.sleep(0.2)
        raise TimeoutError(f"环境列表字段权限弹窗全选状态未达到预期: expected={expected}")

    def _wait_environment_field_display_limit_current_setting(
        self,
        field_names: list[str],
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        expected = [self._canonical_environment_field(item) for item in field_names if str(item).strip()]
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            text = str(self.cdp.evaluate(self._environment_field_display_limit_text_script()) or "")
            actual = [self._canonical_environment_field(item) for item in text.split(">") if str(item).strip()]
            if actual == expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"环境列表字段权限当前设置未回显预期字段: expected={expected}")

    def _environment_field_display_limit_current_fields(self) -> list[str]:
        text = str(self.cdp.evaluate(self._environment_field_display_limit_text_script()) or "")
        fields: list[str] = []
        for candidate in re.split(r"[>、,，\\s]+", text):
            field = self._canonical_environment_field(candidate)
            if field in self._ENVIRONMENT_FIELD_ALIASES and field not in {"升序", "降序"} and field not in fields:
                fields.append(field)
        return fields

    def _upload_bookmark_file(self, file_path: Path) -> None:
        file_content = file_path.read_text(encoding="utf-8", errors="ignore")
        self.cdp.evaluate_with_args(
            """
            ([fileName, filePath, fileContent]) => {
                const ipc = window.ipcRenderer;
                if (!ipc || typeof ipc.invoke !== "function") {
                    throw new Error("ipcRenderer.invoke is not available for bookmark file upload");
                }
                if (window.__dicloakRestoreBookmarkUploadIpc) {
                    try {
                        window.__dicloakRestoreBookmarkUploadIpc();
                    } catch (_) {}
                }
                const originalInvoke = ipc.invoke;
                window.__dicloakRestoreBookmarkUploadIpc = () => {
                    try {
                        ipc.invoke = originalInvoke;
                    } finally {
                        delete window.__dicloakRestoreBookmarkUploadIpc;
                    }
                };
                ipc.invoke = function(channel, ...args) {
                    if (channel === "open-file-dialog") {
                        return Promise.resolve([filePath]);
                    }
                    if (channel === "read-file" && args[0] === filePath) {
                        return Promise.resolve(fileContent);
                    }
                    return originalInvoke.call(this, channel, ...args);
                };
            }
            """,
            [file_path.name, str(file_path), file_content],
        )
        try:
            self.cdp.click_element_by_script(self._bookmark_upload_button_script())
            self._wait_bookmark_file_uploaded(file_path.name)
        finally:
            self.cdp.evaluate(
                """
                () => {
                    if (window.__dicloakRestoreBookmarkUploadIpc) {
                        window.__dicloakRestoreBookmarkUploadIpc();
                    }
                }
                """
            )

    def _wait_bookmark_file_uploaded(self, file_name: str) -> None:
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            text = str(self.cdp.evaluate(self._bookmark_setting_text_script()) or "")
            if file_name in text:
                return
            time.sleep(0.3)
        raise TimeoutError(f"bookmark file was not shown after upload: {file_name}")

    def _select_bookmark_effect_mode(self, mode_text: str) -> None:
        self.cdp.click_element_by_script(self._bookmark_effect_mode_script(mode_text))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._bookmark_effect_mode_checked_script(mode_text)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"bookmark effect mode was not selected: {mode_text}")

    def _select_bookmark_overwrite_rule(self, rule_text: str) -> None:
        self.cdp.click_element_by_script(self._bookmark_overwrite_rule_select_script())
        self.cdp.click_element_by_script(self._visible_dropdown_item_script(rule_text))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if rule_text in str(self.cdp.evaluate(self._bookmark_setting_text_script()) or ""):
                return
            time.sleep(0.2)
        raise TimeoutError(f"bookmark overwrite rule was not selected: {rule_text}")

    def _wait_packet_capture_blocking_enabled(
        self,
        expected: bool,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._packet_capture_blocking_enabled_script())
            if value is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"禁用抓包软件 switch state did not become expected: {expected}")

    def _wait_packet_capture_process_name(
        self,
        process_name: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._packet_capture_process_value_script())
            if str(value or "").strip() == process_name:
                return
            time.sleep(0.2)
        raise TimeoutError(f"禁用抓包软件进程名未保存为预期值: expected={process_name}")

    def _wait_website_restriction_urls(
        self,
        urls: list[str],
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        expected = "\n".join(urls)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            value = self.cdp.evaluate(self._website_restriction_url_value_script())
            if value == expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"访问网站限制网址列表未保存为预期值: expected={expected}")

    def _wait_website_restriction_mode(
        self,
        mode_text: str,
        timeout_seconds: int | None = None,
    ) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._website_restriction_radio_checked_script(mode_text)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"访问网站限制方式未保存为预期值: {mode_text}")

    def _select_website_restriction_mode(self, mode_text: str) -> None:
        if self.cdp.evaluate(self._website_restriction_radio_checked_script(mode_text)):
            return
        self.cdp.click_element_by_script(self._website_restriction_radio_script(mode_text))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._website_restriction_radio_checked_script(mode_text)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"访问网站限制方式未切换到: {mode_text}")

    def _ensure_website_restriction_shortcut_checked(self, shortcut_name: str) -> None:
        shortcut_names = self._website_shortcut_candidates(shortcut_name)
        if self.cdp.evaluate(self._website_restriction_shortcut_checked_script(shortcut_names)):
            return
        self.cdp.click_element_by_script(self._website_restriction_shortcut_script(shortcut_names))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._website_restriction_shortcut_checked_script(shortcut_names)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"访问网站限制快捷选择未勾选: {shortcut_name}")

    def _set_website_restriction_shortcut_checked(self, shortcut_name: str, expected: bool) -> None:
        shortcut_names = self._website_shortcut_candidates(shortcut_name)
        current = self.cdp.evaluate(self._website_restriction_shortcut_checked_script(shortcut_names))
        if current is expected:
            return
        self.cdp.click_element_by_script(self._website_restriction_shortcut_script(shortcut_names))
        deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
        while time.time() < deadline:
            if self.cdp.evaluate(self._website_restriction_shortcut_checked_script(shortcut_names)) is expected:
                return
            time.sleep(0.2)
        raise TimeoutError(f"访问网站限制快捷选择状态未恢复: shortcut={shortcut_name}, expected={expected}")

    def _website_restriction_selected_mode(self) -> str:
        for mode_text in ("禁止访问指定网址", "允许访问指定网址"):
            if self.cdp.evaluate(self._website_restriction_radio_checked_script(mode_text)):
                return mode_text
        return ""

    def _website_restriction_url_lines(self) -> list[str]:
        value = self.cdp.evaluate(self._website_restriction_url_value_script())
        return self._unique_non_empty(str(value or "").splitlines())

    def _website_restriction_shortcut_states(self) -> dict[str, bool]:
        value = self.cdp.evaluate(self._website_restriction_shortcut_states_script())
        if not isinstance(value, dict):
            return {}
        return {str(key): bool(item) for key, item in value.items()}

    def _website_shortcut_candidates(self, shortcut_name: str) -> tuple[str, ...]:
        clean_name = str(shortcut_name or "").strip()
        if clean_name in self.GOOGLE_EXTENSION_SHORTCUT_LABELS:
            return self.GOOGLE_EXTENSION_SHORTCUT_LABELS
        return (clean_name,)

    def _wait_checkbox_states_stable(self, timeout_seconds: int | None = None) -> dict[str, bool]:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        stable_since = 0.0
        previous: dict[str, bool] = {}
        last: dict[str, bool] = {}
        while time.time() < deadline:
            self._wait_until_not_loading()
            current = self.checkbox_states()
            if current and current == previous:
                if stable_since == 0:
                    stable_since = time.time()
                if time.time() - stable_since >= 1.5:
                    return current
            else:
                stable_since = 0.0
                previous = current
            last = current
            time.sleep(0.3)
        raise TimeoutError(f"global settings checkbox states did not become stable: {last}")

    def _assert_only_checkbox_changed(
        self,
        label_text: str,
        before_states: dict[str, bool],
        after_states: dict[str, bool],
        expected_change: tuple[bool, bool] = (False, True),
    ) -> None:
        changed = {
            name: (before_states.get(name), after_states.get(name))
            for name in sorted(set(before_states) & set(after_states))
            if before_states.get(name) != after_states.get(name)
        }
        allowed = {label_text: expected_change}
        unexpected = {
            name: value
            for name, value in changed.items()
            if name not in allowed or value != allowed[name]
        }
        if unexpected:
            raise AssertionError(f"unexpected global settings checkbox changes before save: {unexpected}")

    def _wait_save_finished(self, timeout_seconds: int | None = None) -> bool:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        with self.phase_timing("global_settings.wait_save_finished", timeout_seconds=timeout_seconds):
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                if not self._has_visible_loading():
                    return self._wait_save_success_message(timeout_seconds=self.SAVE_SUCCESS_MESSAGE_SECONDS)
                time.sleep(0.2)
            raise TimeoutError("global settings save did not finish")

    def _wait_save_success_message(self, timeout_seconds: int) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                if self.cdp.evaluate(self._save_success_message_visible_script()):
                    return True
            except Exception:
                pass
            time.sleep(0.2)
        return False

    def _wait_until_not_loading(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self._has_visible_loading():
                return
            time.sleep(0.2)
        raise TimeoutError("global settings page still has visible loading mask")

    def _wait_for_global_settings_rendered(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        stable_since = 0.0
        last_state: dict[str, bool | int] = {}
        while time.time() < deadline:
            state = self._global_settings_render_state()
            last_state = state
            ready = (
                not bool(state.get("loading_text_visible"))
                and int(state.get("visible_loading_count") or 0) == 0
                and bool(state.get("data_sync_present"))
            )
            if ready:
                if stable_since == 0:
                    stable_since = time.time()
                if time.time() - stable_since >= 1.0:
                    return
            else:
                stable_since = 0.0
            time.sleep(0.1)
        raise TimeoutError(f"global settings page did not finish rendering: {last_state}")

    def _global_settings_render_state(self) -> dict[str, bool | int]:
        value = self.cdp.evaluate(
            """
            () => {
                const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                };
                const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const loadingTextVisible = Array.from(document.querySelectorAll("body *"))
                    .filter(visible)
                    .some((el) => {
                        const text = clean(el.innerText || el.textContent);
                        return text === "正在加载中..."
                            || text === "正在加载中…"
                            || text === "正在加载中";
                    });
                const visibleLoadingCount = Array.from(document.querySelectorAll(__LOADING_SELECTOR__))
                    .filter(visible).length;
                return {
                    loading_text_visible: loadingTextVisible,
                    visible_loading_count: visibleLoadingCount,
                    data_sync_present: Boolean(document.querySelector(__DATA_SYNC_SELECTOR__)),
                };
            }
            """.replace("__LOADING_SELECTOR__", repr(self.locator("loading_mask"))).replace(
                "__DATA_SYNC_SELECTOR__",
                repr(self.locator("data_sync_root")),
            )
        )
        if not isinstance(value, dict):
            return {
                "loading_text_visible": True,
                "visible_loading_count": 0,
                "data_sync_present": False,
            }
        return {
            "loading_text_visible": bool(value.get("loading_text_visible")),
            "visible_loading_count": int(value.get("visible_loading_count") or 0),
            "data_sync_present": bool(value.get("data_sync_present")),
        }

    def _has_visible_loading(self) -> bool:
        return bool(
            self.cdp.evaluate(
                """
                () => {
                    const selector = __LOADING_SELECTOR__;
                    const visible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== "none"
                            && style.visibility !== "hidden"
                            && rect.width > 0
                            && rect.height > 0;
                    };
                    return Array.from(document.querySelectorAll(selector))
                        .some(visible);
                }
                """.replace("__LOADING_SELECTOR__", repr(self.locator("loading_mask")))
            )
        )

    def _save_success_message_visible_script(self) -> str:
        return f"""
        () => {{
            const expectedText = {self.SAVE_SUCCESS_MESSAGE!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity || "1") > 0.01
                    && rect.width > 0
                    && rect.height > 0
                    && rect.right > 0
                    && rect.bottom > 0
                    && rect.left < window.innerWidth
                    && rect.top < window.innerHeight;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const messageSelectors = [
                ".el-message--success .el-message__content",
                ".el-message--success",
                ".el-message__content",
                ".el-message",
                "[role='alert']",
            ];
            return messageSelectors
                .flatMap((selector) => Array.from(document.querySelectorAll(selector)))
                .filter(visible)
                .some((el) => clean(el.innerText || el.textContent).includes(expectedText));
        }}
        """

    def _dismiss_blocking_overlays(self) -> None:
        for _ in range(4):
            has_overlay = bool(
                self.cdp.evaluate(
                    """
                    () => Boolean(document.querySelector(__OVERLAY_SELECTOR__))
                    """.replace("__OVERLAY_SELECTOR__", repr(self.locator("blocking_overlay")))
                )
            )
            if not has_overlay:
                return
            clicked = bool(
                self.cdp.evaluate(
                    """
                    () => {
                        const closeButtonSelector = __CLOSE_BUTTON_SELECTOR__;
                        const visible = (el) => {
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== "none"
                                && style.visibility !== "hidden"
                                && rect.width > 0
                                && rect.height > 0;
                        };
                        const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                        const overlays = Array.from(document.querySelectorAll(".el-drawer, .el-dialog, .el-message-box"))
                            .filter(visible);
                        for (const overlay of overlays.reverse()) {
                            const cancel = Array.from(overlay.querySelectorAll("button"))
                                .filter(visible)
                                .find((button) => clean(button.innerText || button.textContent) === "取消");
                            if (cancel) {
                                cancel.click();
                                return true;
                            }
                        }
                        const button = Array.from(document.querySelectorAll(closeButtonSelector)).find(visible);
                        if (button) {
                            button.click();
                            return true;
                        }
                        return false;
                    }
                    """.replace("__CLOSE_BUTTON_SELECTOR__", repr(self.locator("overlay_close_button")))
                )
            )
            if not clicked:
                self.cdp.press("Escape")
            time.sleep(0.3)

    def _close_select_dropdowns(self) -> None:
        for _ in range(3):
            open_dropdown = bool(
                self.cdp.evaluate(
                    """
                    () => {
                        const visible = (el) => {
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== "none"
                                && style.visibility !== "hidden"
                                && rect.width > 0
                                && rect.height > 0;
                        };
                        return Array.from(document.querySelectorAll(".el-select__popper, .el-popper"))
                            .some(visible);
                    }
                    """
                )
            )
            if not open_dropdown:
                return
            self.cdp.press("Escape")
            time.sleep(0.2)

    def _dropdown_option_visible(self, text: str) -> bool:
        return bool(self.cdp.evaluate(self._dropdown_option_visible_script(text)))

    def _data_sync_state_key(self, item_text: str) -> str:
        normalized = str(item_text or "").strip().lower().replace(" ", "_")
        if normalized == "cookie":
            return "cookie"
        if normalized == "local_storage":
            return "local_storage"
        if normalized == "indexeddb":
            return "indexeddb"
        raise ValueError(f"unsupported global data sync item: {item_text}")

    @staticmethod
    def _unique_non_empty(values) -> list[str]:
        result: list[str] = []
        for value in values or []:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    def _checkbox_exists_script(self, label_text: str) -> str:
        return """
        () => Boolean((() => {
            const text = __TEXT__;
            const selector = __CHECKBOX_SELECTOR__;
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(selector))
                .filter(visible)
                .find((el) => (el.innerText || el.textContent || "").includes(text));
        })())
        """.replace("__TEXT__", repr(label_text)).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox_candidates")),
        )

    def _checkbox_script(self, label_text: str) -> str:
        return """
        () => {
            const text = __TEXT__;
            const selector = __CHECKBOX_SELECTOR__;
            const checkboxStateSelector = __CHECKBOX_STATE_SELECTOR__;
            const checkboxInputSelector = __CHECKBOX_INPUT_SELECTOR__;
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const candidates = Array.from(document.querySelectorAll(selector))
                .filter(visible)
                .filter((el) => (el.innerText || el.textContent || "").includes(text));
            const checkbox = candidates.find((el) => el.matches(__CHECKBOX_SELECTOR_ONLY__)) || candidates[0] || null;
            if (!checkbox) return null;
            return checkbox.querySelector(`${checkboxStateSelector}, ${checkboxInputSelector}`) || checkbox;
        }
        """.replace("__TEXT__", repr(label_text)).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox_candidates")),
        ).replace(
            "__CHECKBOX_SELECTOR_ONLY__",
            repr(self.locator("checkbox")),
        ).replace(
            "__CHECKBOX_STATE_SELECTOR__",
            repr(self.locator("checkbox_state")),
        ).replace(
            "__CHECKBOX_INPUT_SELECTOR__",
            repr(self.locator("checkbox_input")),
        )

    def _checkbox_checked_script(self, label_text: str) -> str:
        return """
        () => {
            const text = __TEXT__;
            const selector = __CHECKBOX_SELECTOR__;
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const candidates = Array.from(document.querySelectorAll(selector))
                .filter(visible)
                .filter((el) => (el.innerText || el.textContent || "").includes(text));
            const checkbox = candidates.find((el) => el.matches(__CHECKBOX_SELECTOR_ONLY__)) || candidates[0] || null;
            if (!checkbox) return null;
            const input = checkbox.querySelector(__CHECKBOX_INPUT_SELECTOR__);
            if (input) return Boolean(input.checked);
            const stateEl = checkbox.querySelector(__CHECKBOX_STATE_SELECTOR__) || checkbox;
            const ariaChecked = stateEl.getAttribute("aria-checked");
            if (ariaChecked === "true") return true;
            if (ariaChecked === "false") return false;
            return stateEl.classList.contains("is-checked") || checkbox.classList.contains("is-checked");
        }
        """.replace("__TEXT__", repr(label_text)).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox_candidates")),
        ).replace(
            "__CHECKBOX_SELECTOR_ONLY__",
            repr(self.locator("checkbox")),
        ).replace(
            "__CHECKBOX_INPUT_SELECTOR__",
            repr(self.locator("checkbox_input")),
        ).replace(
            "__CHECKBOX_STATE_SELECTOR__",
            repr(self.locator("checkbox_state")),
        )

    def _cookie_data_sync_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const root = document.querySelector(__ROOT_SELECTOR__);
            if (!root) return null;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .find((checkbox) => clean(checkbox.innerText || checkbox.textContent) === "Cookie") || null;
        })())
        """.replace("__ROOT_SELECTOR__", repr(self.locator("data_sync_root"))).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        )

    def _cookie_data_sync_checkbox_script(self) -> str:
        return """
        () => {
            const root = document.querySelector(__ROOT_SELECTOR__);
            if (!root) return null;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const checkbox = Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .find((item) => clean(item.innerText || item.textContent) === "Cookie") || null;
            if (!checkbox) return null;
            return checkbox.querySelector(__CHECKBOX_STATE_SELECTOR__) || checkbox;
        }
        """.replace("__ROOT_SELECTOR__", repr(self.locator("data_sync_root"))).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__CHECKBOX_STATE_SELECTOR__",
            repr(self.locator("checkbox_state")),
        )

    def _cookie_data_sync_enabled_script(self) -> str:
        return """
        () => {
            const root = document.querySelector(__ROOT_SELECTOR__);
            if (!root) return null;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const checkbox = Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .find((item) => clean(item.innerText || item.textContent) === "Cookie") || null;
            if (!checkbox) return null;
            const input = checkbox.querySelector(__CHECKBOX_INPUT_SELECTOR__);
            if (input) return Boolean(input.checked);
            const state = checkbox.querySelector(__CHECKBOX_STATE_SELECTOR__) || checkbox;
            return state.classList.contains("is-checked") || checkbox.classList.contains("is-checked");
        }
        """.replace("__ROOT_SELECTOR__", repr(self.locator("data_sync_root"))).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__CHECKBOX_INPUT_SELECTOR__",
            repr(self.locator("checkbox_input")),
        ).replace(
            "__CHECKBOX_STATE_SELECTOR__",
            repr(self.locator("checkbox_state")),
        )

    def _local_storage_data_sync_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const root = document.querySelector(__ROOT_SELECTOR__);
            if (!root) return null;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .find((checkbox) => clean(checkbox.innerText || checkbox.textContent) === "Local Storage") || null;
        })())
        """.replace("__ROOT_SELECTOR__", repr(self.locator("data_sync_root"))).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        )

    def _local_storage_data_sync_checkbox_script(self) -> str:
        return """
        () => {
            const root = document.querySelector(__ROOT_SELECTOR__);
            if (!root) return null;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const checkbox = Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .find((item) => clean(item.innerText || item.textContent) === "Local Storage") || null;
            if (!checkbox) return null;
            return checkbox.querySelector(__CHECKBOX_STATE_SELECTOR__) || checkbox;
        }
        """.replace("__ROOT_SELECTOR__", repr(self.locator("data_sync_root"))).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__CHECKBOX_STATE_SELECTOR__",
            repr(self.locator("checkbox_state")),
        )

    def _local_storage_data_sync_enabled_script(self) -> str:
        return """
        () => {
            const root = document.querySelector(__ROOT_SELECTOR__);
            if (!root) return null;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const checkbox = Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .find((item) => clean(item.innerText || item.textContent) === "Local Storage") || null;
            if (!checkbox) return null;
            const input = checkbox.querySelector(__CHECKBOX_INPUT_SELECTOR__);
            if (input) return Boolean(input.checked);
            const state = checkbox.querySelector(__CHECKBOX_STATE_SELECTOR__) || checkbox;
            return state.classList.contains("is-checked") || checkbox.classList.contains("is-checked");
        }
        """.replace("__ROOT_SELECTOR__", repr(self.locator("data_sync_root"))).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__CHECKBOX_INPUT_SELECTOR__",
            repr(self.locator("checkbox_input")),
        ).replace(
            "__CHECKBOX_STATE_SELECTOR__",
            repr(self.locator("checkbox_state")),
        )

    def _indexeddb_data_sync_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const root = document.querySelector(__ROOT_SELECTOR__);
            if (!root) return null;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            return Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .find((checkbox) => clean(checkbox.innerText || checkbox.textContent) === "IndexedDB") || null;
        })())
        """.replace("__ROOT_SELECTOR__", repr(self.locator("data_sync_root"))).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        )

    def _indexeddb_data_sync_checkbox_script(self) -> str:
        return """
        () => {
            const root = document.querySelector(__ROOT_SELECTOR__);
            if (!root) return null;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const checkbox = Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .find((item) => clean(item.innerText || item.textContent) === "IndexedDB") || null;
            if (!checkbox) return null;
            return checkbox.querySelector(__CHECKBOX_STATE_SELECTOR__) || checkbox;
        }
        """.replace("__ROOT_SELECTOR__", repr(self.locator("data_sync_root"))).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__CHECKBOX_STATE_SELECTOR__",
            repr(self.locator("checkbox_state")),
        )

    def _indexeddb_data_sync_enabled_script(self) -> str:
        return """
        () => {
            const root = document.querySelector(__ROOT_SELECTOR__);
            if (!root) return null;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const checkbox = Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .find((item) => clean(item.innerText || item.textContent) === "IndexedDB") || null;
            if (!checkbox) return null;
            const input = checkbox.querySelector(__CHECKBOX_INPUT_SELECTOR__);
            if (input) return Boolean(input.checked);
            const state = checkbox.querySelector(__CHECKBOX_STATE_SELECTOR__) || checkbox;
            return state.classList.contains("is-checked") || checkbox.classList.contains("is-checked");
        }
        """.replace("__ROOT_SELECTOR__", repr(self.locator("data_sync_root"))).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__CHECKBOX_INPUT_SELECTOR__",
            repr(self.locator("checkbox_input")),
        ).replace(
            "__CHECKBOX_STATE_SELECTOR__",
            repr(self.locator("checkbox_state")),
        )

    def _data_sync_checkbox_script(self, item_text: str) -> str:
        return """
        () => {
            const root = document.querySelector(__ROOT_SELECTOR__);
            if (!root) return null;
            const expectedText = __ITEM_TEXT__;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const checkbox = Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .filter(visible)
                .find((item) => clean(item.innerText || item.textContent) === expectedText) || null;
            if (!checkbox) return null;
            const clickTarget = checkbox.querySelector(__CHECKBOX_STATE_SELECTOR__) || checkbox;
            clickTarget.scrollIntoView({ block: "center", inline: "center" });
            return clickTarget;
        }
        """.replace("__ROOT_SELECTOR__", repr(self.locator("data_sync_root"))).replace(
            "__ITEM_TEXT__",
            repr(item_text),
        ).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__CHECKBOX_STATE_SELECTOR__",
            repr(self.locator("checkbox_state")),
        )

    def _data_sync_enabled_script(self, item_text: str) -> str:
        return """
        () => {
            const root = document.querySelector(__ROOT_SELECTOR__);
            if (!root) return null;
            const expectedText = __ITEM_TEXT__;
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const checkbox = Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .filter(visible)
                .find((item) => clean(item.innerText || item.textContent) === expectedText) || null;
            if (!checkbox) return null;
            const input = checkbox.querySelector(__CHECKBOX_INPUT_SELECTOR__);
            if (input) return Boolean(input.checked);
            const state = checkbox.querySelector(__CHECKBOX_STATE_SELECTOR__) || checkbox;
            return state.classList.contains("is-checked") || checkbox.classList.contains("is-checked");
        }
        """.replace("__ROOT_SELECTOR__", repr(self.locator("data_sync_root"))).replace(
            "__ITEM_TEXT__",
            repr(item_text),
        ).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__CHECKBOX_INPUT_SELECTOR__",
            repr(self.locator("checkbox_input")),
        ).replace(
            "__CHECKBOX_STATE_SELECTOR__",
            repr(self.locator("checkbox_state")),
        )

    def _data_sync_one_way_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const finder = __ONE_WAY_SWITCH_SCRIPT__;
            return finder();
        })())
        """.replace("__ONE_WAY_SWITCH_SCRIPT__", self._data_sync_one_way_switch_script())

    def _data_sync_one_way_switch_script(self) -> str:
        return f"""
        () => {{
            const root = document.querySelector({self.locator("data_sync_root")!r});
            if (!root) return null;
            const expectedText = {self.DATA_SYNC_ONE_WAY_SYNC_TEXT!r};
            const visible = (el) => {{
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(root.querySelectorAll(".el-form-item, label, div, span"))
                .filter(visible)
                .filter((el) => clean(el.innerText || el.textContent).includes(expectedText))
                .map((el) => {{
                    const item = el.closest(".el-form-item") || el;
                    const rect = item.getBoundingClientRect();
                    return {{ item, area: rect.width * rect.height }};
                }})
                .filter((candidate) => candidate.item.querySelector({self.locator("switch")!r}))
                .sort((left, right) => left.area - right.area);
            for (const candidate of candidates) {{
                const switchEl = candidate.item.querySelector({self.locator("switch")!r});
                if (!switchEl || !visible(switchEl)) continue;
                const clickTarget = switchEl.querySelector({self.locator("switch_core")!r}) || switchEl;
                clickTarget.scrollIntoView({{ block: "center", inline: "center" }});
                return clickTarget;
            }}
            return null;
        }}
        """

    def _data_sync_one_way_enabled_script(self) -> str:
        return """
        () => {
            const finder = __ONE_WAY_SWITCH_SCRIPT__;
            const target = finder();
            if (!target) return null;
            const switchEl = target.classList.contains("el-switch") ? target : target.closest(".el-switch");
            if (!switchEl) return null;
            const input = switchEl.querySelector("input");
            const ariaChecked = switchEl.getAttribute("aria-checked") || input?.getAttribute("aria-checked") || "";
            if (ariaChecked === "true") return true;
            if (ariaChecked === "false") return false;
            return switchEl.classList.contains("is-checked") || Boolean(input?.checked);
        }
        """.replace("__ONE_WAY_SWITCH_SCRIPT__", self._data_sync_one_way_switch_script())

    def _data_sync_one_way_whitelist_form_item_script(self) -> str:
        return f"""
        () => {{
            const root = document.querySelector({self.locator("data_sync_root")!r});
            if (!root) return null;
            const expectedLabel = {self.DATA_SYNC_ONE_WAY_SYNC_WHITELIST_LABEL!r};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const visible = (el) => {{
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0
                    && rect.left < window.innerWidth
                    && rect.right > 0;
            }};
            const labels = Array.from(root.querySelectorAll("label, .el-form-item__label")).filter(visible);
            for (const label of labels) {{
                if (clean(label.innerText || label.textContent) !== expectedLabel) continue;
                const item = label.closest(".el-form-item");
                if (item && visible(item)) return item;
            }}
            return null;
        }}
        """

    def _data_sync_one_way_whitelist_visible_script(self) -> str:
        return """
        () => {
            const finder = __WHITELIST_FORM_ITEM_SCRIPT__;
            return Boolean(finder());
        }
        """.replace("__WHITELIST_FORM_ITEM_SCRIPT__", self._data_sync_one_way_whitelist_form_item_script())

    def _data_sync_one_way_whitelist_select_script(self) -> str:
        return """
        () => {
            const finder = __WHITELIST_FORM_ITEM_SCRIPT__;
            const item = finder();
            if (!item) return null;
            const select = item.querySelector(__SELECT_CONTROL_SELECTOR__);
            if (!select) return null;
            select.scrollIntoView({ block: "center", inline: "center" });
            return select;
        }
        """.replace("__WHITELIST_FORM_ITEM_SCRIPT__", self._data_sync_one_way_whitelist_form_item_script()).replace(
            "__SELECT_CONTROL_SELECTOR__",
            repr(self.locator("select_control")),
        )

    def _data_sync_one_way_whitelist_values_script(self) -> str:
        return """
        () => {
            const finder = __WHITELIST_FORM_ITEM_SCRIPT__;
            const item = finder();
            if (!item) return [];
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const values = [];
            for (const selector of [
                ".el-tag__content",
                ".el-select__tags-text",
                ".el-select__selected-item",
                ".el-select__selection span",
                ".el-select__wrapper",
            ]) {
                for (const el of Array.from(item.querySelectorAll(selector)).filter(visible)) {
                    const text = clean(el.innerText || el.textContent);
                    if (text && text !== "×" && text !== "请选择" && !values.includes(text)) values.push(text);
                }
            }
            return values;
        }
        """.replace("__WHITELIST_FORM_ITEM_SCRIPT__", self._data_sync_one_way_whitelist_form_item_script())

    def _click_first_data_sync_one_way_whitelist_close_script(self) -> str:
        return """
        () => {
            const finder = __WHITELIST_FORM_ITEM_SCRIPT__;
            const item = finder();
            if (!item) return false;
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const fireClick = (el) => {
                for (const type of ["pointerdown", "mousedown", "mouseup", "click"]) {
                    el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
                }
            };
            const close = Array.from(item.querySelectorAll(".el-tag .el-tag__close, .el-tag .el-icon-close"))
                .find((el) => visible(el) && !el.closest(".el-select-dropdown__item"));
            if (!close) return false;
            fireClick(close);
            return true;
        }
        """.replace("__WHITELIST_FORM_ITEM_SCRIPT__", self._data_sync_one_way_whitelist_form_item_script())

    def _dropdown_option_visible_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const poppers = Array.from(document.querySelectorAll(".el-select__popper, .el-popper"))
                .filter(visible);
            for (const popper of poppers) {{
                const item = Array.from(popper.querySelectorAll(".el-select-dropdown__item, li, span, div"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (item) return true;
            }}
            return false;
        }}
        """

    def _select_dropdown_option_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }};
            const poppers = Array.from(document.querySelectorAll(".el-select__popper, .el-popper"))
                .filter(visible);
            for (const popper of poppers) {{
                const item = Array.from(popper.querySelectorAll(".el-select-dropdown__item, li, span, div"))
                    .find((el) => visible(el) && (el.innerText || el.textContent || "").trim() === expectedText);
                if (item) return item.closest(".el-select-dropdown__item") || item;
            }}
            return null;
        }}
        """

    def _website_restriction_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const root = __WEBSITE_RESTRICTION_ROOT__();
            return root && root.querySelector(__SWITCH_SELECTOR__);
        })())
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _website_restriction_switch_script(self) -> str:
        return """
        () => {
            const switchSelector = __SWITCH_SELECTOR__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(switchSelector);
            if (!switchEl) return null;
            switchEl.scrollIntoView({ block: "center" });
            return switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _website_restriction_switch_center_script(self) -> str:
        return """
        () => {
            const switchSelector = __SWITCH_SELECTOR__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(switchSelector);
            if (!switchEl) return null;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            return {
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                width: rect.width,
                height: rect.height,
                className: String(switchEl.className || ""),
            };
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _website_restriction_switch_dom_click_script(self) -> str:
        return """
        () => {
            const switchSelector = __SWITCH_SELECTOR__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return false;
            const switchEl = root.querySelector(switchSelector);
            if (!switchEl) return false;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return false;
            const eventOptions = { bubbles: true, cancelable: true, view: window };
            core.dispatchEvent(new MouseEvent("mouseover", eventOptions));
            core.dispatchEvent(new MouseEvent("mousemove", eventOptions));
            core.dispatchEvent(new MouseEvent("mousedown", eventOptions));
            core.dispatchEvent(new MouseEvent("mouseup", eventOptions));
            core.click();
            return true;
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _website_restriction_enabled_script(self) -> str:
        return """
        () => {
            const switchSelector = __SWITCH_SELECTOR__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(switchSelector);
            if (!switchEl) return null;
            const input = switchEl.querySelector("input");
            const ariaChecked = switchEl.getAttribute("aria-checked");
            if (ariaChecked === "true") return true;
            if (ariaChecked === "false") return false;
            return switchEl.classList.contains("is-checked") || Boolean(input?.checked);
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _website_restriction_radio_script(self, mode_text: str) -> str:
        return """
        () => {
            const modeText = __MODE_TEXT__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const radio = Array.from(root.querySelectorAll(__RADIO_SELECTOR__))
                .find((el) => (el.innerText || el.textContent || "").includes(modeText));
            if (!radio) return null;
            radio.scrollIntoView({ block: "center" });
            return radio;
        }
        """.replace("__MODE_TEXT__", repr(mode_text)).replace(
            "__WEBSITE_RESTRICTION_ROOT__",
            self._website_restriction_root_function(),
        ).replace(
            "__RADIO_SELECTOR__",
            repr(self.locator("radio")),
        )

    def _website_restriction_radio_checked_script(self, mode_text: str) -> str:
        return """
        () => {
            const modeText = __MODE_TEXT__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return false;
            const radio = Array.from(root.querySelectorAll(__RADIO_SELECTOR__))
                .find((el) => (el.innerText || el.textContent || "").includes(modeText));
            if (!radio) return false;
            return radio.classList.contains("is-checked") || Boolean(radio.querySelector(__INPUT_SELECTOR__)?.checked);
        }
        """.replace("__MODE_TEXT__", repr(mode_text)).replace(
            "__WEBSITE_RESTRICTION_ROOT__",
            self._website_restriction_root_function(),
        ).replace(
            "__RADIO_SELECTOR__",
            repr(self.locator("radio")),
        ).replace(
            "__INPUT_SELECTOR__",
            repr(self.locator("input")),
        )

    def _website_restriction_shortcut_script(self, shortcut_names: tuple[str, ...]) -> str:
        return """
        () => {
            const shortcutNames = __SHORTCUT_NAMES__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const checkbox = Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .find((el) => shortcutNames.some((name) => (el.innerText || el.textContent || "").includes(name)));
            if (!checkbox) return null;
            checkbox.scrollIntoView({ block: "center" });
            return checkbox;
        }
        """.replace("__SHORTCUT_NAMES__", repr(list(shortcut_names))).replace(
            "__WEBSITE_RESTRICTION_ROOT__",
            self._website_restriction_root_function(),
        ).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        )

    def _website_restriction_shortcut_checked_script(self, shortcut_names: tuple[str, ...]) -> str:
        return """
        () => {
            const shortcutNames = __SHORTCUT_NAMES__;
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return false;
            const checkbox = Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__))
                .find((el) => shortcutNames.some((name) => (el.innerText || el.textContent || "").includes(name)));
            if (!checkbox) return false;
            return checkbox.classList.contains("is-checked") || Boolean(checkbox.querySelector(__INPUT_SELECTOR__)?.checked);
        }
        """.replace("__SHORTCUT_NAMES__", repr(list(shortcut_names))).replace(
            "__WEBSITE_RESTRICTION_ROOT__",
            self._website_restriction_root_function(),
        ).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__INPUT_SELECTOR__",
            repr(self.locator("input")),
        )

    def _website_restriction_shortcut_states_script(self) -> str:
        return """
        () => {
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return {};
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const states = {};
            for (const checkbox of Array.from(root.querySelectorAll(__CHECKBOX_SELECTOR__)).filter(visible)) {
                const text = clean(checkbox.innerText || checkbox.textContent);
                if (!text) continue;
                const input = checkbox.querySelector(__INPUT_SELECTOR__);
                states[text] = checkbox.classList.contains("is-checked") || Boolean(input?.checked);
            }
            return states;
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function()).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__INPUT_SELECTOR__",
            repr(self.locator("input")),
        )

    def _website_restriction_url_textarea_script(self) -> str:
        return """
        () => {
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const textarea = Array.from(root.querySelectorAll(__TEXTAREA_SELECTOR__))
                .find((el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });
            if (!textarea) return null;
            textarea.scrollIntoView({ block: "center" });
            return textarea;
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function()).replace(
            "__TEXTAREA_SELECTOR__",
            repr(self.locator("textarea")),
        )

    def _website_restriction_url_value_script(self) -> str:
        return """
        () => {
            const root = __WEBSITE_RESTRICTION_ROOT__();
            if (!root) return null;
            const textarea = Array.from(root.querySelectorAll(__TEXTAREA_SELECTOR__))
                .find((el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });
            return textarea ? String(textarea.value || "") : null;
        }
        """.replace("__WEBSITE_RESTRICTION_ROOT__", self._website_restriction_root_function()).replace(
            "__TEXTAREA_SELECTOR__",
            repr(self.locator("textarea")),
        )

    def _website_restriction_root_function(self) -> str:
        return """
        (() => {
            const formItemSelector = __FORM_ITEM_SELECTOR__;
            const switchSelector = __SWITCH_SELECTOR__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(formItemSelector))
                .filter(visible)
                .filter((el) => clean(el.innerText || el.textContent).includes("访问网站限制"))
                .filter((el) => el.querySelector(switchSelector))
                .sort((left, right) => {
                    const leftText = clean(left.innerText || left.textContent);
                    const rightText = clean(right.innerText || right.textContent);
                    const leftScore = leftText.startsWith("访问网站限制") ? 0 : 1;
                    const rightScore = rightText.startsWith("访问网站限制") ? 0 : 1;
                    if (leftScore !== rightScore) return leftScore - rightScore;
                    const leftRect = left.getBoundingClientRect();
                    const rightRect = right.getBoundingClientRect();
                    return (leftRect.width * leftRect.height) - (rightRect.width * rightRect.height);
            });
            return candidates[0] || null;
        })
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _bookmark_setting_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const root = __BOOKMARK_SETTING_ROOT__();
            return root && root.querySelector(__SWITCH_SELECTOR__);
        })())
        """.replace("__BOOKMARK_SETTING_ROOT__", self._bookmark_setting_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _bookmark_setting_switch_center_script(self) -> str:
        return """
        () => {
            const root = __BOOKMARK_SETTING_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return null;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            return {
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                width: rect.width,
                height: rect.height,
                className: String(switchEl.className || ""),
            };
        }
        """.replace("__BOOKMARK_SETTING_ROOT__", self._bookmark_setting_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _bookmark_setting_switch_dom_click_script(self) -> str:
        return """
        () => {
            const root = __BOOKMARK_SETTING_ROOT__();
            if (!root) return false;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return false;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return false;
            const eventOptions = { bubbles: true, cancelable: true, view: window };
            core.dispatchEvent(new MouseEvent("mouseover", eventOptions));
            core.dispatchEvent(new MouseEvent("mousemove", eventOptions));
            core.dispatchEvent(new MouseEvent("mousedown", eventOptions));
            core.dispatchEvent(new MouseEvent("mouseup", eventOptions));
            core.click();
            return true;
        }
        """.replace("__BOOKMARK_SETTING_ROOT__", self._bookmark_setting_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _bookmark_setting_enabled_script(self) -> str:
        return """
        () => {
            const root = __BOOKMARK_SETTING_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return null;
            const input = switchEl.querySelector("input");
            const ariaChecked = switchEl.getAttribute("aria-checked");
            if (ariaChecked === "true") return true;
            if (ariaChecked === "false") return false;
            return switchEl.classList.contains("is-checked") || Boolean(input?.checked);
        }
        """.replace("__BOOKMARK_SETTING_ROOT__", self._bookmark_setting_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _bookmark_upload_button_script(self) -> str:
        return """
        () => {
            const root = __BOOKMARK_SETTING_ROOT__();
            if (!root) return null;
            const button = Array.from(root.querySelectorAll(__BUTTON_SELECTOR__))
                .find((el) => (el.innerText || el.textContent || "").includes("点击上传"));
            if (!button) return null;
            button.scrollIntoView({ block: "center", inline: "center" });
            return button;
        }
        """.replace("__BOOKMARK_SETTING_ROOT__", self._bookmark_setting_root_function()).replace(
            "__BUTTON_SELECTOR__",
            repr(self.locator("button")),
        )

    def _bookmark_effect_mode_script(self, mode_text: str) -> str:
        return """
        () => {
            const modeText = __MODE_TEXT__;
            const root = __BOOKMARK_SETTING_ROOT__();
            if (!root) return null;
            const radio = Array.from(root.querySelectorAll(__RADIO_SELECTOR__))
                .find((el) => (el.innerText || el.textContent || "").includes(modeText));
            if (!radio) return null;
            radio.scrollIntoView({ block: "center", inline: "center" });
            return radio;
        }
        """.replace("__MODE_TEXT__", repr(mode_text)).replace(
            "__BOOKMARK_SETTING_ROOT__",
            self._bookmark_setting_root_function(),
        ).replace(
            "__RADIO_SELECTOR__",
            repr(self.locator("radio")),
        )

    def _bookmark_effect_mode_checked_script(self, mode_text: str) -> str:
        return """
        () => {
            const modeText = __MODE_TEXT__;
            const root = __BOOKMARK_SETTING_ROOT__();
            if (!root) return false;
            const radio = Array.from(root.querySelectorAll(__RADIO_SELECTOR__))
                .find((el) => (el.innerText || el.textContent || "").includes(modeText));
            if (!radio) return false;
            return radio.classList.contains("is-checked") || Boolean(radio.querySelector(__INPUT_SELECTOR__)?.checked);
        }
        """.replace("__MODE_TEXT__", repr(mode_text)).replace(
            "__BOOKMARK_SETTING_ROOT__",
            self._bookmark_setting_root_function(),
        ).replace(
            "__RADIO_SELECTOR__",
            repr(self.locator("radio")),
        ).replace(
            "__INPUT_SELECTOR__",
            repr(self.locator("input")),
        )

    def _bookmark_overwrite_rule_select_script(self) -> str:
        return """
        () => {
            const root = __BOOKMARK_SETTING_ROOT__();
            if (!root) return null;
            const items = Array.from(root.querySelectorAll(__FORM_ITEM_SELECTOR__))
                .filter((el) => (el.innerText || el.textContent || "").includes("覆盖规则"));
            const item = items[items.length - 1];
            if (!item) return null;
            const select = item.querySelector(__SELECT_CONTROL_SELECTOR__);
            if (!select) return null;
            select.scrollIntoView({ block: "center", inline: "center" });
            return select;
        }
        """.replace("__BOOKMARK_SETTING_ROOT__", self._bookmark_setting_root_function()).replace(
            "__FORM_ITEM_SELECTOR__",
            repr(self.locator("form_item")),
        ).replace(
            "__SELECT_CONTROL_SELECTOR__",
            repr(self.locator("select_control")),
        )

    def _bookmark_setting_text_script(self) -> str:
        return """
        () => {
            const root = __BOOKMARK_SETTING_ROOT__();
            return root ? String(root.innerText || root.textContent || "") : "";
        }
        """.replace("__BOOKMARK_SETTING_ROOT__", self._bookmark_setting_root_function())

    def _environment_list_pagination_setting_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const root = __ENVIRONMENT_LIST_PAGINATION_ROOT__();
            return root && root.querySelector(__SWITCH_SELECTOR__);
        })())
        """.replace(
            "__ENVIRONMENT_LIST_PAGINATION_ROOT__",
            self._environment_list_pagination_setting_root_function(),
        ).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _environment_list_pagination_setting_switch_center_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_LIST_PAGINATION_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return null;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            return {
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                width: rect.width,
                height: rect.height,
                className: String(switchEl.className || ""),
            };
        }
        """.replace(
            "__ENVIRONMENT_LIST_PAGINATION_ROOT__",
            self._environment_list_pagination_setting_root_function(),
        ).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _environment_list_pagination_setting_switch_dom_click_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_LIST_PAGINATION_ROOT__();
            if (!root) return false;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return false;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return false;
            const eventOptions = { bubbles: true, cancelable: true, view: window };
            core.dispatchEvent(new MouseEvent("mouseover", eventOptions));
            core.dispatchEvent(new MouseEvent("mousemove", eventOptions));
            core.dispatchEvent(new MouseEvent("mousedown", eventOptions));
            core.dispatchEvent(new MouseEvent("mouseup", eventOptions));
            core.click();
            return true;
        }
        """.replace(
            "__ENVIRONMENT_LIST_PAGINATION_ROOT__",
            self._environment_list_pagination_setting_root_function(),
        ).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _environment_list_pagination_setting_enabled_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_LIST_PAGINATION_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return null;
            const input = switchEl.querySelector("input");
            const ariaChecked = switchEl.getAttribute("aria-checked");
            if (ariaChecked === "true") return true;
            if (ariaChecked === "false") return false;
            return switchEl.classList.contains("is-checked") || Boolean(input?.checked);
        }
        """.replace(
            "__ENVIRONMENT_LIST_PAGINATION_ROOT__",
            self._environment_list_pagination_setting_root_function(),
        ).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _environment_list_pagination_page_size_select_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_LIST_PAGINATION_ROOT__();
            if (!root) return null;
            const field = __ENVIRONMENT_LIST_PAGINATION_PAGE_SIZE_FIELD__(root);
            if (!field) return null;
            const select = field.querySelector(__SELECT_CONTROL_SELECTOR__);
            if (!select) return null;
            select.scrollIntoView({ block: "center", inline: "center" });
            return select;
        }
        """.replace(
            "__ENVIRONMENT_LIST_PAGINATION_ROOT__",
            self._environment_list_pagination_setting_root_function(),
        ).replace(
            "__ENVIRONMENT_LIST_PAGINATION_PAGE_SIZE_FIELD__",
            self._environment_list_pagination_page_size_field_function(),
        ).replace(
            "__SELECT_CONTROL_SELECTOR__",
            repr(self.locator("select_control_with_input")),
        )

    def _environment_list_pagination_page_size_text_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_LIST_PAGINATION_ROOT__();
            if (!root) return "";
            const field = __ENVIRONMENT_LIST_PAGINATION_PAGE_SIZE_FIELD__(root);
            return field ? String(field.innerText || field.textContent || "") : "";
        }
        """.replace(
            "__ENVIRONMENT_LIST_PAGINATION_ROOT__",
            self._environment_list_pagination_setting_root_function(),
        ).replace(
            "__ENVIRONMENT_LIST_PAGINATION_PAGE_SIZE_FIELD__",
            self._environment_list_pagination_page_size_field_function(),
        )

    def _environment_list_pagination_page_size_selected_script(self, page_size_text: str) -> str:
        return f"""
        () => {{
            const expectedText = {page_size_text!r};
            const normalize = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const root = __ENVIRONMENT_LIST_PAGINATION_ROOT__();
            if (!root) return false;
            const field = __ENVIRONMENT_LIST_PAGINATION_PAGE_SIZE_FIELD__(root);
            if (!field) return false;
            return normalize(field.innerText || field.textContent).includes(expectedText);
        }}
        """.replace(
            "__ENVIRONMENT_LIST_PAGINATION_ROOT__",
            self._environment_list_pagination_setting_root_function(),
        ).replace(
            "__ENVIRONMENT_LIST_PAGINATION_PAGE_SIZE_FIELD__",
            self._environment_list_pagination_page_size_field_function(),
        )

    def _environment_list_pagination_page_size_field_function(self) -> str:
        return """
        ((root) => {
            const formItemSelector = __FORM_ITEM_SELECTOR__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const rootRect = root.getBoundingClientRect();
            const rootContainer = root.parentElement || root;
            const localField = Array.from(root.querySelectorAll(formItemSelector))
                .filter(visible)
                .find((item) => clean(item.innerText || item.textContent).includes("分页条数"));
            if (localField) return localField;

            const scopedFields = Array.from(rootContainer.querySelectorAll(formItemSelector))
                .filter(visible)
                .map((item) => ({ item, rect: item.getBoundingClientRect(), text: clean(item.innerText || item.textContent) }))
                .filter(({ rect }) => rect.y >= rootRect.y - 5 && rect.y <= rootRect.y + 220)
                .sort((left, right) => left.rect.y - right.rect.y);
            return scopedFields.find(({ text }) => text.includes("分页条数"))?.item
                || scopedFields.find(({ item }) => item.querySelector(__SELECT_CONTROL_SELECTOR__))?.item
                || null;
        })
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__SELECT_CONTROL_SELECTOR__",
            repr(self.locator("select_control")),
        )

    def _environment_list_sort_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const root = __ENVIRONMENT_LIST_SORT_ROOT__();
            return root && root.querySelector(__SWITCH_SELECTOR__);
        })())
        """.replace("__ENVIRONMENT_LIST_SORT_ROOT__", self._environment_list_sort_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _environment_list_sort_switch_center_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_LIST_SORT_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return null;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            return {
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                width: rect.width,
                height: rect.height,
                className: String(switchEl.className || ""),
            };
        }
        """.replace("__ENVIRONMENT_LIST_SORT_ROOT__", self._environment_list_sort_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _environment_list_sort_switch_dom_click_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_LIST_SORT_ROOT__();
            if (!root) return false;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return false;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return false;
            const eventOptions = { bubbles: true, cancelable: true, view: window };
            core.dispatchEvent(new MouseEvent("mouseover", eventOptions));
            core.dispatchEvent(new MouseEvent("mousemove", eventOptions));
            core.dispatchEvent(new MouseEvent("mousedown", eventOptions));
            core.dispatchEvent(new MouseEvent("mouseup", eventOptions));
            core.click();
            return true;
        }
        """.replace("__ENVIRONMENT_LIST_SORT_ROOT__", self._environment_list_sort_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _environment_list_sort_enabled_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_LIST_SORT_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return null;
            const input = switchEl.querySelector("input");
            const ariaChecked = switchEl.getAttribute("aria-checked");
            if (ariaChecked === "true") return true;
            if (ariaChecked === "false") return false;
            return switchEl.classList.contains("is-checked") || Boolean(input?.checked);
        }
        """.replace("__ENVIRONMENT_LIST_SORT_ROOT__", self._environment_list_sort_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _environment_list_sort_select_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const root = __ENVIRONMENT_LIST_SORT_ROOT__();
            if (!root) return null;
            const field = __ENVIRONMENT_LIST_SORT_FIELD__(root, {label_text!r});
            if (!field) return null;
            const select = field.querySelector(__SELECT_CONTROL_SELECTOR__);
            if (!select) return null;
            select.scrollIntoView({{ block: "center", inline: "center" }});
            return select;
        }}
        """.replace("__ENVIRONMENT_LIST_SORT_ROOT__", self._environment_list_sort_root_function()).replace(
            "__ENVIRONMENT_LIST_SORT_FIELD__",
            self._environment_list_sort_field_function(),
        ).replace(
            "__SELECT_CONTROL_SELECTOR__",
            repr(self.locator("select_control_with_input")),
        )

    def _environment_list_sort_radio_script(self, label_text: str, option_text: str) -> str:
        return f"""
        () => {{
            const root = __ENVIRONMENT_LIST_SORT_ROOT__();
            if (!root) return null;
            const field = __ENVIRONMENT_LIST_SORT_FIELD__(root, {label_text!r});
            if (!field) return null;
            const normalizeOption = (value) => {{
                const text = String(value || "").replace(/\\s+/g, "").trim();
                const aliases = {{
                    "环境序号": ["环境序号", "序号"],
                    "环境名称": ["环境名称", "名称"],
                    "环境分组": ["环境分组", "分组"],
                    "备注": ["备注"],
                    "标签": ["标签"],
                    "升序": ["升序"],
                    "降序": ["降序"],
                }};
                for (const [canonical, values] of Object.entries(aliases)) {{
                    if (values.some((item) => text === item || text.includes(item))) return canonical;
                }}
                return text;
            }};
            const expectedOption = normalizeOption({option_text!r});
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const radio = Array.from(field.querySelectorAll(__RADIO_SELECTOR__))
                .filter(visible)
                .find((item) => normalizeOption(item.innerText || item.textContent) === expectedOption);
            if (!radio) return null;
            radio.scrollIntoView({{ block: "center", inline: "center" }});
            return radio;
        }}
        """.replace("__ENVIRONMENT_LIST_SORT_ROOT__", self._environment_list_sort_root_function()).replace(
            "__ENVIRONMENT_LIST_SORT_FIELD__",
            self._environment_list_sort_field_function(),
        ).replace(
            "__RADIO_SELECTOR__",
            repr(self.locator("radio")),
        )

    def _environment_list_sort_radio_exists_script(self, label_text: str, option_text: str) -> str:
        return f"""
        () => Boolean((() => {{
            const root = __ENVIRONMENT_LIST_SORT_ROOT__();
            if (!root) return null;
            const field = __ENVIRONMENT_LIST_SORT_FIELD__(root, {label_text!r});
            if (!field) return null;
            const normalizeOption = (value) => {{
                const text = String(value || "").replace(/\\s+/g, "").trim();
                const aliases = {{
                    "环境序号": ["环境序号", "序号"],
                    "环境名称": ["环境名称", "名称"],
                    "环境分组": ["环境分组", "分组"],
                    "备注": ["备注"],
                    "标签": ["标签"],
                    "升序": ["升序"],
                    "降序": ["降序"],
                }};
                for (const [canonical, values] of Object.entries(aliases)) {{
                    if (values.some((item) => text === item || text.includes(item))) return canonical;
                }}
                return text;
            }};
            const expectedOption = normalizeOption({option_text!r});
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            return Array.from(field.querySelectorAll(__RADIO_SELECTOR__))
                .filter(visible)
                .find((item) => normalizeOption(item.innerText || item.textContent) === expectedOption) || null;
        }})())
        """.replace("__ENVIRONMENT_LIST_SORT_ROOT__", self._environment_list_sort_root_function()).replace(
            "__ENVIRONMENT_LIST_SORT_FIELD__",
            self._environment_list_sort_field_function(),
        ).replace(
            "__RADIO_SELECTOR__",
            repr(self.locator("radio")),
        )

    def _environment_list_sort_option_selected_script(self, label_text: str, option_text: str) -> str:
        return f"""
        () => {{
            const root = __ENVIRONMENT_LIST_SORT_ROOT__();
            if (!root) return false;
            const field = __ENVIRONMENT_LIST_SORT_FIELD__(root, {label_text!r});
            if (!field) return false;
            const normalizeOption = (value) => {{
                const text = String(value || "").replace(/\\s+/g, "").trim();
                const aliases = {{
                    "环境序号": ["环境序号", "序号"],
                    "环境名称": ["环境名称", "名称"],
                    "环境分组": ["环境分组", "分组"],
                    "备注": ["备注"],
                    "标签": ["标签"],
                    "升序": ["升序"],
                    "降序": ["降序"],
                }};
                for (const [canonical, values] of Object.entries(aliases)) {{
                    if (values.some((item) => text === item || text.includes(item))) return canonical;
                }}
                return text;
            }};
            const expectedOption = normalizeOption({option_text!r});
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const radio = Array.from(field.querySelectorAll(__RADIO_SELECTOR__))
                .filter(visible)
                .find((item) => normalizeOption(item.innerText || item.textContent) === expectedOption);
            if (radio) {{
                return radio.classList.contains("is-checked") || Boolean(radio.querySelector(__INPUT_SELECTOR__)?.checked);
            }}
            return normalizeOption(clean(field.innerText || field.textContent)) === expectedOption;
        }}
        """.replace("__ENVIRONMENT_LIST_SORT_ROOT__", self._environment_list_sort_root_function()).replace(
            "__ENVIRONMENT_LIST_SORT_FIELD__",
            self._environment_list_sort_field_function(),
        ).replace(
            "__RADIO_SELECTOR__",
            repr(self.locator("radio")),
        ).replace(
            "__INPUT_SELECTOR__",
            repr(self.locator("input")),
        )

    def _environment_list_sort_option_text_script(self, label_text: str) -> str:
        return f"""
        () => {{
            const root = __ENVIRONMENT_LIST_SORT_ROOT__();
            if (!root) return "";
            const field = __ENVIRONMENT_LIST_SORT_FIELD__(root, {label_text!r});
            return field ? String(field.innerText || field.textContent || "") : "";
        }}
        """.replace("__ENVIRONMENT_LIST_SORT_ROOT__", self._environment_list_sort_root_function()).replace(
            "__ENVIRONMENT_LIST_SORT_FIELD__",
            self._environment_list_sort_field_function(),
        )

    def _environment_list_sort_field_function(self) -> str:
        return """
        ((root, labelText) => {
            const formItemSelector = __FORM_ITEM_SELECTOR__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const rootRect = root.getBoundingClientRect();
            const rootContainer = root.parentElement || root;
            const localField = Array.from(root.querySelectorAll(formItemSelector))
                .filter(visible)
                .find((item) => clean(item.innerText || item.textContent).includes(labelText));
            if (localField) return localField;

            const scopedFields = Array.from(rootContainer.querySelectorAll(formItemSelector))
                .filter(visible)
                .map((item) => ({ item, rect: item.getBoundingClientRect(), text: clean(item.innerText || item.textContent) }))
                .filter(({ rect }) => rect.y >= rootRect.y - 5 && rect.y <= rootRect.y + 260)
                .sort((left, right) => left.rect.y - right.rect.y);
            return scopedFields.find(({ text }) => text.includes(labelText))?.item || null;
        })
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item")))

    def _environment_field_display_limit_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const root = __ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__();
            return root && root.querySelector(__SWITCH_SELECTOR__);
        })())
        """.replace("__ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__", self._environment_field_display_limit_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _environment_field_display_limit_switch_center_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return null;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            return {
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                width: rect.width,
                height: rect.height,
                className: String(switchEl.className || ""),
            };
        }
        """.replace("__ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__", self._environment_field_display_limit_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _environment_field_display_limit_switch_dom_click_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__();
            if (!root) return false;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return false;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return false;
            const eventOptions = { bubbles: true, cancelable: true, view: window };
            core.dispatchEvent(new MouseEvent("mouseover", eventOptions));
            core.dispatchEvent(new MouseEvent("mousemove", eventOptions));
            core.dispatchEvent(new MouseEvent("mousedown", eventOptions));
            core.dispatchEvent(new MouseEvent("mouseup", eventOptions));
            core.click();
            return true;
        }
        """.replace("__ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__", self._environment_field_display_limit_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _environment_field_display_limit_enabled_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(__SWITCH_SELECTOR__);
            if (!switchEl) return null;
            const input = switchEl.querySelector("input");
            const ariaChecked = switchEl.getAttribute("aria-checked");
            if (ariaChecked === "true") return true;
            if (ariaChecked === "false") return false;
            return switchEl.classList.contains("is-checked") || Boolean(input?.checked);
        }
        """.replace("__ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__", self._environment_field_display_limit_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _environment_field_display_limit_edit_button_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__();
            if (!root) return null;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(root.querySelectorAll(__CLICKABLE_TEXT_SELECTOR__))
                .filter(visible)
                .filter((el) => clean(el.innerText || el.textContent) === "编辑");
            const button = candidates[candidates.length - 1] || null;
            if (!button) return null;
            button.scrollIntoView({ block: "center", inline: "center" });
            return button;
        }
        """.replace("__ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__", self._environment_field_display_limit_root_function()).replace(
            "__CLICKABLE_TEXT_SELECTOR__",
            repr(self.locator("clickable_text_candidates")),
        )

    def _environment_field_display_limit_text_script(self) -> str:
        return """
        () => {
            const root = __ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__();
            return root ? String(root.innerText || root.textContent || "") : "";
        }
        """.replace("__ENVIRONMENT_FIELD_DISPLAY_LIMIT_ROOT__", self._environment_field_display_limit_root_function())

    def _environment_field_display_limit_dialog_visible_script(self) -> str:
        return """
        () => {
            const dialogTitles = __DIALOG_TITLES__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            return Array.from(document.querySelectorAll(__DIALOG_SELECTOR__))
                .some((dialog) => visible(dialog) && dialogTitles.some((title) => (dialog.innerText || "").includes(title)));
        }
        """.replace("__DIALOG_TITLES__", repr(list(self.ENVIRONMENT_FIELD_DISPLAY_LIMIT_DIALOG_TITLES))).replace(
            "__DIALOG_SELECTOR__",
            repr(self.locator("dialog")),
        )

    def _environment_field_display_limit_dialog_checkbox_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const dialog = __ENVIRONMENT_FIELD_DISPLAY_LIMIT_DIALOG__();
            if (!dialog) return null;
            const normalizeField = (value) => {{
                const text = String(value || "").replace(/\\s+/g, "").trim();
                const aliases = {{
                    "环境序号": ["环境序号", "序号"],
                    "环境名称": ["环境名称", "名称"],
                    "环境分组": ["环境分组", "分组"],
                    "备注": ["备注"],
                    "标签": ["标签"],
                    "全选": ["全选"],
                }};
                for (const [canonical, values] of Object.entries(aliases)) {{
                    if (values.some((item) => text === item || text.includes(item))) return canonical;
                }}
                return text;
            }};
            const expectedField = normalizeField(expectedText);
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const checkbox = Array.from(dialog.querySelectorAll(__CHECKBOX_SELECTOR__))
                .filter(visible)
                .find((item) => normalizeField(clean(item.innerText || item.textContent)) === expectedField);
            if (!checkbox) return null;
            checkbox.scrollIntoView({{ block: "center", inline: "center" }});
            return checkbox;
        }}
        """.replace(
            "__ENVIRONMENT_FIELD_DISPLAY_LIMIT_DIALOG__",
            self._environment_field_display_limit_dialog_function(),
        ).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        )

    def _environment_field_display_limit_dialog_checkbox_checked_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const dialog = __ENVIRONMENT_FIELD_DISPLAY_LIMIT_DIALOG__();
            if (!dialog) return null;
            const normalizeField = (value) => {{
                const text = String(value || "").replace(/\\s+/g, "").trim();
                const aliases = {{
                    "环境序号": ["环境序号", "序号"],
                    "环境名称": ["环境名称", "名称"],
                    "环境分组": ["环境分组", "分组"],
                    "备注": ["备注"],
                    "标签": ["标签"],
                    "全选": ["全选"],
                }};
                for (const [canonical, values] of Object.entries(aliases)) {{
                    if (values.some((item) => text === item || text.includes(item))) return canonical;
                }}
                return text;
            }};
            const expectedField = normalizeField(expectedText);
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const checkbox = Array.from(dialog.querySelectorAll(__CHECKBOX_SELECTOR__))
                .filter(visible)
                .find((item) => normalizeField(clean(item.innerText || item.textContent)) === expectedField);
            if (!checkbox) return null;
            return checkbox.classList.contains("is-checked") || Boolean(checkbox.querySelector(__INPUT_SELECTOR__)?.checked);
        }}
        """.replace(
            "__ENVIRONMENT_FIELD_DISPLAY_LIMIT_DIALOG__",
            self._environment_field_display_limit_dialog_function(),
        ).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__INPUT_SELECTOR__",
            repr(self.locator("input")),
        )

    def _environment_field_display_limit_dialog_checkbox_states_script(self) -> str:
        return """
        () => {
            const dialog = __ENVIRONMENT_FIELD_DISPLAY_LIMIT_DIALOG__();
            if (!dialog) return {};
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const states = {};
            for (const checkbox of Array.from(dialog.querySelectorAll(__CHECKBOX_SELECTOR__)).filter(visible)) {
                const text = clean(checkbox.innerText || checkbox.textContent);
                if (!text) continue;
                states[text] = checkbox.classList.contains("is-checked") || Boolean(checkbox.querySelector(__INPUT_SELECTOR__)?.checked);
            }
            return states;
        }
        """.replace(
            "__ENVIRONMENT_FIELD_DISPLAY_LIMIT_DIALOG__",
            self._environment_field_display_limit_dialog_function(),
        ).replace(
            "__CHECKBOX_SELECTOR__",
            repr(self.locator("checkbox")),
        ).replace(
            "__INPUT_SELECTOR__",
            repr(self.locator("input")),
        )

    def _environment_field_display_limit_dialog_function(self) -> str:
        return """
        (() => {
            const dialogTitles = __DIALOG_TITLES__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const dialogs = Array.from(document.querySelectorAll(__DIALOG_SELECTOR__))
                .filter((dialog) => visible(dialog) && dialogTitles.some((title) => (dialog.innerText || "").includes(title)));
            return dialogs[dialogs.length - 1] || null;
        })
        """.replace("__DIALOG_TITLES__", repr(list(self.ENVIRONMENT_FIELD_DISPLAY_LIMIT_DIALOG_TITLES))).replace(
            "__DIALOG_SELECTOR__",
            repr(self.locator("dialog")),
        )

    def _environment_field_display_limit_root_function(self) -> str:
        return """
        (() => {
            const formItemSelector = __FORM_ITEM_SELECTOR__;
            const switchSelector = __SWITCH_SELECTOR__;
            const settingLabels = __SETTING_LABELS__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(formItemSelector))
                .filter(visible)
                .filter((el) => {
                    const text = clean(el.innerText || el.textContent);
                    return settingLabels.some((label) => text.includes(label));
                })
                .filter((el) => el.querySelector(switchSelector))
                .sort((left, right) => {
                    const leftText = clean(left.innerText || left.textContent);
                    const rightText = clean(right.innerText || right.textContent);
                    const leftScore = settingLabels.some((label) => leftText.startsWith(label)) ? 0 : 1;
                    const rightScore = settingLabels.some((label) => rightText.startsWith(label)) ? 0 : 1;
                    if (leftScore !== rightScore) return leftScore - rightScore;
                    const leftRect = left.getBoundingClientRect();
                    const rightRect = right.getBoundingClientRect();
                    return (leftRect.width * leftRect.height) - (rightRect.width * rightRect.height);
            });
            return candidates[0] || null;
        })
        """.replace("__SETTING_LABELS__", repr(list(self.ENVIRONMENT_FIELD_DISPLAY_LIMIT_LABELS))).replace(
            "__FORM_ITEM_SELECTOR__",
            repr(self.locator("form_item")),
        ).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _environment_list_pagination_setting_root_function(self) -> str:
        return """
        (() => {
            const formItemSelector = __FORM_ITEM_SELECTOR__;
            const switchSelector = __SWITCH_SELECTOR__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(formItemSelector))
                .filter(visible)
                .filter((el) => clean(el.innerText || el.textContent).includes("环境列表分页设置"))
                .filter((el) => el.querySelector(switchSelector))
                .sort((left, right) => {
                    const leftText = clean(left.innerText || left.textContent);
                    const rightText = clean(right.innerText || right.textContent);
                    const leftScore = leftText.startsWith("环境列表分页设置") ? 0 : 1;
                    const rightScore = rightText.startsWith("环境列表分页设置") ? 0 : 1;
                    if (leftScore !== rightScore) return leftScore - rightScore;
                    const leftRect = left.getBoundingClientRect();
                    const rightRect = right.getBoundingClientRect();
                    return (leftRect.width * leftRect.height) - (rightRect.width * rightRect.height);
            });
            return candidates[0] || null;
        })
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _environment_list_sort_root_function(self) -> str:
        return """
        (() => {
            const formItemSelector = __FORM_ITEM_SELECTOR__;
            const switchSelector = __SWITCH_SELECTOR__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(formItemSelector))
                .filter(visible)
                .filter((el) => clean(el.innerText || el.textContent).includes("环境列表排序"))
                .filter((el) => el.querySelector(switchSelector))
                .sort((left, right) => {
                    const leftText = clean(left.innerText || left.textContent);
                    const rightText = clean(right.innerText || right.textContent);
                    const leftScore = leftText.startsWith("环境列表排序") ? 0 : 1;
                    const rightScore = rightText.startsWith("环境列表排序") ? 0 : 1;
                    if (leftScore !== rightScore) return leftScore - rightScore;
                    const leftRect = left.getBoundingClientRect();
                    const rightRect = right.getBoundingClientRect();
                    return (leftRect.width * leftRect.height) - (rightRect.width * rightRect.height);
            });
            return candidates[0] || null;
        })
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _bookmark_setting_root_function(self) -> str:
        return """
        (() => {
            const rootById = document.querySelector(__BOOKMARK_ROOT_SELECTOR__);
            if (rootById) return rootById;
            const formItemSelector = __FORM_ITEM_SELECTOR__;
            const switchSelector = __SWITCH_SELECTOR__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(formItemSelector))
                .filter(visible)
                .filter((el) => clean(el.innerText || el.textContent).includes("书签设置"))
                .filter((el) => el.querySelector(switchSelector))
                .sort((left, right) => {
                    const leftText = clean(left.innerText || left.textContent);
                    const rightText = clean(right.innerText || right.textContent);
                    const leftScore = leftText.startsWith("书签设置") ? 0 : 1;
                    const rightScore = rightText.startsWith("书签设置") ? 0 : 1;
                    if (leftScore !== rightScore) return leftScore - rightScore;
                    const leftRect = left.getBoundingClientRect();
                    const rightRect = right.getBoundingClientRect();
                    return (leftRect.width * leftRect.height) - (rightRect.width * rightRect.height);
            });
            return candidates[0] || null;
        })
        """.replace("__BOOKMARK_ROOT_SELECTOR__", repr(self.locator("bookmark_setting_root"))).replace(
            "__FORM_ITEM_SELECTOR__",
            repr(self.locator("form_item")),
        ).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _visible_dropdown_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const items = Array.from(document.querySelectorAll(__DROPDOWN_ITEM_SELECTOR__))
                .filter((el) => visible(el))
                .filter((el) => (el.innerText || el.textContent || "").trim() === expectedText);
            return items[items.length - 1] || null;
        }}
        """.replace("__DROPDOWN_ITEM_SELECTOR__", repr(self.locator("dropdown_item_candidates")))

    def _visible_dropdown_item_by_normalized_text_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const normalize = (value) => String(value || "").replace(/\\s+/g, "").trim();
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const items = Array.from(document.querySelectorAll(__DROPDOWN_ITEM_SELECTOR__))
                .filter((el) => visible(el))
                .filter((el) => normalize(el.innerText || el.textContent) === expectedText);
            return items[items.length - 1] || null;
        }}
        """.replace("__DROPDOWN_ITEM_SELECTOR__", repr(self.locator("dropdown_item_candidates")))

    def _environment_list_sort_dropdown_item_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const normalizeOption = (value) => {{
                const text = String(value || "").replace(/\\s+/g, "").trim();
                const aliases = {{
                    "环境序号": ["环境序号", "序号"],
                    "环境名称": ["环境名称", "名称"],
                    "环境分组": ["环境分组", "分组"],
                    "备注": ["备注"],
                    "标签": ["标签"],
                    "升序": ["升序"],
                    "降序": ["降序"],
                }};
                for (const [canonical, values] of Object.entries(aliases)) {{
                    if (values.some((item) => text === item || text.includes(item))) return canonical;
                }}
                return text;
            }};
            const expectedOption = normalizeOption(expectedText);
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const items = Array.from(document.querySelectorAll(__DROPDOWN_ITEM_SELECTOR__))
                .filter((el) => visible(el))
                .filter((el) => normalizeOption(el.innerText || el.textContent) === expectedOption);
            return items[items.length - 1] || null;
        }}
        """.replace("__DROPDOWN_ITEM_SELECTOR__", repr(self.locator("dropdown_item_candidates")))

    def _global_settings_form_select_exists_script(self, label_text: str) -> str:
        return """
        () => {
            const finder = __FORM_ITEM_FINDER__;
            const item = finder();
            return Boolean(item && item.querySelector(__SELECT_CONTROL_SELECTOR__));
        }
        """.replace("__FORM_ITEM_FINDER__", self._global_settings_form_item_function(label_text)).replace(
            "__SELECT_CONTROL_SELECTOR__",
            repr(self.locator("select_control")),
        )

    def _global_settings_form_select_script(self, label_text: str) -> str:
        return """
        () => {
            const finder = __FORM_ITEM_FINDER__;
            const item = finder();
            if (!item) return null;
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0
                    && rect.left < window.innerWidth
                    && rect.right > 0;
            };
            const select = Array.from(item.querySelectorAll(__SELECT_CONTROL_SELECTOR__))
                .find((el) => visible(el)) || null;
            if (select) select.scrollIntoView({ block: "center", inline: "center" });
            return select;
        }
        """.replace("__FORM_ITEM_FINDER__", self._global_settings_form_item_function(label_text)).replace(
            "__SELECT_CONTROL_SELECTOR__",
            repr(self.locator("select_control_with_input")),
        )

    def _global_settings_form_select_value_script(self, label_text: str) -> str:
        return """
        () => {
            const finder = __FORM_ITEM_FINDER__;
            const item = finder();
            if (!item) return "";
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0
                    && !String(el.className || "").includes("is-hidden");
            };
            const preferred = Array.from(item.querySelectorAll(
                ".el-select__placeholder, .el-select__selected-item span, .el-select__selected-item"
            ))
                .filter((el) => visible(el))
                .map((el) => clean(el.innerText || el.textContent))
                .filter(Boolean);
            if (preferred.length) return preferred[0];
            const inputValue = Array.from(item.querySelectorAll("input"))
                .filter((el) => visible(el))
                .map((el) => clean(el.value || el.getAttribute("placeholder") || ""))
                .find(Boolean);
            if (inputValue) return inputValue;
            const select = Array.from(item.querySelectorAll(__SELECT_CONTROL_SELECTOR__)).find((el) => visible(el));
            return clean(select ? (select.innerText || select.textContent) : "");
        }
        """.replace("__FORM_ITEM_FINDER__", self._global_settings_form_item_function(label_text)).replace(
            "__SELECT_CONTROL_SELECTOR__",
            repr(self.locator("select_control")),
        )

    def _clear_local_cache_sync_cloud_switch_script(self) -> str:
        return """
        () => {
            const switchEl = __CLEAR_LOCAL_CACHE_SYNC_CLOUD_SWITCH__();
            if (!switchEl) return null;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            return core;
        }
        """.replace(
            "__CLEAR_LOCAL_CACHE_SYNC_CLOUD_SWITCH__",
            self._clear_local_cache_sync_cloud_switch_function(),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _clear_local_cache_sync_cloud_enabled_script(self) -> str:
        return """
        () => {
            const switchEl = __CLEAR_LOCAL_CACHE_SYNC_CLOUD_SWITCH__();
            if (!switchEl) return null;
            const input = switchEl.querySelector("input");
            const ariaChecked = input?.getAttribute("aria-checked") || switchEl.getAttribute("aria-checked") || "";
            if (ariaChecked === "true") return true;
            if (ariaChecked === "false") return false;
            return switchEl.classList.contains("is-checked") || Boolean(input?.checked);
        }
        """.replace(
            "__CLEAR_LOCAL_CACHE_SYNC_CLOUD_SWITCH__",
            self._clear_local_cache_sync_cloud_switch_function(),
        )

    def _clear_local_cache_sync_cloud_switch_function(self) -> str:
        return """
        (() => {
            const formItemSelector = __FORM_ITEM_SELECTOR__;
            const switchSelector = __SWITCH_SELECTOR__;
            const expectedText = __EXPECTED_TEXT__;
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(formItemSelector))
                .filter(visible)
                .filter((item) => clean(item.innerText || item.textContent).includes(expectedText))
                .map((item) => item.querySelector(switchSelector))
                .filter(visible);
            return candidates[0] || null;
        })
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__EXPECTED_TEXT__",
            repr(self.CLEAR_LOCAL_CACHE_SYNC_CLOUD_TEXT),
        )

    def _global_settings_form_item_function(self, label_text: str) -> str:
        return """
        (() => {
            const expectedLabel = __LABEL_TEXT__;
            const formItemSelector = __FORM_ITEM_SELECTOR__;
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const items = Array.from(document.querySelectorAll(formItemSelector))
                .filter(visible)
                .map((item) => {
                    const label = item.querySelector("label, .el-form-item__label");
                    return {
                        item,
                        labelText: clean(label ? (label.innerText || label.textContent) : ""),
                        text: clean(item.innerText || item.textContent),
                        rect: item.getBoundingClientRect(),
                    };
                })
                .filter(({ labelText, text }) => labelText === expectedLabel || text.startsWith(expectedLabel));
            items.sort((left, right) => {
                const leftExact = left.labelText === expectedLabel ? 0 : 1;
                const rightExact = right.labelText === expectedLabel ? 0 : 1;
                if (leftExact !== rightExact) return leftExact - rightExact;
                return (left.rect.width * left.rect.height) - (right.rect.width * right.rect.height);
            });
            return items[0]?.item || null;
        })
        """.replace("__LABEL_TEXT__", repr(label_text)).replace(
            "__FORM_ITEM_SELECTOR__",
            repr(self.locator("form_item")),
        )

    def _packet_capture_blocking_exists_script(self) -> str:
        return """
        () => Boolean((() => {
            const root = __PACKET_CAPTURE_ROOT__();
            return root && root.querySelector(__SWITCH_SELECTOR__);
        })())
        """.replace("__PACKET_CAPTURE_ROOT__", self._packet_capture_blocking_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _packet_capture_blocking_switch_center_script(self) -> str:
        return """
        () => {
            const switchSelector = __SWITCH_SELECTOR__;
            const root = __PACKET_CAPTURE_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(switchSelector);
            if (!switchEl) return null;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            return {
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                width: rect.width,
                height: rect.height,
                className: String(switchEl.className || ""),
            };
        }
        """.replace("__PACKET_CAPTURE_ROOT__", self._packet_capture_blocking_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _packet_capture_blocking_switch_dom_click_script(self) -> str:
        return """
        () => {
            const switchSelector = __SWITCH_SELECTOR__;
            const root = __PACKET_CAPTURE_ROOT__();
            if (!root) return false;
            const switchEl = root.querySelector(switchSelector);
            if (!switchEl) return false;
            const core = switchEl.querySelector(__SWITCH_CORE_SELECTOR__) || switchEl;
            core.scrollIntoView({ block: "center", inline: "center" });
            const rect = core.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return false;
            const eventOptions = { bubbles: true, cancelable: true, view: window };
            core.dispatchEvent(new MouseEvent("mouseover", eventOptions));
            core.dispatchEvent(new MouseEvent("mousemove", eventOptions));
            core.dispatchEvent(new MouseEvent("mousedown", eventOptions));
            core.dispatchEvent(new MouseEvent("mouseup", eventOptions));
            core.click();
            return true;
        }
        """.replace("__PACKET_CAPTURE_ROOT__", self._packet_capture_blocking_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        ).replace(
            "__SWITCH_CORE_SELECTOR__",
            repr(self.locator("switch_core")),
        )

    def _packet_capture_blocking_enabled_script(self) -> str:
        return """
        () => {
            const switchSelector = __SWITCH_SELECTOR__;
            const root = __PACKET_CAPTURE_ROOT__();
            if (!root) return null;
            const switchEl = root.querySelector(switchSelector);
            if (!switchEl) return null;
            const input = switchEl.querySelector("input");
            const ariaChecked = switchEl.getAttribute("aria-checked");
            if (ariaChecked === "true") return true;
            if (ariaChecked === "false") return false;
            return switchEl.classList.contains("is-checked") || Boolean(input?.checked);
        }
        """.replace("__PACKET_CAPTURE_ROOT__", self._packet_capture_blocking_root_function()).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _packet_capture_process_input_script(self) -> str:
        return """
        () => {
            const root = __PACKET_CAPTURE_ROOT__();
            if (!root) return null;
            const input = __PACKET_CAPTURE_PROCESS_INPUT__(root);
            if (!input) return null;
            input.scrollIntoView({ block: "center", inline: "center" });
            return input;
        }
        """.replace("__PACKET_CAPTURE_ROOT__", self._packet_capture_blocking_root_function()).replace(
            "__PACKET_CAPTURE_PROCESS_INPUT__",
            self._packet_capture_process_input_function(),
        )

    def _packet_capture_process_value_script(self) -> str:
        return """
        () => {
            const root = __PACKET_CAPTURE_ROOT__();
            if (!root) return null;
            const input = __PACKET_CAPTURE_PROCESS_INPUT__(root);
            return input ? String(input.value || "") : null;
        }
        """.replace("__PACKET_CAPTURE_ROOT__", self._packet_capture_blocking_root_function()).replace(
            "__PACKET_CAPTURE_PROCESS_INPUT__",
            self._packet_capture_process_input_function(),
        )

    def _packet_capture_blocking_root_function(self) -> str:
        return """
        (() => {
            const formItemSelector = __FORM_ITEM_SELECTOR__;
            const switchSelector = __SWITCH_SELECTOR__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(formItemSelector))
                .filter(visible)
                .filter((el) => clean(el.innerText || el.textContent).includes("禁用抓包软件"))
                .filter((el) => el.querySelector(switchSelector))
                .sort((left, right) => {
                    const leftText = clean(left.innerText || left.textContent);
                    const rightText = clean(right.innerText || right.textContent);
                    const leftScore = leftText.startsWith("禁用抓包软件") ? 0 : 1;
                    const rightScore = rightText.startsWith("禁用抓包软件") ? 0 : 1;
                    if (leftScore !== rightScore) return leftScore - rightScore;
                    const leftRect = left.getBoundingClientRect();
                    const rightRect = right.getBoundingClientRect();
                    return (leftRect.width * leftRect.height) - (rightRect.width * rightRect.height);
            });
            return candidates[0] || null;
        })
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__SWITCH_SELECTOR__",
            repr(self.locator("switch")),
        )

    def _packet_capture_process_input_function(self) -> str:
        return """
        ((root) => {
            const formItemSelector = __FORM_ITEM_SELECTOR__;
            const editableFieldSelector = __EDITABLE_FIELD_SELECTOR__;
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const rootRect = root.getBoundingClientRect();
            const rootContainer = root.parentElement || root;
            const editableField = (field) => {
                const tag = String(field.tagName || "").toLowerCase();
                const type = String(field.getAttribute("type") || "").toLowerCase();
                if (field.disabled || field.readOnly) return false;
                if (tag === "textarea") return true;
                return tag === "input" && !["checkbox", "radio", "hidden"].includes(type);
            };
            const directInput = Array.from(root.querySelectorAll(editableFieldSelector))
                .filter(visible)
                .filter(editableField)
                .find((input) => {
                    const placeholder = clean(input.getAttribute("placeholder"));
                    return placeholder.includes("软件名称") || placeholder.includes("进程") || placeholder.includes("请输入");
                });
            if (directInput) return directInput;

            const scopedItems = Array.from(rootContainer.querySelectorAll(formItemSelector))
                .filter(visible)
                .map((item) => ({ item, rect: item.getBoundingClientRect(), text: clean(item.innerText || item.textContent) }))
                .filter(({ rect }) => rect.y >= rootRect.y - 5 && rect.y <= rootRect.y + 360);
            for (const { item, text } of scopedItems) {
                if (!text.includes("软件名称") && !text.includes("进程名称") && !text.includes("抓包")) continue;
                const input = Array.from(item.querySelectorAll(editableFieldSelector)).filter(visible).filter(editableField)[0];
                if (input) return input;
            }

            const nearbyInputs = Array.from(rootContainer.querySelectorAll(editableFieldSelector))
                .filter(visible)
                .filter(editableField)
                .map((input) => ({ input, rect: input.getBoundingClientRect(), placeholder: clean(input.getAttribute("placeholder")) }))
                .filter(({ rect }) => rect.y >= rootRect.y - 5 && rect.y <= rootRect.y + 360)
                .sort((left, right) => left.rect.y - right.rect.y);
            return nearbyInputs.find(({ placeholder }) => placeholder.includes("软件名称") || placeholder.includes("进程"))
                ?.input || nearbyInputs[0]?.input || null;
        })
        """.replace("__FORM_ITEM_SELECTOR__", repr(self.locator("form_item"))).replace(
            "__EDITABLE_FIELD_SELECTOR__",
            repr(self.locator("editable_field_candidates")),
        )

    def _visible_text_element_script(self, locator_name: str, text: str, exact: bool = False) -> str:
        return f"""
        () => {{
            const selector = {self.locator(locator_name)!r};
            const expectedText = {text!r};
            const exact = {str(exact).lower()};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const clean = (el) => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(selector))
                .filter((el) => visible(el))
                .filter((el) => exact ? clean(el) === expectedText : clean(el).includes(expectedText))
                .map((el) => {{
                    const rect = el.getBoundingClientRect();
                    return {{ el, rect, area: rect.width * rect.height }};
                }})
                .sort((left, right) => left.area - right.area);
            return candidates[0]?.el || null;
        }}
        """

    def _visible_button_by_text_script(self, text: str) -> str:
        return f"""
        () => {{
            const selector = {self.locator("button")!r};
            const expectedText = {text!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const buttons = Array.from(document.querySelectorAll(selector))
                .filter((button) => visible(button))
                .filter((button) => (button.innerText || button.textContent || "").trim() === expectedText)
                .map((button) => {{
                    const rect = button.getBoundingClientRect();
                    return {{ button, rect }};
                }})
                .sort((left, right) => (right.rect.y - left.rect.y) || (right.rect.x - left.rect.x));
            return buttons[0]?.button || null;
        }}
        """

    def _active_dialog_button_script(self, text: str) -> str:
        return f"""
        () => {{
            const expectedText = {text!r};
            const visible = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && rect.width > 0
                    && rect.height > 0;
            }};
            const overlays = Array.from(document.querySelectorAll(__DIALOG_OR_MESSAGE_BOX_SELECTOR__))
                .filter(visible);
            for (const overlay of overlays.reverse()) {{
                const button = Array.from(overlay.querySelectorAll("button"))
                    .filter(visible)
                    .find((item) => (item.innerText || item.textContent || "").trim() === expectedText);
                if (button) return button;
            }}
            return null;
        }}
        """.replace("__DIALOG_OR_MESSAGE_BOX_SELECTOR__", repr(self.locator("dialog_or_message_box")))

    @classmethod
    def _canonical_environment_field(cls, text: str) -> str:
        clean = (
            str(text or "")
            .replace("升序", "")
            .replace("降序", "")
            .replace("排序", "")
            .replace("▲", "")
            .replace("▼", "")
            .strip()
        )
        compact = "".join(clean.split())
        for canonical, aliases in cls._ENVIRONMENT_FIELD_ALIASES.items():
            if any(compact == alias or compact.find(alias) >= 0 for alias in aliases):
                return canonical
        return clean
