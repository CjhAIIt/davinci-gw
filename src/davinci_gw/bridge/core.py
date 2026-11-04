"""桥接服务的核心客户端。

桥接自身不实现任何路由规则，只把工具调用转发给核心。核心有三种形态：

- ``embedded``：与 MCP STDIO 服务共用同一套应用层逻辑，进程内调用；
- ``stdio``：独立的 MCP 子进程，通过 stdin/stdout 通信；
- ``http``：内网另一台机器上的 MCP 服务，通过 Streamable HTTP 通信。

三种形态都返回同一份有界 JSON 信封，桥接只做转发与鉴权。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Mapping, Protocol

from davinci_gw.bridge.config import BridgeConfigError, CoreConfig

LOGGER = logging.getLogger("davinci_gw.bridge.core")

BRIDGE_TOOL_NAMES = (
    "get_gateway_capabilities",
    "validate_gateway_inputs",
    "preview_gateway_update",
    "generate_gateway_arxml",
)


class CoreUnavailableError(RuntimeError):
    """核心不可达、不支持该工具，或返回了无法解析的结果。"""


async def _await_with_timeout(awaitable: Any, timeout_seconds: float | None, label: str) -> Any:
    """在可选超时下等待一个 awaitable，超时统一转为核心不可用。"""
    try:
        if timeout_seconds is None:
            return await awaitable
        return await asyncio.wait_for(awaitable, timeout_seconds)
    except asyncio.TimeoutError as exc:
        LOGGER.error("core call timeout label=%s timeout=%.3fs", label, timeout_seconds)
        raise CoreUnavailableError(f"核心调用超时（{timeout_seconds} 秒）：{label}") from exc


class CoreClient(Protocol):
    """桥接对核心的最小要求。"""

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """调用核心工具并返回有界 JSON 信封。"""

    async def aclose(self) -> None:
        """释放核心会话。"""


def _extract_payload(result: Any) -> dict[str, Any]:
    """从 MCP 调用结果中取出结构化 JSON 信封。"""
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise CoreUnavailableError("核心返回了无法解析的结果。")


class EmbeddedCore:
    """进程内核心：复用 MCP 服务的应用层逻辑，不引入额外 IPC。"""

    def __init__(self, service: Any | None = None, *, timeout_seconds: float | None = None) -> None:
        if service is None:
            from davinci_gw.mcp.service import GatewayMcpService

            service = GatewayMcpService()
        self._service = service
        self._timeout_seconds = timeout_seconds

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        handlers = {
            "get_gateway_capabilities": self._service.get_gateway_capabilities,
            "validate_gateway_inputs": self._service.validate_gateway_inputs,
            "preview_gateway_update": self._service.preview_gateway_update,
            "generate_gateway_arxml": self._service.generate_gateway_arxml,
        }
        handler = handlers.get(name)
        if handler is None:
            raise CoreUnavailableError(f"核心不支持工具 {name}。")
        payload = handler(**dict(arguments))
        if hasattr(payload, "__await__"):
            payload = await _await_with_timeout(payload, self._timeout_seconds, name)
        return dict(payload)

    async def aclose(self) -> None:
        close = getattr(self._service, "close", None)
        if close is None:
            return
        result = close()
        if hasattr(result, "__await__"):
            await result


class _SessionCore:
    """基于 MCP 客户端会话的核心：会话在独立长驻任务中建立并复用。

    会话必须在同一个任务里进入和退出（MCP 客户端内部使用 anyio 取消域），
    因此这里用专属任务承载会话生命周期；关闭时只发信号并等待该任务收尾。
    """

    def __init__(self, *, timeout_seconds: float | None = None) -> None:
        self._client: Any | None = None
        self._task: asyncio.Task[None] | None = None
        self._ready: asyncio.Event | None = None
        self._stop: asyncio.Event | None = None
        self._error: BaseException | None = None
        self._lock: asyncio.Lock | None = None
        self._timeout_seconds = timeout_seconds

    async def _make_client(self) -> Any:
        raise NotImplementedError

    async def _session_task(self) -> None:
        assert self._ready is not None
        assert self._stop is not None
        try:
            async with await self._make_client() as client:
                self._client = client
                self._ready.set()
                await self._stop.wait()
        except BaseException as exc:  # noqa: BLE001 - 记录后由调用方判断
            self._error = exc
            self._ready.set()

    async def start(self) -> None:
        """建立核心会话；并发首次调用共享同一次建连。

        多个请求同时到达时，只允许其中一个真正建立会话，其余请求等待
        同一个就绪信号后再继续，避免出现“核心会话不可用”的裸失败。
        """
        if self._client is not None:
            return
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if self._client is not None:
                return
            if self._task is None:
                self._ready = asyncio.Event()
                self._stop = asyncio.Event()
                self._error = None
                self._task = asyncio.create_task(self._session_task())
            ready = self._ready
        assert ready is not None
        await ready.wait()
        if self._client is None:
            raise CoreUnavailableError("核心会话启动失败。") from self._error

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if self._client is None:
            await self.start()
        client = self._client
        if client is None:
            raise CoreUnavailableError("核心会话不可用。")
        try:
            result = await _await_with_timeout(
                client.call_tool(name, dict(arguments)), self._timeout_seconds, name,
            )
        except CoreUnavailableError:
            raise
        except Exception as exc:
            LOGGER.error("core tool call failed tool=%s error_type=%s", name, type(exc).__name__)
            raise CoreUnavailableError(f"核心调用失败：{name}") from exc
        if getattr(result, "isError", False):
            LOGGER.error("core returned error tool=%s", name)
        return _extract_payload(result)

    async def aclose(self) -> None:
        task = self._task
        self._task = None
        self._client = None
        self._lock = None
        if task is None:
            return
        assert self._stop is not None
        self._stop.set()
        try:
            await task
        except Exception as exc:  # pragma: no cover - 关闭期异常不影响退出
            LOGGER.error("core session close failed error_type=%s", type(exc).__name__)


class StdioCore(_SessionCore):
    """独立核心进程：通过 STDIO 通信，核心可单独升级。"""

    def __init__(
        self,
        command: str,
        args: tuple[str, ...] = (),
        env: Mapping[str, str] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self._command = command
        self._args = tuple(args)
        self._env = dict(env) if env else None

    async def _make_client(self) -> Any:
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters

        parameters = StdioServerParameters(command=self._command, args=list(self._args), env=self._env)
        return Client(parameters)


class HttpCore(_SessionCore):
    """内网独立核心：通过 Streamable HTTP 通信，核心可单独部署升级。"""

    def __init__(
        self,
        url: str,
        token: str | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self._url = url
        self._token = token

    async def _make_client(self) -> Any:
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client

        headers = {"Authorization": f"Bearer {self._token}"} if self._token else None
        http_client = _create_http_client(headers)
        return Client(streamable_http_client(self._url, http_client=http_client))


def _create_http_client(headers: dict[str, str] | None) -> Any:
    """创建带 MCP 默认超时的 HTTP 客户端；必要时退回普通客户端。"""
    try:
        from mcp.shared._httpx_utils import create_mcp_http_client

        return create_mcp_http_client(headers=headers)
    except Exception:  # pragma: no cover - 仅在 SDK 结构变化时触发
        import httpx2

        return httpx2.AsyncClient(headers=headers)


def build_core(config: CoreConfig) -> CoreClient:
    """按配置创建核心客户端。"""
    config.validate()
    timeout = config.timeout_seconds
    if config.mode == "embedded":
        return EmbeddedCore(timeout_seconds=timeout)
    if config.mode == "stdio":
        assert config.target is not None
        return StdioCore(config.target, config.args, config.env, timeout_seconds=timeout)
    if config.mode == "http":
        assert config.target is not None
        return HttpCore(config.target, config.token, timeout_seconds=timeout)
    raise BridgeConfigError(f"未知的核心模式：{config.mode}")
