# Dicloak 自动化框架

本项目用于 Dicloak Electron APP 的自动化测试。当前框架已具备配置读取、环境预检、APP 生命周期管理、CDP 连接、飞书通知、用例运行编排和 P0 环境管理用例执行能力。

## 环境准备

```bash
pip install -r requirements.txt
playwright install chromium
```

当前默认配置文件为 `config/config.yaml`。该文件已放入 `.gitignore`，用于填写本机真实路径、账号、飞书 webhook 和测试数据路径。

## 运行方式

```bash
python run.py --config config/config.yaml --precheck
python run.py --config config/config.yaml --level P0
python run.py --config config/config.yaml --level P0 --business-module 环境管理
python run.py --config config/config.yaml --module environment_management
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

## 退出码

- `0`：全部通过
- `1`：存在用例失败或异常
- `2`：配置错误或环境预检失败
- `3`：APP 启动失败或 CDP 连接失败，自动化任务取消
- `130`：用户中断

## 配置

复制 `config/config.example.yaml` 为 `config/config.yaml`，再填写本机真实路径、账号、飞书 webhook 和测试数据路径。

`account.team_name` 用于配置自动化账号必须切换到的团队。外部账号可能拥有多个团队，框架登录后会读取 `localStorage.basic:state.userInfo.orgName` 校验当前团队；如果不是目标团队，会点击账号菜单里的“切换团队”，等待团队列表加载后切换到目标团队。

真实配置文件包含敏感信息，已在 `.gitignore` 中排除。

## 当前状态

框架基础能力已经搭建到可以加载配置、执行环境预检、发现用例、启动 APP、连接 CDP、发送飞书通知和统计执行结果。

当前已完成并验证环境管理模块 8 条 P0 用例，文件位于 `tests/p0/environment_management/`：

- `test_01_kernel_integrity.py`
- `test_02_create_default_environment.py`
- `test_03_batch_create_environments.py`
- `test_04_create_134_kernel_environment.py`
- `test_05_batch_create_134_kernel_environments.py`
- `test_06_batch_import_environments.py`
- `test_07_edit_environment_name.py`
- `test_08_edit_fixed_open_url.py`

已预留代理管理、扩展管理、环境分组管理、成员管理、全局设置模块目录，后续新增用例时按业务模块放入对应目录。
