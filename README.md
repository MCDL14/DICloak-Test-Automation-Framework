# Dicloak 自动化框架

本项目用于 Dicloak Electron APP 的自动化测试。当前框架已具备配置读取、环境预检、APP 生命周期管理、CDP 连接、飞书通知、用例运行编排，以及 P0 环境管理、全局设置、扩展管理、环境分组管理、成员分组管理、成员管理、代理管理用例执行能力。

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
python run.py --config config/config.yaml --module extension_management
python run.py --config config/config.yaml --module environment_group_management
python run.py --config config/config.yaml --module member_group_management
python run.py --config config/config.yaml --module proxy_management
python run.py --config config/config.yaml --module test_02_group_containing_environment.py --attach-existing-app
python run.py --config config/config.yaml --module test_01_kernel_integrity.py
python run.py --config config/config.yaml --module p0/environment_management/test_01_kernel_integrity.py
python run.py --config config/config.yaml --module tests/p0/environment_management/test_01_kernel_integrity.py
python run.py --config config/config.yaml --case test_142_kernel_integrity
```

`--business-module` 用于按业务模块运行用例；当前支持：环境管理、代理管理、扩展管理、环境分组管理、成员分组管理、成员管理、全局设置。

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

## 本地登录存储模拟站

框架已提供独立的 Local Auth Lab，用于验证 DICloak 对 Cookie、Local Storage、IndexedDB 的浏览器数据上传与恢复能力。Local Auth Lab 层只提供测试基础设施和可复用操作层；具体业务流程由环境管理用例独立编排。三个站点分别使用独立 Origin，并且每个站点只保存一种登录令牌：

- `cookie.dicloak.localhost`：HttpOnly Cookie；
- `localstorage.dicloak.localhost`：Local Storage；
- `indexeddb.dicloak.localhost`：IndexedDB。

三个页面均支持注册、登录、退出、当前账号和登录状态展示。账号按站点写入本地 SQLite，注册成功后不会自动登录，也不会创建 session 或写入浏览器令牌；令牌无效、过期、被撤销或不存在时统一显示“未登录”。密码使用 scrypt 派生值保存，session token 使用 HMAC-SHA256 签名。

框架默认配置中的该能力保持关闭。旧的 `config.yaml` 没有 `local_auth_lab` 整段配置时仍按关闭处理，普通 `--precheck` 和所有未声明依赖的现有用例不会增加 DNS、端口、数据库、模板或密钥检查。当前工作区通过被 Git 忽略的 `config/local_auth_lab.yaml` 启用真实测试站；该文件可覆盖 Windows `config.yaml` 和 macOS `config.macos.yaml` 中的同名段。

启用后首次启动会在 `test_data/local_auth_lab/credentials.json` 原子生成签名密钥和管理密钥，并始终优先读取该持久文件。文件、SQLite 数据库及 WAL/SHM 均被 Git 和普通代码快照强制排除。环境变量只用于首次生成文件时引导写入，后续改变环境变量不会轮换已经固化的密钥：

```powershell
$env:DICLOAK_AUTH_LAB_SIGNING_SECRET = "请使用仅供测试的高强度随机值"
$env:DICLOAK_AUTH_LAB_ADMIN_KEY = "请使用另一个高强度随机值"
```

显式依赖 `local_auth_lab` 的 suite 会先检查固定端口是否已有版本、schema、域名、Origin 模式、Session TTL 和持久签名密钥指纹均兼容的服务；兼容服务存在时直接复用。端口没有兼容服务时，才按启用配置和持久凭据执行专项预检并启动新实例；端口存在旧随机密钥或旧 TTL 服务时会明确判为不兼容，不会误复用。该路径仍只作用于显式依赖的 suite。

Session TTL 当前固定为 `15552000` 秒（180 天）。配置变化不会修改已经签发的旧令牌；从历史随机密钥切换到持久密钥时，服务只对“完整 token 哈希与 SQLite 记录精确相同、账号有效、Session 未撤销且旧 token 未过期”的请求自动换发 180 天新令牌。Cookie 通过 `Set-Cookie` 覆盖，Local Storage 和 IndexedDB 由页面适配层原位覆盖，因此已有云端登录数据可以无密码迁移，伪造 token 不能仅靠未校验 payload 通过迁移。

默认 `origin_mode=localhost` 使用 `*.dicloak.localhost`。Chromium/GinsBrowser 会将这些地址识别为本地主机并隐式绕过代理，因此 Windows、macOS、Linux 均不需要修改 hosts，也不依赖系统 DNS 或代理 Fake-IP 的解析结果。服务仍只监听 `127.0.0.1:18080`。

2026-08-03 Windows 实机验证已完成：固定端口 `18080` 下，控制首页和三个模拟站均可直接通过 `*.dicloak.localhost` 打开，用户人工确认页面正常；验证过程没有修改 hosts、系统 DNS、系统代理或 DICloak APP 配置。Google Chrome 151 + 原生 CDP 三站冒烟也已通过，覆盖“注册后不自动登录、登录后目标存储存在令牌、服务端撤销后被动掉登并清除令牌”。macOS 和 Linux 当前完成了跨平台实现与配置设计，尚未记录对应平台实机结论。

如果产品侧明确过滤 `.localhost` 浏览器数据，可以切换到 `origin_mode=custom_domains` 并配置自定义域名。只有该兼容模式需要让所有域名在运行节点解析到回环地址，例如：

```text
127.0.0.1 sync.dicloak.test
127.0.0.1 cookie.sync.dicloak.test
127.0.0.1 localstorage.sync.dicloak.test
127.0.0.1 indexeddb.sync.dicloak.test
```

框架不会自动修改系统 hosts、代理或 DNS。`localhost` 模式通过静态域名约束和真实 Chromium/CDP 页面访问验证连通性；`custom_domains` 模式额外执行操作系统 DNS 回环检查。

用例接入只需在测试类上显式声明运行时依赖：

```python
class TestBrowserDataCloudRestore(unittest.TestCase):
    REQUIRED_RUNTIME_SERVICES = {"local_auth_lab"}
