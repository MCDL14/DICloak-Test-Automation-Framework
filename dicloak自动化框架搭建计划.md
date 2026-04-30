# Dicloak 自动化框架搭建计划

## 一、目标与范围

本计划用于搭建 Dicloak APP 的自动化测试框架，优先覆盖 P0 主流程，后续逐步补充 P1 和稳定性场景。

第一阶段目标不是一次性补齐全部用例，而是先完成一个可运行、可维护、可扩展的自动化框架，并跑通 P0 验证用例。

当前实现状态：

1. 框架骨架、配置、预检、日志、APP 生命周期、CDP 连接、UIAutomation、飞书通知、用例运行编排已完成。
2. 当前已完成并验证环境管理模块 14 条 P0 用例。
3. P0 用例已按业务模块移动到 `tests/p0/environment_management/`。
4. 已预留 `proxy_management`、`extension_management`、`environment_group_management`、`member_management`、`global_settings` 等模块目录。
5. 当前支持按级别、按文件/目录模块、按业务模块、按单条用例运行。

第一阶段需要达成以下结果：

1. 能通过配置文件启动 Dicloak APP。
2. 能通过配置文件读取账号、密码、飞书 webhook、批量导入文件路径等信息。
3. 能连接 Electron APP 暴露的 CDP 调试端口。
4. 能执行 P0 自动化用例，并输出日志。
5. 用例失败时能抓取错误日志，并发送飞书通知。
6. 支持执行失败重试和模块级熔断。
7. 页面元素定位集中维护，避免元素散落在各个用例中。

## 二、已确认前提

1. Dicloak APP 的 exe 路径需要放在配置文件中维护。
2. 登录账号和密码需要放在配置文件中维护。
3. Dicloak APP 是 Electron 应用。
4. 已验证可以通过 CDP 连接并打开控制台。
5. APP 启动时可使用以下两个独立参数开放 CDP：

```text
--remote-debugging-port=9222
--remote-allow-origins=*
```

6. 飞书 webhook 已具备，具体地址放在配置文件中维护。
7. 批量导入文件格式为 `.xlsx`，文件路径放在配置文件中维护。
8. 登录无验证码，不需要处理验证码、短信验证或二次验证。
9. 导出类用例的目标路径和文件名需要通过配置文件维护。
10. 抓包相关用例用于验证 Dicloak APP 内置的抓包进程拦截功能：自动化只确认指定抓包工具进程存在，并在 APP 内执行打开环境操作，不进入抓包工具内部操作。

## 三、待验证事项

以下事项在框架搭建或具体用例设计时验证：

1. 书签覆盖和追加的数据表字段，需要与 Dicloak 真实模板对齐。
2. 内核删除规则、成员导出校验规则、本地扩展安装校验规则，在具体用例设计时再细化。

已验证事项：

1. CDP 连接后可通过 URL、标题和页面关键元素综合识别 Dicloak 主页面。
2. 批量导入文件上传可通过隐藏的 DOM `input[type=file]` 完成。
3. 环境内核 CDP 端口可通过 `open_env` 请求体中的 PID 读取进程命令行或监听端口解析。

## 四、技术选型

### 1. 编程语言

使用 Python。

建议版本：

```text
Python 3.10 或 Python 3.11
```

选择原因：

1. Windows 桌面自动化生态较成熟。
2. 与 UIAutomation、CDP、Excel 文件处理、HTTP 通知集成成本低。
3. 后续测试数据、日志、飞书通知、报告生成都容易扩展。

### 2. 测试框架

使用 `unittest` 加自定义框架封装。

自定义部分主要包括：

1. APP 启动和关闭。
2. CDP 连接管理。
3. UIAutomation 操作封装。
4. 日志采集。
5. 飞书通知。
6. 失败重试。
7. 模块级熔断。
8. 测试数据读取。
9. 页面对象封装。

### 3. UI 自动化方式

采用 UIAutomation 和 CDP 结合的方式。

职责划分：

1. UIAutomation 负责 APP 外壳、系统窗口、文件选择器、原生弹窗等控件。
2. CDP 负责 Electron 内嵌页面中的 DOM 元素、按钮、列表、表格、页面断言等。
3. 如果同一个元素既能被 UIAutomation 操作，也能被 CDP 操作，优先使用 CDP。
4. 如果 CDP 无法稳定定位，再使用 UIAutomation 作为补充方案。

### 4. 推荐依赖

初期推荐使用以下依赖：

```text
PyYAML
requests
playwright
websocket-client
uiautomation
openpyxl
```

可选依赖：

```text
pywinauto
```

说明：

1. CDP 操作优先使用 `playwright` 的 `connect_over_cdp`，减少手写点击、输入、等待、取文本等基础能力。
2. 如果 `playwright` 无法稳定连接 Electron 页面，再使用 `websocket-client` 直接调用 CDP 协议作为兜底方案。
3. 如果 UIAutomation 对部分窗口支持不稳定，可补充 `pywinauto`。

## 五、配置文件设计

配置文件建议使用 YAML，例如：

```text
config/config.yaml
```

建议配置项如下：

