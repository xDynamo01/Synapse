from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from synapse.core.serialization import load_structured_file
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
        self.data_dir = data_dir
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

    def trace_records(self, correlation_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in self._candidate_record_paths():
            record = self._load_record(path)
            if not record:
                continue
            if record.get("correlation_id") == correlation_id:
                records.append(self._trace_record(path, record))
            for item in record.get("messages", []):
                if isinstance(item, dict) and item.get("correlation_id") == correlation_id:
                    records.append(self._trace_record(path, item, nested_kind="chat_message"))
        return records

    def _candidate_record_paths(self) -> list[Path]:
        patterns = [
            "tasks/*/*.json",
            "agents/*/messages/*.yaml",
            "approvals/*.yaml",
            "jobs/*.yaml",
            "chats/sessions/*.json",
        ]
        paths: list[Path] = []
        for pattern in patterns:
            paths.extend(sorted(self.data_dir.glob(pattern)))
        return paths

    def _load_record(self, path: Path) -> dict[str, Any]:
        if path.suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        return load_structured_file(path)

    def _trace_record(
        self,
        path: Path,
        record: dict[str, Any],
        nested_kind: str | None = None,
    ) -> dict[str, Any]:
        return {
            "kind": nested_kind or self._record_kind(path),
            "path": str(path.relative_to(self.data_dir)).replace("\\", "/"),
            "record": record,
        }

    @staticmethod
    def _record_kind(path: Path) -> str:
        parts = path.parts
        if "tasks" in parts:
            return "task"
        if "messages" in parts:
            return "agent_message"
        if "approvals" in parts:
            return "approval"
        if "jobs" in parts:
            return "job"
        if "sessions" in parts:
            return "chat_session"
        return "record"
