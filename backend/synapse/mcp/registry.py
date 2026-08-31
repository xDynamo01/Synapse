from __future__ import annotations

from synapse.core.exceptions import NotFound, ValidationError
from synapse.mcp.models import (
    MCPConnectionState,
    MCPRegistrySummary,
    MCPServerManifest,
    MCPToolReference,
)


class MCPRegistry:
    def __init__(self) -> None:
        self._servers: dict[str, MCPServerManifest] = {}
        self._tools: dict[tuple[str, str], MCPToolReference] = {}
        self._connections: dict[str, MCPConnectionState] = {}

    def register_server(self, manifest: MCPServerManifest) -> None:
        if not manifest.server_id.strip():
            raise ValidationError("MCP server_id is required")
        self._servers[manifest.server_id] = manifest
        self._connections.setdefault(
            manifest.server_id,
            MCPConnectionState(server_id=manifest.server_id),
        )

    def get_server(self, server_id: str) -> MCPServerManifest:
        try:
            return self._servers[server_id]
        except KeyError as exc:
            raise NotFound(f"MCP server not found: {server_id}") from exc

    def list_servers(self) -> list[MCPServerManifest]:
        return sorted(self._servers.values(), key=lambda server: server.server_id)

    def register_tool_reference(self, tool: MCPToolReference) -> None:
        if not tool.tool_name.strip():
            raise ValidationError("MCP tool_name is required")
        self.get_server(tool.server_id)
        self._tools[(tool.server_id, tool.tool_name)] = tool

    def list_tools(self, server_id: str | None = None) -> list[MCPToolReference]:
        if server_id:
            self.get_server(server_id)
        tools = list(self._tools.values())
        if server_id:
            tools = [tool for tool in tools if tool.server_id == server_id]
        return sorted(tools, key=lambda tool: (tool.server_id, tool.tool_name))

    def connection_states(self) -> list[MCPConnectionState]:
        return sorted(self._connections.values(), key=lambda state: state.server_id)

    def set_connection_state(self, state: MCPConnectionState) -> None:
        self.get_server(state.server_id)
        self._connections[state.server_id] = state

    def summary(self) -> MCPRegistrySummary:
        servers = self.list_servers()
        return MCPRegistrySummary(
            total_servers=len(servers),
            enabled_servers=sum(server.enabled for server in servers),
            connected_servers=sum(state.connected for state in self._connections.values()),
            total_tools=len(self._tools),
        )
