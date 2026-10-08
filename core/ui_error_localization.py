from __future__ import annotations

import re
from dataclasses import dataclass


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
PLATFORM_PREFIX_RE = re.compile(r"^\[[^\]]+\]\s+")
EXCEPTION_LINE_RE = re.compile(
    r"(?P<class>(?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*(?:Error|Exception)):\s*(?P<message>.*)"
)
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
KEY_VALUE_RE = re.compile(r"\b(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^,\n]+)")

DOMAIN_TERMS = (
    ("kernel executable path", "内核可执行文件路径"),
    ("expected cache dir", "预期缓存目录"),
    ("cache subdir", "缓存子目录"),
    ("environment group", "环境分组"),
    ("environment name", "环境名称"),
    ("environment serial", "环境序号"),
    ("environment", "环境"),
    ("disable member", "停用成员"),
    ("disuse member", "停用成员"),
    ("enable member", "启用成员"),
    ("automation account re-login", "自动化账号重新登录"),
    ("first environment serial", "第一条环境序号"),
    ("member login account", "成员登录账号"),
    ("member group", "成员分组"),
    ("member email", "成员邮箱"),
    ("member name", "成员名称"),
    ("member id", "成员 ID"),
    ("member status", "成员状态"),
    ("member type tooltip", "成员类型提示"),
    ("internal member", "内部成员"),
    ("external member", "外部成员"),
    ("member", "成员"),
    ("extension switch", "扩展开关"),
    ("extension group", "扩展分组"),
    ("extension status", "扩展状态"),
    ("extension", "扩展"),
    ("proxy custom account", "自定义代理账号"),
    ("proxy custom password", "自定义代理密码"),
    ("proxy", "代理"),
    ("global settings checkbox", "全局设置复选框"),
    ("global data sync", "全局数据同步"),
    ("local cache", "本地缓存"),
    ("download record kernel cleanup", "下载记录内核清理"),
    ("force logout popup text", "强制退出登录弹窗文案"),
    ("http status", "HTTP 状态码"),
    ("api msg", "API 消息"),
    ("response payload", "响应数据"),
    ("response", "响应"),
    ("export file", "导出文件"),
    ("file", "文件"),
    ("directory", "目录"),
    ("dialog", "弹窗"),
    ("button", "按钮"),
    ("checkbox", "复选框"),
    ("switch", "开关"),
    ("filter", "筛选"),
    ("list", "列表"),
    ("row", "数据行"),
    ("remark", "备注"),
    ("name", "名称"),
    ("status", "状态"),
    ("result", "结果"),
)


@dataclass(frozen=True)
class UiIssueSummary:
    error_type: str
    exception_class: str
    chinese_reason: str
    original_error: str

    @property
    def compact_text(self) -> str:
        exception = f"（{self.exception_class}）" if self.exception_class else ""
        return f"{self.error_type}{exception}：{self.chinese_reason}"

    @property
    def detail_text(self) -> str:
        lines = [f"错误类型：{self.error_type}"]
        if self.exception_class:
            lines.append(f"异常类：{self.exception_class}")
        lines.append(f"中文说明：{self.chinese_reason}")
        if self.original_error:
            lines.append(f"原始错误：{self.original_error}")
        return "\n".join(lines)


def summarize_ui_issue(text: str, status: str) -> UiIssueSummary:
    clean_text = ANSI_ESCAPE_RE.sub("", str(text or "")).strip()
    exception_class, message, original_error = _extract_exception(clean_text)
    error_type = _localized_error_type(exception_class, message, status)
    chinese_reason = _localized_reason(message, error_type, status)
    return UiIssueSummary(
        error_type=error_type,
        exception_class=exception_class,
        chinese_reason=chinese_reason,
        original_error=original_error,
    )


def is_exception_summary_line(line: str) -> bool:
    clean_line = PLATFORM_PREFIX_RE.sub("", ANSI_ESCAPE_RE.sub("", str(line or ""))).strip()
    return bool(EXCEPTION_LINE_RE.search(clean_line))


def _extract_exception(text: str) -> tuple[str, str, str]:
    lines = [PLATFORM_PREFIX_RE.sub("", line).strip() for line in text.splitlines() if line.strip()]
    for line_index in range(len(lines) - 1, -1, -1):
        line = lines[line_index]
        match = EXCEPTION_LINE_RE.search(line)
        if match:
            exception_class = match.group("class").split(".")[-1]
            message = match.group("message").strip()
            if not message:
                continuation = [item for item in lines[line_index + 1:] if item]
                message = "\n".join(continuation).strip()
            original = f"{exception_class}: {message}".strip()
            return exception_class, message, _clip(original, 4000)
    fallback = ""
    for line in reversed(lines):
        if not line.startswith(("File ", "Traceback ", "During handling", "The above exception")):
            fallback = line
            break
    return "", fallback, _clip(fallback, 1200)


