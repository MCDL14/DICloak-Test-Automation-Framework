from __future__ import annotations

import logging

from pages.login_page import LoginPage
from pages.member_page import MemberPage
from tests.p0.member_management.member_open_api import MemberEditApiClient


LOGGER = logging.getLogger("dicloak_automation")


def restore_automation_member_api_state(api_client: MemberEditApiClient) -> list[str]:
    """Best-effort API cleanup for the configured automation account member."""

    errors: list[str] = []
    for params in ({"status": "ENABLED"}, {"disuse_enable": "false"}):
        try:
            payload = api_client.edit_member(**params)
            if payload["status_code"] != 200 or payload["json"].get("msg") != "success":
                errors.append(f"params={params}, payload={payload}")
        except Exception as exc:
            errors.append(f"params={params}, error={exc}")
    return errors


def recover_automation_account_after_api_case(
    api_client: MemberEditApiClient,
    login_page: LoginPage,
    member_page: MemberPage,
) -> list[str]:
    """Restore automation account state, then return to the automation team member list."""

    errors = restore_automation_member_api_state(api_client)
    try:
        login_page.ensure_logged_in_as_config_account()
        login_page.ensure_current_team()
        member_page.open_list()
    except Exception as exc:
        errors.append(f"ui_recovery_error={exc}")
    if errors:
        LOGGER.warning("Member API case fallback recovery completed with issues: %s", "; ".join(errors))
    return errors
