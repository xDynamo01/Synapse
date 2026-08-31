from pathlib import Path

from .agent_kinds_support import provision, runtime_at


def test_persistent_subagent_parallel_project_e2e(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    provision(runtime, "central", "coordinator")
    provision(runtime, "project", "project_specialist")
    runtime.primary_agent.set_primary(runtime.context(), "central")
    first = runtime.missions.create_mission("Primary project", owner_agent_id="central")
    second = runtime.missions.create_mission("Parallel project", owner_agent_id="project")
    assert first.owner_agent_id != second.owner_agent_id
    assert runtime.agents.get("central").kind.value == "persistent"
    assert runtime.agents.get("project").kind.value == "persistent"
    assert runtime.data_dir.resolve("agents/central/MEMORY.md") != runtime.data_dir.resolve(
        "agents/project/MEMORY.md"
    )
