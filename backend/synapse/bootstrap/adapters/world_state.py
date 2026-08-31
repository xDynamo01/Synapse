from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TypedDict

from synapse.attention.models import AttentionEvent
from synapse.attention.runtime import AttentionRuntime
from synapse.core.events import Event
from synapse.world_state.models import WorldStateSnapshot, WorldStateUpdate
from synapse.world_state.runtime import WorldStateRuntime


class _WorldStateCommonFields(TypedDict):
    id: str
    source: str
    timestamp: str
    correlation_id: str | None
    provenance: dict[str, str]


class WorldStateReadAdapter:
    def __init__(self, world_state: WorldStateRuntime) -> None:
        self._world_state = world_state

    def snapshot(self) -> WorldStateSnapshot:
        return self._world_state.snapshot()


class RuntimeEventStateAdapter:
    """Project neutral runtime events into World State and Attention."""

    _ignored_prefixes = ("world_state.", "attention.", "decision.", "loop.", "notification.")

    def __init__(self, world_state: WorldStateRuntime, attention: AttentionRuntime) -> None:
        self.world_state = world_state
        self.attention = attention

    def handle_event(self, event: Event) -> None:
        if event.type.startswith(self._ignored_prefixes):
            return
        try:
            update = self._state_update(event)
            if update:
                self.world_state.apply_state_update(update)
            attention = self._attention_event(event)
            if attention:
                self.attention.ingest_event(attention)
        except Exception:
            # A projection must never break the authoritative source runtime.
            return

    def _state_update(self, event: Event) -> WorldStateUpdate | None:
        payload = event.payload
        common: _WorldStateCommonFields = {
            "id": f"state:{event.id}",
            "source": event.source_module,
            "timestamp": event.timestamp,
            "correlation_id": event.correlation_id,
            "provenance": {"event_id": event.id, "event_type": event.type},
        }
        if event.type == "agent.lifecycle_changed":
            agent_id = str(payload.get("agent_id") or event.actor_id)
            return WorldStateUpdate(
                **common,
                entity_type="agents",
                entity_id=agent_id,
                operation="merge",
                values={
                    "agent_id": agent_id,
                    "lifecycle": payload.get("state", "unknown"),
                    "last_activity": event.timestamp,
                },
            )
        if event.type == "agent.presence_changed":
            agent_id = str(payload.get("agent_id") or event.actor_id)
            return WorldStateUpdate(
                **common,
                entity_type="agents",
                entity_id=agent_id,
                operation="merge",
                values={
                    "agent_id": agent_id,
                    "presence": payload.get("state", "unknown"),
                    "busy": payload.get("state") in {"working", "thinking", "speaking"},
                    "last_activity": event.timestamp,
                },
            )
        if event.type.startswith("mission.") and event.type in {
            "mission.created",
            "mission.updated",
            "mission.archived",
        }:
            mission_id = str(payload.get("mission_id") or payload.get("id") or "")
            if mission_id:
                return WorldStateUpdate(
                    **common,
                    entity_type="missions",
                    entity_id=mission_id,
                    operation="merge",
                    values={
                        "mission_id": mission_id,
                        "status": payload.get("status"),
                        "priority": payload.get("priority"),
                        "progress": payload.get("progress"),
                        "owner_agent_id": payload.get("owner_agent_id"),
                        "updated_at": event.timestamp,
                    },
                )
        if event.type.startswith("conversation."):
            conversation_id = str(payload.get("conversation_id") or payload.get("id") or "")
            if conversation_id:
                return WorldStateUpdate(
                    **common,
                    entity_type="conversations",
                    entity_id=conversation_id,
                    operation="merge",
                    values={
                        "conversation_id": conversation_id,
                        "status": payload.get("status"),
                        "updated_at": event.timestamp,
                    },
                )
        if event.type == "health.checked":
            return WorldStateUpdate(
                **common,
                entity_type="system_state",
                operation="merge",
                values={
                    "health": payload.get("status", "unknown"),
                    "health_checked_at": event.timestamp,
                },
            )
        if event.type == "daemon.tick":
            return WorldStateUpdate(
                **common,
                entity_type="system_state",
                operation="merge",
                values={"daemon_status": "running", "daemon_last_tick_at": event.timestamp},
                expires_at=(self._instant(event.timestamp) + timedelta(minutes=2)).isoformat(),
            )
        if event.type.startswith("job."):
            return WorldStateUpdate(
                **common,
                entity_type="system_state",
                operation="merge",
                values={
                    "scheduler_status": ("degraded" if event.type == "job.failed" else "running"),
                    "scheduler_last_event_at": event.timestamp,
                },
                expires_at=(self._instant(event.timestamp) + timedelta(minutes=10)).isoformat(),
            )
        if event.type == "perception.observation_created":
            observation_id = str(payload.get("observation_id") or "")
            return WorldStateUpdate(
                **common,
                entity_type="environment_state",
                entity_id="recent_observation",
                operation="set",
                values={
                    "observation_id": observation_id,
                    "modality": payload.get("modality"),
                    "summary": payload.get("summary"),
                    "confidence": payload.get("confidence"),
                },
                expires_at=str(
                    payload.get("valid_until")
                    or (self._instant(event.timestamp) + timedelta(minutes=5)).isoformat()
                ),
                sensitivity="sensitive",
            )
        if event.type.startswith("voice.session_"):
            return WorldStateUpdate(
                **common,
                entity_type="environment_state",
                entity_id="audio_state",
                operation="set",
                values={
                    "event": event.type,
                    "session_id": payload.get("session_id"),
                    "updated_at": event.timestamp,
                },
                expires_at=(self._instant(event.timestamp) + timedelta(minutes=2)).isoformat(),
                sensitivity="sensitive",
            )
        return None

    @staticmethod
    def _attention_event(event: Event) -> AttentionEvent | None:
        important = {
            "job.failed": ("medium", "notify"),
            "daemon.error": ("high", "notify"),
            "agent.error": ("high", "notify"),
            "tool.failed": ("medium", "record_only"),
            "mission.failed": ("high", "suggest"),
            "perception.conflict_detected": ("medium", "record_only"),
            "approval.requested": ("high", "notify"),
        }
        if event.type not in important:
            return None
        severity, disposition = important[event.type]
        if event.severity == "critical":
            severity = "critical"
            disposition = "require_approval"
        return AttentionEvent(
            id=f"attention:{event.id}",
            type=event.type,
            source=event.source_module,
            title=str(event.payload.get("title") or event.type.replace(".", " ").title()),
            summary=str(event.payload.get("summary") or event.payload.get("error") or event.type),
            severity=severity,
            urgency={"medium": 0.5, "high": 0.8, "critical": 1.0}.get(severity, 0.2),
            confidence=float(event.payload.get("confidence", 1.0)),
            suggested_dispositions=[disposition],
            correlation_id=event.correlation_id,
            provenance={"event_id": event.id, "event_type": event.type},
            metadata={"deduplication_key": event.payload.get("deduplication_key", event.type)},
            created_at=event.timestamp,
        )

    @staticmethod
    def _instant(value: str) -> datetime:
        instant = datetime.fromisoformat(value)
        return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)
