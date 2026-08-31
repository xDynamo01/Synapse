from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from synapse.sandbox import OpaqueReference, SandboxWorkspaceId
from synapse.sandbox_drivers import (
    WindowsDriverDurableEventV1,
    WindowsDriverEventType,
    WindowsDriverStateIntegrityError,
    WindowsReconciliationAction,
    WindowsRestartClassification,
    WindowsSandboxDriverStore,
    WindowsSandboxReconciliationPlanner,
)

NOW = datetime.now(timezone.utc)
ATTEMPT = OpaqueReference("driver-attempt:durable")
WORKSPACE = SandboxWorkspaceId("workspace:durable")


def initialized(path):
    selected = WindowsSandboxDriverStore(path)
    selected.initialize()
    return selected


def event(sequence, kind, **changes):
    base = WindowsDriverDurableEventV1(
        OpaqueReference(f"driver-event:{sequence}"),
        ATTEMPT,
        WORKSPACE,
        sequence,
        kind,
        NOW + timedelta(seconds=sequence),
    )
    return replace(base, **changes)


def test_empty_store_health_and_first_attempt(tmp_path) -> None:
    store = initialized(tmp_path / "driver.sqlite3")
    health = store.health()
    assert health.store_available and health.schema_compatible and health.integrity_valid
    assert health.replay_available and health.restart_projection_available
    assert not health.live_handle_recovery_available
    assert not health.automatic_destructive_reconciliation_enabled
    assert store.replay() == ()
    assert store.append(event(1, WindowsDriverEventType.ATTEMPT_CREATED))
    assert len(store.replay()) == 1


def test_append_only_idempotency_sequence_and_contradiction(tmp_path) -> None:
    path = tmp_path / "driver.sqlite3"
    store = initialized(path)
    first = event(1, WindowsDriverEventType.ATTEMPT_CREATED)
    assert store.append(first)
    assert not store.append(first)
    with pytest.raises(WindowsDriverStateIntegrityError, match="contradiction"):
        store.append(replace(first, event_type=WindowsDriverEventType.JOB_CREATED))
    with pytest.raises(WindowsDriverStateIntegrityError, match="sequence"):
        store.append(event(3, WindowsDriverEventType.JOB_CREATED))
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append_only"):
            connection.execute("UPDATE driver_events SET event_type='changed'")
        with pytest.raises(sqlite3.IntegrityError, match="append_only"):
            connection.execute("DELETE FROM driver_events")


def test_durable_payload_contains_only_safe_metadata(tmp_path) -> None:
    path = tmp_path / "driver.sqlite3"
    store = initialized(path)
    store.append(
        event(
            1,
            WindowsDriverEventType.PROCESS_RESUMED,
            process_created=True,
            job_created=True,
            job_configured=True,
            containment_verified=True,
            process_resumed=True,
            historical_root_pid=4321,
            safe_references=(OpaqueReference("publication:safe"),),
        )
    )
    raw = path.read_bytes()
    assert b"secret-plaintext" not in raw
    assert b"stdout-payload" not in raw
    assert b"C:\\" not in raw
    projection = WindowsSandboxReconciliationPlanner().project(store.replay())[0]
    assert projection.historical_root_pid == 4321
    assert not projection.handles_recoverable


def test_restart_never_started_completed_and_termination_proof(tmp_path) -> None:
    planner = WindowsSandboxReconciliationPlanner()
    never = planner.project((event(1, WindowsDriverEventType.ATTEMPT_CREATED),))[0]
    assert never.classifications == (WindowsRestartClassification.NEVER_STARTED,)

    proof = OpaqueReference("termination-proof:one")
    completed_events = (
        event(1, WindowsDriverEventType.ATTEMPT_CREATED),
        event(
            2, WindowsDriverEventType.PROCESS_RESUMED, process_resumed=True, historical_root_pid=99
        ),
        event(3, WindowsDriverEventType.TERMINATION_PROVEN, termination_proof_reference=proof),
        event(4, WindowsDriverEventType.ATTEMPT_COMPLETED),
    )
    completed = planner.project(completed_events)[0]
    assert WindowsRestartClassification.COMPLETED_BEFORE_RESTART in completed.classifications
    assert WindowsRestartClassification.TERMINATED_AND_PROVEN in completed.classifications
    assert completed.termination_proof_reference == proof
    assert not completed.reconciliation_required


