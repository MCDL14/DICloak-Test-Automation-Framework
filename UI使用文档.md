# Dicloak 自动化测试 UI 界面 — 使用与接手文档

> 版本：2.3
> 最后更新：2026-06-16
> 适用对象：接手本 UI 模块的开发者 / 日常使用 UI 的测试人员

---

## 一、概述

本 UI 界面是基于 **Streamlit** 构建的轻量级 Web 控制台，作为 Dicloak 自动化测试框架的**附加功能模块**，提供：

- 用例发现、按模块筛选、批量选择
- 一键运行选中的用例，**实时流式**查看执行日志
- 执行完成后自动解析结果统计（总计/通过/失败/错误/跳过/通过率）
- 浏览历史运行记录（从 `logs/` 目录解析）
- UI 执行复用 CLI 的恢复、截图、重试、flaky 统计和飞书通知链路
- 通过 SSH 在内网 Linux/macOS 节点远程执行 CLI，并实时查看远端日志

**核心原则**：UI 模块不复制自动化执行链路，优先复用 `core/` 的既有能力；如需扩展 `core/`，只做向后兼容的通用增强。原有命令行执行方式（`python run.py`）和 `run.py` 入口语义保持不变。

当前 UI 用例发现应能读取到 59 条 P0 用例：环境管理 25 条、全局设置 12 条、环境分组管理 6 条、成员管理 15 条、代理管理 1 条。

---

## 二、文件结构

```
DICloak自动化框架/
├── streamlit_runner.py       # ★ 共享执行器（UI 专用，复用核心能力）
├── core/remote_runner.py      # ★ SSH 远程执行器（供 UI 远程节点模式使用）
├── ui/                       # ★ UI 模块（与项目 pages/ 隔离）
│   ├── app.py                #   UI 主入口（仪表盘）
│   └── pages/                #   Streamlit 自动发现的子页面
│       ├── 01_执行用例.py    #   执行用例页面
│       └── 02_运行历史.py    #   运行历史页面
├── UI使用文档.md              # ★ 本文档
│
│  以下为 UI 复用或做过向后兼容扩展的项目文件：
├── run.py                     # CLI 入口，显式 reset 本次运行日志
├── core/                      # 核心框架（runner.py, result.py, logger.py 等）
├── tests/                     # 测试用例
├── pages/                     # Page Object 类（不被 Streamlit 识别）
├── config/                    # 配置文件
├── logs/                      # 运行日志
└── ...
```

**UI 相关文件：**

| 文件 | 用途 | 是否依赖现有模块 |
|---|---|---|
| `streamlit_runner.py` | 用例发现、执行、飞书通知 | 复用 `core/` 的发现、排序、执行、重试、恢复、截图和通知能力 |
| `core/remote_runner.py` | SSH 远程执行和日志流式回传 | 复用远端 `run.py`，不复制测试执行链路 |
| `ui/app.py` | 仪表盘入口 + 多页面注册 | 只读 `core/config.py` |
| `ui/pages/01_执行用例.py` | 用例选择 + 执行页 | 调用 `streamlit_runner.py` |
| `ui/pages/02_运行历史.py` | 历史记录浏览页 | 只读 `logs/` 目录 |

**核心兼容扩展点：**

| 文件 | 扩展点 | 兼容性说明 |
|---|---|---|
| `core/runner.py` | `_run_suite(stream=None)` 支持注入输出流 | CLI 不传 `stream` 时仍输出到 `sys.stdout` |
| `core/logger.py` | `setup_logger(reset=False)` 默认复用当前 handler | 运行入口显式 `reset=True` 新建本次日志，用例内重复调用不会拆散日志 |
| `core/result.py` | `AutomationTestResult` 统一写入用例级日志 | 所有 CLI/UI 执行都会记录 `CASE START/PASS/FAIL/ERROR/SKIP` 和耗时 |
| `run.py` | CLI 启动时调用 `setup_logger(config, reset=True)` | 保持原 CLI 使用方式不变 |

---

## 三、环境准备

### 3.1 安装依赖

```bash
pip install -r requirements.txt
```

