from pathlib import Path

from synapse.bootstrap.adapters.repository_runtime import DeferredRepositoryRuntime
from synapse.health.contracts import HealthCheckContext


def context() -> HealthCheckContext:
    return HealthCheckContext("repository-health", None, "test", 1.0, False, {})


def test_repository_health_is_factual_across_lifecycle(tmp_path: Path) -> None:
    slot = DeferredRepositoryRuntime(Path(__file__).parents[1], tmp_path)
    before = slot.health_contributor().collect_health(context()).components[0][1]
    assert before.state == "degraded" and before.available is False
    slot.start()
    after = slot.health_contributor().collect_health(context()).components[0][1]
    assert after.state == "ready" and after.ready is True
    assert after.metadata["coding_sessions_configured"] is False
    assert "commit" in after.metadata["unsupported"]
    assert "push" in after.metadata["unsupported"]
    slot.close()
