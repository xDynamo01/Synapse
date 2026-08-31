from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from synapse.context_fusion.contracts import PerceptionSignalRead


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class InteractionContext:
    context_id: str = field(default_factory=lambda: str(uuid4()))
    conversation_id: str | None = None
    multimodal_session_id: str | None = None
    mission_id: str | None = None
    participants: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextSignalGroup:
    speech_signals: list[PerceptionSignalRead] = field(default_factory=list)
    voice_signals: list[PerceptionSignalRead] = field(default_factory=list)
    face_signals: list[PerceptionSignalRead] = field(default_factory=list)
    body_signals: list[PerceptionSignalRead] = field(default_factory=list)
    system_signals: list[PerceptionSignalRead] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextSnapshot:
    interaction_context: InteractionContext
    latest_conversation_summary: dict[str, Any] | None = None
    latest_messages: list[dict[str, Any]] = field(default_factory=list)
    signal_group: ContextSignalGroup = field(default_factory=ContextSignalGroup)
    speech_features: list[dict[str, Any]] = field(default_factory=list)
    mission_summary: dict[str, Any] | None = None
    delegation_summary: dict[str, Any] | None = None
    health_summary: dict[str, Any] | None = None
    readiness_summary: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextConsistency:
    complete: bool
    missing_sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextItem:
    id: str
    source_type: str
    source_id: str
    scope: str
    content: str
    priority: int
    estimated_tokens: int
    confidence: float | None = None
    timestamp: str | None = None
    mandatory: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    information_owner: str = "user-owned"
    classification: str = "internal"
    categories: tuple[str, ...] = ()
    training_use_policy: str = "prohibited"


@dataclass(frozen=True)
class ContextFusionResult:
    snapshot: ContextSnapshot
    consistency: ContextConsistency
    items: list[ContextItem] = field(default_factory=list)
    rendered_context: str = ""
    total_estimated_tokens: int = 0
    budget: int = 4096
    omitted_items: list[ContextItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    generated_at: str = field(default_factory=now_iso)