`streamlit` 和远程执行所需的 `paramiko` 已纳入项目依赖；如只需要补装 UI 依赖，也可以单独执行：

```bash
pip install streamlit paramiko
```

### 3.2 启动 UI

在项目根目录执行：

```bash
streamlit run ui/app.py
```

启动后浏览器自动打开 `http://localhost:8501`。

### 3.3 停止 UI

如果是在当前终端前台启动，按 `Ctrl+C` 即可。

如果是通过后台进程启动，先找到监听 8501 端口的进程，再停止：

```powershell
Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue |
    Select-Object LocalAddress,LocalPort,State,OwningProcess

Stop-Process -Id <OwningProcess> -Force
```

停止后再次确认 8501 没有 `Listen` 状态即可。

---

## 四、页面功能说明

### 4.1 仪表盘（ui/app.py）

- **左侧栏**：显示当前配置状态（账号名）
- **主区域**：动态统计各模块用例数量 + 快速入口链接
- **导航**：点击 "执行用例" / "运行历史" 跳转到对应页面

### 4.2 执行用例（ui/pages/01_执行用例.py）

这是最核心的页面，功能包括：

#### 步骤 1：显示与批量选择
- 左侧栏 "显示模块（不影响执行）" 多选框：只控制主区域显示哪些模块
- "搜索显示" 输入框：按模块、测试类、测试方法或完整 test_id 缩小当前列表显示
- 显示设置不会取消用例勾选，也不会改变本机执行范围
- "全选"/"取消全选" 按钮：批量操作所有用例

#### 步骤 2：选择用例
- 每个模块是一个折叠面板（≤3 条用例默认展开）
- 模块标题行直接显示已选数量，并提供 "选中模块" / "取消模块" 按钮
- 不展开模块也能看到模块选中状态，并直接全选或取消该模块
- 折叠面板内保留每条用例的独立 checkbox
- 勾选状态在切换面板时**不会丢失**（存在 session_state）
- 单条用例取消勾选后，不会被模块级按钮之外的渲染流程自动改回选中

#### 步骤 3：选择运行模式
- **执行位置=本机**：按当前勾选用例执行，继续复用本机 APP/CDP 生命周期。
- **执行位置=远程节点**：通过 SSH 登录目标机器，在远端项目目录执行 `python run.py`。
- **连接已打开的 APP**（默认勾选）：连接已手动启动的 DICloak APP
- **取消勾选**：框架自动启动新 APP
- 本机执行使用全部已勾选用例；左侧显示设置只影响列表可见性。
- 远程节点模式支持的运行范围：
  - 远程预检：`python run.py --config <config> --precheck`
  - P0 全量：`python run.py --config <config> --level P0`
  - 按业务模块：`python run.py --config <config> --business-module <name>`
  - 按目录模块：`python run.py --config <config> --module <module>`
  - 按单用例名：`python run.py --config <config> --case <case>`

远程节点模式暂不按左侧勾选的 test id 过滤；请使用主页面“远程节点执行”区域里的远程运行范围。

侧边栏“执行状态”会显示当前 UI 后台任务是否空闲。若用户刷新页面、终止前台轮询或旧任务异常结束后留下残留执行锁，页面会提示“检测到残留执行锁”，此时可点击“解除残留执行锁”后重新执行；如果后台线程仍在运行，则不会允许解除，避免同时抢占 APP/CDP。

远程节点执行区域按操作层级组织：

- 选择节点。
- SSH 连接信息。
- 远端项目/配置状态。
- 代码同步动作。
- 运行范围。
- 执行选项。
- 命令预览。

远程节点模式会展示当前节点状态：

- 节点名称、平台、SSH 地址。
- 当前 UI 连接信息：SSH IP/主机、端口、用户名和本次会话密码状态。
- 远端项目目录、运行配置、Python 命令、虚拟环境激活脚本。
- 认证来源，只显示 `SSH key`、`SSH agent/key` 或 `password_env:<环境变量名>`，不显示真实密码。
- 连接缓存状态；缓存只保存 IP、端口、用户名，不保存密码。
- 代码同步开关、发布目录和保留快照数量。
- 命令预览，用于在启动前确认实际会执行的 `cd <project_dir> && . <venv_activate> && python run.py ...`。

