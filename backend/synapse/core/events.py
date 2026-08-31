from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from synapse.core.serialization import load_structured_file
from synapse.observability.correlation import CorrelationContext, current_correlation
from synapse.observability.redaction import redact


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
    severity: str = "info"
    source_module: str = "runtime"
    trace_id: str | None = None
    parent_span_id: str | None = None
    duration_ms: int | None = None
    status: str = "completed"
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / "logs" / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._listeners: list[Callable[[Event], None]] = []

    def add_listener(self, listener: Callable[[Event], None]) -> None:
        self._listeners.append(listener)

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
            payload=redact(payload),
            correlation_id=correlation.correlation_id if correlation else None,
            causation_id=correlation.causation_id if correlation else None,
            parent_id=correlation.parent_id if correlation else None,
            source=correlation.source if correlation else "runtime",
            source_module=event_type.split(".", 1)[0],
            trace_id=correlation.correlation_id if correlation else None,
            parent_span_id=correlation.parent_id if correlation else None,
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), sort_keys=True) + "\n")
        for listener in list(self._listeners):
            listener(event)
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
            self._event_defaults(raw)
            events.append(Event(**raw))
        return events

    def tolerant_tail(self, limit: int = 100) -> tuple[list[Event], int]:
        """Read valid events while reporting malformed durable records.

        This never rewrites or quarantines the journal. Callers must preserve the
        corruption count as degraded/unknown state rather than treating the read as complete.
        """
        if not self.path.exists():
            return [], 0
        lines = self.path.read_text(encoding="utf-8").splitlines()
        events: list[Event] = []
        corruptions = 0
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise TypeError("event record must be an object")
                raw.setdefault("correlation_id", None)
                raw.setdefault("causation_id", None)
                raw.setdefault("parent_id", None)
                raw.setdefault("source", "legacy")
                self._event_defaults(raw)
                events.append(Event(**raw))
            except (json.JSONDecodeError, TypeError, ValueError):
                corruptions += 1
        return events, corruptions

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
            self._event_defaults(raw)
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

    def start_span(
        self,
        name: str,
        actor_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        return self.emit(
            f"span.{name}.started",
            actor_id,
            metadata or {},
        )

    def record_event(
        self,
        event_type: str,
        actor_id: str,
        metadata: dict[str, Any],
        correlation: CorrelationContext | None = None,
    ) -> Event:
        return self.emit(event_type, actor_id, metadata, correlation)

    def finish_span(
        self,
        name: str,
        actor_id: str,
        *,
        duration_ms: int,
        status: str = "completed",
        error_code: str | None = None,
    ) -> Event:
        event = self.emit(
            f"span.{name}.finished",
            actor_id,
            {"duration_ms": duration_ms, "status": status, "error_code": error_code},
        )
        return event

    def query_events(
        self,
        *,
        event_type: str | None = None,
        source_module: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Event]:
        events = self.tail(limit=max(offset + limit, 1_000_000))
        if event_type:
            events = [item for item in events if fnmatch_event(item.type, event_type)]
        if source_module:
            events = [item for item in events if item.source_module == source_module]
        if status:
            events = [item for item in events if item.status == status]
        return events[offset : offset + limit]

    def query_trace(self, trace_id: str) -> dict[str, Any]:
        events = self.trace(trace_id)
        return {
            "trace_id": trace_id,
            "events": [asdict(item) for item in events],
            "records": self.trace_records(trace_id),
        }

    def metrics(self) -> dict[str, Any]:
        events = self.tail(limit=1_000_000)
        failures = [item for item in events if item.status == "failed" or item.error_code]
        latencies = [item.duration_ms for item in events if item.duration_ms is not None]
        counters: dict[str, int] = {}
        for item in events:
            counters[item.type] = counters.get(item.type, 0) + 1
        return {
            "counters": {
                "events_total": len(events),
                "failures_total": len(failures),
                "by_event_type": counters,
            },
            "histograms": {
                "duration_ms": {
                    "count": len(latencies),
                    "min": min(latencies) if latencies else None,
                    "max": max(latencies) if latencies else None,
                    "average": sum(latencies) / len(latencies) if latencies else None,
                }
            },
            "snapshot_at": datetime.now(UTC).isoformat(),
        }

    def cleanup(self, retention_days: int = 30, dry_run: bool = False) -> dict[str, Any]:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        keep: list[str] = []
        removed = 0
        for line in lines:
            try:
                raw = json.loads(line)
                timestamp = datetime.fromisoformat(raw["timestamp"])
            except Exception:
                keep.append(line)
                continue
            if timestamp < cutoff:
                removed += 1
            else:
                keep.append(line)
        if not dry_run and removed:
            self.path.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
        return {
            "scanned": len(lines),
            "removed": removed,
            "retained": len(keep),
            "dry_run": dry_run,
            "retention_days": retention_days,
        }

    @staticmethod
    def _event_defaults(raw: dict[str, Any]) -> None:
        raw.setdefault("severity", "info")
        raw.setdefault("source_module", str(raw.get("type", "legacy")).split(".", 1)[0])
        raw.setdefault("trace_id", raw.get("correlation_id"))
        raw.setdefault("parent_span_id", raw.get("parent_id"))
        raw.setdefault("duration_ms", None)
        raw.setdefault("status", "completed")
        raw.setdefault("error_code", None)
        raw.setdefault("metadata", {})

    def _candidate_record_paths(self) -> list[Path]:
        patterns = [
            "tasks/*/*.json",
            "agents/*/messages/*.yaml",
            "approvals/*.yaml",
            "jobs/*.yaml",
            "chats/sessions/*.json",
            "notifications/*.yaml",
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
        if "notifications" in parts:
            return "notification"
        return "record"


def fnmatch_event(value: str, pattern: str) -> bool:
    from fnmatch import fnmatchcase

    return fnmatchcase(value, pattern)
