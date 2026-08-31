from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


ATTENTION_STATUSES = {
    "pending",
    "acknowledged",
    "suppressed",
    "deferred",
    "processing",
    "resolved",
    "expired",
    "failed",
}
SEVERITIES = {"informational", "low", "medium", "high", "critical"}
DISPOSITIONS = {
    "ignore",
    "record_only",
    "notify",
    "suggest",
    "ask_user",
    "respond",
    "execute_reversible_action",
    "start_mission",
    "require_approval",
    "defer",
    "escalate",
}
PROACTIVE_MODES = {"off", "observe", "suggest", "assist", "autonomous_limited"}


@dataclass(frozen=True)
class AttentionEvent:
    type: str
    title: str
    summary: str
    source: str
    severity: str = "informational"
    urgency: float = 0.0
    confidence: float = 1.0
    entity_refs: list[dict[str, str]] = field(default_factory=list)
    suggested_dispositions: list[str] = field(default_factory=list)
    expires_at: str | None = None
    correlation_id: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class AttentionItem:
    type: str
    source_event_ids: list[str]
    entity_refs: list[dict[str, str]]
    title: str
    summary: str
    severity: str
    urgency: float
    relevance: float
    confidence: float
    created_at: str
    expires_at: str | None = None
    status: str = "pending"
    suggested_dispositions: list[str] = field(default_factory=list)
    policy_context: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    updated_at: str = field(default_factory=now_iso)
    deduplication_key: str | None = None
    occurrence_count: int = 1
    suppression_reason: str | None = None
    deferred_until: str | None = None


@dataclass(frozen=True)
class AttentionScoreResult:
    score: float
    factors: dict[str, float]
    thresholds: dict[str, float]
    disposition_recommendation: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Decision:
    attention_item_id: str
    disposition: str
    reason: str
    policy_result: dict[str, Any]
    autonomy_level: str
    risk: str
    selected_agent: str | None = None
    selected_action: dict[str, Any] | None = None
    approval_required: bool = False
    created_at: str = field(default_factory=now_iso)
    expires_at: str | None = None
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))


def attention_item_from_dict(raw: dict[str, Any]) -> AttentionItem:
    allowed = AttentionItem.__dataclass_fields__
    return AttentionItem(**{key: value for key, value in raw.items() if key in allowed})
