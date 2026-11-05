from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

MEMORY_SCOPES = {
    "system",
    "user",
    "agent",
    "conversation",
    "session",
    "task",
    "mission",
    "knowledge",
    "workspace",
    "episodic",
    "working",
}
MEMORY_STATUSES = {"active", "expired", "deleted", "superseded", "invalidated"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, kw_only=True)
class MemoryRecord:
    scope: str
    owner_id: str
    source: str
    content: str
    id: str = field(default_factory=lambda: str(uuid4()))
    content_type: str = "text/plain"
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    expires_at: str | None = None
    confidence: float | None = None
    importance: int = 50
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    revision: int = 1
    status: str = "active"
    information_owner: str = "user-owned"
    classification: str = "internal"
    categories: list[str] = field(default_factory=lambda: ["memory.user"])
    allowed_processing: list[str] = field(default_factory=lambda: ["local"])
    training_use_policy: str = "prohibited"
    provenance: dict[str, Any] = field(default_factory=dict)
    project_id: str | None = None
    rfc_id: str | None = None
    workspace_id: str | None = None
    kind: str = "fact"
    supersedes: str | None = None
    verified: bool = False


@dataclass(frozen=True)
class MemoryQuery:
    query: str
    scopes: list[str]
    owner_ids: list[str] | None = None
    limit: int = 20
    filters: dict[str, Any] = field(default_factory=dict)
    budget: int | None = None


@dataclass(frozen=True)
class MemoryRetrievalResult:
    records: list[MemoryRecord]
    total: int
    estimated_tokens: int
    strategy: str = "text_tags_recency_importance"


@dataclass(frozen=True)
class WorkingMemory(MemoryRecord):
    scope: str = "session"


@dataclass(frozen=True)
class ConversationMemory(MemoryRecord):
    scope: str = "conversation"


@dataclass(frozen=True)
class AgentMemory(MemoryRecord):
    scope: str = "agent"


@dataclass(frozen=True)
class UserMemory(MemoryRecord):
    scope: str = "user"


@dataclass(frozen=True)
class SystemMemory(MemoryRecord):
    scope: str = "system"


@dataclass(frozen=True)
class KnowledgeMemory(MemoryRecord):
    scope: str = "knowledge"


@dataclass(frozen=True)
class TaskOrMissionMemory(MemoryRecord):
    scope: str = "task"


@dataclass(frozen=True)
class PerceptionMemory(MemoryRecord):
    scope: str = "session"


@dataclass(frozen=True)
class FileContextReference:
    id: str
    storage_ref: str
    checksum: str
    content_type: str
    owner_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
