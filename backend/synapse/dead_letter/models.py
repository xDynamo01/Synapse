from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

DeadLetterReason = str
DeadLetterStatus = str

DEAD_LETTER_REASONS: set[DeadLetterReason] = {
    "max_retries_exceeded",
    "timeout_exceeded",
    "manual_move",
    "repeated_failure",
    "execution_failure",
    "unknown",
}

DEAD_LETTER_STATUSES: set[DeadLetterStatus] = {
    "open",
    "reviewed",
    "restored",
    "closed",
    "archived",
}


@dataclass(frozen=True)
class DeadLetterEntry:
    task_id: str
    reason: DeadLetterReason
    status: DeadLetterStatus
    priority: str
    requester_agent_id: str
    assignee_agent_id: str
    mission_id: str | None = None
    attempt_id: str | None = None
    worker_id: str | None = None
    agent_id: str | None = None
    attempts: int = 0
    error: dict[str, Any] | None = None
    payload_redacted: dict[str, Any] = field(default_factory=dict)
    recovery_options: list[str] = field(default_factory=list)
    trace_reference: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None
    dlq_id: str = field(default_factory=lambda: str(uuid4()))
    latest_execution_id: str | None = None
    conversation_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
