from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DelegationInboxEntry:
    task_id: str
    status: str
    priority: str
    requester_agent_id: str
    assignee_agent_id: str
    created_at: str
    updated_at: str
    conversation_id: str | None = None


@dataclass(frozen=True)
class DelegationInboxSummary:
    agent_id: str
    pending_count: int = 0
    accepted_count: int = 0
    in_progress_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    total_count: int = 0
    metadata: dict[str, int] = field(default_factory=dict)
