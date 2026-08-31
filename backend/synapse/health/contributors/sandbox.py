"""Factual Sandbox policy-boundary health projection owned by Health."""

from collections.abc import Callable
from dataclasses import dataclass

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.models import ComponentHealth, HealthCheckItem


@dataclass(frozen=True, slots=True)
class SandboxHealthFacts:
    lifecycle: str
    persistence_available: bool
    schema_valid: bool
    policy_version: str
    configured_adapters: tuple[str, ...]
    materialization_ports_available: bool
    supervision_ports_available: bool
    isolation_driver_available: bool
    real_execution_available: bool
    managed_resources_healthy: bool
    recovery_finding_count: int


class SandboxHealthContributor:
    contributor_id = "sandbox_runtime"

    def __init__(self, facts: Callable[[], SandboxHealthFacts]) -> None:
        self._facts = facts

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        facts = self._facts()
        ready = (
            facts.lifecycle == "started"
            and facts.persistence_available
            and facts.schema_valid
            and bool(facts.policy_version)
            and facts.managed_resources_healthy
            and facts.recovery_finding_count == 0
        )
        component = ComponentHealth(
            component_id="sandbox.runtime",
            module="synapse.sandbox",
            state="ready" if ready else "degraded",
            configured=True,
            available=facts.persistence_available,
            ready=ready,
            degraded=not ready,
            dependencies=["storage", "sandbox_admission_policy"],
            recommendations=(
                []
                if ready
                else ["Inspect Sandbox persistence, policy lifecycle and recovery facts."]
            ),
            metadata={
                "lifecycle": facts.lifecycle,
                "policy_version": facts.policy_version,
                "configured_adapters": facts.configured_adapters,
                "materialization_ports_available": facts.materialization_ports_available,
                "supervision_ports_available": facts.supervision_ports_available,
                "isolation_driver_available": facts.isolation_driver_available,
                "real_execution_available": facts.real_execution_available,
                "managed_resources_healthy": facts.managed_resources_healthy,
                "recovery_finding_count": facts.recovery_finding_count,
            },
        )
        return HealthContribution(
            components=((118, component),),
            checks=(
                (
                    1_185,
                    HealthCheckItem(
                        id="sandbox.runtime",
                        label="Sandbox Runtime",
                        severity="ok" if ready else "warning",
                        summary=(
                            "Sandbox policy boundary is ready; real execution is unavailable."
                            if ready
                            else "Sandbox policy boundary is unavailable."
                        ),
                        metadata={"correlation_id": context.correlation_id},
                    ),
                ),
            ),
            metrics={
                "sandbox_runtime_ready": int(ready),
                "sandbox_real_execution_available": int(facts.real_execution_available),
            },
        )
