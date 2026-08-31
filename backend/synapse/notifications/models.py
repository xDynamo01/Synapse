from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

NOTIFICATION_SEVERITIES = {"info", "success", "warning", "critical"}
NOTIFICATION_CATEGORIES = {
    "approval",
    "communication",
    "agent",
    "scheduler",
    "daemon",
    "system",
    "task",
    "security",
    "unknown",
}


@dataclass(frozen=True)
class Notification:
    title: str
    message: str
    severity: str
    source: str
    category: str
    schema_version: int = 1
    record_type: str = "notification"
    read: bool = False
    read_at: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class NotificationCleanupResult:
    scanned: int
    deleted: int
    preserved_unread: int
    preserved_critical: int
    preserved_recent: int
    max_total_deleted: int
    retention_deleted: int
    remaining: int
    policy: dict[str, Any]