```yaml
app:
  exe_path: "C:/Program Files/Dicloak/Dicloak.exe"
  work_dir: "C:/Program Files/Dicloak"
  startup_args:
    - "--remote-debugging-port=9222"
    - "--remote-allow-origins=*"
  process_name: "Dicloak.exe"
  close_existing_before_start: true
  process_check_timeout: 30
  startup_timeout: 60
  shutdown_timeout: 20

cdp:
  host: "127.0.0.1"
  port: 9222
  driver: "playwright"
  fallback_driver: "websocket"
  connect_timeout: 30
  default_page_url_keyword: ""

account:
  username: "your_username"
  password: "your_password"

feishu:
  enabled: true
  webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
  at_open_id: ""
  at_name: ""
  notify_on_success: false
  notify_on_failure: true
  timeout: 10

report:
  enabled: false
  html_file: "test_report.html"
  port: 9091

test_data:
  environment_name_prefix: "auto_env"
  kernel_142_environment_name: "142环境"
  kernel_134_environment_name: "134环境"

  bookmark:
    storage_dir: "C:/testdata/bookmarks"
    overwrite_file_name: "overwrite_bookmarks.xlsx"
    append_file_name: "append_bookmarks.xlsx"
    overwrite_rows:
      - name: "覆盖书签示例"
        url: "https://example.com/overwrite"
        folder: "自动化测试"
        remark: "覆盖场景"
    append_rows:
      - name: "追加书签示例"
        url: "https://example.com/append"
        folder: "自动化测试"
        remark: "追加场景"

  member_export:
    expected_file_full_path: "C:/testdata/member_export/expected_members.xlsx"
    export_dir: "C:/testdata/member_export/output"
    export_file_name: ""
    export_file_regex: "^导出成员列表 - \\d{12}\\.xlsx$"

  batch_import:
    file_dir: "C:/testdata/import"
    file_name: "dicloak_import.xlsx"

  batch_export:
    export_dir: "C:/testdata/export"
    export_file_name: "environments.xlsx"

  packet_capture:
    process_name: "Charles.exe"
    startup_path: "C:/Program Files/Charles/Charles.exe"

  local_extension:
    package_name: "local_extension.zip"
    package_path: "C:/testdata/extensions"

run:
  case_level: "P0"
  default_parallel: false
  enable_launcher_ui: false
  retry_times: 1
  retry_interval_seconds: 3
  precheck_before_run: true
  stop_on_login_failed: true
  screenshot_on_failure: true
  collect_log_on_failure: true

log:
  level: "INFO"
  dir: "logs"
  keep_days: 14
```

配置原则：

1. APP 路径、账号密码、webhook、导入导出文件路径、工具路径不能写死在代码中。
2. 不同环境可通过不同 YAML 文件区分，例如 `config/dev.yaml`、`config/test.yaml`。
3. 敏感信息不要提交到公共仓库。
4. `feishu.webhook_url` 属于敏感信息，对外共享代码或文档时必须替换为占位符。
5. 本地可保留 `config/config.example.yaml` 作为模板，真实配置文件加入 `.gitignore`。

新增测试数据字段说明：

1. `test_data.bookmark.storage_dir`：书签相关测试文件的存放路径。
2. `test_data.bookmark.overwrite_file_name`：覆盖书签场景使用的文件名。
3. `test_data.bookmark.append_file_name`：追加书签场景使用的文件名。
4. `test_data.bookmark.overwrite_rows`：覆盖书签场景使用的数据表内容，按行维护。
5. `test_data.bookmark.append_rows`：追加书签场景使用的数据表内容，按行维护。
6. `test_data.member_export.expected_file_full_path`：导出成员场景中预先准备的正确文件完整路径。
7. `test_data.member_export.export_dir`：导出成员文件输出路径。
8. `test_data.member_export.export_file_name`：导出成员固定文件名；如果导出文件名带时间戳，则保持为空。
9. `test_data.member_export.export_file_regex`：导出成员文件名正则，例如 `^导出成员列表 - \d{12}\.xlsx$`。
10. `test_data.batch_import.file_dir`：批量导入文件所在路径。
11. `test_data.batch_import.file_name`：批量导入文件名。
12. `test_data.batch_export.export_dir`：批量导出文件路径。
13. `test_data.batch_export.export_file_name`：批量导出文件名。
14. `test_data.packet_capture.process_name`：抓包工具进程名称。
15. `test_data.packet_capture.startup_path`：抓包工具启动路径。
16. `test_data.local_extension.package_name`：本地扩展包名称。
17. `test_data.local_extension.package_path`：本地扩展包所在目录；如果直接配置 zip 完整路径，也兼容。

路径和文件名规则：

1. 导入、导出、书签、本地扩展包等文件都按全路径匹配。
2. 配置中拆分为路径和文件名的场景，实际使用时用 `路径 + 文件名` 拼接为完整路径。
3. 配置中已经是完整路径的字段，例如 `expected_file_full_path`，直接按完整路径校验。
4. 本地扩展包优先按 `package_path + package_name` 拼接完整路径；如果 `package_path` 直接配置为 zip 文件完整路径，也兼容。
5. 文件存在性检查放入环境预检，运行用例前先暴露路径错误。

