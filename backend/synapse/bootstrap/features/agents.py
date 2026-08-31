from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.admin_policy.runtime import AdminPolicyRuntime
from synapse.agents.admin import AgentAdminRuntime
from synapse.agents.audit import AgentAuditRuntime
from synapse.agents.provisioning import AgentProvisioningRuntime
from synapse.agents.provisioning_policy import AgentProvisioningPolicyRuntime
from synapse.agents.runtime import AgentRuntime
from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.context.loader import ContextLoader
from synapse.conversations.runtime import ConversationRuntime
from synapse.dead_letter.runtime import DeadLetterRuntime
from synapse.delegation.autonomy_policy import DelegationAutonomyPolicyRuntime
from synapse.delegation.retry_policy import DelegationRetryPolicyRuntime
from synapse.delegation.runtime import DelegationRuntime
from synapse.delegation.scheduling_policy import DelegationSchedulingPolicyRuntime
from synapse.delegation.timeout_policy import DelegationTimeoutPolicyRuntime
from synapse.delegation_execution.runtime import DelegationExecutionRuntime
from synapse.delegation_inbox.runtime import DelegationInboxRuntime
from synapse.delegation_recovery.runtime import DelegationRecoveryRuntime
from synapse.desktop_automation.runtime import DesktopRuntime
from synapse.maintenance import (
    ConfigurationInspectionContributor,
    DataMaintenanceRuntime,
    FoundationInspectionContributor,
    MaintenanceContributorRegistry,
    RetentionMaintenanceContributor,
    TemporaryFilesMaintenanceContributor,
)
from synapse.primary_agent.runtime import PrimaryAgentRuntime
from synapse.retention.registry import RetentionRegistry
from synapse.retention.runtime import RetentionRuntime
from synapse.tools.router import ToolRouter
from synapse.workers.agent_worker import AgentWorker


@dataclass(frozen=True)
class AgentFeatureDependencies:
    data_dir: Any
    events: Any
    permissions: Any
    platform: Any
    models: Any
    interaction: Any
    system_insight: Any


@dataclass(frozen=True)
class AgentFeature:
    provisioning_policy: AgentProvisioningPolicyRuntime
    admin_policy: AdminPolicyRuntime
    delegation_autonomy: DelegationAutonomyPolicyRuntime
    audit: AgentAuditRuntime
    desktop: DesktopRuntime
    admin: AgentAdminRuntime
    conversations: ConversationRuntime
    delegation: DelegationRuntime
    delegation_inbox: DelegationInboxRuntime
    delegation_scheduling: DelegationSchedulingPolicyRuntime
    delegation_execution: DelegationExecutionRuntime
    delegation_retry: DelegationRetryPolicyRuntime
    delegation_timeout: DelegationTimeoutPolicyRuntime
    dead_letter: DeadLetterRuntime
    delegation_recovery: DelegationRecoveryRuntime
    retention: RetentionRuntime
    maintenance: DataMaintenanceRuntime
    provisioning: AgentProvisioningRuntime
    context_loader: ContextLoader
    tool_router: ToolRouter
    agent_runtime: AgentRuntime
    worker: AgentWorker
    primary_agent: PrimaryAgentRuntime


