# Create Custom Proxy Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a P0 Environment Management case that creates `测试自定义代理` with `http://192.168.20.33:7897`, opens it, fails if a new `GinsBrowser` main process is not detected within 100 seconds, and then confirms close and deletes the environment.

**Architecture:** First probe the live DICloak DOM and complete workflow with a disposable script under `/tmp`; no formal repository code is written until that probe succeeds. Then add narrow custom-proxy drawer operations to `EnvironmentPage`, cover their orchestration with a P1 contract test, and add one P0 business case whose assertions match only the supplied expected results.

**Tech Stack:** Python 3.11, `unittest`, Playwright over Electron CDP, existing `CDPDriver`, `EnvironmentPage`, `core.process`, and project runner.

---

## File map

- Create temporarily: `/tmp/dicloak_custom_proxy_environment_probe.py` — disposable live-DOM and end-to-end probe; never added to Git.
- Modify: `pages/environment_page.py` — custom-proxy create-drawer interactions and state readers.
- Create: `tests/p1/test_environment_custom_proxy_drawer.py` — fast contract tests for the new page-object orchestration.
- Create: `tests/p0/environment_management/test_42_create_custom_proxy_environment.py` — the requested business case in the Environment Management group.
- Modify only if the live DOM requires stable selectors: `locators/environment_locators.yaml` — selectors verified by the disposable probe.

### Task 1: Verify the current live UI with a disposable probe

**Files:**
- Create temporarily: `/tmp/dicloak_custom_proxy_environment_probe.py`

- [ ] **Step 1: Verify DICloak CDP is reachable**

Run:

```bash
curl -fsS http://127.0.0.1:9222/json/version
```

Expected: exit code `0` and JSON containing a CDP browser/WebSocket field. If unavailable, restart `/Applications/DICloak.app` with `--remote-debugging-port=9222 --remote-allow-origins=*` and repeat.

- [ ] **Step 2: Build the disposable probe**

The probe must:

```python
from pathlib import Path

from core.app_config import resolve_app_config
from core.cdp_driver import CDPDriver
from core.config import load_config
from core.logger import setup_logger
from core.process import main_process_ids, wait_for_new_main_process_ids
from pages.environment_page import EnvironmentPage
from pages.login_page import LoginPage

ENVIRONMENT_NAME = "测试自定义代理"
PROXY_ADDRESS = "http://127.0.0.1:7897"
PROXY_IP = "127.0.0.1"
PROXY_PORT = "7897"
OPEN_TIMEOUT_SECONDS = 100
```

It connects to the existing app, logs in/switches to the configured team, opens Environment Management, removes a stale exact-name environment, and then walks the seven requested steps. During the create drawer flow it dumps only non-sensitive DOM metadata for form items: visible label text, input placeholders, input types, current values, and button text. It must not print account credentials, cookies, tokens, webhooks, API keys, or the full configuration.

- [ ] **Step 3: Run the probe and record the verified UI contract**

Run:

```bash
.venv/bin/python /tmp/dicloak_custom_proxy_environment_probe.py
```

Expected sequence:

```text
create_button={visible: True, enabled: True}
drawer_visible=True
environment_name=测试自定义代理
proxy_controls={quick_input_visible: True, parse_button_visible: True}
proxy_values={ip: 127.0.0.1, port: 7897}
proxy_type=HTTP
environment_visible=True
new_ginsbrowser_pids=[<positive pid>]
environment_closed=True
exists_after_delete=False
cleanup=completed
```

If a selector is wrong, edit only the temporary script and rerun from a clean state. Do not change `pages/environment_page.py` or create the formal P0 test until the complete flow, including cleanup, reaches `cleanup=completed`.

### Task 2: Add the failing page-object contract tests

**Files:**
- Create: `tests/p1/test_environment_custom_proxy_drawer.py`
- Test: `tests/p1/test_environment_custom_proxy_drawer.py`

- [ ] **Step 1: Write a probe double and failing tests for the desired public API**

Create tests that instantiate an `EnvironmentPage` probe with a fake CDP recorder and verify these exact operations:

```python
class EnvironmentCustomProxyDrawerTests(unittest.TestCase):
    def test_custom_proxy_flow_fills_name_selects_mode_and_parses_address(self) -> None:
        page = _CustomProxyDrawerProbe()

        page.fill_create_environment_name("测试自定义代理")
        page.select_create_environment_proxy_mode("自定义代理")
        page.parse_create_environment_proxy("http://192.168.20.33:7897")

        self.assertEqual(
            page.calls,
            [
                ("fill-name", "测试自定义代理"),
                ("select-mode", "自定义代理"),
                ("fill-quick-input", "http://192.168.20.33:7897"),
                ("click-parse", "解析"),
                ("wait-parsed", ("192.168.20.33", "7897")),
            ],
        )

    def test_submit_waits_for_drawer_to_close_and_list_to_finish_loading(self) -> None:
        page = _CustomProxyDrawerProbe()

        page.submit_create_environment("create custom proxy environment")

        self.assertEqual(
            page.calls,
            [
                ("submit", "create custom proxy environment"),
                ("wait-list", None),
            ],
        )
```

