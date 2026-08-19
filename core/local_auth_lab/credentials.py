from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.assertions import assert_equal, assert_true


LOCAL_AUTH_LAB_LOGIN_DATA_KEY = "local_auth_lab_login"
LOCAL_AUTH_LAB_LOGIN_PASSWORD = "M12345678"
LOCAL_AUTH_LAB_EXPECTED_ACCOUNTS = {
    "cookie": "MCDL004",
    "localstorage": "MCDL005",
    "indexeddb": "MCDL006",
}


def local_auth_lab_login_credentials(config: dict[str, Any], site_id: str) -> tuple[str, str]:
    test_data = config.get("test_data", {})
    assert_true(isinstance(test_data, dict), "测试数据配置格式错误: test_data 不是字典")
    shared_credentials = test_data.get(LOCAL_AUTH_LAB_LOGIN_DATA_KEY)
    assert_true(
        isinstance(shared_credentials, dict),
        f"test_data.{LOCAL_AUTH_LAB_LOGIN_DATA_KEY} 必须是映射配置",
    )

    expected_account = LOCAL_AUTH_LAB_EXPECTED_ACCOUNTS.get(site_id)
    assert_true(
        expected_account is not None,
        f"Local Auth Lab 不支持的登录站点配置: site_id={site_id}",
    )

    credentials = shared_credentials.get(site_id)
    assert_true(
        isinstance(credentials, dict),
        f"test_data.{LOCAL_AUTH_LAB_LOGIN_DATA_KEY}.{site_id} 必须是映射配置",
    )
    username = str(credentials.get("username", "")).strip()
    password = str(credentials.get("password", ""))
    assert_equal(
        username,
        expected_account,
        f"Local Auth Lab 共享登录配置 {site_id} 账号配置错误",
    )
    assert_equal(
        password,
        LOCAL_AUTH_LAB_LOGIN_PASSWORD,
        f"Local Auth Lab 共享登录配置 {site_id} 密码配置错误",
    )
    return username, password


def local_auth_lab_login_credentials_by_site(
    config: dict[str, Any],
    site_ids: Iterable[str] = LOCAL_AUTH_LAB_EXPECTED_ACCOUNTS,
) -> dict[str, tuple[str, str]]:
    return {
        site_id: local_auth_lab_login_credentials(config, site_id)
        for site_id in site_ids
    }
