from __future__ import annotations

from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks, component


class SkillHealthContributor:
    contributor_id = "skills"

    def __init__(self, skills: Any) -> None:
        self.skills = skills

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        status = self.skills.status()
        invalid = int(status["invalid_packages"])
        return HealthContribution(
            components=(
                component(95, "skills", self.skills, ["storage", "tools"], details=status),
            ),
            checks=checks(
                check(
                    950,
                    "skills.invalid_packages",
                    invalid > 0,
                    "warning",
                    f"{invalid} invalid skill package(s).",
                )
            ),
            metrics={
                "skills_packages": int(status["packages"]),
                "skills_assignments": int(status["assignments"]),
                "skills_leases": int(status["leases"]),
                "skills_invalid_packages": invalid,
            },
        )
