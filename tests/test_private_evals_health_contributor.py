from pathlib import Path

from synapse.bootstrap.adapters.private_evals import build_deferred_private_evals
from synapse.health.contracts import HealthCheckContext


def context() -> HealthCheckContext:
    return HealthCheckContext("private-evals-health", None, "test", 1.0, False, {})


def test_private_evals_health_is_degraded_before_start(tmp_path: Path) -> None:
    slot = build_deferred_private_evals(tmp_path / "private-evals.sqlite3")
    component = slot.health_contributor().collect_health(context()).components[0][1]
    assert component.state == "degraded"
    assert component.available is False
    assert component.metadata["lifecycle"] == "constructed"


def test_private_evals_health_preserves_unavailable_capabilities(tmp_path: Path) -> None:
    slot = build_deferred_private_evals(tmp_path / "private-evals.sqlite3")
    slot.start()
    component = slot.health_contributor().collect_health(context()).components[0][1]
    assert component.state == "degraded"
    assert component.available is True
    assert component.ready is False
    assert component.metadata["persistence"] == "available"
    assert component.metadata["case_execution"] == "unavailable"
    assert component.metadata["case_evaluator"] == "unavailable"
    slot.close()
