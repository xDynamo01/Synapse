from pathlib import Path

from synapse.bootstrap.adapters.coding_sessions import DeferredCodingSessionsRuntime
from synapse.health.contracts import HealthCheckContext


def context() -> HealthCheckContext:
    return HealthCheckContext("coding-sessions-health", None, "test", 1.0, False, {})


def test_coding_sessions_health_is_degraded_before_start(tmp_path: Path) -> None:
    slot = DeferredCodingSessionsRuntime(tmp_path / "coding-sessions.sqlite3")
    component = slot.health_contributor().collect_health(context()).components[0][1]
    assert component.state == "degraded"
    assert component.available is False
    assert component.metadata["lifecycle"] == "constructed"


def test_coding_sessions_health_preserves_unavailable_integrations(tmp_path: Path) -> None:
    slot = DeferredCodingSessionsRuntime(tmp_path / "coding-sessions.sqlite3")
    slot.start()
    component = slot.health_contributor().collect_health(context()).components[0][1]
    states = dict(component.metadata["integrations"])
    assert component.state == "degraded"
    assert component.available is True
    assert states["persistence"] == "supported"
    assert states["repository-runtime"] == "unavailable"
    assert states["sandbox-concrete-execution"] == "unavailable"
    slot.close()
