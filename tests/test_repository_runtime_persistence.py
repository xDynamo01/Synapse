from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from synapse.repository_runtime import (
    RepositoryArtifactKind,
    RepositoryFingerprint,
    RepositoryOccurrenceMetadata,
    RepositoryPersistedLifecycleState,
    RepositoryPersistenceConflict,
    RepositoryPersistenceCorrupt,
    RepositoryPersistenceMigrationMismatch,
    RepositoryPersistenceRecordNotFound,
    RepositoryPersistenceUnavailable,
    RepositoryPersistenceVersionUnsupported,
    RepositoryRecordCompleteness,
    RepositoryRecordDraft,
    RepositoryRetentionMetadata,
    RepositorySQLiteConfig,
    RepositorySQLiteDatabase,
    RepositoryStoreResponsibility,
    RepositoryWriteDisposition,
    SQLiteRepositoryMutationLifecycleStore,
    SQLiteRepositoryObservationSnapshotStore,
    SQLiteRepositoryPlanningAuthorizationStore,
    SQLiteRepositoryRecoveryEvidenceStore,
)

NOW = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)


@pytest.fixture
def database(tmp_path: Path) -> RepositorySQLiteDatabase:
    database = RepositorySQLiteDatabase(
        RepositorySQLiteConfig(str((tmp_path / "repository-runtime.db").resolve()))
    )
    database.migrate(NOW)
    return database


def draft(
    responsibility: RepositoryStoreResponsibility,
    kind: RepositoryArtifactKind,
    identity: str,
    *,
    revision: int = 1,
    expected: int = 0,
    payload: object | None = None,
    lineage: tuple[RepositoryFingerprint, ...] = (),
    completeness: RepositoryRecordCompleteness = RepositoryRecordCompleteness.COMPLETE,
    state: RepositoryPersistedLifecycleState = RepositoryPersistedLifecycleState.NONE,
    source: str = "test-suite",
) -> RepositoryRecordDraft:
    return RepositoryRecordDraft(
        responsibility,
        kind,
        identity,
        "repository:stream:one",
        revision,
        expected,
        f"idempotency:{identity}",
        payload if payload is not None else {"identity": identity},
        lineage,
        RepositoryOccurrenceMetadata(NOW, NOW, source),
        RepositoryRetentionMetadata("retention:default"),
        completeness,
        state,
    )


def test_idempotent_append_replays_without_duplicate(database) -> None:
    store = SQLiteRepositoryObservationSnapshotStore(database)
    record = draft(
        RepositoryStoreResponsibility.OBSERVATION_SNAPSHOT,
        RepositoryArtifactKind.OBSERVATION,
        "observation:one",
    )
    first = store.append(record)
    second = store.append(
        replace(record, occurrence=RepositoryOccurrenceMetadata(NOW, NOW, "retry"))
    )
    assert first.disposition is RepositoryWriteDisposition.APPENDED
    assert second.disposition is RepositoryWriteDisposition.REPLAYED
    assert len(store.replay(record.stream_identity).records) == 1


def test_same_identity_with_divergent_payload_fails_closed(database) -> None:
    store = SQLiteRepositoryObservationSnapshotStore(database)
    record = draft(
        RepositoryStoreResponsibility.OBSERVATION_SNAPSHOT,
        RepositoryArtifactKind.SNAPSHOT,
        "snapshot:one",
    )
    store.append(record)
    with pytest.raises(RepositoryPersistenceConflict):
        store.append(replace(record, payload={"identity": "snapshot:one", "changed": True}))


def test_historical_records_cannot_be_updated_or_deleted(database) -> None:
    store = SQLiteRepositoryMutationLifecycleStore(database)
    store.append(
        draft(
            RepositoryStoreResponsibility.MUTATION_LIFECYCLE,
            RepositoryArtifactKind.MUTATION_JOURNAL,
            "journal:one",
        )
    )
    with pytest.raises(RepositoryPersistenceUnavailable):
        with database.connection() as connection:
            connection.execute("UPDATE repository_mutation_records SET source_reference='changed'")
    with pytest.raises(RepositoryPersistenceUnavailable):
        with database.connection() as connection:
            connection.execute("DELETE FROM repository_mutation_records")


