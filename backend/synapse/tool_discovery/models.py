from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentToolView:
    tool_id: str
    display_name: str
    description: str
    category: str
    available: bool
    requires_approval: bool
    risk_level: str
    reason_unavailable: str | None = None


@dataclass(frozen=True)
class AgentToolCatalog:
    agent_id: str
    total_tools: int
    available_tools: int
    unavailable_tools: int
    approval_required_tools: int
    generated_at: str
    tools: list[AgentToolView] = field(default_factory=list)


@dataclass(frozen=True)
class ToolExplanation:
    tool: AgentToolView
    required_capability: str | None
    required_permission: str | None
    resource_scope_required: bool
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
