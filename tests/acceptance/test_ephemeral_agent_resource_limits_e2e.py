from pathlib import Path

from .agent_kinds_support import (
    Capacity,
    ControlledPressure,
    create_complex_mission,
    provision,
    runtime_at,
)


def test_ephemeral_agent_resource_limits_e2e(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    provision(runtime, "central", tools=["read"])
    mission, plan = create_complex_mission(runtime, count=3)
    runtime.workforce_planner.resource_pressure = ControlledPressure(
        Capacity(True, pressure_level="high", recommended_concurrency=1)
    )
    reduced = runtime.workforce_planner.plan(
        mission, plan, parent_agent_id="central", strategy="parallel"
    )
    assert reduced.max_concurrency == 1 and reduced.strategy == "sequential"
    runtime.workforce_planner.resource_pressure = ControlledPressure(
        Capacity(False, "critical pressure", "critical")
    )
    deferred = runtime.workforce_planner.plan(
        mission, plan, parent_agent_id="central", strategy="parallel"
    )
    assert not deferred.required and deferred.strategy == "deferred"
