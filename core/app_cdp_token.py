# 离线签发桌面 App 的 CDP 调试 token；仅读取指定私钥，不生成或修改密钥，也不启动 App 或访问网络。
"""与 App 的 Ed25519 启动凭证协议兼容，成功时标准输出仅包含一条 token。

依赖：Python 3.9+、cryptography（缺少时执行 python -m pip install cryptography）。
示例：python app_cdp_token.py --private-key C:\\keys\\private.pem --port 9222
"""

import argparse
import base64
import json
from pathlib import Path
import re
import sys
import time
from typing import Optional


DEFAULT_TTL_SECONDS = 120
MAX_TTL_SECONDS = 86400
MAX_SAFE_INTEGER = (1 << 53) - 1


class UniqueOption(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        # 拒绝重复参数，避免操作者误把另一端口或有效期覆盖到最终凭证中。
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"参数 {option_string} 不能重复。")
        setattr(namespace, self.dest, values)


def parse_positive_integer(value: str, maximum: int) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", value) or len(value) > len(str(maximum)):
        raise argparse.ArgumentTypeError(f"必须是 1 到 {maximum} 的整数。")
    number = int(value)
    if number > maximum:
        raise argparse.ArgumentTypeError(f"必须是 1 到 {maximum} 的整数。")
    return number


def base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def issue_token(
    private_key_pem: bytes,
    port: int,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now_seconds: Optional[int] = None,
) -> str:
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("port 必须是 1 到 65535 的整数。")
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
        raise ValueError("ttl-seconds 必须是 1 到 86400 的整数。")
    if now_seconds is None:
        now_seconds = int(time.time())
    if type(now_seconds) is not int or not 0 <= now_seconds <= MAX_SAFE_INTEGER - ttl_seconds:
        raise ValueError("签发时间必须是有效的 Unix 秒数。")
    if not isinstance(private_key_pem, bytes) or not private_key_pem.strip().startswith(b"-----BEGIN PRIVATE KEY-----"):
        raise ValueError("需要 Ed25519 PKCS8 PEM 私钥，不能使用公钥或加密私钥。")

    # 延迟加载依赖，确保未安装 cryptography 时仍能查看 --help。
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        raise ValueError("缺少 cryptography；请使用当前 Python 执行 -m pip install cryptography。") from None

    try:
        private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    except Exception:
        # 不回显密钥或密码库原始异常，防止敏感内容进入终端和日志。
        raise ValueError("无法读取私钥，请提供有效的 Ed25519 PKCS8 PEM 私钥。") from None
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("签发私钥必须使用 Ed25519 算法。")

    payload = {
        "v": 1,
        "aud": "dicloak-app-cdp",
        "iat": now_seconds,
        "exp": now_seconds + ttl_seconds,
        "port": port,
    }
    encoded_payload = base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    # 必须签名 base64url 文本本身，而非原 JSON；字段顺序与现有 Node.js 签发工具一致。
    try:
        signature = private_key.sign(encoded_payload.encode("ascii"))
    except Exception:
        raise ValueError("Ed25519 签名失败。") from None
    return f"{encoded_payload}.{base64url(signature)}"


def main(argv=None) -> int:
    # Windows 重定向时也统一使用 UTF-8，避免中文帮助与错误提示乱码；token 本身始终为 ASCII。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="离线签发 App CDP 调试 token；默认有效期 2 分钟，最长 24 小时。",
        epilog="成功时只输出 token，可赋给 PowerShell 的 $token；不会改动私钥或联网。",
        allow_abbrev=False,
    )
    parser.add_argument("--private-key", required=True, action=UniqueOption, metavar="PEM", help="现有 Ed25519 PKCS8 PEM 私钥路径")
    parser.add_argument(
        "--port", required=True, action=UniqueOption, type=lambda value: parse_positive_integer(value, 65535), help="授权端口，1..65535"
    )
    parser.add_argument(
        "--ttl-seconds", action=UniqueOption, type=lambda value: parse_positive_integer(value, MAX_TTL_SECONDS), help="有效秒数，1..86400，默认 120"
    )
    args = parser.parse_args(argv)
    try:
        # 只读已有文件；不自动寻找、复制、覆盖私钥，也不把凭证另存到磁盘。
        try:
            private_key_pem = Path(args.private_key).expanduser().read_bytes()
        except (OSError, ValueError):
            raise ValueError("无法读取私钥文件，请检查路径和读取权限。") from None
        token = issue_token(private_key_pem, args.port, args.ttl_seconds if args.ttl_seconds is not None else DEFAULT_TTL_SECONDS)
    except ValueError as error:
        print(f"App CDP 凭证错误：{error}", file=sys.stderr)
        return 1
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