def test_checksum_and_unknown_record_version_fail_explicitly(database, tmp_path) -> None:
    store = SQLiteRepositoryRecoveryEvidenceStore(database)
    record = store.append(
        draft(
            RepositoryStoreResponsibility.RECOVERY_EVIDENCE,
            RepositoryArtifactKind.RECOVERY_RESULT,
            "recovery:one",
        )
    ).record
    with database.connection() as connection:
        connection.execute("DROP TRIGGER repository_recovery_records_no_update")
        connection.execute("UPDATE repository_recovery_records SET payload='{}'")
        connection.commit()
    with pytest.raises(RepositoryPersistenceCorrupt):
        store.get_exact(record.semantic_identity, record.semantic_fingerprint.value)

    other = RepositorySQLiteDatabase(
        RepositorySQLiteConfig(str((tmp_path / "unknown-version.db").resolve()))
    )
    other.migrate(NOW)
    other_store = SQLiteRepositoryRecoveryEvidenceStore(other)
    other_record = other_store.append(
        draft(
            RepositoryStoreResponsibility.RECOVERY_EVIDENCE,
            RepositoryArtifactKind.RECONCILIATION,
            "reconciliation:version",
        )
    ).record
    with other.connection() as connection:
        connection.execute("DROP TRIGGER repository_recovery_records_no_update")
        connection.execute("UPDATE repository_recovery_records SET schema_version=2")
        connection.commit()
    with pytest.raises(RepositoryPersistenceVersionUnsupported):
        other_store.get_exact(
            other_record.semantic_identity, other_record.semantic_fingerprint.value
        )


def test_replay_preserves_causal_order_and_exposes_lineage_gap(database) -> None:
    store = SQLiteRepositoryPlanningAuthorizationStore(database)
    first = store.append(
        draft(
            RepositoryStoreResponsibility.PLANNING_AUTHORIZATION,
            RepositoryArtifactKind.MUTATION_PLAN,
            "plan:one",
        )
    ).record
    missing = RepositoryFingerprint.from_content("missing-lineage")
    store.append(
        draft(
            RepositoryStoreResponsibility.PLANNING_AUTHORIZATION,
            RepositoryArtifactKind.AUTHORIZATION_ASSESSMENT,
            "authorization:two",
            revision=2,
            expected=1,
            lineage=(first.semantic_fingerprint, missing),
        )
    )
    replay = store.replay("repository:stream:one")
    assert [item.causal_revision for item in replay.records] == [1, 2]
    assert replay.missing_lineage_fingerprints == (missing,)
    assert not replay.complete


def test_duplicate_revision_stream_conflict_and_exact_missing_read(database) -> None:
    store = SQLiteRepositoryMutationLifecycleStore(database)
    store.append(
        draft(
            RepositoryStoreResponsibility.MUTATION_LIFECYCLE,
            RepositoryArtifactKind.MUTATION_ATTEMPT,
            "attempt:one",
        )
    )
    with pytest.raises(RepositoryPersistenceConflict):
        store.append(
            draft(
                RepositoryStoreResponsibility.MUTATION_LIFECYCLE,
                RepositoryArtifactKind.MUTATION_RESULT,
                "result:conflict",
            )
        )
    with pytest.raises(RepositoryPersistenceRecordNotFound):
        store.get_exact("missing:identity", RepositoryFingerprint.from_content("missing").value)


