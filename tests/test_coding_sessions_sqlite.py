import hashlib
import sqlite3
from pathlib import Path

import pytest

from synapse.coding_sessions import (
    CodingSessionArtifactExistenceRequest,
    CodingSessionCausalRangeReadRequest,
    CodingSessionCheckpointIdentity,
    CodingSessionCheckpointPersistenceState,
    CodingSessionExactRecordReadRequest,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionPersistenceFailureCode,
    CodingSessionPersistenceRecordIdentity,
    CodingSessionPersistenceStream,
    CodingSessionRecordAppendRequest,
    CodingSessionRecordAppendStatus,
    CodingSessionRecordEnvelope,
    CodingSessionReplayRequest,
    CodingSessionRetentionMetadata,
    CodingSessionStreamCompleteness,
)
from synapse.coding_sessions.canonical import canonical_bytes
from synapse.coding_sessions.errors import (
    CodingSessionPersistenceCorrupt,
    CodingSessionPersistenceMigrationMismatch,
    CodingSessionPersistenceUnavailable,
)
from synapse.coding_sessions.sqlite_persistence import (
    CODING_SESSION_SQLITE_MIGRATION_V1_CHECKSUM,
    CODING_SESSION_SQLITE_SCHEMA_VERSION,
    CodingSessionSQLiteConfig,
    CodingSessionSQLiteDatabase,
    SQLiteCodingSessionContractBindingsStore,
    SQLiteCodingSessionControlCancellationStore,
    SQLiteCodingSessionIntentsReceiptsStore,
    SQLiteCodingSessionJournalCheckpointsStore,
    SQLiteCodingSessionLifecycleCoordinationStore,
    SQLiteCodingSessionRecoveryOutcomeStore,
    SQLiteCodingSessionRestartReconciliationStore,
)


def _session() -> CodingSessionIdentity:
    return CodingSessionIdentity.from_stable_key("sqlite-session")


def _payload(category: str) -> tuple[str, CodingSessionFingerprint]:
    value = canonical_bytes({"category": category}).decode("ascii")
    checksum = "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()
    return value, CodingSessionFingerprint(checksum)


def _record(
    revision: int,
    *,
    stream: CodingSessionPersistenceStream,
    category: str,
    parent: CodingSessionRecordEnvelope | None = None,
    idempotency: str | None = None,
    identity: str | None = None,
) -> CodingSessionRecordEnvelope:
    payload, payload_fingerprint = _payload(category)
    parent_fingerprint = parent.record_fingerprint if parent else None
    return CodingSessionRecordEnvelope(
        CodingSessionPersistenceRecordIdentity.from_stable_key(
            identity or f"{stream.value}-{revision}"
        ),
        _session(),
        stream,
        category,
        f"artifact-{stream.value}-{revision}",
        payload,
        payload_fingerprint,
        revision,
        parent_fingerprint,
        ((parent_fingerprint,) if parent_fingerprint else ()),
        CodingSessionFingerprint.from_content(idempotency or f"idempotency-{stream.value}-{revision}"),
        (("observed-at", "100"),),
        CodingSessionRetentionMetadata("retention-v1", "factual"),
    )


def _database(path: str) -> CodingSessionSQLiteDatabase:
    database = CodingSessionSQLiteDatabase(CodingSessionSQLiteConfig(path))
    database.migrate(applied_at="2026-08-09T12:00:00Z")
    return database


def _append_request(
    record: CodingSessionRecordEnvelope,
    previous: CodingSessionRecordEnvelope | None = None,
) -> CodingSessionRecordAppendRequest:
    return CodingSessionRecordAppendRequest(
        record,
        record.causal_revision,
        previous.record_fingerprint if previous else None,
    )


def test_initial_migration_creates_seven_owned_tables(tmp_path: Path) -> None:
    path = str(tmp_path / "coding-sessions.db")
    database = _database(path)

    with database.connection() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE 'coding_session_%_records'"
            ).fetchall()
        }
        checksum = connection.execute(
            "SELECT checksum FROM coding_session_migration_history"
        ).fetchone()[0]

    assert version == CODING_SESSION_SQLITE_SCHEMA_VERSION
    assert len(tables) == 7
    assert checksum == CODING_SESSION_SQLITE_MIGRATION_V1_CHECKSUM


