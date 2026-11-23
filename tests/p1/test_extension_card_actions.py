from __future__ import annotations

import logging
import unittest
from unittest import mock

from core.cdp_driver import CDPDriver
from pages.extension_page import ExtensionPage


CARD_MENU_HTML = """
<html>
  <head>
    <style>
      body { margin:0; }
      .el-card { position:absolute; top:40px; width:340px; height:240px;
                 border:1px solid #444; }
      #card-target { left:40px; }
      #card-other { left:420px; }
      .header { padding:20px; }
      .el-dropdown { position:absolute; right:12px; top:16px; width:24px; height:24px; }
      .el-dropdown > i { display:block; width:24px; height:24px; cursor:pointer; }
      .description { position:absolute; top:90px; left:20px; width:290px; height:70px; }
      .provider { position:absolute; bottom:12px; left:20px; }
      #description-tooltip { position:fixed; left:35px; top:48px; width:355px;
                             height:75px; background:#eee; z-index:50; display:none; }
      .el-dropdown__popper { position:fixed; width:130px; background:#eee;
                             z-index:80; display:none; }
      .el-dropdown-menu { padding:0; margin:0; list-style:none; width:130px; }
      .el-dropdown-menu__item { box-sizing:border-box; width:130px; height:32px;
                               padding:6px 16px; cursor:pointer; }
      #stale-popup { display:block; left:800px; top:40px; }
    </style>
  </head>
  <body>
    <div id="card-target" class="el-card">
      <div class="header"><div class="tw-font-medium">目标扩展</div><div>1.0.0</div>
        <div class="el-dropdown">
          <i id="trigger-target" class="el-tooltip__trigger" role="button"
             aria-haspopup="menu" aria-controls="menu-target" aria-expanded="false">⋮</i>
        </div>
      </div>
      <p id="description-target" class="description el-tooltip__trigger">目标扩展详情</p>
      <div class="provider"><span>提供方:</span><button id="provider-target">DICloak</button></div>
    </div>
    <div id="card-other" class="el-card">
      <div class="header"><div class="tw-font-medium">目标扩展-副本</div><div>2.0.0</div>
        <div class="el-dropdown">
          <i id="trigger-other" class="el-tooltip__trigger" role="button"
             aria-haspopup="menu" aria-controls="menu-other" aria-expanded="false">⋮</i>
        </div>
      </div>
      <p class="description">其他扩展详情</p>
      <div class="provider"><span>提供方:</span><button>DICloak</button></div>
    </div>
    <div id="description-tooltip" class="el-popper is-dark" role="tooltip">目标扩展详情气泡</div>
    <div id="popup-target" class="el-popper el-dropdown__popper" role="tooltip" aria-hidden="true">
      <ul id="menu-target" class="el-dropdown-menu" role="menu" aria-labelledby="trigger-target">
        <li id="target-edit" class="el-dropdown-menu__item" role="menuitem">编辑</li>
        <li id="target-delete" class="el-dropdown-menu__item" role="menuitem">删除</li>
      </ul>
    </div>
    <div id="popup-other" class="el-popper el-dropdown__popper" role="tooltip" aria-hidden="true">
      <ul id="menu-other" class="el-dropdown-menu" role="menu" aria-labelledby="trigger-other">
        <li class="el-dropdown-menu__item" role="menuitem">编辑</li>
        <li class="el-dropdown-menu__item" role="menuitem">删除</li>
      </ul>
    </div>
    <div id="stale-popup" class="el-popper el-dropdown__popper" role="tooltip" aria-hidden="false">
      <ul id="stale-menu" class="el-dropdown-menu" role="menu" aria-labelledby="stale-trigger">
        <li class="el-dropdown-menu__item" role="menuitem">删除</li>
        <li class="el-dropdown-menu__item" role="menuitem">编辑</li>
      </ul>
    </div>
    <script>
      window.actions = [];
      window.triggerClicks = [];
      window.providerClicks = 0;
      window.blockedMenus = new Set();
      window.leavingMenus = new Set();
      const timers = {};
      const tip = document.getElementById('description-tooltip');
      const description = document.getElementById('description-target');
      description.addEventListener('mouseenter', () => { tip.style.display = 'block'; });
      description.addEventListener('mouseleave', () => {
        setTimeout(() => { tip.style.display = 'none'; }, 80);
      });
      document.getElementById('provider-target').addEventListener('click', () => { window.providerClicks++; });
      const hide = key => {
        const popup = document.getElementById('popup-' + key);
        popup.style.display = 'none';
        popup.setAttribute('aria-hidden', 'true');
        document.getElementById('trigger-' + key)?.setAttribute('aria-expanded', 'false');
      };
      for (const key of ['target', 'other']) {
        const trigger = document.getElementById('trigger-' + key);
        const popup = document.getElementById('popup-' + key);
        trigger.addEventListener('mouseenter', () => {
          clearTimeout(timers[key]);
          if (window.blockedMenus.has(key)) return;
          const rect = trigger.getBoundingClientRect();
          popup.style.left = rect.left + 'px';
          popup.style.top = (rect.bottom + 4) + 'px';
          popup.style.display = 'block';
          popup.setAttribute('aria-hidden', 'false');
          trigger.setAttribute('aria-expanded', 'true');
          popup.classList.toggle('el-zoom-in-top-leave-active', window.leavingMenus.has(key));
        });
        trigger.addEventListener('mouseleave', () => {
          timers[key] = setTimeout(() => hide(key), 150);
        });
        popup.addEventListener('mouseenter', () => clearTimeout(timers[key]));
        popup.addEventListener('mouseleave', () => {
          timers[key] = setTimeout(() => hide(key), 150);
        });
        trigger.parentElement.addEventListener('click', () => {
          window.triggerClicks.push(key);
          hide(key);
        });
        popup.querySelectorAll('[role="menuitem"]').forEach(item => {
          item.addEventListener('click', () => {
            window.actions.push({card:key, action:item.textContent.trim(),
              leaving:popup.classList.contains('el-zoom-in-top-leave-active')});
            hide(key);
          });
        });
      }
      document.querySelectorAll('#stale-menu [role="menuitem"]').forEach(item => {
        item.addEventListener('click', () => {
          window.actions.push({card:'stale', action:item.textContent.trim(), leaving:false});
        });
      });
    </script>
  </body>
</html>
"""


class ExtensionCardActionTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = _playwright_page()
        self.browser_page = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        self.browser_page.set_content(CARD_MENU_HTML)
        config = {"timeouts": {"script_element_seconds": 1, "page_seconds": 1}}
        driver = CDPDriver(config, logging.getLogger("extension-card-menu-test"))
        driver.page = self.browser_page
        self.extension_page = ExtensionPage(driver, config=config)

    def actions(self):
        return self.browser_page.evaluate("window.actions")

    def test_more_selector_returns_target_menu_trigger(self) -> None:
        target = self.browser_page.evaluate(
            f"""() => {{
              const element = ({self.extension_page._extension_card_more_button_script('目标扩展')})();
              return {{id:element?.id, tag:element?.tagName, controls:element?.getAttribute('aria-controls')}};
            }}"""
        )

        self.assertEqual(target, {"id": "trigger-target", "tag": "I", "controls": "menu-target"})

    def test_delete_moves_away_from_description_tooltip_and_uses_target_menu(self) -> None:
        self.browser_page.locator("#description-target").hover()
        self.browser_page.locator("#description-tooltip").wait_for(state="visible")
        with (
            mock.patch.object(self.extension_page, "_wait_delete_extension_dialog_visible") as dialog,
            mock.patch.object(self.extension_page, "_click_overlay_button_wait_loading_then_closed") as confirm,
            mock.patch.object(self.extension_page, "_wait_for_extension_list_not_loading"),
            mock.patch.object(self.extension_page, "wait_extension_absent") as absent,
        ):
            self.extension_page.delete_extension("目标扩展")

        self.assertEqual(self.actions(), [{"card": "target", "action": "删除", "leaving": False}])
        self.assertFalse(self.browser_page.locator("#description-tooltip").is_visible())
        self.assertEqual(self.browser_page.evaluate("window.triggerClicks"), [])
        dialog.assert_called_once_with()
        confirm.assert_called_once_with("确定")
        absent.assert_called_once_with("目标扩展")

    def test_edit_uses_target_menu_even_with_unrelated_visible_popup(self) -> None:
        with (
            mock.patch.object(self.extension_page, "_wait_for_edit_extension_dialog_visible") as dialog,
            mock.patch.object(self.extension_page, "_wait_for_dialog_extension_groups_ready") as groups,
        ):
            self.extension_page.open_extension_edit_dialog("目标扩展")

        self.assertEqual(self.actions(), [{"card": "target", "action": "编辑", "leaving": False}])
        self.assertEqual(self.browser_page.evaluate("window.triggerClicks"), [])
        dialog.assert_called_once_with()
        groups.assert_called_once_with()

    def test_missing_target_menu_times_out_without_clicking_stale_popup(self) -> None:
        self.browser_page.evaluate("window.blockedMenus.add('target')")

        with self.assertRaises(TimeoutError):
            self.extension_page._open_extension_card_menu_action("目标扩展", "删除")

        self.assertEqual(self.actions(), [])

    def test_menu_labelled_for_another_card_is_not_used(self) -> None:
        self.browser_page.locator("#menu-target").evaluate(
            "el => el.setAttribute('aria-labelledby', 'trigger-other')"
        )

        with self.assertRaises(TimeoutError):
            self.extension_page._open_extension_card_menu_action("目标扩展", "删除")

        self.assertEqual(self.actions(), [])

    def test_waits_until_target_popup_finishes_leaving(self) -> None:
        self.browser_page.evaluate(
            """() => {
              window.leavingMenus.add('target');
              setTimeout(() => {
                window.leavingMenus.delete('target');
                document.getElementById('popup-target').classList.remove('el-zoom-in-top-leave-active');
              }, 300);
            }"""
        )

        self.extension_page._open_extension_card_menu_action("目标扩展", "删除")

        self.assertEqual(self.actions(), [{"card": "target", "action": "删除", "leaving": False}])

    def test_disabled_target_action_does_not_fall_back_to_other_menu(self) -> None:
        self.browser_page.locator("#target-delete").evaluate("el => el.classList.add('is-disabled')")

        with self.assertRaises(TimeoutError):
            self.extension_page._open_extension_card_menu_action("目标扩展", "删除")

        self.assertEqual(self.actions(), [])

    def test_missing_more_trigger_does_not_click_provider_button(self) -> None:
        self.browser_page.locator("#trigger-target").evaluate("el => el.remove()")

        with self.assertRaises(TimeoutError):
            self.extension_page._open_extension_card_menu_action("目标扩展", "删除")

        self.assertEqual(self.actions(), [])
        self.assertEqual(self.browser_page.evaluate("window.providerClicks"), 0)


class _playwright_page:
    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise unittest.SkipTest("playwright is not installed") from exc
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=True)
        except Exception as exc:
            self._playwright.stop()
            raise unittest.SkipTest(f"playwright chromium is not available: {exc}") from exc
        self._page = self._browser.new_page(viewport={"width": 1100, "height": 700})
        return self._page

    def __exit__(self, exc_type, exc, tb):
        self._browser.close()
        self._playwright.stop()


if __name__ == "__main__":
    unittest.main()
