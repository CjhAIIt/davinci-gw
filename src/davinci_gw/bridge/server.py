"""桥接服务：对外暴露 MCP 工具，把调用转发到独立核心。

桥接只负责三件事：在内部端口上提供 MCP 端点、校验访问令牌、
把工具调用转发给核心。它不新增任何路由规则，行为完全由核心决定。
"""

from __future__ import annotations

import logging
from typing import Any, Mapping
from uuid import uuid4

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from davinci_gw import __version__ as CORE_VERSION
from davinci_gw.bridge.config import BridgeConfig
from davinci_gw.bridge.core import CoreClient, CoreUnavailableError
from davinci_gw.mcp.mapping import envelope, issue
from davinci_gw.mcp.schemas import GatewayToolResponse

LOGGER = logging.getLogger("davinci_gw.bridge.server")

BRIDGE_VERSION = CORE_VERSION

SERVER_INSTRUCTIONS = (
    "这是 DaVinci 网关路由的本地桥接服务，通过内部端口把调用转发到独立核心。"
    "标准工作流：先调用 validate_gateway_inputs，再调用 preview_gateway_update；"
    "向用户展示预览摘要并取得明确确认后，才调用 generate_gateway_arxml。"
    "生成必须使用同一核心进程预览返回的 preparation_id，并指定尚不存在的新 .arxml 输出路径。"
    "所有路径必须是带盘符的本地 Windows 绝对路径；禁止 URL、UNC、设备路径、网络共享"
    "和覆盖基准或已有文件。工具只返回有界 JSON 摘要，禁止请求或返回 ARXML 文件内容。"
)

_BRIDGE_TOOL_ANNOTATIONS = {
    "get_gateway_capabilities": ToolAnnotations(
        read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
    ),
    "validate_gateway_inputs": ToolAnnotations(
        read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
    ),
    "preview_gateway_update": ToolAnnotations(
        read_only_hint=True, destructive_hint=False, idempotent_hint=False, open_world_hint=False,
    ),
    "generate_gateway_arxml": ToolAnnotations(
        read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False,
    ),
}


def _failure(tool: str, summary: str, code: str, message: str) -> dict[str, Any]:
    """构造不泄露内部细节的失败信封。"""
    return envelope(
        tool,
        status="INTERNAL_FAILURE",
        operation_id=str(uuid4()),
        summary=summary,
        issues=[issue(code, message)],
    )


async def _forward(core: CoreClient, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """把工具调用转发给核心，并隔离核心故障。"""
    try:
        payload = await core.call_tool(name, arguments)
    except CoreUnavailableError:
        LOGGER.error("core unavailable tool=%s", name)
        return _failure(name, "桥接无法访问核心。", "BRIDGE_CORE_UNAVAILABLE", "核心不可用或返回了不可解析结果。")
    except Exception as exc:
        LOGGER.error("core forward failed tool=%s error_type=%s", name, type(exc).__name__)
        return _failure(name, "桥接转发核心时发生内部错误。", "BRIDGE_FORWARD_FAILED", "转发失败，请查看受控日志。")
    if not isinstance(payload, dict):
        return _failure(name, "桥接收到非预期的核心响应。", "BRIDGE_INVALID_PAYLOAD", "核心响应格式不受支持。")
    return payload


def build_bridge_server(core: CoreClient, *, config: BridgeConfig) -> MCPServer[Any]:
    """建立桥接 MCP 服务；工具实现只做转发。"""
    server: MCPServer[Any] = MCPServer(
        name="davinci-gw-bridge",
        title="DaVinci 网关配置桥接服务",
        description="在内部端口上把客户端请求转发到独立网关核心。",
        instructions=SERVER_INSTRUCTIONS,
        version=BRIDGE_VERSION,
        log_level="WARNING",
    )

    @server.tool(
        name="get_gateway_capabilities",
        description="查询核心版本、路由能力、Prepared Session 与路径安全策略，并返回桥接自身的端点信息；不读取用户文件。",
        annotations=_BRIDGE_TOOL_ANNOTATIONS["get_gateway_capabilities"],
        structured_output=True,
    )
    async def get_gateway_capabilities() -> GatewayToolResponse:
        payload = await _forward(core, "get_gateway_capabilities", {})
        product = dict(payload.get("product") or {})
        product["transport"] = "streamable-http"
        product["bridge"] = {
            "name": "davinci-gw-bridge",
            "version": BRIDGE_VERSION,
            "endpoint": config.url_for(),
            "core": config.core.describe(),
        }
        payload = {**payload, "product": product}
        return GatewayToolResponse.model_validate(payload)

    @server.tool(
        name="validate_gateway_inputs",
        description="只读校验一个本地 .xlsx 配置表和一个本地 .arxml 基准文件；路径必须为绝对路径。",
        annotations=_BRIDGE_TOOL_ANNOTATIONS["validate_gateway_inputs"],
        structured_output=True,
    )
    async def validate_gateway_inputs(config_path: str, baseline_path: str) -> GatewayToolResponse:
        payload = await _forward(core, "validate_gateway_inputs", {
            "config_path": config_path, "baseline_path": baseline_path,
        })
        return GatewayToolResponse.model_validate(payload)

    @server.tool(
        name="preview_gateway_update",
        description=(
            "解析并预览网关变更。DoIP 前置缺失时须先展示清单并等待用户选择，"
            "再以 BLOCK 或 SKIP 重新预览。成功后创建一次性 preparation_id，不写输出。"
        ),
        annotations=_BRIDGE_TOOL_ANNOTATIONS["preview_gateway_update"],
        structured_output=True,
    )
    async def preview_gateway_update(
        config_path: str, baseline_path: str, doip_missing_policy: str | None = None,
    ) -> GatewayToolResponse:
        payload = await _forward(core, "preview_gateway_update", {
            "config_path": config_path, "baseline_path": baseline_path,
            "doip_missing_policy": doip_missing_policy,
        })
        return GatewayToolResponse.model_validate(payload)

    @server.tool(
        name="generate_gateway_arxml",
        description=(
            "在用户确认预览后，使用 preparation_id 原子生成一个尚不存在的新 .arxml 文件；禁止覆盖。"
        ),
        annotations=_BRIDGE_TOOL_ANNOTATIONS["generate_gateway_arxml"],
        structured_output=True,
    )
    async def generate_gateway_arxml(preparation_id: str, output_path: str) -> GatewayToolResponse:
        payload = await _forward(core, "generate_gateway_arxml", {
            "preparation_id": preparation_id, "output_path": output_path,
        })
        return GatewayToolResponse.model_validate(payload)

    return server


def build_bridge_app(core: CoreClient, *, config: BridgeConfig) -> Any:
    """构建带令牌鉴权与 DNS 重绑定防护的 ASGI 应用。"""
    from mcp.server.transport_security import TransportSecuritySettings

    from davinci_gw.bridge.auth import BearerTokenMiddleware

    server = build_bridge_server(core, config=config)
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts(config.host),
        allowed_origins=[],
    )
    app = server.streamable_http_app(
        streamable_http_path=config.path,
        host=config.host,
        transport_security=transport_security,
    )
    return BearerTokenMiddleware(app, config.effective_token)


def allowed_hosts(host: str) -> list[str]:
    """生成 DNS 重绑定防护允许的 Host 白名单。"""
    if host in ("127.0.0.1", "localhost", "::1"):
        return ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    return [host, f"{host}:*", "127.0.0.1:*", "localhost:*"]
