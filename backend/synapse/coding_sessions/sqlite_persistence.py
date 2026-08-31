"""SQLite V1 adapters for Coding Sessions append-only persistence ports."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from .errors import (
    CodingSessionPersistenceCorrupt,
    CodingSessionPersistenceMigrationMismatch,
    CodingSessionPersistenceUnavailable,
    CodingSessionVersionMismatch,
)
from .identities import (
    CodingSessionCheckpointIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionPersistenceRecordIdentity,
)
from .persistence import (
    CODING_SESSION_RECORD_VERSION,
    CodingSessionArtifactExistenceRequest,
    CodingSessionCausalRangeReadRequest,
    CodingSessionCheckpointPersistenceEvidence,
    CodingSessionCheckpointPersistenceState,
    CodingSessionExactRecordReadRequest,
    CodingSessionExactRecordReadResult,
    CodingSessionPersistenceFailure,
    CodingSessionPersistenceFailureCode,
    CodingSessionPersistenceStream,
    CodingSessionRecordAppendAssessment,
    CodingSessionRecordAppendRequest,
    CodingSessionRecordAppendStatus,
    CodingSessionRecordEnvelope,
    CodingSessionReplayRequest,
    CodingSessionReplayResult,
    CodingSessionRetentionMetadata,
    CodingSessionStreamCompletenessAssessment,
)

CODING_SESSION_SQLITE_SCHEMA_VERSION = 1
_MIGRATION_ID = "coding-sessions-sqlite-v1"
_TABLES = {
    CodingSessionPersistenceStream.CONTRACT_BINDINGS: "coding_session_contract_records",
    CodingSessionPersistenceStream.LIFECYCLE_COORDINATION: "coding_session_lifecycle_records",
    CodingSessionPersistenceStream.INTENTS_RECEIPTS: "coding_session_intent_records",
    CodingSessionPersistenceStream.JOURNAL_CHECKPOINTS: "coding_session_journal_records",
    CodingSessionPersistenceStream.CONTROL_CANCELLATION: "coding_session_control_records",
    CodingSessionPersistenceStream.RESTART_RECONCILIATION: "coding_session_restart_records",
    CodingSessionPersistenceStream.RECOVERY_OUTCOME: "coding_session_recovery_records",
}
_BASE_SCHEMA = """
CREATE TABLE coding_session_schema_metadata (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    schema_version INTEGER NOT NULL
);
CREATE TABLE coding_session_migration_history (
    migration_id TEXT PRIMARY KEY,
    from_version INTEGER NOT NULL,
    to_version INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
CREATE TRIGGER coding_session_migration_no_update
BEFORE UPDATE ON coding_session_migration_history
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER coding_session_migration_no_delete
BEFORE DELETE ON coding_session_migration_history
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""
_RECORD_SCHEMA = """
CREATE TABLE {table} (
    record_identity TEXT PRIMARY KEY,
    session_identity TEXT NOT NULL,
    stream TEXT NOT NULL,
    category TEXT NOT NULL,
    semantic_artifact_identity TEXT NOT NULL,
    canonical_payload TEXT NOT NULL,
    canonical_payload_fingerprint TEXT NOT NULL,
    payload_checksum TEXT NOT NULL,
    record_version TEXT NOT NULL,
    causal_revision INTEGER NOT NULL CHECK(causal_revision >= 1),
    parent_record_fingerprint TEXT,
    lineage TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    occurrence_metadata TEXT NOT NULL,
    retention_metadata TEXT,
    record_fingerprint TEXT NOT NULL UNIQUE,
    UNIQUE(session_identity, stream, causal_revision)
);
CREATE INDEX {table}_causal_range
ON {table}(session_identity, stream, causal_revision);
CREATE INDEX {table}_artifact
ON {table}(session_identity, stream, semantic_artifact_identity, canonical_payload_fingerprint);
CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""
_V1_SQL = _BASE_SCHEMA + "".join(
    _RECORD_SCHEMA.format(table=table) for table in _TABLES.values()
)
CODING_SESSION_SQLITE_MIGRATION_V1_CHECKSUM = "sha256:" + hashlib.sha256(
    f"id={_MIGRATION_ID}\nfrom=0\nto=1\n{' '.join(_V1_SQL.split())}".encode("ascii")
).hexdigest()


@dataclass(frozen=True, slots=True)
class CodingSessionSQLiteConfig:
    database_path: str
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not self.database_path or self.timeout_seconds <= 0:
            raise CodingSessionPersistenceUnavailable()


class CodingSessionSQLiteDatabase:
    def __init__(self, config: CodingSessionSQLiteConfig) -> None:
        self._config = config

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(
                self._config.database_path, timeout=self._config.timeout_seconds
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
        except sqlite3.Error as exc:
            raise CodingSessionPersistenceUnavailable() from exc
        finally:
            if "connection" in locals():
                connection.close()

    def migrate(self, *, applied_at: str) -> None:
        if not applied_at:
            raise CodingSessionPersistenceMigrationMismatch()
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.executescript(_V1_SQL)
                connection.execute(
                    "INSERT INTO coding_session_schema_metadata VALUES (1, ?)",
                    (CODING_SESSION_SQLITE_SCHEMA_VERSION,),
                )
                connection.execute(
                    "INSERT INTO coding_session_migration_history VALUES (?, 0, 1, ?, ?)",
                    (
                        _MIGRATION_ID,
                        CODING_SESSION_SQLITE_MIGRATION_V1_CHECKSUM,
                        applied_at,
                    ),
                )
                connection.execute(
                    f"PRAGMA user_version={CODING_SESSION_SQLITE_SCHEMA_VERSION}"
                )
                connection.commit()
            elif version != CODING_SESSION_SQLITE_SCHEMA_VERSION:
                raise CodingSessionVersionMismatch()
        self.verify()

    def verify(self) -> None:
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            metadata = connection.execute(
                "SELECT schema_version FROM coding_session_schema_metadata WHERE singleton=1"
            ).fetchone()
            migration = connection.execute(
                "SELECT migration_id, from_version, to_version, checksum "
                "FROM coding_session_migration_history WHERE migration_id=?",
                (_MIGRATION_ID,),
            ).fetchone()
        if version != CODING_SESSION_SQLITE_SCHEMA_VERSION:
            raise CodingSessionVersionMismatch()
        if (
            metadata is None
            or metadata[0] != CODING_SESSION_SQLITE_SCHEMA_VERSION
            or migration is None
            or tuple(migration)
            != (_MIGRATION_ID, 0, 1, CODING_SESSION_SQLITE_MIGRATION_V1_CHECKSUM)
        ):
            raise CodingSessionPersistenceMigrationMismatch()


class SQLiteCodingSessionStreamStore:
    def __init__(
        self,
        database: CodingSessionSQLiteDatabase,
        stream: CodingSessionPersistenceStream,
    ) -> None:
        self._database = database
        self._stream = stream
        self._table = _TABLES[stream]

    def append(self, request: CodingSessionRecordAppendRequest) -> CodingSessionRecordAppendAssessment:
        record = request.record
        if record.stream is not self._stream:
            return _rejected(CodingSessionPersistenceFailureCode.DIVERGENT_DUPLICATE_IDENTITY)
        if record.record_version != CODING_SESSION_RECORD_VERSION:
            return _rejected(CodingSessionPersistenceFailureCode.UNSUPPORTED_RECORD_VERSION)
        if _payload_checksum(record.canonical_payload) != record.canonical_payload_fingerprint:
            return _rejected(CodingSessionPersistenceFailureCode.CORRUPTED_FINGERPRINT)
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = self._find_duplicate(connection, record)
            if duplicate is not None:
                existing = self._decode(connection, duplicate)
                if (
                    existing.idempotency_key == record.idempotency_key
                    and existing.semantic_fingerprint == record.semantic_fingerprint
                ):
                    connection.rollback()
                    return CodingSessionRecordAppendAssessment(
                        CodingSessionRecordAppendStatus.IDEMPOTENT,
                        (existing,),
                        existing,
                        (),
                    )
                connection.rollback()
                code = (
                    CodingSessionPersistenceFailureCode.IDEMPOTENCY_COLLISION
                    if existing.idempotency_key == record.idempotency_key
                    else CodingSessionPersistenceFailureCode.DIVERGENT_DUPLICATE_IDENTITY
                )
                return _rejected(code)
            rows = connection.execute(
                f"SELECT * FROM {self._table} WHERE session_identity=? AND stream=? "
                "ORDER BY causal_revision",
                (record.session_identity.value, self._stream.value),
            ).fetchall()
            existing_records = tuple(self._decode(connection, row) for row in rows)
            assessment = CodingSessionRecordAppendAssessment.assess(
                existing_records, request
            )
            if assessment.status is not CodingSessionRecordAppendStatus.APPENDED:
                connection.rollback()
                return assessment
            try:
                connection.execute(
                    f"INSERT INTO {self._table} VALUES ({','.join('?' for _ in range(16))})",
                    _encode(record),
                )
                connection.commit()
            except sqlite3.IntegrityError:
                connection.rollback()
                return _rejected(CodingSessionPersistenceFailureCode.CAUSAL_REVISION_CONFLICT)
        return CodingSessionRecordAppendAssessment(
            CodingSessionRecordAppendStatus.APPENDED,
            (*existing_records, record),
            record,
            (),
        )

    def read_exact(
        self, request: CodingSessionExactRecordReadRequest
    ) -> CodingSessionExactRecordReadResult:
        if request.stream is not self._stream:
            return _missing()
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT * FROM {self._table} WHERE session_identity=? "
                "AND record_identity=? AND record_fingerprint=?",
                (
                    request.session_identity.value,
                    request.record_identity.value,
                    request.expected_record_fingerprint.value,
                ),
            ).fetchone()
            if row is None:
                identity_row = connection.execute(
                    f"SELECT * FROM {self._table} WHERE session_identity=? AND record_identity=?",
                    (request.session_identity.value, request.record_identity.value),
                ).fetchone()
                if identity_row is None:
                    return _missing()
                self._decode(connection, identity_row)
                return CodingSessionExactRecordReadResult(
                    None,
                    (_failure(CodingSessionPersistenceFailureCode.CORRUPTED_FINGERPRINT),),
                )
            return CodingSessionExactRecordReadResult(self._decode(connection, row), ())

    def read_range(
        self, request: CodingSessionCausalRangeReadRequest
    ) -> tuple[CodingSessionRecordEnvelope, ...]:
        if request.stream is not self._stream:
            return ()
        with self._database.connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM {self._table} WHERE session_identity=? AND stream=? "
                "AND causal_revision BETWEEN ? AND ? ORDER BY causal_revision",
                (
                    request.session_identity.value,
                    request.stream.value,
                    request.from_revision,
                    request.through_revision,
                ),
            ).fetchall()
            return tuple(self._decode(connection, row) for row in rows)

    def exists_exact(self, request: CodingSessionArtifactExistenceRequest) -> bool:
        if request.stream is not self._stream:
            return False
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT * FROM {self._table} WHERE session_identity=? AND stream=? "
                "AND semantic_artifact_identity=? AND canonical_payload_fingerprint=?",
                (
                    request.session_identity.value,
                    request.stream.value,
                    request.semantic_artifact_identity,
                    request.canonical_payload_fingerprint.value,
                ),
            ).fetchone()
            return row is not None and self._decode(connection, row) is not None

    def assess_completeness(
        self, request: CodingSessionCausalRangeReadRequest
    ) -> CodingSessionStreamCompletenessAssessment:
        return CodingSessionStreamCompletenessAssessment.assess(
            request, self.read_range(request)
        )

    def checkpoint_persistence_evidence(
        self,
        request: CodingSessionExactRecordReadRequest,
        *,
        checkpoint_identity: CodingSessionCheckpointIdentity,
        checkpoint_fingerprint: CodingSessionFingerprint,
        structural_complete: bool,
        durable_ready: bool,
    ) -> CodingSessionCheckpointPersistenceEvidence:
        result = self.read_exact(request)
        if result.record is None:
            return CodingSessionCheckpointPersistenceEvidence(
                request.session_identity,
                checkpoint_identity,
                checkpoint_fingerprint,
                None,
                None,
                structural_complete,
                durable_ready,
                CodingSessionCheckpointPersistenceState.NOT_PERSISTED,
            )
        return CodingSessionCheckpointPersistenceEvidence(
            request.session_identity,
            checkpoint_identity,
            checkpoint_fingerprint,
            result.record.record_identity,
            result.record.record_fingerprint,
            structural_complete,
            durable_ready,
            CodingSessionCheckpointPersistenceState.PERSISTED,
        )

    def _find_duplicate(
        self, connection: sqlite3.Connection, record: CodingSessionRecordEnvelope
    ) -> sqlite3.Row | None:
        for table in _TABLES.values():
            row = connection.execute(
                f"SELECT * FROM {table} WHERE record_identity=? OR idempotency_key=?",
                (record.record_identity.value, record.idempotency_key.value),
            ).fetchone()
            if row is not None:
                return row
        return None

    def _decode(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> CodingSessionRecordEnvelope:
        try:
            if row["record_version"] != CODING_SESSION_RECORD_VERSION:
                raise CodingSessionVersionMismatch()
            if (
                row["payload_checksum"] != _payload_checksum_value(row["canonical_payload"])
                or row["canonical_payload_fingerprint"] != row["payload_checksum"]
            ):
                raise CodingSessionPersistenceCorrupt()
            lineage = tuple(
                CodingSessionFingerprint(value) for value in json.loads(row["lineage"])
            )
            occurrence = tuple(tuple(item) for item in json.loads(row["occurrence_metadata"]))
            retention_raw = json.loads(row["retention_metadata"])
            retention = (
                CodingSessionRetentionMetadata(*retention_raw)
                if retention_raw is not None
                else None
            )
            record = CodingSessionRecordEnvelope(
                CodingSessionPersistenceRecordIdentity(row["record_identity"]),
                CodingSessionIdentity(row["session_identity"]),
                CodingSessionPersistenceStream(row["stream"]),
                row["category"],
                row["semantic_artifact_identity"],
                row["canonical_payload"],
                CodingSessionFingerprint(row["canonical_payload_fingerprint"]),
                row["causal_revision"],
                CodingSessionFingerprint(row["parent_record_fingerprint"])
                if row["parent_record_fingerprint"]
                else None,
                lineage,
                CodingSessionFingerprint(row["idempotency_key"]),
                occurrence,
                retention,
                row["record_version"],
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CodingSessionPersistenceCorrupt() from exc
        if record.record_fingerprint.value != row["record_fingerprint"]:
            raise CodingSessionPersistenceCorrupt()
        parent = record.parent_record_fingerprint
        if parent is not None and not self._fingerprint_exists(connection, parent.value):
            raise CodingSessionPersistenceCorrupt()
        return record

    @staticmethod
    def _fingerprint_exists(connection: sqlite3.Connection, fingerprint: str) -> bool:
        return any(
            connection.execute(
                f"SELECT 1 FROM {table} WHERE record_fingerprint=?", (fingerprint,)
            ).fetchone()
            is not None
            for table in _TABLES.values()
        )


class SQLiteCodingSessionContractBindingsStore(SQLiteCodingSessionStreamStore):
    def __init__(self, database: CodingSessionSQLiteDatabase) -> None:
        super().__init__(database, CodingSessionPersistenceStream.CONTRACT_BINDINGS)

    append_contract_record = SQLiteCodingSessionStreamStore.append
    read_contract_record_exact = SQLiteCodingSessionStreamStore.read_exact
    contract_artifact_exists_exact = SQLiteCodingSessionStreamStore.exists_exact


class SQLiteCodingSessionLifecycleCoordinationStore(SQLiteCodingSessionStreamStore):
    def __init__(self, database: CodingSessionSQLiteDatabase) -> None:
        super().__init__(database, CodingSessionPersistenceStream.LIFECYCLE_COORDINATION)

    append_lifecycle_record = SQLiteCodingSessionStreamStore.append
    read_lifecycle_range = SQLiteCodingSessionStreamStore.read_range
    assess_lifecycle_completeness = SQLiteCodingSessionStreamStore.assess_completeness
    lifecycle_artifact_exists_exact = SQLiteCodingSessionStreamStore.exists_exact


class SQLiteCodingSessionIntentsReceiptsStore(SQLiteCodingSessionStreamStore):
    def __init__(self, database: CodingSessionSQLiteDatabase) -> None:
        super().__init__(database, CodingSessionPersistenceStream.INTENTS_RECEIPTS)

    append_intent_receipt_record = SQLiteCodingSessionStreamStore.append
    read_intent_receipt_range = SQLiteCodingSessionStreamStore.read_range
    read_intent_receipt_exact = SQLiteCodingSessionStreamStore.read_exact
    intent_receipt_artifact_exists_exact = SQLiteCodingSessionStreamStore.exists_exact


class SQLiteCodingSessionJournalCheckpointsStore(SQLiteCodingSessionStreamStore):
    def __init__(self, database: CodingSessionSQLiteDatabase) -> None:
        super().__init__(database, CodingSessionPersistenceStream.JOURNAL_CHECKPOINTS)

    append_journal_checkpoint_record = SQLiteCodingSessionStreamStore.append
    read_journal_checkpoint_range = SQLiteCodingSessionStreamStore.read_range
    read_checkpoint_exact = SQLiteCodingSessionStreamStore.read_exact
    checkpoint_artifact_exists_exact = SQLiteCodingSessionStreamStore.exists_exact


class SQLiteCodingSessionControlCancellationStore(SQLiteCodingSessionStreamStore):
    def __init__(self, database: CodingSessionSQLiteDatabase) -> None:
        super().__init__(database, CodingSessionPersistenceStream.CONTROL_CANCELLATION)

    append_control_record = SQLiteCodingSessionStreamStore.append
    read_control_range = SQLiteCodingSessionStreamStore.read_range
    control_artifact_exists_exact = SQLiteCodingSessionStreamStore.exists_exact


class SQLiteCodingSessionRestartReconciliationStore(SQLiteCodingSessionStreamStore):
    def __init__(self, database: CodingSessionSQLiteDatabase) -> None:
        super().__init__(database, CodingSessionPersistenceStream.RESTART_RECONCILIATION)

    append_restart_record = SQLiteCodingSessionStreamStore.append
    read_restart_range = SQLiteCodingSessionStreamStore.read_range
    restart_artifact_exists_exact = SQLiteCodingSessionStreamStore.exists_exact

    def replay_session(self, request: CodingSessionReplayRequest) -> CodingSessionReplayResult:
        records: list[CodingSessionRecordEnvelope] = []
        for range_request in request.ranges:
            store = SQLiteCodingSessionStreamStore(self._database, range_request.stream)
            records.extend(store.read_range(range_request))
        return CodingSessionReplayResult.project(request, tuple(records))


class SQLiteCodingSessionRecoveryOutcomeStore(SQLiteCodingSessionStreamStore):
    def __init__(self, database: CodingSessionSQLiteDatabase) -> None:
        super().__init__(database, CodingSessionPersistenceStream.RECOVERY_OUTCOME)

    append_recovery_record = SQLiteCodingSessionStreamStore.append
    read_recovery_range = SQLiteCodingSessionStreamStore.read_range
    read_recovery_record_exact = SQLiteCodingSessionStreamStore.read_exact
    recovery_artifact_exists_exact = SQLiteCodingSessionStreamStore.exists_exact


def _encode(record: CodingSessionRecordEnvelope) -> tuple[object, ...]:
    retention = (
        json.dumps(
            (
                record.retention_metadata.policy_version,
                record.retention_metadata.classification,
                record.retention_metadata.retain_until,
            ),
            separators=(",", ":"),
        )
        if record.retention_metadata
        else "null"
    )
    return (
        record.record_identity.value,
        record.session_identity.value,
        record.stream.value,
        record.category,
        record.semantic_artifact_identity,
        record.canonical_payload,
        record.canonical_payload_fingerprint.value,
        _payload_checksum_value(record.canonical_payload),
        record.record_version,
        record.causal_revision,
        record.parent_record_fingerprint.value if record.parent_record_fingerprint else None,
        json.dumps(tuple(item.value for item in record.lineage), separators=(",", ":")),
        record.idempotency_key.value,
        json.dumps(record.occurrence_metadata, separators=(",", ":")),
        retention,
        record.record_fingerprint.value,
    )


def _payload_checksum_value(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("ascii")).hexdigest()


def _payload_checksum(payload: str) -> CodingSessionFingerprint:
    return CodingSessionFingerprint(_payload_checksum_value(payload))


def _failure(code: CodingSessionPersistenceFailureCode) -> CodingSessionPersistenceFailure:
    return CodingSessionPersistenceFailure(code)


def _rejected(code: CodingSessionPersistenceFailureCode) -> CodingSessionRecordAppendAssessment:
    return CodingSessionRecordAppendAssessment(
        CodingSessionRecordAppendStatus.REJECTED, (), None, (_failure(code),)
    )


def _missing() -> CodingSessionExactRecordReadResult:
    return CodingSessionExactRecordReadResult(
        None, (_failure(CodingSessionPersistenceFailureCode.MISSING_ARTIFACT),)
    )