```

Runner 会在普通环境预检和 suite 筛选完成后，仅为该 suite 启动服务；退出、异常或中断时只停止本次运行拥有的服务实例。用例可组合以下组件，不需要修改现有 APP Page Object 或 `core/kernel_cdp.py`：

- `LocalAuthLabClient`：准备账号、查询状态、撤销 session、按 `siteId/username/runId/jti` 精确清理；
- `KernelCDPSession`：通过 GinsBrowser 动态 CDP 端口创建并独占一个临时页面 target；
- `LocalAuthLabPage`：封装三个页面的打开、注册、登录、退出和状态读取；
- `BrowserStorageInspector`：直接读取 Cookie、Local Storage 或 IndexedDB，供测试建立前后置证据。

需要单独调试服务时，在准备好 `config/local_auth_lab.yaml` 后运行：

```bash
python -m core.local_auth_lab --config config/config.yaml
```

服务数据库、SQLite WAL/SHM、持久凭据和本机覆盖配置均已从 Git 与普通代码快照排除；版本化页面模板会随远端代码同步。macOS 勾选“远程执行前同步当前代码”时，不区分所选用例是否依赖账号站：UI 固定在代码快照成功后通过认证状态专用 SFTP 通道发送覆盖配置、持久凭据和 SQLite 在线备份，远端校验数据库哈希、schema 与密钥指纹全部通过后才启动用例。认证状态同步不等于启动后端；只有 suite 声明 `local_auth_lab` 依赖时远端 Runner 才启动服务，并在执行结束后关闭本次 Runner 拥有的服务。完整架构、接口和隔离约束见 `本地登录存储模拟站技术方案.md`。

## Linux 远端启动

当前已在远端 Ubuntu 24.04 机器完成第一轮 Linux 真机调通。远端项目目录为：

```bash
/home/dic/dicloak_automation_linux
```

登录 Linux 后按下面步骤启动自动化：

```bash
cd /home/dic/dicloak_automation_linux
. .venv/bin/activate
python run.py --config config/config.yaml --precheck
python run.py --config config/config.yaml --module environment_group_management
```

`environment_group_management`、`member_management` 是当前 Linux 已验证通过的主链路模块。托管启动模式会自动完成：

- 关闭已有 DICloak 进程。
- 启动 `/opt/DICloak/dicloak`。
- 附加 `--remote-debugging-port=9222 --remote-allow-origins=*`。
- 等待 APP 前端 ready。
- 执行用例。
- 结束后关闭 DICloak。

如果已经手动启动了带 CDP 参数的 DICloak，可以使用 attach 模式：

```bash
cd /home/dic/dicloak_automation_linux
. .venv/bin/activate
python run.py --config config/config.yaml --module environment_group_management --attach-existing-app
```

Linux 当前已验证：

- `python run.py --config config/config.yaml --precheck` 通过。
- `python run.py --config config/config.yaml --module environment_group_management --attach-existing-app` 通过，结果 `total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module environment_group_management` 通过，结果 `total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module member_management` 通过，结果 `total=15 passed=15 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module global_settings` 当前主要流程已验证：`test_01`、`test_02`、`test_04`、`test_05`、`test_06`、`test_08`、`test_09`、`test_10`、`test_11`、`test_12` 均已通过；`test_07` 按 Windows 专用抓包工具能力跳过；`test_03` 仍受 Linux 环境 Chrome Web Store 页面加载/内核 CDP 响应超时影响。

Linux 当前不支持或未完成验证：

- 不支持 Linux 系统代理自动启停。
- 不支持 Linux 原生文件选择器兜底。
- 尚未完成 `environment_management` 的 Linux 模块回归。
- `global_settings/test_03_disable_extension_management.py` 依赖 Chrome Web Store 页面加载，当前 Linux 环境未使用 APP/内核代理时会出现 `kernel CDP command response timeout`，暂作为 Linux 外部网络/页面依赖限制记录。
- 尚未完成 Linux 导入/导出、桌面截图兜底、代理管理验证。

## Mac 远端运行

当前已在远端 macOS 14.5 arm64 机器完成 P0 全量验证。远端项目目录为：

```bash
/Users/tianji/dicloak_automation_mac
```

登录 Mac 后按下面步骤启动自动化：

```bash
cd /Users/tianji/dicloak_automation_mac
. .venv/bin/activate
python run.py --config config/config.macos.yaml --precheck
python run.py --config config/config.macos.yaml --level P0
```

Mac 当前已验证：

- `python -m compileall -q core pages tests` 通过。
- `python run.py --config config/config.macos.yaml --precheck` 通过。
- `python run.py --config config/config.macos.yaml --module environment_group_management` 通过，结果 `total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.macos.yaml --level P0` 通过，结果 `total=59 passed=58 failed=0 errors=0 skipped=1 flaky=1`。
- UI 远程节点模式已完成“同步当前代码”后执行 `P0 全量` 验证，结果 `total=59 passed=57 failed=0 errors=1 skipped=1 flaky=0`；唯一错误为代理创建弹窗确认后未关闭，保留为 Mac 远端代理业务/环境问题继续排查。

以上 Mac 远端 P0 数量为 2026-06 历史快照；当前 Windows 本地 P0 已扩展为 95 条，最新状态见“最近验证记录”。

Mac 当前跳过项：

- `test_disable_packet_capture_software`：依赖 Windows `.exe` 工具和 `taskkill`，Mac 上按平台能力跳过。

代理管理说明：

- macOS 当前仍不支持系统代理启停能力。
- `test_create_custom_proxy_detect_and_delete` 不再因系统代理 unsupported 跳过；Mac 上会继续执行代理创建、检测和删除流程。最近一次 UI 远程 P0 全量中该用例在创建弹窗确认后未关闭，未作为框架同步链路阻塞项掩盖。

详细记录见 `Mac远程跑通记录.md`。

## 可视化 UI

项目新增 Streamlit 可视化执行入口，CLI 运行方式保持不变。安装依赖后可在项目根目录启动：

```bash
streamlit run ui/app.py
```

UI 支持用例发现、按模块筛选、批量选择、实时日志、执行进度、运行结果统计和历史日志查看，并复用 CLI 的恢复、截图、重试、flaky 统计和飞书通知链路。执行页当前采用“侧边栏筛选 + 模块卡片总览 + 卡片内展开用例 + 底部执行摘要”的选择布局：用例列表优先展示中文业务名称，原始 test id 仅保留在 hover 帮助和实际执行命令中，真正执行时仍把原始 test id 作为 `--case` 参数传给 CLI。用例运行中日志区只展示最近 50 行，避免全量执行时页面被大量日志拖慢；执行进度组件按断言失败、执行错误、跳过、运行/重试中、待执行和已通过分组，显示总耗时与每条用例耗时，并支持在组件内组合使用状态筛选和模块筛选，不会触发 Streamlit 整页重跑。执行结束后顶部日志区会自动收敛为失败、错误、异常等未成功日志；完整过程日志仍以运行历史和 `logs/` 文件为准。用例运行中点击 Streamlit 右上角 `Stop` 会同步取消后台执行：本机任务中断独立 CLI 子进程，远程任务向 SSH PTY 发送 `Ctrl+C`。UI 还支持把 Windows 本机和 macOS 远程执行作为一个同步任务并行启动、统一停止，并分别展示两端结果。不要在 UI 任务之外再用 CLI 抢占同一个 APP、CDP 端口、测试账号或业务数据。详细说明见 `UI使用文档.md`。

### 自动化账号组与同步执行

首次使用前，打开 UI 的“自动化账号组”页面维护固定的两组数据。每组包含：

- 自动化主账号、密码、自动化团队名称和主账号成员 ID；该 ID 只供主账号停用/到期停用接口用例使用。
- 普通 UI 用例使用的外部成员名称和邮箱，与自动化主账号严格区分。
- 内部成员账号、密码和内部成员 ID。
- 该团队的成员 Open API token；停用/到期用例跨团队执行时不能共用另一个团队的 token。

保存位置为 `config/account_groups.yaml`。该文件会记住密码和 token，已加入 `.gitignore`；编辑页面提供“显示密码和 Open API token”开关。仓库只提交不含真实凭据的 `config/account_groups.example.yaml`。

执行页提供三种位置：

- **本机**：选择一组账号后在 Windows 本机执行。
- **远程节点**：选择一组账号后在远端执行。
- **本机 + Mac 远程**：Windows 和 macOS 必须选择不同账号组，同时执行相同的已勾选用例。

两个团队还需要准备一致的业务基线数据。当前全量用例会直接使用成员组 `运营组/管理组`、环境组 `未分组/分组二/分组三`、固定成员备注和环境标签等数据；某个团队缺少这些数据时，只会影响依赖该数据的用例，不代表同步执行通道失败。成员创建用例使用按账号组稳定生成的测试邮箱和内部登录账号，避免双端同时创建时发生平台级唯一值冲突。上级经理、外部成员编辑、邮箱筛选和成员导出从账号组的“用例所需外部成员”读取名称/邮箱，不读取自动化主账号及其 ID；成员导出还会监听 `GET /gin/v1/member`，实时获取 `自动化成员1` 和该外部成员的接口记录及真实 ID，再与导出 Excel 的 14 列逐列比较。

执行时只把当前执行端选中的一组写入临时运行配置。Windows 临时文件在子进程结束后删除；macOS 临时文件通过 SFTP 以 `0600` 权限上传，SSH 命令结束后删除。密码和 token 不会拼入命令预览或运行日志。远端代码快照同步强制排除 `account_groups.yaml` 和 `.ui_account_profile_*.yaml`，即使自定义同步规则包含整个 `config/` 也不会上传两组凭据。

### UI 远程节点执行

UI 已支持通过 SSH 在内网 Linux/macOS 节点执行远端 CLI。远程模式不复制测试执行链路，只在 UI 中选择节点和运行类型；选择“执行用例”时，会按执行页下方已勾选的模块/用例生成远端 `python run.py` 命令。

配置步骤：

```bash
cp config/remote_hosts.example.yaml config/remote_hosts.yaml
```

`config/remote_hosts.yaml` 已加入 `.gitignore`，用于保存远端项目目录、运行配置、虚拟环境和同步策略等节点模板。SSH IP、端口、用户名和 SSH 密码可以在执行页“远程节点执行”的“编辑连接”中维护，并缓存到本机 `config/remote_connection_cache.yaml`；该缓存同样已加入 `.gitignore`。SSH 密码使用当前 Windows 用户的 DPAPI 加密，缓存中不保存明文，也不会同步到远端；仍可改用 SSH key 或通过 `password_env` 指向本机环境变量。

远程节点执行先选择运行类型：

- **远程预检**：只检查远端环境，不运行用例。
- **执行用例**：运行下方已勾选用例。

远程“执行用例”会把下方已勾选用例转换为重复的 `--case <test_id>` 参数，例如：

```bash
python run.py --config <remote-config> --case <test_id_1> --case <test_id_2>
```

执行页左侧的“业务模块”和“搜索用例”只控制列表可见性，不会取消用例勾选，也不会改变本机执行范围。搜索支持模块名、中文用例名、测试类、测试方法和完整 test id。顶部选择工具栏用进度条和“已选 N / M”显示总勾选进度，并提供“选择可见”“清空选择”。每个模块卡片会直接显示已选数量，点击卡片空白主体区域只在前端展开用例，不走 URL 导航也不刷新整个页面；模块使用手风琴模式，展开新模块时会自动收起上一个模块。组件高度根据实际卡片和用例内容动态计算，收起大模块后会立即缩回，不会在模块总览和执行区之间留下大块空白。卡片右侧“全选”“清空”可在不改变展开状态的情况下调整整个模块勾选状态。

远程节点模式的主路径保持为：选择节点、确认连接信息、选择运行类型；如果选择“执行用例”，直接使用下方已勾选用例；最后设置执行选项并点击底部运行按钮。SSH IP、端口和用户名默认使用节点配置或本机缓存，日常执行只需要填写本次会话密码；连接修改、检查/同步、命令预览、节点配置和平台能力矩阵都收在折叠区域里，避免执行者先理解远端项目目录、Python、venv、发布目录等维护细节。

远程连接信息：

- UI 节点卡集中展示平台、SSH 地址和本机密码状态；点击“编辑连接”可修改 IP/主机、端口、用户名和密码。
- “记住 SSH 密码”默认开启；点击“保存连接”或启动远程操作时，会把连接信息写入 `config/remote_connection_cache.yaml`。
- 密码使用 Windows DPAPI 按当前用户加密，不以明文落盘；重新进入页面会自动解密并填入密码控件。清空密码后保存，或取消“记住 SSH 密码”后保存，即可删除本机密码。
- 远程节点主路径按节点摘要、运行方式、执行选项、检查与同步、高级信息组织；远程预检和执行用例使用独立选择卡。
- 如果 UI 密码为空，仍会按 `remote_hosts.yaml` 中的 `key_filename`、`password_env` 或 SSH agent/key 尝试认证。

执行前如果需要排查环境，可以展开“检查与同步”后点击“检查节点”。该检查只读，不启动 APP、不跑用例，会检查：

- 远端项目目录是否存在。
- `run.py` 是否存在。
- 远端配置文件是否存在。
- 虚拟环境激活脚本是否存在并可激活。
- Python 版本是否可读取。
- `yaml`、`playwright`、`psutil`、`openpyxl` 等核心依赖是否可导入。
- 远端配置是否可加载。
- 配置解析出的 DICloak APP 路径是否存在。

已验证：

- UI 后端远程调用 Mac 预检通过：`python run.py --config config/config.macos.yaml --precheck`。
- UI 后端远程调用 Mac 环境分组模块通过：`total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0`。
- UI 后端远程健康检查 Mac 节点通过：`失败=0`。
- UI 远程节点模式可同步当前工作区到 Mac release 快照后执行 `P0 全量`，最近一次结果 `total=59 passed=57 failed=0 errors=1 skipped=1 flaky=0`，产物拉取到 `remote_artifacts/macos-arm64/20260617_200227`。
- 远端项目目录不存在时，健康检查会显示 `[FAIL] project_dir missing: <path>`，并以退出码 `1` 结束。

远端代码同步：

- “检查远端代码”会比较远端当前 `.remote_manifest.json` 和本地当前工作区快照，避免误跑旧代码。
- “同步当前代码”会通过 SFTP 发布本地当前工作区到远端新快照目录，包含本地 `config/` 和 `test_data/`，不依赖远端安装 Git。
- 勾选“远程执行前同步当前代码”后，不再按 level/module/business-module/case 区分是否需要账号站，固定严格按“代码快照 → Local Auth Lab 认证状态 → 远程用例”串行执行；认证状态同步失败时不会继续执行任何远程用例。认证状态使用独立 SFTP 包，不进入 `.remote_manifest.json`，包含 `config/local_auth_lab.yaml`、持久凭据及通过 SQLite backup API 生成的一致性数据库快照。
- 认证状态在远端以 `0600` 权限安装，并校验数据库 SHA-256、schema 和非敏感签名密钥指纹；同步时若远端认证站仍在运行会明确失败，避免新快照误复用仍绑定旧 release 数据库的进程。完整密钥、token 和密码不写入同步日志。该链路让 macOS 后端使用与 Windows 相同的签名密钥和 Session 记录，已同步到云端的登录令牌才能在 Mac 浏览器中免登。
- 2026-08-04 修复 macOS 认证状态同步阶段 `zsh: command not found: python`：独立认证状态安装脚本现在会在远端项目目录内先执行节点 `command_prefix`、再 source `venv_activate`，随后校验 `PYTHON_BIN`；当节点仍配置为 `python` 且系统没有该命令时，会自动回退到 `python3`，仍找不到解释器才以 `PYTHON_BIN_NOT_FOUND` 明确失败。建议 macOS 节点在 `config/remote_hosts.yaml` 中显式配置为 `.venv/bin/python`、`python3` 或 pyenv 的绝对解释器路径。
- 同步会让远端使用当前本地运行配置和测试数据；仅在本地快照缺少某个 `config/*.yaml` 时才保留远端旧配置。远程连接配置、连接缓存、账号组凭据、运行时账号临时文件和运行产物始终排除，远端 `.venv` 会保留。
- 如果远端 `project_dir` 是真实目录，首次同步会先把它改名为 `.backup_<release>`，再创建指向新快照的软链接；旧目录保留可回退。
- 默认发布目录为 `<project_dir>_releases`，可在 `config/remote_hosts.yaml` 中通过 `sync_release_root` 覆盖。
- `config/remote_sync.example.yaml` 描述同步包含/排除规则；真实 `config/remote_sync.yaml` 已加入 `.gitignore`，仅在需要本机覆盖规则时创建。

当前限制：

- 远程模式选择“执行用例”时，会按执行页下方已勾选的 test id 执行；显示模块和搜索显示只影响列表可见性，不改变已勾选状态。
- 远端虚拟环境、依赖和 APP 图形会话仍需提前准备好；同步代码不会安装依赖。
- 远程日志进入 UI 前会做基础脱敏，隐藏 `apiSecret`、`BOOT_TOKEN`、`USER_PASSWD`、`password`、`token` 等字段。

远程节点能力矩阵会在“高级信息”中展示当前平台边界：

| 平台 | 远程/本地执行 | CDP 自动化 | APP 托管启动 | 系统代理 | 原生文件选择器 | 已验证范围 |
| --- | --- | --- | --- | --- | --- | --- |
| Windows | 支持 | 支持 | 支持 | 支持启停和恢复 | 支持 Windows UIAutomation 兜底 | Windows P0 主链路，代理检测受外部代理连通性影响 |
| Linux | 支持 SSH 远程 CLI | 支持 | 已验证 | 暂不支持自动启停；代理管理继续执行业务流程 | 暂不支持 | precheck、environment_group_management、member_management、global_settings 主流程；Web Store 安装检查仍受外部网络影响 |
| macOS | 支持 SSH 远程 CLI | 支持 | 按远端配置和图形会话分层验证 | 暂不支持自动启停；代理管理不跳过 | 暂不支持 | P0 全量、environment_group_management、代理管理业务流程 |

远程执行后可以勾选“远程执行后拉取产物”，UI 会把本次运行开始后修改过的远端 `logs/`、`screenshots/`、`reports/` 拉取到本机：

```text
remote_artifacts/<node-name>/<yyyyMMdd_HHmmss>/
  logs/
  screenshots/
  reports/
```

`remote_artifacts/` 已加入 `.gitignore`，避免远端日志、截图或报告误提交。当前 Mac 远程环境分组模块和 UI 远程 P0 全量链路均已验证：

```text
Mac remote environment_group_management:
total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0
远程产物归档 → 文件数=1 本地目录=remote_artifacts/macos-arm64/20260616_185532

Mac UI remote P0:
total=59 passed=57 failed=0 errors=1 skipped=1 flaky=0
远程产物归档 → 文件数=3 本地目录=remote_artifacts/macos-arm64/20260617_200227
```

Linux 远程节点也已完成同一链路验证：

```text
Linux remote health check:
失败=0

Linux remote environment_group_management:
total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0
远程产物归档 → 文件数=1 本地目录=remote_artifacts/linux-ubuntu/20260616_191350

Linux residual check:
dicloak/ginsbrowser: none
CDP 9222: none
```

## 失败恢复机制

框架已在 `core/result.py` 的 unittest 执行结果层接入用例前后恢复机制，避免某条用例失败后残留弹窗、抽屉、下拉框、遮罩或筛选状态影响下一条用例。

恢复分三层：

- 全局 APP 稳定态恢复：`pages/app_page.py` 只负责选择正确的 Dicloak 主页面、关闭阻塞弹窗/抽屉/下拉浮层、等待加载遮罩消失，并确认 APP 外壳可操作；这一层不进入任何业务模块。
- 模块级恢复：当前环境管理模块通过 `EnvironmentPage.recover_to_module_home()` 进入环境管理列表并清理筛选和选中状态；环境分组管理模块通过 `EnvironmentGroupPage.recover_to_module_home()` 进入环境分组列表并关闭阻塞浮层；扩展管理模块通过 `ExtensionPage.recover_to_module_home()` 进入扩展列表并关闭阻塞浮层；成员分组管理模块通过 `MemberGroupPage.recover_to_module_home()` 进入成员分组列表并关闭阻塞浮层；代理管理模块通过 `ProxyPage.recover_to_module_home()` 进入代理列表并关闭阻塞浮层。后续新增模块需要各自实现自己的模块首页恢复入口。
- 用例级清理：具体用例创建的数据仍由用例自己的 `finally` 或后置逻辑清理，因为只有用例知道哪些数据是本次运行创建的。

全局恢复不会强制跳回“环境管理”，所以后续新增其他模块用例时，不会被环境管理页面状态绑死。

## 失败重试机制

框架在 `core/runner.py` 的执行编排层接入用例级重试。`run.retry_times` 表示异常后额外重试次数，例如 `retry_times: 1` 表示异常用例最多执行 2 次；`run.retry_interval_seconds` 表示两次尝试之间的等待秒数。断言失败属于明确业务结果不符合预期，不再自动重试；只有 unittest `error` 这类执行异常才会按配置重试。

重试按单条 unittest 用例重新加载新的 `TestCase` 实例，并完整执行一轮用例生命周期，所以每次重试都会重新触发：

- `setUpClass` / `setUp`
- `AutomationTestResult.startTest()` 中的用例前恢复
- 用例方法
- `tearDown` / `tearDownClass`
- `AutomationTestResult.stopTest()` 中的用例后恢复

这样第一次异常后残留的弹窗、筛选、选中行、遮罩或模块页面状态，会先经过全局恢复和模块级恢复，再进入下一次尝试。重试后通过的用例会计入 `flaky`，飞书汇总中显示为“重试后通过”。

## 失败截图机制

框架在 `core/result.py` 的 `addFailure` 和 `addError` 阶段接入失败截图，截图会发生在用例后恢复机制之前，尽量保留失败现场。

截图由 `core/screenshot.py` 统一处理，默认通过 `run.screenshot_on_failure: true` 开启，策略如下：

1. 如果当前用例存在可用 CDP，优先通过 Playwright/CDP 截取 APP 页面。
2. 如果 CDP 截图失败，尝试桌面截图。
3. 桌面截图优先使用 `mss`，在 Windows、macOS 和有图形会话的 Linux 上作为兜底；Linux Wayland/headless 会话下可能受系统限制失败。
4. Windows 下如果 `mss` 截图失败，再回退到现有 UIAutomation 桌面截图能力。
5. 所有截图保存到 `screenshots/` 目录。
6. 截图成功后会返回截图路径，写入失败摘要和日志；飞书执行总结中的失败摘要也会带上该路径。

截图失败不会覆盖原始用例失败原因，只会写入 warning 日志并继续执行后续恢复流程。

## CDP 连接排查

`http://127.0.0.1:9222/json/version` 能访问只代表 DICloak 的 CDP HTTP 入口还在，不代表 Playwright 已经可以完成页面自动化连接。若日志出现 `ws connected` 后 `BrowserType.connect_over_cdp` 超时，通常表示当前 Electron CDP 会话已经降级或卡住，应关闭 DICloak、DevTools 和残留子进程后重新启动 APP。

框架只支持 Playwright CDP 驱动页面对象。`fallback_driver` 默认保持为空；raw websocket 只能建立底层 CDP socket，不能提供 Playwright `page`，因此不会再作为页面自动化兜底成功返回。`cdp.connect_timeout` 会直接传给 Playwright attach，避免一次连接失败卡住 180 秒。

## 退出码

- `0`：全部通过
- `1`：存在用例失败或异常
- `2`：配置错误或环境预检失败
- `3`：APP 启动失败或 CDP 连接失败，自动化任务取消
- `130`：用户中断

## 配置

复制 `config/config.example.yaml` 为 `config/config.yaml`，复制 `config/test_data.example.yaml` 为 `config/test_data.yaml`。

`config/config.yaml` 只维护运行环境相关配置，例如 APP 路径、CDP、账号、飞书、Windows 系统代理、超时时间、运行控制和日志。`config/test_data.yaml` 只维护用例数据，例如环境名称、导入导出文件、书签、成员导出、抓包工具、本地扩展包路径和自定义代理测试数据。

主配置通过 `test_data_file` 指向测试数据文件。路径支持绝对路径，也支持相对项目根目录或当前配置文件目录。

`account.team_name` 用于配置自动化账号必须切换到的团队。外部账号可能拥有多个团队，框架登录后会读取 `localStorage.basic:state.userInfo.orgName` 校验当前团队；如果不是目标团队，会点击账号菜单里的“切换团队”，等待团队列表加载后切换到目标团队。

Local Auth Lab 相关登录用例统一复用 `config/test_data.yaml` 中的 `test_data.local_auth_lab_login`，避免按用例或按同步场景重复维护账号。例外仅限 `test_26_cookie_data_validation.py`、`test_27_local_storage_data_validation.py`、`test_28_indexeddb_data_validation.py` 三条预置数据校验用例：它们不会执行登录流程，只打开既有环境读取登录态。

- `local_auth_lab_login.cookie`：所有会登录 Cookie 本地模拟站的用例共用，固定账号 `MCDL004`，密码 `M12345678`。
- `local_auth_lab_login.localstorage`：所有会登录 Local Storage 本地模拟站的用例共用，固定账号 `MCDL005`，密码 `M12345678`。
- `local_auth_lab_login.indexeddb`：所有会登录 IndexedDB 本地模拟站的用例共用，固定账号 `MCDL006`，密码 `M12345678`。

版本化示例文件 `config/test_data.example.yaml` 只保留这一份 Local Auth Lab 登录配置，不再保留 `environment_new_cookie_persistence`、`environment_new_local_storage_persistence`、`environment_new_indexeddb_persistence`、`environment_one_way_sync` 或更早按场景拆分的重复配置。

真实配置文件和真实测试数据文件可能包含敏感信息或本机路径，已在 `.gitignore` 中排除。

会修改团队全局设置的用例通过 `GlobalSettingsPage.prepare_api_recovery()` 声明自己影响的配置块；浏览器设置和数据同步同时声明位掩码块。用例开始前会 GET 当前团队 `org_config`，按固定接口基准语义比较；不一致时使用完整 21 块基准请求体 POST 恢复并再次 GET。接口语义比较只覆盖 `browser_config`、`data_sync_config`、`bookmark_config`、`env_data_sync`、`proxy_detect_config`、`access_limit`、`local_data_config`、`env_page_config`、`env_sort_config`、`env_title_config` 十块：关闭项只比较关闭状态，开启项才比较具体内容。通用 UI 快照的采集、断言和显式 UI 恢复能力仍保留，但相关 P0 不再为每条用例采集和恢复整页 UI 快照。

全局设置页面会在进入后预先安装 `org_config` POST 响应监听。点击“确定”后不再等待“保存成功”提示，而是等待对应团队接口返回、页面 loading 结束并校验 HTTP 200 和业务 `code=0`；异常时最多点击“确定”3 次，每次等待 20 秒。成功响应的完整请求体会作为本次保存期望，再通过 GET 做语义复查。直接 GET/POST 的单次超时为 30 秒，最多尝试 3 次，请求头从当前 APP 获取版本、登录 token 和团队 ID，不发送 `X-Device-Id`，也不把 token 返回到 Python 或写入日志。

用例 finally 只 GET 检查本用例实际影响的配置或位；主流程已经恢复成功时跳过重复 POST，仍有差异时把当前 GET 数据与固定基准合并成完整 POST 请求体，只回填本用例影响的块或位，再 GET 复查。原有保存前后复选框、开关、下拉值和意外联动 UI 断言继续保留，因此接口恢复不会替代功能流程本身的页面校验。

长耗时链路已接入非侵入式阶段耗时日志，运行日志中可按 `PHASE elapsed` / `PHASE failed` 检索环境列表打开、环境创建提交、环境打开、环境关闭、环境删除、全局设置打开、快照采集、快照恢复和保存等待等阶段耗时。阶段日志只记录耗时和上下文，不参与断言、不吞异常，也不改变用例执行流程。

## 当前状态

框架基础能力已经搭建到可以加载配置、执行环境预检、发现用例、启动 APP、连接 CDP、发送飞书通知和统计执行结果。当前 `tests/p0` 可发现 95 条 P0 用例：环境管理 43 条、全局设置 22 条、扩展管理 4 条、环境分组管理 6 条、成员分组管理 1 条、成员管理 15 条、代理管理 4 条。

当前环境管理模块已接入 43 条 P0 用例，文件位于 `tests/p0/environment_management/`：

- `test_01_kernel_integrity.py`：按独立阶段校验 142 内核首次启动、缓存拷贝、缓存启动路径、134 内核下载和 134 环境启动；中间阶段失败会记录原因并继续执行后续阶段，最后统一汇总断言，避免 134 下载被前置断言阻断。
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
- `test_26_cookie_data_validation.py`：先执行 `data_sync_config` 接口基准检查，再回到环境管理页并通过全局设置统一入口进入页面；入口等待 `#/setting` 页面可见、“正在加载中...”文案与 loading 遮罩消失、数据同步区域呈现且复选框状态稳定，再检查页面至少有 3 个复选框处于已勾选状态，并安装当前团队配置 POST 监听。不满足时会先重新进入环境管理页，再进入全局设置，最多重新进入 2 次；重试两次后仍不足 3 个时直接以断言异常结束当前用例。随后确保“数据设置 → 数据同步 → Cookie”已勾选，精确搜索并三次打开预置环境 `Cookie数据校验`；每次通过内核 CDP 访问 `http://cookie.dicloak.localhost:18080`、读取登录状态、关闭环境并校验按钮恢复为“打开”。第二次校验后读取 APP 基础设置中的环境缓存目录，只删除其直接子级中名称为 19 位纯数字、且不是链接或重解析点的目录，确认删除完成后第三次打开环境，断言 Cookie 登录状态仍为“已登录”。该用例显式声明 `local_auth_lab` 运行时依赖，结束阶段只在实际写入后检查和恢复数据同步影响位。
- `test_27_local_storage_data_validation.py`：复用同一全局设置加载保护，确保“数据设置 → 数据同步 → Local Storage”已勾选；未勾选时只允许该项从未勾选变为已勾选，检测到其他复选框同时变化会在保存前失败。随后精确搜索并三次打开预置环境 `Local Storage数据校验`，通过内核 CDP 访问 `http://localstorage.dicloak.localhost:18080` 并读取登录状态；每次关闭环境并校验按钮恢复为“打开”，前两次分别断言“已登录”，中间保留 3 秒业务等待。第二次后安全删除缓存根目录直接子级中的 19 位纯数字普通目录并确认无残留，第三次打开后再次断言云端恢复的 Local Storage 登录状态为“已登录”。该用例显式声明 `local_auth_lab` 运行时依赖；2026-08-03 三用例串行真实回归中一次通过。
- `test_28_indexeddb_data_validation.py`：确保“数据设置 → 数据同步 → IndexedDB”已勾选；未勾选时只允许 `IndexedDB` 一个复选框变化，保存后重新进入页面确认持久状态。随后精确搜索并三次打开预置环境 `IndexedDB数据校验`，通过内核 CDP 访问 `http://indexeddb.dicloak.localhost:18080` 并读取登录状态；每次关闭环境、等待内核停止并确认按钮恢复为“打开”，前两次状态任一次不是“已登录”即结束当前用例，第一次和第二次之间保留 3 秒业务等待。第二次后读取基础设置中的缓存目录，安全删除直接子级中的 19 位纯数字普通目录并确认无残留，第三次打开后断言 IndexedDB 登录状态仍为“已登录”。该用例显式声明 `local_auth_lab` 运行时依赖；2026-08-03 三用例串行真实回归中一次通过。
- `test_29_new_environment_cookie_persistence.py`：确保 Cookie 数据同步已勾选后，先删除可能由中断运行留下的同名自动化环境，再沿用原有 `create_environment()` 流程创建默认配置环境 `自动化-新环境Cookie持续保持`，不额外选择环境分组，也不修改代理、内核或指纹配置。创建成功后首次打开并访问 `http://cookie.dicloak.localhost:18080`，使用 `config/test_data.yaml` 中的本地账号 `MCDL004` 登录，等待 2 秒并读取状态；关闭环境且按钮恢复“打开”后断言账号和状态。等待 3 秒再次打开并断言 Cookie 仍保持登录；随后安全删除 APP 缓存根目录中的 19 位纯数字直接子目录，第三次打开并断言云端恢复后仍为 `MCDL004 / 已登录`。最后删除环境并确认列表中不存在；任一阶段失败时也会尝试关闭并清理该专用环境。该用例已接入 `data_sync_config` 接口前置检查和按影响位恢复。
- `test_30_new_environment_local_storage_persistence.py`：确保 Local Storage 数据同步已勾选后，清理可能由异常中断留下的同名环境，并沿用原有 `create_environment()` 创建默认配置环境 `自动化-新环境Local Storage持续保持`；不额外选择环境分组，不修改代理、内核或指纹配置。创建成功后首次打开并访问 `http://localstorage.dicloak.localhost:18080`，使用本地测试数据中的 `MCDL005` 登录，等待 2 秒后读取状态；每次均先关闭环境、等待内核退出并确认按钮恢复为“打开”，再断言账号和状态。等待 3 秒后二次验证，随后安全删除 APP 缓存根目录中的 19 位纯数字直接子目录并确认无残留，第三次打开验证 Local Storage 云端恢复，最后删除环境并确认不存在。该用例已接入 `data_sync_config` 接口前置检查和按影响位恢复。
- `test_31_new_environment_indexeddb_persistence.py`：确保 IndexedDB 数据同步已勾选后，清理可能由异常中断留下的同名环境，并沿用原有 `create_environment()` 创建默认配置环境 `自动化-新环境IndexedDB持续保持`；不额外选择环境分组，不修改代理、内核或指纹配置。创建成功后首次打开并访问 `http://indexeddb.dicloak.localhost:18080`，使用本地测试数据中的 `MCDL006` 登录，等待 2 秒后读取状态；每次均先关闭环境、等待内核退出并确认按钮恢复为“打开”，再断言账号和状态。等待 3 秒后二次验证，随后安全删除 APP 缓存根目录中的 19 位纯数字直接子目录并确认无残留，第三次打开验证 IndexedDB 云端恢复，最后删除环境并确认不存在。该用例已接入 `data_sync_config` 接口前置检查和按影响位恢复。
- `test_32_individual_environment_cookie_sync.py`：创建环境 `自动化-环境单独设置-cookie同步` 时展开“高级设置”，将“数据同步”从“全局设置”切换为“自定义”，并把已知同步项精确调整为仅勾选 `Cookie`。创建成功后首次打开环境访问 `http://cookie.dicloak.localhost:18080`，复用 `local_auth_lab_login.cookie` 本地测试账号 `MCDL004` 登录并等待 2 秒读取状态；关闭环境并校验操作按钮恢复为“打开”后断言 `MCDL004 / 已登录`。等待 3 秒后二次打开验证 Cookie 仍保持登录；随后进入个人设置基础设置读取 APP 环境缓存目录，只删除名称为 19 位纯数字的直接子目录并确认无残留；第三次打开环境验证删除本地缓存后 Cookie 云端恢复仍为 `MCDL004 / 已登录`。最后删除该环境并确认列表中不存在；异常流程也会尝试关闭和清理同名环境。2026-08-17 Windows 真实单跑通过：`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `test_33_individual_environment_local_storage_sync.py`：创建环境 `自动化-环境单独设置-Local Storage同步` 时展开“高级设置”，将“数据同步”从“全局设置”切换为“自定义”，并把已知同步项精确调整为仅勾选 `Local Storage`。创建成功后首次打开环境访问 `http://localstorage.dicloak.localhost:18080`，复用 `local_auth_lab_login.localstorage` 本地测试账号 `MCDL005` 登录并等待 2 秒读取状态；关闭环境并校验操作按钮恢复为“打开”后断言 `MCDL005 / 已登录`。等待 3 秒后二次打开验证 Local Storage 仍保持登录；随后进入个人设置基础设置读取 APP 环境缓存目录，只删除名称为 19 位纯数字的直接子目录并确认无残留；第三次打开环境验证删除本地缓存后 Local Storage 云端恢复仍为 `MCDL005 / 已登录`。最后删除该环境并确认列表中不存在；异常流程也会尝试关闭和清理同名环境。2026-08-17 Windows 真实单跑通过：`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `test_34_individual_environment_indexeddb_sync.py`：创建环境 `自动化-环境单独设置-IndexedDB同步` 时展开“高级设置”，将“数据同步”从“全局设置”切换为“自定义”，并把已知同步项精确调整为仅勾选 `IndexedDB`。创建成功后首次打开环境访问 `http://indexeddb.dicloak.localhost:18080`，复用 `local_auth_lab_login.indexeddb` 本地测试账号 `MCDL006` 登录并等待 2 秒读取状态；关闭环境并校验操作按钮恢复为“打开”后断言 `MCDL006 / 已登录`。等待 3 秒后二次打开验证 IndexedDB 仍保持登录；随后进入个人设置基础设置读取 APP 环境缓存目录，只删除名称为 19 位纯数字的直接子目录并确认无残留；第三次打开环境验证删除本地缓存后 IndexedDB 云端恢复仍为 `MCDL006 / 已登录`。最后删除该环境并确认列表中不存在；异常流程也会尝试关闭和清理同名环境。2026-08-17 Windows 真实单跑通过：`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
单向同步用例也统一读取 `config/test_data.yaml` 中的 `local_auth_lab_login` 登录账号配置；版本化 `config/test_data.example.yaml` 只保留这一份共享配置。
- `test_35_individual_environment_one_way_sync_forbid_current_account.py`：创建环境 `自动化-环境单独设置-单向同步-禁止当前账号同步` 时展开“高级设置”，将“数据同步”切为“自定义”，精确勾选 `Cookie`、`Local Storage`、`IndexedDB`，打开“防止成员覆盖云端数据，导致环境内账号退出登录”开关，等待“白名单”出现后先清空默认值再选择 `超管组`。首次打开环境依次访问 Cookie、Local Storage、IndexedDB 三个本地模拟站，分别登录 `MCDL004`、`MCDL005`、`MCDL006` 并等待 2 秒，逐项断言 `已登录`；关闭环境并确认按钮恢复为“打开”后，进入个人设置基础设置读取 APP 缓存目录，只删除名称为 19 位纯数字的直接子目录并确认无残留；再次打开环境后逐项断言三个站点均为 `未登录`。2026-08-17 Windows 真实单跑通过：`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `test_36_individual_environment_one_way_sync_allow_current_account.py`：创建环境 `自动化-环境单独设置-单向同步-允许当前账号同步` 时展开“高级设置”，将“数据同步”切为“自定义”，精确勾选 `Cookie`、`Local Storage`、`IndexedDB`，打开“防止成员覆盖云端数据，导致环境内账号退出登录”开关，等待“白名单”出现后先清空默认值再选择 `管理组`。首次打开环境依次访问 Cookie、Local Storage、IndexedDB 三个本地模拟站，分别登录 `MCDL004`、`MCDL005`、`MCDL006` 并等待 2 秒，逐项断言 `已登录`；关闭环境并确认按钮恢复为“打开”后，进入个人设置基础设置读取 APP 缓存目录，只删除名称为 19 位纯数字的直接子目录并确认无残留；再次打开环境后逐项断言三个站点仍为对应账号的 `已登录`。2026-08-17 Windows 真实单跑通过：`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `test_37_individual_environment_disable_cookie_sync.py`：创建环境 `自动化-环境单独设置-不勾选cookie同步` 时展开“高级设置”，将“数据同步”切换为“自定义”，只确保 `Cookie` 未勾选，不强行改动其它同步项。首次打开环境访问 `http://cookie.dicloak.localhost:18080`，使用 `local_auth_lab_login.cookie` 中的 `MCDL004 / M12345678` 登录并等待 2 秒，关闭环境且确认按钮恢复为“打开”后断言 `已登录`；未删除本地缓存时再次打开并断言仍为 `MCDL004 / 已登录`；随后进入个人设置基础设置读取 APP 缓存目录，只删除名称为 19 位纯数字的直接子目录并确认无残留；第三次打开后断言 Cookie 模拟站为 `未登录`。用例最后删除新建环境，异常流程也会尝试关闭和清理同名环境。
- `test_38_individual_environment_disable_local_storage_sync.py`：创建环境 `自动化-环境单独设置-不勾选Local Storage同步` 时展开“高级设置”，将“数据同步”切换为“自定义”，只确保 `Local Storage` 未勾选，不强行改动其它同步项。首次打开环境访问 `http://localstorage.dicloak.localhost:18080`，使用 `local_auth_lab_login.localstorage` 中的 `MCDL005 / M12345678` 登录并等待 2 秒，关闭环境且确认按钮恢复为“打开”后断言 `已登录`；未删除本地缓存时再次打开并断言仍为 `MCDL005 / 已登录`；随后进入个人设置基础设置读取 APP 缓存目录，只删除名称为 19 位纯数字的直接子目录并确认无残留；第三次打开后断言 Local Storage 模拟站为 `未登录`。用例最后删除新建环境，异常流程也会尝试关闭和清理同名环境。
- `test_39_individual_environment_disable_indexeddb_sync.py`：创建环境 `自动化-环境单独设置-不勾选IndexedDB同步` 时展开“高级设置”，将“数据同步”切换为“自定义”，只确保 `IndexedDB` 未勾选，不强行改动其它同步项。首次打开环境访问 `http://indexeddb.dicloak.localhost:18080`，使用 `local_auth_lab_login.indexeddb` 中的 `MCDL006 / M12345678` 登录并等待 2 秒，关闭环境且确认按钮恢复为“打开”后断言 `已登录`；未删除本地缓存时再次打开并断言仍为 `MCDL006 / 已登录`；随后进入个人设置基础设置读取 APP 缓存目录，只删除名称为 19 位纯数字的直接子目录并确认无残留；第三次打开后断言 IndexedDB 模拟站为 `未登录`。用例最后删除新建环境，异常流程也会尝试关闭和清理同名环境。
- `test_40_individual_environment_clear_all_cache_every_open_sync_cloud.py`：创建默认配置环境 `自动化-环境单独设置-清除本地全部缓存-每次都清除-同步云端数据` 后首次打开，依次访问 Cookie、Local Storage、IndexedDB 三个本地模拟站，分别使用 `local_auth_lab_login.cookie/localstorage/indexeddb` 中的 `MCDL004`、`MCDL005`、`MCDL006` 登录并等待 2 秒，关闭环境且确认操作按钮恢复为“打开”后逐项断言已登录。随后编辑该环境，展开“高级设置”，将“清除本地缓存”切换为“自定义”，设置“清除方式”为“清除本地全部缓存”、“清除频率”为“每次打开环境时都清除”，并打开“清除后，再同步云端数据”开关；再次打开环境后只逐站读取登录态，不执行登录操作，最终断言三站均为对应账号的 `已登录`。用例最后删除新建环境，异常流程也会尝试关闭和清理同名环境。2026-08-19 Windows 联合真实回归通过：`total=2 passed=2 failed=0 errors=0 skipped=0 flaky=0`。
- `test_41_individual_environment_clear_all_cache_every_open_no_cloud_sync.py`：创建默认配置环境 `自动化-环境单独设置-清除本地全部缓存-每次都清除-不同步云端数据` 后首次打开，依次访问 Cookie、Local Storage、IndexedDB 三个本地模拟站，分别使用共享账号 `MCDL004`、`MCDL005`、`MCDL006` 登录并等待 2 秒，关闭环境且确认操作按钮恢复为“打开”后逐项断言已登录。随后编辑该环境，将“清除本地缓存”切换为“自定义”，设置“清除方式”为“清除本地全部缓存”、“清除频率”为“每次打开环境时都清除”，并确保“清除后，再同步云端数据”开关关闭；再次打开环境后只逐站读取登录态，不执行登录操作，最终断言三站均为 `未登录`。用例最后删除新建环境，异常流程也会尝试关闭和清理同名环境。2026-08-19 Windows 联合真实回归通过：`total=2 passed=2 failed=0 errors=0 skipped=0 flaky=0`。
- `test_42_create_custom_proxy_environment.py`：创建环境 `自动化-使用-自定义代理-的环境`，在创建抽屉中切换“代理设置”为“自定义代理”，通过快捷输入解析 `http://192.168.20.33:7897`，断言解析出的 IP 为 `192.168.20.33`、端口为 `7897`；保存后搜索并确认环境出现在列表中，打开环境前记录浏览器主进程集合，点击“打开”后最多等待 100 秒检测本次新增的 `GinsBrowser` 主进程。随后根据新主进程解析内核 CDP 端口，固定访问 `https://chromewebstore.google.com/`；目标主机正确、页面无导航错误/`ERR_` 且存在有效正文时判定代理连通。连通性断言失败会先记录，仍继续关闭并删除环境，清理完成后再令用例失败。该用例不验证出口 IP 或代理地区；开始和 `finally` 均会按精确名称清理同名环境。
- `test_43_create_environment_with_existing_proxy.py`：创建环境 `自动化-使用-已有代理-的环境`，在创建抽屉中切换“代理设置”为“已有代理”，搜索 `7897` 并选择当前匹配结果第一项，保存后打开环境。创建按钮、抽屉、名称填写、代理下拉、搜索结果、选中值、提交和列表行均只作为元素/流程等待，超时抛操作异常，不作为业务断言。用例只保留三类业务断言：60 秒内出现本次新增的 `GinsBrowser` 主进程；打开后按钮由“打开”扭转为“关闭”且关闭后恢复为“打开”；通过新进程的内核 CDP 固定访问 `https://chromewebstore.google.com/` 并验证可达。连通性失败会先记录，仍继续关闭、验证按钮恢复并删除环境，清理完成后再令用例失败。用例依赖账号中已有可搜索到 `7897` 的代理，不创建、修改、检测或删除代理，也不验证代理地址、类型、出口 IP 或地区。
当前全局设置模块已接入 22 条 P0 用例，文件位于 `tests/p0/global_settings/`：

所有全局设置用例统一通过 `GlobalSettingsPage.open()` 进入。当前路由不在 `#/setting` 时才点击“全局设置”；已经位于设置页时不重复点击。入口会等待页面标识、loading 状态、`#AsyncData` 和复选框状态稳定，并要求至少 3 个复选框已勾选；首次检查不满足时，按“环境管理 → 全局设置”完整重新进入，最多重试 2 次。页面稳定后安装当前团队 `org_config` POST 响应监听，确保监听发生在任何“确定”点击之前。

所有全局设置保存链路在点击“确定”后等待目标 POST 响应和页面 loading 结束，不再读取顶部 `保存成功` 提示。HTTP/网络/业务响应异常时最多重新点击 2 次，总尝试 3 次；成功响应的请求体随后通过 GET 语义复查。复选框、开关、下拉值和非预期联动仍由原有 UI 断言校验。

22 条全局设置 P0 和环境管理中会临时修改全局数据同步项的 `test_26` 至 `test_31` 都在业务流程前执行接口基准检查，并在 `finally` 中只恢复本用例实际影响的配置块或位。主流程已自行恢复时只 GET 确认并跳过 POST；不再逐用例采集或恢复整页 UI 快照。书签基准为关闭状态，因此关闭语义只校验 `status=false`，不依赖 GET 返回被禁用时的历史文件内容。

- `test_01_disable_view_password.py`：校验禁止查看网站密码。
- `test_02_disable_browser_devtools.py`：禁止打开浏览器开发者工具。
- `test_03_disable_extension_management.py`：禁止管理/移除扩展，以及从本地安装扩展至浏览器。
- `test_04_disable_member_access_google_extension_pages.py`：禁止成员访问谷歌扩展商店和扩展设置页面。
- `test_05_block_specific_websites_google_and_baidu.py`：禁止访问指定网址-快捷勾选 Chrome 应用商店、百度，并通过本地 HTTP 探针校验允许网址仍可访问，降低外网波动影响。
- `test_06_allow_specific_website_bilibili.py`：允许访问指定网址，使用本地 HTTP 探针作为允许网址，并校验 Chrome 应用商店、百度仍被拦截。
- `test_07_disable_packet_capture_software.py`：禁用抓包软件，校验抓包进程存在时禁止打开环境，关闭抓包软件后环境可正常打开。
- `test_08_bookmark_setting_overwrite.py`：书签设置-覆盖，校验上传书签文件覆盖内核现有书签。
- `test_09_bookmark_setting_append.py`：书签设置-追加，校验上传书签文件追加到内核现有书签，并覆盖清空书签。
- `test_10_environment_field_display_limit.py`：环境列表字段权限，校验环境列表按设置展示 `环境序号`、`环境名称`，并兼容新版固定保留的 `环境状态` 列，最后恢复列表字段设置能力。
- `test_11_environment_list_pagination_setting.py`：环境列表分页设置，校验固定分页条数后隐藏分页选择器，并可恢复默认分页。
- `test_12_environment_list_sort_limit.py`：环境列表排序设置，校验全局固定排序后隐藏列表排序按钮，并可恢复手动排序。
- `test_13_global_settings_one_way_sync_disallow_current_account.py`：通过接口基准确保三类数据同步项开启后，在 UI 打开单向同步并选择 `超管组` 白名单；创建环境登录三站、删除本地缓存，再断言三站均退出登录。finally 清理环境并按位恢复 `data_sync_config`、按块恢复 `env_data_sync`。
- `test_14_global_settings_one_way_sync_allow_current_account.py`：同样配置全局单向同步并选择 `管理组` 白名单；创建环境登录三站、删除本地缓存后断言三站仍保持对应账号登录。finally 只恢复本用例影响的两个数据同步块。
- `test_15_disable_cookie_data_sync.py`：在 UI 取消 Cookie 同步并保留取消勾选状态断言；创建环境登录 Cookie 站，验证普通重开仍登录、删除本地缓存后不再恢复。finally 按 `data_sync_config.type` 的 Cookie 变化位恢复固定基准。
- `test_16_disable_local_storage_data_sync.py`：在 UI 取消 Local Storage 同步并保留取消勾选状态断言；验证普通重开仍登录、删除本地缓存后不再恢复，finally 只恢复对应数据同步位。
- `test_17_disable_indexeddb_data_sync.py`：在 UI 取消 IndexedDB 同步并保留取消勾选状态断言；验证普通重开仍登录、删除本地缓存后不再恢复，finally 只恢复对应数据同步位。
- `test_18_clear_all_cache_every_open_sync_cloud.py`：创建环境并登录三站，配置全局每次打开清除全部本地缓存且重新同步云端数据，验证第二次打开后三站仍登录；结束时通过 API 将 `local_data_config` 恢复为固定“不清除”基准。
- `test_19_clear_all_cache_every_open_no_cloud_sync.py`：创建环境并登录三站，配置全局每次打开清除全部本地缓存且不同步云端数据，验证第二次打开后三站均未登录；结束时只恢复 `local_data_config`。
- `test_20_extension_tamper_protection.py`：开启全局扩展加密与防篡改，修改预置扩展文件后验证环境被阻止打开，并在收尾阶段恢复扩展文件、环境状态和 `browser_config.type` 中本用例影响的位。
- `test_21_proxy_check_failure_not_open_environment.py`：开启“代理检测失败时，不打开环境”，使用预置代理失败环境验证业务失败弹窗、浏览器主进程未启动且环境按钮仍保持“打开”，最后关闭该全局设置。
- `test_22_country_mismatch_not_open_browser.py`：开启“国家/地区与上一次打开时不一致，不打开浏览器”，使用预置国家不一致环境验证业务阻止弹窗、浏览器主进程未启动且环境保持关闭，最后恢复全局设置。

全局设置模块 2026-05-15 回归曾出现前 4 条用例异常，已定位并修复：复选框脚本中 `checkboxStateSelector` 和 `checkboxInputSelector` 变量未在点击脚本内定义，导致 `ReferenceError`；同时 Chrome Web Store 页面当前会先出现“切换到 Chrome 即可安装扩展程序和主题背景”的前置阻止提示，第三条用例已兼容该稳定阻止证据。最新整模块验证通过：

- `python run.py --config config/config.yaml --module global_settings --attach-existing-app`：基础 12 条历史回归通过，`total=12 passed=12 failed=0 errors=0 skipped=0 flaky=0`；2026-08-18 将两条“全局设置-单向同步”用例从环境管理迁入后增至 14 条；2026-08-19 新增 5 条数据同步与清缓存用例后增至 19 条；当前再纳入扩展防篡改、代理检测失败阻止打开和国家/地区不一致阻止打开 3 条，全局设置模块只读发现为 22 条。

全局设置模块已兼容新版文案和元素入口：`禁止打开浏览器开发者工具` 支持新旧长短文案，网站限制快捷项支持 `Chrome 应用商店` / `谷歌应用商店`，环境列表字段权限支持 `环境列表字段权限` / `环境字段显示限制` 和 `列表字段` / `列表字段设置` 弹窗标题，并兼容新版环境列表强制展示的 `环境状态` 列。`test_07_disable_packet_capture_software.py` 仍依赖 Windows 抓包工具能以当前权限启动；若工具本身需要管理员权限，需以管理员身份运行自动化进程或调整该用例的环境前置策略。

当前已开始编写并验证环境分组管理模块 6 条 P0 用例，文件位于 `tests/p0/environment_group_management/`：

- `test_01_create_environment_group.py`：创建环境分组，校验创建成功后删除并校验删除成功。
- `test_02_group_containing_environment.py`：包含环境的分组，创建分组和归属该分组的环境，通过“包含环境”筛选框校验筛选结果并清除筛选，删除分组时勾选删除分组下环境，并校验分组和环境都被删除。
- `test_03_group_authorized_member.py`：授权成员的分组，通过 `/gin/v1/member` 实时解析预置成员 `自动化成员1` 在当前团队的真实 ID，并从同一接口记录读取原授权环境分组，再定位该成员并追加授权；追加成功和删除分组后的恢复结果继续通过成员列表校验，前端显示的 `all` 与 `全部分组` 按相同语义处理。
- `test_04_filter_group_name.py`：环境分组名称筛选，切换筛选模式到“备注”并搜索 `勿动！！！`，校验列表结果均匹配备注后切回“分组名称”并清除筛选。
- `test_05_edit_group_name.py`：修改环境分组名称，记录首个可编辑分组的名称和 ID，修改为 `自动化-修改环境分组名称` 后按 ID 校验，再还原原名称并按 ID 校验。
- `test_06_edit_group_remark.py`：修改环境分组备注，记录首个可编辑分组的备注和 ID，修改为 `自动化-修改环境分组备注` 后按 ID 校验，再还原原备注并按 ID 校验。

环境分组模块的通用元素已统一维护在 `locators/environment_group_locators.yaml`，包括菜单候选、弹层、表单项、筛选模式切换图标、搜索/清除按钮、下拉项、表格行/单元格、行内编辑入口、行内操作候选和授权成员悬浮窗等；页面对象只保留按业务文本、分组 ID、列内容判断的动态逻辑。

新版环境分组列表不稳定展示分组 ID 时，`EnvironmentGroupPage` 会在 Page Object 内生成内部稳定行 key：优先使用真实 ID，缺失时使用创建时间，最后才回退到当前可见行序号。该 key 只用于页面对象内部完成行匹配、编辑和清理，测试用例仍只表达业务步骤和断言。

当前已开始编写并验证成员管理模块 15 条 P0 用例，文件位于 `tests/p0/member_management/`：

- `test_01_create_external_member.py`：创建外部成员，选择成员分组 `运营组`、环境分组 `未分组`、成员身份 `员工`、上级经理 `外部成员1`，关闭“到期停用”，校验列表字段、悬浮 `成员身份` 后展示的 `外部成员` tooltip 和编辑弹窗邮箱后删除并校验删除成功。
- `test_02_edit_external_member_name.py`：编辑外部成员名称，将 `外部成员1` 修改为 `自动化-编辑外部成员名称` 后校验列表，再还原并校验。
- `test_03_create_internal_member.py`：创建内部成员，填写登录账号和登录密码，选择成员分组 `运营组`、环境分组 `未分组`、成员身份 `员工`、上级经理 `外部成员1`，关闭“到期停用”，校验列表字段、悬浮 `成员身份` 后展示的 `内部成员` tooltip 和编辑弹窗账号后删除并校验删除成功。
- `test_04_edit_internal_member_name.py`：编辑内部成员名称，仅将 `内部成员003` 修改为 `自动化-编辑内部成员名称` 后校验列表，再还原名称；保留现有上级经理和已有环境分组，仅在环境分组为空、APP 阻止提交时补选 `未分组`。
- `test_05_filter_member_group.py`：成员分组筛选，先创建临时 `运营组` 外部成员保证筛选结果非空，依次筛选 `运营组`、清空筛选、筛选 `管理组`、清空筛选，并校验列表“所属成员分组”列均匹配筛选值，最后删除临时成员。
- `test_06_filter_member_name.py`：成员名称/ID 筛选，输入 `自动化成员` 并搜索，校验列表成员名称均包含该关键字；再通过 `/gin/v1/member` 实时解析 `自动化成员1` 在当前团队的真实 ID，清空后按该 ID 搜索并校验结果，不读取账号组主账号 ID。
- `test_07_filter_member_remark.py`：成员备注筛选，通过“更多筛选”抽屉在 `备注` 输入 `必要数据` 并立即筛选，校验列表备注均包含该关键字后清空筛选。
- `test_08_filter_member_login_account_email.py`：登录账号/邮箱筛选，内部登录账号从当前账号组内部成员读取，外部邮箱从当前账号组“用例所需外部成员”读取；筛选后逐行打开编辑弹窗读取对应字段并校验，最后清空筛选。
- `test_09_batch_edit_member_remark.py`：批量编辑成员备注，按原备注定位预置成员，依次校验覆盖备注、追加备注和还原备注，并在失败清理中兜底还原原备注。
- `test_10_export_member.py`：导出成员，目标为 `自动化成员1` 和当前账号组配置的用例外部成员；监听成员接口获取两者真实 ID 后勾选导出所选成员，校验文件名规则并将 Excel 14 列与接口快照逐列比较，最后清理临时文件。
- `test_11_no_edit_permission_member.py`：无编辑权限成员环境操作校验，使用 MCDL007 登录后校验环境列表所有编辑入口（快捷编辑五列、下拉编辑、批量编辑备注、批量更多三项）均不可见，最后切回自动化账号并兜底还原。
- `test_12_api_disable_external_member.py`：API 编辑外部成员-停用成员，通过成员 open API 将指定外部成员置为停用，校验接口状态码和 `msg=success`，再在 APP 内切换页面触发强制退出弹窗，点击“退出登录”后校验回到登录页，最后调用接口启用成员、重新登录自动化账号、确认团队并回到成员列表。
- `test_13_api_disuse_external_member.py`：API 编辑外部成员-到期停用成员，通过成员 open API 设置 `disuse_enable=true`、过期时间和时区，校验接口状态码和 `msg=success`，在 APP 内点击刷新后检查强制退出弹窗；若页面内刷新未触发会话失效，则执行页面级刷新触发检查，点击“退出登录”后校验回到登录页，随后按步骤调用 `status=ENABLED` 重新启用成员，并额外清理到期停用开关，重新登录、确认自动化团队并回到成员列表。
- `test_14_api_disable_internal_member.py`：API 编辑内部成员-停用成员，退出自动化账号后登录内部成员 `MCDL007`，通过成员 open API 将该内部成员置为停用，校验接口状态码和 `msg=success`；在 APP 内切换环境分组/环境管理触发自动退登并校验回到登录页，再直接点击“立即登录”校验停用账号提示且未登录成功；最后调用接口启用成员、验证内部成员可重新登录，并切回自动化账号、确认团队后回到成员列表。
- `test_15_api_disuse_internal_member.py`：API 编辑内部成员-到期停用成员，登录内部成员 `MCDL007` 后通过成员 open API 设置 `disuse_enable=true`、过期时间和时区，校验接口状态码和 `msg=success`；点击 APP 刷新按钮后校验回到登录页，若页面内刷新未触发则用页面级刷新兜底；直接点击“立即登录”校验停用账号提示且未登录成功；最后调用 `status=ENABLED` 启用成员、额外清理到期停用开关，验证内部成员可重新登录，并切回自动化账号、确认团队后回到成员列表。

成员 open API 用例统一使用 `MemberEditApiClient` 调用接口；请求地址、自动化主账号成员 ID、内部成员信息、到期停用参数和状态码重试参数统一维护在 `test_data.api_member_edit`，其中内部成员与重试参数采用 `internal_member`、`disuse`、`status_retry` 小块分组。主账号成员 ID 只允许用于 `test_12`、`test_13` 停用/到期停用接口流程，普通 UI 用例不得读取。真实 token 不写入仓库，优先通过 `DICLOAK_API_MEMBER_EDIT_TOKEN` 环境变量注入；目标主账号 ID 可用 `DICLOAK_API_MEMBER_EDIT_MEMBER_ID` 临时覆盖。

四条成员 open API 用例在异常路径增加了 `api_case_recovery.py` 兜底恢复：用例出现问题后会 best-effort 调用接口恢复自动化账号 `status=ENABLED`、`disuse_enable=false`，再尝试重新登录配置中的自动化账号、确认自动化团队并回到成员列表。恢复失败不会覆盖原始用例失败原因，但会写入 warning 日志，方便排查现场。

成员管理新版列表不再稳定展示成员 ID 时，`MemberPage` 会通过当前 APP 登录态读取成员列表接口数据，并结合可见行的归一化姓名、当前列表索引和“本账号”标记匹配真实成员 ID；DOM 名称末尾的 `(本账号)` 会在映射时移除，同名成员优先使用本账号身份和列表顺序消歧。新版列表不直接显示 `内部成员/外部成员` 时，创建成员用例会先断言列表 `成员身份` 为 `员工`，再 hover 对应单元格读取 tooltip 中的成员类型。

当前已新增代理管理模块 4 条 P0 用例，文件位于 `tests/p0/proxy_management/`：

- `test_01_create_custom_proxy.py`：创建自定义代理，进入代理管理页前先开启 Windows 系统代理，系统代理主机和端口由 `config.yaml` 顶层 `windows_system_proxy.host/port` 配置，默认 `127.0.0.1:7897`，结束后恢复系统代理；进入代理管理页后创建 HTTP 自定义代理，填写主机、端口、账号、密码，并显式确保“代理类型”为 `HTTP`；在创建弹窗中点击“检测代理”，等待“连接测试成功”或“连接失败”；保存后按新代理序号、主机、端口和代理类型一起校验列表创建成功，点击行内第一个操作按钮重新检测并从“检测中”所在单元格读取结果，最后点击行内最后一个操作按钮删除，并按新代理序号、主机、端口和代理类型一起校验删除成功。若弹窗或列表检测结果为“连接失败”，用例会延迟断言失败，同时继续执行清理逻辑。账号和密码优先从本地 `config/test_data.yaml` 或环境变量 `DICLOAK_PROXY_CUSTOM_ACCOUNT`、`DICLOAK_PROXY_CUSTOM_PASSWORD` 读取，不写入仓库模板。
- `test_02_batch_create_proxy.py`：批量创建代理，进入代理管理页点击“批量创建”，先输入单条 `HTTP://192.168.20.33:7897:test:M12345678{批量创建代理}` 并在下方预览表按代理类型、代理主机、代理端口、代理账号、代理密码和代理备注逐项软断言；Windows 平台启用配置中的系统代理 `127.0.0.1:7897` 后点击“检测代理”，等待出口 IP 列检测结束并软断言存在实际出口 IP，随后恢复系统代理；再输入带第 3 行错误的多行数据，软断言出现“第3行格式有误”；最后输入有效多行数据，点击“确定”，按预期成功 3 个、重复 2 个校验结果弹窗，确认后在列表中按新代理序号、类型、主机和端口校验创建结果，勾选本次创建的 3 条代理，通过列表上方批量操作栏点击“删除”并在二次确认弹窗点击“确定删除”，删除后再次校验 3 条代理均不存在。该用例使用软断言收集问题，业务流程和清理不会因中途断言失败提前中断。
- `test_03_create_nodemaven_proxy.py`：创建 NodeMaven 动态代理，进入代理管理页点击“创建代理”，选择 `NodeMaven (动态代理)`，填写主机、端口、账号、密码，选择国家/地区“美国”并填写备注；Windows 平台启用配置中的系统代理 `127.0.0.1:7897` 后在创建弹窗点击“检测代理”，等待“连接测试成功/连接失败”，检测成功时软断言弹窗详情包含 `United States(US)`；点击“确定”后按新代理序号、类型、主机、端口和备注校验列表创建结果，点击该行操作列第一个按钮重新检测，检测成功时软断言出口 IP 列包含 `US-United States`；删除代理前先显式关闭系统代理，再删除该代理并校验删除成功，最后在兜底清理中恢复用例开始前的系统代理快照。该用例的账号和密码优先从本地 `config/test_data.yaml` 的 `test_data.proxy_nodemaven` 或环境变量 `DICLOAK_PROXY_NODEMAVEN_ACCOUNT`、`DICLOAK_PROXY_NODEMAVEN_PASSWORD` 读取。
- `test_04_batch_create_and_bulk_detect_proxy.py`：批量创建并批量检测代理，进入代理管理页点击“批量创建”，输入 1 条 `SOCKS5` 代理 `192.168.20.33:7897` 和 2 条 `HTTP` 代理 `127.0.0.1:7897`、`gate.nodemaven.com:8080`，备注均为“批量检测代理”；NodeMaven 网关账号和密码从本地 `test_data.proxy_nodemaven` 或 `DICLOAK_PROXY_NODEMAVEN_ACCOUNT`、`DICLOAK_PROXY_NODEMAVEN_PASSWORD` 注入，不写入仓库。用例提交批量创建后校验结果弹窗 `成功 3 个、重复 0 个`，在列表中按新代理序号校验三条代理创建成功和可见字段正确，勾选这三条代理后点击列表上方“批量检测”，逐行等待检测结束并软断言连接成功，最后批量删除并校验三条代理均不存在。

代理检测等待说明：创建代理弹窗会先确认真实检测已启动，例如“检测代理”按钮 disabled/loading、弹窗 loading、文案变化或最终结果已出现，再等待“连接测试成功/连接失败”；批量检测和列表行内检测继续基于按钮禁用、出口 IP 列变化和“检测中”状态等待。超时时会输出最后一次按钮状态、loading 状态、出口 IP 文案或当前行文本，便于区分代理连通性问题、APP 未发起检测和列表渲染/保存问题。

代理管理新版列表不直接展示代理 ID，`ProxyPage` 已改为读取表格“序号”作为行 key，用于创建后等待、行内检测、勾选、批量删除和删除后消失校验。代理检测类用例仍依赖配置中的本机系统代理 `windows_system_proxy.host/port` 可用；若 `127.0.0.1:7897` 未监听，检测失败或列表加载失败属于环境前置问题，不归类为元素定位失败。

当前已新增扩展管理模块 4 条 P0 用例，文件位于 `tests/p0/extension_management/`：

- `test_01_create_local_extension.py`：创建本地上传扩展，进入扩展管理页点击“添加扩展”，添加方式切换为“安装包”，先填写 `test_data.local_extension.extension_name` 指定的扩展名称，再上传 `test_data.local_extension.package_path/package_name` 指向的 zip 安装包，扩展分组确保为“未分组”；保存后校验扩展卡片存在、名称正确、提供方为“本地扩展”，随后通过卡片右上角更多菜单删除并校验删除成功。由于 Electron 真实文件选择器返回的 `File.path` 是上传校验关键字段，自动化会在临时 ASCII zip 副本上通过浏览器 file chooser 注入文件，并在页面上下文补齐原始项目 zip 路径；安装包模式识别兼容新版 `accept=".zip,application/zip"` 输入和“将 ZIP 文件拖到此处，或点击上传”的上传区域，上传完成等待兼容弹窗展示完整路径、原始 zip 文件名或临时 ASCII zip 文件名，保存后清理临时文件。
- `test_02_add_market_extension.py`：添加扩展市场里的扩展，进入扩展管理后切换“扩展市场”，按 `test_data.extension_market.extension_name` 搜索，按 `test_data.extension_market.extension_description` 精确匹配搜索结果卡片并点击“添加”；添加弹窗会等待扩展名称和默认分组“未分组”异步回填完成后再确认，随后切回“添加扩展”列表，断言同一扩展卡片同时包含目标名称和描述，最后通过卡片右上角更多菜单删除并校验删除成功。用例开始和 finally 清理均会显式切回“添加扩展”TAB，避免误操作扩展市场搜索结果卡片。
- `test_03_create_google_extension_and_enable.py`：创建 Chrome 应用商店扩展并同时启用，读取 `test_data.google_extension.extension_url/name/description/environment_name`，在“添加扩展”弹窗中保持“Chrome 应用商店”方式，填写扩展 URL，等待扩展分组回填或选择“未分组”，勾选“同时启用该扩展，在自动同步到对应环境”后保存；扩展列表按名称和描述断言，提供方期望为“谷歌商店”，提供方断言失败会记录为延迟断言并继续执行；随后进入环境管理搜索并打开“自动化扩展启用验证”，通过内核 CDP 访问 `chrome://extensions/`，递归读取 Chrome 扩展页 Shadow DOM 文本，断言目标扩展名称和描述存在，失败同样延迟到关闭环境、清空筛选和删除扩展后统一抛出。
- `test_04_hide_extension.py`：隐藏扩展，目标扩展名称固定为 `ZeroOmega`，其余数据读取 `test_data.hide_extension.extension_keyword/member_group/environment_name`；用例开头必须在“添加扩展”列表中找到已有扩展 `ZeroOmega`，找不到会直接失败并提示缺少前置扩展，不会自动创建扩展。用例编辑目标扩展，打开“隐藏设置”，确保“成员分组”为“全部分组”，保存后打开扩展卡片右下角开关；进入环境管理搜索并打开 `自动化扩展启用验证`，访问 `chrome://extensions/` 并断言页面文本不包含 `ZeroOmega`。当前既有 `ZeroOmega` 暂无稳定扩展 ID 可用于内核 target 精确检测，因此该辅助检测仅记录跳过；随后关闭环境、清空筛选、关闭扩展开关（带确认弹窗和最多 2 次重试）、关闭隐藏设置，不删除已有扩展。

最近验证记录：

- `python run.py --config config/config.yaml --module global_settings --attach-existing-app`：2026-08-25 全局设置接口基准与按影响范围恢复落地后，22 条完整模块真实回归通过，`total=22 passed=22 failed=0 errors=0 skipped=0 flaky=0`，运行时间 `19:17:18~19:40:20`。每条运行前基准 GET 均首次成功并确认匹配；UI 保存继续保留控件状态断言，同时以目标 POST 响应和后续 GET 作为持久化证据。
- `python run.py --config config/config.yaml --case <environment test_26...test_31> --attach-existing-app`：2026-08-25 六条环境数据关联用例真实联合回归通过，`total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0`。六条用例内部耗时合计 `509.67s`，相比 2026-08-24 旧 UI 快照恢复流程的 `573.17s` 减少 `63.50s`，约 `11.1%`；当前主要耗时来自 18 次环境启动/关闭、环境列表重复加载、内核 CDP 接入及新环境创建/删除，不是三种存储接口本身。
- `python run.py --config config/config.yaml --case tests.p0.global_settings.test_02_disable_browser_devtools.TestDisableBrowserDevtools.test_disable_browser_devtools --attach-existing-app`：2026-08-25 全局设置接口基准与按位恢复改造后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`，用例耗时 `37.43s`。UI 保存响应监听和 GET 复查均在首次尝试成功；finally 检出 DevTools 位仍偏离基准后执行完整 POST，并再次 GET 通过，验证了 `browser_config.type` 只恢复本用例动态识别出的变化位。
- `python run.py --config config/config.yaml --case tests.p0.global_settings.test_11_environment_list_pagination_setting.TestEnvironmentListPaginationSetting.test_environment_list_pagination_setting --attach-existing-app`：2026-08-25 接口恢复改造前后连续真实验证均通过。首次运行由前置 GET 发现 `browser_config.type=1` 与新基准 `32769` 不一致，完整 POST 基准并复查成功，用例耗时 `61.31s`；移除逐用例 UI 快照采集和 finally 页面重入后复跑耗时 `50.05s`，减少 `11.26s`。分页设置在主流程自行关闭，finally 仅 GET 确认已恢复并跳过重复 POST。
- `python -m unittest discover -s tests/p1 -p "test_*.py"`：2026-08-25 全局设置接口恢复单元回归通过，`Ran 188 tests ... OK`。新增覆盖完整 21 块基准、10 块语义白名单、关闭项内容忽略、开启项内容校验、位掩码合并、完整恢复请求体、直接接口 3 次重试、UI 保存响应监听、HTTP 异常重试、GET 不一致报错和不发送 `X-Device-Id`。
- `python run.py --config config/config.yaml --module test_43_create_environment_with_existing_proxy.py --attach-existing-app`：2026-08-25 已有代理环境断言边界与 Chrome Web Store 连通性变更后最终代码真实运行通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`，用例耗时 `53.26s`（unittest 总耗时 `62.721s`）。实际页面证据为 `target_url=https://chromewebstore.google.com/`、标题 `Chrome Web Store`、`error=''`、正文长度 `3144088`；按钮完成“打开→关闭→打开”，环境 `自动化-使用-已有代理-的环境` 已关闭并删除。首次运行曾因已有代理下拉 input 的 `aria-controls` 异步挂载而在操作等待阶段报错；页面对象改为轮询等待该稳定标识、超时抛 `TimeoutError` 后重跑通过。
- `python run.py --config config/config.yaml --module test_42_create_custom_proxy_environment.py --attach-existing-app`：2026-08-25 自定义代理环境连通性变更后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`，用例耗时 `54.07s`（unittest 总耗时 `63.412s`）。内核页面证据为 `target_url=https://chromewebstore.google.com/`、标题 `Chrome Web Store`、`error=''`、正文长度 `4863115`；环境 `自动化-使用-自定义代理-的环境` 已正常关闭并删除。
- `python run.py --config config/config.yaml --case tests.p0.global_settings.test_15_disable_cookie_data_sync.TestDisableCookieDataSync.test_cookie_not_restored_after_cache_deletion_when_global_cookie_sync_disabled --attach-existing-app`：2026-08-21 当时的“保存成功”提示优先判定真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`，用例耗时 `134.93s`。该记录仅保留为历史证据；2026-08-25 起保存完成判定已替换为目标 POST 响应、loading 结束和后续 GET 复查，不再读取该提示。
- `python run.py --config config/config.yaml --case tests.p0.extension_management.test_01_create_local_extension.TestCreateLocalExtension.test_create_local_extension_and_delete --attach-existing-app`：2026-08-21 本地扩展上传 UI 改版后重新临时脚本探测并修复，确认新版 ZIP 输入为 `accept=".zip,application/zip"`，上传入口为“将 ZIP 文件拖到此处，或点击上传”的 `.el-upload` 区域；修复后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`，用例耗时 `14.71s`。
- `python run.py --config config/config.yaml --case tests.p0.extension_management.test_01_create_local_extension.TestCreateLocalExtension.test_create_local_extension_and_delete --case tests.p0.proxy_management.test_04_batch_create_and_bulk_detect_proxy.TestBatchCreateAndBulkDetectProxy.test_batch_create_proxy_then_bulk_detect_and_delete --attach-existing-app`：2026-08-21 修复 macOS 远端全量暴露的本地扩展上传等待和批量代理数据撞库后，受影响用例联合真实回归通过，`total=2 passed=2 failed=0 errors=0 skipped=0 flaky=0`。本地扩展流程已调整为先填写扩展名称再上传 zip，上传完成等待兼容完整路径、原始 zip 文件名和临时 ASCII zip 文件名；批量代理第一条数据已从 `HTTP://192.168.20.33:7897{批量检测代理}` 调整为 `SOCKS5://192.168.20.33:7897{批量检测代理}`，本次运行新建代理序号 `803/804/805` 已批量删除。
- `python -c "from streamlit_runner import discover_cases; print(len(discover_cases()))"`：2026-08-21 拉取远端最新代码后，用例发现数量为 93 条；按 `tests/p0` 文件结构统计，当前 P0 分布为环境管理 43、全局设置 20、扩展管理 4、环境分组管理 6、成员分组管理 1、成员管理 15、代理管理 4。本次拉取新增环境管理 `test_42_create_custom_proxy_environment.py` 和 `test_43_create_environment_with_existing_proxy.py`，并补充对应 P1 页面对象契约测试及 `docs/superpowers/` 设计/计划文档。
- `python run.py --config config/config.yaml --case tests.p0.extension_management.test_04_hide_extension.TestHideExtension.test_hide_extension_from_chrome_extensions_page --attach-existing-app`：2026-08-20 按用例前置口径修正“隐藏扩展”为必须使用已有 `ZeroOmega` 后真实单跑失败，`total=1 passed=0 failed=0 errors=1 skipped=0 flaky=0`，失败点为已有 `ZeroOmega` 编辑隐藏设置后点击“确定”弹窗未关闭：`TimeoutError: overlay did not close`。用例不会自动创建或删除扩展，缺少已有 `ZeroOmega` 时会在开头直接失败；当时 P0 发现为 91 条：环境管理 41、全局设置 20、扩展管理 4、环境分组管理 6、成员分组管理 1、成员管理 15、代理管理 4。
- `python run.py --config config/config.yaml --business-module 扩展管理 --attach-existing-app`：2026-08-20 新增扩展管理“创建谷歌扩展同时启用扩展”用例后真实模块运行通过，`total=3 passed=3 failed=0 errors=0 skipped=0 flaky=0`。此前先用临时脚本验证添加弹窗默认 Chrome 应用商店模式、URL textarea、分组异步回填和“同时启用”复选框状态，再用临时完整流程跑通“Chrome 商店 URL 添加 → 勾选同时启用 → 列表名称/描述/提供方读取 → 打开自动化扩展启用验证环境 → chrome://extensions/ 名称和描述校验 → 关闭环境 → 删除扩展”闭环，输出 `TMP_GOOGLE_EXTENSION_ENABLE_FLOW_OK` 后才整理正式用例。新增单用例 `test_03_create_google_extension_and_enable.py` 真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。当前 P0 发现为 90 条：环境管理 41、全局设置 20、扩展管理 3、环境分组管理 6、成员分组管理 1、成员管理 15、代理管理 4。
- `python run.py --config config/config.yaml --business-module 扩展管理 --attach-existing-app`：2026-08-20 新增扩展市场“添加市场扩展并删除”用例后真实模块运行通过，`total=2 passed=2 failed=0 errors=0 skipped=0 flaky=0`。此前先用临时脚本完整验证“扩展市场搜索 → 按名称和描述匹配搜索结果 → 添加弹窗等待名称/分组回填 → 确认添加 → 添加扩展列表名称和描述校验 → 删除并校验删除成功”闭环，临时脚本输出 `TMP_EXTENSION_MARKET_ADD_FLOW_OK`。新增单用例 `test_02_add_market_extension.py` 真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。当前 P0 发现为 89 条：环境管理 41、全局设置 20、扩展管理 2、环境分组管理 6、成员分组管理 1、成员管理 15、代理管理 4。
- `python run.py --config config/config.yaml --business-module 扩展管理 --attach-existing-app`：2026-08-20 新增扩展管理“创建本地扩展”用例后真实模块运行通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。此前先用临时脚本完整验证“添加扩展 → 安装包上传 → 名称/分组填写 → 列表名称和提供方校验 → 删除并校验删除成功”闭环，临时脚本输出 `TMP_EXTENSION_LOCAL_UPLOAD_FLOW_OK`。当时 P0 发现为 88 条：环境管理 41、全局设置 20、扩展管理 1、环境分组管理 6、成员分组管理 1、成员管理 15、代理管理 4。
- `python run.py --config config/config.yaml --case tests.p0.global_settings.test_19_clear_all_cache_every_open_no_cloud_sync.TestGlobalSettingsClearAllCacheEveryOpenNoCloudSync.test_clear_all_cache_every_open_without_cloud_sync_clears_site_login_state --attach-existing-app`：2026-08-19 新增全局设置“清除本地全部缓存-每次都清除-不同步云端数据”用例后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。用例首次打开新建默认配置环境后分别登录 Cookie、Local Storage、IndexedDB 三站，第二次打开环境只访问并读取状态不再登录，三站均为 `未登录`；结束时删除新建环境，并通过全局设置快照恢复其它配置，同时把“清除方式”恢复为“不清除”。同步验证完整 P1 `Ran 119 tests ... OK`，P0 发现为 85 条。
- `python run.py --config config/config.yaml --case tests.p0.global_settings.test_18_clear_all_cache_every_open_sync_cloud.TestGlobalSettingsClearAllCacheEveryOpenSyncCloud.test_clear_all_cache_every_open_then_sync_cloud_data_keeps_sites_logged_in --attach-existing-app`：2026-08-19 新增全局设置“清除本地全部缓存-每次都清除-同步云端数据”用例后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。用例首次打开新建默认配置环境后分别登录 Cookie、Local Storage、IndexedDB 三站，第二次打开环境只访问并读取状态不再登录，三站直接恢复为 `MCDL004/MCDL005/MCDL006 / 已登录`；结束时删除新建环境，并通过全局设置快照恢复其它配置，同时把“清除方式”恢复为“不清除”。同步验证完整 P1 `Ran 118 tests ... OK`，P0 发现为 84 条。
- `python run.py --config config/config.yaml --case tests.p0.environment_management.test_40_individual_environment_clear_all_cache_every_open_sync_cloud.TestIndividualEnvironmentClearAllCacheEveryOpenSyncCloud.test_clear_all_cache_every_open_then_sync_cloud_data_keeps_sites_logged_in --case tests.p0.environment_management.test_41_individual_environment_clear_all_cache_every_open_no_cloud_sync.TestIndividualEnvironmentClearAllCacheEveryOpenNoCloudSync.test_clear_all_cache_every_open_without_cloud_sync_clears_site_login_state --attach-existing-app`：2026-08-19 根据用例流程修正，“同步云端数据”场景第二次打开环境后只读取三站登录态，不再执行登录；同时验证“不同步云端数据”场景第二次打开后也只读取登录态。联合真实回归通过，`total=2 passed=2 failed=0 errors=0 skipped=0 flaky=0`；`test_40` 第二轮三站直接恢复为 `MCDL004/MCDL005/MCDL006 / 已登录`，`test_41` 第二轮三站均为 `未登录`。同步验证完整 P1 `Ran 116 tests ... OK`，P0 发现为 83 条。
- `python run.py --config config/config.yaml --case tests.p0.environment_management.test_40_individual_environment_clear_all_cache_every_open_sync_cloud.TestIndividualEnvironmentClearAllCacheEveryOpenSyncCloud.test_clear_all_cache_every_open_then_sync_cloud_data_keeps_sites_logged_in --attach-existing-app`：2026-08-19 新增环境管理“环境单独设置-清除本地全部缓存-每次都清除-同步云端数据”用例后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。首次打开依次登录三站，状态为 `MCDL004 / 已登录`、`MCDL005 / 已登录`、`MCDL006 / 已登录`；编辑环境启用“清除本地全部缓存”“每次打开环境时都清除”“清除后，再同步云端数据”后再次打开，只读取登录态不再登录，三站直接恢复为对应账号的 `已登录`，用例结束后删除新建环境。后续已在“同步/不同步云端数据”联合回归中重新验证，当前完整 P1 为 `Ran 116 tests ... OK`，P0 发现为 83 条。
- `python run.py --config config/config.yaml --case tests.p0.environment_management.test_39_individual_environment_disable_indexeddb_sync.TestIndividualEnvironmentDisableIndexedDBSync.test_indexeddb_not_restored_after_cache_deletion_when_individual_indexeddb_sync_disabled --attach-existing-app`：2026-08-19 新增环境管理“环境单独设置-不勾选 IndexedDB 同步”用例后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。用例创建自定义数据同步环境，只取消勾选 IndexedDB，三段状态依次为 `MCDL006 / 已登录`、未删除本地缓存再次打开后 `MCDL006 / 已登录`、删除 2 个合规 19 位缓存目录后 `未登录`；用例结束后删除新建环境。同步验证完整 P1 `Ran 114 tests ... OK`，P0 发现为 81 条。
- `python run.py --config config/config.yaml --case tests.p0.global_settings.test_17_disable_indexeddb_data_sync.TestDisableIndexedDBDataSync.test_indexeddb_not_restored_after_cache_deletion_when_global_indexeddb_sync_disabled --attach-existing-app`：2026-08-19 新增全局设置“不勾选 IndexedDB 同步”用例后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。用例先将全局设置 IndexedDB 取消勾选并保存，三段状态依次为 `MCDL006 / 已登录`、未删除本地缓存再次打开后 `MCDL006 / 已登录`、删除 2 个合规 19 位缓存目录后 `未登录`；用例结束后删除新建环境并恢复全局设置 IndexedDB 勾选。同步验证完整 P1 `Ran 114 tests ... OK`，P0 发现为 80 条。
- `python run.py --config config/config.yaml --case tests.p0.environment_management.test_38_individual_environment_disable_local_storage_sync.TestIndividualEnvironmentDisableLocalStorageSync.test_local_storage_not_restored_after_cache_deletion_when_individual_local_storage_sync_disabled --attach-existing-app`：2026-08-19 新增环境管理“环境单独设置-不勾选 Local Storage 同步”用例后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。用例创建自定义数据同步环境，只取消勾选 Local Storage，三段状态依次为 `MCDL005 / 已登录`、未删除本地缓存再次打开后 `MCDL005 / 已登录`、删除 2 个合规 19 位缓存目录后 `未登录`；用例结束后删除新建环境。同步验证完整 P1 `Ran 111 tests ... OK`，P0 发现为 79 条。
- `python run.py --config config/config.yaml --case tests.p0.global_settings.test_16_disable_local_storage_data_sync.TestDisableLocalStorageDataSync.test_local_storage_not_restored_after_cache_deletion_when_global_local_storage_sync_disabled --attach-existing-app`：2026-08-19 新增全局设置“不勾选 Local Storage 同步”用例后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。用例先将全局设置 Local Storage 取消勾选并保存，三段状态依次为 `MCDL005 / 已登录`、未删除本地缓存再次打开后 `MCDL005 / 已登录`、删除 2 个合规 19 位缓存目录后 `未登录`；用例结束后删除新建环境并恢复全局设置 Local Storage 勾选。当时同步验证完整 P1 `Ran 111 tests ... OK`，P0 发现为 78 条。
- `python run.py --config config/config.yaml --case tests.p0.environment_management.test_37_individual_environment_disable_cookie_sync.TestIndividualEnvironmentDisableCookieSync.test_cookie_not_restored_after_cache_deletion_when_individual_cookie_sync_disabled --attach-existing-app`：2026-08-19 新增环境管理“环境单独设置-不勾选 Cookie 同步”用例后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。三段状态依次为 `MCDL004 / 已登录`、未删除本地缓存再次打开后 `MCDL004 / 已登录`、删除 2 个合规 19 位缓存目录后 `未登录`；用例结束后删除新建环境。同步验证完整 P1 `Ran 108 tests ... OK`，P0 发现为 77 条。
- `python run.py --config config/config.yaml --case tests.p0.global_settings.test_15_disable_cookie_data_sync.TestDisableCookieDataSync.test_cookie_not_restored_after_cache_deletion_when_global_cookie_sync_disabled --attach-existing-app`：2026-08-19 新增全局设置“不勾选 Cookie 同步”用例后真实单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。三段状态依次为 `MCDL004 / 已登录`、未删除本地缓存再次打开后 `MCDL004 / 已登录`、删除 2 个合规 19 位缓存目录后 `未登录`；用例结束后删除新建环境并恢复全局设置 Cookie 勾选。同步验证 `python -m unittest discover -s tests/p1 -p "test_*.py"` 通过；新增环境单独设置不勾选 Cookie 同步用例并补充页对象单测后，当前 P1 为 `Ran 108 tests ... OK`。
- `python run.py --config config/config.yaml --module global_settings --attach-existing-app`：2026-08-18 全局设置快照恢复改造后真实运行，基础 12 条通过，`test_13`、`test_14` 因当时本机忽略配置缺少旧单向同步共享账号配置，在用例数据校验阶段失败，结果 `total=14 passed=12 failed=2 errors=0 skipped=0 flaky=0`；补齐当时本机 `config/test_data.yaml` 的共享账号配置后，单独补跑两条全局单向同步用例通过，`total=2 passed=2 failed=0 errors=0 skipped=0 flaky=0`。2026-08-19 起登录类用例已统一改读 `local_auth_lab_login`。
- `python run.py --config config/config.yaml --case tests.p0.environment_management.test_26_cookie_data_validation.TestCookieDataValidation.test_cookie_data_survives_close_reopen_and_local_cache_deletion --case tests.p0.environment_management.test_27_local_storage_data_validation.TestLocalStorageDataValidation.test_local_storage_data_survives_close_reopen_and_local_cache_deletion --case tests.p0.environment_management.test_28_indexeddb_data_validation.TestIndexedDBDataValidation.test_indexeddb_data_survives_close_reopen_and_local_cache_deletion --case tests.p0.environment_management.test_29_new_environment_cookie_persistence.TestNewEnvironmentCookiePersistence.test_new_environment_cookie_survives_close_reopen_and_local_cache_deletion --case tests.p0.environment_management.test_30_new_environment_local_storage_persistence.TestNewEnvironmentLocalStoragePersistence.test_new_environment_local_storage_survives_close_reopen_and_local_cache_deletion --case tests.p0.environment_management.test_31_new_environment_indexeddb_persistence.TestNewEnvironmentIndexedDBPersistence.test_new_environment_indexeddb_survives_close_reopen_and_local_cache_deletion --attach-existing-app`：2026-08-18 环境管理侧涉及全局设置快照恢复的 6 条通过，`total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0`。
- 当前 APP `127.0.0.1:9222` 全局设置真实快照已读取并保存到 `reports/snapshots/global_settings_snapshot_20260818_161352.json`；随后使用同一快照执行一次无变更 UI 恢复验证，`restore_global_settings_snapshot()` 完成后重新读取的强校验字段与原始快照一致。
- `python -m compileall -q core pages tests streamlit_runner.py run.py ui`、`config/test_data.example.yaml` 与本机 `config/test_data.yaml` YAML 解析检查、Local Auth Lab 共享登录配置读取验证、`git diff --check`：2026-08-19 将所有会登录本地模拟站的用例统一收敛到 `local_auth_lab_login` 后均通过；当前 example YAML 仅保留这一条 Local Auth Lab 相关账号配置。
- `python -m unittest discover -s tests/p1 -p "test_*.py"`：2026-08-04 修复 macOS 远端 Local Auth Lab 认证状态同步脚本未加载 venv 且裸跑 `python` 的问题后通过，`Ran 100 tests ... OK`；定向 `python -m unittest tests.p1.test_remote_sync -v` 通过，`Ran 7 tests ... OK`。
- `python run.py --config config/config.yaml --module test_02_create_default_environment.py --attach-existing-app` 与 `python run.py --config config/config.yaml --module test_03_batch_create_environments.py --attach-existing-app`：2026-08-04 为创建环境抽屉“确定”按钮增加二次提交保护后均通过，结果分别为 `total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。当前逻辑为：点击“确定”后若抽屉未关闭且按钮未进入 loading，则等待 2 秒后再次点击“确定”；第二次仍未关闭且未进入 loading 时才重新打开创建抽屉，最多重新打开 2 次，每次重开后都保留同样的 2 秒后二次点击。
- `python -m unittest discover -s tests/p1 -p "test_*.py"`：2026-08-04 创建环境抽屉二次提交保护加入后通过，`Ran 99 tests ... OK`。
- `python -m unittest discover -s tests/p1 -p "test_*.py"`：2026-08-04 为环境列表进入/创建后/搜索后的 loading 等待增加搜索刷新重试保护后通过，`Ran 97 tests ... OK`；真实页面非变更烟测 `open_list()`、`search_environment_without_assert("_tmp_refresh_probe_")`、`clear_search()` 输出 `REAL_LIST_WAIT_SMOKE_OK`。当时真实创建用例 `test_02_create_default_environment.py --attach-existing-app` 被创建抽屉提交按钮未进入 loading 的保护拦截，未走到创建成功后的列表刷新阶段，因此不作为本次列表 loading 改动的通过结论；该提交问题已在后续二次提交保护中修复。
- `python run.py --config config/config.yaml --module test_02_create_default_environment.py --attach-existing-app` 与 `python run.py --config config/config.yaml --module test_03_batch_create_environments.py --attach-existing-app`：2026-08-04 为创建环境/批量创建环境抽屉增加默认 `未分组` 回显等待与提交 loading 状态保护后均通过，结果分别为 `total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。进入创建抽屉后会等待 `环境分组` 回显 `未分组`，20 秒未回显则最多重新打开抽屉 2 次；点击“确定”后若抽屉未关闭且按钮未进入 loading，也最多重新打开抽屉 2 次，仍未满足时按用例异常处理。
- `python run.py --config config/config.yaml --module test_02_create_default_environment.py --attach-existing-app`：2026-07-09 通过 `127.0.0.1:9222` CDP 确认环境列表真实 DOM 后，补强表格 loading 等待，单跑通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_10_environment_field_display_limit.py --attach-existing-app`：2026-07-09 兼容新版强制展示 `环境状态` 列后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_01_create_external_member.py --attach-existing-app`：2026-07-09 兼容成员类型改为 hover `成员身份` tooltip 展示后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_03_create_internal_member.py --attach-existing-app`：2026-07-09 兼容成员类型改为 hover `成员身份` tooltip 展示后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_11_no_edit_permission_member.py --attach-existing-app`：2026-07-09 兼容退出登录头像点击被 tooltip 拦截后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python -m compileall -q pages tests` 和 `git diff --check`：2026-07-09 静态验证通过，`git diff --check` 仅有当前 Windows 工作区 LF/CRLF 换行提示。
- `python run.py --config config/config.yaml --module environment_group_management --attach-existing-app`：2026-07-01 环境分组新版无 ID 行 key 兼容后通过，`total=6 passed=6 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module environment_management --attach-existing-app`：2026-07-01 环境管理元素修复后模块通过，`total=25 passed=25 failed=0 errors=0 skipped=0 flaky=1`。
- `python run.py --config config/config.yaml --module member_management --attach-existing-app`：2026-07-01 成员管理真实 ID 匹配修复后通过，`total=15 passed=15 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --attach-existing-app`：2026-07-01 P0 全量结果 `total=62 passed=57 failed=1 errors=4 skipped=0 flaky=1`；剩余问题已归类为抓包工具管理员权限、`127.0.0.1:7897` 本地代理不可用和 NodeMaven/IP 查询环境波动，未发现新的元素定位失败。
- `python run.py --config config/config.yaml --case <Cookie> --case <Local Storage> --case <IndexedDB>`：2026-08-03 使用单一 Runner 按 Cookie → Local Storage → IndexedDB 串行真实回归通过，`total=3 passed=3 failed=0 errors=0 skipped=0 flaky=0`，三种数据同步项均为 `changed=False`；三站三次读取全部为“已登录”，账号依次为 `MCDL001`、`MCDL002`、`MCDL003`，每次关闭环境后操作按钮均恢复为“打开”，每条用例删除合规缓存目录后第三次恢复成功。
- `python run.py --config config/config.yaml --module test_10_environment_field_display_limit.py --attach-existing-app`：2026-06-30 兼容全局设置“环境列表字段权限”和环境列表“列表字段”新文案后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_04_create_134_kernel_environment.py --attach-existing-app`：2026-06-30 兼容创建环境抽屉内层“指纹设置”（旧版“更多指纹”）入口后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_02_batch_create_proxy.py --attach-existing-app`：2026-06-30 代理列表新版不直接展示 ID 后改为按表格序号定位、选择和批量删除，结果 `total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_04_batch_create_and_bulk_detect_proxy.py`：2026-06-25 新增代理管理“批量创建代理后批量检测”用例后通过，结果 `total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`；日志确认三条代理创建成功，列表上方“批量检测”后三条代理均返回 `连接成功`，随后按新代理序号批量删除并校验不存在。
- `python run.py --config config/config.yaml --module test_02_batch_create_proxy.py --attach-existing-app`：2026-06-24 优化代理检测等待诊断后复跑通过，结果 `total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`；批量检测仍按真实按钮禁用/出口 IP 列变化结束，未增加硬等待。
- `python run.py --config config/config.yaml --module test_03_create_nodemaven_proxy.py --attach-existing-app`：2026-06-24 优化代理检测等待诊断后复跑通过，结果 `total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`；日志确认创建弹窗检测返回 `连接测试成功` 且详情包含 `国家/地区: United States(US)`，列表行内检测返回 `连接成功` 且出口 IP 列包含 `US-United States`，删除代理前先出现 `System proxy disable before NodeMaven delete`，随后按当时的新代理 ID 删除并校验不存在；新版列表当前已改为按表格序号行 key。
- `python run.py --config config/config.yaml --module test_13_sort_environment_serial.py --attach-existing-app`：2026-06-08 兼容环境列表表头由“环境序号/环境名称/环境分组”调整为“序号/名称/分组”后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_14_move_remark_column.py --attach-existing-app`：2026-06-08 兼容列表字段设置中“序号/名称/分组”短文案后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_10_environment_field_display_limit.py --attach-existing-app`：2026-06-08 兼容全局设置环境字段显示限制中的环境字段短文案后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_12_environment_list_sort_limit.py --attach-existing-app`：2026-06-08 兼容全局设置环境列表排序字段短文案和升序/降序回显后通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
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
- `python run.py --config config/config.yaml --module member_management --attach-existing-app`：成员管理早期 11 条用例通过，`total=11 passed=11 failed=0 errors=0 skipped=0 flaky=0`；当前成员管理完整模块已扩展到 15 条，最新结果见 2026-07-01 记录。
- `python run.py --config config/config.yaml --module test_11_no_edit_permission_member.py --attach-existing-app`：新增"无编辑权限成员环境操作校验"用例通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_12_api_disable_external_member.py --attach-existing-app`：新增“API编辑外部成员-停用成员”用例通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_13_api_disuse_external_member.py --attach-existing-app`：新增“API编辑外部成员-到期停用成员”用例通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`，耗时约 23.38s；临时探测确认页面内刷新图标不会稳定触发到期停用强制退出弹窗，页面级刷新可触发。
- `python run.py --config config/config.yaml --module test_14_api_disable_internal_member.py --attach-existing-app`：新增“API编辑内部成员-停用成员”用例通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`，耗时约 43.92s；已补强 `logout_to_login_page()`，并让内部成员登录步骤在当前已是 `MCDL007` 时直接复用登录态，避免停用前重复退出/登录。
- `python run.py --config config/config.yaml --module test_15_api_disuse_internal_member.py --attach-existing-app`：新增“API编辑内部成员-到期停用成员”用例通过，`total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`，耗时约 58.45s；补充成员 open API 非 200 状态码重试 3 次后回归通过。
- 四条成员 open API 用例补充异常兜底恢复后回归通过：`test_12_api_disable_external_member.py`、`test_13_api_disuse_external_member.py`、`test_14_api_disable_internal_member.py`、`test_15_api_disuse_internal_member.py` 分别单跑通过，均为 `total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python -m compileall -q pages tests core`：2026-06-09 新增代理管理“创建自定义代理”用例后通过。
- `git diff --check`：2026-06-09 新增代理管理“创建自定义代理”用例后通过，仅提示 `config/test_data.example.yaml`、`core/config.py` 工作区 LF/CRLF 转换。
- `python run.py --config config/config.yaml --module test_01_create_custom_proxy.py --attach-existing-app`：2026-06-09 将 ping/F5 预检改为开启配置中的 Windows 系统代理后通过，默认配置为 `127.0.0.1:7897`；日志确认用例开始时开启系统代理、结束时关闭系统代理，结果 `total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`。
- `python run.py --config config/config.yaml --module test_01_create_custom_proxy.py --attach-existing-app`：2026-06-09 代理管理“创建自定义代理”补充 HTTP 类型选择和类型校验后通过，结果 `total=1 passed=1 failed=0 errors=0 skipped=0 flaky=0`；日志确认创建行 `type=HTTP`、执行行内检测、删除单条新代理，运行后注册表确认 `ProxyEnable=0`。
- `python -c "from streamlit_runner import discover_cases; cases=discover_cases(); print(len(cases))"`：新增代理管理用例后的早期发现数量为 59 条；当前可发现数量为 93 条。
- `python run.py --config config/config.yaml --attach-existing-app`：早期全量 P0 运行通过，`total=54 passed=54 failed=0 errors=0 skipped=0 flaky=0`（2026-05-29 两次验证）；当前全量状态见 2026-07-01 记录。

扩展管理、成员分组管理等模块已开始接入 P0 用例，后续新增用例继续按业务模块放入对应目录。
