from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from synapse.deployment import (
    ApplyReceiptReference,
    AuthorizationReference,
    CausationReference,
    CorrelationReference,
    DeploymentAppendDisposition,
    DeploymentAttemptId,
    DeploymentEventContradiction,
    DeploymentEventId,
    DeploymentFingerprint,
    DeploymentJournalAppendRequest,
    DeploymentJournalRecord,
    DeploymentLifecycleState,
    DeploymentMachineKey,
    DeploymentMachineKind,
    DeploymentPersistenceCorrupt,
    DeploymentReplayFailed,
    DeploymentSchemaIncompatible,
    DeploymentSequenceConflict,
    DeploymentSequenceGap,
    DeploymentTransitionEventV1,
    OccurrenceReference,
    PromotionId,
    PromotionLifecycleState,
    PromotionTransitionEventV1,
    ReleaseId,
    RollbackAttemptId,
    RollbackLifecycleState,
    RollbackTransitionEventV1,
    RolloutId,
    RolloutLifecycleState,
    RolloutTransitionEventV1,
    TransitionFailureClass,
    replay_deployment_history,
)
from synapse.deployment.canonical import canonical_json
from synapse.deployment.identities import DeploymentTargetId, RevisionId
from synapse.deployment_adapters import DeploymentSQLiteConfig, SQLiteDeploymentJournalStore


def _deployment_event(
    number: int,
    prior: DeploymentLifecycleState = DeploymentLifecycleState.PROPOSED,
    resulting: DeploymentLifecycleState = DeploymentLifecycleState.AUTHORIZATION_PENDING,
    *,
    authorization: bool = False,
) -> DeploymentTransitionEventV1:
    return DeploymentTransitionEventV1(
        DeploymentEventId(f"deployment-event:persist-{number}"),
        ReleaseId("deployment-release:persist"),
        DeploymentAttemptId("deployment-attempt:persist"),
        prior,
        resulting,
        CorrelationReference("correlation:persist"),
        CausationReference(f"causation:persist-{number}"),
        OccurrenceReference(f"occurrence:persist-{number}"),
        AuthorizationReference(f"authorization:persist-{number}") if authorization else None,
    )


def _rollout_event() -> RolloutTransitionEventV1:
    return RolloutTransitionEventV1(
        DeploymentEventId("deployment-event:rollout-persist"),
        RolloutId("deployment-rollout:persist"),
        ReleaseId("deployment-release:persist"),
        RolloutLifecycleState.PLANNED,
        RolloutLifecycleState.AUTHORIZED,
        CorrelationReference("correlation:rollout-persist"),
        None,
        OccurrenceReference("occurrence:rollout-persist"),
        AuthorizationReference("authorization:rollout-persist"),
    )


def _promotion_event() -> PromotionTransitionEventV1:
    return PromotionTransitionEventV1(
        DeploymentEventId("deployment-event:promotion-persist"),
        PromotionId("deployment-promotion:persist"),
        RolloutId("deployment-rollout:persist"),
        PromotionLifecycleState.PENDING,
        PromotionLifecycleState.AUTHORIZED,
        CorrelationReference("correlation:promotion-persist"),
        None,
        OccurrenceReference("occurrence:promotion-persist"),
        AuthorizationReference("authorization:promotion-persist"),
    )


def _rollback_event() -> RollbackTransitionEventV1:
    return RollbackTransitionEventV1(
        DeploymentEventId("deployment-event:rollback-persist"),
        RollbackAttemptId("deployment-rollback-attempt:persist"),
        ReleaseId("deployment-release:persist"),
        DeploymentTargetId("deployment-target:persist"),
        RevisionId("deployment-revision:failed"),
        RevisionId("deployment-revision:rollback"),
        None,
        RollbackLifecycleState.REQUESTED,
        RollbackLifecycleState.AUTHORIZATION_PENDING,
        CorrelationReference("correlation:rollback-persist"),
        None,
        OccurrenceReference("occurrence:rollback-persist"),
    )


@pytest.fixture
def store(tmp_path: Path) -> SQLiteDeploymentJournalStore:
    result = SQLiteDeploymentJournalStore(
        DeploymentSQLiteConfig((tmp_path / "deployment.sqlite3").resolve())
    )
    result.initialize()
    return result


def _append(store, sequence, event):
    return store.append(
        DeploymentJournalAppendRequest(
            DeploymentMachineKey(
                {
                    DeploymentTransitionEventV1: DeploymentMachineKind.DEPLOYMENT,
                    RolloutTransitionEventV1: DeploymentMachineKind.ROLLOUT,
                    PromotionTransitionEventV1: DeploymentMachineKind.PROMOTION,
                    RollbackTransitionEventV1: DeploymentMachineKind.ROLLBACK,
                }[type(event)],
                (
                    event.attempt_id.value
                    if isinstance(event, DeploymentTransitionEventV1)
                    else event.rollout_id.value
                    if isinstance(event, RolloutTransitionEventV1)
                    else event.promotion_id.value
                    if isinstance(event, PromotionTransitionEventV1)
                    else event.rollback_attempt_id.value
                ),
            ),
            sequence,
            event,
        )
    )


