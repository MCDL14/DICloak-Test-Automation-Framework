# Linux 代理实测与全局设置验证文档

更新时间：2026-07-01

本文档单独记录 Linux 代理能力实测结论，以及带代理参数执行全局设置用例的结果。本文只记录验证事实和后续方案，不包含远程机器密码、业务账号、OpenAPI secret 或完整 APP 日志。

说明：本文保留 Linux 代理和全局设置在 2026-06 的历史实测结论。当前 Windows 本地 P0 已更新为 62 条；2026-07-01 全量中代理相关剩余问题与 `127.0.0.1:7897` 本地代理未监听或影响 APP 列表加载有关，应按运行环境前置排查，不归类为元素定位失败。

## 1. 背景

跨平台兼容改造已完成 Windows 基线能力，并在 Ubuntu 机器上跑通了基础启动、预检和部分模块用例。后续需要判断代理相关能力在 Linux 上应如何落地，避免代理配置影响普通用例稳定性。

当前重点问题：

- Linux 是否能启停系统代理。
- Linux 系统代理启用后，DICloak APP 是否实际生效。
- 如果改用 APP 启动参数代理，是否会影响全局设置用例稳定性。

## 2. Ubuntu 环境信息

已验证 Ubuntu 机器：

- 系统：Ubuntu 24.04
- Python：3.12.3
- 自动化项目目录：`/home/dic/dicloak_automation_linux`
- DICloak 安装目录：`/opt/DICloak/dicloak`
- DICloak Linux 内核浏览器进程：`ginsbrowser`
- 自动化虚拟环境：`/home/dic/dicloak_automation_linux/.venv`

已通过的基础验证：

```bash
python -m compileall -q core pages tests
python run.py --config config/config.yaml --precheck
python run.py --config config/config.yaml --module environment_group_management
```

其中 `environment_group_management` 模块在 Linux 上通过：

```text
total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0
```

## 3. GNOME 系统代理能力实测

Ubuntu 上具备 GNOME `gsettings` 代理配置能力：

- `gsettings` 存在。
- `dconf` 存在。
- `org.gnome.system.proxy` schema 存在。
- `http` / `https` / `socks` 代理项存在。
- 当前用户 DBus session 可写入代理配置。

已验证可写字段：

- `org.gnome.system.proxy mode`
- `org.gnome.system.proxy ignore-hosts`
- `org.gnome.system.proxy.http enabled`
- `org.gnome.system.proxy.http host`
- `org.gnome.system.proxy.http port`
- `org.gnome.system.proxy.https host`
- `org.gnome.system.proxy.https port`

安全探针结果：

```text
PROBE_WRITE_OK=True
RESTORE_OK=True
```

结论：

- Ubuntu 桌面系统代理可以通过 GNOME `gsettings` 写入和恢复。
- 实现时不能使用 shell `source` 临时文件恢复配置，因为 `ignore-hosts` 这类数组值容易被 shell 引号和分隔符破坏。
- 如果未来仍需保留 GNOME 系统代理后端，必须使用 Python `subprocess` 逐项读取和逐项恢复。

## 4. GNOME 系统代理对 DICloak APP 的生效验证

验证方式：

1. 在 Ubuntu 上启动本地临时代理探针，监听 `127.0.0.1:18997`。
2. 通过 `gsettings` 将 GNOME 系统代理设置为 `127.0.0.1:18997`。
3. 启动 DICloak APP。
4. 通过 APP 的 CDP 页面访问 `.invalid` 探针域名。
5. 判断本地代理探针是否收到请求。
6. 无论成功失败都恢复原始 GNOME 代理配置。

验证结果：

```text
APP_LAUNCHED=True
PROXY_HIT_COUNT=0
PAGE_MARKER_FOUND=False
goto_error=net::ERR_NAME_NOT_RESOLVED
APP_PROXY_EFFECTIVE=False
RESTORE_OK=True
```

结论：

- DICloak APP 在 Linux 上启动后没有使用 GNOME 系统代理。
- `.invalid` 域名直接 DNS 失败，说明请求没有进入本地代理探针。
- GNOME 系统代理虽然可写，但不能作为当前 DICloak Linux 自动化代理主方案。

## 5. APP 启动参数代理生效验证

验证方式：

1. 不修改 GNOME 系统代理。
2. 启动 DICloak APP 时追加 Chromium/Electron 参数：

```text
--proxy-server=127.0.0.1:18997
```

3. 本地临时代理探针监听 `127.0.0.1:18997`。
4. 通过 APP 的 CDP 页面访问 `.invalid` 探针域名。

验证结果：

```text
APP_LAUNCHED=True
PROXY_HIT_COUNT=9
PAGE_MARKER_FOUND=True
APP_PROXY_ARG_EFFECTIVE=True
```

探针收到的代表性请求包括：

```text
CONNECT gin-server.dicloak.com:443
GET http://dicloak-proxy-probe.invalid/...
```

结论：

