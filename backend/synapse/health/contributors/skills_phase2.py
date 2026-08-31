"""Factual Skills Phase 2 health projection owned by Health."""

from collections.abc import Callable
from dataclasses import dataclass

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.models import ComponentHealth, HealthCheckItem


@dataclass(frozen=True)
class SkillsPhase2HealthFacts:
    lifecycle: str
    status: str
    schema_current: bool
    database_reachable: bool
    migration: str
    integrity: str
    foreign_keys: str
    compatibility_enabled: bool


class SkillsPhase2HealthContributor:
    contributor_id = "skills_phase2"

    def __init__(self, facts: Callable[[], SkillsPhase2HealthFacts]) -> None:
        self._facts = facts

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        facts = self._facts()
        ready = (
            facts.lifecycle == "started"
            and facts.status == "healthy"
            and facts.schema_current
            and facts.database_reachable
            and not facts.compatibility_enabled
        )
        component = ComponentHealth(
            component_id="skills.phase2",
            module="synapse.skills",
            state="ready" if ready else "degraded",
            configured=True,
            available=facts.database_reachable,
            ready=ready,
            degraded=not ready,
            dependencies=["storage"],
            recommendations=[] if ready else ["Inspect Skills Phase 2 persistence health."],
            metadata={
                "lifecycle": facts.lifecycle,
                "status": facts.status,
                "schema_current": facts.schema_current,
                "database_reachable": facts.database_reachable,
                "migration": facts.migration,
                "integrity": facts.integrity,
                "foreign_keys": facts.foreign_keys,
                "compatibility_enabled": facts.compatibility_enabled,
            },
        )
        return HealthContribution(
            components=((118, component),),
            checks=((1_180, HealthCheckItem(
                id="skills.phase2",
                label="Skills Phase 2",
                severity="ok" if ready else "warning",
                summary="Skills Phase 2 is ready." if ready else "Skills Phase 2 is unavailable.",
                metadata={"correlation_id": context.correlation_id},
            )),),
            metrics={"skills_phase2_ready": int(ready)},
        )