## 六、框架功能设计

### 1. 环境预检

自动化运行前先执行环境预检，尽量在用例执行前暴露配置和环境问题。

预检内容：

1. Python 版本是否符合要求。
2. APP `exe_path` 是否存在。
3. APP `work_dir` 是否存在。
4. APP 启动参数是否包含两个独立的 CDP 参数。
5. 批量导入文件完整路径是否存在。
6. 书签文件存放目录是否存在。
7. 成员导出预期正确文件是否存在。
8. 批量导出目录是否存在。
9. 抓包工具启动路径是否存在。
10. 本地扩展包完整路径是否存在。
11. CDP 端口是否被占用。
12. 飞书 webhook 是否为空。

预检结果处理：

1. 必要路径不存在时，取消自动化任务。
2. 飞书 webhook 为空时，只跳过通知，不阻断测试。
3. CDP 端口被占用时，结合现有 APP 实例处理策略判断是否关闭已有 APP。
4. 预检失败需要输出明确错误，并返回配置或环境错误退出码。

### 2. APP 生命周期管理

需要封装以下能力：

1. 按配置文件启动 Dicloak APP。
2. 启动时附加 CDP 参数。
3. 启动 APP 前检查 Dicloak 是否已经运行。
4. 如果已经运行，先正常关闭已有 APP，再重新打开。
5. 打开 APP 后检测 APP 进程是否存在。
6. 进程检测最多等待 30 秒。
7. 如果 30 秒内没有检测到 APP 进程，发送飞书通知。
8. 进程检测超时后，仍尝试连接 CDP。
9. 如果 CDP 也连接失败，再发送飞书通知，并取消自动化任务。
10. 等待 APP 主窗口出现。
11. 等待 CDP 端口可访问。
12. 测试结束后关闭 APP。
13. APP 启动失败时记录错误日志并发送飞书提醒。

### 3. CDP 连接管理

需要封装以下能力：

1. 通过 `http://127.0.0.1:9222/json` 获取页面列表。
2. 根据页面标题或 URL 选择目标页面。
3. 优先使用 Playwright `connect_over_cdp` 连接。
4. 如果 Playwright 连接失败，再尝试使用 WebSocket 直接连接 CDP。
5. 执行 DOM 查询、点击、输入、取文本等基础操作。
6. 支持等待元素出现、等待元素可点击、等待文本变化。
7. 连接失败时输出明确错误原因。
8. 目标页面识别方式已验证，连接后会跳过 DevTools 页面并优先选择 Dicloak 主页面。

### 4. UIAutomation 操作封装

需要封装以下能力：

1. 查找 APP 主窗口。
2. 查找原生控件。
3. 点击按钮、输入文本、选择文件。
4. 处理 Windows 文件选择器。
5. 处理原生弹窗。
6. 操作失败时输出控件信息和截图。

### 5. 页面对象封装

用例中不直接写元素定位，统一通过页面对象操作。

建议页面对象包括：

```text
pages/login_page.py
pages/environment_page.py
pages/kernel_page.py
pages/import_page.py
```

示例职责：

1. `LoginPage`：登录、判断是否已登录、读取当前登录账号、账号不一致时退出重登、处理登录失败。
2. `EnvironmentPage`：创建环境、打开环境、关闭环境、删除环境、读取环境列表。
3. `KernelPage`：查看内核版本、下载内核、切换内核环境。
4. `ImportPage`：批量导入、选择 xlsx 文件、确认导入、读取导入结果。

### 5.1 登录态处理

Dicloak APP 重启后可能保留登录态，因此打开 APP 后不能直接假设当前登录账号就是自动化账号。

第一版采用“方案 1 + 方案 3”的组合策略：

1. 打开 APP 后先判断是否已登录。
2. 如果未登录，使用 `account.username` 和 `account.password` 登录。
3. 如果已登录，读取 APP 当前登录账号。
4. 如果当前账号与 `account.username` 一致，继续执行用例。
5. 如果当前账号与 `account.username` 不一致，先退出登录，再使用自动化账号重新登录。
6. 重新登录后再次读取当前账号并校验。
7. 如果无法读取当前账号、无法退出登录或重登后账号仍不一致，则判定登录态异常。
8. 登录态异常时触发登录失败熔断，取消依赖登录态的后续用例，并按配置发送飞书失败告警。

该策略不清理 APP 本地数据，不删除登录缓存文件，避免误删用户数据或影响 APP 配置。

已实测补充：

