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
    _SessionCore,
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


class _FakeSessionClient:
    """最小 MCP 客户端替身：可控制响应延迟。"""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.calls: list[str] = []

    async def call_tool(self, name: str, arguments: Any) -> Any:
        if self.delay:
            await asyncio.sleep(self.delay)
        self.calls.append(name)
        return _FakeResult(structured_content=_envelope(name))

    async def __aenter__(self) -> "_FakeSessionClient":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False


class _SessionCoreStub(_SessionCore):
    """可观测建连次数与延迟的会话核心。"""

    def __init__(self, *, delay: float = 0.0, timeout_seconds: float | None = None) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.sessions = 0
        self.client = _FakeSessionClient(delay=delay)

    async def _make_client(self) -> Any:
        self.sessions += 1
        await asyncio.sleep(0.05)
        return self.client


def test_concurrent_first_calls_share_a_single_session() -> None:
    """并发首次调用必须等待同一次建连，而不是直接判定核心不可用。"""
    core = _SessionCoreStub()

    async def scenario() -> None:
        results = await asyncio.gather(
            core.call_tool("get_gateway_capabilities", {}),
            core.call_tool("get_gateway_capabilities", {}),
            core.call_tool("get_gateway_capabilities", {}),
        )
        assert [item["status"] for item in results] == ["SUCCESS"] * 3
        await core.aclose()

    asyncio.run(scenario())
    assert core.sessions == 1


def test_core_call_respects_the_configured_timeout() -> None:
    """核心调用超时必须真正生效，而不是只做参数校验。"""
    core = _SessionCoreStub(delay=5.0, timeout_seconds=0.05)

    async def scenario() -> None:
        with pytest.raises(CoreUnavailableError) as failure:
            await core.call_tool("get_gateway_capabilities", {})
        assert "超时" in str(failure.value)
        await core.aclose()

    asyncio.run(scenario())


class _SlowService(_FakeService):
    """处理过程很慢的核心服务替身。"""

    async def validate_gateway_inputs(self, **kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(5)
        return _envelope("validate_gateway_inputs")


def test_embedded_core_applies_the_timeout() -> None:
    core = EmbeddedCore(_SlowService(), timeout_seconds=0.05)

    async def scenario() -> None:
        with pytest.raises(CoreUnavailableError):
            await core.call_tool("validate_gateway_inputs", {
                "config_path": "C:/tmp/a.xlsx", "baseline_path": "C:/tmp/a.arxml",
            })

    asyncio.run(scenario())


def test_build_core_passes_the_timeout_to_the_core() -> None:
    assert build_core(CoreConfig(mode="embedded", timeout_seconds=12.5))._timeout_seconds == 12.5
    assert build_core(CoreConfig(mode="http", target="http://127.0.0.1:9100/mcp",
                                 timeout_seconds=30.0))._timeout_seconds == 30.0


class _FlakySessionCore(_SessionCore):
    """第一次建连失败、第二次成功的会话核心。"""

    def __init__(self) -> None:
        super().__init__()
        self.sessions = 0

    async def _make_client(self) -> Any:
        self.sessions += 1
        if self.sessions == 1:
            raise ConnectionRefusedError("核心暂时不可达")
        return _FakeSessionClient()


def test_failed_session_is_reset_so_the_next_call_can_reconnect() -> None:
    """首次建连失败后必须能重连，而不是永远复用一个失败的任务。"""
    core = _FlakySessionCore()

    async def scenario() -> None:
        with pytest.raises(CoreUnavailableError):
            await core.call_tool("get_gateway_capabilities", {})
        result = await core.call_tool("get_gateway_capabilities", {})
        assert result["status"] == "SUCCESS"
        await core.aclose()

    asyncio.run(scenario())
    assert core.sessions == 2
