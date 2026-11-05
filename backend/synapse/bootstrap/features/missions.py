from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.ephemeral_agents.runtime import EphemeralAgentRuntime
from synapse.mission_control.runtime import MissionControlRuntime
from synapse.missions.attempts import TaskAttemptRuntime
from synapse.missions.context import MissionContextRuntime
from synapse.missions.dispatcher import MissionDispatcher
from synapse.missions.planner import PlannerRuntime
from synapse.missions.recovery import MissionRecoveryRuntime
from synapse.missions.runtime import MissionRuntime
from synapse.missions.supervision import MissionSupervisionRuntime
from synapse.missions.trace import MissionTraceRuntime
from synapse.missions.verification import ResultVerifier
from synapse.swarm.interaction import SwarmInteractionRuntime
from synapse.swarm.runtime import SwarmRuntime
from synapse.swarm.workforce import EphemeralWorkforcePlanner
from synapse.workers.registry import WorkerRegistry
from synapse.workers.runtime import WorkerRuntime
from synapse.workers.scheduler import WorkerScheduler


@dataclass(frozen=True)
class MissionFeatureDependencies:
    data_dir: Any
    events: Any
    platform: Any
    agents: Any
    system_insight: Any


@dataclass(frozen=True)
class MissionFeature:
    planner: PlannerRuntime
    worker_registry: WorkerRegistry
    worker_scheduler: WorkerScheduler
    result_verifier: ResultVerifier
    attempts: TaskAttemptRuntime
    missions: MissionRuntime
    worker_execution: WorkerRuntime
    mission_dispatcher: MissionDispatcher
    mission_recovery: MissionRecoveryRuntime
    mission_trace: MissionTraceRuntime
    swarm: SwarmRuntime
    swarm_interactions: SwarmInteractionRuntime
    mission_context: MissionContextRuntime
    mission_supervision: MissionSupervisionRuntime
    mission_control: MissionControlRuntime
    ephemeral_agents: EphemeralAgentRuntime
    workforce_planner: EphemeralWorkforcePlanner


class MissionFeatureBuilder:
    metadata = FeatureMetadata("missions-and-swarm")

    def build(self, d: MissionFeatureDependencies) -> BuiltFeature[MissionFeature]:
        a = d.agents
        p = d.platform
        planner = PlannerRuntime(d.data_dir, d.events)
        worker_registry = WorkerRegistry(d.data_dir, d.events)
        worker_scheduler = WorkerScheduler(worker_registry)
        result_verifier = ResultVerifier()
        attempts = TaskAttemptRuntime(d.data_dir, d.events)
        missions = MissionRuntime(
            d.data_dir,
            d.events,
            a.delegation,
            a.dead_letter,
            a.conversations,
            p.agents,
            planner,
            worker_registry,
            worker_scheduler,
            result_verifier,
            attempts,
        )
        missions.resource_pressure = d.system_insight.resource_pressure
        missions.desktop_runtime = a.desktop
        worker_execution = WorkerRuntime(
            attempts, worker_registry, missions, planner, result_verifier, d.events
        )
        mission_dispatcher = MissionDispatcher(
            missions,
            planner,
            attempts,
            worker_registry,
            worker_scheduler,
            worker_execution,
            d.events,
        )
        missions.dispatcher = mission_dispatcher
        mission_recovery = MissionRecoveryRuntime(
            missions,
            planner,
            attempts,
            worker_registry,
            worker_scheduler,
            d.events,
            a.dead_letter,
        )
        mission_trace = MissionTraceRuntime(d.events)
        ephemeral_agents = EphemeralAgentRuntime(
            d.data_dir,
            d.events,
            agents=d.platform.agents,
            identities=d.platform.identities,
            resource_pressure=d.system_insight.resource_pressure,
            model_capability=d.system_insight.model_capabilities,
            workers=worker_registry,
            attempts=attempts,
            authorized_tools=lambda agent_id: [
                tool.tool_id for tool in a.agent_runtime.available_tools(agent_id).tools
                if tool.available or tool.requires_approval
            ],
        )
        workforce_planner = EphemeralWorkforcePlanner(
            d.platform.agents,
            d.system_insight.resource_pressure,
            d.system_insight.model_capabilities,
            ephemeral_agents,
        )
        swarm = SwarmRuntime(
            d.data_dir,
            d.events,
            missions,
            worker_registry,
            ephemeral_agents,
            workforce_planner,
        )
        swarm_interactions = SwarmInteractionRuntime(
            d.data_dir,
            d.events,
            missions,
            planner,
            swarm,
            ephemeral_agents,
            a.primary_agent,
        )
        mission_context = MissionContextRuntime(
            d.events,
            missions,
            a.delegation,
            a.delegation_execution,
            a.dead_letter,
            a.delegation_recovery,
            a.conversations,
            a.delegation_timeout,
        )
        mission_supervision = MissionSupervisionRuntime(
            d.events, missions, mission_context, a.delegation_recovery, a.dead_letter
        )
        mission_control = MissionControlRuntime(
            missions,
            mission_context,
            mission_supervision,
            a.delegation_inbox,
            a.delegation,
            a.admin,
            attempts,
            worker_registry,
            swarm,
            a.dead_letter,
        )
        value = MissionFeature(
            planner,
            worker_registry,
            worker_scheduler,
            result_verifier,
            attempts,
            missions,
            worker_execution,
            mission_dispatcher,
            mission_recovery,
            mission_trace,
            swarm,
            swarm_interactions,
            mission_context,
            mission_supervision,
            mission_control,
            ephemeral_agents,
            workforce_planner,
        )
        return BuiltFeature(
            value,
            self.metadata,
            health_contributors=(missions, mission_supervision, ephemeral_agents),
            ports={"missions": missions, "mission_control": mission_control},
        )
