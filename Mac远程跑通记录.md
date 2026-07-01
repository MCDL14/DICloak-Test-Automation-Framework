# Mac 远程跑通记录

更新时间：2026-07-01

本文档记录 Mac 真机远程接入、环境准备和首轮模块跑通结果。本文不记录 SSH 密码、业务账号、OpenAPI secret 或完整 APP 日志。

说明：本文保留 2026-06 Mac 远端验证的历史运行结果，旧记录中的 P0 数量 59 是当时用例集状态。当前 Windows 本地 P0 已更新为 62 条，最新元素修复和全量状态见 `README.md` 与 `任务进度同步文档.md` 的 2026-07-01 记录。

## 1. 远程环境

远程终端：

```bash
ssh tianji@192.168.40.5
```

系统信息：

```text
ProductName: macOS
ProductVersion: 14.5
BuildVersion: 23F79
Architecture: arm64
```

工具版本：

```text
系统 python3: Python 3.9.6
可用 Python: /Users/tianji/.pyenv/shims/python3.11 -> Python 3.11.6
git: 2.39.3 (Apple Git-146)
```

## 2. DICloak APP 信息

已发现两个 APP bundle：

```text
/Applications/DICloak.app
/Applications/DICloak 2.app
```

本轮选择 `/Applications/DICloak.app`，信息如下：

```text
Executable: DICloak
Version: 2.9.4
BundleID: com.dicloak
Executable path: /Applications/DICloak.app/Contents/MacOS/DICloak
Work dir: /Applications/DICloak.app/Contents/MacOS
Process name: DICloak
Browser process name: GinsBrowser
```

## 3. 自动化项目同步

本轮同步当前 Windows 工作区到 Mac 新目录：

```text
/Users/tianji/dicloak_automation_mac_20260616_115230
```

并创建软链接：

```text
/Users/tianji/dicloak_automation_mac
```

同步时排除了：

- `.git`
- `.venv`
- `logs`
- `reports`
- `screenshots`
- `__pycache__`
- `.pytest_cache`
- 临时目录和运行产物

注意：

- macOS 系统 `unzip` 在当前 SSH locale 下解压中文文件名时报 `Illegal byte sequence`。
- 已改用远端 Python `zipfile.extractall()` 解压，中文文件名可正常恢复。

## 4. Python 环境

首次使用系统 Python 3.9.6 创建虚拟环境后，预检失败：

```text
Precheck Python version FAIL current=3.9.6, expected>=3.10
```

随后改用 Python 3.11.6 重建虚拟环境：

```bash
cd /Users/tianji/dicloak_automation_mac
/Users/tianji/.pyenv/shims/python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
```

依赖导入检查：

```text
yaml=True
playwright=True
psutil=True
openpyxl=True
```

## 5. Mac 专用配置

本轮在 Mac 远端生成运行配置：

```text
config/config.macos.yaml
```

关键配置：

```yaml
platform:
  name: macos

platforms:
  macos:
    executable_path: /Applications/DICloak.app/Contents/MacOS/DICloak
    work_dir: /Applications/DICloak.app/Contents/MacOS
    process_name: DICloak
    browser_process_name: GinsBrowser
    startup_args:
      - --remote-debugging-port=9222
      - --remote-allow-origins=*
```

本轮远程验证关闭飞书通知：

```yaml
feishu:
  enabled: false
```

## 6. 已执行验证

编译检查：

```bash
cd /Users/tianji/dicloak_automation_mac
. .venv/bin/activate
python -m compileall -q core pages tests
```

结果：

```text
COMPILE_EXIT=0
```

预检：

```bash
python run.py --config config/config.macos.yaml --precheck
```

结果：

```text
PRECHECK_EXIT=0
Python version PASS current=3.11.6, expected>=3.10
APP exe_path exists PASS /Applications/DICloak.app/Contents/MacOS/DICloak
APP work_dir exists PASS /Applications/DICloak.app/Contents/MacOS
APP startup arg remote-debugging-port PASS
APP startup arg remote-allow-origins PASS
CDP port status checked PASS 127.0.0.1:9222 occupied=False
Feishu webhook configured PASS feishu disabled
```

环境分组模块托管启动验证：

```bash
python run.py --config config/config.macos.yaml --module environment_group_management
```

结果：

```text
total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0
```

重试统计：

```text
RETRY_FAILURE_COUNT=0
RETRYING_COUNT=0
PASSED_AFTER_RETRY_COUNT=0
```

通过用例：

```text
test_create_and_delete_environment_group ... ok
test_delete_group_with_contained_environment ... ok
test_group_authorized_member ... ok
test_filter_group_name ... ok
test_edit_group_name_and_restore ... ok
test_edit_group_remark_and_restore ... ok
```

## 7. 当前结论

Mac 真机已完成首轮跑通：

- SSH 可连接。
- 当前工作区已同步到 Mac。
- Python 3.11 虚拟环境可用。
- 依赖安装完成。
- Mac 专用配置可通过预检。
- DICloak 2.9.4 可由框架托管启动。
- CDP `127.0.0.1:9222` 可连接。
- `environment_group_management` 模块 6 条用例全部通过。
- 本轮没有触发重试。

## 8. 已知注意事项

