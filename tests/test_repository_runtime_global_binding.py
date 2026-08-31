from pathlib import Path

import pytest

from synapse.bootstrap.adapters.repository_runtime import (
    DeferredRepositoryRuntime,
    RepositoryRuntimeSlotState,
    RepositoryRuntimeSlotUnavailable,
)
from synapse.repository_runtime import RepositoryAdapterFeature


def test_repository_runtime_slot_is_inert_and_does_not_bind_mutation(tmp_path: Path) -> None:
    slot = DeferredRepositoryRuntime(Path(__file__).parents[1], tmp_path)
    database = tmp_path / "repository-runtime.sqlite3"
    assert slot.state is RepositoryRuntimeSlotState.CONSTRUCTED
    assert not database.exists()
    with pytest.raises(RepositoryRuntimeSlotUnavailable):
        _ = slot.runtime
    slot.start()
    health = slot.runtime.health()
    assert database.is_file() and health.persistence_available and health.schema_valid
    assert health.coding_sessions_configured is False
    assert RepositoryAdapterFeature.COMMIT in health.unsupported_features
    assert RepositoryAdapterFeature.PUSH in health.unsupported_features
    slot.close()


def test_repository_lifecycle_is_capability_conditional(tmp_path: Path) -> None:
    resource = DeferredRepositoryRuntime(tmp_path, tmp_path).lifecycle_resource()
    assert resource.required is False
    assert resource.metadata["failure_behavior"] == (
        "report degraded when the project root is not Git"
    )
