from __future__ import annotations

from typing import Any

from core.local_auth_lab.settings import LocalAuthLabSettings
from pages.base_page import BasePage


class LocalAuthLabPage(BasePage):
    locator_file = "local_auth_lab_locators.yaml"

    def __init__(self, cdp_driver, config: dict[str, Any]):
        super().__init__(cdp_driver, config=config)
        self.settings = LocalAuthLabSettings.from_config(config)

    def open(self, site_id: str) -> None:
        if site_id not in {"cookie", "localstorage", "indexeddb"}:
            raise ValueError(f"unsupported local auth lab site: {site_id}")
        self.cdp.navigate(self.settings.base_urls[site_id])
        self.wait_visible("auth_status")
        status_selector = self.locator("auth_status")
        self.cdp.wait_until(
            "['未登录', '已登录', '服务不可用'].includes("
            f"(document.querySelector({status_selector!r})?.textContent || '').trim())",
            message="local auth lab page did not finish its initial session check",
        )

    def show_register(self) -> None:
        self.click("show_register")
        self.wait_visible("register_form")

    def register(self, username: str, password: str) -> None:
        self.show_register()
        self.fill("register_username", username)
        self.fill("register_password", password)
        self.fill("confirm_password", password)
        self.click("register_button")
        message_selector = self.locator("message")
        self.cdp.wait_until(
            f"(document.querySelector({message_selector!r})?.textContent || '').includes('注册成功')",
            message="registration did not complete successfully",
        )
        self.wait_for_status("未登录")

    def login(self, username: str, password: str, run_id: str = "") -> None:
        self.fill("username", username)
        self.fill("password", password)
        if run_id:
            self.fill("run_id_input", run_id)
        self.click("login_button")
        self.wait_for_status("已登录")

    def logout(self) -> None:
        self.click("logout_button")
        self.wait_for_status("未登录")

    def wait_for_status(self, expected: str, timeout_seconds: float | None = None) -> None:
        selector = self.locator("auth_status")
        self.cdp.wait_until(
            f"(document.querySelector({selector!r})?.textContent || '').trim() === {expected!r}",
            timeout_seconds,
            f"auth status did not become {expected}",
        )

    @property
    def auth_status(self) -> str:
        return self.text("auth_status")

    @property
    def current_account(self) -> str:
        return self.text("current_account")

    @property
    def token_fingerprint(self) -> str:
        return self.text("token_fingerprint")
