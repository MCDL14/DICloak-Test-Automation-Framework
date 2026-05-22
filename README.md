# Dicloak 自动化框架

本项目用于 Dicloak Electron APP 的自动化测试。当前框架已具备配置读取、环境预检、APP 生命周期管理、CDP 连接、飞书通知、用例运行编排，以及 P0 环境管理、全局设置、环境分组管理用例执行能力。

## 环境准备

```bash
pip install -r requirements.txt
playwright install chromium
```

当前默认运行配置文件为 `config/config.yaml`，默认测试数据配置文件为 `config/test_data.yaml`。这两个真实配置文件已放入 `.gitignore`，用于填写本机真实路径、账号、飞书 webhook 和测试数据路径。

## 运行方式

```bash
python run.py --config config/config.yaml --precheck
python run.py --config config/config.yaml --level P0
python run.py --config config/config.yaml --level P0 --business-module 环境管理
python run.py --config config/config.yaml --module environment_management
python run.py --config config/config.yaml --module global_settings
python run.py --config config/config.yaml --module environment_group_management
python run.py --config config/config.yaml --module test_02_group_containing_environment.py --attach-existing-app
python run.py --config config/config.yaml --module test_01_kernel_integrity.py
python run.py --config config/config.yaml --module p0/environment_management/test_01_kernel_integrity.py
python run.py --config config/config.yaml --module tests/p0/environment_management/test_01_kernel_integrity.py
python run.py --config config/config.yaml --case test_142_kernel_integrity
```

`--business-module` 用于按业务模块运行用例；当前支持：环境管理、代理管理、扩展管理、环境分组管理、成员管理、全局设置。

`--module` 用于运行单个模块，优先按文件或目录精确发现用例；如果没有找到对应文件或目录，再按模块关键字过滤已发现的用例。

也可以直接使用默认配置路径：

```bash
python run.py --precheck
```

调试时如果 APP 已经手动打开，并且启动时带了 `--remote-debugging-port=9222 --remote-allow-origins=*`，可以让框架只连接已有 APP，不再关闭、启动或结束 APP：

```bash
python run.py --config config/config.yaml --module test_01_kernel_integrity.py --attach-existing-app
```

这个模式只适合本地调试。正式自动化运行仍建议让框架按配置统一管理 APP 生命周期。

## 失败恢复机制

框架已在 `core/result.py` 的 unittest 执行结果层接入用例前后恢复机制，避免某条用例失败后残留弹窗、抽屉、下拉框、遮罩或筛选状态影响下一条用例。

恢复分三层：

- 全局 APP 稳定态恢复：`pages/app_page.py` 只负责选择正确的 Dicloak 主页面、关闭阻塞弹窗/抽屉/下拉浮层、等待加载遮罩消失，并确认 APP 外壳可操作；这一层不进入任何业务模块。
- 模块级恢复：当前环境管理模块通过 `EnvironmentPage.recover_to_module_home()` 进入环境管理列表并清理筛选和选中状态；环境分组管理模块通过 `EnvironmentGroupPage.recover_to_module_home()` 进入环境分组列表并关闭阻塞浮层。后续代理管理、扩展管理、成员管理等模块需要各自实现自己的模块首页恢复入口。
- 用例级清理：具体用例创建的数据仍由用例自己的 `finally` 或后置逻辑清理，因为只有用例知道哪些数据是本次运行创建的。

全局恢复不会强制跳回“环境管理”，所以后续新增其他模块用例时，不会被环境管理页面状态绑死。

## 失败重试机制

框架在 `core/runner.py` 的执行编排层接入用例级重试。`run.retry_times` 表示失败后额外重试次数，例如 `retry_times: 1` 表示最多执行 2 次；`run.retry_interval_seconds` 表示两次尝试之间的等待秒数。

重试按单条 unittest 用例重新加载新的 `TestCase` 实例，并完整执行一轮用例生命周期，所以每次重试都会重新触发：

- `setUpClass` / `setUp`
- `AutomationTestResult.startTest()` 中的用例前恢复
- 用例方法
- `tearDown` / `tearDownClass`
- `AutomationTestResult.stopTest()` 中的用例后恢复

