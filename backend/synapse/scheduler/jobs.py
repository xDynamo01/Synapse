from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

JOB_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}


@dataclass(frozen=True)
class Job:
    type: str
    payload: dict[str, Any]
    status: str = "pending"
    priority: int = 100
    attempts: int = 0
    max_attempts: int = 3
    scheduled_for: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    failed_reason: str | None = None
    correlation_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def is_due(self, now: datetime | None = None) -> bool:
        if not self.scheduled_for:
            return True
        due_at = datetime.fromisoformat(self.scheduled_for)
        return due_at <= (now or datetime.now(UTC))

    def with_updates(self, **updates: Any) -> "Job":
        payload = {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "status": self.status,
            "priority": self.priority,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at,
            "updated_at": datetime.now(UTC).isoformat(),
            "scheduled_for": self.scheduled_for,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "failed_reason": self.failed_reason,
            "correlation_id": self.correlation_id,
        }
        payload.update(updates)
        return Job(**payload)
