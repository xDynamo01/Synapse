from pathlib import Path

from .agent_kinds_support import (
    create_complex_mission,
    provision,
    register_workers,
    runtime_at,
)


def test_mixed_persistent_ephemeral_swarm_e2e(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    provision(runtime, "central", "coordinator", tools=["read"])
    provision(runtime, "reviewer", "persistent_reviewer", tools=["read"])
    runtime.primary_agent.set_primary(runtime.context(), "central")
    mission, _ = create_complex_mission(runtime)
    register_workers(runtime, 2)
    swarm = runtime.swarm.create(
        mission.mission_id, "parallel", "central", ["reviewer"]
    )
    instances = runtime.swarm.provision_workforce(swarm.swarm_id)
    members = runtime.swarm.get(swarm.swarm_id).member_agent_ids
    assert "reviewer" in members
    assert all(item.ephemeral_agent_id in members for item in instances)
    assert runtime.primary_agent.get_primary().agent_id == "central"
    assert runtime.agents.get("reviewer").kind.value == "persistent"
