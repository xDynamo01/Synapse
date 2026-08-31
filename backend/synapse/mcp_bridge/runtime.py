from __future__ import annotations

import re
from dataclasses import asdict
from datetime import UTC, datetime

from synapse.core.exceptions import NotFound
from synapse.mcp.runtime import MCPRuntime
from synapse.mcp_bridge.models import MCPToolBridgeDefinition, MCPToolBridgeStatus
from synapse.tools.contracts import ToolExecutionPort
from synapse.tools.models import ToolDefinition, ToolExecutionRequest

MCP_EXECUTION_UNAVAILABLE = "MCP execution is not implemented in this stage"


class MCPToolBridgeRuntime:
    def __init__(self, mcp: MCPRuntime, tools: ToolExecutionPort) -> None:
        self.mcp = mcp
        self.tools = tools
        self._bridged: dict[str, MCPToolBridgeDefinition] = {}

    def list_bridge_tools(self) -> list[MCPToolBridgeDefinition]:
        return sorted(self._bridged.values(), key=lambda tool: tool.bridge_tool_id)

    def get_bridge_tool(self, bridge_tool_id: str) -> MCPToolBridgeDefinition:
        try:
            return self._bridged[bridge_tool_id]
        except KeyError as exc:
            raise NotFound(f"MCP bridge tool not found: {bridge_tool_id}") from exc

    def sync_from_mcp_registry(self) -> MCPToolBridgeStatus:
        servers = {server.server_id: server for server in self.mcp.list_servers()}
        connections = {state.server_id: state for state in self.mcp.health()}
        for reference in self.mcp.list_tools():
            server = servers[reference.server_id]
            state = connections[reference.server_id]
            bridge_tool_id = self.bridge_tool_id(reference.server_id, reference.tool_name)
            available = bool(
                server.enabled
                and server.installed
                and state.connected
                and self.mcp.can_execute(reference.server_id, reference.tool_name)
            )
            bridged = MCPToolBridgeDefinition(
                bridge_tool_id=bridge_tool_id,
                server_id=reference.server_id,
                mcp_tool_name=reference.tool_name,
                display_name=f"{server.display_name}: {reference.tool_name}",
                description=reference.description,
                input_schema=reference.input_schema,
                output_schema=reference.output_schema,
                enabled=available,
                available=available,
                risk_level="high",
                metadata={
                    **reference.metadata,
                    "mcp_bridge": True,
                    "server_installed": server.installed,
                    "server_enabled": server.enabled,
                    "server_connected": state.connected,
                    "execution_implemented": available,
                    "processing_boundary": "external_mcp",
                    "provider_id": reference.server_id,
                },
            )
            self._bridged[bridge_tool_id] = bridged
            handler = self._handler(bridged) if available else self._unavailable_handler
            self.tools.register(self._tool_definition(bridged), handler)
        return self.bridge_status()

    def bridge_status(self) -> MCPToolBridgeStatus:
        bridged = self.list_bridge_tools()
        return MCPToolBridgeStatus(
            total_mcp_tools=len(self.mcp.list_tools()),
            bridged_tools=len(bridged),
            unavailable_tools=sum(not tool.available for tool in bridged),
            generated_at=datetime.now(UTC).isoformat(),
            metadata={"execution_implemented": any(tool.enabled for tool in bridged)},
        )

    def explain_bridge_tool(self, bridge_tool_id: str) -> dict[str, object]:
        bridged = self.get_bridge_tool(bridge_tool_id)
        return {
            "bridge_tool": asdict(bridged),
            "tool_definition": asdict(self.tools.get_tool(bridge_tool_id)),
            "execution_available": bridged.enabled and bridged.available,
            "reason": None if bridged.enabled and bridged.available else MCP_EXECUTION_UNAVAILABLE,
        }

    @staticmethod
    def bridge_tool_id(server_id: str, tool_name: str) -> str:
        return f"mcp:{_identifier(server_id)}:{_identifier(tool_name)}"

    @staticmethod
    def _tool_definition(bridged: MCPToolBridgeDefinition) -> ToolDefinition:
        return ToolDefinition(
            tool_id=bridged.bridge_tool_id,
            display_name=bridged.display_name,
            description=bridged.description,
            category="mcp",
            input_schema=bridged.input_schema,
            output_schema=bridged.output_schema,
            enabled=bridged.enabled and bridged.available,
            approval_required=True,
            risk_level=bridged.risk_level,
            metadata={
                **bridged.metadata,
                "server_id": bridged.server_id,
                "mcp_tool_name": bridged.mcp_tool_name,
                "unavailable_reason": MCP_EXECUTION_UNAVAILABLE,
            },
        )

    @staticmethod
    def _unavailable_handler(request: ToolExecutionRequest) -> dict[str, object]:
        raise RuntimeError(MCP_EXECUTION_UNAVAILABLE)

    def _handler(self, bridged: MCPToolBridgeDefinition):
        return MCPToolExecutorAdapter(self.mcp, bridged)


class MCPToolExecutorAdapter:
    """Technology-only adapter invoked exclusively by ToolRuntime."""

    def __init__(self, mcp: MCPRuntime, definition: MCPToolBridgeDefinition) -> None:
        self.mcp = mcp
        self.definition = definition

    def __call__(self, request: ToolExecutionRequest) -> dict[str, object]:
        return self.mcp.execute_tool(
            self.definition.server_id,
            self.definition.mcp_tool_name,
            request.arguments,
        )


def _identifier(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip().lower())
    return normalized.strip("._-") or "unnamed"