1. 当前登录账号优先从 `localStorage.basic:state.userInfo.email` 读取，兜底读取 `localStorage.basic:state.userInfo.name`。右上角账号文本存在截断显示，不能用于精确账号校验。
2. 退出登录入口为右上角账号区域 `header.el-header .tool-bar-ri .avatar`，退出菜单项为 `.userInfo-popover li:last-child`，确认框按钮为 `.el-message-box button:has-text('确定')`。
3. 登录页地址为 `#/sso/login`，账号输入框为 `input[placeholder='请输入邮箱或账号']`，密码输入框为 `input[type='password'][placeholder='请输入密码']`，登录按钮为 `button:has-text('立即登录')`。
4. 登录动作保留固定 selector，同时增加登录页可见输入框兜底：固定 selector 失败时，按页面可见输入框顺序填入账号和密码，并按坐标点击 `立即登录`。
5. 登录成功后必须重新读取 `localStorage.basic:state.userInfo`，确认当前账号与 `account.username` 一致。
6. 自动化账号是外部账号，可能拥有多个团队；登录账号校验通过后，必须继续校验 `localStorage.basic:state.userInfo.orgName` 是否等于 `account.team_name`。
7. 如果当前团队不是 `account.team_name`，点击账号菜单中的“切换团队”，等待团队列表接口返回并出现目标团队名称，再点击目标团队。
8. 团队切换完成后再次读取 `localStorage.basic:state.userInfo.orgName`，确认已经切换到目标团队；如果超时或切换后仍不一致，判定登录态异常。

### 5.2 内核进程与内核 CDP 识别

APP 打开环境后会调用 `open_env` 接口，接口请求体包含本次环境对应的内核主进程 PID，例如 `{"pid":"18712"}`。

框架打开环境时必须监听 APP 页面的 `open_env` 请求，并从请求体读取 PID。后续不能只按 `GinsBrowser.exe` 进程名判断环境是否打开，因为一个 Chromium 内核会产生多个同名子进程，多个环境同时打开时也会存在多个 `GinsBrowser.exe`。

标准流程：

1. 点击指定环境行的“打开”按钮时，同步监听 URL 包含 `/open_env` 且方法为 `PATCH` 的请求。
2. 从请求 body 解析 `pid`，将环境名称与 PID 绑定。
3. 等待该 PID 存活，而不是等待任意 `GinsBrowser.exe` 存在。
4. 优先从该 PID 的命令行解析 `--remote-debugging-port`。
5. 如果命令行没有 CDP 端口，则通过该 PID 的监听端口反查可访问 `/json/version` 的端口。
6. 请求 `http://127.0.0.1:<port>/json/version`，确认内核 CDP 可用。
7. 关闭环境时等待该 PID 退出，而不是等待全部 `GinsBrowser.exe` 退出。

### 6. 全局元素定位管理

元素定位不能散落在测试用例中。

建议按页面或模块维护：

```text
locators/
  login_locators.yaml
  environment_locators.yaml
  kernel_locators.yaml
  import_locators.yaml
```

每个元素至少维护：

1. 元素名称。
2. 定位方式。
3. 定位表达式。
4. 元素用途。
5. 是否为关键元素。

示例：

```yaml
login:
  username_input:
    by: "css"
    value: "input[name='username']"
    desc: "登录页账号输入框"
  password_input:
    by: "css"
    value: "input[name='password']"
    desc: "登录页密码输入框"
  login_button:
    by: "css"
    value: "button[type='submit']"
    desc: "登录按钮"
```

定位原则：

1. 优先使用稳定的 CSS 选择器。
2. 优先使用业务属性、测试属性、唯一文本、稳定 class。
3. 尽量避免 XPath。
4. 避免依赖动态 class、绝对层级、屏幕坐标。
5. 无法稳定定位时，记录原因并考虑推动前端增加测试属性。

### 7. 日志与错误采集

日志至少包括：

1. 本次执行的配置文件。
2. APP 启动参数。
3. CDP 连接结果。
4. 每条用例开始和结束时间。
5. 每个关键步骤的操作日志。
6. 断言失败原因。
7. 异常堆栈。
8. 失败截图路径。
9. APP 错误日志路径。

失败时需要尽量采集：

1. 自动化框架日志。
2. APP 本地日志。
3. 当前页面标题和 URL。
4. 当前页面关键 DOM 文本。
5. 截图。
6. 失败用例名称和步骤。

### 8. 飞书通知

飞书通知参考当前目录下的 `飞书接入文档.md` 进行设计，第一版优先使用飞书自定义机器人的文本消息能力。

飞书通知分为三类：

1. 执行总结通知。
2. 失败告警通知。
3. 模块级熔断通知。

配置字段：

```yaml
feishu:
  enabled: true
  webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
  at_open_id: ""
  at_name: ""
  notify_on_success: false
  notify_on_failure: true
  timeout: 10
```

字段说明：

1. `enabled`：是否启用飞书通知。
2. `webhook_url`：飞书自定义机器人 Webhook 地址。
3. `at_open_id`：需要 @ 的飞书用户 open_id。
4. `at_name`：@ 人展示名称。
5. `notify_on_success`：P0 全部通过时是否发送通知。
6. `notify_on_failure`：P0 失败时是否发送通知。
7. `timeout`：发送请求的超时时间，默认 10 秒。

建议通知内容包括：

```text
项目：Dicloak 自动化
环境：测试环境
级别：P0
结果：失败
总数：3
通过：2
失败：1
异常：0
跳过：0
通过率：66.7%
失败用例：test_batch_import
失败原因：导入结果存在失败环境
日志路径：logs/20260427_xxx.log
截图路径：screenshots/20260427_xxx.png
报告链接：http://192.168.20.33:9091/test_report.html
```

