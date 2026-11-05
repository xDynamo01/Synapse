"""Read-only composition adapter from the durable EventBus to project activity feeds."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from synapse.core.events import Event, EventBus
from synapse.operational_projection import (
    ActivityResume,
    OperationalSourceRecord,
    ProjectActivityFeed,
    ProjectActivitySnapshot,
    SourceAdaptationDisposition,
    adapt_source_record,
)
from synapse.project_governance.errors import ProjectNotFound


class ProjectScopeRegistry(Protocol):
    def get(self, project_id: str) -> object: ...


class OperationalProjectionRuntime:
    def __init__(self, events: EventBus, *, max_retained_events: int = 1_000) -> None:
        self._events = events
        self._max_retained_events = max_retained_events
        self._feeds: dict[str, ProjectActivityFeed] = {}
        self._seen: set[str] = set()
        self._unscoped_events = 0
        self._unsupported_events = 0
        self._corrupt_event_records = 0

    def snapshot(self, project_id: str, observed_at: str) -> ProjectActivitySnapshot:
        self.refresh()
        return self._degraded_snapshot(self._feed(project_id).snapshot(observed_at))

    def resume(
        self, project_id: str, cursor: str | None, observed_at: str
    ) -> ActivityResume:
        self.refresh()
        resumed = self._feed(project_id).resume(cursor, observed_at)
        return replace(resumed, snapshot=self._degraded_snapshot(resumed.snapshot))

    def refresh(self) -> int:
        appended = 0
        events, corruptions = self._events.tolerant_tail(limit=1_000_000)
        self._corrupt_event_records = corruptions
        for event in events:
            if event.id in self._seen:
                continue
            self._seen.add(event.id)
            project_id = _project_id(event)
            feed = self._feed(project_id) if project_id is not None else None
            result = adapt_source_record(
                _source_record(event, project_id),
                (feed.snapshot(event.timestamp).revision + 1) if feed is not None else 1,
            )
            if result.disposition is SourceAdaptationDisposition.PROJECT_SCOPE_UNKNOWN:
                self._unscoped_events += 1
                continue
            if result.disposition is not SourceAdaptationDisposition.ADAPTED:
                self._unsupported_events += 1
                continue
            if feed is not None and result.fact is not None:
                feed.append(result.fact)
                appended += 1
        return appended

    def diagnostics(self) -> dict[str, int]:
        return {
            "projects": len(self._feeds),
            "seen_events": len(self._seen),
            "unscoped_events": self._unscoped_events,
            "unsupported_events": self._unsupported_events,
            "corrupt_event_records": self._corrupt_event_records,
        }

    def scope_allowed(self, scope_id: str, projects: ProjectScopeRegistry) -> bool:
        if scope_id.startswith("conversation:") and len(scope_id) > len("conversation:"):
            return True
        try:
            projects.get(scope_id)
        except ProjectNotFound:
            return False
        return True

    def _degraded_snapshot(self, snapshot: ProjectActivitySnapshot) -> ProjectActivitySnapshot:
        if self._corrupt_event_records == 0:
            return snapshot
        reasons = tuple(sorted({*snapshot.degradation_reasons, "operational-event-log-corrupt"}))
        return replace(snapshot, degraded=True, degradation_reasons=reasons)

    def _feed(self, project_id: str) -> ProjectActivityFeed:
        return self._feeds.setdefault(
            project_id,
            ProjectActivityFeed(project_id, max_retained_events=self._max_retained_events),
        )
def _project_id(event: Event) -> str | None:
    if event.type.startswith(("local_chat.", "lmstudio.native.")):
        conversation_id = event.payload.get("conversation_id")
        if isinstance(conversation_id, str) and conversation_id.strip():
            return f"conversation:{conversation_id}"
    value = event.payload.get("project_id")
    if isinstance(value, str) and value.strip():
        return value
    # Task lifecycle events carry their project scope in task metadata. Keep
    # the projection authoritative without requiring every producer to flatten
    # the same metadata into the event envelope.
    metadata = event.payload.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("project_id")
        if isinstance(value, str) and value.strip():
            return value
    task = event.payload.get("task")
    if isinstance(task, dict) and isinstance(task.get("metadata"), dict):
        value = task["metadata"].get("project_id")
        if isinstance(value, str) and value.strip():
            return value
    conversation_id = event.payload.get("conversation_id")
    if isinstance(conversation_id, str) and conversation_id.strip():
        return f"conversation:{conversation_id}"
    return None


def _source_record(event: Event, project_id: str | None) -> OperationalSourceRecord:
    return OperationalSourceRecord(
        event_id=event.id,
        event_type=event.type,
        actor_id=event.actor_id,
        occurred_at=event.timestamp,
        project_id=project_id,
        payload=event.payload,
        source_reference=f"event-log:{event.id}",
        correlation_reference=event.correlation_id,
    )
