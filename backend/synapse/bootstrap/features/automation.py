from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.daemon.identity import RunnerIdentityStore
from synapse.daemon.runner import DaemonRunner
from synapse.daemon.status import DaemonStatusStore
from synapse.decisions.runtime import DecisionRuntime
from synapse.scheduler.lock import SchedulerLock
from synapse.scheduler.queue import JobQueue
from synapse.scheduler.runtime import SchedulerRuntime
from synapse.tools.permission_bridge import ToolPermissionBridge


@dataclass(frozen=True)
class AutomationFeatureDependencies:
    data_dir: Any
    events: Any
    permissions: Any
    platform: Any
    agents: Any
    missions: Any


@dataclass(frozen=True)
class AutomationFeature:
    runner_identity: RunnerIdentityStore
    scheduler_lock: SchedulerLock
    scheduler: SchedulerRuntime
    daemon: DaemonRunner
    decisions: DecisionRuntime
    tool_permission_bridge: ToolPermissionBridge


class AutomationFeatureBuilder:
    metadata = FeatureMetadata("automation")

    def build(self, d: AutomationFeatureDependencies) -> BuiltFeature[AutomationFeature]:
        p, a, m = d.platform, d.agents, d.missions
        job_queue = JobQueue(d.data_dir)
        runner_identity = RunnerIdentityStore(d.data_dir, d.events)
        runner = runner_identity.load()
        scheduler_lock = SchedulerLock.from_policy(d.data_dir, d.events, owner_id=runner.runner_id)
        scheduler = SchedulerRuntime(
            job_queue,
            a.worker,
            d.events,
            p.presence,
            p.lifecycle,
            p.notifications,
            scheduler_lock,
            a.admin,
            a.retention,
            a.delegation_inbox,
            a.delegation_timeout,
            a.dead_letter,
        )
        scheduler.missions = m.missions
        daemon = DaemonRunner(
            scheduler,
            DaemonStatusStore(d.data_dir),
            d.events,
            runner_identity,
            missions=m.missions,
            mission_recovery=m.mission_recovery,
        )
        m.mission_control.scheduler = scheduler
        m.mission_control.daemon = daemon
        decisions = DecisionRuntime(
            d.events,
            d.permissions,
            p.policies,
            p.capabilities,
            a.provisioning_policy,
            a.admin_policy,
            p.tools,
            a.delegation_autonomy,
            a.delegation,
            p.identities,
        )
        permission_bridge = ToolPermissionBridge(
            d.permissions, p.approvals, decisions, p.policies, p.capabilities, d.events
        )
        value = AutomationFeature(
            runner_identity, scheduler_lock, scheduler, daemon, decisions, permission_bridge
        )
        return BuiltFeature(
            value,
            self.metadata,
            health_contributors=(scheduler, daemon),
            ports={"scheduler": scheduler, "daemon": daemon, "decisions": decisions},
        )
