from __future__ import annotations

from dataclasses import dataclass

from synapse.approvals.resume import ApprovalResumeRuntime
from synapse.bootstrap.features.agents import AgentFeature
from synapse.bootstrap.features.automation import AutomationFeature
from synapse.bootstrap.features.foundation import FoundationFeature
from synapse.bootstrap.features.integration import IntegrationFeature
from synapse.bootstrap.features.interaction import InteractionFeature
from synapse.bootstrap.features.missions import MissionFeature
from synapse.bootstrap.features.models import ModelFeature
from synapse.bootstrap.features.platform import PlatformFeature
from synapse.commands.handlers import build_command_handlers
from synapse.commands.registry import CommandRegistry
from synapse.commands.runtime import CommandRuntime
from synapse.commands.services import CommandServices
from synapse.intelligence_boundary.runtime import IntelligenceBoundaryRuntime
from synapse.project_governance.runtime import ProjectGovernanceRuntime
from synapse.skills.runtime import SkillsRuntime


@dataclass(frozen=True)
class CommandCompositionDependencies:
    foundation: FoundationFeature
    platform: PlatformFeature
    models: ModelFeature
    interaction: InteractionFeature
    agents: AgentFeature
    missions: MissionFeature
    automation: AutomationFeature
    integration: IntegrationFeature
    skills: SkillsRuntime
    governance: ProjectGovernanceRuntime
    intelligence_boundary: IntelligenceBoundaryRuntime
    approval_resume: ApprovalResumeRuntime


def build_command_runtime(d: CommandCompositionDependencies) -> CommandRuntime:
    f, p, mo, i, a, m, au, x = (
        d.foundation,
        d.platform,
        d.models,
        d.interaction,
        d.agents,
        d.missions,
        d.automation,
        d.integration,
    )
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
        approval_resume=d.approval_resume,
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
        skills=d.skills,
        project_governance=d.governance,
        intelligence_boundary=d.intelligence_boundary,
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
