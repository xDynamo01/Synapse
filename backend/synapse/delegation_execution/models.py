from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

ExecutionStatus = str

EXECUTION_STATUSES: set[ExecutionStatus] = {
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
}


@dataclass(frozen=True)
class DelegationExecution:
    task_id: str
    attempt_number: int
    status: ExecutionStatus
    started_at: str
    assignee_agent_id: str
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    finished_at: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    result_summary: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()
