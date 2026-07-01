from __future__ import annotations

import time
from pathlib import Path

from core.config import timeout_seconds as config_timeout_seconds
from pages.base_page import BasePage


class GlobalSettingsPage(BasePage):
    locator_file = "global_settings_locators.yaml"
    DISABLE_DEVTOOLS_LABELS = ("禁止打开浏览器开发者工具", "禁止打开浏览器开发者工具界面")
    ENVIRONMENT_FIELD_DISPLAY_LIMIT_LABELS = ("环境列表字段权限", "环境字段显示限制")
    ENVIRONMENT_FIELD_DISPLAY_LIMIT_DIALOG_TITLES = ("列表字段", "列表字段设置")
    GOOGLE_EXTENSION_SHORTCUT_LABELS = ("Chrome 应用商店", "谷歌应用商店")
    _ENVIRONMENT_FIELD_ALIASES = {
        "环境序号": ("环境序号", "序号"),
        "环境名称": ("环境名称", "名称"),
        "环境分组": ("环境分组", "分组"),
        "备注": ("备注",),
        "标签": ("标签",),
        "升序": ("升序",),
        "降序": ("降序",),
    }

    def open(self) -> None:
        self._dismiss_blocking_overlays()
        self.cdp.click_element_by_script(
            self._visible_text_element_script("global_settings_menu_candidates", "全局设置", exact=True)
        )
        self._wait_for_global_settings_page()

    def ensure_disable_view_password_enabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_enabled("禁止查看网站密码")

    def ensure_disable_devtools_enabled(self) -> bool:
        """Return True when this method changed the setting."""
        return self.ensure_checkbox_enabled(self.DISABLE_DEVTOOLS_LABELS)

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

    def configure_packet_capture_blocking(self, process_name: str) -> None:
        """Enable packet capture blocking and save the configured process name."""
        clean_process_name = str(process_name or "").strip()
        if not clean_process_name:
            raise ValueError("packet capture process name must not be empty")

        self._wait_for_packet_capture_blocking()
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
            self._wait_save_finished()
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
            self._wait_save_finished()
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

    def configure_environment_field_display_limit(self, field_names: list[str]) -> None:
        """Enable environment field display limit, select exact fields, and save."""
        clean_fields = [str(item).strip() for item in field_names if str(item).strip()]
        if not clean_fields:
            raise ValueError("environment field display limit requires at least one field")

        self._wait_for_environment_field_display_limit()
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
            self._wait_save_finished()
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

    def configure_environment_list_pagination_setting(self, page_size_text: str = "20 条/页") -> None:
        """Enable environment list pagination setting, select page size, and save."""
        clean_page_size = str(page_size_text or "").replace(" ", "").strip()
        if not clean_page_size:
            raise ValueError("environment list pagination setting requires a page size")

        self._wait_for_environment_list_pagination_setting()
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
            self._wait_save_finished()
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

    def configure_environment_list_sort(self, field_text: str, direction_text: str) -> None:
        """Enable environment list sort limit, choose field/direction, and save."""
        clean_field = str(field_text or "").strip()
        clean_direction = str(direction_text or "").strip()
        if not clean_field:
            raise ValueError("environment list sort requires a sort field")
        if clean_direction not in {"升序", "降序"}:
            raise ValueError(f"unsupported environment list sort direction: {clean_direction}")

        self._wait_for_environment_list_sort()
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
            self._wait_save_finished()
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

    def configure_website_restriction_blocklist(
        self,
        urls: list[str],
        shortcut_name: str = "Chrome 应用商店",
    ) -> None:
        """Enable website restriction and save a blocklist with a shortcut option."""
        self._wait_for_website_restriction()
        shortcut_names = self._website_shortcut_candidates(shortcut_name)
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
            self._wait_save_finished()
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
        marker_selector = self.locator("global_settings_page_marker")
        while time.time() < deadline:
            if self.cdp.evaluate(
                """
                () => {
                    const marker = document.querySelector(__MARKER_SELECTOR__);
                    const text = marker ? (marker.innerText || marker.textContent || "") : "";
                    return text.includes("全局设置") && text.includes("禁止查看网站密码");
                }
                """.replace("__MARKER_SELECTOR__", repr(marker_selector))
            ):
                return
            time.sleep(0.2)
        raise TimeoutError("global settings page did not appear")

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

    def _wait_for_checkbox(self, label_text: str, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.cdp.evaluate(self._checkbox_exists_script(label_text)):
                return
            time.sleep(0.2)
        raise TimeoutError(f"{label_text} checkbox did not appear")

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

    def _wait_save_finished(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self._has_visible_loading():
                return
            time.sleep(0.2)
        raise TimeoutError("global settings save did not finish")

    def _wait_until_not_loading(self, timeout_seconds: int | None = None) -> None:
        timeout_seconds = timeout_seconds or config_timeout_seconds(self.config, "page_seconds", 10)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self._has_visible_loading():
                return
            time.sleep(0.2)
        raise TimeoutError("global settings page still has visible loading mask")

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
                            const rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        };
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