远程连接信息填写：

- 在“远程连接信息”中填写 SSH IP/主机、端口、用户名。
- 可以填写“SSH 密码（本次 UI 会话）”，该密码只保存在当前 Streamlit 会话内存里，不写入 YAML、不写入缓存、不进入日志。
- 勾选“缓存 IP、端口和用户名到本机”后，执行远程操作或点击“保存连接缓存”会写入 `config/remote_connection_cache.yaml`。
- `config/remote_connection_cache.yaml` 已加入 `.gitignore`，用于减少重复输入；密码仍需要每次 UI 会话手动填写，或改用 `password_env` / SSH key。

远程节点模式还提供远端代码管理：

- **检查远端代码**：比较远端当前 `.remote_manifest.json` 和本地当前工作区快照，判断是否会跑旧代码。
- **同步当前代码**：通过 SFTP 把本地当前工作区发布到远端新快照目录，不依赖远端安装 Git。
- **远程执行前同步当前代码**：执行用例前先同步，默认关闭，避免误同步。

同步会保留远端已有 `config/*.yaml` 运行配置和 `.venv`，并排除本地真实配置、远程连接缓存、日志、截图、报告和 `remote_artifacts/`。默认发布目录为 `<project_dir>_releases`，真实规则可通过本机 `config/remote_sync.yaml` 覆盖；示例见 `config/remote_sync.example.yaml`。

远程节点模式还提供“检查远程节点”按钮。该按钮只做只读健康检查，不启动 APP、不执行用例。检查项包括：

- 项目目录是否存在。
- `run.py` 是否存在。
- 远端配置文件是否存在。
- 虚拟环境激活脚本是否存在并可激活。
- Python 版本是否可读取。
- `yaml`、`playwright`、`psutil`、`openpyxl` 是否可导入。
- 远端配置是否可加载。
- 配置解析出的 APP 路径是否存在。

如果远端没有项目，会显示类似：

```text
[FAIL] project_dir missing: /path/to/project
远程健康检查完成 → 失败=1
```

远程节点模式还提供“远程执行后拉取产物”开关，默认开启。执行结束后会通过 SFTP 拉取本次运行开始后修改过的远端：

```text
logs/
screenshots/
reports/
```

本机归档目录：

```text
remote_artifacts/<node-name>/<yyyyMMdd_HHmmss>/
  logs/
  screenshots/
  reports/
```

`remote_artifacts/` 已加入 `.gitignore`，不要提交远程日志、截图或报告。

远程任务结束后，如果日志中包含健康检查、退出码或产物归档信息，执行页会额外展示“远程执行摘要”：

- `[PASS]` / `[FAIL]` 数量。
- 远程退出码和耗时。
- 健康检查失败项数量。
- 远程产物归档目录。
- `[FAIL]` 明细行。

#### 远程节点能力矩阵

执行页会展示 Windows、Linux、macOS 的远程节点能力矩阵，避免不同平台边界混淆：

| 平台 | 远程/本地执行 | CDP 自动化 | APP 托管启动 | 系统代理 | 原生文件选择器 | 产物拉取 | 已验证范围 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Windows | 支持 | 支持 | 支持 | 支持启停和恢复 | 支持 Windows UIAutomation 兜底 | 本机产物直接保留；远程节点可拉取 | Windows P0 主链路，代理检测受外部代理连通性影响 |
| Linux | 支持 SSH 远程 CLI | 支持 | 已验证 | 暂不支持自动启停；代理管理继续执行业务流程 | 暂不支持 | 支持 `logs/screenshots/reports` | `precheck`、`environment_group_management`、`member_management`、`global_settings` 主流程；Web Store 安装检查仍受外部网络影响 |
| macOS | 支持 SSH 远程 CLI | 支持 | 按远端配置和图形会话分层验证 | 暂不支持自动启停；代理管理不跳过 | 暂不支持 | 支持 `logs/screenshots/reports` | P0 全量、`environment_group_management`、代理管理业务流程 |

