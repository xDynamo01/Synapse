from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from synapse.sandbox.errors import (
    SandboxPersistenceConflict,
    SandboxPersistenceCorrupt,
    SandboxPersistenceMigrationMismatch,
    SandboxPersistenceVersionUnsupported,
)
from synapse.sandbox.persistence_models import (
    SandboxArtifactKind,
    SandboxCompleteness,
    SandboxOccurrenceMetadata,
    SandboxRecordDraft,
    SandboxRecoveryState,
    SandboxRetentionMetadata,
    SandboxStoreResponsibility,
    SandboxWriteDisposition,
)
from synapse.sandbox.sqlite_persistence import (
    SandboxSQLiteConfig,
    SandboxSQLiteDatabase,
    SQLiteSandboxAdmissionStore,
    SQLiteSandboxCatalogStore,
    SQLiteSandboxLifecycleStore,
    SQLiteSandboxRecoveryReader,
    SQLiteSandboxResultStore,
)

NOW = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)


@pytest.fixture
def database(tmp_path: Path) -> SandboxSQLiteDatabase:
    database = SandboxSQLiteDatabase(SandboxSQLiteConfig((tmp_path / "sandbox.db").resolve()))
    database.migrate(NOW)
    return database


def draft(
    responsibility: SandboxStoreResponsibility,
    kind: SandboxArtifactKind,
    identity: str,
    *,
    sequence: int = 1,
    expected: int = 0,
    payload: object | None = None,
    lineage: tuple[str, ...] = (),
    recovery: SandboxRecoveryState = SandboxRecoveryState.NONE,
    completeness: SandboxCompleteness = SandboxCompleteness.COMPLETE,
) -> SandboxRecordDraft:
    return SandboxRecordDraft(
        responsibility=responsibility,
        artifact_kind=kind,
        semantic_identity=identity,
        stream_identity="attempt:one",
        sequence=sequence,
        expected_stream_version=expected,
        idempotency_key=f"idempotency:{identity}",
        payload=payload if payload is not None else {"identity": identity},
        lineage_fingerprints=lineage,
        occurrence=SandboxOccurrenceMetadata(NOW, NOW, "test-suite"),
        retention=SandboxRetentionMetadata("retention:default"),
        recovery_state=recovery,
        completeness=completeness,
    )


def test_idempotency_replays_and_divergent_identity_fails_closed(
    database: SandboxSQLiteDatabase,
) -> None:
    store = SQLiteSandboxAdmissionStore(database)
    record = draft(
        SandboxStoreResponsibility.ADMISSION, SandboxArtifactKind.ADMISSION_REQUEST, "admission:one"
    )

    assert store.append(record).disposition is SandboxWriteDisposition.APPENDED
    assert (
        store.append(
            replace(record, occurrence=SandboxOccurrenceMetadata(NOW, NOW, "retry"))
        ).disposition
        is SandboxWriteDisposition.REPLAYED
    )

    with pytest.raises(SandboxPersistenceConflict):
        store.append(replace(record, payload={"identity": "admission:one", "changed": True}))


def test_occurrence_does_not_change_semantic_identity() -> None:
    original = draft(
        SandboxStoreResponsibility.ADMISSION, SandboxArtifactKind.ADMISSION_REQUEST, "admission:one"
    )
    replay = replace(
        original,
        occurrence=SandboxOccurrenceMetadata(NOW, NOW, "different-source", "correlation:two"),
    )
    assert original.semantic_fingerprint == replay.semantic_fingerprint


def test_optimistic_concurrency_and_historical_mutation_are_rejected(
    database: SandboxSQLiteDatabase,
) -> None:
    store = SQLiteSandboxLifecycleStore(database)
    first = draft(
        SandboxStoreResponsibility.LIFECYCLE, SandboxArtifactKind.EXECUTION_ATTEMPT, "attempt:one"
    )
    store.append(first)
    with pytest.raises(SandboxPersistenceConflict):
        store.append(
            draft(
                SandboxStoreResponsibility.LIFECYCLE,
                SandboxArtifactKind.RUNTIME_EVENT,
                "event:two",
                sequence=2,
                expected=0,
            )
        )

    with (
        database.connection() as connection,
        pytest.raises(sqlite3.IntegrityError, match="append-only"),
    ):
        connection.execute("UPDATE sandbox_lifecycle_records SET source_ref='changed'")


def test_checksum_and_unknown_record_version_fail_explicitly(
    database: SandboxSQLiteDatabase,
) -> None:
    store = SQLiteSandboxResultStore(database)
    record = store.append(
        draft(SandboxStoreResponsibility.RESULT, SandboxArtifactKind.EXECUTION_RESULT, "result:one")
    ).record
    with database.connection() as connection:
        connection.execute("DROP TRIGGER sandbox_result_records_no_update")
        connection.execute("UPDATE sandbox_result_records SET payload='{}'")
    with pytest.raises(SandboxPersistenceCorrupt):
        store.get_exact(record.semantic_identity, record.semantic_fingerprint)

    other_path = database.database_path.parent / "version.db"
    other = SandboxSQLiteDatabase(SandboxSQLiteConfig(other_path.resolve()))
    other.migrate(NOW)
    other_store = SQLiteSandboxResultStore(other)
    other_record = other_store.append(
        draft(
            SandboxStoreResponsibility.RESULT,
            SandboxArtifactKind.EXECUTION_RESULT,
            "result:version",
        )
    ).record
    with other.connection() as connection:
        connection.execute("DROP TRIGGER sandbox_result_records_no_update")
        connection.execute("UPDATE sandbox_result_records SET schema_version=2")
    with pytest.raises(SandboxPersistenceVersionUnsupported):
        other_store.get_exact(other_record.semantic_identity, other_record.semantic_fingerprint)