第一版如果暂时没有 HTML 报告，可以不发送报告链接，只发送日志路径和截图路径。后续如果增加报告服务，可参考 `飞书接入文档.md` 中的本机局域网 IP 加端口拼接方式。

消息发送格式：

```python
payload = {
    "msg_type": "text",
    "content": {
        "text": text,
    },
}
```

请求头：

```python
headers = {"Content-Type": "application/json; charset=utf-8"}
```

@ 人格式：

```python
mention = f'<at user_id="{at_open_id}">{at_name}</at>'
```

只有同时配置 `at_open_id` 和 `at_name` 时，消息中才生成 @ 标签。

发送成功判断：

```python
resp.status_code == 200 and resp.json().get("code") == 0
```

以下情况正常跳过通知，并且不影响测试结果：

1. `feishu.enabled` 为 `false`。
2. `feishu.webhook_url` 为空。
3. 当前执行结果不满足通知条件，例如成功时 `notify_on_success` 为 `false`。

以下情况视为通知发送失败，需要记录日志：

1. 请求超时。
2. 网络连接失败。
3. HTTP 状态码不是 200。
4. 飞书响应 JSON 中 `code` 不等于 0。
5. 飞书响应不是合法 JSON。

通知原则：

1. P0 失败必须发送飞书。
2. P0 全部通过可配置是否发送。
3. 单个断言不建议每次都发送飞书，避免通知过多。
4. 模块级熔断需要单独发送明确提醒。
5. webhook 和 @ 人配置必须从配置文件读取，不允许写死在代码中。
6. 飞书通知失败不能覆盖原始测试失败原因，只能作为附加错误记录。

后续实现建议：

1. `core/feishu.py` 只负责消息组装和 Webhook 发送。
2. `core/result.py` 负责承接 `unittest` 执行统计，包括总数、通过、失败、异常、跳过、通过率、失败用例、日志路径和截图路径。
3. `run.py` 在测试执行完成后，将结果对象交给 `core/feishu.py` 发送总结。
4. 第一版不直接依赖 Allure 结果文件，后续如果引入 Allure，再补充读取 `reports/allure-results/*-result.json` 的统计逻辑。

### 9. 失败重试

重试主要用于处理短暂的 UI 卡顿、接口延迟、CDP 连接不稳定等问题。

建议规则：

1. 用例级重试次数从配置文件读取。
2. 默认重试 1 次。
3. 断言类失败是否重试需要谨慎，避免掩盖真实问题。
4. 环境创建、删除、导入等有副作用的操作，需要确保重试前状态可控。
5. 每次重试必须记录日志。

### 10. 模块级熔断

模块级熔断用于避免基础能力失败后继续执行大量无效用例。

建议熔断规则：

1. 登录失败，跳过所有依赖登录的用例。
2. APP 启动失败，跳过全部 UI 用例。
3. CDP 连接失败，跳过所有依赖 CDP 的用例。
4. 环境列表页面无法打开，跳过环境管理相关用例。
5. 内核列表或内核下载失败，跳过内核切换相关用例。
6. 批量导入入口不可用，跳过批量导入相关用例。

熔断需要输出：

1. 熔断模块。
2. 触发原因。
3. 被跳过的用例数量。
4. 飞书告警。

### 11. 测试数据管理与清理

测试数据分为两类：

1. 使用现有数据的用例。
2. 执行过程中创建新数据的用例。

处理原则：

1. 可以稳定复用的数据，优先配置在 `test_data` 中，由用例直接使用。
2. 需要创建数据的用例，创建时使用统一自动化前缀，例如 `auto_env`。
3. 创建新数据的用例必须设计后置清理动作。
4. 用例执行结束后删除本次用例产生的新数据。
5. 清理失败时记录日志和飞书失败摘要，但不能扩大删除范围。
6. 删除环境、删除内核、删除扩展、删除书签等高风险操作必须使用前缀、白名单或明确配置保护。
7. 具体内核删除规则、成员导出校验规则、本地扩展安装校验规则，在对应用例设计时补充。

### 12. 导入导出文件校验

导入导出相关文件按完整路径校验。

规则：

1. 导入文件完整路径由 `test_data.batch_import.file_dir` 和 `test_data.batch_import.file_name` 拼接得到。
2. 批量导出文件完整路径由 `test_data.batch_export.export_dir` 和 `test_data.batch_export.export_file_name` 拼接得到。
3. 成员导出文件如果 `test_data.member_export.export_file_name` 不为空，则由 `export_dir + export_file_name` 拼接得到。
4. 成员导出文件如果 `export_file_name` 为空，则在 `export_dir` 中按 `test_data.member_export.export_file_regex` 匹配，例如 `导出成员列表 - 202604281947.xlsx`。
5. 成员导出预期文件直接使用 `test_data.member_export.expected_file_full_path`。
6. 自动化校验时需要同时匹配路径和文件名。
7. 导出类用例需要等待文件生成完成，再进行断言。
8. 文件生成完成的判断可结合文件是否存在、文件大小是否大于 0、短时间内文件大小是否稳定。

