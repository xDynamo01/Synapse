from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MCPToolBridgeDefinition:
    bridge_tool_id: str
    server_id: str
    mcp_tool_name: str
    display_name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    enabled: bool = False
    available: bool = False
    risk_level: str = "high"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPToolBridgeStatus:
    total_mcp_tools: int
    bridged_tools: int
    unavailable_tools: int
    generated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)
