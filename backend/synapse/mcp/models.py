from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MCPServerManifest:
    server_id: str
    display_name: str
    version: str
    description: str
    transport: str
    enabled: bool = False
    installed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPToolReference:
    server_id: str
    tool_name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPConnectionState:
    server_id: str
    connected: bool = False
    last_seen: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPRegistrySummary:
    total_servers: int
    enabled_servers: int
    connected_servers: int
    total_tools: int