def test_reopen_preserves_append_and_exact_read(tmp_path: Path) -> None:
    path = str(tmp_path / "restart.db")
    database = _database(path)
    store = SQLiteCodingSessionLifecycleCoordinationStore(database)
    record = _record(
        1,
        stream=CodingSessionPersistenceStream.LIFECYCLE_COORDINATION,
        category="lifecycle-suspended",
    )
    assert store.append_lifecycle_record(_append_request(record)).status is CodingSessionRecordAppendStatus.APPENDED

    reopened = _database(path)
    reopened_store = SQLiteCodingSessionLifecycleCoordinationStore(reopened)
    result = reopened_store.read_exact(
        CodingSessionExactRecordReadRequest(
            _session(), record.stream, record.record_identity, record.record_fingerprint
        )
    )

    assert result.record == record
    assert result.record is not None and result.record.category == "lifecycle-suspended"


def test_idempotent_append_does_not_duplicate_and_collision_fails_closed(
    tmp_path: Path,
) -> None:
    database = _database(str(tmp_path / "idempotency.db"))
    store = SQLiteCodingSessionIntentsReceiptsStore(database)
    record = _record(
        1,
        stream=CodingSessionPersistenceStream.INTENTS_RECEIPTS,
        category="intent-pending",
        idempotency="shared",
    )
    assert store.append(_append_request(record)).status is CodingSessionRecordAppendStatus.APPENDED
    assert store.append(_append_request(record)).status is CodingSessionRecordAppendStatus.IDEMPOTENT
    divergent = _record(
        2,
        stream=record.stream,
        category="intent-succeeded",
        idempotency="shared",
    )
    collision = store.append(_append_request(divergent, record))

    assert collision.status is CodingSessionRecordAppendStatus.REJECTED
    assert collision.failures[0].code is CodingSessionPersistenceFailureCode.IDEMPOTENCY_COLLISION
    assert len(store.read_range(CodingSessionCausalRangeReadRequest(_session(), record.stream, 1, 5))) == 1


def test_record_identity_and_idempotency_are_unique_across_stream_tables(tmp_path: Path) -> None:
    database = _database(str(tmp_path / "cross-stream.db"))
    lifecycle = SQLiteCodingSessionLifecycleCoordinationStore(database)
    first = _record(
        1,
        stream=CodingSessionPersistenceStream.LIFECYCLE_COORDINATION,
        category="lifecycle-suspended",
        identity="global-identity",
        idempotency="global-key",
    )
    lifecycle.append(_append_request(first))
    recovery = SQLiteCodingSessionRecoveryOutcomeStore(database)
    divergent = _record(
        1,
        stream=CodingSessionPersistenceStream.RECOVERY_OUTCOME,
        category="recovery-required",
        identity="global-identity",
        idempotency="global-key",
    )

    result = recovery.append(_append_request(divergent))

    assert result.status is CodingSessionRecordAppendStatus.REJECTED
    assert result.failures[0].code is CodingSessionPersistenceFailureCode.IDEMPOTENCY_COLLISION
    assert recovery.read_range(
        CodingSessionCausalRangeReadRequest(_session(), divergent.stream, 1, 1)
    ) == ()


def test_revision_and_lineage_conflicts_are_atomic(tmp_path: Path) -> None:
    database = _database(str(tmp_path / "conflicts.db"))
    store = SQLiteCodingSessionRecoveryOutcomeStore(database)
    first = _record(1, stream=CodingSessionPersistenceStream.RECOVERY_OUTCOME, category="recovery-required")
    assert store.append(_append_request(first)).status is CodingSessionRecordAppendStatus.APPENDED
    gap = _record(3, stream=first.stream, category="recovery-reconciling")
    result = store.append(CodingSessionRecordAppendRequest(gap, 3, None))

    assert result.status is CodingSessionRecordAppendStatus.REJECTED
    assert {
        CodingSessionPersistenceFailureCode.CAUSAL_REVISION_CONFLICT,
        CodingSessionPersistenceFailureCode.LINEAGE_GAP,
    } <= {item.code for item in result.failures}
    assert len(store.read_range(CodingSessionCausalRangeReadRequest(_session(), first.stream, 1, 5))) == 1


def test_database_triggers_reject_update_and_delete(tmp_path: Path) -> None:
    path = str(tmp_path / "append-only.db")
    database = _database(path)
    store = SQLiteCodingSessionContractBindingsStore(database)
    record = _record(1, stream=CodingSessionPersistenceStream.CONTRACT_BINDINGS, category="contract")
    store.append(_append_request(record))

    with pytest.raises(CodingSessionPersistenceUnavailable):
        with database.connection() as connection:
            connection.execute("UPDATE coding_session_contract_records SET category='changed'")
    with pytest.raises(CodingSessionPersistenceUnavailable):
        with database.connection() as connection:
            connection.execute("DELETE FROM coding_session_contract_records")


