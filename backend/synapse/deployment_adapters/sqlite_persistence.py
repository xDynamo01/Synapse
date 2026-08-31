"""SQLite V1 append-only journal adapter for Deployment facts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, TypeVar

from synapse.deployment.canonical import canonical_json
from synapse.deployment.errors import (
    DeploymentEventContradiction,
    DeploymentFencingConflict,
    DeploymentFencingIntegrityError,
    DeploymentFencingUnavailable,
    DeploymentIdempotencyContradiction,
    DeploymentPersistenceCorrupt,
    DeploymentPersistenceError,
    DeploymentPersistenceUnavailable,
    DeploymentReplayFailed,
    DeploymentSchemaIncompatible,
    DeploymentSequenceConflict,
    DeploymentSequenceGap,
)
from synapse.deployment.fencing import (
    DEPLOYMENT_FENCING_AUTHORITY_VERSION,
    DeploymentFencingHealthV1,
    DeploymentFencingScopeKind,
    DeploymentFencingScopeV1,
    DeploymentFencingTransitionRequestV1,
    DeploymentGeneration,
    DeploymentGenerationFactV1,
    DeploymentIdempotencyDisposition,
    DeploymentIdempotencyRecordV1,
    DeploymentIdempotencyRequestV1,
    DeploymentIdempotencyStatus,
    DeploymentMutationClass,
    replay_generation_history,
)
from synapse.deployment.identities import (
    ApplyReceiptReference,
    ArtifactReference,
    AuthorizationReference,
    CapabilityReference,
    CausationReference,
    CorrelationReference,
    DeploymentAttemptId,
    DeploymentEventId,
    DeploymentFingerprint,
    DeploymentIdempotencyKey,
    DeploymentTargetId,
    ObservationReference,
    OccurrenceReference,
    PromotionId,
    ReleaseId,
    RequesterReference,
    RevisionId,
    RollbackAttemptId,
    RollbackReceiptReference,
    RolloutId,
    SlotId,
    VerificationReference,
)
from synapse.deployment.persistence import (
    DEPLOYMENT_JOURNAL_FORMAT_V1,
    DEPLOYMENT_JOURNAL_SCHEMA_VERSION,
    DeploymentAppendDisposition,
    DeploymentAppendResult,
    DeploymentJournalAppendRequest,
    DeploymentJournalEvent,
    DeploymentJournalIntegrity,
    DeploymentJournalRecord,
    DeploymentMachineKey,
    DeploymentMachineKind,
    DeploymentPersistenceHealth,
    DeploymentProjection,
    machine_key_for,
    replay_deployment_history,
)
from synapse.deployment.state_machines import (
    DeploymentLifecycleState,
    DeploymentTransitionEventV1,
    PromotionLifecycleState,
    PromotionTransitionEventV1,
    RollbackLifecycleState,
    RollbackTransitionEventV1,
    RolloutLifecycleState,
    RolloutStageV1,
    RolloutTransitionEventV1,
    TransitionFailureClass,
)

_MIGRATION_ID = "deployment-journal-v1"
_SCHEMA = """
CREATE TABLE deployment_schema_metadata (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    schema_version INTEGER NOT NULL,
    record_format TEXT NOT NULL,
    migration_id TEXT NOT NULL,
    migration_checksum TEXT NOT NULL
);
CREATE TABLE deployment_journal_events (
    machine_kind TEXT NOT NULL,
    machine_identity TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence >= 1),
    event_identity TEXT NOT NULL UNIQUE,
    event_fingerprint TEXT NOT NULL,
    canonical_payload TEXT NOT NULL,
    payload_checksum TEXT NOT NULL,
    correlation_reference TEXT NOT NULL,
    causation_reference TEXT,
    occurrence_reference TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    record_format TEXT NOT NULL,
    PRIMARY KEY(machine_kind, machine_identity, sequence)
);
CREATE INDEX deployment_journal_machine
ON deployment_journal_events(machine_kind, machine_identity, sequence);
CREATE TRIGGER deployment_journal_no_update
BEFORE UPDATE ON deployment_journal_events
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER deployment_journal_no_delete
BEFORE DELETE ON deployment_journal_events
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""
_MIGRATION_CHECKSUM = hashlib.sha256(
    f"id={_MIGRATION_ID}\nfrom=0\nto=1\n{' '.join(_SCHEMA.split())}".encode()
).hexdigest()
_COLUMNS = (
    "machine_kind",
    "machine_identity",
    "sequence",
    "event_identity",
    "event_fingerprint",
    "canonical_payload",
    "payload_checksum",
    "correlation_reference",
    "causation_reference",
    "occurrence_reference",
    "schema_version",
    "record_format",
)

