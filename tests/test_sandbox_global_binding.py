from pathlib import Path

import pytest

from synapse.bootstrap.adapters.sandbox import (
    DeferredSandboxRuntime,
    SandboxSlotState,
    SandboxSlotUnavailable,
)
from synapse.bootstrap.adapters.sandbox_policy import (
    build_local_windows_sandbox_admission_policy,
)


def test_deferred_slot_is_inert_and_starts_without_execution_ports(tmp_path: Path) -> None:
    database = tmp_path / "sandbox-runtime.sqlite3"
    slot = DeferredSandboxRuntime(database)

    assert slot.state is SandboxSlotState.CONSTRUCTED
    assert not database.exists()
    with pytest.raises(SandboxSlotUnavailable):
        _ = slot.runtime

    slot.start()
    health = slot.runtime.health()
    assert slot.state is SandboxSlotState.STARTED
    assert database.is_file()
    assert health.persistence_available and health.schema_valid
    assert slot.runtime.policy == build_local_windows_sandbox_admission_policy()
    assert not health.materialization_ports_available
    assert not health.supervision_ports_available
    assert not health.isolation_driver_available
    assert not health.real_execution_available

    slot.close()
    assert slot.state is SandboxSlotState.CLOSED
    with pytest.raises(SandboxSlotUnavailable):
        _ = slot.runtime


def test_lifecycle_is_required_and_explicitly_non_executable(tmp_path: Path) -> None:
    resource = DeferredSandboxRuntime(tmp_path / "sandbox.sqlite3").lifecycle_resource()

    assert resource.required
    assert resource.metadata["failure_behavior"] == "rollback startup and fail the lifespan"
    assert resource.metadata["execution_activation"] == "unavailable"