def test_corrupt_payload_and_record_fingerprint_block_reads(tmp_path: Path) -> None:
    path = str(tmp_path / "corrupt.db")
    database = _database(path)
    store = SQLiteCodingSessionControlCancellationStore(database)
    record = _record(1, stream=CodingSessionPersistenceStream.CONTROL_CANCELLATION, category="cancellation-pending")
    store.append(_append_request(record))
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER coding_session_control_records_no_update")
        connection.execute("UPDATE coding_session_control_records SET canonical_payload='corrupt'")
        connection.commit()

    with pytest.raises(CodingSessionPersistenceCorrupt):
        store.read_range(CodingSessionCausalRangeReadRequest(_session(), record.stream, 1, 1))


def test_migration_checksum_mismatch_fails_reopen(tmp_path: Path) -> None:
    path = str(tmp_path / "migration.db")
    database = _database(path)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER coding_session_migration_no_update")
        connection.execute("UPDATE coding_session_migration_history SET checksum='sha256:bad'")
        connection.commit()

    with pytest.raises(CodingSessionPersistenceMigrationMismatch):
        database.verify()


def test_exact_artifact_range_checkpoint_and_replay(tmp_path: Path) -> None:
    database = _database(str(tmp_path / "replay.db"))
    journal = SQLiteCodingSessionJournalCheckpointsStore(database)
    checkpoint = _record(1, stream=CodingSessionPersistenceStream.JOURNAL_CHECKPOINTS, category="checkpoint-incomplete")
    journal.append(_append_request(checkpoint))
    exact = CodingSessionExactRecordReadRequest(
        _session(), checkpoint.stream, checkpoint.record_identity, checkpoint.record_fingerprint
    )
    evidence = journal.checkpoint_persistence_evidence(
        exact,
        checkpoint_identity=CodingSessionCheckpointIdentity.from_stable_key("checkpoint"),
        checkpoint_fingerprint=checkpoint.canonical_payload_fingerprint,
        structural_complete=False,
        durable_ready=True,
    )
    exists = journal.exists_exact(
        CodingSessionArtifactExistenceRequest(
            _session(), checkpoint.stream, checkpoint.semantic_artifact_identity, checkpoint.canonical_payload_fingerprint
        )
    )
    restart_store = SQLiteCodingSessionRestartReconciliationStore(database)
    replay = restart_store.replay_session(
        CodingSessionReplayRequest(
            _session(),
            (CodingSessionCausalRangeReadRequest(_session(), checkpoint.stream, 1, 1),),
            frozenset({checkpoint.stream}),
        )
    )

    assert exists
    assert evidence.persistence_state is CodingSessionCheckpointPersistenceState.PERSISTED
    assert evidence.durable_ready and not evidence.structural_complete
    assert replay.completeness is CodingSessionStreamCompleteness.COMPLETE
    assert replay.records[0].category == "checkpoint-incomplete"


def test_restart_replay_preserves_intermediate_states(tmp_path: Path) -> None:
    database = _database(str(tmp_path / "states.db"))
    cases = (
        (CodingSessionPersistenceStream.LIFECYCLE_COORDINATION, "lifecycle-suspended"),
        (CodingSessionPersistenceStream.INTENTS_RECEIPTS, "intent-pending"),
        (CodingSessionPersistenceStream.CONTROL_CANCELLATION, "cancellation-pending"),
        (CodingSessionPersistenceStream.RESTART_RECONCILIATION, "repository-unknown"),
        (CodingSessionPersistenceStream.RECOVERY_OUTCOME, "recovery-reconciling"),
    )
    for stream, category in cases:
        SQLiteCodingSessionRestartReconciliationStore(database)
        store = {
            CodingSessionPersistenceStream.LIFECYCLE_COORDINATION: SQLiteCodingSessionLifecycleCoordinationStore,
            CodingSessionPersistenceStream.INTENTS_RECEIPTS: SQLiteCodingSessionIntentsReceiptsStore,
            CodingSessionPersistenceStream.CONTROL_CANCELLATION: SQLiteCodingSessionControlCancellationStore,
            CodingSessionPersistenceStream.RESTART_RECONCILIATION: SQLiteCodingSessionRestartReconciliationStore,
            CodingSessionPersistenceStream.RECOVERY_OUTCOME: SQLiteCodingSessionRecoveryOutcomeStore,
        }[stream](database)
        record = _record(1, stream=stream, category=category)
        store.append(_append_request(record))
    ranges = tuple(CodingSessionCausalRangeReadRequest(_session(), stream, 1, 1) for stream, _ in cases)
    replay = SQLiteCodingSessionRestartReconciliationStore(database).replay_session(
        CodingSessionReplayRequest(_session(), ranges, frozenset(stream for stream, _ in cases))
    )

    assert {item.category for item in replay.records} == {category for _, category in cases}
    assert "lifecycle-active" not in {item.category for item in replay.records}
