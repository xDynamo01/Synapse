from __future__ import annotations

from pathlib import Path

from synapse.bootstrap.adapters.deployment import build_deployment_health_contributor
from synapse.deployment_composition import (
    DeploymentRuntimeConfig,
    build_deployment_runtime,
)
from synapse.health.contracts import HealthCheckContext


def context() -> HealthCheckContext:
    return HealthCheckContext("2026-08-20T00:00:00+00:00", None, "test", 1.0)


def test_contributor_reports_unstarted_runtime_as_degraded(tmp_path: Path) -> None:
    runtime = build_deployment_runtime(DeploymentRuntimeConfig(tmp_path / "deployment.sqlite3"))

    contribution = build_deployment_health_contributor(runtime).collect_health(context())
    component = contribution.components[0][1]
    assert component.state == "degraded"
    assert component.ready is False
    assert contribution.checks[0][1].severity == "warning"


def test_contributor_reports_started_foundation_without_widening_optional_ports(
    tmp_path: Path,
) -> None:
    runtime = build_deployment_runtime(DeploymentRuntimeConfig(tmp_path / "deployment.sqlite3"))
    runtime.start()

    contribution = build_deployment_health_contributor(runtime).collect_health(context())
    component = contribution.components[0][1]
    assert component.state == "ready"
    assert component.ready is True
    assert component.metadata["apply"] == "unavailable"
    assert component.metadata["verification"] == "unavailable"
    assert component.metadata["rollback"] == "unavailable"


def test_contributor_preserves_reconciliation_as_action_required(tmp_path: Path) -> None:
    runtime = build_deployment_runtime(
        DeploymentRuntimeConfig(
            tmp_path / "deployment.sqlite3",
            reconciliation_required=True,
        )
    )
    runtime.start()

    contribution = build_deployment_health_contributor(runtime).collect_health(context())
    component = contribution.components[0][1]
    assert component.state == "action_required"
    assert component.ready is False
    assert contribution.checks[0][1].severity == "critical"