def _localized_error_type(exception_class: str, message: str, status: str) -> str:
    combined = f"{exception_class} {message}".lower()
    element_words = (
        "element", "selector", "locator", "button", "input", "dialog", "drawer",
        "popover", "tab", "option", "bounding box", "元素", "按钮", "输入框", "弹窗",
    )
    missing_words = ("not found", "missing", "no such element", "未找到", "不存在")
    timeout_words = ("timeout", "timed out", "did not appear", "did not become", "等待超时")

    if status == "failed" or exception_class == "AssertionError":
        return "断言失败"
    if any(word in combined for word in element_words) and any(word in combined for word in missing_words):
        return "元素未找到"
    if any(word in combined for word in timeout_words):
        return "元素等待超时" if any(word in combined for word in element_words) else "等待超时"
    if exception_class in {"NoSuchElementException", "ElementNotFoundError"}:
        return "元素未找到"
    if exception_class in {"FileNotFoundError"}:
        return "文件未找到"
    if exception_class in {"PermissionError"}:
        return "权限不足"
    if exception_class in {"ConnectionError", "ConnectionRefusedError", "ConnectionResetError", "WebSocketException"}:
        return "连接失败"
    if "connection" in combined or "websocket" in combined or "cdp" in combined:
        return "连接异常"
    if exception_class in {"JSONDecodeError"} or "json" in combined and "decode" in combined:
        return "响应数据解析失败"
    if exception_class == "KeyError":
        return "缺少数据字段"
    if exception_class == "ValueError":
        return "参数或数据值错误"
    if exception_class == "TypeError":
        return "数据类型错误"
    if exception_class == "RuntimeError":
        return "运行时错误"
    if exception_class in {"OSError", "ProcessLookupError", "ChildProcessError"}:
        return "系统或进程错误"
    return "执行异常"


def _localized_reason(message: str, error_type: str, status: str) -> str:
    clean_message = "\n".join(
        " ".join(line.split())
        for line in str(message or "").splitlines()
        if line.strip()
    ).strip()
    lower = clean_message.lower()

    if _mostly_chinese(clean_message.partition(":")[0]):
        return _clip(clean_message, 500)
    if "chrome web store install was not blocked or prevented" in lower:
        base = "预期扩展安装应被阻止，但页面没有出现可确认的阻止结果。"
        return _with_key_facts(base, clean_message)
    match = re.search(r"expected\s+(.+?),\s*got\s+(.+)$", clean_message, re.IGNORECASE)
    if match:
        return _clip(f"期望值为 {match.group(1)}，实际值为 {match.group(2)}。", 500)
    if "value mismatch" in lower:
        return _with_key_facts("实际值与期望值不一致。", clean_message)
    if status == "failed" or error_type == "断言失败":
        translated_assertion = _translate_assertion_message(clean_message)
        if translated_assertion:
            return _clip(translated_assertion, 1000)
    if "still exists" in lower:
        return _with_key_facts("预期目标应已消失，但实际仍然存在。", clean_message)
    if "was not blocked" in lower or "not blocked or prevented" in lower:
        return _with_key_facts("预期操作应被阻止，但实际没有检测到阻止结果。", clean_message)
    if "did not close" in lower:
        return _with_key_facts("目标弹窗或页面未在规定时间内关闭。", clean_message)
    if "did not disappear" in lower:
        return _with_key_facts("目标内容未在规定时间内消失。", clean_message)
    if "did not become ready" in lower:
        return _with_key_facts("目标页面或业务状态未在规定时间内就绪。", clean_message)
    if "did not appear" in lower:
        return _with_key_facts("等待的页面内容没有在规定时间内出现。", clean_message)
    if "did not start" in lower:
        return _with_key_facts("操作没有在规定时间内开始。", clean_message)
    if "script did not return a visible enabled element" in lower:
        return _with_key_facts("等待元素出现并变为可见、可操作状态超时。", clean_message)
    if "selector is not clickable" in lower or "element is not clickable" in lower:
        return _with_key_facts("目标元素当前不可点击。", clean_message)
    if "selector is not enabled" in lower or "element is not enabled" in lower:
        return _with_key_facts("目标元素当前不可操作。", clean_message)
    if "not found" in lower or "missing" in lower or "no such element" in lower:
        return _with_key_facts("未找到预期的目标元素或业务数据。", clean_message)
    if "timeout" in lower or "timed out" in lower:
        return _with_key_facts("等待页面或业务状态完成超时。", clean_message)

    defaults = {
        "断言失败": "实际结果没有满足用例的预期条件。",
        "元素未找到": "未找到目标元素，请检查页面结构、当前页面状态或定位条件。",
        "元素等待超时": "目标元素没有在规定时间内出现或达到可操作状态。",
        "等待超时": "页面、接口或业务状态没有在规定时间内完成。",
        "文件未找到": "未找到用例需要的文件或目录。",
        "权限不足": "当前进程或账号没有完成该操作所需的权限。",
        "连接失败": "无法建立或维持所需的网络、浏览器或远端连接。",
        "连接异常": "浏览器、CDP、WebSocket 或远端连接发生异常。",
        "响应数据解析失败": "接口或页面返回的数据无法按预期格式解析。",
        "缺少数据字段": "返回数据或配置中缺少用例需要的字段。",
        "参数或数据值错误": "传入参数或读取到的数据值不符合要求。",
        "数据类型错误": "数据类型与代码预期不一致。",
        "运行时错误": "用例执行过程中发生运行时异常。",
        "系统或进程错误": "操作系统或子进程执行失败。",
        "执行异常": "用例执行过程中发生未分类异常。",
    }
    base = defaults.get(error_type, defaults["执行异常"])
    if status == "failed":
        return "实际结果没有满足用例的预期条件；日志中未捕获到具体断言消息。"
    return base


