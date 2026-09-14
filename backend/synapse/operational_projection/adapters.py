"""Pure normalization of already-authorized operational source records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from .models import (
    OperationalEntity,
    OperationalEntityKind,
    OperationalFact,
    OperationalFactKind,
    OperationalStatus,
    ResourceSummary,
    SafeScalar,
    safe_metadata,
)


class SourceAdaptationDisposition(StrEnum):
    ADAPTED = "adapted"
    PROJECT_SCOPE_UNKNOWN = "project-scope-unknown"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class OperationalSourceRecord:
    event_id: str
    event_type: str
    actor_id: str
    occurred_at: str
    project_id: str | None
    payload: Mapping[str, object]
    source_reference: str
    correlation_reference: str | None = None


@dataclass(frozen=True, slots=True)
class SourceAdaptationResult:
    disposition: SourceAdaptationDisposition
    fact: OperationalFact | None = None
    reason: str | None = None


_PREFIX_KIND = {
    "agent": OperationalEntityKind.AGENT,
    "worker": OperationalEntityKind.WORKER,
    "swarm": OperationalEntityKind.SWARM,
    "mission": OperationalEntityKind.MISSION,
    "task": OperationalEntityKind.TASK,
    "tool": OperationalEntityKind.TOOL_EXECUTION,
    "memory": OperationalEntityKind.MEMORY_SOURCE,
    "context": OperationalEntityKind.CONTEXT_SOURCE,
    "context_fusion": OperationalEntityKind.CONTEXT_SOURCE,
    "approval": OperationalEntityKind.APPROVAL,
    "eval": OperationalEntityKind.EVALUATION,
    "voice": OperationalEntityKind.VOICE_SESSION,
    "runtime": OperationalEntityKind.RUNTIME,
    "chat": OperationalEntityKind.AGENT,
    "conversation": OperationalEntityKind.TASK,
    "message": OperationalEntityKind.AGENT,
    "presence": OperationalEntityKind.AGENT,
    "lmstudio": OperationalEntityKind.RUNTIME,
    "context_build_started": OperationalEntityKind.CONTEXT_SOURCE,
}
_ID_KEYS = {
    OperationalEntityKind.AGENT: ("agent_id",),
    OperationalEntityKind.WORKER: ("worker_id", "agent_id"),
    OperationalEntityKind.SWARM: ("swarm_id",),
    OperationalEntityKind.MISSION: ("mission_id",),
    OperationalEntityKind.TASK: ("task_id",),
    OperationalEntityKind.TOOL_EXECUTION: ("call_id", "tool_call_id", "tool"),
    OperationalEntityKind.MEMORY_SOURCE: ("memory_id", "record_id"),
    OperationalEntityKind.CONTEXT_SOURCE: ("context_id", "snapshot_id"),
    OperationalEntityKind.APPROVAL: ("approval_id", "request_id"),
    OperationalEntityKind.EVALUATION: ("run_id", "evaluation_id"),
    OperationalEntityKind.VOICE_SESSION: ("voice_session_id", "session_id"),
    OperationalEntityKind.RUNTIME: ("runtime_id", "model_name", "provider_id"),
}
_SAFE_METADATA_KEYS = {
    "attempt",
    "capability_status",
    "file_count",
    "finish_reason",
    "input_count",
    "latency_ms",
    "memory_count",
    "model_name",
    "output_count",
    "output_rate",
    "phase",
    "provider",
    "provider_id",
    "result_count",
    "first_output_ms",
    "status_code",
    "tool",
    "total_count",
    "worker_count",
}


def adapt_source_record(record: OperationalSourceRecord, revision: int) -> SourceAdaptationResult:
    if record.project_id is None or not record.project_id.strip():
        return SourceAdaptationResult(
            SourceAdaptationDisposition.PROJECT_SCOPE_UNKNOWN,
            reason="source record has no canonical project scope",
        )
    prefix = record.event_type.split(".", 1)[0]
    kind = _PREFIX_KIND.get(prefix)
    if record.event_type == "chat.response_generated":
        kind = OperationalEntityKind.RUNTIME
    if prefix == "local_chat":
        # Conversation-scoped chat events are factual operational activity.
        # Provider-bearing events represent the selected model runtime; the
        # remaining lifecycle events represent the participating primary agent.
        kind = OperationalEntityKind.RUNTIME if record.payload.get("provider_id") else OperationalEntityKind.AGENT
    if kind is None:
        return SourceAdaptationResult(
            SourceAdaptationDisposition.UNSUPPORTED,
            reason="source event type is not mapped",
        )
    entity_id = _entity_id(kind, record)
    if entity_id is None:
        return SourceAdaptationResult(
            SourceAdaptationDisposition.INVALID,
            reason="source event has no stable entity identity",
        )
    status = _status(record.event_type, record.payload)
    metadata = dict(_metadata(record.payload))
    # Direction comes from existing chat lifecycle events, not visual node placement.
    # Other phases (including failures) must not masquerade as a delivered response.
    if record.event_type in {"local_chat.thinking", "local_chat.completed"}:
        parent_id = _parent_entity_id(kind, record)
        runtime_id = f"{kind.value}:{entity_id}"
        if kind is OperationalEntityKind.RUNTIME and parent_id and len(runtime_id) <= 256 and len(parent_id) <= 256:
            outgoing = record.event_type == "local_chat.thinking"
            metadata.update({
                "transfer_source": parent_id if outgoing else runtime_id,
                "transfer_target": runtime_id if outgoing else parent_id,
                "transfer_kind": "request" if outgoing else "response",
            })
    metadata = dict(safe_metadata(metadata))
    entity = OperationalEntity(
        entity_id=f"{kind.value}:{entity_id}",
        kind=kind,
        role=_text(record.payload.get("role"), prefix),
        status=status,
        label=_text(record.payload.get("label") or record.payload.get("name"), entity_id),
        current_task=_optional_text(record.payload.get("current_task")),
        current_operation=_optional_text(record.payload.get("current_operation") or record.payload.get("activity") or record.event_type),
        started_at=_optional_text(record.payload.get("started_at")),
        parent_entity_id=_parent_entity_id(kind, record),
        mission_id=_optional_text(record.payload.get("mission_id")),
        resources=ResourceSummary(
            files=_count(record.payload.get("file_count")),
            memories=_count(record.payload.get("memory_count")),
            tool_results=_count(record.payload.get("result_count")),
        ),
        metadata=metadata,
    )
    return SourceAdaptationResult(
        SourceAdaptationDisposition.ADAPTED,
        OperationalFact(
            event_id=record.event_id,
            project_id=record.project_id,
            revision=revision,
            occurred_at=record.occurred_at,
            kind=OperationalFactKind.UPSERT_ENTITY,
            source_reference=record.source_reference,
            entity=entity,
            correlation_reference=record.correlation_reference,
            metadata=metadata,
        ),
    )


def _entity_id(
    kind: OperationalEntityKind, record: OperationalSourceRecord
) -> str | None:
    if record.event_type == "chat.response_generated":
        model_id = _chat_model_id(record.payload)
        if model_id is not None:
            return model_id
    if kind is OperationalEntityKind.RUNTIME:
        model_id = _chat_model_id(record.payload)
        if model_id is not None:
            return model_id
    if record.event_type == "message.sent":
        role = _optional_text(record.payload.get("role"))
        if role == "assistant":
            return _optional_text(record.payload.get("sender_agent_id"))
        if role == "user":
            return _optional_text(record.payload.get("receiver_agent_id"))
    if kind is OperationalEntityKind.TASK:
        return _optional_text(record.payload.get("conversation_id"))
    for key in _ID_KEYS[kind]:
        value = _optional_text(record.payload.get(key))
        if value is not None:
            return value
    return record.actor_id if record.actor_id.strip() else None


def _status(event_type: str, payload: Mapping[str, object]) -> OperationalStatus:
    raw = _optional_text(payload.get("status") or payload.get("state"))
    candidate = (raw or event_type.rsplit(".", 1)[-1]).replace("_", "-")
    aliases = {
        "started": OperationalStatus.RUNNING,
        "spawned": OperationalStatus.RUNNING,
        "created": OperationalStatus.IDLE,
        "succeeded": OperationalStatus.COMPLETED,
        "thinking": OperationalStatus.PROCESSING,
        "received": OperationalStatus.LISTENING,
        "generated": OperationalStatus.COMPLETED,
        "response-generated": OperationalStatus.COMPLETED,
        "sent": OperationalStatus.COMPLETED,
        "approved": OperationalStatus.COMPLETED,
        "requested": OperationalStatus.APPROVAL_NEEDED,
        "rejected": OperationalStatus.FAILED,
        "error": OperationalStatus.FAILED,
    }
    try:
        return OperationalStatus(candidate)
    except ValueError:
        return aliases.get(candidate, OperationalStatus.UNKNOWN)


def _metadata(payload: Mapping[str, object]) -> Mapping[str, SafeScalar]:
    selected = {
        key: value
        for key, value in payload.items()
        if key in _SAFE_METADATA_KEYS and isinstance(value, (str, int, float, bool, type(None)))
    }
    return safe_metadata(selected)


def _chat_model_id(payload: Mapping[str, object]) -> str | None:
    model = payload.get("model")
    if isinstance(model, Mapping):
        provider = _optional_text(model.get("provider"))
        model_name = _optional_text(model.get("model"))
        if provider and model_name:
            return f"{provider}:{model_name}"
        return model_name or provider
    provider = _optional_text(payload.get("provider_id"))
    model_name = _optional_text(payload.get("model_name"))
    if provider and model_name:
        return f"{provider}:{model_name}"
    return model_name or provider


def _parent_entity_id(kind: OperationalEntityKind, record: OperationalSourceRecord) -> str | None:
    explicit = _optional_text(record.payload.get("parent_entity_id"))
    if explicit is not None:
        return explicit
    if kind is OperationalEntityKind.RUNTIME:
        agent_id = _optional_text(record.payload.get("agent_id"))
        return (agent_id if agent_id.startswith("agent:") else f"agent:{agent_id}") if agent_id else None
    return None


def _text(value: object, default: str) -> str:
    return _optional_text(value) or default


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value[:256]


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
