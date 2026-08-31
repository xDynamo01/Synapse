from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentToolCallProposal:
    tool_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    confidence: float | None = None
    raw_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentToolCallingParseResult:
    found: bool
    proposals: list[AgentToolCallProposal]
    errors: list[str]
    raw_text: str


@dataclass(frozen=True)
class AgentToolCallingResult:
    agent_id: str
    conversation_id: str | None = None
    created_intents: list[dict[str, Any]] = field(default_factory=list)
    skipped_proposals: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
