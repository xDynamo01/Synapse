from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks, component


class PlatformHealthContributor:
    contributor_id = "platform"

    def __init__(
        self,
        runner_identity: Any,
        daemon: Any,
        scheduler: Any,
        notifications: Any,
        approvals: Any,
        retention: Any,
        migrations: Any,
        decisions: Any,
        capabilities: Any,
        event_bus: Any,
    ) -> None:
        self.runner_identity = runner_identity
        self.daemon = daemon
        self.scheduler = scheduler
        self.notifications = notifications
        self.approvals = approvals
        self.retention = retention
        self.migrations = migrations
        self.decisions = decisions
        self.capabilities = capabilities
        self.event_bus = event_bus

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        recurring = self.scheduler.load_recurring_jobs()
        unread_critical = [
            item for item in self.notifications.list_unread() if item.severity == "critical"
        ]
        pending_jobs = len(self.scheduler.list_jobs(status="pending"))
        failed_jobs = len(self.scheduler.list_jobs(status="failed"))
        approvals_pending = len(self.approvals.list_pending())
        retention = (
            {"available": True, **asdict(self.retention.retention_status())}
            if self.retention
            else {"available": False}
        )
        migrations = (
            {"available": True, **asdict(self.migrations.migration_status())}
            if self.migrations
            else {"available": False}
        )
        capability_count = len(self.capabilities.list_capabilities()) if self.capabilities else 0
        daemon = asdict(self.daemon.status())
        scheduler_lock = self.scheduler.lock_status()
        summary = {
            "runner": asdict(self.runner_identity.load()),
            "daemon": daemon,
            "scheduler_lock": scheduler_lock,
            "pending_jobs": pending_jobs,
            "failed_jobs": failed_jobs,
            "recurring_jobs_due": sum(item.is_due() for item in recurring),
            "unread_critical_notifications": len(unread_critical),
            "approvals_pending": approvals_pending,
            "retention": retention,
            "migrations": migrations,
            "decision_runtime_available": self.decisions is not None,
            "capability_count": capability_count,
        }
        return HealthContribution(
            components=(
                component(13, "policy", self.decisions, []),
                component(14, "observability", self.event_bus, []),
                component(18, "notification_sink", self.notifications, ["attention"]),
            ),
            summary=summary,
            checks=checks(
                check(0, "jobs.failed", failed_jobs > 0, "warning", f"{failed_jobs} failed job(s)"),
                check(
                    1,
                    "notifications.critical_unread",
                    bool(unread_critical),
                    "critical",
                    f"{len(unread_critical)} unread critical notification(s)",
                ),
                check(
                    2,
                    "approvals.pending",
                    approvals_pending > 0,
                    "warning",
                    f"{approvals_pending} pending approval(s)",
                ),
                check(
                    7,
                    "daemon.stopped",
                    not bool(daemon.get("running", False)),
                    "warning",
                    "daemon is not running",
                ),
                check(
                    8,
                    "scheduler.lock_stale",
                    bool(scheduler_lock.get("stale", False)),
                    "warning",
                    "scheduler lock is stale",
                    scheduler_lock,
                ),
                check(
                    9,
                    "migrations.unavailable",
                    not migrations.get("available", False),
                    "warning",
                    "migration runtime unavailable",
                ),
                check(
                    10,
                    "retention.unavailable",
                    not retention.get("available", False),
                    "warning",
                    "retention runtime unavailable",
                ),
                check(
                    11,
                    "capabilities.empty",
                    capability_count == 0,
                    "warning",
                    "no capabilities registered",
                ),
            ),
            metrics={
                "scheduler_queue_depth": pending_jobs,
                "failed_jobs": failed_jobs,
                "pending_approvals": approvals_pending,
            },
        )
