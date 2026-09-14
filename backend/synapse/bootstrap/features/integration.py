from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.agent_tool_calling.runtime import AgentToolCallingRuntime
from synapse.bootstrap.adapters.agent_memory_tools import register_agent_memory_tools
from synapse.bootstrap.adapters.context_fusion import (
    ConversationContextAdapter,
    MemoryContextAdapter,
    MissionContextAdapter,
    MultimodalContextAdapter,
    PerceptionContextAdapter,
    RuntimeStatusContextAdapter,
)
from synapse.bootstrap.adapters.provider_taxonomy import register_runtime_provider_projections
from synapse.bootstrap.adapters.tool_execution import register_desktop_tool_adapters
from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.context_fusion.contracts import ContextFusionSettings
from synapse.context_fusion.runtime import ContextFusionRuntime
from synapse.execution_router.runtime import ExecutionRouterRuntime
from synapse.health.contributors import (
    AgentsHealthContributor,
    DelegationHealthContributor,
    IntegrationHealthContributor,
    MissionsHealthContributor,
    ModelsHealthContributor,
    PerceptionHealthContributor,
    PlatformHealthContributor,
    ToolsHealthContributor,
    VoiceHealthContributor,
)
from synapse.health.registry import HealthContributorRegistry
from synapse.health.runtime import HealthRuntime
from synapse.mcp.runtime import MCPRuntime
from synapse.mcp_bridge.runtime import MCPToolBridgeRuntime
from synapse.readiness.runtime import ReadinessRuntime
from synapse.tool_discovery.runtime import ToolDiscoveryRuntime
from synapse.tool_intents.runtime import ToolIntentRuntime
from synapse.tools.runtime import ToolRuntime, register_seed_runtime_tools
from synapse.workers.execution_adapter import WorkerExecutionAdapter


@dataclass(frozen=True)
class IntegrationFeatureDependencies:
    data_dir: Any
    events: Any
    default_actor_id: str
    platform: Any
    models: Any
    interaction: Any
    agents: Any
    missions: Any
    automation: Any


@dataclass(frozen=True)
class IntegrationFeature:
    health: HealthRuntime
    readiness: ReadinessRuntime
    tool_runtime: ToolRuntime
    tool_discovery: ToolDiscoveryRuntime
    tool_intents: ToolIntentRuntime
    mcp: MCPRuntime
    mcp_bridge: MCPToolBridgeRuntime
    execution_router: ExecutionRouterRuntime
    agent_tool_calling: AgentToolCallingRuntime
    context_fusion: ContextFusionRuntime
    worker_execution_adapter: WorkerExecutionAdapter