- 系统自带 Python 3.9.6 不满足框架预检要求，Mac 运行必须使用 Python 3.10+，本轮使用 Python 3.11.6。
- 远端系统 `unzip` 对中文文件名不稳定，后续同步当前工作区建议继续使用 Python `zipfile` 或 Git。
- 当前仅验证了低风险环境分组模块。
- 全局设置、环境管理、成员管理、导入导出、代理能力和 Windows 专属工具依赖仍需分层验证。
- `test_07_disable_packet_capture_software` 依赖 Windows `.exe` 工具，预计 Mac 上需要 skip、降级验证或替换为 Mac 专用探针。

## 9. 下一步建议

建议 Mac 后续验证顺序：

1. 继续使用 `/Users/tianji/dicloak_automation_mac` 和 `config/config.macos.yaml`。
2. 跑 `member_management`，验证普通 UI、导出和成员类流程。
3. 跑 `environment_management`，验证内核进程识别、环境打开/关闭、导入导出。
4. 跑 `global_settings` 前先处理 Windows 专属 `.exe` 工具依赖。
5. 代理能力最后单独验证，不纳入首轮 Mac 基线。

## 10. P0 全量运行记录

执行时间：2026-06-16

全量前加固：

- `test_07_disable_packet_capture_software` 明确标记为 Windows 专属用例，Mac 上跳过，避免执行 `test_data/Tools/geek.exe` 和 Windows `taskkill`。
- `core.kernel_cache.resolve_kernel_browsers_dir()` 增加 Mac 内核缓存目录解析：设置页返回环境缓存目录 `.DICloakCache`，但 Mac 内核目录实际位于 `~/Library/Application Support/DICloak/browsers`。
- `resolve_app_config()` 补充 macOS/Linux 默认进程名兜底，避免未加载 Mac 专用配置时仍按 `GinsBrowser.exe` 查找内核进程。
- `EnvironmentPage.set_pagination_size()` 增强分页下拉操作：Mac 上右下角 Crisp 浮层会拦截真实鼠标事件，因此分页下拉打开和选项点击增加坐标点击与 DOM 事件 fallback。

失败项复跑验证：

```bash
python run.py --config config/config.macos.yaml --module test_01_kernel_integrity.py
python run.py --config config/config.macos.yaml --module test_11_environment_list_pagination_setting.py
```

复跑结果：

```text
test_01_kernel_integrity.py: total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0
test_11_environment_list_pagination_setting.py: total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0
```

最终全量命令：

```bash
cd /Users/tianji/dicloak_automation_mac
. .venv/bin/activate
python -m compileall -q core pages tests
python run.py --config config/config.macos.yaml --level P0
```

最终全量结果：

```text
total=59 passed=57 failed=0 errors=0 skipped=2 flaky=1
EXIT_CODE=0
```

重试统计：

```text
RETRY_FAILURE_COUNT=1
RETRYING_COUNT=1
PASSED_AFTER_RETRY_COUNT=1
```

重试后通过的用例：

```text
tests.p0.environment_management.test_01_kernel_integrity.TestKernelIntegrity.test_142_kernel_integrity
```

跳过用例：

```text
test_disable_packet_capture_software ... skipped 'packet capture blocking validation depends on Windows executable tools'
test_create_custom_proxy_detect_and_delete ... skipped 'system proxy is not supported on platform: macos'
```

收尾状态：

```text
POST_CLEANUP_CDP_9222_OCCUPIED=False
```

结论：

- Mac P0 全量已跑通。
- 当前 Mac 全量有效通过 57 条，平台能力限制跳过 2 条。
- 唯一 flaky 来自内核完整性用例首轮波动，第二轮自动重试通过。
- 本轮未发现最终失败或错误用例。

## 11. 代理管理用例不再按系统代理能力跳过

调整时间：2026-06-16

调整目标：

- macOS 当前仍不支持系统代理启停能力。
- 代理管理业务用例不能因为系统代理 unsupported 被跳过。

实现方式：

- 移除代理管理用例类级 `skipUnless(system_proxy_supported())`。
- 用例运行时判断系统代理能力：
  - Windows 支持系统代理时，继续启用系统代理并在 finally 中恢复原始快照。
  - macOS/Linux 不支持系统代理时，记录日志并继续执行代理创建、检测、删除流程。

Mac 单条验证：

```bash
python run.py --config config/config.macos.yaml --module proxy_management
```

结果：

```text
total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0
```

关键日志：

```text
System proxy is unsupported on this platform; continue proxy management case without it
Proxy custom created id=2066760840294371329 type=HTTP host=accel.ipflygates.com port=5001
Proxy custom row detect result id=2066760840294371329 result=连接成功
Proxy custom delete finished id=2066760840294371329
```

调整后 Mac P0 全量验证：

```bash
python run.py --config config/config.macos.yaml --level P0
```

结果：

```text
total=59 passed=58 failed=0 errors=0 skipped=1 flaky=1
EXIT_CODE=0
```

重试统计：

```text
RETRY_FAILURE_COUNT=1
RETRYING_COUNT=1
PASSED_AFTER_RETRY_COUNT=1
```

重试后通过的用例：

```text
tests.p0.global_settings.test_11_environment_list_pagination_setting.TestEnvironmentListPaginationSetting.test_environment_list_pagination_setting
```

当前唯一跳过用例：

```text
test_disable_packet_capture_software ... skipped 'packet capture blocking validation depends on Windows executable tools'
```

收尾状态：

```text
POST_CLEANUP_CDP_9222_OCCUPIED=False
```
