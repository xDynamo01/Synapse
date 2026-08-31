from pathlib import Path

import pytest

from synapse.bootstrap.adapters.skills_phase2 import (
    DeferredSkillsPhase2Runtime,
    SkillsPhase2SlotState,
    SkillsPhase2SlotUnavailable,
)
from synapse.skills.composition import SkillsRuntimeState


def test_skills_phase2_slot_is_inert_and_lifecycle_owned(tmp_path: Path) -> None:
    database = tmp_path / "skills-phase2.sqlite3"
    slot = DeferredSkillsPhase2Runtime(database)
    assert slot.state is SkillsPhase2SlotState.CONSTRUCTED
    assert not database.exists()
    with pytest.raises(SkillsPhase2SlotUnavailable):
        _ = slot.runtime
    slot.start()
    health = slot.runtime.health()
    assert database.is_file()
    assert health.runtime_state is SkillsRuntimeState.READY
    assert health.schema_current and health.database_reachable
    assert health.compatibility_enabled is False
    slot.close()
    assert slot.state is SkillsPhase2SlotState.CLOSED
