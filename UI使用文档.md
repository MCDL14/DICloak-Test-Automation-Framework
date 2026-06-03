# Dicloak 自动化测试 UI 界面 — 使用与接手文档

> 版本：1.3  
> 最后更新：2026-06-03  
> 适用对象：接手本 UI 模块的开发者 / 日常使用 UI 的测试人员

---

## 一、概述

本 UI 界面是基于 **Streamlit** 构建的轻量级 Web 控制台，作为 Dicloak 自动化测试框架的**附加功能模块**，提供：

- 用例发现、按模块筛选、批量选择
- 一键运行选中的用例，**实时流式**查看执行日志
- 执行完成后自动解析结果统计（总计/通过/失败/错误/跳过/通过率）
- 浏览历史运行记录（从 `logs/` 目录解析）

**核心原则**：UI 模块**不修改任何现有代码**（`core/`、`run.py`、`tests/` 均保持不变）。原有命令行执行方式（`python run.py`）完全不受影响。

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
│  以下为项目原有文件，UI 未做任何改动：
├── run.py                     # 原有 CLI 入口
├── core/                      # 核心框架（runner.py, result.py, feishu.py 等）
├── tests/                     # 测试用例
├── pages/                     # Page Object 类（不被 Streamlit 识别）
├── config/                    # 配置文件
├── logs/                      # 运行日志
└── ...
```

**新增文件清单**（共 4 个）：

| 文件 | 用途 | 是否依赖现有模块 |
|---|---|---|
| `streamlit_runner.py` | 用例发现、执行、飞书通知 | 复用 `core/` 全部能力 |
| `ui/app.py` | 仪表盘入口 + 多页面注册 | 只读 `core/config.py` |
| `ui/pages/01_执行用例.py` | 用例选择 + 执行页 | 调用 `streamlit_runner.py` |
| `ui/pages/02_运行历史.py` | 历史记录浏览页 | 只读 `logs/` 目录 |

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

在终端按 `Ctrl+C` 即可。

---

## 四、页面功能说明

### 4.1 仪表盘（ui/app.py）

![仪表盘]

- **左侧栏**：显示当前配置状态（账号名）
- **主区域**：动态统计各模块用例数量 + 快速入口链接
- **导航**：点击 "执行用例" / "运行历史" 跳转到对应页面

### 4.2 执行用例（ui/pages/01_执行用例.py）

这是最核心的页面，功能包括：

#### 步骤 1：筛选模块
- 左侧栏 "筛选模块" 多选框：取消勾选不需要的模块
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
- 后台线程执行，前台**实时流式**显示日志（最多保留 200 行）
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
- 默认显示最近 50 条，点击 "加载更多" 翻页
- 左侧栏可勾选 "只显示失败的运行" 进行筛选
- 每条记录展开后显示 6 个指标卡片 + "查看完整日志" 按钮

---

## 五、如何添加新页面

Streamlit 多页面采用**文件即页面**机制，步骤：

1. 在 `ui/pages/` 目录新建 `.py` 文件，例如 `ui/pages/03_data_report.py`
2. 文件开头写 `st.set_page_config(page_title="数据报表", page_icon="📊", layout="wide")`
3. 编写页面内容（纯 Python + `st.*` API）
4. 在 `ui/app.py` 添加导航入口：
   ```python
   st.page_link("ui/pages/03_data_report.py", label="📊 数据报表", icon="📊")
   ```
5. 重启 `streamlit run ui/app.py`

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

### 7.1 为什么不修改 core/ 或 run.py？

这是**第 1 条需求**。所有 UI 代码都是新增文件，通过 `import` 复用核心模块的**公开 API**（`AutomationRunner`、`AutomationTextRunner`、`FeishuNotifier` 等）。`run.py` 的 CLI 流程完全不受影响。

### 7.2 为什么需要一个共享执行器（streamlit_runner.py）？

这是**第 2 条需求**（飞书通知不能丢）。如果直接在 Streamlit 页面里调用 `unittest.TextTestRunner`，会丢失：

- 恢复钩子（`TestRecoveryManager`）
- 失败截图（`capture_failure_screenshot`）
- 飞书通知（`FeishuNotifier.send_summary()`）
- APP/CDP 生命周期管理

`streamlit_runner.py` 完整复现了 `AutomationRunner.run()` 的执行流水线，确保 UI 执行和 CLI 执行的行为一致。

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
3. `pages/01_run_tests.py` 在前台轮询 queue，每收到一条消息就刷新日志显示
4. 后台线程放入 `None` 作为哨兵，前台收到后停止轮询

### 7.5 为什么选择 Streamlit？

对比方案：

| 方案 | 模块化 | 迭代便捷 | 无 HTML/CSS | 总评 |
|---|---|---|---|---|
| Flask + HTML | 需手写路由 | 需前后端联动 | ❌ | 一般 |
| FastAPI + Vue | 过于重量级 | 前后端分离 | ❌ | 太重 |
| **Streamlit** | **文件即页面** | **纯 Python** | **✅** | **最优** |

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

### Q2: 执行用例时卡住没有日志

检查：
1. DICloak APP 是否已打开（默认是"连接已打开的 APP"模式）
2. CDP 调试端口是否匹配（默认 9222）
3. 查看终端是否有 CDP 连接错误日志

### Q3: 执行完成后没有飞书通知

检查 `config/config.yaml` 中 `feishu.webhook_url` 是否配置正确。

### Q4: 如何同时保留 CLI 和 UI 两种执行方式？

两者互不干扰：
- CLI：`python run.py`（和以前完全一样）
- UI：`streamlit run ui/app.py`

### Q5: 如何修改日志流式显示的保留行数？

在 `ui/pages/01_执行用例.py` 中修改 `log_lines[-200:]` 的数字。

### Q6: Streamlit 端口被占用？

```bash
streamlit run ui/app.py --server.port 8502
```

### Q7: 页面一直 loading 不显示内容？

可能是 `streamlit_runner.py` 中 `discover_cases()` 扫描用例时出错。在终端查看报错信息。

---

## 十、版本历史

| 版本 | 日期 | 变更内容 |
|---|---|---|
| 1.3 | 2026-06-03 | 首页用例数量改为动态统计；执行页模块级全选改为显式按钮，避免覆盖单条选择；`streamlit` 纳入 `requirements.txt` |
| 1.2 | 2026-06-02 | 页面文件改为中文名，菜单直接显示中文 |
| 1.0 | 2026-05-22 | 初始版本：仪表盘 + 执行用例 + 运行历史 |
