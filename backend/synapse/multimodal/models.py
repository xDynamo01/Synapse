from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

CommunicationChannel = str
CommunicationSessionStatus = str

COMMUNICATION_CHANNELS: set[str] = {
    "text",
    "audio",
    "voice",
    "vision",
    "face",
    "body",
    "system",
    "screen",
    "camera",
}

COMMUNICATION_SESSION_STATUSES: set[str] = {
    "active",
    "paused",
    "closed",
    "failed",
}


@dataclass(frozen=True)
class SignalMetadata:
    confidence: float | None = None
    provider_id: str | None = None
    model_name: str | None = None
    latency_ms: int | None = None
    source_device: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommunicationEvent:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    channel: CommunicationChannel = "system"
    event_type: str = "event"
    source: str = "system"
    target: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    correlation_id: str | None = None
    causation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommunicationSession:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    participants: list[str] = field(default_factory=list)
    active_channels: list[CommunicationChannel] = field(default_factory=list)
    status: CommunicationSessionStatus = "active"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MultimodalObservation:
    source_observation_ids: list[str]
    time_window: dict[str, Any]
    interpretation: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    entities: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    confidence: float | None = None
    relevance: float | None = None
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    correlation_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
