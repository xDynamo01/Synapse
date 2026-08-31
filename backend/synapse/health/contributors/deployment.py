"""Factual Deployment health projection owned by Health."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.models import ComponentHealth, HealthCheckItem


@dataclass(frozen=True)
class DeploymentHealthFacts:
    lifecycle: str
    persistence: str
    fencing: str
    apply: str
    verification: str
    rollback: str
    reconciliation: str


class DeploymentHealthContributor:
    contributor_id = "deployment"

    def __init__(self, facts: Callable[[], DeploymentHealthFacts]) -> None:
        self._facts = facts

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        health = self._facts()
        persistence_available = health.persistence == "available"
        fencing_available = health.fencing == "available"
        reconciliation_required = health.reconciliation == "required"
        ready = (
            health.lifecycle == "started"
            and persistence_available
            and fencing_available
            and not reconciliation_required
        )
        state = "ready" if ready else "action_required" if reconciliation_required else "degraded"
        summary = (
            "Deployment reconciliation is required."
            if reconciliation_required
            else "Deployment persistence or fencing is unavailable."
            if not ready
            else "Deployment persistence and fencing are available."
        )
        component = ComponentHealth(
            component_id="deployment.runtime",
            module="synapse.deployment",
            state=state,
            configured=True,
            available=persistence_available and fencing_available,
            ready=ready,
            degraded=not ready,
            dependencies=["storage", "sandbox"],
            recommendations=[]
            if ready
            else ["Inspect Deployment health and reconciliation facts."],
            metadata={
                "lifecycle": health.lifecycle,
                "persistence": health.persistence,
                "fencing": health.fencing,
                "apply": health.apply,
                "verification": health.verification,
                "rollback": health.rollback,
                "reconciliation": health.reconciliation,
            },
        )
        check = HealthCheckItem(
            id="deployment.runtime",
            label="Deployment Runtime",
            severity="ok" if ready else "critical" if reconciliation_required else "warning",
            summary=summary,
            metadata={"correlation_id": context.correlation_id},
        )
        return HealthContribution(
            components=((115, component),),
            checks=((1_150, check),),
            metrics={
                "deployment_ready": int(ready),
                "deployment_reconciliation_required": int(reconciliation_required),
            },
        )
