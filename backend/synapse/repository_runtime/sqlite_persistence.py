"""SQLite V1 adapters for durable append-only Repository Runtime records."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

from .canonical import canonical_bytes
from .errors import (
    RepositoryPersistenceConflict,
    RepositoryPersistenceCorrupt,
    RepositoryPersistenceMigrationMismatch,
    RepositoryPersistenceRecordNotFound,
    RepositoryPersistenceUnavailable,
    RepositoryPersistenceVersionUnsupported,
)
from .identities import RepositoryFingerprint
from .persistence import (
    REPOSITORY_RECORD_FORMAT,
    REPOSITORY_SCHEMA_VERSION,
    RepositoryArtifactKind,
    RepositoryOccurrenceMetadata,
    RepositoryPersistedLifecycleState,
    RepositoryPersistedRecord,
    RepositoryRecordCompleteness,
    RepositoryRecordDraft,
    RepositoryReplay,
    RepositoryRestartState,
    RepositoryRetentionMetadata,
    RepositoryStoreResponsibility,
    RepositoryWriteDisposition,
    RepositoryWriteResult,
)
from .persistence_contracts import RepositoryArtifactStore

_TABLES = {
    RepositoryStoreResponsibility.OBSERVATION_SNAPSHOT: "repository_observation_records",
    RepositoryStoreResponsibility.PLANNING_AUTHORIZATION: "repository_planning_records",
    RepositoryStoreResponsibility.MUTATION_LIFECYCLE: "repository_mutation_records",
    RepositoryStoreResponsibility.RECOVERY_EVIDENCE: "repository_recovery_records",
}
_RESPONSIBILITY = {
    **{
        kind: RepositoryStoreResponsibility.OBSERVATION_SNAPSHOT
        for kind in (
            RepositoryArtifactKind.IDENTITY,
            RepositoryArtifactKind.PLATFORM_PROFILE,
            RepositoryArtifactKind.OBSERVATION,
            RepositoryArtifactKind.OBSERVATION_ASSESSMENT,
            RepositoryArtifactKind.PATH_CATALOG,
            RepositoryArtifactKind.SNAPSHOT,
        )
    },
    **{
        kind: RepositoryStoreResponsibility.PLANNING_AUTHORIZATION
        for kind in (
            RepositoryArtifactKind.CHANGE_SET,
            RepositoryArtifactKind.MUTATION_PLAN,
            RepositoryArtifactKind.AUTHORIZATION_FACT,
            RepositoryArtifactKind.AUTHORIZATION_ASSESSMENT,
            RepositoryArtifactKind.RESTORE_POINT_MANIFEST,
            RepositoryArtifactKind.RESTORE_POINT_VERIFICATION,
        )
    },
    **{
        kind: RepositoryStoreResponsibility.MUTATION_LIFECYCLE
        for kind in (
            RepositoryArtifactKind.MUTATION_ATTEMPT,
            RepositoryArtifactKind.MUTATION_JOURNAL,
            RepositoryArtifactKind.MUTATION_RESULT,
        )
    },
    **{
        kind: RepositoryStoreResponsibility.RECOVERY_EVIDENCE
        for kind in (
            RepositoryArtifactKind.REPOSITORY_VERIFICATION,
            RepositoryArtifactKind.RECONCILIATION,
            RepositoryArtifactKind.RECOVERY_PLAN,
            RepositoryArtifactKind.RECOVERY_ATTEMPT,
            RepositoryArtifactKind.RECOVERY_JOURNAL,
            RepositoryArtifactKind.RECOVERY_RESULT,
        )
    },
}
_MIGRATION_ID = "repository-runtime-persistence-v1"
_BASE_SCHEMA = """
CREATE TABLE repository_schema_metadata (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1), schema_version INTEGER NOT NULL
);
CREATE TABLE repository_migration_history (
    migration_id TEXT PRIMARY KEY, from_version INTEGER NOT NULL,
    to_version INTEGER NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL
);
CREATE TRIGGER repository_migration_history_no_update BEFORE UPDATE ON repository_migration_history
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER repository_migration_history_no_delete BEFORE DELETE ON repository_migration_history
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""
_RECORD_SCHEMA = """
CREATE TABLE {table} (
    semantic_identity TEXT NOT NULL,
    semantic_fingerprint TEXT NOT NULL UNIQUE,
    artifact_kind TEXT NOT NULL,
    stream_identity TEXT NOT NULL,
    causal_revision INTEGER NOT NULL CHECK(causal_revision >= 1),
    idempotency_key TEXT NOT NULL UNIQUE,
    record_format TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    payload_checksum TEXT NOT NULL,
    lineage TEXT NOT NULL,
    completeness TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    correlation_reference TEXT,
    retention_policy_reference TEXT NOT NULL,
    retain_until TEXT,
    legal_hold INTEGER NOT NULL CHECK(legal_hold IN (0, 1)),
    purge_eligible INTEGER NOT NULL CHECK(purge_eligible IN (0, 1)),
    PRIMARY KEY(semantic_identity, semantic_fingerprint),
    UNIQUE(stream_identity, causal_revision)
);
CREATE INDEX {table}_stream ON {table}(stream_identity, causal_revision);
CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""
_V1_SQL = _BASE_SCHEMA + "".join(_RECORD_SCHEMA.format(table=table) for table in _TABLES.values())
REPOSITORY_MIGRATION_V1_CHECKSUM = (
    "sha256:"
    + hashlib.sha256(
        f"id={_MIGRATION_ID}\nfrom=0\nto=1\n{' '.join(_V1_SQL.split())}".encode("ascii")
    ).hexdigest()
)


@dataclass(frozen=True, slots=True)
class RepositorySQLiteConfig:
    database_path: str
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not self.database_path or self.timeout_seconds <= 0:
            raise RepositoryPersistenceUnavailable("repository SQLite config is invalid")


class RepositorySQLiteDatabase:
    def __init__(self, config: RepositorySQLiteConfig) -> None:
        self._config = config

    @property
    def database_path(self) -> str:
        return self._config.database_path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(self.database_path, timeout=self._config.timeout_seconds)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
        except sqlite3.Error as exc:
            raise RepositoryPersistenceUnavailable("repository SQLite operation failed") from exc
        finally:
            if "connection" in locals():
                connection.close()

    def migrate(self, applied_at: datetime) -> None:
        if applied_at.tzinfo is None or applied_at.utcoffset() is None:
            raise RepositoryPersistenceMigrationMismatch(
                "migration timestamp must be timezone-aware"
            )
        with self.connection() as connection:
            current = connection.execute("PRAGMA user_version").fetchone()[0]
            if current == 0:
                connection.executescript(_V1_SQL)
                connection.execute("INSERT INTO repository_schema_metadata VALUES (1, 1)")
                connection.execute(
                    "INSERT INTO repository_migration_history VALUES (?, 0, 1, ?, ?)",
                    (_MIGRATION_ID, REPOSITORY_MIGRATION_V1_CHECKSUM, _timestamp(applied_at)),
                )
                connection.execute("PRAGMA user_version=1")
                connection.commit()
            elif current != REPOSITORY_SCHEMA_VERSION:
                raise RepositoryPersistenceVersionUnsupported(
                    "repository schema version unsupported"
                )
        self.verify()

    def verify(self) -> None:
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            row = connection.execute(
                "SELECT migration_id, from_version, to_version, checksum FROM repository_migration_history WHERE migration_id=?",
                (_MIGRATION_ID,),
            ).fetchone()
            metadata = connection.execute(
                "SELECT schema_version FROM repository_schema_metadata WHERE singleton=1"
            ).fetchone()
        if version != REPOSITORY_SCHEMA_VERSION:
            raise RepositoryPersistenceVersionUnsupported("repository schema version unsupported")
        if (
            row is None
            or metadata is None
            or tuple(row) != (_MIGRATION_ID, 0, 1, REPOSITORY_MIGRATION_V1_CHECKSUM)
            or metadata[0] != REPOSITORY_SCHEMA_VERSION
        ):
            raise RepositoryPersistenceMigrationMismatch("repository migration checksum mismatch")


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _checksum(payload: str) -> RepositoryFingerprint:
    return RepositoryFingerprint("sha256:" + hashlib.sha256(payload.encode("ascii")).hexdigest())


class SQLiteRepositoryArtifactStore(RepositoryArtifactStore):
    def __init__(
        self, database: RepositorySQLiteDatabase, responsibility: RepositoryStoreResponsibility
    ) -> None:
        self._database = database
        self._responsibility = responsibility
        self._table = _TABLES[responsibility]

    def append(self, draft: RepositoryRecordDraft) -> RepositoryWriteResult:
        if (
            draft.responsibility is not self._responsibility
            or _RESPONSIBILITY.get(draft.artifact_kind) is not self._responsibility
        ):
            raise RepositoryPersistenceConflict("artifact belongs to a different repository store")
        payload = canonical_bytes(draft.payload).decode("ascii")
        lineage = json.dumps(
            tuple(item.value for item in draft.lineage_fingerprints), separators=(",", ":")
        )
        values = (
            draft.semantic_identity,
            draft.semantic_fingerprint.value,
            draft.artifact_kind.value,
            draft.stream_identity,
            draft.causal_revision,
            draft.idempotency_key,
            draft.record_format,
            draft.schema_version,
            payload,
            _checksum(payload).value,
            lineage,
            draft.completeness.value,
            draft.lifecycle_state.value,
            _timestamp(draft.occurrence.occurred_at),
            _timestamp(draft.occurrence.observed_at),
            draft.occurrence.source_reference,
            draft.occurrence.correlation_reference,
            draft.retention.policy_reference,
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
                    and existing[0]["semantic_fingerprint"] == draft.semantic_fingerprint.value
                ):
                    connection.rollback()
                    return RepositoryWriteResult(
                        RepositoryWriteDisposition.REPLAYED, self._decode(connection, existing[0])
                    )
                connection.rollback()
                raise RepositoryPersistenceConflict("repository identity or idempotency conflict")
            current = connection.execute(
                f"SELECT COALESCE(MAX(causal_revision), 0) FROM {self._table} WHERE stream_identity=?",
                (draft.stream_identity,),
            ).fetchone()[0]
            if current != draft.expected_causal_revision:
                connection.rollback()
                raise RepositoryPersistenceConflict("repository stream conflict")
            try:
                connection.execute(
                    f"INSERT INTO {self._table} VALUES ({','.join('?' for _ in values)})", values
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise RepositoryPersistenceConflict("repository causal revision conflict") from exc
        return RepositoryWriteResult(
            RepositoryWriteDisposition.APPENDED,
            self.get_exact(draft.semantic_identity, draft.semantic_fingerprint.value),
        )

    def get_exact(self, semantic_identity: str, fingerprint: str) -> RepositoryPersistedRecord:
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT * FROM {self._table} WHERE semantic_identity=? AND semantic_fingerprint=?",
                (semantic_identity, fingerprint),
            ).fetchone()
            if row is None:
                raise RepositoryPersistenceRecordNotFound("repository artifact not found")
            return self._decode(connection, row)

    def replay(self, stream_identity: str) -> RepositoryReplay:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM {self._table} WHERE stream_identity=? ORDER BY causal_revision",
                (stream_identity,),
            ).fetchall()
            records = tuple(self._decode(connection, row) for row in rows)
        revisions = {item.causal_revision for item in records}
        missing_revisions = tuple(
            index for index in range(1, max(revisions, default=0) + 1) if index not in revisions
        )
        missing_lineage = tuple(
            sorted(
                {item for record in records for item in record.missing_lineage_fingerprints},
                key=lambda item: item.value,
            )
        )
        return RepositoryReplay(
            stream_identity,
            records,
            missing_revisions,
            missing_lineage,
            bool(records) and not missing_revisions and not missing_lineage,
        )

    def restart_state(self, stream_identity: str) -> RepositoryRestartState:
        replay = self.replay(stream_identity)
        states = tuple(item.lifecycle_state for item in replay.records)
        completeness = (
            RepositoryRecordCompleteness.COMPLETE
            if replay.complete
            and all(
                item.completeness is RepositoryRecordCompleteness.COMPLETE
                for item in replay.records
            )
            else RepositoryRecordCompleteness.PARTIAL
        )
        return RepositoryRestartState(
            stream_identity, replay.records, states, completeness, replay.complete
        )

    def _decode(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> RepositoryPersistedRecord:
        if (
            row["record_format"] != REPOSITORY_RECORD_FORMAT
            or row["schema_version"] != REPOSITORY_SCHEMA_VERSION
        ):
            raise RepositoryPersistenceVersionUnsupported("repository record version unsupported")
        checksum = _checksum(row["payload"])
        if checksum.value != row["payload_checksum"]:
            raise RepositoryPersistenceCorrupt("repository payload checksum invalid")
        try:
            lineage = tuple(RepositoryFingerprint(value) for value in json.loads(row["lineage"]))
            artifact_kind = RepositoryArtifactKind(row["artifact_kind"])
            completeness = RepositoryRecordCompleteness(row["completeness"])
            lifecycle = RepositoryPersistedLifecycleState(row["lifecycle_state"])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RepositoryPersistenceCorrupt("repository record encoding invalid") from exc
        missing = tuple(
            item for item in lineage if not self._fingerprint_exists(connection, item.value)
        )
        return RepositoryPersistedRecord(
            self._responsibility,
            artifact_kind,
            row["semantic_identity"],
            RepositoryFingerprint(row["semantic_fingerprint"]),
            row["stream_identity"],
            row["causal_revision"],
            row["idempotency_key"],
            row["payload"],
            checksum,
            checksum,
            lineage,
            missing,
            RepositoryOccurrenceMetadata(
                datetime.fromisoformat(row["occurred_at"]),
                datetime.fromisoformat(row["observed_at"]),
                row["source_reference"],
                row["correlation_reference"],
            ),
            RepositoryRetentionMetadata(
                row["retention_policy_reference"],
                datetime.fromisoformat(row["retain_until"]) if row["retain_until"] else None,
                bool(row["legal_hold"]),
                bool(row["purge_eligible"]),
            ),
            completeness,
            lifecycle,
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


class SQLiteRepositoryObservationSnapshotStore(SQLiteRepositoryArtifactStore):
    def __init__(self, database: RepositorySQLiteDatabase) -> None:
        super().__init__(database, RepositoryStoreResponsibility.OBSERVATION_SNAPSHOT)


class SQLiteRepositoryPlanningAuthorizationStore(SQLiteRepositoryArtifactStore):
    def __init__(self, database: RepositorySQLiteDatabase) -> None:
        super().__init__(database, RepositoryStoreResponsibility.PLANNING_AUTHORIZATION)


class SQLiteRepositoryMutationLifecycleStore(SQLiteRepositoryArtifactStore):
    def __init__(self, database: RepositorySQLiteDatabase) -> None:
        super().__init__(database, RepositoryStoreResponsibility.MUTATION_LIFECYCLE)


class SQLiteRepositoryRecoveryEvidenceStore(SQLiteRepositoryArtifactStore):
    def __init__(self, database: RepositorySQLiteDatabase) -> None:
        super().__init__(database, RepositoryStoreResponsibility.RECOVERY_EVIDENCE)
