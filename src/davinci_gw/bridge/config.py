"""桥接服务的监听参数与独立核心配置。"""

from __future__ import annotations

import ipaddress
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CoreMode = Literal["embedded", "stdio", "http"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_PATH = "/mcp"
LOOPBACK_NAMES = frozenset({"localhost"})

REDACTED = "***"

# 规范化后与之相等的参数名视为敏感项：值不进入任何对外描述。
SENSITIVE_NAMES = frozenset({
    "token", "accesstoken", "authtoken", "refreshtoken", "idtoken", "bearertoken",
    "secret", "clientsecret", "apisecret", "sharedsecret",
    "password", "passwd", "pwd", "passphrase",
    "credential", "credentials", "apikey", "accesskey", "secretkey", "privatekey",
    "sessionkey", "auth", "authorization", "key",
})


class BridgeConfigError(ValueError):
    """桥接配置不合法；调用方必须拒绝启动。"""


def is_loopback_host(host: str) -> bool:
    """判断监听地址是否只能在本机到达。"""
    candidate = host.strip().strip("[]").lower()
    if candidate in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def _normalize_name(name: str) -> str:
    """把参数名规范化为只含小写字母数字的形式，便于精确匹配。"""
    return re.sub(r"[^0-9a-z]", "", name.lower())


def is_sensitive_name(name: str) -> bool:
    """判断参数名是否属于可能承载凭据的名称。"""
    return _normalize_name(name.lstrip("-")) in SENSITIVE_NAMES


def redact_url(target: str) -> str:
    """抹掉 URL 中的用户凭据与敏感查询参数。

    核心目标可能写成 ``https://user:pass@host/mcp?token=xxx``，
    这类值一旦原样进入对外描述，持有 Bridge 令牌的客户端就能拿到
    超出 Bridge 自身权限的凭据。
    """
    try:
        parts = urlsplit(target)
    except ValueError:  # pragma: no cover - urlsplit 极少抛错
        return target
    if not parts.scheme or not parts.netloc:
        # 本地路径或可执行文件路径不是 URL，按原样保留。
        return target
    netloc = parts.netloc
    if "@" in netloc:
        userinfo, _, hostport = netloc.rpartition("@")
        name, separator, _ = userinfo.partition(":")
        netloc = f"{name}:{REDACTED}@{hostport}" if separator else f"{REDACTED}@{hostport}"
    query = parts.query
    if query:
        pairs = [
            (key, REDACTED if is_sensitive_name(key) else value)
            for key, value in parse_qsl(query, keep_blank_values=True)
        ]
        query = urlencode(pairs)
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def redact_args(args: tuple[str, ...]) -> list[str]:
    """抹掉命令行参数中的凭据。

    同时覆盖 ``--token=xxx`` 与 ``--token xxx`` 两种写法；参数名不含
    敏感字样的值原样保留，便于客户端判断核心形态。
    """
    redacted: list[str] = []
    redact_next = False
    for arg in args:
        if redact_next:
            redacted.append(REDACTED)
            redact_next = False
            continue
        name, separator, _ = arg.partition("=")
        if separator and is_sensitive_name(name):
            redacted.append(f"{name}={REDACTED}")
            continue
        if is_sensitive_name(arg):
            redacted.append(arg)
            redact_next = True
            continue
        redacted.append(arg)
    return redacted


@dataclass(frozen=True)
class CoreConfig:
    """独立核心的配置。

    核心与桥接进程解耦：桥接只负责转发，核心可以是同进程实现、
    独立的 STDIO 子进程，或内网另一台机器上的 HTTP 服务。
    """

    mode: CoreMode = "embedded"
    target: str | None = None
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    token: str | None = None
    timeout_seconds: float = 3600.0

    def validate(self) -> None:
        if self.mode not in ("embedded", "stdio", "http"):
            raise BridgeConfigError(f"未知的核心模式：{self.mode}")
        if self.mode in ("stdio", "http") and not self.target:
            raise BridgeConfigError(f"核心模式 {self.mode} 必须提供核心目标。")
        if self.mode == "http" and not str(self.target).lower().startswith(("http://", "https://")):
            raise BridgeConfigError("http 核心目标必须是 http 或 https 地址。")
        if self.timeout_seconds <= 0:
            raise BridgeConfigError("核心超时必须为正数。")

    def describe(self) -> dict[str, object]:
        """给出可公开的核心描述；令牌与目标中的凭据一律脱敏。

        该描述会随 ``get_gateway_capabilities`` 返回给任意通过鉴权的
        客户端，也会写进客户端发现文件，因此不能包含任何可能越权的
        凭据：令牌字段本身不参与描述，目标地址与参数中的密码、
        密钥类取值会被替换为 ``***``。
        """
        return {
            "mode": self.mode,
            "target": redact_url(self.target) if self.target else self.target,
            "args": redact_args(self.args),
        }


@dataclass(frozen=True)
class BridgeConfig:
    """桥接服务的监听、鉴权与核心配置。"""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    path: str = DEFAULT_PATH
    token: str | None = None
    core: CoreConfig = field(default_factory=CoreConfig)
    descriptor_path: Path | None = None
    allow_remote: bool = False
    tls_certfile: str | None = None
    tls_keyfile: str | None = None
    allow_remote_insecure: bool = False

    def __post_init__(self) -> None:
        """在构造时确定访问令牌。

        令牌必须在整个进程生命周期内保持不变：客户端发现文件里的令牌
        与服务端鉴权用的令牌必须逐字一致，否则调用会被判为 401。
        因此这里一次性生成并固定，而不是每次读取时重新生成。
        """
        if not self.token:
            object.__setattr__(self, "token", secrets.token_urlsafe(32))

    @property
    def tls_enabled(self) -> bool:
        """是否以 TLS 提供服务。"""
        return bool(self.tls_certfile and self.tls_keyfile)

    def validate(self) -> None:
        if not self.path.startswith("/"):
            raise BridgeConfigError("服务路径必须以 / 开头。")
        if not 0 <= self.port <= 65535:
            raise BridgeConfigError("端口必须在 0 到 65535 之间。")
        if not self.allow_remote and not is_loopback_host(self.host):
            raise BridgeConfigError("默认只允许回环监听；确需对外监听时必须显式开启允许远端。")
        if bool(self.tls_certfile) != bool(self.tls_keyfile):
            raise BridgeConfigError("TLS 证书与私钥必须同时提供。")
        if not is_loopback_host(self.host) and not self.tls_enabled and not self.allow_remote_insecure:
            # 对外监听时令牌与路由结果会跨主机传输，明文等同于把凭据
            # 交给链路上的旁观者。要么启用 TLS，要么由运维显式声明
            # 该端口已置于受信加密隧道之后。
            raise BridgeConfigError(
                "对外监听必须启用 TLS：提供 --tls-certfile 与 --tls-keyfile；"
                "若端口已置于受信加密隧道之后，请显式使用 --allow-remote-insecure。"
            )
        self.core.validate()

    @property
    def effective_token(self) -> str:
        """返回本次启动确定的访问令牌；多次读取结果一致。"""
        assert self.token is not None  # noqa: S101 - 由 __post_init__ 保证
        return self.token

    def url_for(self, port: int | None = None) -> str:
        """返回客户端可用的服务地址。"""
        host = self.host if ":" not in self.host else f"[{self.host}]"
        scheme = "https" if self.tls_enabled else "http"
        return f"{scheme}://{host}:{port if port is not None else self.port}{self.path}"
