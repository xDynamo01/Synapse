from pathlib import Path

import pytest

from synapse.bootstrap.adapters.private_evals import (
    PrivateEvalsSlotState,
    PrivateEvalsSlotUnavailable,
    build_deferred_private_evals,
)
from synapse.private_evals import CapabilityBindingStatus, PrivateEvalsLifecycleState


def test_private_evals_slot_is_inert_until_started(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    slot = build_deferred_private_evals(database)

    assert slot.state is PrivateEvalsSlotState.CONSTRUCTED
    assert not database.exists()
    with pytest.raises(PrivateEvalsSlotUnavailable):
        _ = slot.handle


def test_private_evals_slot_starts_with_explicit_unavailable_bindings(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    slot = build_deferred_private_evals(database)
    slot.start()

    readiness = slot.handle.readiness
    assert database.is_file()
    assert slot.state is PrivateEvalsSlotState.STARTED
    assert readiness.lifecycle_state is PrivateEvalsLifecycleState.DEGRADED
    assert readiness.persistence_status is CapabilityBindingStatus.AVAILABLE
    assert all(
        capability.status is CapabilityBindingStatus.UNAVAILABLE
        for capability in (
            readiness.intelligence_snapshot,
            readiness.case_execution,
            readiness.case_evaluator,
            readiness.governance_write,
        )
    )
    slot.start()
    slot.close()
    assert slot.state is PrivateEvalsSlotState.CLOSED
    with pytest.raises(PrivateEvalsSlotUnavailable):
        _ = slot.handle
    slot.close()


def test_closed_private_evals_slot_cannot_restart(tmp_path: Path) -> None:
    slot = build_deferred_private_evals(tmp_path / "private-evals.sqlite3")
    slot.close()

    with pytest.raises(PrivateEvalsSlotUnavailable):
        slot.start()
