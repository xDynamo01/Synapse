from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

MODALITIES = {
    "audio",
    "speech",
    "vision",
    "screen",
    "camera",
    "system",
    "interaction",
    "multimodal",
}
SENSITIVITY_LEVELS = {"public", "internal", "sensitive", "restricted"}
SignalType = str


class PerceptionArtifactKind(StrEnum):
    RAW_OBSERVATION = "raw_observation"
    DERIVED_FEATURE = "derived_feature"
    MODEL_INFERENCE = "model_inference"
    CONTEXTUAL_INTERPRETATION = "contextual_interpretation"


class RetentionClass(StrEnum):
    TRANSIENT_ONLY = "transient_only"
    POLICY_PERSISTABLE = "policy_persistable"
    RAW_MEDIA_EXPLICIT_ONLY = "raw_media_explicit_only"


class PerceptionBundleStatus(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    NOT_REQUESTED = "not_requested"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class PerceptionSignal:
    type: str
    modality: str
    source: str
    values: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=now_iso)
    session_id: str | None = None
    conversation_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    confidence: float | None = None
    provenance: list[dict[str, Any]] = field(default_factory=list)
    sensitivity: str = "internal"
    expires_at: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    artifact_kind: PerceptionArtifactKind | None = None
    retention_class: RetentionClass = RetentionClass.POLICY_PERSISTABLE
    source_identity: str | None = None
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    occurrence_started_at: str | None = None
    occurrence_ended_at: str | None = None
    input_references: list[str] = field(default_factory=list)
    lineage: list[str] = field(default_factory=list)
    policy_version: str | None = None
    external_processing: bool = False
    external_interpretation_owner: str | None = None
    external_interpretation_reference: str | None = None

    @property
    def signal_id(self) -> str:
        return self.id

    @property
    def signal_type(self) -> str:
        return self.type

    @property
    def source_runtime(self) -> str:
        return self.source

    @property
    def payload(self) -> dict[str, Any]:
        return self.values

    @property
    def source_provider(self) -> str | None:
        for item in self.provenance:
            if item.get("provider"):
                return str(item["provider"])
        return None

    @property
    def multimodal_session_id(self) -> str | None:
        value = self.metadata.get("multimodal_session_id")
        return str(value) if value else None


@dataclass(frozen=True)
class PerceptionObservation:
    type: str
    description: dict[str, Any]
    signal_ids: list[str]
    id: str = field(default_factory=lambda: str(uuid4()))
    entities: list[dict[str, Any]] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    relevance: float | None = None
    timestamp: str = field(default_factory=now_iso)
    valid_until: str | None = None
    provenance: list[dict[str, Any]] = field(default_factory=list)
    sensitivity: str = "internal"
    warnings: list[str] = field(default_factory=list)
    correlation_id: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    artifact_kind: PerceptionArtifactKind | None = None
    retention_class: RetentionClass = RetentionClass.POLICY_PERSISTABLE
    input_references: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PerceptionConflict:
    observation_ids: list[str]
    reason: str
    id: str = field(default_factory=lambda: str(uuid4()))
    detected_at: str = field(default_factory=now_iso)
    attributes: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    correlation_id: str | None = None


@dataclass(frozen=True)
class PerceptionBatch:
    batch_id: str = field(default_factory=lambda: str(uuid4()))
    session_id: str | None = None
    signals: list[PerceptionSignal] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignalSummary:
    total_signals: int
    by_type: dict[str, int] = field(default_factory=dict)
    average_confidence: float | None = None
    sources: list[str] = field(default_factory=list)
    observation_count: int = 0
    expired_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CleanupResult:
    dry_run: bool
    expired_signals: int
    expired_observations: int
    raw_assets: int
    deleted: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VoicePerceptionRequest:
    request_id: str
    voice_session_id: str
    utterance_id: str
    transcription_id: str
    audio_checksum_reference: str
    correlation_reference: str
    occurrence_started_at: str
    occurrence_ended_at: str
    actor_reference: str
    transcript_reference: str | None = None
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class PerceptionArtifactReference:
    artifact_id: str
    artifact_kind: PerceptionArtifactKind
    type: str
    provider: str | None
    model: str | None
    model_version: str | None
    confidence: float | None
    occurrence_started_at: str | None
    occurrence_ended_at: str | None
    lineage: tuple[str, ...]
    sensitivity: str
    retention_class: RetentionClass


@dataclass(frozen=True)
class PerceptionResultBundle:
    bundle_id: str
    fingerprint: str
    status: PerceptionBundleStatus
    voice_session_id: str
    utterance_id: str
    transcription_id: str
    correlation_reference: str
    artifact_references: tuple[PerceptionArtifactReference, ...]
    provenance: tuple[str, ...]
    sensitivity: str
    created_at: str = field(default_factory=now_iso)
    missing_capabilities: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
