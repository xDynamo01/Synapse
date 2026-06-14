from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from synapse.tools.calls import ToolCallRequest


@dataclass(frozen=True)
class ModelRequest:
    agent_id: str
    provider: str
    model: str | None
    user_message: str
    context: dict[str, Any]
    tools: list[dict[str, Any]] = field(default_factory=list)
    base_url: str | None = None


@dataclass(frozen=True)
class ModelResponse:
    content: str
    provider: str
    model: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