这样第一次失败后残留的弹窗、筛选、选中行、遮罩或模块页面状态，会先经过全局恢复和模块级恢复，再进入下一次尝试。重试后通过的用例会计入 `flaky`，飞书汇总中显示为“重试后通过”。

## 失败截图机制

框架在 `core/result.py` 的 `addFailure` 和 `addError` 阶段接入失败截图，截图会发生在用例后恢复机制之前，尽量保留失败现场。

截图由 `core/screenshot.py` 统一处理，默认通过 `run.screenshot_on_failure: true` 开启，策略如下：

1. 如果当前用例存在可用 CDP，优先通过 Playwright/CDP 截取 APP 页面。
2. 如果 CDP 截图失败，尝试桌面截图。
3. 桌面截图优先使用 `mss`，兼容 Windows 和 macOS。
4. Windows 下如果 `mss` 截图失败，再回退到现有 UIAutomation 桌面截图能力。
5. 所有截图保存到 `screenshots/` 目录。
6. 截图成功后会返回截图路径，写入失败摘要和日志；飞书执行总结中的失败摘要也会带上该路径。

截图失败不会覆盖原始用例失败原因，只会写入 warning 日志并继续执行后续恢复流程。

## 退出码

- `0`：全部通过
- `1`：存在用例失败或异常
- `2`：配置错误或环境预检失败
- `3`：APP 启动失败或 CDP 连接失败，自动化任务取消
- `130`：用户中断

## 配置

复制 `config/config.example.yaml` 为 `config/config.yaml`，复制 `config/test_data.example.yaml` 为 `config/test_data.yaml`。

`config/config.yaml` 只维护运行环境相关配置，例如 APP 路径、CDP、账号、飞书、超时时间、运行控制和日志。`config/test_data.yaml` 只维护用例数据，例如环境名称、导入导出文件、书签、成员导出、抓包工具和本地扩展包路径。

主配置通过 `test_data_file` 指向测试数据文件。路径支持绝对路径，也支持相对项目根目录或当前配置文件目录。

`account.team_name` 用于配置自动化账号必须切换到的团队。外部账号可能拥有多个团队，框架登录后会读取 `localStorage.basic:state.userInfo.orgName` 校验当前团队；如果不是目标团队，会点击账号菜单里的“切换团队”，等待团队列表加载后切换到目标团队。

真实配置文件和真实测试数据文件可能包含敏感信息或本机路径，已在 `.gitignore` 中排除。

## 当前状态

框架基础能力已经搭建到可以加载配置、执行环境预检、发现用例、启动 APP、连接 CDP、发送飞书通知和统计执行结果。当前 `tests/p0` 可发现 53 条 P0 用例：环境管理 25 条、全局设置 12 条、环境分组管理 6 条、成员管理 10 条。

当前已完成并验证环境管理模块 25 条 P0 用例，文件位于 `tests/p0/environment_management/`：

- `test_01_kernel_integrity.py`
- `test_02_create_default_environment.py`
- `test_03_batch_create_environments.py`
- `test_04_create_134_kernel_environment.py`
- `test_05_batch_create_134_kernel_environments.py`
- `test_06_batch_import_environments.py`
- `test_07_edit_environment_name.py`
- `test_08_edit_fixed_open_url.py`
- `test_09_filter_environment_group.py`
- `test_10_filter_environment_remark.py`
- `test_11_top_environment.py`
- `test_12_quick_edit_environment_name.py`
- `test_13_sort_environment_serial.py`
- `test_14_move_remark_column.py`
- `test_15_export_environment.py`
- `test_16_create_multi_group_environment.py`
- `test_17_batch_create_multi_group_environments.py`
- `test_18_edit_single_environment_multi_group.py`
- `test_19_batch_edit_environment_multi_group.py`
- `test_20_create_tag.py`
- `test_21_create_environment_with_tags.py`
- `test_22_batch_create_environments_with_tags.py`
- `test_23_batch_edit_environment_tags.py`
- `test_24_edit_environment_tags.py`
- `test_25_filter_environment_tag.py`

当前全局设置模块已完成并验证 12 条 P0 用例，文件位于 `tests/p0/global_settings/`：

