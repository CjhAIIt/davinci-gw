"""桥接核心客户端的转发与结果解析。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from davinci_gw.bridge.config import BridgeConfigError, CoreConfig
from davinci_gw.bridge.core import (
    CoreUnavailableError,
    EmbeddedCore,
    HttpCore,
    StdioCore,
    _extract_payload,
    build_core,
)


def _envelope(tool: str) -> dict[str, Any]:
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
    }


class _FakeService:
    """最小核心服务替身，记录收到的调用。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_gateway_capabilities(self) -> dict[str, Any]:
        self.calls.append(("get_gateway_capabilities", {}))
        return _envelope("get_gateway_capabilities")

    async def validate_gateway_inputs(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("validate_gateway_inputs", kwargs))
        return _envelope("validate_gateway_inputs")

    async def preview_gateway_update(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("preview_gateway_update", kwargs))
        return _envelope("preview_gateway_update")

    async def generate_gateway_arxml(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("generate_gateway_arxml", kwargs))
        return _envelope("generate_gateway_arxml")


class _FakeResult:
    def __init__(self, structured_content: Any = None, content: list[Any] | None = None) -> None:
        self.structured_content = structured_content
        self.content = content or []
        self.isError = False


class _FakeText:
    def __init__(self, text: str) -> None:
        self.text = text


def test_embedded_core_forwards_tool_calls() -> None:
    service = _FakeService()
    core = EmbeddedCore(service)

    async def scenario() -> None:
        capabilities = await core.call_tool("get_gateway_capabilities", {})
        assert capabilities["status"] == "SUCCESS"
        await core.call_tool("validate_gateway_inputs", {
            "config_path": "C:/tmp/a.xlsx", "baseline_path": "C:/tmp/a.arxml",
        })

    asyncio.run(scenario())
    assert service.calls[0][0] == "get_gateway_capabilities"
    assert service.calls[1] == ("validate_gateway_inputs", {
        "config_path": "C:/tmp/a.xlsx", "baseline_path": "C:/tmp/a.arxml",
    })


def test_embedded_core_rejects_unknown_tools() -> None:
    core = EmbeddedCore(_FakeService())

    async def scenario() -> None:
        with pytest.raises(CoreUnavailableError):
            await core.call_tool("start_bug_repair", {})

    asyncio.run(scenario())


def test_extract_payload_prefers_structured_content() -> None:
    payload = _envelope("get_gateway_capabilities")
    assert _extract_payload(_FakeResult(structured_content=payload)) == payload


def test_extract_payload_falls_back_to_text_content() -> None:
    payload = _envelope("preview_gateway_update")
    result = _FakeResult(content=[_FakeText(json.dumps(payload))])
    assert _extract_payload(result) == payload


def test_extract_payload_rejects_unusable_results() -> None:
    with pytest.raises(CoreUnavailableError):
        _extract_payload(_FakeResult(content=[_FakeText("not json")]))
    with pytest.raises(CoreUnavailableError):
        _extract_payload(_FakeResult())


def test_build_core_selects_the_configured_core() -> None:
    assert isinstance(build_core(CoreConfig(mode="embedded")), EmbeddedCore)
    assert isinstance(build_core(CoreConfig(mode="stdio", target="davinci-gw-mcp.exe")), StdioCore)
    assert isinstance(build_core(CoreConfig(mode="http", target="http://127.0.0.1:9100/mcp")), HttpCore)


def test_build_core_rejects_invalid_configuration() -> None:
    with pytest.raises(BridgeConfigError):
        build_core(CoreConfig(mode="stdio"))
