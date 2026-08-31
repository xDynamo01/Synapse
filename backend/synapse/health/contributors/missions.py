from __future__ import annotations

from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks, component


class MissionsHealthContributor:
    contributor_id = "missions"

    def __init__(self, missions: Any, mission_context: Any, mission_supervision: Any) -> None:
        self.missions = missions
        self.mission_context = mission_context
        self.mission_supervision = mission_supervision

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        active = self.missions.active_missions_count() if self.missions else 0
        failed = self.missions.failed_missions_count() if self.missions else 0
        try:
            critical_context = (
                self.mission_context.critical_missions_count() if self.mission_context else 0
            )
        except Exception:
            critical_context = 0
        try:
            warning = (
                self.mission_supervision.warning_missions_count() if self.mission_supervision else 0
            )
            critical = (
                self.mission_supervision.critical_missions_count()
                if self.mission_supervision
                else 0
            )
        except Exception:
            warning = critical = 0
        return HealthContribution(
            components=(component(5, "missions", self.missions, ["agents", "tools"]),),
            summary={
                "active_missions_count": active,
                "failed_missions_count": failed,
                "missions_with_critical_context": critical_context,
                "missions_warning_count": warning,
                "missions_critical_count": critical,
            },
            checks=checks(
                check(
                    21,
                    "missions.failed",
                    failed > 0,
                    "warning",
                    f"{failed} failed mission(s)",
                    {"failed_missions_count": failed, "active_missions_count": active},
                ),
                check(
                    22,
                    "missions.context_critical",
                    critical_context > 0,
                    "warning",
                    f"{critical_context} mission(s) with critical context",
                    {"missions_with_critical_context": critical_context},
                ),
                check(
                    23,
                    "missions.supervision_attention",
                    warning > 0 or critical > 0,
                    "warning",
                    f"{warning} warning mission(s), {critical} critical mission(s)",
                    {"missions_warning_count": warning, "missions_critical_count": critical},
                ),
            ),
            metrics={"active_missions": active},
        )
