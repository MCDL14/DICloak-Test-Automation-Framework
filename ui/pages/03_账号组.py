"""维护本机与远程并行执行使用的两组自动化账号。"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.account_groups import (  # noqa: E402
    ACCOUNT_GROUP_SLOTS,
    AccountGroupError,
    load_account_groups,
    save_account_groups,
)
from core.config import ConfigError, load_config  # noqa: E402
from core.app_packages import (  # noqa: E402
    AppPackageError,
    TEST_ACCOUNT_GROUPS_PATH,
    TEST_PACKAGE_SETTINGS_PATH,
    load_test_package_settings,
    save_test_package_settings,
)


_ACCOUNT_GROUPS_PATH = _PROJECT_ROOT / "config" / "account_groups.yaml"
_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"


st.set_page_config(page_title="自动化账号组", page_icon="🔐", layout="wide")
st.title("自动化账号组")
package_label = st.radio(
    "账号配置范围", ["生产 APP 包", "测试 APP 包"], horizontal=True,
    key="account_package_scope",
)
is_test_package = package_label == "测试 APP 包"
package_kind = "test" if is_test_package else "production"
account_groups_path = _PROJECT_ROOT / TEST_ACCOUNT_GROUPS_PATH if is_test_package else _ACCOUNT_GROUPS_PATH
st.caption(
    "两组账号分别供 Windows 本机和 macOS 远程执行选择。"
    f"当前编辑：{package_label}，仅保存到 `{account_groups_path.relative_to(_PROJECT_ROOT).as_posix()}`；不会改写另一套账号。"
)

try:
    base_config = load_config(_CONFIG_PATH, ignore_runtime_profiles=True)
    groups = load_account_groups(account_groups_path, base_config=base_config, package_kind=package_kind)
except (ConfigError, AccountGroupError) as exc:
    st.error(f"账号组配置读取失败：{exc}")
    st.stop()

if is_test_package:
    st.info("测试包两组账号独立维护，首次配置为空，不迁移生产账号、密码或 API 密钥。")
    try:
        package_settings = load_test_package_settings(_PROJECT_ROOT / TEST_PACKAGE_SETTINGS_PATH)
    except AppPackageError as exc:
        st.error(f"测试包运行配置读取失败：{exc}")
        st.stop()
    with st.expander("测试 APP 包运行配置", expanded=True):
        with st.form("test_app_package_settings_form"):
            test_windows_path = st.text_input(
                "Windows 测试包可执行文件路径", value=package_settings["windows_exe_path"],
                key="test_package_windows_exe_path", placeholder="填写测试包 .exe 的完整路径（无默认值）",
                help="只用于测试包入口；留空时不能执行 Windows 测试包，不会回退生产包路径。请确认该路径实际安装的是测试构建。",
            ).strip()
            test_api_base = st.text_input(
                "测试包服务端请求地址", value=package_settings["api_base_url"],
                key="test_package_api_base_url", help="HTTP(S) 服务端根地址，不包含 /gin/v1；控制框架业务 API，不会重写 APP 包自身内置的后端地址。",
            ).strip()
            if test_api_base.lower().startswith("http://"):
                st.caption("当前测试 API 使用 HTTP（非 TLS），请仅在可信测试网络中使用；如服务支持 HTTPS，可直接修改地址。")
            test_mac_name = st.selectbox(
                "Mac 测试包名称", options=["DICloak", "DICloak2"],
                index=["DICloak", "DICloak2"].index(package_settings["macos_app_name"]),
                key="test_package_macos_app_name",
                help="从 /Applications 下所选 .app 的 Info.plist 解析真实可执行文件；请确认安装的是测试包。",
            )
            test_cdp_port = st.number_input(
                "测试包 CDP 端口", min_value=1, max_value=65535,
                value=int(package_settings["cdp_port"]), step=1, key="test_package_cdp_port",
                help="默认与生产包端口分开；连接前会核对监听进程的实际路径，不会仅凭端口连接。",
            )
            st.caption("CDP 沿用执行端已有私钥签发配置，凭证有效期规则保持 120 秒；这里不保存私钥或凭证。")
            package_saved = st.form_submit_button("保存测试包运行配置", type="primary")
        if package_saved:
            try:
                save_test_package_settings(_PROJECT_ROOT / TEST_PACKAGE_SETTINGS_PATH, {
                    "windows_exe_path": test_windows_path, "api_base_url": test_api_base,
                    "macos_app_name": test_mac_name, "cdp_port": int(test_cdp_port),
                })
                st.success("测试包运行配置已保存，执行页将读取新配置；生产包配置未改变。")
            except AppPackageError as exc:
                st.error(f"测试包运行配置保存失败：{exc}")

show_passwords = st.toggle(
    "显示密码、Open API token 和 Http API 密钥",
    value=False,
    help="只控制当前页面输入框显示方式，不会把敏感信息写入日志。",
    **({"key": "test_package_show_passwords"} if is_test_package else {}),
)
secret_input_type = "default" if show_passwords else "password"

with st.form("test_package_account_groups_form" if is_test_package else "account_groups_form"):
    edited_groups: dict[str, dict] = {}
    for index, slot in enumerate(ACCOUNT_GROUP_SLOTS, start=1):
        slot_key = f"test_package_{slot}" if is_test_package else slot
        group = groups[slot]
        automation_account = group["automation_account"]
        case_external_member = group["case_external_member"]
        internal_member = group["internal_member"]
        with st.expander(group["name"] or f"自动化账号组 {index}", expanded=True):
            group_name = st.text_input(
                "组名称",
                value=group["name"],
                key=f"{slot_key}_name",
                placeholder=f"自动化账号组 {index}",
            ).strip()

            st.markdown("**自动化主账号**")
            ext_account_col, ext_password_col = st.columns(2)
            with ext_account_col:
                external_username = st.text_input(
                    "主账号",
                    value=automation_account["username"],
                    key=f"{slot_key}_external_username",
                    placeholder="邮箱或登录账号",
                ).strip()
            with ext_password_col:
                external_password = st.text_input(
                    "主账号密码",
                    value=automation_account["password"],
                    type=secret_input_type,
                    key=f"{slot_key}_external_password",
                )

            ext_team_col, ext_id_col = st.columns(2)
            with ext_team_col:
                team_name = st.text_input(
                    "自动化团队名称",
                    value=automation_account["team_name"],
                    key=f"{slot_key}_team_name",
                    help="登录后框架会自动切换并校验当前团队。",
                ).strip()
            with ext_id_col:
                external_member_id = st.text_input(
                    "主账号成员 ID",
                    value=automation_account["member_id"],
                    key=f"{slot_key}_external_member_id",
                    help="仅供自动化主账号停用和到期停用接口用例使用。",
                ).strip()

            st.markdown("**用例所需外部成员**")
            case_name_col, case_email_col = st.columns(2)
            with case_name_col:
                case_external_name = st.text_input(
                    "外部成员名称",
                    value=case_external_member["name"],
                    key=f"{slot_key}_case_external_name",
                    help="供上级经理、编辑成员、导出成员等普通 UI 用例使用。",
                ).strip()
            with case_email_col:
                case_external_email = st.text_input(
                    "外部成员邮箱",
                    value=case_external_member["email"],
                    key=f"{slot_key}_case_external_email",
                    help="供登录账号/邮箱筛选用例使用。",
                ).strip()

            st.markdown("**内部成员账号**")
            int_account_col, int_password_col, int_id_col = st.columns(3)
            with int_account_col:
                internal_username = st.text_input(
                    "内部账号",
                    value=internal_member["username"],
                    key=f"{slot_key}_internal_username",
                ).strip()
            with int_password_col:
                internal_password = st.text_input(
                    "内部账号密码",
                    value=internal_member["password"],
                    type=secret_input_type,
                    key=f"{slot_key}_internal_password",
                )
            with int_id_col:
                internal_member_id = st.text_input(
                    "内部成员 ID",
                    value=internal_member["member_id"],
                    key=f"{slot_key}_internal_member_id",
                ).strip()

            member_api_token = st.text_input(
                "成员 Open API token",
                value=group["member_api_token"],
                type=secret_input_type,
                key=f"{slot_key}_member_api_token",
                help="停用和到期用例调用成员编辑 Open API。不同团队必须使用对应团队的 token。",
            ).strip()

            http_api_key = st.text_input(
                "Http API 密钥",
                value=group["http_api_key"],
                type=secret_input_type,
                key=f"{slot_key}_http_api_key",
                help="供环境列表 Http API 使用；不同账号组请配置各自团队的密钥。",
            ).strip()

            edited_groups[slot] = {
                "name": group_name,
                "automation_account": {
                    "username": external_username,
                    "password": external_password,
                    "team_name": team_name,
                    "member_id": external_member_id,
                },
                "case_external_member": {
                    "name": case_external_name,
                    "email": case_external_email,
                },
                "internal_member": {
                    "username": internal_username,
                    "password": internal_password,
                    "member_id": internal_member_id,
                },
                "member_api_token": member_api_token,
                "http_api_key": http_api_key,
            }

    saved = st.form_submit_button("保存两个账号组", type="primary", use_container_width=True)

if saved:
    try:
        save_account_groups(account_groups_path, edited_groups, package_kind=package_kind)
        st.success(f"{package_label}的两个账号组已保存。执行用例页面会立即读取最新配置。")
    except AccountGroupError as exc:
        st.error(f"账号组保存失败：{exc}")
