from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.mcp.models import (
    MCPConnectionState,
    MCPRegistrySummary,
    MCPServerManifest,
    MCPToolReference,
)
from synapse.mcp.registry import MCPRegistry

SEED_SERVERS = (
    ("local_fs", "Local Filesystem"),
    ("github", "GitHub"),
    ("browser", "Browser"),
    ("unreal", "Unreal Engine"),
    ("blender", "Blender"),
    ("docker", "Docker"),
)


class MCPRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        registry: MCPRegistry | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        self.registry = registry or MCPRegistry()
        self._executors: dict[tuple[str, str], Callable[[dict[str, Any]], dict[str, Any]]] = {}
        self.servers_path = self.data_dir.resolve("mcp/servers.yaml")
        self.tools_path = self.data_dir.resolve("mcp/tool_registry.yaml")
        self.servers_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()
        self._register_seed_servers()
        self._persist()

    def register_server(self, manifest: MCPServerManifest) -> MCPServerManifest:
        self.registry.register_server(manifest)
        self._persist_servers()
        return manifest

    def register_tool(self, tool: MCPToolReference) -> MCPToolReference:
        self.registry.register_tool_reference(tool)
        self._persist_tools()
        return tool

    def register_executor(
        self,
        server_id: str,
        tool_name: str,
        executor: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        server = self.get_server(server_id)
        if not server.enabled or not server.installed:
            raise ValueError(f"MCP server is disabled or not installed: {server_id}")
        self._executors[(server_id, tool_name)] = executor
        self.registry.set_connection_state(
            MCPConnectionState(
                server_id=server_id,
                connected=True,
                last_seen=datetime.now(UTC).isoformat(),
                metadata={"transport": server.transport},
            )
        )
        self.events.emit("mcp_server_health_changed", server_id, {"connected": True})

    def can_execute(self, server_id: str, tool_name: str) -> bool:
        return (server_id, tool_name) in self._executors

    def execute_tool(
        self, server_id: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        executor = self._executors.get((server_id, tool_name))
        if not executor:
            raise RuntimeError(f"MCP server unavailable: {server_id}")
        try:
            result = executor(dict(arguments))
        except Exception as exc:
            raise RuntimeError(f"MCP protocol error for {server_id}:{tool_name}") from exc
        if not isinstance(result, dict):
            raise RuntimeError("MCP protocol error: tool result must be an object")
        return result

    def get_server(self, server_id: str) -> MCPServerManifest:
        return self.registry.get_server(server_id)

    def list_servers(self) -> list[MCPServerManifest]:
        return self.registry.list_servers()

    def list_tools(self, server_id: str | None = None) -> list[MCPToolReference]:
        return self.registry.list_tools(server_id)

    def health(self) -> list[MCPConnectionState]:
        return self.registry.connection_states()

    def summary(self) -> MCPRegistrySummary:
        return self.registry.summary()

    def _load(self) -> None:
        server_payload = load_structured_file(self.servers_path)
        for raw in server_payload.get("servers", []):
            if isinstance(raw, dict):
                self.registry.register_server(MCPServerManifest(**raw))
        tool_payload = load_structured_file(self.tools_path)
        for raw in tool_payload.get("tools", []):
            if isinstance(raw, dict):
                self.registry.register_tool_reference(MCPToolReference(**raw))

    def _register_seed_servers(self) -> None:
        existing = {server.server_id for server in self.registry.list_servers()}
        for server_id, display_name in SEED_SERVERS:
            if server_id in existing:
                continue
            self.registry.register_server(
                MCPServerManifest(
                    server_id=server_id,
                    display_name=display_name,
                    version="0.0.0",
                    description=f"Placeholder manifest for a future {display_name} MCP server.",
                    transport="unconfigured",
                    enabled=False,
                    installed=False,
                    metadata={"seed": True, "connection_supported": False},
                )
            )

    def _persist(self) -> None:
        self._persist_servers()
        self._persist_tools()

    def _persist_servers(self) -> None:
        dump_structured_file(
            self.servers_path,
            {"servers": [asdict(server) for server in self.registry.list_servers()]},
        )

    def _persist_tools(self) -> None:
        dump_structured_file(
            self.tools_path,
            {"tools": [asdict(tool) for tool in self.registry.list_tools()]},
        )

    def status(self) -> dict[str, Any]:
        return {
            "summary": asdict(self.summary()),
            "connections": [asdict(state) for state in self.health()],
            "external_connections_supported": False,
        }
