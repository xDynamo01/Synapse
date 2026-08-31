from __future__ import annotations

from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks, component


class ProjectGovernanceHealthContributor:
    contributor_id = "project_governance"

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        status = self.runtime.health_snapshot()
        critical = int(status["rfc_conflicts"]) + int(status["unresolved_critical_questions"])
        return HealthContribution(
            components=(
                component(
                    96,
                    "project_governance",
                    self.runtime,
                    ["storage", "tools"],
                    details={"status": "ready", **status},
                ),
            ),
            checks=checks(
                check(
                    960,
                    "project_governance.conflicts",
                    critical > 0,
                    "warning",
                    f"{critical} critical project governance issue(s).",
                ),
                check(
                    961,
                    "project_governance.stale_plans",
                    int(status["stale_plans"]) > 0,
                    "warning",
                    f"{status['stale_plans']} stale implementation plan(s).",
                ),
            ),
            metrics={
                "project_governance_projects": int(status["projects"]),
                "project_governance_rfc_conflicts": int(status["rfc_conflicts"]),
                "project_governance_stale_plans": int(status["stale_plans"]),
                "project_governance_missing_approvals": int(status["missing_approvals"]),
            },
        )