def test_replay_preserves_causal_order_and_exposes_lineage_gaps(
    database: SandboxSQLiteDatabase,
) -> None:
    store = SQLiteSandboxLifecycleStore(database)
    first = store.append(
        draft(
            SandboxStoreResponsibility.LIFECYCLE,
            SandboxArtifactKind.EXECUTION_ATTEMPT,
            "attempt:one",
        )
    ).record
    second = store.append(
        draft(
            SandboxStoreResponsibility.LIFECYCLE,
            SandboxArtifactKind.RUNTIME_EVENT,
            "event:two",
            sequence=2,
            expected=1,
            lineage=(first.semantic_fingerprint, "sha256:" + "f" * 64),
        )
    ).record

    replay = store.replay("attempt:one")
    assert [item.sequence for item in replay.records] == [1, 2]
    assert replay.records[1].semantic_fingerprint == second.semantic_fingerprint
    assert replay.missing_lineage_fingerprints == ("sha256:" + "f" * 64,)
    assert not replay.complete


def test_recovery_exposes_incomplete_facts_without_operational_finalization(
    database: SandboxSQLiteDatabase,
) -> None:
    lifecycle = SQLiteSandboxLifecycleStore(database)
    result = SQLiteSandboxResultStore(database)
    lifecycle.append(
        draft(
            SandboxStoreResponsibility.LIFECYCLE,
            SandboxArtifactKind.EXECUTION_ATTEMPT,
            "attempt:incomplete",
            recovery=SandboxRecoveryState.ATTEMPT_INCOMPLETE,
            completeness=SandboxCompleteness.PARTIAL,
        )
    )
    result.append(
        draft(
            SandboxStoreResponsibility.RESULT,
            SandboxArtifactKind.EVIDENCE_BUNDLE,
            "evidence:incomplete",
            recovery=SandboxRecoveryState.EVIDENCE_INCOMPLETE,
            completeness=SandboxCompleteness.INVALID,
        )
    )

    findings = SQLiteSandboxRecoveryReader(database).findings()
    assert {finding.state for finding in findings} == {
        SandboxRecoveryState.ATTEMPT_INCOMPLETE,
        SandboxRecoveryState.EVIDENCE_INCOMPLETE,
    }
    assert all(finding.state is not SandboxRecoveryState.NONE for finding in findings)


def test_restart_does_not_turn_attempt_without_terminal_record_into_terminal(
    database: SandboxSQLiteDatabase,
) -> None:
    store = SQLiteSandboxLifecycleStore(database)
    attempt = store.append(
        draft(
            SandboxStoreResponsibility.LIFECYCLE,
            SandboxArtifactKind.EXECUTION_ATTEMPT,
            "attempt:restart",
        )
    ).record

    finding = SQLiteSandboxRecoveryReader(database).findings()[0]
    assert finding.fact_fingerprint == attempt.semantic_fingerprint
    assert finding.state is SandboxRecoveryState.ATTEMPT_INCOMPLETE
    assert finding.completeness is SandboxCompleteness.PARTIAL


def test_partial_materialization_and_unverified_termination_remain_explicit(
    database: SandboxSQLiteDatabase,
) -> None:
    store = SQLiteSandboxLifecycleStore(database)
    store.append(
        draft(
            SandboxStoreResponsibility.LIFECYCLE,
            SandboxArtifactKind.MATERIALIZATION_OUTCOME,
            "materialization:partial",
            recovery=SandboxRecoveryState.CLEANUP_REQUIRED,
            completeness=SandboxCompleteness.PARTIAL,
        )
    )
    store.append(
        draft(
            SandboxStoreResponsibility.LIFECYCLE,
            SandboxArtifactKind.TERMINATION_PROOF,
            "termination:unverified",
            sequence=2,
            expected=1,
            recovery=SandboxRecoveryState.TERMINATION_UNVERIFIED,
            completeness=SandboxCompleteness.PARTIAL,
        )
    )
    states = [finding.state for finding in SQLiteSandboxRecoveryReader(database).findings()]
    assert states == [
        SandboxRecoveryState.CLEANUP_REQUIRED,
        SandboxRecoveryState.TERMINATION_UNVERIFIED,
    ]


def test_migration_checksum_divergence_fails_closed(database: SandboxSQLiteDatabase) -> None:
    with database.connection() as connection:
        connection.execute("DROP TRIGGER sandbox_migration_history_no_update")
        connection.execute("UPDATE sandbox_migration_history SET checksum='divergent'")
        connection.execute(
            "CREATE TRIGGER sandbox_migration_history_no_update "
            "BEFORE UPDATE ON sandbox_migration_history "
            "BEGIN SELECT RAISE(ABORT, 'append-only'); END"
        )
    with pytest.raises(SandboxPersistenceMigrationMismatch):
        database.verify()


def test_stores_are_separate_and_exact_reads_require_identity_and_fingerprint(
    database: SandboxSQLiteDatabase,
) -> None:
    catalog = SQLiteSandboxCatalogStore(database)
    admission = SQLiteSandboxAdmissionStore(database)
    policy = catalog.append(
        draft(
            SandboxStoreResponsibility.CATALOG, SandboxArtifactKind.ADMISSION_POLICY, "policy:one"
        )
    ).record
    with pytest.raises(SandboxPersistenceConflict):
        admission.append(
            draft(
                SandboxStoreResponsibility.CATALOG,
                SandboxArtifactKind.ADMISSION_POLICY,
                "policy:two",
            )
        )
    assert catalog.get_exact(policy.semantic_identity, policy.semantic_fingerprint) == policy
