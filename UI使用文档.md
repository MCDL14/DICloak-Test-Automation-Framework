# Dicloak 自动化测试 UI 界面 — 使用与接手文档

> 版本：1.9
> 最后更新：2026-06-08
> 适用对象：接手本 UI 模块的开发者 / 日常使用 UI 的测试人员

---

## 一、概述

本 UI 界面是基于 **Streamlit** 构建的轻量级 Web 控制台，作为 Dicloak 自动化测试框架的**附加功能模块**，提供：

- 用例发现、按模块筛选、批量选择
- 一键运行选中的用例，**实时流式**查看执行日志
- 执行完成后自动解析结果统计（总计/通过/失败/错误/跳过/通过率）
- 浏览历史运行记录（从 `logs/` 目录解析）
- UI 执行复用 CLI 的恢复、截图、重试、flaky 统计和飞书通知链路

**核心原则**：UI 模块不复制自动化执行链路，优先复用 `core/` 的既有能力；如需扩展 `core/`，只做向后兼容的通用增强。原有命令行执行方式（`python run.py`）和 `run.py` 入口语义保持不变。

当前 UI 用例发现应能读取到 58 条 P0 用例：环境管理 25 条、全局设置 12 条、环境分组管理 6 条、成员管理 15 条。

---

## 二、文件结构

```
DICloak自动化框架/
├── streamlit_runner.py       # ★ 共享执行器（UI 专用，复用核心能力）
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

`streamlit` 已纳入项目依赖；如只需要补装 UI 依赖，也可以单独执行 `pip install streamlit`。

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

#### 步骤 1：筛选模块
- 左侧栏 "筛选模块" 多选框：取消勾选不需要的模块
- "搜索用例" 输入框：按模块、测试类、测试方法或完整 test_id 缩小当前展示范围
- "全选"/"取消全选" 按钮：批量操作所有用例

#### 步骤 2：选择用例
- 每个模块是一个折叠面板（≤3 条用例默认展开）
- 面板内有 "选中本模块" / "取消本模块" 按钮 + 每条用例的独立 checkbox
- 勾选状态在切换面板时**不会丢失**（存在 session_state）
- 单条用例取消勾选后，不会被模块级按钮之外的渲染流程自动改回选中

#### 步骤 3：选择运行模式
- **连接已打开的 APP**（默认勾选）：连接已手动启动的 DICloak APP
- **取消勾选**：框架自动启动新 APP

#### 步骤 4：执行
- 点击 "▶ 运行选中（N 条）" 按钮
- 后台线程执行，前台**实时流式**显示日志（固定高度展示，最多保留 200 行）
- 执行完成后自动展示：
  - **6 个指标卡片**：总计、通过、失败、错误、跳过、通过率
  - **失败/错误详情**：展开面板列出 FAIL/ERROR 行

#### 飞书通知
- 使用 UI 执行时，失败/错误**照常发送飞书通知**，与 `python run.py` 行为一致
- 通知由 `streamlit_runner.py` 内部调用 `FeishuNotifier.send_summary()` 完成

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
  │         └─ core/cdp_driver.py   #   CDPDriver（CDP 连接）
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

---

## 十、边界与后续计划

### 10.1 当前定位

- 当前 UI 是本地自动化执行控制台，用于日常调试、选择用例、查看实时日志和浏览历史记录。
- 当前 UI 不是多人测试平台，没有用户认证、权限隔离、远程任务队列或运行记录数据库。
- 当前执行模型是单 Streamlit 进程内串行执行；跨进程的 CLI/UI 并发需要人工避免。
- 当前历史页只读取 `logs/run_*.log`，不维护独立任务状态表。

### 10.2 后续优先级

1. 运行历史页增加模块筛选和失败详情搜索。
2. 执行用例页增加按测试 ID 精确粘贴选择。
3. 增加执行中取消任务能力，但必须同步设计 APP/CDP 清理和业务数据清理策略。
4. 如果需要多人或远程使用，引入任务队列、跨进程执行锁、用户权限和持久化运行记录。
5. 将 UI 冒烟验证纳入固定检查项：启动服务、确认首页/执行页/历史页 HTTP 200、确认用例发现数量、关闭服务并确认端口释放。

---

## 十一、版本历史

| 版本 | 日期 | 变更内容 |
|---|---|---|
| 1.9 | 2026-06-08 | 同步当前 P0 用例发现数量为 58 条；成员管理已包含 15 条用例，四条成员 open API 用例具备接口非 200 重试和异常兜底恢复能力 |
| 1.8 | 2026-06-08 | 执行页实时日志区域改为固定高度展示，避免运行时随日志长度不断撑高页面 |
| 1.7 | 2026-06-04 | 补充 Windows 后台进程停止 UI 的方式；记录 UI 冒烟验证应覆盖启动、页面访问、用例发现和服务关闭 |
| 1.6 | 2026-06-04 | 执行页增加用例搜索；执行异常时按预检失败、APP/CDP 失败、执行器异常等场景展示更明确状态；运行历史页增加关键词、来源和日期范围筛选，并改为按日志文件修改时间倒序 |
| 1.5 | 2026-06-04 | 优化自动化日志：`setup_logger()` 默认复用当前运行 handler，避免用例 `setUpClass()` 拆散主日志；运行入口显式 reset 新建日志；用例结果层统一写入 CASE START/PASS/FAIL/ERROR/SKIP 和耗时；历史页日志按钮根据文件大小显示完整日志或末尾预览 |
| 1.4 | 2026-06-04 | UI 执行复用 CLI `_run_suite()`，保持重试/flaky 行为一致；用例发现使用独立 logger，避免刷新页面清空运行日志 handler；UI 执行增加进程级串行锁；首页和执行页增加配置/发现失败兜底；历史页增强 unittest fallback 解析；修正 `page_link` 路径说明 |
| 1.3 | 2026-06-03 | 首页用例数量改为动态统计；执行页模块级全选改为显式按钮，避免覆盖单条选择；`streamlit` 纳入 `requirements.txt` |
| 1.2 | 2026-06-02 | 页面文件改为中文名，菜单直接显示中文 |
| 1.0 | 2026-05-22 | 初始版本：仪表盘 + 执行用例 + 运行历史 |
