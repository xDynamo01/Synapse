"""Stable JSON-compatible projection serialization without presentation semantics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import cast

from .models import OperationalFact, ProjectActivitySnapshot


def snapshot_dict(snapshot: ProjectActivitySnapshot) -> dict[str, object]:
    return {
        "format": snapshot.format_version,
        "projectId": snapshot.project_id,
        "revision": snapshot.revision,
        "observedAt": snapshot.observed_at,
        "entities": [_camel(_plain_dict(entity)) for entity in snapshot.entities],
        "relations": [_camel(_plain_dict(relation)) for relation in snapshot.relations],
        "degraded": snapshot.degraded,
        "degradationReasons": list(snapshot.degradation_reasons),
        "lastEventId": snapshot.last_event_id,
    }


def fact_dict(fact: OperationalFact) -> dict[str, object]:
    return _camel(_plain_dict(fact))


def _plain_dict(value: object) -> dict[str, object]:
    return cast(dict[str, object], _plain(value))


def _plain(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _camel(values: dict[str, object]) -> dict[str, object]:
    return {_camel_key(key): value for key, value in values.items()}


def _camel_key(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)
