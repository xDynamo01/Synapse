"""Canonical application composition coordinating bounded feature builders."""

from __future__ import annotations

import os
from dataclasses import dataclass

from synapse.approvals.resume import ApprovalResumeRuntime
from synapse.bootstrap.adapters.global_runtimes import bind_health, bind_lifecycle, build_all
from synapse.bootstrap.adapters.mom import (
    MoMConfigurations,
    PrimaryBinding,
    PrimaryChatRouting,
    PrimaryInference,
)
from synapse.bootstrap.adapters.operational_projection import OperationalProjectionRuntime
from synapse.bootstrap.adapters.search import configure_search_runtime
from synapse.bootstrap.bindings import canonical_global_binding_inventory
from synapse.bootstrap.container import RuntimeContainer
from synapse.bootstrap.features.agents import AgentFeatureBuilder, AgentFeatureDependencies
from synapse.bootstrap.features.automation import (
    AutomationFeatureBuilder,
    AutomationFeatureDependencies,
)
from synapse.bootstrap.features.foundation import FoundationFeatureBuilder
from synapse.bootstrap.features.integration import (
    IntegrationFeatureBuilder,
    IntegrationFeatureDependencies,
)
from synapse.bootstrap.features.intelligence_boundary import (
    IntelligenceBoundaryFeatureBuilder,
    IntelligenceBoundaryFeatureDependencies,
)
from synapse.bootstrap.features.interaction import (
    InteractionFeatureBuilder,
    InteractionFeatureDependencies,
)
from synapse.bootstrap.features.missions import MissionFeatureBuilder, MissionFeatureDependencies
from synapse.bootstrap.features.models import ModelFeatureBuilder, ModelFeatureDependencies
from synapse.bootstrap.features.platform import PlatformFeatureBuilder, PlatformFeatureDependencies
from synapse.bootstrap.features.project_governance import (
    ProjectGovernanceFeatureBuilder,
    ProjectGovernanceFeatureDependencies,
)
from synapse.bootstrap.features.skills import SkillsFeatureBuilder, SkillsFeatureDependencies
from synapse.bootstrap.features.world import WorldFeatureBuilder, WorldFeatureDependencies
from synapse.bootstrap.lifecycle import LifecycleManager, LifecycleReport
from synapse.chat.runtime import ChatRuntime
from synapse.commands.handlers import build_command_handlers
from synapse.commands.registry import CommandRegistry
from synapse.commands.runtime import CommandRuntime
from synapse.commands.services import CommandServices
from synapse.core.config import Settings
from synapse.mom.runtime import MoMRuntime
from synapse.project_knowledge.embedding_providers import learned_embedding_provider_from_env
from synapse.project_knowledge.runtime import ProjectKnowledgeRuntime
from synapse.voice.perception import VoicePerceptionSink


@dataclass
class Application:
    """Owns one runtime graph and its explicit process lifecycle."""

    container: RuntimeContainer
    lifecycle: LifecycleManager
    metadata: dict[str, object]
    startup_report: LifecycleReport | None = None
    shutdown_report: LifecycleReport | None = None

    def start(self) -> LifecycleReport:
        self.startup_report = self.lifecycle.start()
        return self.startup_report

    def close(self) -> LifecycleReport:
        self.shutdown_report = self.lifecycle.close()
        return self.shutdown_report


def build_application(settings: Settings | None = None) -> Application:
    """Construct an application without activating lifecycle resources."""
    container = create_runtime(settings)
    return Application(container, container.application_lifecycle, dict(container.bootstrap_metadata))


def _project_knowledge_semantic_enabled() -> bool:
    value = os.environ.get("SYNAPSE_PROJECT_KNOWLEDGE_LEARNED_EMBEDDINGS", "").casefold()
    return value in {"1", "true", "yes", "on"}


