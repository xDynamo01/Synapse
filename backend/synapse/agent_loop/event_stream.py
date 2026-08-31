from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.core.events import EventBus
from synapse.observability.redaction import redact

PUBLIC_EVENT_TYPES = {
    "world_state.updated",
    "attention.created",
    "attention.escalated",
    "attention.resolved",
    "decision.created",
    "decision.awaiting_approval",
    "loop.cycle_started",
    "loop.action_started",
    "loop.action_completed",
    "loop.action_failed",
    "loop.paused",
    "loop.degraded",
}


class AgentEventStream:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    def list_events(self, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        events = [
            event
            for event in self.event_bus.tail(limit=1_000_000)
            if event.type in PUBLIC_EVENT_TYPES
        ]
        safe = []
        for event in events[offset : offset + min(max(limit, 0), 500)]:
            payload = asdict(event)
            payload["payload"] = redact(payload["payload"])
            payload.pop("metadata", None)
            safe.append(payload)
        return safe
