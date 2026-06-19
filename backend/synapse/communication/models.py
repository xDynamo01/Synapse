from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

EMAIL_CATEGORIES = {
    "recruitment",
    "project",
    "personal",
    "newsletter",
    "system",
    "unknown",
}

DRAFT_STATUSES = {"draft", "approved", "sent_future", "cancelled"}


@dataclass(frozen=True)
class EmailMessage:
    id: str
    provider: str
    subject: str
    sender: str
    recipients: list[str]
    received_at: str
    body: str
    thread_id: str | None = None
    summary: str | None = None
    labels: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None


@dataclass(frozen=True)
class DraftMessage:
    provider: str
    subject: str
    recipients: list[str]
    body: str
    created_by_agent: str
    status: str = "draft"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    correlation_id: str | None = None


@dataclass(frozen=True)
class CommunicationBriefing:
    provider: str
    agent_id: str
    total_messages: int
    categories: dict[str, int]
    important: list[str]
    low_priority: list[str]
    summary: str
    correlation_id: str | None = None