### 13. 抓包进程拦截校验

Dicloak APP 内有一个功能可以配置抓包工具进程名称。一旦该进程存在，APP 应该不允许打开环境。

注意：该拦截逻辑属于 Dicloak APP 自身功能，不能由自动化框架在点击“打开环境”前代替 APP 阻止。自动化框架只负责准备前置条件、执行 APP 页面操作，并断言 APP 的实际拦截结果。

是否验证“抓包进程存在时 APP 阻止打开环境”、验证哪些提示和状态，全部写在具体用例中，不通过配置开关控制。

第一版抓包相关自动化边界：

1. 按配置读取抓包工具进程名称和启动路径。
2. 需要时按配置启动抓包工具。
3. 校验指定进程是否存在，作为用例前置条件。
4. 在 APP 内点击打开环境。
5. 指定进程存在时，验证 APP 阻止环境打开。
6. 验证 APP 的提示文案、环境状态或打开结果符合预期。
7. 框架页面对象不得在点击前自行拦截打开环境动作。
8. 不进入抓包工具内部操作。
9. 不读取、导出或分析抓包内容。

### 14. 运行入口、启动界面与退出码

第一版先提供命令行运行入口，后续可增加带 UI 的启动界面。

建议命令：

```bash
python run.py --config config/config.yaml --level P0
python run.py --config config/config.yaml --level P0 --business-module 环境管理
python run.py --config config/config.yaml --module environment_management
python run.py --config config/config.yaml --module test_01_kernel_integrity.py
python run.py --config config/config.yaml --module p0/environment_management/test_01_kernel_integrity.py
python run.py --config config/config.yaml --module tests/p0/environment_management/test_01_kernel_integrity.py
python run.py --config config/config.yaml --case test_142_kernel_integrity
python run.py --config config/config.yaml --precheck
```

`--module` 用于单模块运行，优先按文件或目录精确发现用例；如果没有找到对应文件或目录，再按模块关键字过滤已发现的用例。模块参数支持文件名、相对 `tests/` 的路径、完整 `tests/...` 路径和点分模块关键字。

`--business-module` 用于按业务模块运行用例；当前支持：环境管理、代理管理、扩展管理、环境分组管理、成员管理、全局设置。

后续带 UI 的启动界面建议支持：

1. 选择配置文件。
2. 选择执行级别，例如 P0、P1。
3. 选择模块或单条用例。
4. 启动前执行环境预检。
5. 展示执行进度和最终结果。
6. 打开日志、截图、报告目录。

退出码规则：

1. `0`：全部通过。
2. `1`：存在用例失败或异常。
3. `2`：配置错误或环境预检失败。
4. `3`：APP 启动失败或 CDP 连接失败，自动化任务取消。
5. `130`：用户中断。

## 七、预计项目结构

建议项目结构如下：

```text
DICloak自动化框架/
├─ config/
│  ├─ config.example.yaml
│  └─ config.yaml
├─ core/
│  ├─ precheck.py
│  ├─ app.py
│  ├─ cdp_driver.py
│  ├─ ui_driver.py
│  ├─ config.py
│  ├─ logger.py
│  ├─ retry.py
│  ├─ feishu.py
│  ├─ assertions.py
│  ├─ circuit_breaker.py
│  ├─ result.py
│  └─ runner.py
├─ locators/
│  ├─ login_locators.yaml
│  ├─ environment_locators.yaml
│  ├─ kernel_locators.yaml
│  └─ import_locators.yaml
├─ pages/
│  ├─ login_page.py
│  ├─ environment_page.py
│  ├─ kernel_page.py
│  └─ import_page.py
├─ test_data/
│  ├─ import/
│  ├─ export/
│  ├─ bookmarks/
│  ├─ members/
│  ├─ extensions/
│  └─ README.md
├─ tests/
│  ├─ p0/
│  │  ├─ environment_management/
│  │  │  ├─ test_01_kernel_integrity.py
│  │  │  ├─ test_02_create_default_environment.py
│  │  │  ├─ test_03_batch_create_environments.py
│  │  │  ├─ test_04_create_134_kernel_environment.py
│  │  │  ├─ test_05_batch_create_134_kernel_environments.py
│  │  │  ├─ test_06_batch_import_environments.py
│  │  │  ├─ test_07_edit_environment_name.py
│  │  │  ├─ test_08_edit_fixed_open_url.py
│  │  │  ├─ test_09_filter_environment_group.py
│  │  │  ├─ test_10_filter_environment_remark.py
│  │  │  ├─ test_11_top_environment.py
│  │  │  ├─ test_12_quick_edit_environment_name.py
│  │  │  ├─ test_13_sort_environment_serial.py
│  │  │  └─ test_14_move_remark_column.py
│  │  ├─ proxy_management/
│  │  ├─ extension_management/
│  │  ├─ environment_group_management/
│  │  ├─ member_management/
│  │  └─ global_settings/
│  └─ p1/
├─ logs/
├─ reports/
├─ screenshots/
├─ requirements.txt
├─ run.py
├─ launcher_ui.py
└─ README.md
```

