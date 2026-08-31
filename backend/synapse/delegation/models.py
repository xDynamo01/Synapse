from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

TaskStatus = str
TaskPriority = str
CompletionStatus = str

TASK_STATUSES: set[TaskStatus] = {
    "pending",
    "accepted",
    "rejected",
    "in_progress",
    "completed",
    "failed",
    "cancelled",
}

TASK_PRIORITIES: set[TaskPriority] = {"low", "normal", "high", "critical"}
COMPLETION_STATUSES: set[CompletionStatus] = {"completed", "failed", "needs_followup"}


@dataclass(frozen=True)
class DelegationTask:
    title: str
    description: str
    requester_agent_id: str
    assignee_agent_id: str
    status: TaskStatus = "pending"
    priority: TaskPriority = "normal"
    conversation_id: str | None = None
    mission_id: str | None = None
    due_at: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class DelegationCompletionSignal:
    task_id: str
    status: CompletionStatus
    summary: str
    created_by_agent_id: str
    result: str | None = None
    failure_reason: str | None = None
    needs_followup: bool = False
    followup_message: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