- DICloak APP 在 Linux 上可以通过 `--proxy-server` 启动参数使用代理。
- 该方案真实生效，但会让 APP 启动阶段的业务请求一起走代理。
- 如果代理不可用、延迟高或需要认证，可能影响登录态刷新、首页加载、线路初始化、内核信息加载和 CDP ready 稳定性。

## 6. 指定代理执行全局设置用例结果

按要求在 Ubuntu 上使用指定代理启动 APP：

```text
--proxy-server=192.168.20.33:7897
```

执行模块：

```bash
python run.py --config /tmp/proxy_global_20260616_112541_config.yaml --module global_settings
```

执行结果：

```text
total=12 passed=11 failed=0 errors=1 skipped=0 flaky=0
EXIT_CODE=1
```

重试统计：

```text
RETRY_FAILURE_COUNT=1
RETRYING_COUNT=1
PASSED_AFTER_RETRY_COUNT=0
```

说明：

- 本次全局设置共执行 12 条用例。
- 11 条通过。
- 1 条最终报错。
- 中途触发 1 次重试。
- 没有用例通过重试恢复成功，因此 `flaky=0`。

触发重试并最终报错的用例：

```text
tests.p0.global_settings.test_07_disable_packet_capture_software.TestDisablePacketCaptureSoftware.test_disable_packet_capture_software
```

失败原因：

```text
PermissionError: [Errno 13] Permission denied:
'/home/dic/dicloak_automation_linux_20260615_193149/test_data/Tools/geek.exe'
```

判断：

- 失败点是 Linux 上尝试执行 Windows `.exe` 工具 `geek.exe`。
- 该问题属于用例跨平台依赖不兼容，不是本次代理参数直接导致。
- 后续应将该用例在 Linux 上跳过、降级验证，或替换为 Linux 可用的抓包软件探针。

## 7. 已确认成功的关键用例

在 `--proxy-server=192.168.20.33:7897` 场景下，以下用例成功：

```text
test_disable_extension_management_and_install
(tests.p0.global_settings.test_03_disable_extension_management.TestDisableExtensionManagement.test_disable_extension_management_and_install) ... ok
```

该用例对应业务描述：

```text
禁止管理/移除扩展，以及从本地安装扩展至浏览器
```

结论：

- 该用例在 Linux + APP 启动代理参数场景下通过。
- 本次失败用例不是扩展管理限制用例，而是禁用抓包软件用例。

## 8. 当前代理方案判断

不建议作为主方案：

- Linux GNOME `gsettings` 系统代理。

原因：

- 系统代理可写，但 DICloak APP 实测不生效。
- 继续实现会得到“配置成功但 APP 不走代理”的误导性能力。

短期可用但需限制范围：

- APP 启动参数 `--proxy-server=host:port`。

适用场景：

- 代理管理相关用例。
- 明确需要 APP 网络栈走代理的验证。
- 临时验证代理连通性或代理影响范围。

不适合作为默认配置的原因：

- APP 启动期请求会立即走代理。
- 代理不稳定可能影响普通模块。
- 失败定位会从 UI 自动化问题扩大到网络代理问题。

更稳的短期候选：

- `--proxy-pac-url=file:///path/to/proxy.pac`

PAC 模式建议：

```js
function FindProxyForURL(url, host) {
  if (dnsDomainIs(host, "dicloak-proxy-probe.invalid")) {
    return "PROXY 127.0.0.1:7897";
  }

  return "DIRECT";
}
```

价值：

- APP 仍需启动参数，但默认直连。
- 仅让指定域名或指定探针流量走代理。
- 比全量 `--proxy-server` 对 APP 初始化影响更小。

长期推荐方案：

- APP 产品侧提供自动化专用运行时代理控制接口。

理想能力：

```text
POST /automation/proxy/enable
POST /automation/proxy/disable
```

APP 内部可使用 Electron `session.defaultSession.setProxy()` 实现运行时切换。这样 APP 可以正常启动，等 ready 后只在代理用例阶段启用代理，用例结束后恢复直连。

## 9. 后续工作建议

建议后续 Linux 代理相关工作按下面顺序推进：

1. 不把 Linux GNOME 系统代理作为 APP 自动化代理主方案。
2. 不将 `--proxy-server` 设置为 Linux 普通用例默认启动参数。
3. 代理相关用例如需真实验证 APP 网络栈走代理，优先使用隔离配置临时追加启动参数。
4. 带代理运行时优先选择代理管理相关用例，不扩大到环境管理、成员管理、全局设置等普通模块。
5. `test_07_disable_packet_capture_software` 需要单独做平台兼容处理：
   - Linux 跳过 Windows `.exe` 工具依赖；或
   - 替换为 Linux 可用的抓包软件探针；或
   - 拆分为 Windows 专属用例和跨平台降级验证用例。
6. 如需要降低启动期全量代理风险，可继续验证 PAC 模式：

```text
--proxy-pac-url=file:///path/to/dicloak-automation-proxy.pac
```

7. 如需要长期统一 Windows/Linux 代理能力，建议推动 APP 侧提供自动化专用运行时代理控制接口。