def test_initialize_empty_schema_v1_and_health(store) -> None:
    machine = DeploymentMachineKey(
        DeploymentMachineKind.DEPLOYMENT, "deployment-attempt:persist"
    )
    assert store.latest_sequence(machine) == 0
    assert store.history(machine) == ()
    health = store.health()
    assert health.store_available
    assert health.schema_compatible
    assert health.append_integrity
    assert health.replay_available
    assert not health.corruption_detected


def test_append_strict_sequence_idempotency_and_contradiction(store) -> None:
    first = _deployment_event(1)
    appended = _append(store, 1, first)
    assert appended.disposition is DeploymentAppendDisposition.APPENDED
    assert appended.record.event == first
    assert canonical_json(appended.record.event) == appended.record.canonical_payload
    assert _append(store, 1, first).disposition is DeploymentAppendDisposition.IDEMPOTENT
    with pytest.raises(DeploymentEventContradiction):
        _append(store, 1, replace(first, resulting_state=DeploymentLifecycleState.DENIED))
    with pytest.raises(DeploymentSequenceGap):
        _append(
            store,
            3,
            _deployment_event(
                3,
                DeploymentLifecycleState.AUTHORIZATION_PENDING,
                DeploymentLifecycleState.AUTHORIZED,
                authorization=True,
            ),
        )
    with pytest.raises(DeploymentSequenceConflict):
        _append(
            store,
            1,
            _deployment_event(
                2,
                DeploymentLifecycleState.AUTHORIZATION_PENDING,
                DeploymentLifecycleState.AUTHORIZED,
                authorization=True,
            ),
        )


def test_concurrent_next_sequence_allows_one_winner(tmp_path: Path) -> None:
    path = (tmp_path / "race.sqlite3").resolve()
    SQLiteDeploymentJournalStore(DeploymentSQLiteConfig(path)).initialize()

    def append(number: int) -> str:
        contender = SQLiteDeploymentJournalStore(DeploymentSQLiteConfig(path))
        try:
            _append(contender, 1, _deployment_event(number))
            return "appended"
        except DeploymentSequenceConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(append, (11, 12)))
    assert sorted(outcomes) == ["appended", "conflict"]


def test_four_histories_and_replays_are_separate(store) -> None:
    events = (_deployment_event(1), _rollout_event(), _promotion_event(), _rollback_event())
    for event in events:
        _append(store, 1, event)
    projections = tuple(
        store.replay(
            DeploymentMachineKey(kind, identity)
        )
        for kind, identity in (
            (DeploymentMachineKind.DEPLOYMENT, "deployment-attempt:persist"),
            (DeploymentMachineKind.ROLLOUT, "deployment-rollout:persist"),
            (DeploymentMachineKind.PROMOTION, "deployment-promotion:persist"),
            (DeploymentMachineKind.ROLLBACK, "deployment-rollback-attempt:persist"),
        )
    )
    assert [projection.state.value for projection in projections] == [
        "authorization-pending",
        "authorized",
        "authorized",
        "authorization-pending",
    ]
    assert all(len(projection.events) == 1 for projection in projections)


def test_machine_replay_rejects_incompatible_event_type() -> None:
    rollout = _rollout_event()
    machine = DeploymentMachineKey(
        DeploymentMachineKind.DEPLOYMENT, "deployment-attempt:persist"
    )
    record = DeploymentJournalRecord(
        machine,
        1,
        rollout.event_id,
        rollout.fingerprint,
        rollout,
        canonical_json(rollout),
        DeploymentFingerprint("sha256:" + "0" * 64).value,
    )
    with pytest.raises(DeploymentReplayFailed):
        replay_deployment_history(machine, (record,))


def test_restart_preserves_sequence_and_replays_without_external_effects(store) -> None:
    first = _deployment_event(1)
    second = _deployment_event(
        2,
        DeploymentLifecycleState.AUTHORIZATION_PENDING,
        DeploymentLifecycleState.AUTHORIZED,
        authorization=True,
    )
    _append(store, 1, first)
    reopened = SQLiteDeploymentJournalStore(DeploymentSQLiteConfig(store.database_path))
    reopened.initialize()
    machine = DeploymentMachineKey(
        DeploymentMachineKind.DEPLOYMENT, "deployment-attempt:persist"
    )
    assert reopened.latest_sequence(machine) == 1
    _append(reopened, 2, second)
    assert reopened.replay(machine).state is DeploymentLifecycleState.AUTHORIZED


