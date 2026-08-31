from pathlib import Path

from synapse.bootstrap.adapters.sandbox import DeferredSandboxRuntime
from synapse.health.contracts import HealthCheckContext


def context() -> HealthCheckContext:
    return HealthCheckContext(
        "2026-08-20T00:00:00+00:00", "correlation:sandbox-health", "full", 1.0
    )


def test_health_is_degraded_before_lifecycle_start(tmp_path: Path) -> None:
    slot = DeferredSandboxRuntime(tmp_path / "sandbox.sqlite3")
    contribution = slot.health_contributor().collect_health(context())
    component = contribution.components[0][1]

    assert component.component_id == "sandbox.runtime"
    assert component.degraded and not component.ready
    assert component.metadata["lifecycle"] == "constructed"
    assert component.metadata["real_execution_available"] is False


def test_health_separates_ready_policy_boundary_from_real_execution(tmp_path: Path) -> None:
    slot = DeferredSandboxRuntime(tmp_path / "sandbox.sqlite3")
    slot.start()
    contribution = slot.health_contributor().collect_health(context())
    component = contribution.components[0][1]

    assert component.ready and not component.degraded
    assert component.metadata["policy_version"] == (
        "sandbox-admission-policy:local-windows-v1"
    )
    assert component.metadata["configured_adapters"] == ()
    assert component.metadata["materialization_ports_available"] is False
    assert component.metadata["supervision_ports_available"] is False
    assert component.metadata["isolation_driver_available"] is False
    assert component.metadata["real_execution_available"] is False
    assert contribution.metrics == {
        "sandbox_runtime_ready": 1,
        "sandbox_real_execution_available": 0,
    }
    slot.close()