def _with_key_facts(base: str, message: str) -> str:
    facts: list[str] = []
    labels = {
        "expected": "期望",
        "expected_error": "期望错误",
        "actual": "实际",
        "target_url": "目标地址",
        "status_before": "操作前状态",
        "status_after": "操作后状态",
        "timeout_seconds": "超时秒数",
        "selector": "元素定位",
        "name": "名称",
        "pid": "进程 ID",
        "executable": "可执行文件",
        "expected_parent": "预期父目录",
        "remaining": "剩余内容",
        "field": "字段",
        "type": "类型",
        "code": "状态码",
    }
    values = {"true": "是", "false": "否", "installable": "可安装", "enabled": "已启用"}
    for match in KEY_VALUE_RE.finditer(message):
        key = match.group("key")
        if key not in labels:
            continue
        value = match.group("value").strip()
        localized_value = values.get(value.lower(), value)
        facts.append(f"{labels[key]}={_clip(localized_value, 90)}")
        if len(facts) >= 5:
            break
    if not facts:
        return base
    return _clip(f"{base} 关键信息：{'；'.join(facts)}。", 500)


def _clip(value: str, limit: int) -> str:
    clean_value = str(value or "").strip()
    if len(clean_value) <= limit:
        return clean_value
    return f"{clean_value[: max(0, limit - 1)]}…"


def _translate_assertion_message(message: str) -> str:
    clean_message = str(message or "").strip()
    if not clean_message:
        return "实际结果没有满足用例的预期条件。"
    clauses = [item.strip() for item in re.split(r"[;\n]+", clean_message) if item.strip()]
    translated = [_translate_assertion_clause(clause) for clause in clauses]
    translated = [item for item in translated if item]
    if not translated:
        return "实际结果没有满足用例的预期条件，具体业务信息见英文原文。"
    return "；".join(translated)


