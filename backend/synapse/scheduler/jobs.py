from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

JOB_STATUSES = {"pending", "paused", "running", "completed", "failed", "cancelled"}
RECURRING_JOB_TYPES = {
    "notification_cleanup",
    "process_agent_inbox",
    "process_agent_delegations",
    "agent_admin_request_cleanup",
    "retention_cleanup_domain",
    "delegation_inbox_rebuild",
    "delegation_timeout_scan",
    "dead_letter_review_scan",
    "mission_dispatch",
    "agent_loop_cycle",
}


@dataclass(frozen=True)
class Job:
    type: str
    payload: dict[str, Any]
    schema_version: int = 1
    record_type: str = "job"
    status: str = "pending"
    priority: int = 100
    attempts: int = 0
    max_attempts: int = 3
    scheduled_for: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    failed_reason: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    parent_id: str | None = None
    source: str | None = None
    target: str | None = None
    schedule: str = "one_shot"
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_result: dict[str, Any] | None = None
    retry_policy: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    misfire_policy: str = "run_once"
    revision: int = 1
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def is_due(self, now: datetime | None = None) -> bool:
        if not self.scheduled_for:
            return True
        due_at = datetime.fromisoformat(self.scheduled_for)
        return due_at <= (now or datetime.now(UTC))

    def with_updates(self, **updates: Any) -> "Job":
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "schema_version": self.schema_version,
            "record_type": self.record_type,
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
            "causation_id": self.causation_id,
            "parent_id": self.parent_id,
            "source": self.source,
            "target": self.target,
            "schedule": self.schedule,
            "next_run_at": self.next_run_at,
            "last_run_at": self.last_run_at,
            "last_result": self.last_result,
            "retry_policy": self.retry_policy,
            "idempotency_key": self.idempotency_key,
            "misfire_policy": self.misfire_policy,
            "revision": self.revision + 1,
        }
        payload.update(updates)
        return Job(**payload)


@dataclass(frozen=True)
class RecurringJobDefinition:
    id: str
    type: str
    payload: dict[str, Any]
    interval_minutes: int
    enabled: bool = True
    priority: int = 100
    max_attempts: int = 3
    last_run_at: str | None = None
    next_run_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def is_due(self, now: datetime | None = None) -> bool:
        if not self.enabled:
            return False
        if not self.next_run_at:
            return True
        return datetime.fromisoformat(self.next_run_at) <= (now or datetime.now(UTC))

    def with_updates(self, **updates: Any) -> "RecurringJobDefinition":
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "interval_minutes": self.interval_minutes,
            "enabled": self.enabled,
            "priority": self.priority,
            "max_attempts": self.max_attempts,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "created_at": self.created_at,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        payload.update(updates)
        return RecurringJobDefinition(**payload)
