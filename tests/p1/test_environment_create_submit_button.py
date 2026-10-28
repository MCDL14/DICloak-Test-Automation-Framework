from __future__ import annotations

import unittest

from pages.environment_page import EnvironmentPage


PAGE_STYLE = """
<style>
  .el-drawer, .el-dialog { display:block; width:760px; min-height:180px; }
  .el-drawer__header, .el-dialog__header { display:block; height:30px; }
  button { display:inline-block; min-width:36px; min-height:30px; }
</style>
"""


def _drawer(body: str, *, title: str = "创建环境", drawer_id: str = "create-drawer") -> str:
    return f"""
      <section class="el-drawer" id="{drawer_id}">
        <header class="el-drawer__header"><h4>{title}</h4></header>
        <div class="el-drawer__body">{body}</div>
      </section>
    """


SPLIT_BUTTON = """
  <div class="tw-relative tw-inline-flex">
    <button id="create-submit" data-testid="create-env">创建环境</button>
    <button id="preferences-toggle" data-testid="create-env-preferences-toggle"
            aria-label="选择要保存的偏好"><svg width="12" height="12"></svg></button>
  </div>
"""


class EnvironmentCreateSubmitButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise unittest.SkipTest("playwright is not installed") from exc
        cls._playwright = sync_playwright().start()
        try:
            cls._browser = cls._playwright.chromium.launch(headless=True)
        except Exception as exc:
            cls._playwright.stop()
            raise unittest.SkipTest(f"playwright chromium is not available: {exc}") from exc

    @classmethod
    def tearDownClass(cls) -> None:
        cls._browser.close()
        cls._playwright.stop()

    def setUp(self) -> None:
        self.browser_page = self._browser.new_page(viewport={"width": 1100, "height": 900})
        self.page = EnvironmentPage(cdp_driver=self.browser_page, config={})

    def tearDown(self) -> None:
        self.browser_page.close()

    def _content(self, html: str) -> None:
        self.browser_page.set_content(f"<html><head>{PAGE_STYLE}</head><body>{html}</body></html>")

    def _target_id(self) -> str | None:
        handle = self.browser_page.evaluate_handle(self.page._create_environment_submit_button_script())
        return handle.evaluate("el => el ? el.id : null")

    def _state(self) -> dict:
        return self.browser_page.evaluate(self.page._create_environment_submit_button_state_script())

    def test_new_split_button_uses_primary_without_standard_footer(self) -> None:
        self._content(_drawer(SPLIT_BUTTON))

        self.assertEqual(self._target_id(), "create-submit")
        state = self._state()
        self.assertTrue(state["visible"])
        self.assertEqual(state["text"], "创建环境")
        self.assertFalse(state["loading"])
        self.assertFalse(state["disabled"])

    def test_hidden_old_drawer_and_background_create_entry_are_ignored(self) -> None:
        self._content(
            '<button id="background-entry" data-testid="create-env">创建环境</button>'
            + '<div style="display:none">'
            + _drawer('<button id="stale-submit" data-testid="create-env">创建环境</button>', drawer_id="stale")
            + "</div>"
            + _drawer(SPLIT_BUTTON)
        )

        self.assertEqual(self._target_id(), "create-submit")

    def test_non_create_overlay_cannot_supply_a_submit_button(self) -> None:
        self._content(_drawer('<button id="edit-confirm">确定</button>', title="编辑环境"))

        self.assertIsNone(self._target_id())
        self.assertFalse(self._state()["visible"])

    def test_background_create_entry_cannot_supply_a_submit_button(self) -> None:
        self._content('<button id="background-entry" data-testid="create-env">创建环境</button>')

        self.assertIsNone(self._target_id())
        self.assertFalse(self._state()["visible"])

    def test_similarly_named_group_dialog_is_not_an_environment_create(self) -> None:
        for title in ("创建环境分组", "批量创建分组"):
            with self.subTest(title=title):
                self._content(
                    '<section class="el-dialog"><header class="el-dialog__header">'
                    + title
                    + '</header><button id="group-confirm">确定</button></section>'
                )
                self.assertIsNone(self._target_id())
                self.assertFalse(self._state()["visible"])

    def test_old_drawer_confirm_text_remains_supported(self) -> None:
        self._content(_drawer('<button>取消</button><button id="old-submit">确定</button>'))

        self.assertEqual(self._target_id(), "old-submit")
        self.assertEqual(self._state()["text"], "确定")

    def test_create_text_fallback_works_without_test_id(self) -> None:
        self._content(_drawer('<button>取消</button><button id="text-submit">创建环境</button>'))

        self.assertEqual(self._target_id(), "text-submit")

    def test_batch_create_dialog_confirm_remains_supported(self) -> None:
        self._content(
            '<section class="el-dialog"><header class="el-dialog__header"><h4>批量创建</h4></header>'
            '<div class="el-dialog__body"><button id="batch-submit">确定</button></div></section>'
        )

        self.assertEqual(self._target_id(), "batch-submit")

    def test_stable_test_id_wins_over_legacy_confirm_text(self) -> None:
        self._content(_drawer('<button id="unrelated-confirm">确定</button>' + SPLIT_BUTTON))

        self.assertEqual(self._target_id(), "create-submit")

    def test_preferences_toggle_is_excluded_from_text_fallback(self) -> None:
        self._content(
            _drawer(
                '<button id="preferences-toggle" data-testid="create-env-preferences-toggle">创建环境</button>'
                '<button id="legacy-submit">确定</button>'
            )
        )

        self.assertEqual(self._target_id(), "legacy-submit")

    def test_nested_dialog_confirm_is_not_a_drawer_submit_candidate(self) -> None:
        self._content(
            _drawer(
                '<section class="el-dialog"><header class="el-dialog__header">保存偏好</header>'
                '<button id="nested-confirm">确定</button></section>'
            )
        )

        self.assertIsNone(self._target_id())

    def test_nested_dialog_confirm_does_not_replace_primary_submit(self) -> None:
        self._content(
            _drawer(
                SPLIT_BUTTON
                + '<section class="el-dialog"><header class="el-dialog__header">保存偏好</header>'
                '<button id="nested-confirm">确定</button></section>'
            )
        )

        self.assertEqual(self._target_id(), "create-submit")

    def test_loading_state_is_read_from_same_new_primary_button(self) -> None:
        self._content(_drawer(SPLIT_BUTTON))
        self.browser_page.locator("#preferences-toggle").evaluate("el => el.classList.add('is-loading')")
        self.assertFalse(self._state()["loading"])

        self.browser_page.locator("#create-submit").evaluate("el => el.classList.add('is-loading')")

        self.assertEqual(self._target_id(), "create-submit")
        self.assertTrue(self._state()["loading"])

    def test_disabled_property_and_loading_icon_are_reported(self) -> None:
        self._content(_drawer(SPLIT_BUTTON))
        self.browser_page.locator("#create-submit").evaluate(
            "el => { el.disabled = true; el.insertAdjacentHTML('afterbegin', '<i class=\"el-icon is-loading\"></i>'); }"
        )

        state = self._state()
        self.assertTrue(state["disabled"])
        self.assertTrue(state["loading"])

    def test_loading_and_disabled_element_plus_classes_are_reported(self) -> None:
        self._content(_drawer('<button id="old-submit" class="is-loading is-disabled">确定</button>'))

        state = self._state()
        self.assertTrue(state["loading"])
        self.assertTrue(state["disabled"])

    def test_accessibility_busy_and_disabled_flags_are_reported(self) -> None:
        self._content(_drawer(SPLIT_BUTTON))
        self.browser_page.locator("#create-submit").evaluate(
            "el => { el.setAttribute('aria-busy', 'true'); el.setAttribute('aria-disabled', 'true'); }"
        )

        state = self._state()
        self.assertTrue(state["loading"])
        self.assertTrue(state["disabled"])
        self.assertEqual(state["ariaDisabled"], "true")

    def test_public_state_reader_uses_new_submit_state_script(self) -> None:
        self._content(_drawer(SPLIT_BUTTON))

        state = self.page._create_environment_submit_button_state()

        self.assertEqual(state, self._state())
        self.assertEqual(state["text"], "创建环境")


if __name__ == "__main__":
    unittest.main()
