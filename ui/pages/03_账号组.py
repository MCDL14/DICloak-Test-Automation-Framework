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


_ACCOUNT_GROUPS_PATH = _PROJECT_ROOT / "config" / "account_groups.yaml"
_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"


st.set_page_config(page_title="自动化账号组", page_icon="🔐", layout="wide")
st.title("自动化账号组")
st.caption(
    "两组账号分别供 Windows 本机和 macOS 远程执行选择。"
    "配置仅保存在本机 `config/account_groups.yaml`，该文件已忽略提交。"
)

try:
    base_config = load_config(_CONFIG_PATH)
    groups = load_account_groups(_ACCOUNT_GROUPS_PATH, base_config=base_config)
except (ConfigError, AccountGroupError) as exc:
    st.error(f"账号组配置读取失败：{exc}")
    st.stop()

show_passwords = st.toggle(
    "显示密码和 Open API token",
    value=False,
    help="只控制当前页面输入框显示方式，不会把敏感信息写入日志。",
)
secret_input_type = "default" if show_passwords else "password"

with st.form("account_groups_form"):
    edited_groups: dict[str, dict] = {}
    for index, slot in enumerate(ACCOUNT_GROUP_SLOTS, start=1):
        group = groups[slot]
        automation_account = group["automation_account"]
        case_external_member = group["case_external_member"]
        internal_member = group["internal_member"]
        with st.expander(group["name"] or f"自动化账号组 {index}", expanded=True):
            group_name = st.text_input(
                "组名称",
                value=group["name"],
                key=f"{slot}_name",
                placeholder=f"自动化账号组 {index}",
            ).strip()

            st.markdown("**自动化主账号**")
            ext_account_col, ext_password_col = st.columns(2)
            with ext_account_col:
                external_username = st.text_input(
                    "主账号",
                    value=automation_account["username"],
                    key=f"{slot}_external_username",
                    placeholder="邮箱或登录账号",
                ).strip()
            with ext_password_col:
                external_password = st.text_input(
                    "主账号密码",
                    value=automation_account["password"],
                    type=secret_input_type,
                    key=f"{slot}_external_password",
                )

            ext_team_col, ext_id_col = st.columns(2)
            with ext_team_col:
                team_name = st.text_input(
                    "自动化团队名称",
                    value=automation_account["team_name"],
                    key=f"{slot}_team_name",
                    help="登录后框架会自动切换并校验当前团队。",
                ).strip()
            with ext_id_col:
                external_member_id = st.text_input(
                    "主账号成员 ID",
                    value=automation_account["member_id"],
                    key=f"{slot}_external_member_id",
                    help="仅供自动化主账号停用和到期停用接口用例使用。",
                ).strip()

            st.markdown("**用例所需外部成员**")
            case_name_col, case_email_col = st.columns(2)
            with case_name_col:
                case_external_name = st.text_input(
                    "外部成员名称",
                    value=case_external_member["name"],
                    key=f"{slot}_case_external_name",
                    help="供上级经理、编辑成员、导出成员等普通 UI 用例使用。",
                ).strip()
            with case_email_col:
                case_external_email = st.text_input(
                    "外部成员邮箱",
                    value=case_external_member["email"],
                    key=f"{slot}_case_external_email",
                    help="供登录账号/邮箱筛选用例使用。",
                ).strip()

            st.markdown("**内部成员账号**")
            int_account_col, int_password_col, int_id_col = st.columns(3)
            with int_account_col:
                internal_username = st.text_input(
                    "内部账号",
                    value=internal_member["username"],
                    key=f"{slot}_internal_username",
                ).strip()
            with int_password_col:
                internal_password = st.text_input(
                    "内部账号密码",
                    value=internal_member["password"],
                    type=secret_input_type,
                    key=f"{slot}_internal_password",
                )
            with int_id_col:
                internal_member_id = st.text_input(
                    "内部成员 ID",
                    value=internal_member["member_id"],
                    key=f"{slot}_internal_member_id",
                ).strip()

            member_api_token = st.text_input(
                "成员 Open API token",
                value=group["member_api_token"],
                type=secret_input_type,
                key=f"{slot}_member_api_token",
                help="停用和到期用例调用成员编辑 Open API。不同团队必须使用对应团队的 token。",
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
            }

    saved = st.form_submit_button("保存两个账号组", type="primary", use_container_width=True)

if saved:
    try:
        save_account_groups(_ACCOUNT_GROUPS_PATH, edited_groups)
        st.success("账号组已保存。执行用例页面会立即读取最新配置。")
    except AccountGroupError as exc:
        st.error(f"账号组保存失败：{exc}")
