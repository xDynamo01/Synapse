"""Factual Private Evals health projection owned by Health."""

from collections.abc import Callable
from dataclasses import dataclass

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.models import ComponentHealth, HealthCheckItem


@dataclass(frozen=True)
class PrivateEvalsHealthFacts:
    lifecycle: str
    persistence: str
    read_only: bool
    commands_available: bool
    queries_available: bool
    intelligence_snapshot: str
    case_execution: str
    case_evaluator: str
    governance_write: str
    limitations: tuple[str, ...]


class PrivateEvalsHealthContributor:
    contributor_id = "private_evals"

    def __init__(self, facts: Callable[[], PrivateEvalsHealthFacts]) -> None:
        self._facts = facts

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        facts = self._facts()
        external = (
            facts.intelligence_snapshot,
            facts.case_execution,
            facts.case_evaluator,
            facts.governance_write,
        )
        ready = facts.lifecycle == "externally_bound" and all(
            state == "available" for state in external
        )
        available = facts.persistence == "available"
        component = ComponentHealth(
            component_id="private_evals.runtime",
            module="synapse.private_evals",
            state="ready" if ready else "degraded",
            configured=True,
            available=available,
            ready=ready,
            degraded=not ready,
            dependencies=["storage", "intelligence_boundary", "sandbox", "project_governance"],
            recommendations=[] if ready else ["Configure required Private Evals capabilities."],
            metadata={
                "lifecycle": facts.lifecycle,
                "persistence": facts.persistence,
                "read_only": facts.read_only,
                "commands_available": facts.commands_available,
                "queries_available": facts.queries_available,
                "intelligence_snapshot": facts.intelligence_snapshot,
                "case_execution": facts.case_execution,
                "case_evaluator": facts.case_evaluator,
                "governance_write": facts.governance_write,
                "limitations": facts.limitations,
            },
        )
        return HealthContribution(
            components=((116, component),),
            checks=((1_160, HealthCheckItem(
                id="private_evals.runtime",
                label="Private Evals Runtime",
                severity="ok" if ready else "warning",
                summary="Private Evals is ready." if ready else "Private Evals capabilities are limited.",
                metadata={"correlation_id": context.correlation_id},
            )),),
            metrics={"private_evals_ready": int(ready)},
        )
