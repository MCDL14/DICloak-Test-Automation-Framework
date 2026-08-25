# Create Existing Proxy Environment Implementation Plan

> **2026-08-25 requirement update:** The implemented case now creates `自动化-使用-已有代理-的环境`, keeps business assertions only for the new `GinsBrowser` process, open/close action-button transitions, and Chrome Web Store connectivity, and treats the remaining creation steps as timeout-based operations. Chrome Web Store assertion failure is delayed until the environment is still closed and deleted. Earlier names and assertion criteria below are retained as historical plan context and are superseded by this update.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Maintain a P0 Environment Management case that creates `自动化-使用-已有代理-的环境`, chooses the first existing proxy matched by `7897`, validates process startup, button-state transitions, and Chrome Web Store connectivity, then closes and deletes only the environment.

**Architecture:** First prove the current DICloak DOM and full lifecycle with a disposable `/tmp` CDP probe. After the probe succeeds, add a narrow existing-proxy selector API to `EnvironmentPage`, define it test-first with a P1 recorder double, and add a P0 business case by reusing the lifecycle and cleanup structure of the custom-proxy case.

**Tech Stack:** Python 3.11, `unittest`, Playwright over Electron CDP, existing `CDPDriver`, `EnvironmentPage`, `core.process`, and the project P0 runner.

---

## File map

- Create temporarily: `/tmp/dicloak_existing_proxy_environment_probe.py` — disposable live-DOM and full-lifecycle probe; never added to Git.
- Modify: `pages/environment_page.py` — existing-proxy selector visibility, search, first-result selection, selected-text reading, and synchronization.
- Create: `tests/p1/test_environment_existing_proxy_drawer.py` — fast contract tests for the new page-object API.
- Create: `tests/p0/environment_management/test_43_create_environment_with_existing_proxy.py` — requested P0 Environment Management business case.

### Task 1: Verify the current live UI with a disposable probe

**Files:**
- Create temporarily: `/tmp/dicloak_existing_proxy_environment_probe.py`

- [ ] **Step 1: Confirm DICloak CDP is reachable**

Run:

```bash
curl -fsS http://127.0.0.1:9222/json/version
```

Expected: exit code `0` and JSON containing browser/CDP metadata. If unavailable, launch `/Applications/DICloak.app` with remote debugging on port `9222`, then repeat.

- [ ] **Step 2: Inspect the existing-proxy control without repository changes**

Create a disposable probe using the existing driver and page objects:

```python
from pathlib import Path

from core.app_config import resolve_app_config
from core.cdp_driver import CDPDriver
from core.config import load_config, timeout_seconds
from core.logger import setup_logger
from core.process import main_process_ids, wait_for_new_main_process_ids
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage

ENVIRONMENT_NAME = "测试已有代理"
PROXY_SEARCH_TEXT = "7897"
OPEN_TIMEOUT_SECONDS = 60
```

The probe must connect to the current app, enter Environment Management, remove only a stale exact-name `测试已有代理` environment, open the create drawer, select `已有代理`, and print only non-sensitive control metadata:

```text
placeholder
input value
visible dropdown item count
first dropdown item text
selected display text
```

It must never print credentials, cookies, tokens, launch command lines, webhook URLs, API keys, or the full config.

- [ ] **Step 3: Complete the full lifecycle in the disposable probe**

The temporary DOM interaction must:

```python
# Locate the right-hand .el-select by its displayed .el-select__placeholder text.
# The nested input[role="combobox"] has an empty placeholder attribute.
EXISTING_PROXY_PLACEHOLDER = "请选择已有代理"

# Click the input, fill the search text through CDPDriver.fill_element_by_script,
# wait for a visible, enabled .el-select-dropdown__item, then click the first item.
# After the click, wait until the visible dropdown closes and read non-empty
# selected display text from the same select component.
```

Then save, search for `测试已有代理`, capture existing `GinsBrowser` main PIDs, open the environment, wait up to 60 seconds for a new PID, close and confirm, delete only the environment, and check no exact-name residue remains.

Run:

```bash
.venv/bin/python /tmp/dicloak_existing_proxy_environment_probe.py
```

Expected sequence:

```text
create_button={visible: True, enabled: True}
drawer_visible=True
environment_name=测试已有代理
existing_proxy_select_visible=True
matching_option_count=2
first_option_text=SOCKS5://127.0.0.1:7897 IP: 103.172.183.85 (SG - Singapore) 序号:604 | 已绑0个
selected_proxy_text=SOCKS5://127.0.0.1:7897 (序号:604 | 已绑0个)
environment_visible=True
new_ginsbrowser_pids=[<positive pid>]
environment_closed=True
exists_after_delete=False
cleanup=completed
```

If the dropdown DOM differs, change only the disposable probe and rerun from a clean state. Do not modify repository page objects or tests until the complete sequence reaches `cleanup=completed`.

