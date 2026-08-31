"""Composition adapter for Deployment's neutral Health projection."""

from synapse.deployment_composition import DeploymentRuntime
from synapse.health.contributors.deployment import (
    DeploymentHealthContributor,
    DeploymentHealthFacts,
)


def build_deployment_health_contributor(runtime: DeploymentRuntime) -> DeploymentHealthContributor:
    def facts() -> DeploymentHealthFacts:
        health = runtime.health()
        return DeploymentHealthFacts(
            lifecycle=health.lifecycle.value,
            persistence=health.persistence.value,
            fencing=health.fencing.value,
            apply=health.apply.value,
            verification=health.verification.value,
            rollback=health.rollback.value,
            reconciliation=health.reconciliation.value,
        )

    return DeploymentHealthContributor(facts)
