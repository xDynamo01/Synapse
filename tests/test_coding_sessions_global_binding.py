from pathlib import Path

import pytest

from synapse.bootstrap.adapters.coding_sessions import (
    CodingSessionsSlotState,
    CodingSessionsSlotUnavailable,
    DeferredCodingSessionsRuntime,
)


def test_coding_sessions_global_slot_is_inert_and_lifecycle_owned(tmp_path: Path) -> None:
    database = tmp_path / "coding-sessions.sqlite3"
    slot = DeferredCodingSessionsRuntime(database)
    assert slot.state is CodingSessionsSlotState.CONSTRUCTED
    assert not database.exists()
    with pytest.raises(CodingSessionsSlotUnavailable):
        _ = slot.runtime

    slot.start()
    health = slot.runtime.health()
    assert database.is_file()
    assert health.open and health.persistence_available and health.schema_valid
    states = {item.capability.value: item.state.value for item in health.integrations}
    assert states["persistence"] == "supported"
    assert all(state == "unavailable" for capability, state in states.items() if capability != "persistence")
    slot.start()
    slot.close()
    assert slot.state is CodingSessionsSlotState.CLOSED
    with pytest.raises(CodingSessionsSlotUnavailable):
        slot.start()
