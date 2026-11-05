"""桥接服务的访问令牌校验。

桥接在内部端口上对外提供 MCP 端点，任何能访问该端口的进程都可能
发起调用，因此所有请求都必须携带启动时确定的 Bearer 令牌。
"""

from __future__ import annotations

import hmac
from typing import Any, Awaitable, Callable, MutableMapping

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class BearerTokenMiddleware:
    """校验 ``Authorization: Bearer <token>`` 的纯 ASGI 中间件。"""

    def __init__(self, app: Any, token: str) -> None:
        self._app = app
        self._token = token

    @property
    def expected_token(self) -> str:
        """本次启动要求的令牌；与客户端发现文件中的令牌必须一致。"""
        return self._token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        if not self._authorized(scope.get("headers") or []):
            await self._reject(receive, send)
            return
        await self._app(scope, receive, send)

    def _authorized(self, headers: list[tuple[bytes, bytes]]) -> bool:
        for raw_name, raw_value in headers:
            if raw_name.decode("latin-1").lower() != "authorization":
                continue
            scheme, _, value = raw_value.decode("latin-1").partition(" ")
            if scheme.lower() != "bearer":
                return False
            return hmac.compare_digest(value.strip(), self._token)
        return False

    async def _reject(self, receive: Receive, send: Send) -> None:
        # 先排空请求体再回应：否则客户端还在发送 body 时服务端就关闭连接，
        # Windows 会用 RST 中断连接，调用方收到的是连接错误而不是 401。
        await self._drain_body(receive)
        body = b'{"error":"unauthorized"}'
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("latin-1")),
                (b"www-authenticate", b"Bearer"),
            ],
        })
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _drain_body(receive: Receive) -> None:
        """读取并丢弃请求体，最多处理 1 MiB，避免异常客户端无限占用内存。"""
        limit = 1 << 20
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return
            limit -= len(message.get("body", b""))
            if not message.get("more_body", False):
                return
            if limit <= 0:
                return
