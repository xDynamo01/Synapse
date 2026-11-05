from synapse.bootstrap.adapters.cognitive_planning import CognitivePlanning
from synapse.bootstrap.adapters.mom import PrimaryInference
from synapse.bootstrap.adapters.resource_policy import ResourcePolicyAdapter
from synapse.bootstrap.adapters.swarm_residency import SwarmResidency
from synapse.bootstrap.features.agents import AgentFeature
from synapse.bootstrap.features.missions import MissionFeature
from synapse.bootstrap.features.models import ModelFeature
from synapse.bootstrap.features.platform import PlatformFeature
from synapse.chat.runtime import ChatRuntime
from synapse.core.exceptions import ValidationError
from synapse.missions.models import MissionTask
from synapse.model_providers.synapse_local import SynapseLocalModelAdapter
from synapse.mom.runtime import MoMRuntime


def bind_cognitive_orchestration(mom: MoMRuntime, chat: ChatRuntime, models: ModelFeature,
                                 missions: MissionFeature, platform: PlatformFeature,
                                 agents: AgentFeature) -> None:
    chat.complex_missions = CognitivePlanning(
        mom, PrimaryInference(models.models, agents.context_loader, platform.memory),
        models.models, missions.missions, missions.planner,
    )
    local_pool = models.models.adapters["synapse_local"]
    if isinstance(local_pool, SynapseLocalModelAdapter):
        resources = ResourcePolicyAdapter(local_pool, missions.swarm, missions.missions)
        mom.resources = resources
        missions.mission_dispatcher.resource_limit = resources.concurrency
        missions.swarm.admission_lock = missions.mission_dispatcher.admission_lock
        saved_policy = mom.configurations.read("default")
        if saved_policy is not None:
            mom.resources.apply(saved_policy.resource_policy)
        residency = SwarmResidency(
            models.models, platform.agents, missions.ephemeral_agents, missions.attempts,
            models.system_insight.resource_pressure, local_pool,
            missions.missions,
        )
        missions.swarm.residency = residency
        missions.swarm_interactions.select_model_routes = residency.select_model_routes

        def guard_plan_review(mission_id: str) -> None:
            for swarm in missions.swarm.list(mission_id):
                if (swarm.status in {"running", "paused"}
                        or swarm.metadata.get("resource_transition", "STABLE") != "STABLE"
                        or local_pool.has_reservation(swarm.swarm_id)):
                    raise ValidationError("Release Swarm resources before replacing its mission plan.")

        missions.missions.plan_review_guard = guard_plan_review

        def admit_worker(mission_id: str, task: MissionTask, agent_id: str) -> bool:
            coordinators = resources.coordinators(mission_id)
            return not coordinators or (len(coordinators) == 1
                                        and agent_id in coordinators[0].member_agent_ids)

        missions.mission_dispatcher.worker_admission = admit_worker

        def admit_route(mission_id: str, task: MissionTask, agent_id: str) -> tuple[str, str] | None:
            resources.concurrency(mission_id, 1)
            active = resources.coordinators(mission_id)
            if len(active) > 1:
                raise ValueError("Mission has multiple Swarm coordinators.")
            return residency.task_route(active[0], task, agent_id) if active else None

        missions.mission_dispatcher.route_admission = admit_route
        missions.worker_execution.route_admission = admit_route