#### 步骤 4：执行
- 点击 "▶ 运行选中（N 条）" 按钮
- 后台线程执行，前台**实时流式**显示日志（固定高度展示，最多保留 200 行）
- 执行完成后自动展示：
  - **6 个指标卡片**：总计、通过、失败、错误、跳过、通过率
  - **失败/错误详情**：展开面板列出 FAIL/ERROR 行

#### 飞书通知
- 使用 UI 执行时，失败/错误**照常发送飞书通知**，与 `python run.py` 行为一致
- 通知由 `streamlit_runner.py` 内部调用 `FeishuNotifier.send_summary()` 完成

### 4.4 远程节点配置

复制示例文件：

```bash
cp config/remote_hosts.example.yaml config/remote_hosts.yaml
```

`config/remote_hosts.yaml` 已加入 `.gitignore`，用于保存节点模板。SSH IP、端口、用户名可以直接在 UI 中填写并缓存到 `config/remote_connection_cache.yaml`；该缓存同样已加入 `.gitignore`，且不保存密码。示例：

```yaml
hosts:
  - name: macos-arm64
    enabled: true
    platform: macos
    host: 192.168.40.5
    port: 22
    username: tianji
    project_dir: /Users/tianji/dicloak_automation_mac
    python: python
    config: config/config.macos.yaml
    venv_activate: .venv/bin/activate
    password_env: DICLOAK_REMOTE_MAC_PASSWORD
    key_filename: ""
    command_prefix: ""
```

配置说明：

- `project_dir`：远端项目目录，目录内必须有 `run.py`。
- `venv_activate`：远端虚拟环境激活脚本；配置后执行器会先 `cd project_dir && . venv_activate`。
- `python`：远端运行命令中的 Python，可配 `python` 或绝对路径。
- `config`：远端自动化配置文件路径，相对 `project_dir`。
- `password_env`：本机环境变量名，密码只从环境变量读取，不写入 YAML。
- `key_filename`：SSH key 路径；推荐优先使用 SSH key。

UI 连接信息优先级：

1. UI 中填写的 SSH IP/端口/用户名会覆盖 `remote_hosts.yaml` 中的默认连接信息。
2. UI 中填写的临时密码优先用于本次远程操作。
3. 如果 UI 密码为空，则继续使用 `password_env`、`key_filename` 或 SSH agent/key。
4. 本机连接缓存 `config/remote_connection_cache.yaml` 只作为下次打开 UI 时的默认填充值，不保存密码。

Windows PowerShell 临时设置密码环境变量示例：

```powershell
$env:DICLOAK_REMOTE_MAC_PASSWORD = "<password>"
streamlit run ui/app.py
```

远程日志会在进入 UI 前做基础脱敏，当前会隐藏 `apiSecret`、`BOOT_TOKEN`、`USER_PASSWD`、`password`、`token` 等字段。

### 4.3 运行历史（ui/pages/02_运行历史.py）

- 自动扫描 `logs/` 目录下的 `run_*.log` 文件
- 支持两种日志格式：
  - **CLI 格式**：`Final test summary: total=... passed=... failed=...`
  - **UI 格式**：`运行完成 → 总计=... 通过=...`
- 默认按日志文件修改时间倒序显示最近 50 条，点击 "加载更多" 翻页
- 左侧栏支持按失败状态、关键词、来源和日期范围筛选
- 每条记录展开后显示 6 个指标卡片 + "查看完整日志" 按钮
- 自动化日志包含用例级 `CASE START`、`CASE PASS`、`CASE FAIL`、`CASE ERROR`、`CASE SKIP` 和耗时，便于从历史页定位具体用例过程

---

## 五、如何添加新页面

Streamlit 多页面采用**文件即页面**机制，步骤：

1. 在 `ui/pages/` 目录新建 `.py` 文件，例如 `ui/pages/03_data_report.py`
2. 文件开头写 `st.set_page_config(page_title="数据报表", page_icon="📊", layout="wide")`
3. 编写页面内容（纯 Python + `st.*` API）
4. 在 `ui/app.py` 添加导航入口：
   ```python
   st.page_link("pages/03_data_report.py", label="📊 数据报表", icon="📊")
   ```