说明：

1. `core/` 放框架底层能力。
2. `pages/` 放业务页面操作。
3. `locators/` 放元素定位。
4. `tests/` 放测试用例。
5. `test_data/` 按模块放测试数据说明和非敏感样例。
6. `logs/`、`reports/`、`screenshots/` 放运行产物。
7. `launcher_ui.py` 是后续带 UI 启动界面的预留入口，第一版可以先不实现。

## 八、P0 用例设计

当前第一阶段已完成环境管理模块 14 条 P0 用例，用于验证框架可用性。

已实现用例：

1. `test_01_kernel_integrity.py`：内核完整性校验。
2. `test_02_create_default_environment.py`：创建默认配置环境。
3. `test_03_batch_create_environments.py`：批量创建 5 个环境。
4. `test_04_create_134_kernel_environment.py`：创建 134 内核环境。
5. `test_05_batch_create_134_kernel_environments.py`：批量创建 134 内核环境。
6. `test_06_batch_import_environments.py`：批量导入环境。
7. `test_07_edit_environment_name.py`：编辑环境名称。
8. `test_08_edit_fixed_open_url.py`：编辑固定打开网址。
9. `test_09_filter_environment_group.py`：环境列表筛选-自动化分组。
10. `test_10_filter_environment_remark.py`：环境列表备注筛选。
11. `test_11_top_environment.py`：置顶环境。
12. `test_12_quick_edit_environment_name.py`：列表快捷修改环境名称。
13. `test_13_sort_environment_serial.py`：环境序号升降序。
14. `test_14_move_remark_column.py`：字段排序-备注调整到首位。

以下 P0-1、P0-2、P0-3 是早期主流程草案，已被上面的环境管理模块用例拆分和覆盖。

### P0-1：环境生命周期

流程：

```text
打开 APP
登录
创建环境
打开环境
关闭环境
```

验证点：

1. APP 能正常启动。
2. 登录成功。
3. 环境创建成功。
4. 新环境能在环境列表中找到。
5. 环境能正常打开。
6. 环境能正常关闭。

### P0-2：内核切换与版本验证

流程：

```text
删除所有非包自带的内核
打开 142 环境
获取内核版本号
下载 134 内核
打开 134 环境
获取内核版本号
```

验证点：

1. 非包自带内核能被清理。
2. 142 环境能正常打开。
3. 能读取 142 环境的内核版本号。
4. 134 内核能正常下载。
5. 134 环境能正常打开。
6. 能读取 134 环境的内核版本号。
7. 两次读取到的版本号符合预期。

注意：

1. 删除内核属于高风险操作，需要限定只删除测试环境内允许删除的内核。
2. 删除前需要确认哪些内核属于包自带内核。
3. 如果无法可靠判断，不应直接执行删除动作。

### P0-3：批量导入

流程：

```text
点击批量导入
点击选择导入文件
选择配置文件中的 xlsx 文件
点击确定
验证是否有导入失败的环境
回到环境列表
遍历列表验证环境数据是否正确
```

验证点：

1. 批量导入入口可点击。
2. 能打开文件选择器。
3. 能选择配置文件中的 `.xlsx` 文件。
4. 导入流程能正常提交。
5. 导入结果中没有失败环境。
6. 环境列表中能找到导入文件中的环境。
7. 环境列表展示的数据与 xlsx 数据一致。

注意：

1. xlsx 文件路径从 `test_data.batch_import.file_dir` 读取。
2. xlsx 文件名从 `test_data.batch_import.file_name` 读取。
3. 实际导入文件完整路径由文件路径和文件名拼接得到。
4. xlsx 内容需要有稳定的测试数据，避免与已有环境冲突。
5. 导入前后建议记录环境数量，辅助判断导入结果。
6. 文件上传方式已验证，当前优先通过隐藏的 DOM `input[type=file]` 设置文件；UIAutomation 文件选择器作为兜底能力保留。

## 九、UI 元素定位方法

元素定位方法按优先级排序：

1. CDP 控制台复制 CSS selector，并人工优化。
2. 使用业务属性、测试属性、唯一文本定位。
3. UIAutomation 抓窗工具定位原生控件。
4. AI 辅助分析元素位置和页面结构。
5. 人工分析 DOM 或控件树。

不推荐：

1. 绝对 XPath。
2. 屏幕坐标。
3. 动态 class。
4. 依赖层级过深的选择器。

## 十、实施阶段

### 阶段 1：框架骨架

预计 1 到 2 天。

目标：

1. 完成项目目录。
2. 完成配置读取。
3. 完成环境预检。
4. 完成日志封装。
5. 完成 APP 启动封装。
6. 完成已有 APP 实例关闭和重新启动。
7. 完成 CDP 连接验证。
8. 完成飞书通知封装。
9. 完成 `unittest` 命令行运行入口。

验收标准：

1. 能读取配置文件。
2. 能执行环境预检并输出结果。
3. 能在启动前关闭已有 Dicloak APP。
4. 能启动 Dicloak APP。
5. 能在 30 秒内检测 APP 进程是否存在。
6. 能优先通过 Playwright 连接 CDP 并获取页面列表。
7. 能发送一条测试飞书通知。
8. 能执行一条空用例并生成日志。
9. 能按约定退出码返回执行结果。

