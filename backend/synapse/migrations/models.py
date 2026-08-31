from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

MigrationFunction = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class SchemaMetadata:
    schema_version: int
    record_type: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MigrationDefinition:
    record_type: str
    from_version: int
    to_version: int
    migrate: MigrationFunction


@dataclass(frozen=True)
class MigrationHistoryEntry:
    record_type: str
    from_version: int
    to_version: int
    status: str
    path: str | None = None
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class MigrationStatus:
    current_versions: dict[str, int]
    migrations_available: int
    last_history: dict[str, Any] | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