5. 重启 `streamlit run ui/app.py`

注意：`st.page_link()` 的路径相对 Streamlit 入口 `ui/app.py`，所以应写 `pages/xxx.py`，不要写 `ui/pages/xxx.py`。

**不需要**写任何 HTML/CSS/JS，不需要注册路由。

---

## 六、如何调整 UI 排布

### 6.1 调整卡片位置

```python
# 当前是 6 列指标卡片
cols = st.columns(6)
cols[0].metric("📊 总计", total)
cols[1].metric("✅ 通过", passed)
# ...

# 改为 3 列 2 行：
cols = st.columns(3)
cols[0].metric("📊 总计", total)
cols[1].metric("✅ 通过", passed)
cols[2].metric("❌ 失败", failed)
cols2 = st.columns(3)
cols2[0].metric("⚠️ 错误", errors)
# ...
```

### 6.2 调整侧边栏

直接在 `with st.sidebar:` 块内增删 `st.*` 组件即可，调整顺序就是调整调用顺序。

### 6.3 调整模块折叠面板

在 `ui/pages/01_执行用例.py` 中修改 `expanded` 参数：

```python
# 当前：≤3 条用例默认展开
expanded=len(mod_cases) <= 3

# 改为：始终折叠
expanded=False

# 改为：始终展开
expanded=True
```

### 6.4 修改页面标题/图标

在各自页面的 `st.set_page_config(...)` 中修改即可。

---

## 七、关键设计决策说明

### 7.1 为什么 UI 只做兼容扩展？

UI 的价值是选择用例、实时展示日志和浏览历史，不应该重新实现一套自动化执行器。1.4 版本对 `AutomationRunner._run_suite()` 增加了可选 `stream` 参数，这是向后兼容扩展：CLI 未传入时仍输出到 `sys.stdout`，UI 传入队列流后可以实时展示日志。`run.py` 的 CLI 流程完全不受影响。

### 7.2 为什么需要一个共享执行器（streamlit_runner.py）？

设计目标是让 UI 执行不绕开核心自动化链路。如果直接在 Streamlit 页面里调用 `unittest.TextTestRunner`，会丢失：

- 恢复钩子（`TestRecoveryManager`）
- 失败截图（`capture_failure_screenshot`）
- 飞书通知（`FeishuNotifier.send_summary()`）
- APP/CDP 生命周期管理

`streamlit_runner.py` 复用 `AutomationRunner` 的用例发现、优先级排序、APP/CDP 生命周期和 `_run_suite()` 执行入口，确保 UI 执行和 CLI 执行在恢复钩子、失败截图、重试、flaky 统计和飞书通知上保持一致。

### 7.3 为什么 UI 代码放在 ui/ 子目录？

项目原有的 `pages/` 目录存放的是 Page Object 类（`login_page.py`、`member_page.py` 等），
如果 Streamlit 入口放在项目根目录，它会自动把 `pages/` 下的**所有** `.py` 文件注册为导航页面，
导致菜单中出现十几个无关的 "page" 条目。

将 UI 代码放在 `ui/` 子目录后：
- Streamlit 只识别 `ui/pages/` 下的页面文件
- 项目原有的 `pages/`（Page Object）完全不受影响

### 7.4 实时日志流是如何实现的？

采用 **线程 + 队列** 模式：

1. `streamlit_runner.py` 在后台线程中执行用例
2. 自定义 `_QueueStream`（IO 流）和 `_QueueLogHandler`（日志 Handler）将输出推送到 `queue.Queue`
3. `ui/pages/01_执行用例.py` 在前台轮询 queue，每收到一条消息就刷新日志显示
4. 后台线程放入 `None` 作为哨兵，前台收到后停止轮询
5. 如果后台线程仍存活但长时间没有新日志，页面会提示可能存在 APP/CDP 或系统弹窗卡住，方便人工排查
6. `streamlit_runner.py` 使用进程级执行锁，避免多个 UI 会话同时抢占同一个 APP/CDP 和全局 logger

