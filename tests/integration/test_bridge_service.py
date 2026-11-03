"""桥接服务在真实内部端口上的端到端行为。"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from contextlib import AsyncExitStack
from typing import Any

import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from davinci_gw.bridge.config import BridgeConfig, CoreConfig
from davinci_gw.bridge.server import build_bridge_app


class _StubCore:
    """不接触文件的核心替身。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: Any) -> dict[str, Any]:
        self.calls.append((name, dict(arguments)))
        return {
            "schema_version": "1.0",
            "tool": name,
            "operation_id": "op-1",
            "status": "SUCCESS",
            "success": True,
            "summary": "ok",
            "issue_count": 0,
            "issues_truncated": False,
            "issues": [],
        }

    async def aclose(self) -> None:
        return None


def _post_without_token(url: str, token: str | None = None) -> int:
    """发起一个 MCP 请求，返回状态码；令牌为 None 时不带认证头。"""
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)


def test_bridge_serves_mcp_over_an_internal_port_with_token_auth() -> None:
    import uvicorn

    core = _StubCore()
    config = BridgeConfig(host="127.0.0.1", port=0, token="test-token", core=CoreConfig(mode="embedded"))
    config.validate()

    async def scenario() -> None:
        app = build_bridge_app(core, config=config)
        uvicorn_config = uvicorn.Config(
            app, host=config.host, port=config.port, log_level="warning", access_log=False,
        )
        server = uvicorn.Server(uvicorn_config)
        task = asyncio.create_task(server.serve())
        try:
            while not server.started:
                if task.done():
                    task.result()
                    raise AssertionError("桥接服务意外退出。")
                await asyncio.sleep(0.02)
            port = server.servers[0].sockets[0].getsockname()[1]
            url = f"http://127.0.0.1:{port}/mcp"

            # 无令牌与错误令牌都必须被拒绝。
            # 阻塞式请求必须放到线程中，否则会饿死同循环里的服务端。
            assert await asyncio.to_thread(_post_without_token, url) == 401
            assert await asyncio.to_thread(_post_without_token, url, "wrong-token") == 401

            # 正确令牌可以通过官方 MCP 客户端完成握手与调用。
            async with AsyncExitStack() as stack:
                from mcp.shared._httpx_utils import create_mcp_http_client

                http_client = await stack.enter_async_context(
                    create_mcp_http_client(headers={"Authorization": "Bearer test-token"}),
                )
                transport = streamable_http_client(url, http_client=http_client)
                async with Client(transport) as client:
                    listed = await client.list_tools()
                    assert [tool.name for tool in listed.tools] == [
                        "get_gateway_capabilities",
                        "validate_gateway_inputs",
                        "preview_gateway_update",
                        "generate_gateway_arxml",
                    ]
                    result = await client.call_tool("get_gateway_capabilities")
                    payload = result.structured_content
                    assert payload["status"] == "SUCCESS"
                    assert payload["product"]["transport"] == "streamable-http"
                    assert payload["product"]["bridge"]["endpoint"].endswith("/mcp")
        finally:
            server.should_exit = True
            await task

    asyncio.run(scenario())
    assert core.calls == [("get_gateway_capabilities", {})]