def test_crash_while_active_is_orphaned_and_pid_is_not_identity(tmp_path) -> None:
    path = tmp_path / "driver.sqlite3"
    store = initialized(path)
    store.append(event(1, WindowsDriverEventType.ATTEMPT_CREATED))
    store.append(
        event(
            2,
            WindowsDriverEventType.PROCESS_RESUMED,
            process_created=True,
            job_created=True,
            job_configured=True,
            containment_verified=True,
            process_resumed=True,
            historical_root_pid=777,
        )
    )
    restarted = initialized(path)
    projection = WindowsSandboxReconciliationPlanner().project(restarted.replay())[0]
    assert WindowsRestartClassification.ORPHANED in projection.classifications
    assert WindowsRestartClassification.STARTED_BUT_HANDLES_LOST in projection.classifications
    assert projection.historical_root_pid == 777 and not projection.handles_recoverable
    plan = WindowsSandboxReconciliationPlanner().plan(projection)
    assert plan.required_actions == (WindowsReconciliationAction.MANUAL_PROCESS_RECONCILIATION,)
    assert plan.automatic_actions == ()


def test_incomplete_states_plan_only_safe_or_manual_actions(tmp_path) -> None:
    events = (
        event(1, WindowsDriverEventType.ATTEMPT_CREATED),
        event(
            2,
            WindowsDriverEventType.PUBLICATION_STATE_OBSERVED,
            publication_state="publication_requested",
        ),
        event(3, WindowsDriverEventType.CLEANUP_STATE_OBSERVED, cleanup_state="partial"),
        event(4, WindowsDriverEventType.SECRET_STATE_OBSERVED, secret_state="revocation_unproven"),
        event(
            5,
            WindowsDriverEventType.OUTPUT_CAPTURE_OBSERVED,
            output_capture_state="finalization_incomplete",
        ),
    )
    planner = WindowsSandboxReconciliationPlanner()
    projection = planner.project(events)[0]
    assert {
        WindowsRestartClassification.PUBLICATION_INCOMPLETE,
        WindowsRestartClassification.CLEANUP_INCOMPLETE,
        WindowsRestartClassification.SECRET_REVOCATION_UNPROVEN,
        WindowsRestartClassification.OUTPUT_CAPTURE_INCOMPLETE,
        WindowsRestartClassification.RECONCILIATION_REQUIRED,
    } <= set(projection.classifications)
    plan = planner.plan(projection)
    assert WindowsReconciliationAction.OBTAIN_CURRENT_CLEANUP_AUTHORITY in plan.required_actions
    assert WindowsReconciliationAction.VERIFY_PUBLICATION_METADATA in plan.required_actions
    assert plan.automatic_actions == ()


def test_replay_is_deterministic_and_performs_no_host_effects(tmp_path) -> None:
    path = tmp_path / "driver.sqlite3"
    store = initialized(path)
    store.append(event(1, WindowsDriverEventType.ATTEMPT_CREATED))
    store.append(
        event(
            2, WindowsDriverEventType.PROCESS_RESUMED, process_resumed=True, historical_root_pid=12
        )
    )
    first = WindowsSandboxReconciliationPlanner().project(store.replay())
    second = WindowsSandboxReconciliationPlanner().project(initialized(path).replay())
    assert first == second
    assert WindowsSandboxReconciliationPlanner().plan(first[0]).automatic_actions == ()


def test_corruption_and_incompatible_schema_fail_closed(tmp_path) -> None:
    corrupt_path = tmp_path / "corrupt.sqlite3"
    store = initialized(corrupt_path)
    store.append(event(1, WindowsDriverEventType.ATTEMPT_CREATED))
    with sqlite3.connect(corrupt_path) as connection:
        connection.execute("DROP TRIGGER driver_events_no_update")
        connection.execute("UPDATE driver_events SET checksum='sha256:bad'")
    with pytest.raises(WindowsDriverStateIntegrityError, match="checksum"):
        store.replay()
    assert not store.health().integrity_valid

    incompatible_path = tmp_path / "incompatible.sqlite3"
    incompatible = initialized(incompatible_path)
    with sqlite3.connect(incompatible_path) as connection:
        connection.execute("UPDATE driver_schema SET schema_version=999")
    health = incompatible.health()
    assert not health.schema_compatible and not health.replay_available
    with pytest.raises(WindowsDriverStateIntegrityError, match="schema_incompatible"):
        incompatible.replay()