远程节点模式复用同一套队列展示机制，但后台线程改为：

1. 读取 `config/remote_hosts.yaml`。
2. 使用 `core.remote_runner` 通过 SSH 执行远端 CLI。
3. 按行读取远端 stdout/stderr，脱敏后推送到 UI。
4. 解析远端 CLI 的 `Final test summary: total=...` 摘要并展示指标卡片。

健康检查也使用同一套 SSH 与队列机制，但执行的是只读 shell 检查脚本，输出 `[PASS]` / `[FAIL]` 明细和 `远程健康检查完成 → 失败=N` 汇总。

远程产物拉取在远程命令结束后执行，通过 SFTP 遍历远端 `logs`、`screenshots`、`reports`，只复制本次运行开始时间之后修改的文件。拉取失败不会覆盖远程用例执行结果，会在 UI 日志中显示“远程产物拉取失败”。

### 7.5 为什么选择 Streamlit？

对比方案：

| 方案 | 模块化 | 迭代便捷 | 无 HTML/CSS | 总评 |
|---|---|---|---|---|
| Flask + HTML | 需手写路由 | 需前后端联动 | ❌ | 一般 |
| FastAPI + Vue | 过于重量级 | 前后端分离 | ❌ | 太重 |
| **Streamlit** | **文件即页面** | **纯 Python** | **✅** | **适合当前本地控制台阶段** |

---

## 八、依赖关系图

```
ui/app.py                          # 仪表盘入口
  ├─ ui/pages/01_执行用例.py         # 执行用例页
  │    └─ streamlit_runner.py       # 共享执行器 ★ 核心（项目根目录）
  │         ├─ core/runner.py       #   AutomationRunner（用例发现/排序）
  │         ├─ core/result.py       #   AutomationTextRunner + RunResult
  │         ├─ core/feishu.py       #   FeishuNotifier（飞书通知）
  │         ├─ core/precheck.py     #   EnvironmentPrechecker
  │         ├─ core/app.py          #   AppManager（APP 生命周期）
  │         ├─ core/cdp_driver.py   #   CDPDriver（CDP 连接）
  │         └─ core/remote_runner.py #  SSH 远程执行器
  └─ ui/pages/02_运行历史.py         # 运行历史页
       └─ logs/*.log                #   直接读取日志文件
```

---

## 九、常见问题

### Q1: UI 启动后报 "配置加载失败"

确认 `config/config.yaml` 存在且格式正确。
如果首页用例统计或执行页用例发现失败，先运行：

```bash
python run.py --config config/config.yaml --precheck
```

### Q2: 执行用例时卡住没有日志

检查：
1. DICloak APP 是否已打开（默认是"连接已打开的 APP"模式）
2. CDP 调试端口是否匹配（默认 9222）
3. 查看终端是否有 CDP 连接错误日志

### Q3: 执行完成后没有飞书通知

检查 `config/config.yaml` 中 `feishu.webhook_url` 是否配置正确。

### Q4: 如何同时保留 CLI 和 UI 两种执行方式？

两种入口互相独立：
- CLI：`python run.py`（和以前完全一样）
- UI：`streamlit run ui/app.py`

注意：CLI 和 UI 不建议同时对同一个 APP、CDP 端口、测试账号或业务数据执行自动化。UI 的 `_RUN_LOCK` 只保证同一 Streamlit 进程内串行执行，不能阻止另一个终端同时运行 CLI。

### Q5: 如何修改日志流式显示的保留行数？

在 `ui/pages/01_执行用例.py` 中修改：

- `_LOG_DISPLAY_LINES`：实时日志最多保留行数。
- `_LOG_DISPLAY_HEIGHT`：实时日志展示区域固定高度，单位为像素。

### Q6: Streamlit 端口被占用？

```bash
streamlit run ui/app.py --server.port 8502
```

### Q7: 页面一直 loading 不显示内容？

可能是 `streamlit_runner.py` 中 `discover_cases()` 扫描用例时出错。在终端查看报错信息。