def _translate_assertion_clause(clause: str) -> str:
    clean_clause = " ".join(str(clause or "").split()).strip()
    lower = clean_clause.lower()
    if not clean_clause:
        return ""
    if _mostly_chinese(clean_clause):
        return clean_clause
    if lower.startswith("kernel executable path is not under expected cache dir"):
        return _with_key_facts("内核可执行文件路径不在预期缓存目录下。", clean_clause)
    if lower.startswith("refuse to clear unexpected cache subdir"):
        return _with_trailing_value("为避免误删，拒绝清理非预期的缓存子目录。", clean_clause)

    patterns = (
        (r"^(?P<object>.+?) was not created(?: in (?P<place>.+))?$", "{object}未创建成功{place}。"),
        (r"^(?P<object>.+?) was not deleted(?: from (?P<place>.+))?$", "{object}未删除成功{place}。"),
        (r"^(?P<object>.+?) was not found(?: in (?P<place>.+))?$", "未找到{object}{place}。"),
        (r"^(?P<object>.+?) was not visible(?: after (?P<condition>.+))?$", "{object}不可见{condition}。"),
        (r"^(?P<object>.+?) was not updated(?: in (?P<place>.+))?$", "{object}未更新成功{place}。"),
        (r"^(?P<object>.+?) was not restored(?: in (?P<place>.+))?$", "{object}未还原成功{place}。"),
        (r"^(?P<object>.+?) was not blocked(?: or prevented)?(?: (?P<condition>.+))?$", "{object}未按预期被阻止{condition}。"),
        (r"^(?P<object>.+?) was not generated$", "{object}未生成。"),
        (r"^(?P<object>.+?) was not saved as (?P<state>.+)$", "{object}未保存为{state}。"),
        (r"^(?P<object>.+?) did not match(?: in (?P<place>.+))?$", "{object}与预期不一致{place}。"),
        (r"^(?P<object>.+?) did not appear(?: (?P<condition>.+))?$", "{object}未出现{condition}。"),
        (r"^(?P<object>.+?) did not close(?: (?P<condition>.+))?$", "{object}未关闭{condition}。"),
        (r"^(?P<object>.+?) did not disappear(?: (?P<condition>.+))?$", "{object}未消失{condition}。"),
        (r"^(?P<object>.+?) did not become ready(?: (?P<condition>.+))?$", "{object}未就绪{condition}。"),
        (r"^(?P<object>.+?) did not start(?: (?P<condition>.+))?$", "{object}未开始{condition}。"),
        (r"^(?P<object>.+?) still exists$", "{object}仍然存在。"),
        (r"^(?P<object>.+?) returned no rows$", "{object}没有返回任何数据行。"),
        (r"^(?P<object>.+?) is empty$", "{object}为空。"),
        (r"^(?P<object>.+?) is not valid json$", "{object}不是有效的 JSON 数据。"),
        (r"^(?P<object>.+?) must be an object$", "{object}必须是对象。"),
        (r"^(?P<object>.+?) must be an array$", "{object}必须是数组。"),
        (r"^(?P<object>.+?) has no id$", "{object}缺少 ID。"),
        (r"^(?P<object>.+?) contains duplicate (?P<field>.+)$", "{object}包含重复的{field}。"),
        (r"^(?P<object>.+?) does not exist$", "{object}不存在。"),
        (r"^(?P<object>.+?) login failed$", "{object}登录失败。"),
        (r"^(?P<object>.+?) should login after enabled$", "{object}启用后应能够登录。"),
        (r"^(?P<object>.+?) mismatch$", "{object}与预期不一致。"),
        (r"^unexpected (?P<object>.+)$", "检测到非预期的{object}。"),
    )
    headline, separator, trailing = clean_clause.partition(":")
    for pattern, template in patterns:
        match = re.match(pattern, headline.strip(), re.IGNORECASE)
        if not match:
            continue
        values = {key: _translate_domain_terms(value or "") for key, value in match.groupdict().items()}
        for key in ("place", "condition"):
            if values.get(key):
                values[key] = f"（{values[key]}）"
        translated = template.format(**values)
        if separator and trailing.strip():
            translated = f"{translated} 相关值：{trailing.strip()}。"
        return translated

    translated_terms = _translate_domain_terms(headline)
    if translated_terms != headline:
        suffix = f" 相关值：{trailing.strip()}。" if separator and trailing.strip() else ""
        return f"{translated_terms}未满足预期。{suffix}".strip()
    return "该断言的实际结果不符合预期，具体业务信息见英文原文。"


def _translate_domain_terms(value: str) -> str:
    translated = str(value or "").strip()
    for english, chinese in DOMAIN_TERMS:
        translated = re.sub(rf"\b{re.escape(english)}\b", chinese, translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bafter clearing\b", "清空后", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bbefore save\b", "保存前", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bafter enabled\b", "启用后", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\benabled\b", "已启用", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bdisabled\b", "已禁用", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bchecked\b", "已勾选", translated, flags=re.IGNORECASE)
    return translated.strip()


def _with_trailing_value(base: str, message: str) -> str:
    _headline, separator, trailing = str(message or "").partition(":")
    if separator and trailing.strip():
        return f"{base} 相关值：{trailing.strip()}。"
    return base


def _mostly_chinese(value: str) -> bool:
    chinese_count = len(CHINESE_RE.findall(str(value or "")))
    latin_count = len(re.findall(r"[A-Za-z]", str(value or "")))
    return chinese_count > 0 and chinese_count >= max(2, latin_count // 3)
