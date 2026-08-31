import pytest

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.missions.runtime import MissionRuntime

from .project_governance_support import approve, initialize, markdown, plan, runtime


def test_rfc_revision_stales_plan_and_blocks_mission_start(tmp_path):
    governance = runtime(tmp_path)
    initialize(governance)
    rfc = approve(governance)
    implementation = plan(governance)
    missions = MissionRuntime(
        DataDir(tmp_path), EventBus(tmp_path), implementation_binding=governance
    )
    mission = missions.create_mission(
        "Governed mission",
        project_id="synapse",
        rfc_id="RFC-0001",
        rfc_revision=rfc.revision,
        rfc_checksum=rfc.checksum,
        implementation_plan_id=implementation.plan_id,
        implementation_plan_revision=implementation.revision,
        implementation_plan_checksum=implementation.checksum,
    )
    governance.rfcs.revise(
        "synapse",
        "RFC-0001",
        markdown() + "\nChanged.",
        actor_id="author",
        change_summary="Changed requirements",
    )
    assert governance.plans.get(implementation.plan_id).status == "stale"
    with pytest.raises(ValidationError, match="RFC gate blocked"):
        missions.run_mission(mission.mission_id)