class IntegrationFeatureBuilder:
    metadata = FeatureMetadata("execution-and-observability")

    def build(self, d: IntegrationFeatureDependencies) -> BuiltFeature[IntegrationFeature]:
        p, mo, i, a, m, au = (
            d.platform,
            d.models,
            d.interaction,
            d.agents,
            d.missions,
            d.automation,
        )
        register_runtime_provider_projections(
            mo.provider_catalog, platform=p, models=mo, interaction=i, agents=a
        )
        health_registry = HealthContributorRegistry()
        health_registry.register_all(
            (
                PlatformHealthContributor(
                    au.runner_identity,
                    au.daemon,
                    au.scheduler,
                    p.notifications,
                    p.approvals,
                    a.retention,
                    p.migrations,
                    au.decisions,
                    p.capabilities,
                    d.events,
                ),
                AgentsHealthContributor(
                    p.agents, p.presence, a.provisioning, a.admin, mo.model_hub
                ),
                DelegationHealthContributor(
                    a.delegation_inbox,
                    a.delegation_execution,
                    a.delegation_timeout,
                    a.dead_letter,
                    a.delegation_recovery,
                ),
                MissionsHealthContributor(m.missions, m.mission_context, m.mission_supervision),
                ModelsHealthContributor(
                    mo.providers,
                    mo.provider_plugins,
                    mo.lmstudio,
                    mo.model_hub,
                    mo.provider_settings,
                    mo.system_insight,
                ),
                VoiceHealthContributor(
                    i.voice,
                    mo.speech_adapters,
                    i.speech_pipeline,
                    i.multimodal,
                    i.audio,
                ),
                PerceptionHealthContributor(i.perception, i.vision),
            )
        )
        health = HealthRuntime(health_registry, d.events)
        readiness = ReadinessRuntime(d.data_dir, health)
        mo.system_insight.health_runtime = health
        mo.system_insight.readiness_runtime = readiness
        tool_runtime = ToolRuntime(
            d.data_dir, d.events, registry=p.tools, permission_bridge=au.tool_permission_bridge
        )
        a.tool_router.bind(tool_runtime)
        register_agent_memory_tools(tool_runtime, p.memory)
        register_seed_runtime_tools(
            tool_runtime,
            health=health,
            readiness=readiness,
            conversations=a.conversations,
            missions=m.missions,
            admin=a.admin,
            providers=mo.providers,
            voice=i.voice,
        )
        register_desktop_tool_adapters(
            tool_runtime, lambda: m.missions.desktop_runtime or a.desktop
        )
        m.missions.tool_runtime = tool_runtime
        tool_discovery = ToolDiscoveryRuntime(tool_runtime, d.default_actor_id)
        tool_intents = ToolIntentRuntime(d.data_dir, d.events, tool_runtime, d.default_actor_id)
        mcp = MCPRuntime(d.data_dir, d.events)
        mcp_bridge = MCPToolBridgeRuntime(mcp, tool_runtime)
        mcp_bridge.sync_from_mcp_registry()
        execution_router = ExecutionRouterRuntime(
            tool_runtime, tool_intents, mcp_bridge, mo.providers, mo.provider_plugins
        )
        tool_intents.execution_router = execution_router
        agent_tool_calling = AgentToolCallingRuntime(
            d.data_dir, tool_intents, tool_discovery, execution_router
        )
        a.agent_runtime.agent_tool_calling = agent_tool_calling
        a.agent_runtime.tool_discovery = tool_discovery
        health_registry.register(
            ToolsHealthContributor(
                p.approvals,
                tool_runtime,
                tool_intents,
                mcp,
                mcp_bridge,
                execution_router,
            )
        )
        health.tool_discovery_runtime_available = True
        m.mission_supervision.health = health
        m.mission_supervision.readiness = readiness
        conversation_context = ConversationContextAdapter(a.conversations)
        mission_context = MissionContextAdapter(m.missions, m.mission_context, a.delegation)
        perception_context = PerceptionContextAdapter(i.perception)
        multimodal_context = MultimodalContextAdapter(i.multimodal)
        memory_context = MemoryContextAdapter(p.memory)
        runtime_status_context = RuntimeStatusContextAdapter(health, readiness)
        context_fusion = ContextFusionRuntime(
            ContextFusionSettings(snapshot_root=d.data_dir.resolve("context_fusion/snapshots")),
            d.events,
            conversation_context,
            mission_context,
            perception_context,
            multimodal_context,
            runtime_status_context,
            memory_context,
        )
        integration_health = IntegrationHealthContributor(context_fusion)
        integration_health.agent_multimodal_bridge_available = True
        health_registry.register(integration_health)
        a.worker.context_fusion = context_fusion
        m.worker_execution.context_fusion = context_fusion
        adapter = WorkerExecutionAdapter(a.context_loader, a.agent_runtime, context_fusion)
        m.worker_execution.executor = adapter.execute
        value = IntegrationFeature(
            health,
            readiness,
            tool_runtime,
            tool_discovery,
            tool_intents,
            mcp,
            mcp_bridge,
            execution_router,
            agent_tool_calling,
            context_fusion,
            adapter,
        )
        return BuiltFeature(
            value,
            self.metadata,
            health_contributors=(health, readiness),
            ports={"health": health, "readiness": readiness, "tools": tool_runtime},
        )
