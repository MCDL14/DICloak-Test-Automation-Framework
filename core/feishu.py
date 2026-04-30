from __future__ import annotations

import logging
from typing import Any

from core.result import RunResult


class FeishuNotifier:
    def __init__(self, config: dict[str, Any], logger: logging.Logger):
        self.config = config.get("feishu", {})
        self.logger = logger

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True)) and bool(self.webhook_url)

    @property
    def webhook_url(self) -> str:
        return str(self.config.get("webhook_url", "")).strip()

    def send_text(self, text: str) -> bool:
        if not self.enabled:
            self.logger.info("Feishu webhook is empty or disabled, skip notification")
            return False

        import requests

        payload = {"msg_type": "text", "content": {"text": self._with_mention(text)}}
        headers = {"Content-Type": "application/json; charset=utf-8"}
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=headers,
                timeout=int(self.config.get("timeout", 10)),
            )
            if response.status_code != 200:
                self.logger.error("Feishu notification failed, HTTP %s: %s", response.status_code, response.text)
                return False
            body = response.json()
            if body.get("code") != 0:
                self.logger.error("Feishu notification failed, response: %s", body)
                return False
            return True
        except requests.RequestException as exc:
            self.logger.error("Feishu notification request error: %s", exc)
            return False
        except ValueError as exc:
            self.logger.error("Feishu notification response is not JSON: %s", exc)
            return False

    def send_test(self) -> bool:
        return self.send_text("Dicloak 自动化飞书测试通知")

    def send_failure(self, title: str, detail: str) -> bool:
        if not self.config.get("notify_on_failure", True):
            return False
        return self.send_text(f"{title}\n{detail}")

    def send_summary(self, result: RunResult) -> bool:
        if result.success and not self.config.get("notify_on_success", False):
            return False
        status = "通过" if result.success else "失败"
        text = (
            f"Dicloak 自动化执行{status}\n"
            f"总数：{result.total}\n"
            f"通过：{result.passed}\n"
            f"失败：{result.failed}\n"
            f"异常：{result.errors}\n"
            f"跳过：{result.skipped}\n"
            f"通过率：{result.pass_rate}%"
        )
        if result.failures:
            text += "\n失败摘要：\n" + result.failed_summary()
        return self.send_text(text)

    def send_breaker(self, module_name: str, reason: str) -> bool:
        return self.send_failure("Dicloak 自动化模块熔断", f"模块：{module_name}\n原因：{reason}")

    def _with_mention(self, text: str) -> str:
        open_id = str(self.config.get("at_open_id", "")).strip()
        name = str(self.config.get("at_name", "")).strip()
        if not open_id:
            return text
        display_name = name or open_id
        return f"{text}\n<at user_id=\"{open_id}\">{display_name}</at>"
