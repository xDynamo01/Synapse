from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

ToolIntentSource = str
ToolIntentStatus = str

TOOL_INTENT_SOURCES: set[str] = {"user", "agent", "model", "system"}
TOOL_INTENT_STATUSES: set[str] = {
    "proposed",
    "reviewed",
    "approved",
    "rejected",
    "executed",
    "failed",
    "cancelled",
}


@dataclass(frozen=True)
class ToolIntentReview:
    intent_id: str
    decision: str
    reasons: list[str] = field(default_factory=list)
    reviewed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    reviewed_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolIntent:
    tool_id: str
    proposed_arguments: dict[str, Any]
    source: ToolIntentSource
    status: ToolIntentStatus = "proposed"
    source_agent_id: str | None = None
    conversation_id: str | None = None
    mission_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    decision_snapshot: dict[str, Any] = field(default_factory=dict)
    tool_snapshot: dict[str, Any] = field(default_factory=dict)
    review: dict[str, Any] | None = None
    execution_result: dict[str, Any] | None = None
    execution_plan: dict[str, Any] | None = None
    executed_at: str | None = None
    executor: str | None = None
    intent_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