- `test_01_disable_view_password.py`：校验禁止查看网站密码。
- `test_02_disable_browser_devtools.py`：禁止打开浏览器开发者工具。
- `test_03_disable_extension_management.py`：禁止管理/移除扩展，以及从本地安装扩展至浏览器。
- `test_04_disable_member_access_google_extension_pages.py`：禁止成员访问谷歌扩展商店和扩展设置页面。
- `test_05_block_specific_websites_google_and_baidu.py`：禁止访问指定网址-快捷勾选谷歌应用商店、百度，并校验 b 站可正常访问。
- `test_06_allow_specific_website_bilibili.py`：允许访问指定网址-b 站。
- `test_07_disable_packet_capture_software.py`：禁用抓包软件，校验抓包进程存在时禁止打开环境，关闭抓包软件后环境可正常打开。
- `test_08_bookmark_setting_overwrite.py`：书签设置-覆盖，校验上传书签文件覆盖内核现有书签。
- `test_09_bookmark_setting_append.py`：书签设置-追加，校验上传书签文件追加到内核现有书签，并覆盖清空书签。
- `test_10_environment_field_display_limit.py`：环境字段显示限制，校验环境列表只展示指定字段并恢复字段设置能力。
- `test_11_environment_list_pagination_setting.py`：环境列表分页设置，校验固定分页条数后隐藏分页选择器，并可恢复默认分页。
- `test_12_environment_list_sort_limit.py`：环境列表排序设置，校验全局固定排序后隐藏列表排序按钮，并可恢复手动排序。

全局设置模块 2026-05-15 回归曾出现前 4 条用例异常，已定位并修复：复选框脚本中 `checkboxStateSelector` 和 `checkboxInputSelector` 变量未在点击脚本内定义，导致 `ReferenceError`；同时 Chrome Web Store 页面当前会先出现“切换到 Chrome 即可安装扩展程序和主题背景”的前置阻止提示，第三条用例已兼容该稳定阻止证据。最新整模块验证通过：

- `python run.py --config config/config.yaml --module global_settings --attach-existing-app`：`total=12 passed=12 failed=0 errors=0 skipped=0 flaky=0`。

当前已开始编写并验证环境分组管理模块 6 条 P0 用例，文件位于 `tests/p0/environment_group_management/`：

- `test_01_create_environment_group.py`：创建环境分组，校验创建成功后删除并校验删除成功。
- `test_02_group_containing_environment.py`：包含环境的分组，创建分组和归属该分组的环境，通过“包含环境”筛选框校验筛选结果并清除筛选，删除分组时勾选删除分组下环境，并校验分组和环境都被删除。
- `test_03_group_authorized_member.py`：授权成员的分组，创建环境分组后给 `自动化成员1` 追加授权，校验授权成员弹窗和“授权成员”筛选结果，删除分组后校验成员授权环境分组恢复为原始分组。
- `test_04_filter_group_name.py`：环境分组名称筛选，切换筛选模式到“备注”并搜索 `勿动！！！`，校验列表结果均匹配备注后切回“分组名称”并清除筛选。
- `test_05_edit_group_name.py`：修改环境分组名称，记录首个可编辑分组的名称和 ID，修改为 `自动化-修改环境分组名称` 后按 ID 校验，再还原原名称并按 ID 校验。
- `test_06_edit_group_remark.py`：修改环境分组备注，记录首个可编辑分组的备注和 ID，修改为 `自动化-修改环境分组备注` 后按 ID 校验，再还原原备注并按 ID 校验。

环境分组模块的通用元素已统一维护在 `locators/environment_group_locators.yaml`，包括菜单候选、弹层、表单项、筛选模式切换图标、搜索/清除按钮、下拉项、表格行/单元格、行内编辑入口、行内操作候选和授权成员悬浮窗等；页面对象只保留按业务文本、分组 ID、列内容判断的动态逻辑。

当前已开始编写并验证成员管理模块 10 条 P0 用例，文件位于 `tests/p0/member_management/`：

