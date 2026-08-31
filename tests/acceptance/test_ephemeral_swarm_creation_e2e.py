from dataclasses import asdict
from pathlib import Path

import pytest

from synapse.ephemeral_agents.models import EphemeralAgentState
from synapse.missions.errors import SwarmInvalidStrategy
from synapse.swarm.strategies import STRATEGIES

from .agent_kinds_support import (
    create_complex_mission,
    provision,
    register_workers,
    runtime_at,
)


def test_ephemeral_swarm_creation_e2e(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    provision(runtime, "central", "coordinator", tools=["read"])
    mission, plan = create_complex_mission(runtime)
    register_workers(runtime, 2)
    swarm = runtime.swarm.create(mission.mission_id, "parallel", "central", [])
    workforce = runtime.swarm.get_workforce_plan(swarm.swarm_id)
    assert workforce.required and len(workforce.agents) == 2
    instances = runtime.swarm.provision_workforce(swarm.swarm_id)
    assert all(item.state is EphemeralAgentState.ASSIGNED for item in instances)
    updated_plan = runtime.planner.get_plan(mission.mission_id, plan.plan_id)
    assert all(task.metadata.get("ephemeral_agent_id") for task in updated_plan.tasks)

    outputs = []
    for item in instances:
        runtime.ephemeral_agents.start(item.ephemeral_agent_id)
        result = runtime.ephemeral_agents.complete(
            item.ephemeral_agent_id,
            output_reference=f"result:{item.task_id}",
            attempt_ids=[],
            verification={"approved": True},
        )
        outputs.append({"task_id": item.task_id, "agent_id": item.ephemeral_agent_id, "result": asdict(result)})
        runtime.ephemeral_agents.destroy(item.ephemeral_agent_id)
    consolidated = STRATEGIES["parallel"].finalize(
        runtime.swarm.get(swarm.swarm_id), outputs, {"complete": True}
    )
    assert len(consolidated.outputs) == 2
    assert all(runtime.ephemeral_agents.get(item.ephemeral_agent_id).state is EphemeralAgentState.DESTROYED for item in instances)
    assert runtime.ephemeral_agents.contexts.list_all() == ()


def test_required_workforce_rejects_missing_ephemeral_runtime(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    provision(runtime, "central", "coordinator", tools=["read"])
    mission, _plan = create_complex_mission(runtime)
    register_workers(runtime, 2)
    swarm = runtime.swarm.create(mission.mission_id, "parallel", "central", [])
    runtime.swarm.ephemeral_agents = None

    with pytest.raises(SwarmInvalidStrategy, match="Ephemeral agent runtime is unavailable"):
        runtime.swarm.provision_workforce(swarm.swarm_id)
