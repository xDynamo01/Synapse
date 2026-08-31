from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from synapse.core.permissions import PermissionContext


@dataclass(frozen=True)
class ContextFusionSettings:
    snapshot_root: Path
    source_timeout_seconds: float = 5.0


@dataclass(frozen=True)
class ConversationContextRead:
    participants: list[str]
    summary: dict[str, Any] | None
    messages: list[dict[str, Any]]


@dataclass(frozen=True)
class MissionRead:
    conversation_id: str | None
    owner_agent_id: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class MissionSummaryRead:
    summary: dict[str, Any]
    context_summary: dict[str, Any]


@dataclass(frozen=True)
class DelegationTaskRead:
    requester_agent_id: str
    assignee_agent_id: str
    status: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class PerceptionSignalRead:
    type: str
    modality: str
    source: str
    values: dict[str, Any]
    id: str
    timestamp: str
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
    artifact_kind: str | None = None
    retention_class: str = "policy_persistable"
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
    def signal_type(self) -> str:
        return self.type

    @property
    def payload(self) -> dict[str, Any]:
        return self.values

    @property
    def multimodal_session_id(self) -> str | None:
        value = self.metadata.get("multimodal_session_id")
        return str(value) if value else None


@dataclass(frozen=True)
class PerceptionObservationRead:
    id: str
    content: str
    type: str
    confidence: float | None
    relevance: float | None
    provenance: list[dict[str, Any]]
    sensitivity: str
    valid_until: str | None
    warnings: list[str]
    signal_ids: list[str]


@dataclass(frozen=True)
class MemoryContextRead:
    id: str
    scope: str
    content: str
    importance: int
    confidence: float | None
    revision: int
    source: str


class ConversationContextReader(Protocol):
    def participants(self, conversation_id: str) -> list[str]: ...
    def read(self, conversation_id: str) -> ConversationContextRead: ...


class MissionContextReader(Protocol):
    def get_mission(self, mission_id: str) -> MissionRead: ...
    def list_task_ids(self, mission_id: str) -> list[str]: ...
    def get_task(self, task_id: str) -> DelegationTaskRead: ...
    def summarize(self, mission_id: str) -> MissionSummaryRead: ...


class PerceptionContextReader(Protocol):
    def list_signals(self) -> list[PerceptionSignalRead]: ...
    def list_observations(
        self, *, conversation_id: str | None, session_id: str | None
    ) -> list[PerceptionObservationRead]: ...


class MultimodalContextReader(Protocol):
    def participants(self, session_id: str) -> list[str]: ...


class MemoryContextReader(Protocol):
    def retrieve(
        self,
        permission_context: PermissionContext,
        scopes: list[str],
        owner_ids: list[str],
        limit: int,
    ) -> list[MemoryContextRead]: ...


class RuntimeStatusContextReader(Protocol):
    def health_summary(self) -> dict[str, Any]: ...
    def readiness_summary(self) -> dict[str, Any]: ...