class AgentFeatureBuilder:
    metadata = FeatureMetadata("agents-and-delegation")

    def build(self, d: AgentFeatureDependencies) -> BuiltFeature[AgentFeature]:
        p = d.platform
        i = d.interaction
        provisioning_policy = AgentProvisioningPolicyRuntime(d.data_dir, p.capability_registry)
        admin_policy = AdminPolicyRuntime(d.data_dir, d.permissions, d.events)
        delegation_autonomy = DelegationAutonomyPolicyRuntime(d.data_dir, d.events)
        audit = AgentAuditRuntime(d.data_dir)
        desktop = DesktopRuntime(
            d.data_dir,
            d.events,
            p.policies,
            p.approvals,
            audit,
            i.vision,
            perception=i.perception,
            insight=d.system_insight,
        )
        admin = AgentAdminRuntime(
            d.data_dir,
            p.agents,
            p.identities,
            p.capability_registry,
            d.events,
            p.presence,
            p.lifecycle,
            audit,
            admin_policy,
            p.approvals,
        )
        conversations = ConversationRuntime(d.data_dir, p.agents, d.permissions, d.events, admin)
        primary_agent = PrimaryAgentRuntime(
            d.data_dir,
            d.events,
            p.agents,
            conversations,
            approvals=p.approvals,
            notifications=p.notifications,
            voice=i.voice,
        )
        admin.primary_agent = primary_agent
        p.communication.conversations = conversations
        p.communication.admin = admin
        delegation = DelegationRuntime(
            d.data_dir,
            p.agents,
            p.capabilities,
            d.events,
            admin,
            audit,
            p.communication,
            conversations,
        )
        delegation_inbox = DelegationInboxRuntime(d.data_dir, d.events)
        delegation_scheduling = DelegationSchedulingPolicyRuntime(d.data_dir, d.events)
        delegation_execution = DelegationExecutionRuntime(d.data_dir, d.events, delegation)
        delegation_retry = DelegationRetryPolicyRuntime(d.data_dir, d.events)
        delegation_timeout = DelegationTimeoutPolicyRuntime(
            d.data_dir, d.events, delegation, delegation_execution
        )
        dead_letter = DeadLetterRuntime(
            d.data_dir, d.events, delegation, delegation_execution, delegation_inbox
        )
        delegation_inbox.dead_letter = dead_letter
        delegation.inbox = delegation_inbox
        delegation.executions = delegation_execution
        delegation.retry_policy = delegation_retry
        delegation_recovery = DelegationRecoveryRuntime(
            d.events,
            delegation,
            delegation_execution,
            delegation_retry,
            delegation_timeout,
            dead_letter,
        )
        registry = RetentionRegistry()
        registry.register(
            domain_id="notifications",
            description="Local notification records.",
            policy_path=str(d.data_dir.resolve("config/notification_policy.yaml")),
            supports_dry_run=True,
            default_dry_run=True,
            cleanup=lambda dry_run: _notification_cleanup(p.notifications, dry_run),
            status=lambda: {"total": len(p.notifications.list_notifications()), "enabled": True},
        )
        registry.register(
            domain_id="agent_admin_requests",
            description="Agent administrative action approval/apply requests.",
            policy_path=str(d.data_dir.resolve("config/agent_admin_retention_policy.yaml")),
            supports_dry_run=True,
            default_dry_run=True,
            cleanup=admin.cleanup_admin_action_requests,
            status=admin.admin_action_request_retention_status,
        )
        retention = RetentionRuntime(registry, d.events)
        maintenance_registry = MaintenanceContributorRegistry()
        maintenance_registry.register(FoundationInspectionContributor(d.data_dir))
        maintenance_registry.register(ConfigurationInspectionContributor(d.data_dir))
        maintenance_registry.register(TemporaryFilesMaintenanceContributor(d.data_dir))
        maintenance_registry.register(RetentionMaintenanceContributor(retention))
        maintenance = DataMaintenanceRuntime(
            d.data_dir,
            d.events,
            d.permissions,
            p.policies,
            p.approvals,
            maintenance_registry,
        )
        provisioning = AgentProvisioningRuntime(
            d.data_dir,
            p.capability_registry,
            d.events,
            p.approvals,
            provisioning_policy,
            admin,
            audit,
        )
        context_loader = ContextLoader(
            d.data_dir,
            d.permissions,
            d.events,
            p.agents,
            p.identities,
            p.policies,
            p.tasks,
        )
        tool_router = ToolRouter(
            p.tools, d.permissions, p.approvals, d.events, p.presence, p.capabilities
        )
        agent_runtime = AgentRuntime(
            p.agents, p.policies, d.models, tool_router, d.events, p.presence
        )
        worker = AgentWorker(
            p.communication,
            context_loader,
            agent_runtime,
            p.policies,
            d.events,
            p.presence,
            p.lifecycle,
            admin,
            delegation,
            delegation_inbox,
            delegation_scheduling,
            delegation_autonomy,
            delegation_execution,
            p.identities,
        )
        value = AgentFeature(
            provisioning_policy,
            admin_policy,
            delegation_autonomy,
            audit,
            desktop,
            admin,
            conversations,
            delegation,
            delegation_inbox,
            delegation_scheduling,
            delegation_execution,
            delegation_retry,
            delegation_timeout,
            dead_letter,
            delegation_recovery,
            retention,
            maintenance,
            provisioning,
            context_loader,
            tool_router,
            agent_runtime,
            worker,
            primary_agent,
        )
        return BuiltFeature(
            value,
            self.metadata,
            health_contributors=(
                provisioning,
                admin,
                retention,
                delegation,
                primary_agent,
            ),
            ports={
                "agent_runtime": agent_runtime,
                "worker": worker,
                "conversations": conversations,
            },
        )


def _notification_cleanup(notifications: Any, dry_run: bool) -> Any:
    if not dry_run:
        return notifications.cleanup_notifications()
    current = notifications.list_notifications()
    return {
        "dry_run": True,
        "scanned": len(current),
        "deleted": 0,
        "preserved": len(current),
        "candidates": [],
        "errors": [],
        "remaining": len(current),
    }
