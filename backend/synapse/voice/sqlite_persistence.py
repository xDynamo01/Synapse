from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from synapse.core.exceptions import NotFound, ValidationError
from synapse.voice.persistence_models import (
    VOICE_RECORD_FORMAT_V1,
    VOICE_SQLITE_SCHEMA_VERSION,
    VoiceCompleteness,
    VoicePersistenceHealth,
    VoicePersistenceState,
    VoiceRecord,
    VoiceRecordDraft,
    VoiceReplay,
    canonical_json,
    semantic_fingerprint,
)

_MIGRATION_ID = "voice-schema-v1"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS voice_migrations (
    migration_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, checksum TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS voice_records (
    record_id TEXT PRIMARY KEY,
    stream_id TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    payload TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    fingerprint TEXT NOT NULL UNIQUE,
    lineage TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    retention TEXT NOT NULL,
    completeness TEXT NOT NULL,
    format_version TEXT NOT NULL,
    UNIQUE(stream_id, revision)
);
CREATE INDEX IF NOT EXISTS voice_records_stream_revision
ON voice_records(stream_id, revision);
CREATE TRIGGER IF NOT EXISTS voice_records_no_update BEFORE UPDATE ON voice_records
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS voice_records_no_delete BEFORE DELETE ON voice_records
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS voice_migrations_no_update BEFORE UPDATE ON voice_migrations
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS voice_migrations_no_delete BEFORE DELETE ON voice_migrations
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""
_MIGRATION_CHECKSUM = hashlib.sha256(_SCHEMA.encode("utf-8")).hexdigest()


class SQLiteVoiceJournal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in {0, VOICE_SQLITE_SCHEMA_VERSION}:
                raise ValidationError("Voice persistence schema mismatch.")
            connection.executescript(_SCHEMA)
            row = connection.execute(
                "SELECT schema_version, checksum FROM voice_migrations WHERE migration_id=?",
                (_MIGRATION_ID,),
            ).fetchone()
            if row is None:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO voice_migrations VALUES (?, ?, ?)",
                    (_MIGRATION_ID, VOICE_SQLITE_SCHEMA_VERSION, _MIGRATION_CHECKSUM),
                )
                connection.execute(f"PRAGMA user_version={VOICE_SQLITE_SCHEMA_VERSION}")
                connection.commit()
            elif row[0] != VOICE_SQLITE_SCHEMA_VERSION or row[1] != _MIGRATION_CHECKSUM:
                raise ValidationError("Voice persistence migration mismatch.")

    def append(
        self, draft: VoiceRecordDraft, *, expected_revision: int | None = None
    ) -> VoiceRecord:
        if not draft.stream_id or not draft.fact_type or not draft.idempotency_key:
            raise ValidationError("Voice record identity is incomplete.")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                "SELECT * FROM voice_records WHERE idempotency_key=? OR fingerprint=?",
                (draft.idempotency_key, draft.fingerprint),
            ).fetchone()
            if duplicate is not None:
                record = self._decode(duplicate)
                if record.fingerprint != draft.fingerprint:
                    connection.rollback()
                    raise ValidationError("Voice record idempotency conflict.")
                connection.commit()
                return record
            current = int(
                connection.execute(
                    "SELECT COALESCE(MAX(revision), 0) FROM voice_records WHERE stream_id=?",
                    (draft.stream_id,),
                ).fetchone()[0]
            )
            if expected_revision is not None and current != expected_revision:
                connection.rollback()
                raise ValidationError("Voice journal optimistic revision conflict.")
            if draft.revision != current + 1:
                connection.rollback()
                raise ValidationError("Voice journal lineage gap.")
            known = {
                row[0]
                for row in connection.execute(
                    "SELECT fingerprint FROM voice_records WHERE fingerprint IN ({})".format(
                        ",".join("?" for _ in draft.lineage) or "NULL"
                    ),
                    draft.lineage,
                )
            }
            if any(item not in known for item in draft.lineage):
                connection.rollback()
                raise ValidationError("Voice journal lineage reference is missing.")
            connection.execute(
                "INSERT INTO voice_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    draft.record_id,
                    draft.stream_id,
                    draft.fact_type,
                    draft.revision,
                    canonical_json(draft.payload),
                    draft.idempotency_key,
                    draft.fingerprint,
                    canonical_json(draft.lineage),
                    draft.occurred_at,
                    canonical_json(draft.retention),
                    draft.completeness.value,
                    VOICE_RECORD_FORMAT_V1,
                ),
            )
            connection.commit()
        return VoiceRecord(
            draft.record_id,
            draft.stream_id,
            draft.fact_type,
            draft.revision,
            draft.payload,
            draft.idempotency_key,
            draft.fingerprint,
            draft.lineage,
            draft.occurred_at,
            draft.retention,
            draft.completeness,
        )

    def read_exact(self, record_id: str, fingerprint: str) -> VoiceRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM voice_records WHERE record_id=? AND fingerprint=?",
                (record_id, fingerprint),
            ).fetchone()
        if row is None:
            raise NotFound("Voice record not found for exact identity and fingerprint.")
        return self._decode(row)

    def read_causal_range(
        self, stream_id: str, start_revision: int, end_revision: int
    ) -> tuple[VoiceRecord, ...]:
        if start_revision < 1 or end_revision < start_revision:
            raise ValidationError("Invalid voice causal range.")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM voice_records WHERE stream_id=? AND revision BETWEEN ? AND ? ORDER BY revision",
                (stream_id, start_revision, end_revision),
            ).fetchall()
        return tuple(self._decode(row) for row in rows)

    def replay(self, stream_id: str) -> VoiceReplay:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM voice_records WHERE stream_id=? ORDER BY revision", (stream_id,)
            ).fetchall()
            known = {row[0] for row in connection.execute("SELECT fingerprint FROM voice_records")}
        records = tuple(self._decode(row) for row in rows)
        expected = set(range(1, (records[-1].revision if records else 0) + 1))
        missing_revisions = tuple(sorted(expected - {record.revision for record in records}))
        missing_lineage = tuple(
            sorted({item for record in records for item in record.lineage if item not in known})
        )
        complete = (
            not missing_revisions
            and not missing_lineage
            and all(record.completeness is VoiceCompleteness.COMPLETE for record in records)
        )
        return VoiceReplay(stream_id, records, missing_revisions, missing_lineage, complete)

    def stream_ids(self, prefix: str) -> tuple[str, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT stream_id FROM voice_records WHERE stream_id LIKE ? ORDER BY stream_id",
                (f"{prefix}%",),
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def health(self) -> VoicePersistenceHealth:
        try:
            with self._connection() as connection:
                integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                row = connection.execute(
                    "SELECT checksum FROM voice_migrations WHERE migration_id=?", (_MIGRATION_ID,)
                ).fetchone()
            if integrity != "ok":
                return VoicePersistenceHealth(
                    VoicePersistenceState.CORRUPT, version, detail=integrity
                )
            if version != VOICE_SQLITE_SCHEMA_VERSION:
                return VoicePersistenceHealth(VoicePersistenceState.SCHEMA_MISMATCH, version)
            if row is None or row[0] != _MIGRATION_CHECKSUM:
                return VoicePersistenceHealth(
                    VoicePersistenceState.MIGRATION_MISMATCH, version, row[0] if row else None
                )
            return VoicePersistenceHealth(
                VoicePersistenceState.AVAILABLE, version, _MIGRATION_CHECKSUM
            )
        except sqlite3.DatabaseError:
            return VoicePersistenceHealth(VoicePersistenceState.CORRUPT)
        except OSError:
            return VoicePersistenceHealth(VoicePersistenceState.UNAVAILABLE)

    @staticmethod
    def _decode(row: sqlite3.Row) -> VoiceRecord:
        try:
            payload = json.loads(row["payload"])
            lineage = tuple(json.loads(row["lineage"]))
            retention = json.loads(row["retention"])
            completeness = VoiceCompleteness(row["completeness"])
            if row["format_version"] != VOICE_RECORD_FORMAT_V1:
                raise ValueError
            actual = semantic_fingerprint(
                stream_id=row["stream_id"],
                fact_type=row["fact_type"],
                revision=row["revision"],
                payload=payload,
            )
            if actual != row["fingerprint"]:
                raise ValueError
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValidationError("Voice journal record is corrupt.") from exc
        return VoiceRecord(
            row["record_id"],
            row["stream_id"],
            row["fact_type"],
            row["revision"],
            payload,
            row["idempotency_key"],
            row["fingerprint"],
            lineage,
            row["occurred_at"],
            retention,
            completeness,
            row["format_version"],
        )
