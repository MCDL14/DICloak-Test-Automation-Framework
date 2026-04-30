from __future__ import annotations

import sys
import unittest
from collections.abc import Callable
from typing import TypeVar


SUPPORTED_CASE_MODULES = (
    "环境管理",
    "代理管理",
    "扩展管理",
    "环境分组管理",
    "成员管理",
    "全局设置",
)

_CASE_MODULE_ALIASES = {
    "env": "环境管理",
    "environment": "环境管理",
    "environment_management": "环境管理",
    "环境": "环境管理",
    "环境管理": "环境管理",
    "proxy": "代理管理",
    "proxy_management": "代理管理",
    "代理": "代理管理",
    "代理管理": "代理管理",
    "extension": "扩展管理",
    "extension_management": "扩展管理",
    "扩展": "扩展管理",
    "扩展管理": "扩展管理",
    "environment_group": "环境分组管理",
    "environment_group_management": "环境分组管理",
    "group": "环境分组管理",
    "环境分组": "环境分组管理",
    "环境分组管理": "环境分组管理",
    "member": "成员管理",
    "member_management": "成员管理",
    "成员": "成员管理",
    "成员管理": "成员管理",
    "global": "全局设置",
    "global_setting": "全局设置",
    "global_settings": "全局设置",
    "setting": "全局设置",
    "settings": "全局设置",
    "全局": "全局设置",
    "全局设置": "全局设置",
}

T = TypeVar("T")


def normalize_case_module(value: str | None) -> str:
    if not value:
        return ""
    key = str(value).strip()
    if not key:
        return ""
    normalized_key = key.lower().replace("-", "_").replace(" ", "_")
    return _CASE_MODULE_ALIASES.get(normalized_key) or _CASE_MODULE_ALIASES.get(key) or ""


def supported_case_modules_text() -> str:
    return "、".join(SUPPORTED_CASE_MODULES)


def case_module(module_name: str) -> Callable[[T], T]:
    canonical_name = normalize_case_module(module_name)
    if not canonical_name:
        raise ValueError(f"unsupported case module: {module_name}")

    def decorator(target: T) -> T:
        setattr(target, "__case_module__", canonical_name)
        return target

    return decorator


def get_test_case_module(test: unittest.TestCase) -> str:
    method = getattr(test, getattr(test, "_testMethodName", ""), None)
    method_module = normalize_case_module(str(getattr(method, "__case_module__", "") or ""))
    if method_module:
        return method_module

    class_module = normalize_case_module(str(getattr(test.__class__, "__case_module__", "") or ""))
    if class_module:
        return class_module

    module_obj = sys.modules.get(test.__class__.__module__)
    file_module = normalize_case_module(str(getattr(module_obj, "CASE_MODULE", "") or ""))
    if file_module:
        return file_module

    return ""
