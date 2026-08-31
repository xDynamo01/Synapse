from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from synapse.health.models import ComponentHealth, HealthCheckItem, HomelabHealthSummary


@dataclass(frozen=True)
class HealthCheckContext:
    timestamp: str
    correlation_id: str | None
    mode: str
    timeout_budget_seconds: float
    include_diagnostics: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthContribution:
    components: tuple[tuple[int, ComponentHealth], ...] = ()
    summary: dict[str, Any] = field(default_factory=dict)
    checks: tuple[tuple[int, HealthCheckItem], ...] = ()
    metrics: dict[str, int] = field(default_factory=dict)


class HealthContributor(Protocol):
    contributor_id: str

    def collect_health(self, context: HealthCheckContext) -> HealthContribution: ...


class HealthSnapshotSource(Protocol):
    def summary(self) -> HomelabHealthSummary: ...
