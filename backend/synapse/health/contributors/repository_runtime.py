"""Factual Repository Runtime health projection owned by Health."""

from collections.abc import Callable
from dataclasses import dataclass

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.models import ComponentHealth, HealthCheckItem


@dataclass(frozen=True)
class RepositoryRuntimeHealthFacts:
    lifecycle: str
    persistence_available: bool
    schema_valid: bool
    local_adapter_available: bool
    git_available: bool
    platform: str
    supported: tuple[str, ...]
    degraded: tuple[str, ...]
    unsupported: tuple[str, ...]
    unavailable: tuple[str, ...]
    coding_sessions_configured: bool
    managed_resources_healthy: bool


class RepositoryRuntimeHealthContributor:
    contributor_id = "repository_runtime"

    def __init__(self, facts: Callable[[], RepositoryRuntimeHealthFacts]) -> None:
        self._facts = facts

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        facts = self._facts()
        ready = (
            facts.lifecycle == "started"
            and facts.persistence_available
            and facts.schema_valid
            and facts.local_adapter_available
            and facts.git_available
            and facts.managed_resources_healthy
        )
        component = ComponentHealth(
            component_id="repository_runtime.runtime",
            module="synapse.repository_runtime",
            state="ready" if ready else "degraded",
            configured=True,
            available=facts.persistence_available and facts.local_adapter_available,
            ready=ready,
            degraded=not ready,
            dependencies=["storage", "git"],
            recommendations=[] if ready else ["Inspect Repository Runtime persistence and Git facts."],
            metadata={
                "lifecycle": facts.lifecycle,
                "persistence_available": facts.persistence_available,
                "schema_valid": facts.schema_valid,
                "local_adapter_available": facts.local_adapter_available,
                "git_available": facts.git_available,
                "platform": facts.platform,
                "supported": facts.supported,
                "degraded": facts.degraded,
                "unsupported": facts.unsupported,
                "unavailable": facts.unavailable,
                "coding_sessions_configured": facts.coding_sessions_configured,
                "managed_resources_healthy": facts.managed_resources_healthy,
            },
        )
        return HealthContribution(
            components=((119, component),),
            checks=((1_190, HealthCheckItem(
                id="repository_runtime.runtime",
                label="Repository Runtime",
                severity="ok" if ready else "warning",
                summary="Repository Runtime is ready." if ready else "Repository Runtime is unavailable.",
                metadata={"correlation_id": context.correlation_id},
            )),),
            metrics={"repository_runtime_ready": int(ready)},
        )
