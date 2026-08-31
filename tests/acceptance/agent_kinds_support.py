from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from synapse.agents.provisioning import AgentCreateRequest
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.missions.models import MissionTask, WorkerDescriptor

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Capacity:
    sufficient: bool = True
    reason: str = "capacity available"
    pressure_level: str = "low"
    recommended_concurrency: int | None = None


class ControlledPressure:
    def __init__(self, capacity: Capacity | None = None):
        self.capacity = capacity or Capacity()

    def assess_capacity(self, workload: str):
        return self.capacity


class ControlledModels:
    def recommend_route(self, task: str, provider: str | None, model: str | None):
        return SimpleNamespace(
            provider_id=provider or "controlled",
            model_id=model or "small-test-model",
            status="recommended",
            reason="capability and pressure matched",
            estimated_ram_gb=1.0,
            estimated_vram_gb=0.0,
        )


def runtime_at(data_dir: Path, *, clean: bool = False):
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    create_runtime(settings)
    if clean:
        shutil.rmtree(data_dir / "agents", ignore_errors=True)
        (data_dir / "agents").mkdir(parents=True)
    dump_structured_file(
        data_dir / "config" / "permissions.yaml",
        {"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}},
    )
    runtime = create_runtime(settings)
    if clean:
        shutil.rmtree(data_dir / "agents", ignore_errors=True)
        (data_dir / "agents").mkdir(parents=True)
    pressure = ControlledPressure()
    models = ControlledModels()
    runtime.ephemeral_agents.resource_pressure = pressure
    runtime.ephemeral_agents.model_capability = models
    runtime.workforce_planner.resource_pressure = pressure
    runtime.workforce_planner.model_capability = models
    return runtime


def provision(runtime, agent_id: str, role: str = "project_agent", tools=()):
    result = runtime.provisioning.create_agent(
        AgentCreateRequest(
            agent_id=agent_id,
            display_name=agent_id.title(),
            role=role,
            autonomy_level="manual",
        ),
        context=runtime.context(),
    )
    path = runtime.data_dir.resolve(f"agents/{agent_id}/CONFIG.yaml")
    config = load_structured_file(path)
    config["preferred_tools"] = list(tools)
    config["allowed_tools"] = list(tools)
    dump_structured_file(path, config)
    return result


def create_complex_mission(runtime, owner: str = "central", count: int = 2):
    mission = runtime.missions.create_mission(
        "Complex acceptance mission",
        objective="Execute parallel verified specialist work",
        owner_agent_id=owner,
    )
    tasks = [
        MissionTask(
            mission.mission_id,
            f"Specialist {index}",
            f"Produce verified stream {index}",
            task_id=f"task-{index}",
            required_capabilities=["work"],
            required_tools=["read"],
        )
        for index in range(count)
    ]
    plan = runtime.planner.create_plan(mission.mission_id, mission.objective, tasks=tasks)
    runtime.missions.attach_plan(mission.mission_id, plan.plan_id)
    return mission, plan


def register_workers(runtime, count: int):
    for index in range(count):
        runtime.worker_registry.register(
            WorkerDescriptor(
                worker_id=f"worker-{index}",
                agent_id="central",
                status="idle",
                capabilities=["work"],
                tools=["read"],
            )
        )
