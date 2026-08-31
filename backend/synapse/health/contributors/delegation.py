from __future__ import annotations

from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks


class DelegationHealthContributor:
    contributor_id = "delegation"

    def __init__(
        self, inbox: Any, execution: Any, timeout: Any, dead_letter: Any, recovery: Any
    ) -> None:
        self.delegation_inbox = inbox
        self.delegation_execution = execution
        self.delegation_timeout = timeout
        self.dead_letter = dead_letter
        self.delegation_recovery = recovery

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        inbox = self.delegation_inbox.status() if self.delegation_inbox else {"available": False}
        execution = (
            self.delegation_execution.status()
            if self.delegation_execution
            else {"available": False}
        )
        timeout = (
            self.delegation_timeout.status() if self.delegation_timeout else {"available": False}
        )
        open_count = len(self.dead_letter.list_open_entries()) if self.dead_letter else 0
        try:
            recovery_count = (
                self.delegation_recovery.recovery_candidates_count()
                if self.delegation_recovery
                else 0
            )
        except Exception:
            recovery_count = 0
        return HealthContribution(
            summary={
                "delegation_inbox": inbox,
                "delegation_execution": execution,
                "delegation_timeout": timeout,
                "dead_letter_open_count": open_count,
                "recovery_candidates_count": recovery_count,
            },
            checks=checks(
                check(
                    13,
                    "delegation_inbox.unavailable",
                    not inbox.get("available", False),
                    "warning",
                    "delegation inbox runtime unavailable",
                ),
                check(
                    14,
                    "delegation_inbox.corrupted",
                    bool(inbox.get("corrupted_agents")),
                    "warning",
                    "delegation inbox corruption detected",
                    inbox,
                ),
                check(
                    15,
                    "delegation_inbox.rebuild_failed",
                    int(inbox.get("rebuild_failures", 0)) > 0,
                    "warning",
                    "delegation inbox rebuild failure(s) detected",
                    inbox,
                ),
                check(
                    16,
                    "delegation_execution.unavailable",
                    not execution.get("available", False),
                    "warning",
                    "delegation execution runtime unavailable",
                ),
                check(
                    17,
                    "delegation_execution.failed_recent",
                    int(execution.get("failed_recent", 0)) > 0,
                    "warning",
                    "recent failed delegation execution(s)",
                    execution,
                ),
                check(
                    18,
                    "delegation_timeout.candidates",
                    int(timeout.get("timeout_candidates", 0)) > 0,
                    "warning",
                    "delegation timeout candidate(s) detected",
                    timeout,
                ),
                check(
                    19,
                    "dead_letter.open",
                    open_count > 0,
                    "warning",
                    f"{open_count} open dead letter entries",
                    {"open_count": open_count},
                ),
                check(
                    20,
                    "recovery.candidates",
                    recovery_count > 0,
                    "warning",
                    f"{recovery_count} delegation recovery candidate(s)",
                    {"candidate_count": recovery_count},
                ),
            ),
            metrics={"dlq_open_entries": open_count},
        )
