from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from synapse.observability.correlation import CorrelationContext, current_correlation


@dataclass(frozen=True)
class Event:
    type: str
    actor_id: str
    payload: dict[str, Any]
    correlation_id: str | None = None
    causation_id: str | None = None
    source: str = "runtime"
    parent_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class EventBus:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "logs" / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        event_type: str,
        actor_id: str,
        payload: dict[str, Any],
        correlation: CorrelationContext | None = None,
    ) -> Event:
        correlation = correlation or current_correlation()
        event = Event(
            type=event_type,
            actor_id=actor_id,
            payload=payload,
            correlation_id=correlation.correlation_id if correlation else None,
            causation_id=correlation.causation_id if correlation else None,
            parent_id=correlation.parent_id if correlation else None,
            source=correlation.source if correlation else "runtime",
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), sort_keys=True) + "\n")
        return event

    def tail(self, limit: int = 100) -> list[Event]:
        if not self.path.exists():
            return []

        lines = self.path.read_text(encoding="utf-8").splitlines()
        events: list[Event] = []
        for line in lines[-limit:]:
            if not line.strip():
                continue
            raw = json.loads(line)
            raw.setdefault("correlation_id", None)
            raw.setdefault("causation_id", None)
            raw.setdefault("parent_id", None)
            raw.setdefault("source", "legacy")
            events.append(Event(**raw))
        return events

    def trace(self, correlation_id: str) -> list[Event]:
        if not self.path.exists():
            return []
        events: list[Event] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            raw.setdefault("correlation_id", None)
            raw.setdefault("causation_id", None)
            raw.setdefault("parent_id", None)
            raw.setdefault("source", "legacy")
            event = Event(**raw)
            if event.correlation_id == correlation_id:
                events.append(event)
        return events
