from pathlib import Path

from synapse.bootstrap.adapters.skills_phase2 import DeferredSkillsPhase2Runtime
from synapse.health.contracts import HealthCheckContext


def context() -> HealthCheckContext:
    return HealthCheckContext("skills-phase2-health", None, "test", 1.0, False, {})


def test_skills_phase2_health_is_factual_across_lifecycle(tmp_path: Path) -> None:
    slot = DeferredSkillsPhase2Runtime(tmp_path / "skills.sqlite3")
    before = slot.health_contributor().collect_health(context()).components[0][1]
    assert before.state == "degraded" and before.available is False
    slot.start()
    after = slot.health_contributor().collect_health(context()).components[0][1]
    assert after.state == "ready" and after.ready is True
    assert after.metadata["compatibility_enabled"] is False
    assert after.metadata["integrity"] == "not_checked"
    slot.close()
