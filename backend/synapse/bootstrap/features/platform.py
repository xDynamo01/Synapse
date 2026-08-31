from __future__ import annotations

from dataclasses import dataclass

from synapse.agents.communication import AgentCommunication
from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.registry import AgentRegistry
from synapse.approvals.manager import ApprovalManager
from synapse.auth.devices import DeviceRegistry
from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.capabilities.registry import CapabilityRegistry, builtin_capability_registry
from synapse.capabilities.runtime import CapabilityRuntime
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionManager
from synapse.lifecycle.runtime import LifecycleRuntime
from synapse.memory.store import MemoryStore
from synapse.migrations.registry import MigrationRegistry
from synapse.migrations.runtime import MigrationRuntime
from synapse.notifications.local_provider import LocalNotificationProvider
from synapse.notifications.runtime import NotificationRuntime
from synapse.policies.effective import EffectivePolicyRuntime
from synapse.presence.runtime import PresenceRuntime
from synapse.tasks.runtime import TaskRuntime
from synapse.tools.builtin import register_builtin_runtime_tools
from synapse.tools.registry import RuntimeToolRegistry


@dataclass(frozen=True)
class PlatformFeatureDependencies:
    data_dir: DataDir
    events: EventBus
    permissions: PermissionManager


@dataclass(frozen=True)
class PlatformFeature:
    agents: AgentRegistry
    identities: AgentIdentityRuntime
    communication: AgentCommunication
    presence: PresenceRuntime
    lifecycle: LifecycleRuntime
    notifications: NotificationRuntime
    migrations: MigrationRuntime
    devices: DeviceRegistry
    approvals: ApprovalManager
    memory: MemoryStore
    tasks: TaskRuntime
    tools: RuntimeToolRegistry
    capability_registry: CapabilityRegistry
    policies: EffectivePolicyRuntime
    capabilities: CapabilityRuntime


class PlatformFeatureBuilder:
    metadata = FeatureMetadata("platform")

    def build(self, dependencies: PlatformFeatureDependencies) -> BuiltFeature[PlatformFeature]:
        data_dir = dependencies.data_dir
        events = dependencies.events
        permissions = dependencies.permissions
        agents = AgentRegistry(data_dir)
        identities = AgentIdentityRuntime(data_dir)
        communication = AgentCommunication(data_dir, agents, permissions, events)
        presence = PresenceRuntime(data_dir, events)
        lifecycle = LifecycleRuntime(data_dir, events, presence)
        notifications = NotificationRuntime(
            data_dir, events, LocalNotificationProvider(data_dir), permissions=permissions
        )
        migration_registry = MigrationRegistry()
        for record_type in ("job", "notification", "approval"):
            migration_registry.register_record_type(record_type, 1)
        migrations = MigrationRuntime(data_dir, migration_registry)
        devices = DeviceRegistry(data_dir, events)
        approvals = ApprovalManager(data_dir, permissions, devices, events)
        memory = MemoryStore(data_dir, permissions, events)
        tasks = TaskRuntime(data_dir, permissions, events)
        tools = RuntimeToolRegistry()
        capability_registry = builtin_capability_registry()
        policies = EffectivePolicyRuntime(
            agents, identities, tools, permissions, approvals, devices, capability_registry
        )
        capabilities = CapabilityRuntime(capability_registry, policies, events, data_dir)
        register_builtin_runtime_tools(tools, data_dir, communication, tasks)
        value = PlatformFeature(
            agents,
            identities,
            communication,
            presence,
            lifecycle,
            notifications,
            migrations,
            devices,
            approvals,
            memory,
            tasks,
            tools,
            capability_registry,
            policies,
            capabilities,
        )
        return BuiltFeature(
            value,
            self.metadata,
            health_contributors=(notifications, migrations, presence),
            ports={"agents": agents, "policies": policies, "capabilities": capabilities},
        )
