from __future__ import annotations

from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks, component


class IntelligenceBoundaryHealthContributor:
    contributor_id = "intelligence_boundary"

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        status = self.runtime.status()
        unguarded = len(status["unguarded_paths"])
        invalid = int(status["invalid_or_expired_profiles"])
        return HealthContribution(
            components=(
                component(
                    97,
                    "intelligence_boundary",
                    self.runtime,
                    ["storage", "approvals", "tools"],
                    details={"status": "degraded" if unguarded else "ready", **status},
                ),
            ),
            checks=checks(
                check(
                    970,
                    "intelligence_boundary.unguarded_paths",
                    unguarded > 0,
                    "warning",
                    f"{unguarded} known unguarded path limitation(s).",
                ),
                check(
                    971,
                    "intelligence_boundary.invalid_trust_profiles",
                    invalid > 0,
                    "warning",
                    f"{invalid} invalid or expired trust profile(s).",
                ),
            ),
            metrics={
                "intelligence_assets": int(status["assets"]),
                "intelligence_decisions": int(status["decisions"]),
                "intelligence_manifests": int(status["manifests"]),
                "intelligence_ledger_records": int(status["ledger_records"]),
                "intelligence_unguarded_paths": unguarded,
            },
        )