_AUTHORITY_MIGRATION_ID = "deployment-authority-v1"
_AUTHORITY_SCHEMA = """
CREATE TABLE deployment_authority_metadata (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    schema_version INTEGER NOT NULL,
    authority_version TEXT NOT NULL,
    migration_id TEXT NOT NULL,
    migration_checksum TEXT NOT NULL
);
CREATE TABLE deployment_fencing_history (
    scope_fingerprint TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK(generation >= 1),
    owner_reference TEXT NOT NULL,
    authority_identity TEXT NOT NULL,
    occurrence_reference TEXT NOT NULL,
    transition_fingerprint TEXT NOT NULL UNIQUE,
    fact_fingerprint TEXT NOT NULL UNIQUE,
    previous_fact_fingerprint TEXT,
    canonical_payload TEXT NOT NULL,
    payload_checksum TEXT NOT NULL,
    PRIMARY KEY(scope_fingerprint, generation)
);
CREATE INDEX deployment_fencing_scope_generation
ON deployment_fencing_history(scope_fingerprint, generation);
CREATE TRIGGER deployment_fencing_no_update
BEFORE UPDATE ON deployment_fencing_history
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER deployment_fencing_no_delete
BEFORE DELETE ON deployment_fencing_history
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TABLE deployment_idempotency_facts (
    idempotency_key TEXT NOT NULL,
    scope_fingerprint TEXT NOT NULL,
    operation TEXT NOT NULL,
    semantic_fingerprint TEXT NOT NULL,
    fencing_generation INTEGER NOT NULL CHECK(fencing_generation >= 1),
    canonical_payload TEXT NOT NULL,
    payload_checksum TEXT NOT NULL,
    PRIMARY KEY(operation, scope_fingerprint, idempotency_key)
);
CREATE TRIGGER deployment_idempotency_no_update
BEFORE UPDATE ON deployment_idempotency_facts
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER deployment_idempotency_no_delete
BEFORE DELETE ON deployment_idempotency_facts
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""
_AUTHORITY_MIGRATION_CHECKSUM = hashlib.sha256(
    f"id={_AUTHORITY_MIGRATION_ID}\nfrom=0\nto=1\n{' '.join(_AUTHORITY_SCHEMA.split())}".encode()
).hexdigest()


@dataclass(frozen=True, slots=True)
class DeploymentSQLiteConfig:
    database_path: Path
    busy_timeout_ms: int = 5_000

    def __post_init__(self) -> None:
        if (
            not isinstance(self.database_path, Path)
            or not self.database_path.is_absolute()
            or str(self.database_path).startswith(("\\\\", "//"))
            or ".." in self.database_path.parts
            or (self.database_path.exists() and self.database_path.is_dir())
            or (self.database_path.parent.exists() and self.database_path.parent.is_symlink())
            or isinstance(self.busy_timeout_ms, bool)
            or self.busy_timeout_ms <= 0
        ):
            raise ValueError("deployment SQLite configuration is invalid")


class SQLiteDeploymentJournalStore:
    def __init__(self, config: DeploymentSQLiteConfig) -> None:
        self._config = config

    @property
    def database_path(self) -> Path:
        return self._config.database_path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(
                str(self.database_path),
                timeout=self._config.busy_timeout_ms / 1_000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.enable_load_extension(False)
        except (OSError, sqlite3.Error) as exc:
            raise DeploymentPersistenceUnavailable("deployment persistence unavailable") from exc
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            tables = self._tables(connection)
            if not tables:
                try:
                    connection.executescript("BEGIN EXCLUSIVE;\n" + _SCHEMA)
                    connection.execute(
                        "INSERT INTO deployment_schema_metadata VALUES (1, ?, ?, ?, ?)",
                        (
                            DEPLOYMENT_JOURNAL_SCHEMA_VERSION,
                            DEPLOYMENT_JOURNAL_FORMAT_V1,
                            _MIGRATION_ID,
                            _MIGRATION_CHECKSUM,
                        ),
                    )
                    connection.commit()
                except sqlite3.Error as exc:
                    connection.rollback()
                    raise DeploymentPersistenceCorrupt(
                        "deployment schema initialization failed"
                    ) from exc
            self._verify_schema(connection)

    def append(self, request: DeploymentJournalAppendRequest) -> DeploymentAppendResult:
        payload = canonical_json(request.event)
        checksum = _checksum(payload)
        with self._connection() as connection:
            self._verify_schema(connection)
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM deployment_journal_events WHERE event_identity=?",
                    (request.event.event_id.value,),
                ).fetchone()
                if existing is not None:
                    record = self._decode(existing)
                    connection.rollback()
                    if record.machine == request.machine and record.canonical_payload == payload:
                        return DeploymentAppendResult(
                            DeploymentAppendDisposition.IDEMPOTENT, record
                        )
                    raise DeploymentEventContradiction(
                        "deployment event identity has contradictory content"
                    )
                latest = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(sequence),0) FROM deployment_journal_events "
                        "WHERE machine_kind=? AND machine_identity=?",
                        (request.machine.kind.value, request.machine.identity),
                    ).fetchone()[0]
                )
                expected = latest + 1
                if request.sequence > expected:
                    connection.rollback()
                    raise DeploymentSequenceGap("deployment journal sequence gap")
                if request.sequence < expected:
                    connection.rollback()
                    raise DeploymentSequenceConflict("deployment journal sequence conflict")
                values = (
                    request.machine.kind.value,
                    request.machine.identity,
                    request.sequence,
                    request.event.event_id.value,
                    request.event.fingerprint.value,
                    payload,
                    checksum,
                    request.event.correlation.value,
                    request.event.causation.value if request.event.causation else None,
                    request.event.occurrence.value,
                    DEPLOYMENT_JOURNAL_SCHEMA_VERSION,
                    DEPLOYMENT_JOURNAL_FORMAT_V1,
                )
                connection.execute(
                    f"INSERT INTO deployment_journal_events VALUES ({','.join('?' for _ in values)})",
                    values,
                )
                connection.commit()
            except (DeploymentPersistenceError, DeploymentSequenceConflict, DeploymentSequenceGap):
                raise
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise DeploymentSequenceConflict("deployment concurrent append conflict") from exc
            except sqlite3.Error as exc:
                connection.rollback()
                raise DeploymentPersistenceUnavailable("deployment append unavailable") from exc
        return DeploymentAppendResult(
            DeploymentAppendDisposition.APPENDED,
            self.history(request.machine)[-1],
        )

    def history(self, machine: DeploymentMachineKey) -> tuple[DeploymentJournalRecord, ...]:
        with self._connection() as connection:
            self._verify_schema(connection)
            rows = connection.execute(
                "SELECT * FROM deployment_journal_events "
                "WHERE machine_kind=? AND machine_identity=? ORDER BY sequence",
                (machine.kind.value, machine.identity),
            ).fetchall()
        records = tuple(self._decode(row) for row in rows)
        sequences = tuple(record.sequence for record in records)
        if sequences != tuple(range(1, len(records) + 1)):
            raise DeploymentSequenceGap("deployment stored history has a sequence gap")
        return records

    def latest_sequence(self, machine: DeploymentMachineKey) -> int:
        with self._connection() as connection:
            self._verify_schema(connection)
            return int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence),0) FROM deployment_journal_events "
                    "WHERE machine_kind=? AND machine_identity=?",
                    (machine.kind.value, machine.identity),
                ).fetchone()[0]
            )

    def replay(self, machine: DeploymentMachineKey) -> DeploymentProjection:
        try:
            return replay_deployment_history(machine, self.history(machine))
        except DeploymentReplayFailed:
            raise
        except (DeploymentPersistenceError, TypeError, ValueError) as exc:
            raise DeploymentReplayFailed("deployment replay failed closed") from exc

    def integrity_check(self) -> DeploymentJournalIntegrity:
        try:
            with self._connection() as connection:
                self._verify_schema(connection)
                keys = tuple(
                    DeploymentMachineKey(DeploymentMachineKind(row[0]), str(row[1]))
                    for row in connection.execute(
                        "SELECT DISTINCT machine_kind,machine_identity "
                        "FROM deployment_journal_events"
                    )
                )
            for key in keys:
                records = self.history(key)
                if records:
                    replay_deployment_history(key, records)
            return DeploymentJournalIntegrity(True, True, True, True, False)
        except DeploymentSchemaIncompatible:
            return DeploymentJournalIntegrity(True, False, False, False, True)
        except DeploymentPersistenceError:
            return DeploymentJournalIntegrity(True, True, False, False, True)
        except (OSError, sqlite3.Error):
            return DeploymentJournalIntegrity(False, False, False, False, False)

    def health(self) -> DeploymentPersistenceHealth:
        integrity = self.integrity_check()
        return DeploymentPersistenceHealth(
            integrity.store_available,
            integrity.schema_compatible,
            integrity.append_integrity,
            integrity.replay_available,
            integrity.corruption_detected,
        )

    def _verify_schema(self, connection: sqlite3.Connection) -> None:
        expected_tables = {"deployment_schema_metadata", "deployment_journal_events"}
        if not expected_tables.issubset(self._tables(connection)):
            raise DeploymentPersistenceCorrupt("deployment schema is incomplete")
        columns = tuple(
            row[1] for row in connection.execute("PRAGMA table_info(deployment_journal_events)")
        )
        if columns != _COLUMNS:
            raise DeploymentPersistenceCorrupt("deployment journal columns are invalid")
        objects = connection.execute(
            "SELECT type,name FROM sqlite_master WHERE type IN ('index','trigger')"
        ).fetchall()
        indexes = {
            row[1] for row in objects if row[0] == "index" and not row[1].startswith("sqlite_")
        }
        triggers = {row[1] for row in objects if row[0] == "trigger"}
        if not {"deployment_journal_machine"}.issubset(indexes) or not {
            "deployment_journal_no_update",
            "deployment_journal_no_delete",
        }.issubset(triggers):
            raise DeploymentPersistenceCorrupt("deployment append-only protections are incomplete")
        metadata = connection.execute(
            "SELECT schema_version,record_format,migration_id,migration_checksum "
            "FROM deployment_schema_metadata WHERE singleton=1"
        ).fetchone()
        if metadata is None or metadata[0] != DEPLOYMENT_JOURNAL_SCHEMA_VERSION:
            raise DeploymentSchemaIncompatible("deployment schema version unsupported")
        if tuple(metadata[1:]) != (
            DEPLOYMENT_JOURNAL_FORMAT_V1,
            _MIGRATION_ID,
            _MIGRATION_CHECKSUM,
        ):
            raise DeploymentSchemaIncompatible("deployment migration identity mismatch")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DeploymentPersistenceCorrupt("deployment SQLite integrity failed")

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not str(row[0]).startswith("sqlite_")
        }

    @staticmethod
    def _decode(row: sqlite3.Row) -> DeploymentJournalRecord:
        if (
            row["schema_version"] != DEPLOYMENT_JOURNAL_SCHEMA_VERSION
            or row["record_format"] != DEPLOYMENT_JOURNAL_FORMAT_V1
        ):
            raise DeploymentSchemaIncompatible("deployment record version unsupported")
        payload = str(row["canonical_payload"])
        if _checksum(payload) != row["payload_checksum"]:
            raise DeploymentPersistenceCorrupt("deployment payload checksum mismatch")
        try:
            raw = json.loads(payload)
            if canonical_json(raw) != payload:
                raise DeploymentPersistenceCorrupt("deployment payload is not canonical")
            kind = DeploymentMachineKind(row["machine_kind"])
            event = _decode_event(kind, raw)
            machine = DeploymentMachineKey(kind, str(row["machine_identity"]))
        except DeploymentPersistenceError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DeploymentPersistenceCorrupt("deployment payload is malformed") from exc
        if (
            machine_key_for(event) != machine
            or event.event_id.value != row["event_identity"]
            or event.fingerprint.value != row["event_fingerprint"]
            or event.correlation.value != row["correlation_reference"]
            or (event.causation.value if event.causation else None) != row["causation_reference"]
            or event.occurrence.value != row["occurrence_reference"]
        ):
            raise DeploymentPersistenceCorrupt("deployment record correspondence mismatch")
        return DeploymentJournalRecord(
            machine,
            int(row["sequence"]),
            event.event_id,
            event.fingerprint,
            event,
            payload,
            str(row["payload_checksum"]),
        )


class SQLiteDeploymentAuthorityStore:
    """Deployment-owned fencing/idempotency authority in the existing SQLite DB."""

    def __init__(self, config: DeploymentSQLiteConfig) -> None:
        self._config = config
        self._journal = SQLiteDeploymentJournalStore(config)

    @property
    def database_path(self) -> Path:
        return self._config.database_path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._journal._connection() as connection:
            yield connection

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        return SQLiteDeploymentJournalStore._tables(connection)

    def initialize(self) -> None:
        self._journal.initialize()
        with self._connection() as connection:
            if "deployment_authority_metadata" not in self._tables(connection):
                try:
                    connection.executescript("BEGIN EXCLUSIVE;\n" + _AUTHORITY_SCHEMA)
                    connection.execute(
                        "INSERT INTO deployment_authority_metadata VALUES (1, 1, ?, ?, ?)",
                        (
                            DEPLOYMENT_FENCING_AUTHORITY_VERSION,
                            _AUTHORITY_MIGRATION_ID,
                            _AUTHORITY_MIGRATION_CHECKSUM,
                        ),
                    )
                    connection.commit()
                except sqlite3.Error as exc:
                    connection.rollback()
                    raise DeploymentFencingIntegrityError(
                        "deployment authority schema initialization failed"
                    ) from exc
            self._verify_authority_schema(connection)

    def transition(
        self, request: DeploymentFencingTransitionRequestV1
    ) -> DeploymentGenerationFactV1:
        scope_key = request.scope.fingerprint.value
        with self._connection() as connection:
            self._verify_authority_schema(connection)
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM deployment_fencing_history "
                    "WHERE scope_fingerprint=? ORDER BY generation DESC LIMIT 1",
                    (scope_key,),
                ).fetchone()
                latest = self._decode_generation(row) if row is not None else None
                current = latest.generation.value if latest else 0
                if request.expected_generation != current:
                    connection.rollback()
                    raise DeploymentFencingConflict(
                        "deployment generation compare-and-advance conflict"
                    )
                fact = DeploymentGenerationFactV1.create(
                    request,
                    current + 1,
                    latest.fact_fingerprint if latest else None,
                )
                payload = canonical_json(fact)
                connection.execute(
                    "INSERT INTO deployment_fencing_history VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        scope_key,
                        fact.generation.value,
                        fact.owner.value,
                        fact.authority_identity.value,
                        fact.occurrence.value,
                        fact.transition_fingerprint.value,
                        fact.fact_fingerprint.value,
                        fact.previous_fact_fingerprint.value
                        if fact.previous_fact_fingerprint
                        else None,
                        payload,
                        _checksum(payload),
                    ),
                )
                connection.commit()
                return fact
            except DeploymentFencingConflict:
                raise
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise DeploymentFencingConflict(
                    "deployment generation transition conflicts"
                ) from exc
            except sqlite3.Error as exc:
                connection.rollback()
                raise DeploymentFencingUnavailable("deployment fencing store unavailable") from exc

    def latest(self, scope: DeploymentFencingScopeV1) -> DeploymentGenerationFactV1 | None:
        history = self.history(scope)
        return history[-1] if history else None

    def history(self, scope: DeploymentFencingScopeV1) -> tuple[DeploymentGenerationFactV1, ...]:
        with self._connection() as connection:
            self._verify_authority_schema(connection)
            rows = connection.execute(
                "SELECT * FROM deployment_fencing_history "
                "WHERE scope_fingerprint=? ORDER BY generation",
                (scope.fingerprint.value,),
            ).fetchall()
        facts = tuple(self._decode_generation(row) for row in rows)
        if any(fact.scope != scope for fact in facts):
            raise DeploymentFencingIntegrityError("deployment fencing scope mismatch")
        try:
            replay_generation_history(facts)
        except ValueError as exc:
            raise DeploymentFencingIntegrityError(
                "deployment generation history is corrupt"
            ) from exc
        return facts

    def record_idempotency(
        self,
        request: DeploymentIdempotencyRequestV1,
        generation: DeploymentGeneration,
    ) -> tuple[DeploymentIdempotencyDisposition, DeploymentIdempotencyRecordV1]:
        with self._connection() as connection:
            self._verify_authority_schema(connection)
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM deployment_idempotency_facts "
                    "WHERE operation=? AND scope_fingerprint=? AND idempotency_key=?",
                    (
                        request.operation.value,
                        request.scope.fingerprint.value,
                        request.idempotency_key.value,
                    ),
                ).fetchone()
                if row is not None:
                    existing = self._decode_idempotency(row)
                    connection.rollback()
                    if (
                        existing.operation == request.operation
                        and existing.scope == request.scope
                        and existing.semantic_fingerprint == request.semantic_fingerprint
                    ):
                        return DeploymentIdempotencyDisposition.IDEMPOTENT, existing
                    raise DeploymentIdempotencyContradiction(
                        "deployment idempotency key has contradictory semantics"
                    )
                record = DeploymentIdempotencyRecordV1(
                    request.operation,
                    request.scope,
                    request.idempotency_key,
                    request.semantic_fingerprint,
                    generation,
                    request.first_accepted_occurrence,
                )
                payload = canonical_json(record)
                connection.execute(
                    "INSERT INTO deployment_idempotency_facts VALUES (?,?,?,?,?,?,?)",
                    (
                        record.idempotency_key.value,
                        record.scope.fingerprint.value,
                        record.operation.value,
                        record.semantic_fingerprint.value,
                        record.fencing_generation.value,
                        payload,
                        _checksum(payload),
                    ),
                )
                connection.commit()
                return DeploymentIdempotencyDisposition.RECORDED, record
            except DeploymentIdempotencyContradiction:
                raise
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise DeploymentIdempotencyContradiction(
                    "deployment idempotency record conflicts"
                ) from exc
            except sqlite3.Error as exc:
                connection.rollback()
                raise DeploymentFencingUnavailable(
                    "deployment idempotency store unavailable"
                ) from exc

    def idempotency_record(
        self, request: DeploymentIdempotencyRequestV1
    ) -> DeploymentIdempotencyRecordV1 | None:
        with self._connection() as connection:
            self._verify_authority_schema(connection)
            row = connection.execute(
                "SELECT * FROM deployment_idempotency_facts "
                "WHERE operation=? AND scope_fingerprint=? AND idempotency_key=?",
                (
                    request.operation.value,
                    request.scope.fingerprint.value,
                    request.idempotency_key.value,
                ),
            ).fetchone()
        return self._decode_idempotency(row) if row is not None else None

    def health(self) -> DeploymentFencingHealthV1:
        try:
            with self._connection() as connection:
                self._verify_authority_schema(connection)
                scope_rows = connection.execute(
                    "SELECT DISTINCT scope_fingerprint FROM deployment_fencing_history"
                ).fetchall()
                all_rows = connection.execute(
                    "SELECT * FROM deployment_fencing_history ORDER BY scope_fingerprint,generation"
                ).fetchall()
                idempotency_rows = connection.execute(
                    "SELECT * FROM deployment_idempotency_facts"
                ).fetchall()
            for scope_row in scope_rows:
                facts = tuple(
                    self._decode_generation(row)
                    for row in all_rows
                    if row["scope_fingerprint"] == scope_row[0]
                )
                replay_generation_history(facts)
            for row in idempotency_rows:
                self._decode_idempotency(row)
            return DeploymentFencingHealthV1(True, True, True, True, True, True, True, False)
        except (DeploymentFencingIntegrityError, ValueError):
            return DeploymentFencingHealthV1(True, True, False, False, False, False, False, True)
        except (DeploymentPersistenceError, OSError, sqlite3.Error):
            return DeploymentFencingHealthV1(False, False, False, False, False, False, False, False)

    def _verify_authority_schema(self, connection: sqlite3.Connection) -> None:
        required_tables = {
            "deployment_authority_metadata",
            "deployment_fencing_history",
            "deployment_idempotency_facts",
        }
        if not required_tables.issubset(self._tables(connection)):
            raise DeploymentFencingIntegrityError("deployment authority schema is incomplete")
        objects = connection.execute(
            "SELECT type,name FROM sqlite_master WHERE type IN ('index','trigger')"
        ).fetchall()
        names = {str(row[1]) for row in objects}
        if not {
            "deployment_fencing_scope_generation",
            "deployment_fencing_no_update",
            "deployment_fencing_no_delete",
            "deployment_idempotency_no_update",
            "deployment_idempotency_no_delete",
        }.issubset(names):
            raise DeploymentFencingIntegrityError(
                "deployment authority append-only protections are incomplete"
            )
        metadata = connection.execute(
            "SELECT schema_version,authority_version,migration_id,migration_checksum "
            "FROM deployment_authority_metadata WHERE singleton=1"
        ).fetchone()
        if metadata is None or tuple(metadata) != (
            1,
            DEPLOYMENT_FENCING_AUTHORITY_VERSION,
            _AUTHORITY_MIGRATION_ID,
            _AUTHORITY_MIGRATION_CHECKSUM,
        ):
            raise DeploymentFencingIntegrityError(
                "deployment authority schema version is incompatible"
            )
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DeploymentFencingIntegrityError("deployment authority SQLite integrity failed")

    @staticmethod
    def _decode_generation(row: sqlite3.Row) -> DeploymentGenerationFactV1:
        payload = str(row["canonical_payload"])
        if _checksum(payload) != row["payload_checksum"]:
            raise DeploymentFencingIntegrityError("deployment fencing checksum mismatch")
        try:
            raw = json.loads(payload)
            if canonical_json(raw) != payload:
                raise DeploymentFencingIntegrityError("deployment fencing payload is not canonical")
            scope = _decode_scope(raw["scope"])
            fact = DeploymentGenerationFactV1(
                scope,
                DeploymentGeneration(_generation_value(raw["generation"])),
                RequesterReference(str(raw["owner"])),
                CapabilityReference(str(raw["authority_identity"])),
                str(raw["authority_version"]),
                OccurrenceReference(str(raw["occurrence"])),
                _optional_fingerprint(raw["semantic_binding_fingerprint"]),
                DeploymentFingerprint(str(raw["transition_fingerprint"])),
                _optional_fingerprint(raw["previous_fact_fingerprint"]),
                DeploymentFingerprint(str(raw["fact_fingerprint"])),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DeploymentFencingIntegrityError(
                "deployment fencing payload is malformed"
            ) from exc
        if (
            fact.scope.fingerprint.value != row["scope_fingerprint"]
            or fact.generation.value != row["generation"]
            or fact.fact_fingerprint.value != row["fact_fingerprint"]
            or fact.transition_fingerprint.value != row["transition_fingerprint"]
        ):
            raise DeploymentFencingIntegrityError("deployment fencing record mismatch")
        return fact

    @staticmethod
    def _decode_idempotency(row: sqlite3.Row) -> DeploymentIdempotencyRecordV1:
        payload = str(row["canonical_payload"])
        if _checksum(payload) != row["payload_checksum"]:
            raise DeploymentFencingIntegrityError("deployment idempotency checksum mismatch")
        try:
            raw = json.loads(payload)
            if canonical_json(raw) != payload:
                raise DeploymentFencingIntegrityError(
                    "deployment idempotency payload is not canonical"
                )
            record = DeploymentIdempotencyRecordV1(
                DeploymentMutationClass(str(raw["operation"])),
                _decode_scope(raw["scope"]),
                DeploymentIdempotencyKey(str(raw["idempotency_key"])),
                DeploymentFingerprint(str(raw["semantic_fingerprint"])),
                DeploymentGeneration(_generation_value(raw["fencing_generation"])),
                OccurrenceReference(str(raw["first_accepted_occurrence"])),
                DeploymentIdempotencyStatus(str(raw["status"])),
                _optional(CapabilityReference, raw["result_reference"]),
                str(raw["version"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DeploymentFencingIntegrityError(
                "deployment idempotency payload is malformed"
            ) from exc
        if (
            record.idempotency_key.value != row["idempotency_key"]
            or record.scope.fingerprint.value != row["scope_fingerprint"]
            or record.operation.value != row["operation"]
            or record.semantic_fingerprint.value != row["semantic_fingerprint"]
            or record.fencing_generation.value != row["fencing_generation"]
        ):
            raise DeploymentFencingIntegrityError("deployment idempotency record mismatch")
        return record


def _checksum(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _optional_fingerprint(value: object) -> DeploymentFingerprint | None:
    return None if value is None else DeploymentFingerprint(str(value))


def _generation_value(value: object) -> int:
    if not isinstance(value, dict) or set(value) != {"value"}:
        raise ValueError("deployment generation must be a canonical object")
    raw = value["value"]
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("deployment generation value must be an integer")
    return raw


def _decode_scope(value: object) -> DeploymentFencingScopeV1:
    if not isinstance(value, dict):
        raise ValueError("fencing scope must be an object")
    return DeploymentFencingScopeV1(
        DeploymentFencingScopeKind(str(value["kind"])),
        _optional(ReleaseId, value.get("release_id")),
        _optional(DeploymentTargetId, value.get("target_id")),
        _optional(SlotId, value.get("slot_id")),
        _optional(RolloutId, value.get("rollout_id")),
        _optional(RollbackAttemptId, value.get("rollback_attempt_id")),
        _optional(RevisionId, value.get("source_revision")),
        _optional(RevisionId, value.get("intended_revision")),
    )


T = TypeVar("T")


def _string(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional(factory: Callable[[str], T], value: object) -> T | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional reference must be a string")
    return factory(value)


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("optional integer is invalid")
    return value


def _common(
    raw: dict[str, object],
) -> tuple[
    DeploymentEventId,
    CorrelationReference,
    CausationReference | None,
    OccurrenceReference,
]:
    return (
        DeploymentEventId(_string(raw, "event_id")),
        CorrelationReference(_string(raw, "correlation")),
        _optional(CausationReference, raw["causation"]),
        OccurrenceReference(_string(raw, "occurrence")),
    )


def _decode_event(kind: DeploymentMachineKind, raw: dict[str, object]) -> DeploymentJournalEvent:
    event_id, correlation, causation, occurrence = _common(raw)
    failure = _optional(TransitionFailureClass, raw["failure_class"])
    authorization = _optional(AuthorizationReference, raw.get("authorization_reference"))
    receipt = _optional(ApplyReceiptReference, raw.get("apply_receipt_reference"))
    observation = _optional(ObservationReference, raw.get("observation_reference"))
    verification = _optional(VerificationReference, raw.get("verification_reference"))
    if kind is DeploymentMachineKind.DEPLOYMENT:
        return DeploymentTransitionEventV1(
            event_id,
            ReleaseId(_string(raw, "release_id")),
            DeploymentAttemptId(_string(raw, "attempt_id")),
            DeploymentLifecycleState(_string(raw, "prior_state")),
            DeploymentLifecycleState(_string(raw, "resulting_state")),
            correlation,
            causation,
            occurrence,
            authorization,
            receipt,
            observation,
            verification,
            failure,
            str(raw["format_version"]),
        )
    if kind is DeploymentMachineKind.ROLLOUT:
        stage_raw = raw.get("stage")
        stage = None
        if isinstance(stage_raw, dict):
            stage = RolloutStageV1(
                int(stage_raw["sequence"]),
                CapabilityReference(_string(stage_raw, "stage_reference")),
                _optional(SlotId, stage_raw["slot_id"]),
                _optional_integer(stage_raw["abstract_percentage"]),
                _optional(CapabilityReference, stage_raw["gate_reference"]),
            )
        return RolloutTransitionEventV1(
            event_id,
            RolloutId(_string(raw, "rollout_id")),
            ReleaseId(_string(raw, "release_id")),
            RolloutLifecycleState(_string(raw, "prior_state")),
            RolloutLifecycleState(_string(raw, "resulting_state")),
            correlation,
            causation,
            occurrence,
            authorization,
            stage,
            failure,
            str(raw["format_version"]),
        )
    if kind is DeploymentMachineKind.PROMOTION:
        return PromotionTransitionEventV1(
            event_id,
            PromotionId(_string(raw, "promotion_id")),
            RolloutId(_string(raw, "rollout_id")),
            PromotionLifecycleState(_string(raw, "prior_state")),
            PromotionLifecycleState(_string(raw, "resulting_state")),
            correlation,
            causation,
            occurrence,
            authorization,
            receipt,
            failure,
            str(raw["format_version"]),
        )
    return RollbackTransitionEventV1(
        event_id,
        RollbackAttemptId(_string(raw, "rollback_attempt_id")),
        ReleaseId(_string(raw, "release_id")),
        DeploymentTargetId(_string(raw, "target_id")),
        RevisionId(_string(raw, "source_revision")),
        RevisionId(_string(raw, "intended_revision")),
        _optional(ArtifactReference, raw["intended_artifact_reference"]),
        RollbackLifecycleState(_string(raw, "prior_state")),
        RollbackLifecycleState(_string(raw, "resulting_state")),
        correlation,
        causation,
        occurrence,
        authorization,
        _optional(RollbackReceiptReference, raw.get("rollback_receipt_reference")),
        observation,
        verification,
        failure,
        str(raw["format_version"]),
    )
