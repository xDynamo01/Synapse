"""Bind existing Swarm transitions to the managed local pool, not to MoM."""
from __future__ import annotations

from synapse.agents.registry import AgentRegistry
from synapse.core.exceptions import ValidationError
from synapse.ephemeral_agents.runtime import EphemeralAgentRuntime
from synapse.missions.attempts import TaskAttemptRuntime
from synapse.missions.models import MissionTask, SwarmDescriptor
from synapse.missions.runtime import MissionRuntime
from synapse.model_providers.synapse_local import SynapseLocalModelAdapter
from synapse.models.router import ModelRouter
from synapse.system_insight.resource_pressure import ResourcePressureRuntime


class SwarmResidency:
    def __init__(self, models: ModelRouter, agents: AgentRegistry,
                 ephemeral: EphemeralAgentRuntime, attempts: TaskAttemptRuntime,
                 pressure: ResourcePressureRuntime, local: SynapseLocalModelAdapter,
                 missions: MissionRuntime):
        self.models, self.agents, self.ephemeral = models, agents, ephemeral
        self.attempts, self.pressure, self.local = attempts, pressure, local
        self.missions = missions

    def select_model_routes(self, count: int, explicit: tuple[str, ...]) -> list[tuple[str, str]]:
        profiles = self.models.system_config.get("models", {}).get("resource_profiles", {})
        if not profiles:
            return []
        if explicit:
            names = list(explicit)
            if any(name not in profiles for name in names):
                raise ValidationError("O modelo solicitado não possui um perfil de recursos para Swarm.")
        else:
            names = sorted(profiles, key=lambda name: int(profiles[name].get("ram_bytes", 0)))[:min(count, self.local.max_loaded_models)]
        return [("synapse_local", name) for name in names]

    def prepare(self, swarm: SwarmDescriptor) -> None:
        if not swarm.member_agent_ids:
            raise ValidationError("Swarm requires participants before activation.")
        if self.local.recovery_required(swarm.swarm_id):
            self.release(swarm)
        selected: set[str] = set()
        routes: set[tuple[str, str | None]] = set()
        for agent_id in swarm.member_agent_ids:
            if agent_id.startswith("ephemeral:"):
                instance = self.ephemeral.get(agent_id)
                if instance.mission_id != swarm.mission_id or instance.state.value not in {"assigned", "running", "waiting", "completed"}:
                    raise ValidationError("Temporary participant is not active in this mission.")
                selection = instance.model_selection
                routes.add((str(selection.get("provider") or ""), selection.get("model")))
                continue
            route = self.models.route_for_agent(self.agents.get(agent_id))
            routes.add((route.provider, route.model))
        mission = self.missions.get_mission(swarm.mission_id)
        if mission.plan_id:
            for task in self.missions.list_tasks(swarm.mission_id):
                if task.metadata.get("model"):
                    provider = task.metadata.get("provider")
                    if not provider:
                        providers = {provider for provider, _ in routes}
                        if len(providers) != 1:
                            raise ValidationError("Task model override needs an explicit provider.")
                        provider = next(iter(providers))
                    routes.add((str(provider), str(task.metadata["model"])))
        for provider, model in routes:
            if provider == "mock":
                continue
            if provider != "synapse_local" or not model:
                raise ValidationError("Provider does not support guaranteed Swarm residency.")
            selected.add(model)
        if not selected:
            return
        profiles = self.models.system_config.get("models", {}).get("resource_profiles", {})
        ram = vram = 0
        for model in selected:
            profile = profiles.get(model, {})
            required_ram, required_vram = profile.get("ram_bytes"), profile.get("vram_bytes")
            if (type(required_ram) is not int or required_ram <= 0
                    or type(required_vram) is not int or required_vram < 0):
                raise ValidationError("Configure measured RAM/VRAM resource profiles before Swarm activation.")
            ram += required_ram
            vram += required_vram
        hardware = self.pressure.hardware.inspect()
        available_ram = max(0, (hardware.memory.total_bytes or 0) - (hardware.memory.used_bytes or 0))
        available_vram = sum(max(0, (gpu.memory_total_bytes or 0) - (gpu.memory_used_bytes or 0))
                             for gpu in hardware.gpus if gpu.memory_used_bytes is not None)
        self.local.reserve_models(swarm.swarm_id, tuple(selected), ram_bytes=ram, vram_bytes=vram,
                                  available_ram=available_ram, available_vram=available_vram)

    def release(self, swarm: SwarmDescriptor) -> None:
        active = [attempt for attempt in self.attempts.list(mission_id=swarm.mission_id)
                  if self.attempts.active_for_task(attempt.task_id) == attempt]
        if active:
            raise ValidationError("Swarm transition deferred until active mission attempts finish.")
        self.local.release_models(swarm.swarm_id)

    def task_route(self, swarm: SwarmDescriptor, task: MissionTask, agent_id: str) -> tuple[str, str]:
        if agent_id not in swarm.member_agent_ids:
            raise ValidationError("Worker is not a member of this Swarm.")
        if agent_id.startswith("ephemeral:"):
            instance = self.ephemeral.get(agent_id)
            if instance.mission_id != swarm.mission_id or instance.task_id != task.task_id:
                raise ValidationError("Temporary participant cannot execute another task or mission.")
            selection = instance.model_selection
            provider = str(selection.get("provider") or "")
            model = str(selection.get("model") or "")
        else:
            route = self.models.route_for_agent(self.agents.get(agent_id))
            provider = str(task.metadata.get("provider") or route.provider)
            model = str(task.metadata.get("model") or route.model or "")
        if not model:
            raise ValidationError("Swarm participant has no assigned model.")
        if provider != "mock" and (provider != "synapse_local"
                                   or not self.local.owns_reservation(swarm.swarm_id, model)):
            raise ValidationError("Task model is not reserved by this Swarm.")
        return provider, model
