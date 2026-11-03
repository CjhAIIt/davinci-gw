"""桥接服务的监听参数与独立核心配置。"""

from __future__ import annotations

import ipaddress
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping

CoreMode = Literal["embedded", "stdio", "http"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_PATH = "/mcp"
LOOPBACK_NAMES = frozenset({"localhost"})


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
        """给出可公开的核心描述；不包含令牌等敏感信息。"""
        return {"mode": self.mode, "target": self.target, "args": list(self.args)}


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

    def validate(self) -> None:
        if not self.path.startswith("/"):
            raise BridgeConfigError("服务路径必须以 / 开头。")
        if not 0 <= self.port <= 65535:
            raise BridgeConfigError("端口必须在 0 到 65535 之间。")
        if not self.allow_remote and not is_loopback_host(self.host):
            raise BridgeConfigError("默认只允许回环监听；确需对外监听时必须显式开启允许远端。")
        self.core.validate()

    @property
    def effective_token(self) -> str:
        """返回访问令牌；未显式配置时生成一次性随机值。"""
        return self.token or secrets.token_urlsafe(32)

    def url_for(self, port: int | None = None) -> str:
        """返回客户端可用的服务地址。"""
        host = self.host if ":" not in self.host else f"[{self.host}]"
        return f"http://{host}:{port if port is not None else self.port}{self.path}"
