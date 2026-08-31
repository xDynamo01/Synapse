from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

VOICE_RECORD_FORMAT_V1 = "voice-record-v1"
VOICE_SQLITE_SCHEMA_VERSION = 1


class VoicePersistenceState(StrEnum):
    AVAILABLE = "available"
    SCHEMA_MISMATCH = "schema_mismatch"
    MIGRATION_MISMATCH = "migration_mismatch"
    CORRUPT = "corrupt"
    UNAVAILABLE = "unavailable"


class VoiceCompleteness(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def semantic_fingerprint(
    *, stream_id: str, fact_type: str, revision: int, payload: dict[str, Any]
) -> str:
    semantic = {
        "fact_type": fact_type,
        "format": VOICE_RECORD_FORMAT_V1,
        "payload": payload,
        "revision": revision,
        "stream_id": stream_id,
    }
    return hashlib.sha256(canonical_json(semantic).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VoiceRecordDraft:
    stream_id: str
    fact_type: str
    revision: int
    payload: dict[str, Any]
    idempotency_key: str
    lineage: tuple[str, ...] = ()
    record_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    retention: dict[str, Any] = field(default_factory=dict)
    completeness: VoiceCompleteness = VoiceCompleteness.COMPLETE

    @property
    def fingerprint(self) -> str:
        return semantic_fingerprint(
            stream_id=self.stream_id,
            fact_type=self.fact_type,
            revision=self.revision,
            payload=self.payload,
        )


@dataclass(frozen=True)
class VoiceRecord:
    record_id: str
    stream_id: str
    fact_type: str
    revision: int
    payload: dict[str, Any]
    idempotency_key: str
    fingerprint: str
    lineage: tuple[str, ...]
    occurred_at: str
    retention: dict[str, Any]
    completeness: VoiceCompleteness
    format_version: str = VOICE_RECORD_FORMAT_V1


@dataclass(frozen=True)
class VoiceReplay:
    stream_id: str
    records: tuple[VoiceRecord, ...]
    missing_revisions: tuple[int, ...]
    missing_lineage: tuple[str, ...]
    complete: bool


@dataclass(frozen=True)
class VoicePersistenceHealth:
    state: VoicePersistenceState
    schema_version: int | None = None
    migration_checksum: str | None = None
    detail: str | None = None
