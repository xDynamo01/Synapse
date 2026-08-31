from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.core.events import EventBus

SENSITIVE_KEYS = {"prompt", "secret", "token", "password", "input_snapshot", "payload", "content"}


@dataclass(frozen=True)
class MissionTraceEvent:
    id: str
    mission_id: str
    event_type: str
    timestamp: str
    status: str | None = None
    plan_id: str | None = None
    swarm_id: str | None = None
    task_id: str | None = None
    attempt_id: str | None = None
    worker_id: str | None = None
    agent_id: str | None = None
    execution_id: str | None = None
    delegation_id: str | None = None
    correlation_id: str | None = None
    tool_ids: list[str] = field(default_factory=list)
    verification: dict[str, Any] | None = None
    recovery_action: str | None = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MissionTraceRuntime:
    def __init__(self, events: EventBus):
        self.events = events

    def list(
        self,
        mission_id: str,
        *,
        event_type: str | None = None,
        task_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[MissionTraceEvent]:
        records: list[MissionTraceEvent] = []
        for event in self.events.tail(limit=10000):
            payload = event.payload
            if payload.get("mission_id") != mission_id:
                continue
            if event_type and event.type != event_type:
                continue
            if task_id and payload.get("task_id") != task_id:
                continue
            records.append(
                MissionTraceEvent(
                    id=event.id,
                    mission_id=mission_id,
                    event_type=event.type,
                    timestamp=event.timestamp,
                    status=payload.get("status"),
                    plan_id=payload.get("plan_id"),
                    swarm_id=payload.get("swarm_id"),
                    task_id=payload.get("task_id"),
                    attempt_id=payload.get("attempt_id"),
                    worker_id=payload.get("worker_id"),
                    agent_id=payload.get("agent_id") or event.actor_id,
                    execution_id=payload.get("execution_id"),
                    delegation_id=payload.get("delegation_id"),
                    correlation_id=event.correlation_id or payload.get("correlation_id"),
                    tool_ids=list(payload.get("tool_call_ids", [])),
                    verification=self._redact(payload.get("verification_result")),
                    recovery_action=payload.get("recovery_action"),
                    error=self._redact(payload.get("error")),
                    metadata=self._redact(
                        {key: value for key, value in payload.items() if key not in SENSITIVE_KEYS}
                    ),
                )
            )
        return records[offset : offset + min(limit, 500)]

    def summarize(self, mission_id: str) -> dict[str, Any]:
        records = self.list(mission_id, limit=500)
        counts: dict[str, int] = {}
        for record in records:
            counts[record.event_type] = counts.get(record.event_type, 0) + 1
        return {
            "mission_id": mission_id,
            "total_events": len(records),
            "event_counts": dict(sorted(counts.items())),
        }

    def export(self, mission_id: str) -> dict[str, Any]:
        return {
            "summary": self.summarize(mission_id),
            "events": [asdict(item) for item in self.list(mission_id, limit=500)],
        }

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else self._redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value
