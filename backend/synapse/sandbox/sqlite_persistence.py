"""SQLite V1 adapters for durable append-only Sandbox artifact records."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .canonical import canonical_bytes
from .errors import (
    SandboxPersistenceConflict,
    SandboxPersistenceCorrupt,
    SandboxPersistenceMigrationMismatch,
    SandboxPersistenceRecordNotFound,
    SandboxPersistenceUnavailable,
    SandboxPersistenceVersionUnsupported,
)
from .persistence_contracts import SandboxArtifactStore
from .persistence_models import (
    SANDBOX_RECORD_FORMAT,
    SANDBOX_SCHEMA_VERSION,
    SandboxArtifactKind,
    SandboxCompleteness,
    SandboxOccurrenceMetadata,
    SandboxPersistedRecord,
    SandboxRecordDraft,
    SandboxRecoveryFinding,
    SandboxRecoveryState,
    SandboxReplay,
    SandboxRetentionMetadata,
    SandboxStoreResponsibility,
    SandboxWriteDisposition,
    SandboxWriteResult,
)

_TABLES = {
    SandboxStoreResponsibility.CATALOG: "sandbox_catalog_records",
    SandboxStoreResponsibility.ADMISSION: "sandbox_admission_records",
    SandboxStoreResponsibility.LIFECYCLE: "sandbox_lifecycle_records",
    SandboxStoreResponsibility.RESULT: "sandbox_result_records",
}
_ARTIFACT_RESPONSIBILITY = {
    **{
        kind: SandboxStoreResponsibility.CATALOG
        for kind in (SandboxArtifactKind.ADMISSION_POLICY, SandboxArtifactKind.EVIDENCE_POLICY)
    },
    **{
        kind: SandboxStoreResponsibility.ADMISSION
        for kind in (
            SandboxArtifactKind.ADMISSION_REQUEST,
            SandboxArtifactKind.ADMISSION_SNAPSHOT,
            SandboxArtifactKind.ADMISSION_ASSESSMENT,
            SandboxArtifactKind.ADMISSION_DECISION,
            SandboxArtifactKind.EXECUTION_PLAN,
            SandboxArtifactKind.CAPABILITY_GRANT_SET,
            SandboxArtifactKind.FILESYSTEM_GRANT_SET,
            SandboxArtifactKind.FILESYSTEM_SPECIFICATION,
            SandboxArtifactKind.NETWORK_GRANT_SET,
            SandboxArtifactKind.NETWORK_SPECIFICATION,
            SandboxArtifactKind.PROCESS_GRANT_SET,
            SandboxArtifactKind.PROCESS_SPECIFICATION,
            SandboxArtifactKind.RESOURCE_GRANT_SET,
            SandboxArtifactKind.RESOURCE_SPECIFICATION,
            SandboxArtifactKind.SECRET_GRANT_SET,
            SandboxArtifactKind.SECRET_SPECIFICATION,
            SandboxArtifactKind.MATERIALIZATION_PLAN,
        )
    },
    **{
        kind: SandboxStoreResponsibility.LIFECYCLE
        for kind in (
            SandboxArtifactKind.MATERIALIZATION_RECORD,
            SandboxArtifactKind.MATERIALIZATION_VERIFICATION,
            SandboxArtifactKind.MATERIALIZATION_OUTCOME,
            SandboxArtifactKind.EXECUTION_ATTEMPT,
            SandboxArtifactKind.RUNTIME_EVENT,
            SandboxArtifactKind.RUNTIME_OBSERVATION,
            SandboxArtifactKind.TERMINATION_PROOF,
            SandboxArtifactKind.CANCELLATION_REQUEST,
            SandboxArtifactKind.DEADLINE_SET,
            SandboxArtifactKind.DEADLINE_EVALUATION,
            SandboxArtifactKind.CANCELLATION_DECISION,
            SandboxArtifactKind.CANCELLATION_EVENT,
            SandboxArtifactKind.CANCELLATION_RESULT,
        )
    },
    **{
        kind: SandboxStoreResponsibility.RESULT
        for kind in (
            SandboxArtifactKind.EXECUTION_RESULT,
            SandboxArtifactKind.EVIDENCE_ITEM,
            SandboxArtifactKind.EVIDENCE_BUNDLE,
        )
    },
}
_MIGRATION_ID = "sandbox-persistence-v1"
_BASE_SCHEMA = """
CREATE TABLE sandbox_schema_metadata (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1), schema_version INTEGER NOT NULL
);
CREATE TABLE sandbox_migration_history (
    migration_id TEXT PRIMARY KEY, from_version INTEGER NOT NULL,
    to_version INTEGER NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL
);
CREATE TRIGGER sandbox_migration_history_no_update BEFORE UPDATE ON sandbox_migration_history
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER sandbox_migration_history_no_delete BEFORE DELETE ON sandbox_migration_history
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""
_RECORD_SCHEMA = """
CREATE TABLE {table} (
    semantic_identity TEXT NOT NULL,
    semantic_fingerprint TEXT NOT NULL UNIQUE,
    artifact_kind TEXT NOT NULL,
    stream_identity TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence >= 1),
    idempotency_key TEXT NOT NULL UNIQUE,
    record_format TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    payload_checksum TEXT NOT NULL,
    lineage TEXT NOT NULL,
    completeness TEXT NOT NULL,
    recovery_state TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    correlation_ref TEXT,
    retention_policy_ref TEXT NOT NULL,
    retain_until TEXT,
    legal_hold INTEGER NOT NULL CHECK(legal_hold IN (0, 1)),
    purge_eligible INTEGER NOT NULL CHECK(purge_eligible IN (0, 1)),
    PRIMARY KEY(semantic_identity, semantic_fingerprint),
    UNIQUE(stream_identity, sequence)
);
CREATE INDEX {table}_stream ON {table}(stream_identity, sequence);
CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""
_V1_SQL = _BASE_SCHEMA + "".join(_RECORD_SCHEMA.format(table=table) for table in _TABLES.values())
_MIGRATION_CHECKSUM = hashlib.sha256(
    f"id={_MIGRATION_ID}\nfrom=0\nto=1\n{' '.join(_V1_SQL.split())}".encode()
).hexdigest()
_RECORD_COLUMNS = (
    "semantic_identity",
    "semantic_fingerprint",
    "artifact_kind",
    "stream_identity",
    "sequence",
    "idempotency_key",
    "record_format",
    "schema_version",
    "payload",
    "payload_checksum",
    "lineage",
    "completeness",
    "recovery_state",
    "occurred_at",
    "observed_at",
    "source_ref",
    "correlation_ref",
    "retention_policy_ref",
    "retain_until",
    "legal_hold",
    "purge_eligible",
)


@dataclass(frozen=True, slots=True)
class SandboxSQLiteConfig:
    database_path: Path
    busy_timeout_ms: int = 5_000

    def __post_init__(self) -> None:
        raw = str(self.database_path)
        if (
            not isinstance(self.database_path, Path)
            or not self.database_path.is_absolute()
            or raw.startswith(("\\\\", "//"))
            or ".." in self.database_path.parts
            or self.database_path.exists()
            and self.database_path.is_dir()
            or self.database_path.parent.exists()
            and self.database_path.parent.is_symlink()
        ):
            raise ValueError("sandbox database path must be absolute")
        if isinstance(self.busy_timeout_ms, bool) or self.busy_timeout_ms <= 0:
            raise ValueError("sandbox database timeout is invalid")


class SandboxSQLiteDatabase:
    def __init__(self, config: SandboxSQLiteConfig) -> None:
        self._config = config

    @property
    def database_path(self) -> Path:
        return self._config.database_path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(
                str(self._config.database_path),
                timeout=self._config.busy_timeout_ms / 1_000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.enable_load_extension(False)
        except (OSError, sqlite3.Error) as exc:
            raise SandboxPersistenceUnavailable("sandbox persistence unavailable") from exc
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self, applied_at: datetime) -> None:
        if applied_at.tzinfo is None or applied_at.utcoffset() is None:
            raise ValueError("migration timestamp must be timezone-aware")
        with self.connection() as connection:
            tables = self._tables(connection)
            if not tables:
                try:
                    connection.executescript("BEGIN EXCLUSIVE;\n" + _V1_SQL)
                    connection.execute(
                        "INSERT INTO sandbox_schema_metadata VALUES (1, ?)",
                        (SANDBOX_SCHEMA_VERSION,),
                    )
                    connection.execute(
                        "INSERT INTO sandbox_migration_history VALUES (?, 0, ?, ?, ?)",
                        (
                            _MIGRATION_ID,
                            SANDBOX_SCHEMA_VERSION,
                            _MIGRATION_CHECKSUM,
                            _timestamp(applied_at),
                        ),
                    )
                    connection.commit()
                except sqlite3.Error as exc:
                    connection.rollback()
                    raise SandboxPersistenceCorrupt("sandbox migration failed") from exc
            self.verify(connection)

    def verify(self, connection: sqlite3.Connection | None = None) -> None:
        manager = self.connection() if connection is None else _existing(connection)
        with manager as active:
            expected = {"sandbox_schema_metadata", "sandbox_migration_history", *_TABLES.values()}
            if self._tables(active) != expected:
                raise SandboxPersistenceCorrupt("sandbox schema is incomplete")
            objects = active.execute(
                "SELECT type, name FROM sqlite_master WHERE type IN ('index', 'trigger')"
            ).fetchall()
            indexes = {
                row[1] for row in objects if row[0] == "index" and not row[1].startswith("sqlite_")
            }
            triggers = {row[1] for row in objects if row[0] == "trigger"}
            expected_indexes = {f"{table}_stream" for table in _TABLES.values()}
            expected_triggers = {
                f"{table}_no_{operation}"
                for table in _TABLES.values()
                for operation in ("update", "delete")
            }
            expected_triggers.update(
                {"sandbox_migration_history_no_update", "sandbox_migration_history_no_delete"}
            )
            if indexes != expected_indexes or triggers != expected_triggers:
                raise SandboxPersistenceCorrupt("sandbox schema protections are incomplete")
            for table in _TABLES.values():
                columns = tuple(row[1] for row in active.execute(f"PRAGMA table_info({table})"))
                if columns != _RECORD_COLUMNS:
                    raise SandboxPersistenceCorrupt("sandbox record schema is invalid")
            version = active.execute(
                "SELECT schema_version FROM sandbox_schema_metadata WHERE singleton=1"
            ).fetchone()
            if version is None or version[0] != SANDBOX_SCHEMA_VERSION:
                raise SandboxPersistenceVersionUnsupported("sandbox schema version unsupported")
            migration = active.execute(
                "SELECT from_version, to_version, checksum FROM sandbox_migration_history WHERE migration_id=?",
                (_MIGRATION_ID,),
            ).fetchone()
            if migration is None or tuple(migration) != (
                0,
                SANDBOX_SCHEMA_VERSION,
                _MIGRATION_CHECKSUM,
            ):
                raise SandboxPersistenceMigrationMismatch("sandbox migration checksum mismatch")
            if active.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise SandboxPersistenceCorrupt("sandbox database integrity failed")

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not str(row[0]).startswith("sqlite_")
        }


@contextmanager
def _existing(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    yield connection


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _checksum(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("ascii")).hexdigest()


class SQLiteSandboxArtifactStore(SandboxArtifactStore):
    def __init__(
        self, database: SandboxSQLiteDatabase, responsibility: SandboxStoreResponsibility
    ) -> None:
        self._database = database
        self._responsibility = responsibility
        self._table = _TABLES[responsibility]

    def append(self, draft: SandboxRecordDraft) -> SandboxWriteResult:
        if draft.responsibility is not self._responsibility:
            raise SandboxPersistenceConflict("record belongs to a different store")
        if _ARTIFACT_RESPONSIBILITY[draft.artifact_kind] is not self._responsibility:
            raise SandboxPersistenceConflict("artifact kind belongs to a different store")
        payload = canonical_bytes(draft.payload).decode("ascii")
        values = (
            draft.semantic_identity,
            draft.semantic_fingerprint,
            draft.artifact_kind.value,
            draft.stream_identity,
            draft.sequence,
            draft.idempotency_key,
            draft.record_format,
            draft.schema_version,
            payload,
            _checksum(payload),
            json.dumps(draft.lineage_fingerprints),
            draft.completeness.value,
            draft.recovery_state.value,
            _timestamp(draft.occurrence.occurred_at),
            _timestamp(draft.occurrence.observed_at),
            draft.occurrence.source_ref,
            draft.occurrence.correlation_ref,
            draft.retention.policy_ref,
            _timestamp(draft.retention.retain_until) if draft.retention.retain_until else None,
            int(draft.retention.legal_hold),
            int(draft.retention.purge_eligible),
        )
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                f"SELECT * FROM {self._table} WHERE idempotency_key=? OR semantic_identity=?",
                (draft.idempotency_key, draft.semantic_identity),
            ).fetchall()
            if existing:
                if (
                    len(existing) == 1
                    and existing[0]["semantic_fingerprint"] == draft.semantic_fingerprint
                ):
                    connection.rollback()
                    return SandboxWriteResult(
                        SandboxWriteDisposition.REPLAYED, self._decode(connection, existing[0])
                    )
                connection.rollback()
                raise SandboxPersistenceConflict("sandbox idempotency or identity conflict")
            current = connection.execute(
                f"SELECT COALESCE(MAX(sequence), 0) FROM {self._table} WHERE stream_identity=?",
                (draft.stream_identity,),
            ).fetchone()[0]
            if current != draft.expected_stream_version:
                connection.rollback()
                raise SandboxPersistenceConflict("sandbox optimistic concurrency conflict")
            if draft.sequence != draft.expected_stream_version + 1:
                connection.rollback()
                raise SandboxPersistenceConflict("sandbox causal sequence conflict")
            try:
                connection.execute(
                    f"INSERT INTO {self._table} VALUES ({','.join('?' for _ in values)})", values
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise SandboxPersistenceConflict("sandbox append conflict") from exc
            return SandboxWriteResult(
                SandboxWriteDisposition.APPENDED,
                self.get_exact(draft.semantic_identity, draft.semantic_fingerprint),
            )

    def get_exact(self, semantic_identity: str, fingerprint: str) -> SandboxPersistedRecord:
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT * FROM {self._table} WHERE semantic_identity=? AND semantic_fingerprint=?",
                (semantic_identity, fingerprint),
            ).fetchone()
            if row is None:
                raise SandboxPersistenceRecordNotFound("sandbox record not found")
            return self._decode(connection, row)

    def replay(self, stream_identity: str) -> SandboxReplay:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM {self._table} WHERE stream_identity=? ORDER BY sequence",
                (stream_identity,),
            ).fetchall()
            records = tuple(self._decode(connection, row) for row in rows)
        sequences = {record.sequence for record in records}
        missing_sequences = tuple(
            index for index in range(1, max(sequences, default=0) + 1) if index not in sequences
        )
        missing_lineage = tuple(
            sorted({item for record in records for item in record.missing_lineage_fingerprints})
        )
        return SandboxReplay(
            stream_identity,
            records,
            missing_sequences,
            missing_lineage,
            not missing_sequences and not missing_lineage,
        )

    def _decode(self, connection: sqlite3.Connection, row: sqlite3.Row) -> SandboxPersistedRecord:
        if (
            row["record_format"] != SANDBOX_RECORD_FORMAT
            or row["schema_version"] != SANDBOX_SCHEMA_VERSION
        ):
            raise SandboxPersistenceVersionUnsupported("sandbox record version unsupported")
        if _checksum(row["payload"]) != row["payload_checksum"]:
            raise SandboxPersistenceCorrupt("sandbox record checksum invalid")
        try:
            lineage = tuple(json.loads(row["lineage"]))
            SandboxArtifactKind(row["artifact_kind"])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SandboxPersistenceCorrupt("sandbox record encoding invalid") from exc
        missing = tuple(
            fingerprint
            for fingerprint in lineage
            if not self._fingerprint_exists(connection, fingerprint)
        )
        retain_until = datetime.fromisoformat(row["retain_until"]) if row["retain_until"] else None
        return SandboxPersistedRecord(
            self._responsibility,
            SandboxArtifactKind(row["artifact_kind"]),
            row["semantic_identity"],
            row["semantic_fingerprint"],
            row["stream_identity"],
            row["sequence"],
            row["payload"],
            row["payload_checksum"],
            lineage,
            missing,
            SandboxOccurrenceMetadata(
                datetime.fromisoformat(row["occurred_at"]),
                datetime.fromisoformat(row["observed_at"]),
                row["source_ref"],
                row["correlation_ref"],
            ),
            SandboxRetentionMetadata(
                row["retention_policy_ref"],
                retain_until,
                bool(row["legal_hold"]),
                bool(row["purge_eligible"]),
            ),
            SandboxCompleteness(row["completeness"]),
            SandboxRecoveryState(row["recovery_state"]),
            row["record_format"],
            row["schema_version"],
        )

    @staticmethod
    def _fingerprint_exists(connection: sqlite3.Connection, fingerprint: str) -> bool:
        return any(
            connection.execute(
                f"SELECT 1 FROM {table} WHERE semantic_fingerprint=?", (fingerprint,)
            ).fetchone()
            is not None
            for table in _TABLES.values()
        )


class SQLiteSandboxCatalogStore(SQLiteSandboxArtifactStore):
    def __init__(self, database: SandboxSQLiteDatabase) -> None:
        super().__init__(database, SandboxStoreResponsibility.CATALOG)


class SQLiteSandboxAdmissionStore(SQLiteSandboxArtifactStore):
    def __init__(self, database: SandboxSQLiteDatabase) -> None:
        super().__init__(database, SandboxStoreResponsibility.ADMISSION)


class SQLiteSandboxLifecycleStore(SQLiteSandboxArtifactStore):
    def __init__(self, database: SandboxSQLiteDatabase) -> None:
        super().__init__(database, SandboxStoreResponsibility.LIFECYCLE)


class SQLiteSandboxResultStore(SQLiteSandboxArtifactStore):
    def __init__(self, database: SandboxSQLiteDatabase) -> None:
        super().__init__(database, SandboxStoreResponsibility.RESULT)


class SQLiteSandboxRecoveryReader:
    """Projects persisted incomplete facts; it performs no operational recovery."""

    def __init__(self, database: SandboxSQLiteDatabase) -> None:
        self._database = database

    def findings(self) -> tuple[SandboxRecoveryFinding, ...]:
        findings: list[SandboxRecoveryFinding] = []
        explicit: set[str] = set()
        with self._database.connection() as connection:
            for table in _TABLES.values():
                rows = connection.execute(
                    f"SELECT stream_identity, semantic_identity, recovery_state, completeness, semantic_fingerprint "
                    f"FROM {table} WHERE recovery_state != ? OR completeness != ? "
                    "ORDER BY stream_identity, sequence",
                    (SandboxRecoveryState.NONE.value, SandboxCompleteness.COMPLETE.value),
                ).fetchall()
                projected = [
                    SandboxRecoveryFinding(
                        row[0],
                        row[1],
                        SandboxRecoveryState(row[2]),
                        SandboxCompleteness(row[3]),
                        row[4],
                    )
                    for row in rows
                ]
                findings.extend(projected)
                explicit.update(finding.fact_fingerprint for finding in projected)
            all_rows = connection.execute(
                " UNION ALL ".join(
                    f"SELECT stream_identity, semantic_identity, artifact_kind, semantic_fingerprint FROM {table}"
                    for table in _TABLES.values()
                )
                + " ORDER BY stream_identity, semantic_identity"
            ).fetchall()
            by_stream: dict[str, list[sqlite3.Row]] = {}
            for row in all_rows:
                by_stream.setdefault(row[0], []).append(row)
            for stream, rows in by_stream.items():
                kinds = {SandboxArtifactKind(row[2]) for row in rows}
                candidates = (
                    (
                        SandboxArtifactKind.EXECUTION_ATTEMPT,
                        SandboxArtifactKind.EXECUTION_RESULT,
                        SandboxRecoveryState.ATTEMPT_INCOMPLETE,
                    ),
                    (
                        SandboxArtifactKind.CANCELLATION_DECISION,
                        SandboxArtifactKind.CANCELLATION_RESULT,
                        SandboxRecoveryState.CANCELLATION_IN_PROGRESS,
                    ),
                    (
                        SandboxArtifactKind.EVIDENCE_ITEM,
                        SandboxArtifactKind.EVIDENCE_BUNDLE,
                        SandboxRecoveryState.EVIDENCE_INCOMPLETE,
                    ),
                )
                for start, terminal, state in candidates:
                    if start in kinds and terminal not in kinds:
                        fact = next(row for row in rows if row[2] == start.value)
                        if fact[3] not in explicit:
                            findings.append(
                                SandboxRecoveryFinding(
                                    stream,
                                    fact[1],
                                    state,
                                    SandboxCompleteness.PARTIAL,
                                    fact[3],
                                )
                            )
        return tuple(findings)