### Q8: 远程节点列表为空？

确认已经创建 `config/remote_hosts.yaml`，且至少有一个节点 `enabled: true`。不要把真实密码写进 YAML；使用 `password_env` 或 `key_filename`。

### Q9: 远程预检提示缺少 Python 包？

优先检查远端节点是否配置了正确的 `venv_activate`。本轮 Mac 验证曾发现直接使用 pyenv Python 会缺少 `PyYAML`，改为激活远端 `.venv/bin/activate` 后预检通过。

### Q10: 远端没有项目会怎么样？

点击“检查远程节点”会提前失败并提示 `[FAIL] project_dir missing: <path>`。如果直接远程执行，也会在 `cd <project_dir>` 阶段失败。可以先点击“同步当前代码”创建远端快照和项目软链接；但同步不会自动创建 `.venv` 或真实 `config/*.yaml`，这些仍需要在远端准备或从旧项目目录保留。

### Q11: 本机提示 CDP 连不上，但 9222 端口能访问？

`/json/version` 能返回只说明 CDP HTTP 入口还在。若日志显示 `ws connected` 后 `BrowserType.connect_over_cdp` 超时，说明 Playwright 没能完成 browser-level CDP attach，当前 APP/CDP 会话通常需要重启。框架不再把 raw websocket 当作页面自动化兜底，因为它不能提供 Playwright `page`，后续页面对象无法点击、输入或截图。

---

## 十、边界与后续计划

### 10.1 当前定位

- 当前 UI 是本地自动化执行控制台，用于日常调试、选择用例、查看实时日志和浏览历史记录。
- 当前 UI 已支持单机进程内的 SSH 远程节点执行，但不是多人测试平台，没有用户认证、权限隔离、远程任务队列或运行记录数据库。
- 当前执行模型是单 Streamlit 进程内串行执行；跨进程的 CLI/UI 并发需要人工避免。
- 当前历史页只读取 `logs/run_*.log`，不维护独立任务状态表。
- 远程节点模式支持 SFTP 快照同步当前代码，但不安装依赖、不创建真实运行配置；远端虚拟环境、APP 图形会话和配置文件仍需提前准备好。
- 远程执行摘要优先展示最终用例统计；失败/错误详情只聚焦用例失败块和 unittest 错误块，避免把远端浏览器 stderr 噪声误当作用例失败详情。
- 远程运行范围默认为“远程预检”，该模式只检查远端环境，不运行用例；执行按钮会随范围显示“执行远程预检”“远程执行 P0 全量”等文案，避免误把预检当作全量执行。

### 10.2 后续优先级

1. 运行历史页增加模块筛选和失败详情搜索。
2. 执行用例页增加按测试 ID 精确粘贴选择。
3. 增加执行中取消任务能力，但必须同步设计 APP/CDP 清理和业务数据清理策略。
4. 远程节点代码同步继续补充回退入口和同步历史展示。
5. 如果需要多人使用，引入任务队列、跨进程执行锁、用户权限和持久化运行记录。
6. 将 UI 冒烟验证纳入固定检查项：启动服务、确认首页/执行页/历史页 HTTP 200、确认用例发现数量、关闭服务并确认端口释放。

---

## 十一、版本历史