@pytest.mark.parametrize(
    ("store_type", "responsibility", "kind", "state", "completeness"),
    (
        (
            SQLiteRepositoryObservationSnapshotStore,
            RepositoryStoreResponsibility.OBSERVATION_SNAPSHOT,
            RepositoryArtifactKind.OBSERVATION,
            RepositoryPersistedLifecycleState.OBSERVATION_PARTIAL,
            RepositoryRecordCompleteness.PARTIAL,
        ),
        (
            SQLiteRepositoryPlanningAuthorizationStore,
            RepositoryStoreResponsibility.PLANNING_AUTHORIZATION,
            RepositoryArtifactKind.MUTATION_PLAN,
            RepositoryPersistedLifecycleState.PLAN_AWAITING_AUTHORIZATION,
            RepositoryRecordCompleteness.PARTIAL,
        ),
        (
            SQLiteRepositoryMutationLifecycleStore,
            RepositoryStoreResponsibility.MUTATION_LIFECYCLE,
            RepositoryArtifactKind.MUTATION_JOURNAL,
            RepositoryPersistedLifecycleState.APPLICATION_PARTIAL,
            RepositoryRecordCompleteness.PARTIAL,
        ),
        (
            SQLiteRepositoryRecoveryEvidenceStore,
            RepositoryStoreResponsibility.RECOVERY_EVIDENCE,
            RepositoryArtifactKind.REPOSITORY_VERIFICATION,
            RepositoryPersistedLifecycleState.VERIFICATION_DIVERGENT,
            RepositoryRecordCompleteness.PARTIAL,
        ),
        (
            SQLiteRepositoryRecoveryEvidenceStore,
            RepositoryStoreResponsibility.RECOVERY_EVIDENCE,
            RepositoryArtifactKind.RECOVERY_PLAN,
            RepositoryPersistedLifecycleState.RECOVERY_REQUIRED,
            RepositoryRecordCompleteness.PARTIAL,
        ),
        (
            SQLiteRepositoryRecoveryEvidenceStore,
            RepositoryStoreResponsibility.RECOVERY_EVIDENCE,
            RepositoryArtifactKind.RECOVERY_JOURNAL,
            RepositoryPersistedLifecycleState.RECOVERY_PARTIAL,
            RepositoryRecordCompleteness.PARTIAL,
        ),
        (
            SQLiteRepositoryRecoveryEvidenceStore,
            RepositoryStoreResponsibility.RECOVERY_EVIDENCE,
            RepositoryArtifactKind.RECOVERY_RESULT,
            RepositoryPersistedLifecycleState.ROLLBACK_FAILED,
            RepositoryRecordCompleteness.COMPLETE,
        ),
        (
            SQLiteRepositoryRecoveryEvidenceStore,
            RepositoryStoreResponsibility.RECOVERY_EVIDENCE,
            RepositoryArtifactKind.RECOVERY_RESULT,
            RepositoryPersistedLifecycleState.MANUAL_INTERVENTION,
            RepositoryRecordCompleteness.COMPLETE,
        ),
    ),
)
def test_restart_preserves_intermediate_state_exactly(
    database, store_type, responsibility, kind, state, completeness
) -> None:
    store = store_type(database)
    store.append(
        draft(
            responsibility, kind, f"artifact:{state.value}", state=state, completeness=completeness
        )
    )
    restarted = store_type(
        RepositorySQLiteDatabase(RepositorySQLiteConfig(database.database_path))
    ).restart_state("repository:stream:one")
    assert restarted.lifecycle_states == (state,)
    assert restarted.records[0].completeness is completeness
    assert restarted.completeness is completeness


def test_occurrence_metadata_does_not_change_semantic_identity() -> None:
    original = draft(
        RepositoryStoreResponsibility.RECOVERY_EVIDENCE,
        RepositoryArtifactKind.RECOVERY_RESULT,
        "recovery:semantic",
    )
    replay = replace(
        original,
        occurrence=RepositoryOccurrenceMetadata(NOW, NOW, "different-source"),
    )
    assert original.semantic_fingerprint == replay.semantic_fingerprint


def test_migration_checksum_divergence_fails_closed(database) -> None:
    with database.connection() as connection:
        connection.execute("DROP TRIGGER repository_migration_history_no_update")
        connection.execute("UPDATE repository_migration_history SET checksum='sha256:divergent'")
        connection.commit()
    with pytest.raises(RepositoryPersistenceMigrationMismatch):
        database.verify()


def test_stores_are_separate_and_have_no_lifecycle_execution_authority(database) -> None:
    observation = SQLiteRepositoryObservationSnapshotStore(database)
    planning = SQLiteRepositoryPlanningAuthorizationStore(database)
    record = draft(
        RepositoryStoreResponsibility.OBSERVATION_SNAPSHOT,
        RepositoryArtifactKind.SNAPSHOT,
        "snapshot:separate",
    )
    observation.append(record)
    with pytest.raises(RepositoryPersistenceConflict):
        planning.append(record)
    assert not hasattr(planning, "apply_operation")
    assert not hasattr(planning, "apply_recovery_step")
