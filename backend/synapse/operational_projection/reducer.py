"""Deterministic reducer for project-scoped operational facts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .models import (
    OperationalEntity,
    OperationalFact,
    OperationalFactKind,
    OperationalRelation,
    ProjectActivitySnapshot,
)


class OperationalProjectionError(Exception):
    """Base error with no source payload disclosure."""


class CrossProjectFact(OperationalProjectionError):
    pass


class StaleOperationalFact(OperationalProjectionError):
    pass


class OperationalRevisionGap(OperationalProjectionError):
    pass


class ContradictoryOperationalFact(OperationalProjectionError):
    pass


class InvalidOperationalFact(OperationalProjectionError):
    pass


@dataclass(slots=True)
class OperationalProjectionReducer:
    project_id: str
    _revision: int = 0
    _last_event_id: str | None = None
    _entities: dict[str, OperationalEntity] = field(default_factory=dict)
    _relations: dict[str, OperationalRelation] = field(default_factory=dict)
    _degradation_reasons: set[str] = field(default_factory=set)
    _events: dict[str, OperationalFact] = field(default_factory=dict)

    def apply(self, fact: OperationalFact) -> bool:
        if fact.project_id != self.project_id:
            raise CrossProjectFact("operational fact belongs to another project")
        existing = self._events.get(fact.event_id)
        if existing is not None:
            if existing != fact:
                raise ContradictoryOperationalFact("event identity has contradictory content")
            return False
        if fact.revision <= self._revision:
            raise StaleOperationalFact("operational fact revision is stale")
        if fact.revision != self._revision + 1:
            raise OperationalRevisionGap("operational fact revision gap")
        self._reduce(fact)
        self._events[fact.event_id] = fact
        self._revision = fact.revision
        self._last_event_id = fact.event_id
        return True

    def replay(self, facts: tuple[OperationalFact, ...]) -> ProjectActivitySnapshot:
        for fact in facts:
            self.apply(fact)
        observed_at = facts[-1].occurred_at if facts else datetime.now(UTC).isoformat()
        return self.snapshot(observed_at)

    def snapshot(self, observed_at: str) -> ProjectActivitySnapshot:
        return ProjectActivitySnapshot(
            project_id=self.project_id,
            revision=self._revision,
            observed_at=observed_at,
            entities=tuple(self._entities[key] for key in sorted(self._entities)),
            relations=tuple(self._relations[key] for key in sorted(self._relations)),
            degraded=bool(self._degradation_reasons),
            degradation_reasons=tuple(sorted(self._degradation_reasons)),
            last_event_id=self._last_event_id,
        )

    def _reduce(self, fact: OperationalFact) -> None:
        if fact.kind is OperationalFactKind.UPSERT_ENTITY and fact.entity is not None:
            self._entities[fact.entity.entity_id] = fact.entity
            return
        if fact.kind is OperationalFactKind.REMOVE_ENTITY and fact.entity_id is not None:
            self._entities.pop(fact.entity_id, None)
            self._relations = {
                key: relation
                for key, relation in self._relations.items()
                if fact.entity_id not in {relation.source_entity_id, relation.target_entity_id}
            }
            return
        if fact.kind is OperationalFactKind.UPSERT_RELATION and fact.relation is not None:
            if not {
                fact.relation.source_entity_id,
                fact.relation.target_entity_id,
            }.issubset(self._entities):
                raise InvalidOperationalFact("relation references an unknown entity")
            self._relations[fact.relation.relation_id] = fact.relation
            return
        if fact.kind is OperationalFactKind.REMOVE_RELATION and fact.relation_id is not None:
            self._relations.pop(fact.relation_id, None)
            return
        if (
            fact.kind is OperationalFactKind.MARK_DEGRADED
            and fact.degradation_reason is not None
        ):
            self._degradation_reasons.add(fact.degradation_reason)
            return
        if (
            fact.kind is OperationalFactKind.CLEAR_DEGRADED
            and fact.degradation_reason is not None
        ):
            self._degradation_reasons.discard(fact.degradation_reason)
            return
        raise InvalidOperationalFact("operational fact payload does not match its kind")
