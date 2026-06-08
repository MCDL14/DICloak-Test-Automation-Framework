from __future__ import annotations

from core.assertions import assert_true
from pages.login_page import LoginPage
from pages.member_page import MemberPage
from tests.p0.member_management.member_open_api import (
    DEFAULT_DISABLED_LOGIN_MESSAGE,
    DEFAULT_INTERNAL_MEMBER_ID,
    DEFAULT_INTERNAL_PASSWORD,
    DEFAULT_INTERNAL_USERNAME,
    disabled_login_message,
    internal_member_id,
    internal_member_password,
    internal_member_username,
)


INTERNAL_MEMBER_USERNAME = DEFAULT_INTERNAL_USERNAME
INTERNAL_MEMBER_PASSWORD = DEFAULT_INTERNAL_PASSWORD
INTERNAL_MEMBER_ID = DEFAULT_INTERNAL_MEMBER_ID
DISABLED_LOGIN_MESSAGE = DEFAULT_DISABLED_LOGIN_MESSAGE


def login_internal_member(login_page: LoginPage) -> None:
    username = internal_member_username(login_page.config)
    password = internal_member_password(login_page.config)
    if login_page.is_logged_in() and login_page.current_account() == username:
        return

    if login_page.is_logged_in():
        login_page.logout_to_login_page()
    login_page.login(username, password)
    login_page.wait_logged_in(timeout_seconds=20)
    current_account = login_page.current_account()
    assert_true(
        bool(current_account) and current_account == username,
        f"internal member login account mismatch: expected={username}, actual={current_account}",
    )


def assert_disabled_member_cannot_login(login_page: LoginPage) -> None:
    login_page.click_login_button()
    expected_message = disabled_login_message(login_page.config)
    message = login_page.wait_login_failed_message(expected_message)
    assert_true(expected_message in message, f"disabled login message mismatch: {message}")
    assert_true(not login_page.is_logged_in(), "disabled internal member should not login successfully")


def configured_internal_member_id(config: dict) -> str:
    return internal_member_id(config)


def restore_automation_account(login_page: LoginPage, member_page: MemberPage) -> None:
    try:
        login_page.ensure_logged_in_as_config_account()
        login_page.ensure_current_team()
        member_page.open_list()
    except Exception:
        pass