- `test_01_create_external_member.py`：创建外部成员，选择成员分组 `运营组`、环境分组 `未分组`、成员身份 `员工`、上级经理 `外部成员1`，关闭“到期停用”，校验列表字段和编辑弹窗邮箱后删除并校验删除成功。
- `test_02_edit_external_member_name.py`：编辑外部成员名称，将 `外部成员1` 修改为 `自动化-编辑外部成员名称` 后校验列表，再还原并校验。
- `test_03_create_internal_member.py`：创建内部成员，填写登录账号和登录密码，选择成员分组 `运营组`、环境分组 `未分组`、成员身份 `员工`、上级经理 `外部成员1`，关闭“到期停用”，校验列表字段和编辑弹窗账号后删除并校验删除成功。
- `test_04_edit_internal_member_name.py`：编辑内部成员名称，将 `内部成员003` 修改为 `自动化-编辑内部成员名称` 后校验列表，再选择上级经理 `外部成员1` 并还原名称。
- `test_05_filter_member_group.py`：成员分组筛选，先创建临时 `运营组` 外部成员保证筛选结果非空，依次筛选 `运营组`、清空筛选、筛选 `管理组`、清空筛选，并校验列表“所属成员分组”列均匹配筛选值，最后删除临时成员。
- `test_06_filter_member_name.py`：成员名称/ID 筛选，输入 `自动化成员` 并搜索，校验列表成员名称均包含该关键字；清空后输入 `1972494001272483841` 并搜索，校验列表成员 ID 均匹配该 ID。
- `test_07_filter_member_remark.py`：成员备注筛选，通过“更多筛选”抽屉在 `备注` 输入 `必要数据` 并立即筛选，校验列表备注均包含该关键字后清空筛选。
- `test_08_filter_member_login_account_email.py`：登录账号/邮箱筛选，通过“更多筛选”抽屉分别输入 `mcdl003` 和 `oytrhsjwe@tempmail.cn`，筛选后逐行打开编辑弹窗读取登录账号或成员邮箱并校验包含关键字，最后清空筛选。
- `test_09_batch_edit_member_remark.py`：批量编辑成员备注，按原备注定位预置成员，依次校验覆盖备注、追加备注和还原备注，并在失败清理中兜底还原原备注。
- `test_10_export_member.py`：导出成员，按成员名称精确筛选获取 `自动化成员1` 和 `外部成员1` 的 ID 后勾选导出所选成员，校验导出文件名规则、xlsx 表头、导出范围仅包含所选成员、目标成员行和预置文件内容一致，并清理临时导出文件。

最近验证记录：

- `python run.py --config config/config.yaml --module global_settings --attach-existing-app`：2026-05-15 修复全局设置复选框脚本异常和 Chrome Web Store 前置阻止提示兼容后通过，`total=12 passed=12 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_02_group_containing_environment.py --attach-existing-app`：新增“包含环境”筛选校验后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_03_group_authorized_member.py --attach-existing-app`：新增“授权成员的分组”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_04_filter_group_name.py --attach-existing-app`：新增“环境分组名称筛选”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_05_edit_group_name.py --attach-existing-app`：新增“修改环境分组名称”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_06_edit_group_remark.py --attach-existing-app`：新增“修改环境分组备注”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module environment_group_management --attach-existing-app`：整理环境分组统一元素定位后通过，`total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_01_create_external_member.py --attach-existing-app`：新增“创建外部成员”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_02_edit_external_member_name.py --attach-existing-app`：新增“编辑外部成员名称”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_03_create_internal_member.py --attach-existing-app`：新增“创建内部成员”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_04_edit_internal_member_name.py --attach-existing-app`：新增“编辑内部成员名称”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_05_filter_member_group.py --attach-existing-app`：新增“成员分组筛选”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_06_filter_member_name.py --attach-existing-app`：新增“成员名称筛选”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_07_filter_member_remark.py --attach-existing-app`：新增“成员备注筛选”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_08_filter_member_login_account_email.py --attach-existing-app`：新增“登录账号、邮箱筛选”用例后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_01_create_external_member.py --attach-existing-app`：修复成员列表入口会因“团队管理”折叠而找不到“成员列表”后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module member_management --attach-existing-app`：成员管理 10 条用例通过，`total=10 passed=10 failed=0 errors=0 skipped=0 flaky=0`。

已预留代理管理、扩展管理等模块目录，后续新增用例时按业务模块放入对应目录。