def create_runtime(
    settings: Settings | None = None,
    *,
    voice_perception_sink: VoicePerceptionSink | None = None,
) -> RuntimeContainer:
    settings = settings or Settings.from_env()
    foundation_built = FoundationFeatureBuilder().build(settings)
    foundation = foundation_built.value
    operational_projection = OperationalProjectionRuntime(foundation.events)
    global_runtimes = build_all(foundation.data_dir, settings.project_root)
    deployment, private_evals, coding_sessions, skills_phase2, sandbox, repository_runtime = (
        global_runtimes
    )
    models_built = ModelFeatureBuilder().build(
        ModelFeatureDependencies(foundation.data_dir, foundation.config, foundation.events)
    )
    models = models_built.value
    platform_built = PlatformFeatureBuilder().build(
        PlatformFeatureDependencies(foundation.data_dir, foundation.events, foundation.permissions)
    )
    platform = platform_built.value
    interaction_built = InteractionFeatureBuilder().build(
        InteractionFeatureDependencies(
            foundation.data_dir,
            foundation.events,
            platform.agents,
            models.providers,
            models.speech_adapters,
            settings.default_actor_id,
            voice_perception_sink,
        )
    )
    interaction = interaction_built.value
    agents_built = AgentFeatureBuilder().build(
        AgentFeatureDependencies(
            foundation.data_dir,
            foundation.events,
            foundation.permissions,
            platform,
            models.models,
            interaction,
            models.system_insight,
        )
    )
    agents = agents_built.value
    missions_built = MissionFeatureBuilder().build(
        MissionFeatureDependencies(
            foundation.data_dir, foundation.events, platform, agents, models.system_insight
        )
    )
    missions = missions_built.value
    automation_built = AutomationFeatureBuilder().build(
        AutomationFeatureDependencies(
            foundation.data_dir,
            foundation.events,
            foundation.permissions,
            platform,
            agents,
            missions,
        )
    )
    automation = automation_built.value
    integration_built = IntegrationFeatureBuilder().build(
        IntegrationFeatureDependencies(
            foundation.data_dir,
            foundation.events,
            settings.default_actor_id,
            platform,
            models,
            interaction,
            agents,
            missions,
            automation,
        )
    )
    integration = integration_built.value
    skills_built = SkillsFeatureBuilder().build(
        SkillsFeatureDependencies(
            foundation.data_dir,
            foundation.events,
            integration.tool_runtime,
            integration.health,
        )
    )
    skills = skills_built.value
    governance_built = ProjectGovernanceFeatureBuilder().build(
        ProjectGovernanceFeatureDependencies(
            foundation.data_dir,
            foundation.events,
            integration.tool_runtime,
            integration.health,
        )
    )
    governance = governance_built.value
    intelligence_built = IntelligenceBoundaryFeatureBuilder().build(
        IntelligenceBoundaryFeatureDependencies(
            foundation.data_dir,
            foundation.events,
            integration.health,
        )
    )
    intelligence_boundary = intelligence_built.value
    models.models.egress_gate = intelligence_boundary
    integration.tool_runtime.egress_gate = intelligence_boundary
    search = configure_search_runtime(
        data_dir=foundation.data_dir,
        tools=platform.tools,
        egress_gate=intelligence_boundary,
    )
    project_knowledge = ProjectKnowledgeRuntime(
        foundation.data_dir,
        foundation.events,
        platform.memory,
        semantic_enabled=_project_knowledge_semantic_enabled(),
        learned_embedding_provider=learned_embedding_provider_from_env(
            data_dir=foundation.data_dir,
        ),
    )
    agents.context_loader.skill_context = skills
    agents.context_loader.project_context = governance
    agents.primary_agent.skill_context = skills
    agents.primary_agent.project_context = governance
    missions.ephemeral_agents.skill_leases = skills
    missions.workforce_planner.skill_resolution = skills
    skills.project_context = governance
    missions.missions.implementation_binding = governance

    approval_resume = ApprovalResumeRuntime(
        platform.approvals, agents.tool_router, platform.policies
    )
    commands = _build_commands(
        foundation,
        platform,
        models,
        interaction,
        agents,
        missions,
        automation,
        integration,
        skills,
        governance,
        intelligence_boundary,
        approval_resume,
    )
    chat = ChatRuntime(
        foundation.data_dir,
        foundation.events,
        agents.context_loader,
        agents.agent_runtime,
        commands,
        platform.presence,
        agents.admin,
        agents.conversations,
        models.lmstudio,
        models.model_hub,
        platform.memory,
        integration.context_fusion,
        models.models,
    )
    interaction.voice.chat = chat
    mom = MoMRuntime(
        PrimaryBinding(agents.primary_agent, agents.admin), MoMConfigurations(foundation.data_dir),
        PrimaryInference(models.models, agents.context_loader, platform.memory),
        foundation.permissions, foundation.events,
    )
    commands.chat = chat
    chat.primary_model_routing = PrimaryChatRouting(mom)
    integration.health.chat = chat
    world_built = WorldFeatureBuilder().build(
        WorldFeatureDependencies(
            foundation.data_dir,
            foundation.events,
            settings.default_actor_id,
            platform,
            agents,
            missions,
            automation,
            integration,
            models.system_insight,
            chat,
        )
    )
    world = world_built.value
    agents.primary_agent.attention = world.attention
    agents.primary_agent.missions = missions.missions
    agents.primary_agent.health = integration.health
    agents.primary_agent.agent_loop = world.agent_loop
    commands.world_state = world.world_state
    commands.attention = world.attention
    commands.agent_loop = world.agent_loop
    commands.desktop = agents.desktop

    built_features = (
        foundation_built,
        models_built,
        platform_built,
        interaction_built,
        agents_built,
        missions_built,
        automation_built,
        integration_built,
        skills_built,
        governance_built,
        intelligence_built,
        world_built,
    )
    lifecycle = LifecycleManager()
    for built in built_features:
        for resource in built.lifecycle_resources:
            lifecycle.register(resource)
    bind_lifecycle(
        lifecycle, deployment, private_evals, coding_sessions, skills_phase2, sandbox,
        repository_runtime
    )
    bind_health(
        integration.health.registry, deployment, private_evals, coding_sessions,
        skills_phase2, sandbox, repository_runtime
    )
    metadata = {
        "composition_root": "synapse.bootstrap.application",
        "feature_builders": tuple(built.metadata.name for built in built_features),
        "auto_started_resources": tuple(resource.name for resource in lifecycle.resources),
        "health_contributors": 6
        + sum((len(built.health_contributors) for built in built_features), 0),
        "global_binding_inventory": canonical_global_binding_inventory(),
    }
    return RuntimeContainer(
        settings=settings,
        data_dir=foundation.data_dir,
        config=foundation.config,
        events=foundation.events,
        operational_projection=operational_projection,
        permissions=foundation.permissions,
        models=models.models,
        agents=platform.agents,
        identities=platform.identities,
        audit=agents.audit,
        admin_policy=agents.admin_policy,
        admin=agents.admin,
        provisioning=agents.provisioning,
        provisioning_policy=agents.provisioning_policy,
        agent_runtime=agents.agent_runtime,
        primary_agent=agents.primary_agent,
        communication=platform.communication,
        conversations=agents.conversations,
        dead_letter=agents.dead_letter,
        delegation=agents.delegation,
        delegation_execution=agents.delegation_execution,
        delegation_autonomy=agents.delegation_autonomy,
        delegation_retry=agents.delegation_retry,
        delegation_timeout=agents.delegation_timeout,
        delegation_scheduling=agents.delegation_scheduling,
        delegation_inbox=agents.delegation_inbox,
        delegation_recovery=agents.delegation_recovery,
        missions=missions.missions,
        planner=missions.planner,
        worker_registry=missions.worker_registry,
        worker_scheduler=missions.worker_scheduler,
        result_verifier=missions.result_verifier,
        attempts=missions.attempts,
        worker_execution=missions.worker_execution,
        worker_execution_adapter=integration.worker_execution_adapter,
        mission_recovery=missions.mission_recovery,
        mission_trace=missions.mission_trace,
        mission_dispatcher=missions.mission_dispatcher,
        swarm=missions.swarm,
        ephemeral_agents=missions.ephemeral_agents,
        workforce_planner=missions.workforce_planner,
        mission_context=missions.mission_context,
        mission_supervision=missions.mission_supervision,
        mission_control=missions.mission_control,
        presence=platform.presence,
        lifecycle=platform.lifecycle,
        notifications=platform.notifications,
        devices=platform.devices,
        approvals=platform.approvals,
        approval_resume=approval_resume,
        policies=platform.policies,
        memory=platform.memory,
        context_loader=agents.context_loader,
        tasks=platform.tasks,
        tools=agents.tool_router,
        tool_runtime=integration.tool_runtime,
        tool_discovery=integration.tool_discovery,
        tool_intents=integration.tool_intents,
        mcp=integration.mcp,
        mcp_bridge=integration.mcp_bridge,
        execution_router=integration.execution_router,
        agent_tool_calling=integration.agent_tool_calling,
        tool_router=agents.tool_router,
        worker=agents.worker,
        scheduler=automation.scheduler,
        daemon=automation.daemon,
        runner_identity=automation.runner_identity,
        health=integration.health,
        readiness=integration.readiness,
        migrations=platform.migrations,
        capabilities=platform.capabilities,
        decisions=automation.decisions,
        deployment=deployment,
        private_evals=private_evals,
        coding_sessions=coding_sessions,
        skills_phase2=skills_phase2,
        sandbox=sandbox,
        repository_runtime=repository_runtime,
        search=search,
        project_knowledge=project_knowledge,
        world_state=world.world_state,
        attention=world.attention,
        attention_decisions=world.attention_decisions,
        agent_loop=world.agent_loop,
        agent_event_stream=world.agent_event_stream,
        retention=agents.retention,
        maintenance=agents.maintenance,
        providers=models.providers,
        provider_settings=models.provider_settings,
        provider_catalog=models.provider_catalog,
        provider_plugins=models.provider_plugins,
        lmstudio=models.lmstudio,
        model_hub=models.model_hub,
        system_insight=models.system_insight,
        desktop=agents.desktop,
        voice=interaction.voice,
        multimodal=interaction.multimodal,
        audio=interaction.audio,
        vision=interaction.vision,
        capture=interaction.capture,
        perception=interaction.perception,
        context_fusion=integration.context_fusion,
        skills=skills,
        project_governance=governance,
        intelligence_boundary=intelligence_boundary,
        speech_adapters=models.speech_adapters,
        speech_pipeline=interaction.speech_pipeline,
        commands=commands,
        chat=chat,
        mom=mom,
        application_lifecycle=lifecycle,
        bootstrap_metadata=metadata,
    )


