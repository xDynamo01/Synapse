from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

RecoveryPolicy = Literal[
    "fail_closed", "quarantine_record", "recover_from_backup", "skip_with_warning"
]


@dataclass(frozen=True)
class CollectionRecord:
    record_id: str
    schema_version: int
    revision: int
    created_at: str
    updated_at: str
    checksum: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class CollectionQuery:
    cursor: str | None = None
    limit: int = 100
    filters: Mapping[str, Any] = field(default_factory=dict)
    sort: Literal["record_id", "created_at", "updated_at"] = "record_id"
    descending: bool = False
    include_deleted: bool = False
    expected_schema_version: int | None = None


@dataclass(frozen=True)
class CollectionPage:
    items: tuple[CollectionRecord, ...]
    next_cursor: str | None = None
    total: int | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class WriteResult:
    record_id: str
    previous_revision: int | None
    revision: int
    created: bool
    checksum: str
    written_at: str


@dataclass(frozen=True)
class DeleteResult:
    record_id: str
    deleted: bool
    tombstoned: bool
    previous_revision: int | None
    revision: int | None


@dataclass(frozen=True)
class RecoveryResult:
    scanned: int
    valid: int
    repaired: int
    quarantined: int
    failed: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetentionPolicy:
    max_age_seconds: int | None = None
    max_records: int | None = None
    max_bytes: int | None = None
    tombstone_age_seconds: int | None = None
    dry_run: bool = True


@dataclass(frozen=True)
class CleanupResult:
    scanned: int
    eligible: int
    deleted: int
    retained: int
    failed: int
    reclaimed_bytes: int
    warnings: tuple[str, ...] = ()
