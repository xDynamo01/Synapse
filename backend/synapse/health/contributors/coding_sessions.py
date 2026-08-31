"""Factual Coding Sessions health projection owned by Health."""

from collections.abc import Callable
from dataclasses import dataclass

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.models import ComponentHealth, HealthCheckItem


@dataclass(frozen=True)
class CodingSessionsHealthFacts:
    lifecycle: str
    persistence_available: bool
    schema_valid: bool
    managed_resources_healthy: bool
    integrations: tuple[tuple[str, str], ...]


class CodingSessionsHealthContributor:
    contributor_id = "coding_sessions"

    def __init__(self, facts: Callable[[], CodingSessionsHealthFacts]) -> None:
        self._facts = facts

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        facts = self._facts()
        external = tuple(state for capability, state in facts.integrations if capability != "persistence")
        ready = (
            facts.lifecycle == "started"
            and facts.persistence_available
            and facts.schema_valid
            and facts.managed_resources_healthy
            and all(state == "supported" for state in external)
        )
        available = facts.persistence_available and facts.schema_valid
        component = ComponentHealth(
            component_id="coding_sessions.runtime",
            module="synapse.coding_sessions",
            state="ready" if ready else "degraded",
            configured=True,
            available=available,
            ready=ready,
            degraded=not ready,
            dependencies=["storage", "repository_runtime", "sandbox", "private_evals", "deployment"],
            recommendations=[] if ready else ["Configure required Coding Sessions integrations."],
            metadata={
                "lifecycle": facts.lifecycle,
                "persistence_available": facts.persistence_available,
                "schema_valid": facts.schema_valid,
                "managed_resources_healthy": facts.managed_resources_healthy,
                "integrations": facts.integrations,
            },
        )
        return HealthContribution(
            components=((117, component),),
            checks=((1_170, HealthCheckItem(
                id="coding_sessions.runtime",
                label="Coding Sessions Runtime",
                severity="ok" if ready else "warning",
                summary="Coding Sessions is ready." if ready else "Coding Sessions integrations are limited.",
                metadata={"correlation_id": context.correlation_id},
            )),),
            metrics={"coding_sessions_ready": int(ready)},
        )
