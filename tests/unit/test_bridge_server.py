"""桥接服务只转发、不新增业务行为。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mcp import Client

from davinci_gw.bridge.config import BridgeConfig, CoreConfig
from davinci_gw.bridge.core import CoreUnavailableError
from davinci_gw.bridge.server import build_bridge_server


def _envelope(tool: str, **payload: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "tool": tool,
        "operation_id": "op-1",
        "status": "SUCCESS",
        "success": True,
        "summary": "ok",
        "issue_count": 0,
        "issues_truncated": False,
        "issues": [],
        **payload,
    }


class _RecordingCore:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail = fail

    async def call_tool(self, name: str, arguments: Any) -> dict[str, Any]:
        self.calls.append((name, dict(arguments)))
        if self.fail:
            raise CoreUnavailableError("core down")
        return _envelope(name)

    async def aclose(self) -> None:
        return None


def _config() -> BridgeConfig:
    return BridgeConfig(core=CoreConfig(mode="embedded"))


def test_bridge_exposes_only_the_gateway_tools() -> None:
    core = _RecordingCore()
    server = build_bridge_server(core, config=_config())

    async def scenario() -> None:
        async with Client(server) as client:
            listed = await client.list_tools()
            assert [tool.name for tool in listed.tools] == [
                "get_gateway_capabilities",
                "validate_gateway_inputs",
                "preview_gateway_update",
                "generate_gateway_arxml",
            ]

    asyncio.run(scenario())


def test_bridge_forwards_arguments_unchanged() -> None:
    core = _RecordingCore()
    server = build_bridge_server(core, config=_config())

    async def scenario() -> None:
        async with Client(server) as client:
            await client.call_tool("preview_gateway_update", {
                "config_path": "C:/tmp/a.xlsx",
                "baseline_path": "C:/tmp/a.arxml",
                "doip_missing_policy": "SKIP",
            })
            await client.call_tool("generate_gateway_arxml", {
                "preparation_id": "prep-1", "output_path": "C:/tmp/out.arxml",
            })

    asyncio.run(scenario())
    assert core.calls[0] == ("preview_gateway_update", {
        "config_path": "C:/tmp/a.xlsx",
        "baseline_path": "C:/tmp/a.arxml",
        "doip_missing_policy": "SKIP",
    })
    assert core.calls[1] == ("generate_gateway_arxml", {
        "preparation_id": "prep-1", "output_path": "C:/tmp/out.arxml",
    })


def test_capabilities_describe_the_bridge_and_its_core() -> None:
    core = _RecordingCore()
    server = build_bridge_server(core, config=_config())
    captured: dict[str, Any] = {}

    async def scenario() -> None:
        async with Client(server) as client:
            result = await client.call_tool("get_gateway_capabilities")
            captured["product"] = result.structured_content["product"]

    asyncio.run(scenario())
    product = captured["product"]
    assert product["transport"] == "streamable-http"
    assert product["bridge"]["core"]["mode"] == "embedded"
    assert product["bridge"]["endpoint"].endswith("/mcp")


def test_core_failure_becomes_a_controlled_envelope() -> None:
    core = _RecordingCore(fail=True)
    server = build_bridge_server(core, config=_config())
    captured: dict[str, Any] = {}

    async def scenario() -> None:
        async with Client(server) as client:
            result = await client.call_tool("validate_gateway_inputs", {
                "config_path": "C:/tmp/a.xlsx", "baseline_path": "C:/tmp/a.arxml",
            })
            captured["payload"] = result.structured_content

    asyncio.run(scenario())
    payload = captured["payload"]
    assert payload["status"] == "INTERNAL_FAILURE"
    assert payload["success"] is False
    assert payload["issues"][0]["code"] == "BRIDGE_CORE_UNAVAILABLE"
