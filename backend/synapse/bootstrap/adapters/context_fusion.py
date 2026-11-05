from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.context_fusion.contracts import (
    ConversationContextRead,
    DelegationTaskRead,
    MemoryContextRead,
    MissionRead,
    MissionSummaryRead,
    PerceptionObservationRead,
    PerceptionSignalRead,
)
from synapse.core.permissions import PermissionContext


class ConversationContextAdapter:
    def __init__(self, conversations: Any) -> None:
        self._conversations = conversations

    def participants(self, conversation_id: str) -> list[str]:
        return list(self._conversations.get_conversation(conversation_id).participants)

    def read(self, conversation_id: str) -> ConversationContextRead:
        payload = self._conversations.build_conversation_context(conversation_id)
        return ConversationContextRead(
            participants=list(payload.get("participants", [])),
            summary=payload.get("summary"),
            messages=list(payload.get("messages", [])),
        )

    def list_conversations(self) -> list[Any]:
        """Frozen Health compatibility; not part of the consumer port."""
        return self._conversations.list_conversations()


class MissionContextAdapter:
    def __init__(self, missions: Any, mission_context: Any, delegation: Any) -> None:
        self._missions = missions
        self._mission_context = mission_context
        self._delegation = delegation

    def get_mission(self, mission_id: str) -> MissionRead:
        mission = self._missions.get_mission(mission_id)
        return MissionRead(
            conversation_id=mission.conversation_id,
            owner_agent_id=mission.owner_agent_id,
            payload=asdict(mission),
        )

    def list_task_ids(self, mission_id: str) -> list[str]:
        return [item.task_id for item in self._missions.list_mission_tasks(mission_id)]

    def get_task(self, task_id: str) -> DelegationTaskRead:
        task = self._delegation.get_task(task_id)
        return DelegationTaskRead(
            requester_agent_id=task.requester_agent_id,
            assignee_agent_id=task.assignee_agent_id,
            status=task.status,
            payload=asdict(task),
        )

    def summarize(self, mission_id: str) -> MissionSummaryRead:
        summary = self._missions.summarize_mission(mission_id)
        context = self._mission_context.build_context(mission_id, emit_event=False)
        return MissionSummaryRead(
            summary=asdict(summary),
            context_summary=asdict(context.summary),
        )


class PerceptionContextAdapter:
    def __init__(self, perception: Any) -> None:
        self._perception = perception

    def list_signals(self) -> list[PerceptionSignalRead]:
        return [PerceptionSignalRead(**asdict(item)) for item in self._perception.list_signals()]

    def list_observations(
        self, *, conversation_id: str | None, session_id: str | None
    ) -> list[PerceptionObservationRead]:
        return [
            PerceptionObservationRead(
                id=item.id,
                content=str(item.description.get("summary", item.type)),
                type=item.type,
                confidence=item.confidence,
                relevance=item.relevance,
                provenance=list(item.provenance),
                sensitivity=item.sensitivity,
                valid_until=item.valid_until,
                warnings=list(item.warnings),
                signal_ids=list(item.signal_ids),
            )
            for item in self._perception.list_observations(
                conversation_id=conversation_id, session_id=session_id
            )
        ]


class MultimodalContextAdapter:
    def __init__(self, multimodal: Any) -> None:
        self._multimodal = multimodal

    def participants(self, session_id: str) -> list[str]:
        return list(self._multimodal.get_session(session_id).participants)


class MemoryContextAdapter:
    def __init__(self, memory: Any) -> None:
        self._memory = memory

    def retrieve(
        self,
        permission_context: PermissionContext,
        query: str,
        scopes: list[str],
        owner_ids: list[str],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryContextRead]:
        result = self._memory.retrieve_memory(
            permission_context, query, scopes, owner_ids=owner_ids, limit=limit, filters=filters
        )
        return [
            MemoryContextRead(
                id=item.id,
                scope=item.scope,
                content=item.content,
                importance=item.importance,
                confidence=item.confidence,
                revision=item.revision,
                source=item.source,
                tags=item.tags,
                metadata={**item.metadata, "workspace_id": item.workspace_id, "kind": item.kind,
                          "verified": item.verified, "supersedes": item.supersedes,
                          "provenance": item.provenance},
            )
            for item in result.records
        ]


class RuntimeStatusContextAdapter:
    def __init__(self, health: Any, readiness: Any) -> None:
        self._health = health
        self._readiness = readiness

    def health_summary(self) -> dict[str, Any]:
        return asdict(self._health.summary())

    def readiness_summary(self) -> dict[str, Any]:
        return asdict(self._readiness.evaluate())
