"""Client-neutral operational projection contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

SNAPSHOT_FORMAT_V1 = "project-activity-snapshot-v1"
EVENT_FORMAT_V1 = "project-activity-event-v1"


class OperationalEntityKind(StrEnum):
    PROJECT = "project"
    AGENT = "agent"
    WORKER = "worker"
    SWARM = "swarm"
    MISSION = "mission"
    TASK = "task"
    TOOL_EXECUTION = "tool-execution"
    MEMORY_SOURCE = "memory-source"
    CONTEXT_SOURCE = "context-source"
    COMMUNICATION = "communication"
    APPROVAL = "approval"
    EVALUATION = "evaluation"
    RUNTIME = "runtime"
    VOICE_SESSION = "voice-session"


class OperationalStatus(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    APPROVAL_NEEDED = "approval-needed"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class OperationalRelationKind(StrEnum):
    PARENT = "parent"
    DELEGATION = "delegation"
    COMMUNICATION = "communication"
    TOOL_USE = "tool-use"
    CONTEXT_USE = "context-use"
    EVALUATION = "evaluation"


class OperationalFactKind(StrEnum):
    UPSERT_ENTITY = "upsert-entity"
    REMOVE_ENTITY = "remove-entity"
    UPSERT_RELATION = "upsert-relation"
    REMOVE_RELATION = "remove-relation"
    MARK_DEGRADED = "mark-degraded"
    CLEAR_DEGRADED = "clear-degraded"


SafeScalar = str | int | float | bool | None
SafeMetadata = Mapping[str, SafeScalar]


@dataclass(frozen=True, slots=True)
class ResourceSummary:
    files: int = 0
    memories: int = 0
    tool_results: int = 0

    def __post_init__(self) -> None:
        if min(self.files, self.memories, self.tool_results) < 0:
            raise ValueError("resource counts cannot be negative")


@dataclass(frozen=True, slots=True)
class OperationalEntity:
    entity_id: str
    kind: OperationalEntityKind
    role: str
    status: OperationalStatus
    label: str
    current_task: str | None = None
    current_operation: str | None = None
    started_at: str | None = None
    parent_entity_id: str | None = None
    mission_id: str | None = None
    resources: ResourceSummary = field(default_factory=ResourceSummary)
    metadata: SafeMetadata = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        _required("entity_id", self.entity_id)
        _required("role", self.role)
        _required("label", self.label)
        if self.started_at is not None:
            _timestamp(self.started_at)
        object.__setattr__(self, "metadata", safe_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class OperationalRelation:
    relation_id: str
    source_entity_id: str
    target_entity_id: str
    kind: OperationalRelationKind
    active: bool = True

    def __post_init__(self) -> None:
        _required("relation_id", self.relation_id)
        _required("source_entity_id", self.source_entity_id)
        _required("target_entity_id", self.target_entity_id)


@dataclass(frozen=True, slots=True)
class OperationalFact:
    event_id: str
    project_id: str
    revision: int
    occurred_at: str
    kind: OperationalFactKind
    source_reference: str
    entity: OperationalEntity | None = None
    entity_id: str | None = None
    relation: OperationalRelation | None = None
    relation_id: str | None = None
    degradation_reason: str | None = None
    correlation_reference: str | None = None
    metadata: SafeMetadata = field(default_factory=lambda: MappingProxyType({}))
    format_version: str = EVENT_FORMAT_V1

    def __post_init__(self) -> None:
        for name, value in (
            ("event_id", self.event_id),
            ("project_id", self.project_id),
            ("source_reference", self.source_reference),
        ):
            _required(name, value)
        if self.revision < 1:
            raise ValueError("revision must be positive")
        _timestamp(self.occurred_at)
        if self.format_version != EVENT_FORMAT_V1:
            raise ValueError("unsupported operational event format")
        object.__setattr__(self, "metadata", safe_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class ProjectActivitySnapshot:
    project_id: str
    revision: int
    observed_at: str
    entities: tuple[OperationalEntity, ...]
    relations: tuple[OperationalRelation, ...]
    degraded: bool
    degradation_reasons: tuple[str, ...]
    last_event_id: str | None
    format_version: str = SNAPSHOT_FORMAT_V1


def safe_metadata(values: Mapping[str, SafeScalar]) -> SafeMetadata:
    forbidden = {"chain_of_thought", "prompt", "secret", "token", "password", "content"}
    normalized: dict[str, SafeScalar] = {}
    for key, value in values.items():
        lowered = key.casefold()
        if any(fragment in lowered for fragment in forbidden):
            raise ValueError("sensitive operational metadata key")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError("operational metadata must be scalar")
        if isinstance(value, str) and len(value) > 256:
            raise ValueError("operational metadata value is too long")
        normalized[key] = value
    return MappingProxyType(dict(sorted(normalized.items())))


def _required(name: str, value: str) -> None:
    if not value.strip() or len(value) > 256:
        raise ValueError(f"{name} must be a bounded non-empty string")


def _timestamp(value: str) -> None:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