def test_unknown_and_missing_evidence_remain_exact_after_restart(store) -> None:
    events = (
        _deployment_event(1),
        _deployment_event(2, DeploymentLifecycleState.AUTHORIZATION_PENDING, DeploymentLifecycleState.AUTHORIZED, authorization=True),
        _deployment_event(3, DeploymentLifecycleState.AUTHORIZED, DeploymentLifecycleState.PREPARED),
        _deployment_event(4, DeploymentLifecycleState.PREPARED, DeploymentLifecycleState.APPLYING),
        _deployment_event(5, DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.APPLY_OUTCOME_UNKNOWN),
    )
    unknown = replace(
        events[-1], failure_class=TransitionFailureClass.EXTERNAL_OUTCOME_UNKNOWN
    )
    events = (*events[:-1], unknown)
    for sequence, event in enumerate(events, 1):
        _append(store, sequence, event)
    machine = DeploymentMachineKey(DeploymentMachineKind.DEPLOYMENT, events[0].attempt_id.value)
    assert store.replay(machine).state is DeploymentLifecycleState.APPLY_OUTCOME_UNKNOWN

    other_path = store.database_path.parent / "missing.sqlite3"
    other = SQLiteDeploymentJournalStore(DeploymentSQLiteConfig(other_path.resolve()))
    other.initialize()
    for sequence, event in enumerate(events[:4], 1):
        _append(other, sequence, event)
    assert other.replay(machine).state is DeploymentLifecycleState.APPLYING


def _drop_update_trigger(connection: sqlite3.Connection) -> None:
    connection.execute("DROP TRIGGER deployment_journal_no_update")


def _restore_update_trigger(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TRIGGER deployment_journal_no_update BEFORE UPDATE "
        "ON deployment_journal_events BEGIN SELECT RAISE(ABORT, 'append-only'); END"
    )


def test_append_only_trigger_blocks_update_and_delete(store) -> None:
    _append(store, 1, _deployment_event(1))
    with sqlite3.connect(store.database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE deployment_journal_events SET sequence=2")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM deployment_journal_events")


@pytest.mark.parametrize("mutation", ["checksum", "malformed", "sequence", "machine"])
def test_corruption_fails_closed(store, mutation) -> None:
    _append(store, 1, _deployment_event(1))
    with sqlite3.connect(store.database_path) as connection:
        _drop_update_trigger(connection)
        if mutation == "checksum":
            connection.execute("UPDATE deployment_journal_events SET payload_checksum='sha256:bad'")
        elif mutation == "malformed":
            connection.execute("UPDATE deployment_journal_events SET canonical_payload='{' ")
        elif mutation == "sequence":
            connection.execute("UPDATE deployment_journal_events SET sequence=2")
        else:
            connection.execute("UPDATE deployment_journal_events SET machine_identity='deployment-attempt:foreign'")
        _restore_update_trigger(connection)
    machine = DeploymentMachineKey(DeploymentMachineKind.DEPLOYMENT, "deployment-attempt:persist")
    if mutation != "machine":
        with pytest.raises((DeploymentPersistenceCorrupt, DeploymentSequenceGap)):
            store.history(machine)
    assert store.health().corruption_detected


def test_incompatible_schema_and_reducer_invalid_history_fail_closed(store) -> None:
    with sqlite3.connect(store.database_path) as connection:
        connection.execute("UPDATE deployment_schema_metadata SET schema_version=99")
    with pytest.raises(DeploymentSchemaIncompatible):
        store.initialize()

    path = store.database_path.parent / "reducer.sqlite3"
    other = SQLiteDeploymentJournalStore(DeploymentSQLiteConfig(path.resolve()))
    other.initialize()
    event = _deployment_event(1)
    _append(other, 1, event)
    forged = replace(event, resulting_state=DeploymentLifecycleState.APPLIED, apply_receipt_reference=ApplyReceiptReference("apply-receipt:forged"))
    payload = canonical_json(forged)
    checksum = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    with sqlite3.connect(path) as connection:
        _drop_update_trigger(connection)
        connection.execute(
            "UPDATE deployment_journal_events SET canonical_payload=?,payload_checksum=?,event_fingerprint=?",
            (payload, checksum, forged.fingerprint.value),
        )
        _restore_update_trigger(connection)
    machine = DeploymentMachineKey(DeploymentMachineKind.DEPLOYMENT, event.attempt_id.value)
    with pytest.raises(DeploymentReplayFailed):
        other.replay(machine)


def test_persisted_payload_contains_only_safe_domain_facts(store) -> None:
    _append(store, 1, _deployment_event(1))
    with sqlite3.connect(store.database_path) as connection:
        payload = connection.execute(
            "SELECT canonical_payload FROM deployment_journal_events"
        ).fetchone()[0]
    assert "secret-value" not in payload
    assert "provider-payload" not in payload
    assert "C:\\" not in payload
    assert "artifact-bytes" not in payload