The probe overrides the low-level DOM scripts and waits, so these tests exercise orchestration without opening DICloak.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.p1.test_environment_custom_proxy_drawer -v
```

Expected: FAIL or ERROR because `EnvironmentPage` does not yet define the custom-proxy drawer API. Confirm the failure names the missing method, not a test syntax/import problem.

### Task 3: Implement the minimal EnvironmentPage API

**Files:**
- Modify: `pages/environment_page.py`
- Modify only if confirmed by Task 1: `locators/environment_locators.yaml`
- Test: `tests/p1/test_environment_custom_proxy_drawer.py`

- [ ] **Step 1: Add narrow public operations and readers**

Add these public operations to `EnvironmentPage`:

```python
def create_environment_button_state(self) -> dict[str, bool]:
    value = self.cdp.evaluate(self._create_environment_button_state_script())
    return value if isinstance(value, dict) else {"visible": False, "enabled": False}

def open_create_environment_drawer(self) -> None:
    self.cdp.click_element_by_script(self._visible_locator_script("create_button"))
    self._wait_create_environment_default_group_selected(
        timeout_seconds=self.CREATE_ENVIRONMENT_DEFAULT_GROUP_SECONDS
    )

def create_environment_drawer_visible(self) -> bool:
    return self._create_environment_drawer_visible()

def fill_create_environment_name(self, name: str) -> None:
    self.fill("environment_name_input", name)

def create_environment_name_value(self) -> str:
    return self._active_environment_name_input_value()

def select_create_environment_proxy_mode(self, mode: str) -> None:
    if self._active_drawer_form_radio_button_selected("代理设置", mode):
        return
    self.cdp.click_element_by_script(
        self._active_drawer_form_radio_button_script("代理设置", mode)
    )
    self._wait_active_drawer_form_radio_button_selected("代理设置", mode)

def create_environment_proxy_controls_state(self) -> dict[str, bool]:
    return {
        "quick_input_visible": self._active_drawer_input_visible_by_placeholder("选填"),
        "parse_button_visible": self._active_drawer_form_button_visible("快捷输入", "解析"),
    }

def parse_create_environment_proxy(self, proxy_address: str) -> None:
    proxy_ip, proxy_port = proxy_address.rsplit(":", 1)
    self.cdp.fill_element_by_script(
        self._active_drawer_input_by_placeholder_script("选填"), proxy_address
    )
    self.cdp.click_element_by_script(
        self._active_drawer_form_button_script("快捷输入", "解析")
    )
    self._wait_create_environment_proxy_values(proxy_ip, proxy_port)

def create_environment_proxy_values(self) -> tuple[str, str]:
    return (
        self._active_drawer_input_value_by_placeholder("代理主机"),
        self._active_drawer_input_value_by_placeholder("代理端口"),
    )

def submit_create_environment(self, context: str) -> None:
    self._submit_active_create_environment_drawer(context)
    self._wait_for_environment_list_not_loading_with_refresh_retry()
```

Implementation constraints:

- Scope every query to the active visible `.el-drawer`.
- Use the live-verified labels `代理设置` and `快捷输入`. Resolve parsed fields by the live-verified placeholders `代理主机` and `代理端口`, scoped to the active visible drawer; do not use global input order.
- Select `自定义代理` only from a visible Element Plus popper.
- Fill inputs through `CDPDriver.fill_element_by_script` so Vue receives real input events.
- Click `解析` through `CDPDriver.click_element_by_script`.
- `parse_create_environment_proxy` waits until the IP and port values equal the two components of the supplied `host:port`; this is an operational synchronization wait used by the explicit parse expectation.
- `submit_create_environment` reuses `_submit_active_create_environment_drawer(context)` and `_wait_for_environment_list_not_loading_with_refresh_retry()`.
- Add the exact private helpers referenced above: `_create_environment_button_state_script`, `_wait_active_drawer_form_radio_button_selected`, `_active_drawer_input_by_placeholder_script`, `_active_drawer_input_visible_by_placeholder`, `_active_drawer_input_value_by_placeholder`, `_active_drawer_form_button_script`, `_active_drawer_form_button_visible`, and `_wait_create_environment_proxy_values`. All use the existing active-drawer visibility rules and `page_seconds` timeout.
- Do not add network probing, proxy-geolocation reads, environment-action-state checks, or browser-page checks.

- [ ] **Step 2: Run the contract tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.p1.test_environment_custom_proxy_drawer -v
```

Expected: all tests in the module pass with exit code `0`.

- [ ] **Step 3: Run the existing create-drawer regression module**

Run:

```bash
.venv/bin/python -m unittest tests.p1.test_environment_create_drawer_retry -v
```

Expected: all existing tests pass with exit code `0`.

### Task 4: Add the formal P0 Environment Management case

**Files:**
- Create: `tests/p0/environment_management/test_42_create_custom_proxy_environment.py`

