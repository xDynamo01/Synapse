from __future__ import annotations

from .world_attention_support import DomainFixture, FixedDecisionRuntime, MissionSpy, loop


def test_agent_loop_creates_mission_reference_without_waiting() -> None:
    fixture = DomainFixture()
    try:
        missions = MissionSpy()
        fixture.high_item("start_mission")
        runtime = loop(fixture, FixedDecisionRuntime("start_mission", {"title": "Investigate"}), mission_runtime=missions)
        result = runtime.run_cycle("acceptance.mission")
        assert result.action_result.output_reference == {"mission_id": "mission-1"}
        assert result.action_result.verification["verified"]
        assert missions.calls == 1
    finally:
        fixture.close()