### Task 2: Define the existing-proxy page API with failing tests

**Files:**
- Create: `tests/p1/test_environment_existing_proxy_drawer.py`
- Test: `tests/p1/test_environment_existing_proxy_drawer.py`

- [ ] **Step 1: Create a recorder double and tests for the desired API**

The recorder double subclasses `EnvironmentPage`, provides `self.cdp = self`, and records low-level calls. Add these tests before production code:

```python
class EnvironmentExistingProxyDrawerTests(unittest.TestCase):
    def test_existing_proxy_select_visibility_uses_displayed_placeholder_text(self) -> None:
        page = _ExistingProxyDrawerProbe()

        self.assertTrue(page.create_environment_existing_proxy_select_visible())
        self.assertEqual(page.calls, [("select-visible", "请选择已有代理")])

    def test_existing_proxy_select_visibility_waits_for_async_render(self) -> None:
        page = _ExistingProxyDrawerProbe(visible_sequence=[False, False, True])

        self.assertTrue(page.create_environment_existing_proxy_select_visible())
        self.assertEqual(len(page.calls), 3)

    def test_searches_right_hand_existing_proxy_select_and_chooses_first_result(self) -> None:
        page = _ExistingProxyDrawerProbe()

        selected_text = page.select_first_create_environment_existing_proxy("7897")

        self.assertEqual(
            selected_text,
            "SOCKS5://127.0.0.1:7897 (序号:604 | 已绑0个)",
        )
        self.assertEqual(
            page.calls,
            [
                ("input-script", "请选择已有代理"),
                ("control-id", "existing-proxy-input"),
                ("click-search-input", "existing-proxy-input"),
                ("fill-search-input", ("existing-proxy-input", "7897")),
                ("wait-first-option", None),
                ("first-option-script", None),
                ("click-first-option", "first-existing-proxy-option"),
                ("wait-dropdown-closed", None),
                ("wait-selected-text", "existing-proxy-listbox"),
            ],
        )
```

The probe overrides the displayed-placeholder select locator, async visibility sequence, exact select search-input locator, `aria-controls` reader, dropdown-item wait/click, dropdown-close wait, and selected-text wait so the tests verify orchestration without opening DICloak.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.p1.test_environment_existing_proxy_drawer -v
```

Expected: FAIL/ERROR because `EnvironmentPage` does not define `create_environment_existing_proxy_select_visible` and `select_first_create_environment_existing_proxy`. Confirm the failure is the missing API, not an import or syntax error.

### Task 3: Implement the minimal EnvironmentPage API

**Files:**
- Modify: `pages/environment_page.py`
- Test: `tests/p1/test_environment_existing_proxy_drawer.py`

- [ ] **Step 1: Add the public selector operations**

Add these methods near the existing create-environment proxy methods:

```python
def create_environment_existing_proxy_select_visible(self) -> bool:
    deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
    while time.time() < deadline:
        if self._active_drawer_select_visible_by_placeholder_text("请选择已有代理"):
            return True
        time.sleep(0.2)
    return False

def select_first_create_environment_existing_proxy(self, search_text: str) -> str:
    input_script = self._active_drawer_select_search_input_by_placeholder_text_script(
        "请选择已有代理"
    )
    control_id = self._select_search_input_control_id(input_script)
    self.cdp.click_element_by_script(input_script)
    self.cdp.fill_element_by_script(input_script, search_text)
    self._wait_first_visible_enabled_select_dropdown_item()
    self.cdp.click_element_by_script(
        self._first_visible_enabled_select_dropdown_item_script()
    )
    self._wait_select_dropdown_closed()
    return self._wait_create_environment_existing_proxy_selected_text(control_id)
```

The live probe proved the order `click → fill`, the exact right-hand component scope, and the `aria-controls` identity used after the placeholder disappears.

- [ ] **Step 2: Add only the private DOM helpers required by the public API**

Implement `_active_drawer_select_visible_by_placeholder_text`, `_active_drawer_select_by_placeholder_text_script`, `_active_drawer_select_search_input_by_placeholder_text_script`, `_select_search_input_control_id`, `_wait_first_visible_enabled_select_dropdown_item`, `_first_visible_enabled_select_dropdown_item_script`, `_create_environment_existing_proxy_selected_text`, `_active_drawer_select_selected_text_by_control_id_script`, and `_wait_create_environment_existing_proxy_selected_text` with the project's existing visibility and polling conventions. The core waits and selected-text reader are:

```python
def _wait_first_visible_enabled_select_dropdown_item(self) -> None:
    finder = self._first_visible_enabled_select_dropdown_item_script()
    deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
    while time.time() < deadline:
        if self.cdp.evaluate(
            f"""
            () => {{
                const findItem = {finder};
                return Boolean(findItem());
            }}
            """
        ):
            return
        time.sleep(0.2)
    raise TimeoutError("no visible enabled existing-proxy dropdown item appeared")