### 阶段 2：P0-1 跑通

预计 0.5 到 1 天。

目标：

1. 完成登录页面对象。
2. 完成环境管理页面对象的基础操作。
3. 跑通环境生命周期用例。

验收标准：

1. 用例能完成登录。
2. 用例能创建环境。
3. 用例能打开并关闭环境。
4. 失败时能输出明确日志和截图。

### 阶段 3：P0-2 和 P0-3 跑通

预计 1 到 2 天。

目标：

1. 完成内核相关页面对象。
2. 完成批量导入页面对象。
3. 跑通内核切换和批量导入用例。

验收标准：

1. 能正确读取内核版本号。
2. 能完成指定内核下载和环境打开。
3. 能选择配置文件中的 xlsx 文件。
4. 能校验导入结果和环境列表数据。

### 阶段 4：稳定性增强

预计 1 天。

目标：

1. 增加失败重试。
2. 增加模块级熔断。
3. 增加失败日志采集。
4. 增加飞书执行总结。

验收标准：

1. 登录失败时触发熔断。
2. CDP 连接失败时触发熔断。
3. P0 失败时发送飞书。
4. 执行结果清晰可追踪。

### 阶段 5：长期用例补充

长期任务。

优先级：

1. 环境列表和环境管理。
2. 经常容易出问题的功能。
3. 代理管理。
4. 扩展管理。
5. 环境分组。
6. 成员管理。
7. 其他遗漏场景。

参考资料：

1. 早期主流程用例地址：https://wcnjxlemm9cv.feishu.cn/mindnotes/VBIwbvWgZmdhQTnGZOecfyzrnoe#mindmap
2. 目前已记录的测试用例：https://wcnjxlemm9cv.feishu.cn/drive/folder/M3JWfdQfNlfji4dLXuScrizenrc

## 十一、风险与应对

### 1. 元素定位失效

风险：

APP UI 改版后，元素定位可能大面积失效。

应对：

1. 元素统一维护在 `locators/`。
2. 优先使用稳定属性。
3. 关键流程元素变更后优先修复页面对象，不逐个修改用例。
4. 推动前端增加自动化测试专用属性。

### 2. CDP 页面选择不稳定

风险：

Electron 可能暴露多个页面，自动化连接错页面会导致操作失败。

应对：

1. 通过 URL、标题、页面关键元素综合判断目标页面。
2. 在配置中支持 `default_page_url_keyword`。
3. 连接后先执行页面健康检查。

### 3. 文件选择器不稳定

风险：

批量导入需要操作 Windows 文件选择器，容易受焦点和窗口层级影响。

应对：

1. 优先尝试 CDP 或 DOM input 上传文件能力。
2. 如果必须使用系统文件选择器，则使用 UIAutomation 封装。
3. 操作前确认文件路径存在。
4. 失败时截图并输出窗口控件信息。

### 4. 用例数据污染

风险：

自动化创建或导入的数据可能影响下一轮执行。

应对：

1. 测试环境名称使用统一前缀。
2. 用例执行前清理同前缀历史数据。
3. 用例执行后按需清理测试数据。
4. 删除操作必须限定范围，避免误删真实数据。

### 5. 重试掩盖真实问题

风险：

重试可能让偶现问题不容易被发现。

应对：

1. 每次重试都写日志。
2. 最终通过但发生过重试的用例，在结果中标记为 flaky。
3. 断言失败默认不盲目重试。

## 十二、维护原则

1. 自动化框架本身应尽量稳定，日常维护重点是页面元素和测试数据。
2. 用例只描述业务流程，不直接写复杂定位和底层操作。
3. 页面对象只封装页面行为，不写测试断言。
4. 断言尽量写在测试用例层，便于看清业务验证点。
5. 公共能力放在 `core/`，不要散落在页面对象中。
6. 每次 APP UI 改动后，优先运行 P0 用例确认主流程。
7. 新增用例前先确认是否已有页面对象方法可复用。
8. 对高风险操作，例如删除内核、删除环境，需要增加保护条件。

## 十三、第一版交付清单

第一版建议交付以下内容：

1. 项目目录结构。
2. 配置模板。
3. 环境预检能力。
4. APP 启动、关闭和已有实例处理能力。
5. APP 进程 30 秒检测能力。
6. CDP 连接能力。
7. UIAutomation 基础能力。
8. 日志系统。
9. 飞书通知。
10. 失败重试。
11. 模块级熔断。
12. 页面对象模板。
13. 导入导出文件完整路径校验。
14. 用例数据后置清理机制。
15. 环境管理模块 14 条 P0 用例。
16. 命令行运行入口和退出码规则。
17. README 使用说明。

第一版不强制包含：

1. 完整 HTML 测试报告。
2. 所有 P1 用例。
3. CI/CD 集成。
4. 测试数据管理平台。
5. 复杂可视化看板。
6. 带 UI 的启动界面。

这些内容可在 P0 稳定后再逐步补充。