| 版本 | 日期 | 变更内容 |
|---|---|---|
| 2.9 | 2026-06-18 | 远程执行按钮按运行范围动态显示文案：预检明确显示“执行远程预检”，P0 显示“远程执行 P0 全量”，并补充预检不运行用例的提示 |
| 2.8 | 2026-06-17 | 补充 Mac UI 远程同步后 P0 全量验证；远程执行摘要改为优先读取最终用例统计，失败/错误详情聚焦用例失败块，减少浏览器 stderr 噪声干扰 |
| 2.7 | 2026-06-17 | 执行页优化显示筛选、模块级选择和远程节点布局：显示模块/搜索显示仅影响列表可见性，模块标题行可直接选中或取消模块，远程节点执行区按节点、SSH、状态、同步、范围、选项和命令预览分组 |
| 2.6 | 2026-06-17 | 远程节点模式新增 UI 连接信息填写：支持在侧边栏填写 SSH IP、端口、用户名和本次会话密码，并把 IP、端口、用户名缓存到本机 `config/remote_connection_cache.yaml`；密码不落盘 |
| 2.5 | 2026-06-17 | 远程节点模式新增“检查远端代码”“同步当前代码”和“远程执行前同步当前代码”：通过 SFTP 快照发布本地当前工作区到 Linux/macOS 远端，不依赖远端 Git，并保留远端配置、虚拟环境和旧快照 |
| 2.4 | 2026-06-17 | 远程节点模式增强：侧边栏展示节点非敏感配置摘要和远程命令预览；执行结果区展示远程健康检查/退出码/产物归档摘要；新增 Windows/Linux/macOS 远程节点能力矩阵 |
| 2.3 | 2026-06-16 | 补充 Linux 远程节点真实验证：健康检查通过，环境分组模块 `total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0`，远程产物拉取到 `remote_artifacts/linux-ubuntu/20260616_191350`，并确认运行后无 `dicloak/ginsbrowser` 和 CDP 9222 残留 |
| 2.2 | 2026-06-16 | 远程节点模式新增“远程执行后拉取产物”开关，执行后通过 SFTP 拉取本次新增/修改的 `logs`、`screenshots`、`reports` 到 `remote_artifacts/<node>/<timestamp>`；验证 Mac 环境分组模块通过并拉取 run log |
| 2.1 | 2026-06-16 | 远程节点模式新增“检查远程节点”按钮，支持只读检查项目目录、run.py、配置、venv、Python 依赖、配置加载和 APP 路径；验证 Mac 健康检查通过，并验证项目目录缺失时会明确 `[FAIL] project_dir missing` |
| 2.0 | 2026-06-16 | 新增 UI 远程节点模式：通过 SSH 调用远端 `run.py`，支持预检、P0 全量、业务模块、目录模块和单用例名；新增 `config/remote_hosts.example.yaml`、`core/remote_runner.py`，并验证 Mac 远程预检和环境分组模块通过 |
| 1.9 | 2026-06-08 | 同步当前 P0 用例发现数量为 58 条；成员管理已包含 15 条用例，四条成员 open API 用例具备接口非 200 重试和异常兜底恢复能力 |
| 1.8 | 2026-06-08 | 执行页实时日志区域改为固定高度展示，避免运行时随日志长度不断撑高页面 |
| 1.7 | 2026-06-04 | 补充 Windows 后台进程停止 UI 的方式；记录 UI 冒烟验证应覆盖启动、页面访问、用例发现和服务关闭 |
| 1.6 | 2026-06-04 | 执行页增加用例搜索；执行异常时按预检失败、APP/CDP 失败、执行器异常等场景展示更明确状态；运行历史页增加关键词、来源和日期范围筛选，并改为按日志文件修改时间倒序 |
| 1.5 | 2026-06-04 | 优化自动化日志：`setup_logger()` 默认复用当前运行 handler，避免用例 `setUpClass()` 拆散主日志；运行入口显式 reset 新建日志；用例结果层统一写入 CASE START/PASS/FAIL/ERROR/SKIP 和耗时；历史页日志按钮根据文件大小显示完整日志或末尾预览 |
| 1.4 | 2026-06-04 | UI 执行复用 CLI `_run_suite()`，保持重试/flaky 行为一致；用例发现使用独立 logger，避免刷新页面清空运行日志 handler；UI 执行增加进程级串行锁；首页和执行页增加配置/发现失败兜底；历史页增强 unittest fallback 解析；修正 `page_link` 路径说明 |
| 1.3 | 2026-06-03 | 首页用例数量改为动态统计；执行页模块级全选改为显式按钮，避免覆盖单条选择；`streamlit` 纳入 `requirements.txt` |
| 1.2 | 2026-06-02 | 页面文件改为中文名，菜单直接显示中文 |
| 1.0 | 2026-05-22 | 初始版本：仪表盘 + 执行用例 + 运行历史 |