def _first_visible_enabled_select_dropdown_item_script(self) -> str:
    return """
    () => {
        const visible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== "none"
                && style.visibility !== "hidden"
                && rect.width > 0
                && rect.height > 0;
        };
        const poppers = Array.from(document.querySelectorAll(
            ".el-select__popper, .el-select-dropdown, .el-popper"
        )).filter(visible);
        for (const popper of poppers.reverse()) {
            const item = Array.from(popper.querySelectorAll(".el-select-dropdown__item"))
                .find((el) => visible(el)
                    && !el.classList.contains("is-disabled")
                    && el.getAttribute("aria-disabled") !== "true");
            if (item) return item;
        }
        return null;
    }
    """

def _active_drawer_select_selected_text_by_control_id_script(
    self,
    control_id: str,
) -> str:
    return f"""
    () => {{
        const expectedControlId = {control_id!r};
        const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
        const visible = (el) => {{
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== "none"
                && style.visibility !== "hidden"
                && rect.width > 0
                && rect.height > 0;
        }};
        const drawers = Array.from(document.querySelectorAll(".el-drawer")).filter(visible);
        for (const drawer of drawers.reverse()) {{
            const input = Array.from(drawer.querySelectorAll('input[role="combobox"]'))
                .find((candidate) =>
                    candidate.getAttribute("aria-controls") === expectedControlId
                );
            if (!input) continue;
            const select = input.closest(".el-select");
            if (!select) continue;
            const selected = Array.from(select.querySelectorAll(
                ".el-select__selected-item, .el-select__selected-item span"
            ))
                .filter(visible)
                .map((el) => clean(el.innerText || el.textContent))
                .find(Boolean);
            if (selected) return selected;
        }}
        return "";
    }}
    """

def _wait_create_environment_existing_proxy_selected_text(self, control_id: str) -> str:
    deadline = time.time() + config_timeout_seconds(self.config, "page_seconds", 10)
    while time.time() < deadline:
        selected_text = self._create_environment_existing_proxy_selected_text(control_id)
        if selected_text:
            return selected_text
        time.sleep(0.2)
    raise TimeoutError("existing proxy did not become selected")
```

Required DOM rules:

- Select component: displayed `.el-select__placeholder` text exactly equals `请选择已有代理`; do not inspect the nested input's empty placeholder attribute.
- Search input: obtain the `input[role="combobox"]` only from that exact right-hand select and capture its `aria-controls` before selection, so the left【代理分组】select cannot be chosen.
- Result item: the first visible `.el-select-dropdown__item` in a visible Element Plus popper, excluding `.is-disabled` and nodes with `aria-disabled="true"`.
- Selected text: after the displayed placeholder disappears, find the original input by captured `aria-controls`, then require non-empty visible text from its `.el-select__selected-item` after the dropdown has closed. Never fall back to the uncommitted search input value.
- Never use a global list item by ordinal without first restricting to the visible select dropdown.
- `_wait_create_environment_existing_proxy_selected_text` polls until the component reports non-empty selected text and returns that text.
- All waits use the existing `page_seconds` timeout and 0.2-second polling style.

- [ ] **Step 3: Run the contract tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.p1.test_environment_existing_proxy_drawer -v
```

Expected: all tests pass with exit code `0`.

- [ ] **Step 4: Run adjacent create-drawer tests**

Run:

```bash
.venv/bin/python -m unittest tests.p1.test_environment_existing_proxy_drawer tests.p1.test_environment_custom_proxy_drawer tests.p1.test_environment_create_drawer_retry -v
```

Expected: all tests pass with zero failures/errors.

### Task 4: Add the formal P0 Environment Management case

**Files:**
- Create: `tests/p0/environment_management/test_43_create_environment_with_existing_proxy.py`

- [ ] **Step 1: Add the unittest class and exact constants**

Use:

```python
CASE_MODULE = "环境管理"
ENVIRONMENT_NAME = "测试已有代理"
PROXY_SEARCH_TEXT = "7897"
ENVIRONMENT_OPEN_TIMEOUT_SECONDS = 60
```

Follow `test_42_create_custom_proxy_environment.py` for `setUpClass`, `tearDownClass`, exact-name stale cleanup, process snapshot/detection, close confirmation, batch deletion, and non-overriding `finally` cleanup.

- [ ] **Step 2: Implement only the requested assertions**

The test body must use this sequence:

```python
create_button_state = environment_page.create_environment_button_state()
assert_true(
    create_button_state["visible"] and create_button_state["enabled"],
    "创建环境按钮不可见或不可点击",
)

environment_page.open_create_environment_drawer()
assert_true(
    environment_page.create_environment_drawer_visible(),
    "创建环境抽屉未展开",
)

environment_page.fill_create_environment_name(ENVIRONMENT_NAME)
assert_equal(
    environment_page.create_environment_name_value(),
    ENVIRONMENT_NAME,
    "环境名称未成功填入",
)

environment_page.select_create_environment_proxy_mode("已有代理")
assert_true(
    environment_page.create_environment_existing_proxy_select_visible(),
    "请选择已有代理下拉选择框未显示",
)

selected_proxy_text = environment_page.select_first_create_environment_existing_proxy(
    PROXY_SEARCH_TEXT
)
assert_true(bool(selected_proxy_text), "未成功搜索并选中已有代理")

environment_page.submit_create_environment("create environment with existing proxy")
assert_true(
    not environment_page.create_environment_drawer_visible(),
    "创建成功后抽屉未关闭",
)
environment_page.search_environment_without_assert(ENVIRONMENT_NAME)
assert_true(
    environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME),
    f"环境管理列表未显示环境: {ENVIRONMENT_NAME}",
)
```

Before clicking【打开】, use the exact process-detection sequence:

```python
existing_browser_process_ids = set(main_process_ids(browser_process_name))
environment_page.click_environment_action(ENVIRONMENT_NAME, "打开")
try:
    new_browser_process_ids = wait_for_new_main_process_ids(
        browser_process_name,
        existing_browser_process_ids,
        expected_count=1,
        timeout_seconds=ENVIRONMENT_OPEN_TIMEOUT_SECONDS,
    )
except TimeoutError as exc:
    raise AssertionError(
        f"{ENVIRONMENT_OPEN_TIMEOUT_SECONDS}s 内未检测到新启动的 "
        f"{browser_process_name} 主进程"
    ) from exc
assert_true(
    bool(new_browser_process_ids),
    f"未检测到新启动的 {browser_process_name} 主进程",
)
```

After the process assertion succeeds, operationally wait for【关闭】, close and confirm, wait for【打开】, then delete only `测试已有代理` through the exact selected-row batch action. Do not inspect the selected proxy's address/type/connectivity or browser contents.

- [ ] **Step 3: Preserve non-asserting lifecycle cleanup**

Before creation, remove a stale exact-name environment if present. In `finally`, reopen Environment Management, search the exact name, close it if its action is【关闭】, confirm the close dialog, then batch-delete the environment. Log cleanup errors without replacing the test body's original failure. Clear search best-effort. Never navigate to Proxy Management or delete a proxy.

### Task 5: Verify formal behavior and regression scope

**Files:**
- Verify: `pages/environment_page.py`
- Verify: `tests/p1/test_environment_existing_proxy_drawer.py`
- Verify: `tests/p0/environment_management/test_43_create_environment_with_existing_proxy.py`

- [ ] **Step 1: Compile changed Python files**

Run:

```bash
.venv/bin/python -m py_compile pages/environment_page.py tests/p1/test_environment_existing_proxy_drawer.py tests/p0/environment_management/test_43_create_environment_with_existing_proxy.py
```

Expected: exit code `0` with no output.

- [ ] **Step 2: Run the targeted P1 regression set**

Run:

```bash
.venv/bin/python -m unittest tests.p1.test_environment_existing_proxy_drawer tests.p1.test_environment_custom_proxy_drawer tests.p1.test_environment_create_drawer_retry -v
```

Expected: all tests pass with zero failures/errors.

- [ ] **Step 3: Run the complete P1 suite**

Run:

```bash
.venv/bin/python -m unittest discover -s tests/p1 -p 'test_*.py'
```

Expected: zero failures/errors. Run outside the sandbox if Local Auth Lab cannot bind its required localhost port.

- [ ] **Step 4: Run the formal P0 case against the current CDP app**

Run:

```bash
.venv/bin/python run.py --config config/config.yaml --module test_43_create_environment_with_existing_proxy.py --attach-existing-app
```

Expected: the target case passes, `测试已有代理` is closed and deleted, and the existing proxy remains untouched. If no new `GinsBrowser` main process appears within 60 seconds, the case records Fail without terminating the later-case test runner.

- [ ] **Step 5: Check constants, residue, and repository integrity**

Run:

```bash
rg -n '^CASE_MODULE|^ENVIRONMENT_NAME|^PROXY_SEARCH_TEXT|^ENVIRONMENT_OPEN_TIMEOUT_SECONDS' tests/p0/environment_management/test_43_create_environment_with_existing_proxy.py
git diff --check
git status --short
```

Expected constants are `环境管理`, `测试已有代理`, `7897`, and `60`; no exact-name environment remains in DICloak; only the planned page object, P1/P0 tests, and plan are changed or untracked; the `/tmp` probe never appears in Git status.
