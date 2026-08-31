"""Cursor, replay and resynchronization semantics independent from transport."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

from .models import OperationalFact, ProjectActivitySnapshot
from .reducer import OperationalProjectionReducer

CURSOR_FORMAT_V1 = "project-activity-cursor-v1"


class OperationalCursorError(Exception):
    pass


class CrossProjectCursor(OperationalCursorError):
    pass


class InvalidOperationalCursor(OperationalCursorError):
    pass


class OperationalResyncRequired(OperationalCursorError):
    pass


@dataclass(frozen=True, slots=True)
class OperationalCursor:
    project_id: str
    revision: int
    event_id: str
    format_version: str = CURSOR_FORMAT_V1

    def encode(self) -> str:
        raw = json.dumps(
            {
                "event_id": self.event_id,
                "format": self.format_version,
                "project_id": self.project_id,
                "revision": self.revision,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @classmethod
    def decode(cls, value: str) -> OperationalCursor:
        try:
            padding = "=" * (-len(value) % 4)
            raw = json.loads(base64.urlsafe_b64decode(value + padding))
            cursor = cls(
                project_id=raw["project_id"],
                revision=raw["revision"],
                event_id=raw["event_id"],
                format_version=raw["format"],
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise InvalidOperationalCursor("invalid operational cursor") from exc
        if cursor.format_version != CURSOR_FORMAT_V1 or cursor.revision < 1:
            raise InvalidOperationalCursor("unsupported operational cursor")
        return cursor


@dataclass(frozen=True, slots=True)
class ActivityResume:
    snapshot: ProjectActivitySnapshot
    events: tuple[OperationalFact, ...]
    cursor: OperationalCursor | None
    resynchronized: bool


@dataclass(slots=True)
class ProjectActivityFeed:
    project_id: str
    max_retained_events: int = 1_000
    _reducer: OperationalProjectionReducer = field(init=False)
    _events: list[OperationalFact] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.max_retained_events < 1:
            raise ValueError("max_retained_events must be positive")
        self._reducer = OperationalProjectionReducer(self.project_id)

    def append(self, fact: OperationalFact) -> OperationalCursor:
        self._reducer.apply(fact)
        self._events.append(fact)
        if len(self._events) > self.max_retained_events:
            self._events.pop(0)
        return OperationalCursor(self.project_id, fact.revision, fact.event_id)

    def snapshot(self, observed_at: str) -> ProjectActivitySnapshot:
        return self._reducer.snapshot(observed_at)

    def resume(self, encoded_cursor: str | None, observed_at: str) -> ActivityResume:
        snapshot = self.snapshot(observed_at)
        if encoded_cursor is None:
            return ActivityResume(snapshot, (), self.current_cursor(), True)
        cursor = OperationalCursor.decode(encoded_cursor)
        if cursor.project_id != self.project_id:
            raise CrossProjectCursor("cursor belongs to another project")
        if cursor.revision > snapshot.revision:
            raise InvalidOperationalCursor("cursor revision is ahead of the projection")
        match = next(
            (
                index
                for index, event in enumerate(self._events)
                if event.revision == cursor.revision and event.event_id == cursor.event_id
            ),
            None,
        )
        if match is None:
            raise OperationalResyncRequired("cursor is outside retained activity")
        events = tuple(self._events[match + 1 :])
        return ActivityResume(snapshot, events, self.current_cursor(), False)

    def current_cursor(self) -> OperationalCursor | None:
        if not self._events:
            return None
        event = self._events[-1]
        return OperationalCursor(self.project_id, event.revision, event.event_id)

    def retained_events(self) -> tuple[OperationalFact, ...]:
        return tuple(self._events)