- [ ] **Step 1: Add the unittest class and exact constants**

Use:

```python
CASE_MODULE = "环境管理"
ENVIRONMENT_NAME = "测试自定义代理"
PROXY_ADDRESS = "http://192.168.20.33:7897"
PROXY_IP = "192.168.20.33"
PROXY_PORT = "7897"
ENVIRONMENT_OPEN_TIMEOUT_SECONDS = 100
```

`setUpClass` must follow the existing P0 pattern: load `config/config.yaml`, create the logger and `CDPDriver`, connect, and call `LoginPage.ensure_logged_in_as_config_account()`. `tearDownClass` closes only the CDP connection.

- [ ] **Step 2: Implement the seven business steps with only permitted assertions**

The test body must perform these checks in order:

```python
button_state = environment_page.create_environment_button_state()
assert_true(button_state["visible"] and button_state["enabled"], "创建环境按钮不可见或不可点击")

environment_page.open_create_environment_drawer()
assert_true(environment_page.create_environment_drawer_visible(), "创建环境抽屉未展开")

environment_page.fill_create_environment_name(ENVIRONMENT_NAME)
assert_equal(environment_page.create_environment_name_value(), ENVIRONMENT_NAME)

environment_page.select_create_environment_proxy_mode("自定义代理")
controls = environment_page.create_environment_proxy_controls_state()
assert_true(controls["quick_input_visible"], "快捷输入文本框未显示")
assert_true(controls["parse_button_visible"], "解析按钮未显示")

environment_page.parse_create_environment_proxy(PROXY_ADDRESS)
proxy_ip, proxy_port = environment_page.create_environment_proxy_values()
assert_equal(proxy_ip, PROXY_IP)
assert_equal(proxy_port, PROXY_PORT)

environment_page.submit_create_environment("create custom proxy environment")
assert_true(not environment_page.create_environment_drawer_visible(), "创建成功后抽屉未关闭")
environment_page.search_environment_without_assert(ENVIRONMENT_NAME)
assert_true(
    environment_page.environment_visible_in_current_list(ENVIRONMENT_NAME),
    f"环境管理列表未显示环境: {ENVIRONMENT_NAME}",
)
```

Before clicking【打开】, capture `existing_ids = set(main_process_ids(browser_process_name))`. Click the target row action, then call:

```python
try:
    new_pids = wait_for_new_main_process_ids(
        browser_process_name,
        existing_ids,
        expected_count=1,
        timeout_seconds=ENVIRONMENT_OPEN_TIMEOUT_SECONDS,
    )
except TimeoutError as exc:
    raise AssertionError(
        f"100s 内未检测到新启动的 {browser_process_name} 主进程"
    ) from exc
assert_true(bool(new_pids), f"未检测到新启动的 {browser_process_name} 主进程")
```

After the process assertion succeeds, operationally wait until the row can be closed, click【关闭】, confirm the visible close dialog with【确定】when present, and wait until the row returns to【打开】. Then delete the exact environment through the selected-row batch action and wait for it to disappear. Do not inspect browser contents or proxy connectivity.

- [ ] **Step 3: Add non-asserting idempotent cleanup**

Before creation, perform an exact-name search and best-effort removal of a stale environment. The body owns the normal close-confirm-delete sequence. In `finally`, search the exact name; if its current action is【关闭】, click it, confirm the close dialog when present, and operationally wait for【打开】; then delete the environment and clear the search. Cleanup exceptions are logged at warning level and do not replace the body failure.

### Task 5: Verify the formal case and regression scope

**Files:**
- Verify: `pages/environment_page.py`
- Verify: `tests/p1/test_environment_custom_proxy_drawer.py`
- Verify: `tests/p0/environment_management/test_42_create_custom_proxy_environment.py`

- [ ] **Step 1: Compile the changed Python files**

Run:

```bash
.venv/bin/python -m py_compile pages/environment_page.py tests/p1/test_environment_custom_proxy_drawer.py tests/p0/environment_management/test_42_create_custom_proxy_environment.py
```

Expected: exit code `0` with no output.

- [ ] **Step 2: Run both P1 contract modules**

Run:

```bash
.venv/bin/python -m unittest tests.p1.test_environment_custom_proxy_drawer tests.p1.test_environment_create_drawer_retry -v
```

Expected: all tests pass, zero failures/errors.

- [ ] **Step 3: Run the formal P0 case against the existing CDP app**

Run:

```bash
.venv/bin/python run.py --config config/config.yaml --module test_42_create_custom_proxy_environment.py --attach-existing-app
```

Expected: the one target case passes; the environment is closed and deleted afterward. If no new `GinsBrowser` main process appears within 100 seconds, the case records Fail and the runner returns a test-failure exit code without aborting later selected cases.

- [ ] **Step 4: Check repository integrity**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only the planned page object, locator (if needed), P1 test, P0 test, and plan/document files are changed or untracked. `/tmp/dicloak_custom_proxy_environment_probe.py` must not appear in Git status.
