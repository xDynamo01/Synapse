from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class Event:
    type: str
    actor_id: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class EventBus:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "logs" / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event_type: str, actor_id: str, payload: dict[str, Any]) -> Event:
        event = Event(type=event_type, actor_id=actor_id, payload=payload)
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
            events.append(Event(**raw))
        return events