def _build_commands(
    f, p, mo, i, a, m, au, x, skills, governance, intelligence_boundary, approval_resume
) -> CommandRuntime:
    services = CommandServices(
        config=f.config,
        events=f.events,
        agents=p.agents,
        identities=p.identities,
        policies=p.policies,
        memory=p.memory,
        tasks=p.tasks,
        tools=a.tool_router,
        tool_runtime=x.tool_runtime,
        approvals=p.approvals,
        permissions=f.permissions,
        approval_resume=approval_resume,
        worker=a.worker,
        scheduler=au.scheduler,
        daemon=au.daemon,
        presence=p.presence,
        lifecycle=p.lifecycle,
        notifications=p.notifications,
        runner_identity=au.runner_identity,
        health=x.health,
        readiness=x.readiness,
        migrations=p.migrations,
        capabilities=p.capabilities,
        provisioning=a.provisioning,
        primary_agent=a.primary_agent,
        audit=a.audit,
        admin_policy=a.admin_policy,
        decisions=au.decisions,
        retention=a.retention,
        maintenance=a.maintenance,
        conversations=a.conversations,
        dead_letter=a.dead_letter,
        delegation=a.delegation,
        delegation_autonomy=a.delegation_autonomy,
        delegation_retry=a.delegation_retry,
        delegation_timeout=a.delegation_timeout,
        delegation_scheduling=a.delegation_scheduling,
        delegation_inbox=a.delegation_inbox,
        delegation_execution=a.delegation_execution,
        delegation_recovery=a.delegation_recovery,
        missions=m.missions,
        mission_context=m.mission_context,
        mission_supervision=m.mission_supervision,
        mission_control=m.mission_control,
        providers=mo.providers,
        models=mo.models,
        provider_plugins=mo.provider_plugins,
        lmstudio=mo.lmstudio,
        voice=i.voice,
        multimodal=i.multimodal,
        audio=i.audio,
        vision=i.vision,
        perception=i.perception,
        context_fusion=x.context_fusion,
        skills=skills,
        project_governance=governance,
        intelligence_boundary=intelligence_boundary,
        speech_adapters=mo.speech_adapters,
        speech_pipeline=i.speech_pipeline,
        tool_discovery=x.tool_discovery,
        tool_intents=x.tool_intents,
        mcp=x.mcp,
        mcp_bridge=x.mcp_bridge,
        execution_router=x.execution_router,
        agent_tool_calling=x.agent_tool_calling,
        attempts=m.attempts,
        worker_registry=m.worker_registry,
        worker_execution=m.worker_execution,
        mission_recovery_runtime=m.mission_recovery,
        swarm=m.swarm,
        ephemeral_agents=m.ephemeral_agents,
        workforce_planner=m.workforce_planner,
        mission_trace=m.mission_trace,
        system_insight=mo.system_insight,
        desktop=None,
        chat=None,
        world_state=None,
        attention=None,
        agent_loop=None,
    )
    registry = CommandRegistry()
    registry.register_all(build_command_handlers(services))
    return CommandRuntime(registry, services)
