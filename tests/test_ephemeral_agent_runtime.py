from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from synapse.agents.provisioning import AgentCreateRequest
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.ephemeral_agents.errors import (
    EphemeralAgentError,
    EphemeralAgentResourceUnavailable,
)
from synapse.ephemeral_agents.models import EphemeralAgentSpec, EphemeralAgentState
from synapse.missions.models import MissionTask, WorkerDescriptor

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Capacity:
    sufficient: bool = True
    reason: str = "capacity available"
    pressure_level: str = "low"
    recommended_concurrency: int | None = None


class Pressure:
    def __init__(self, capacity: Capacity | None = None):
        self.capacity = capacity or Capacity()

    def assess_capacity(self, workload: str):
        return self.capacity


class Models:
    def recommend_route(self, task: str, provider: str | None, model: str | None):
        return SimpleNamespace(
            provider_id=provider or "test-provider",
            model_id=model or "test-model",
            status="recommended",
            reason="explicit test route",
            estimated_ram_gb=1.0,
            estimated_vram_gb=0.0,
        )


def runtime_at(data_dir: Path):
    fresh = not data_dir.exists()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    create_runtime(settings)
    if fresh:
        shutil.rmtree(data_dir / "agents", ignore_errors=True)
    dump_structured_file(
        data_dir / "config" / "permissions.yaml",
        {"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}},
    )
    runtime = create_runtime(settings)
    runtime.ephemeral_agents.resource_pressure = Pressure()
    runtime.ephemeral_agents.model_capability = Models()
    runtime.workforce_planner.resource_pressure = Pressure()
    runtime.workforce_planner.model_capability = Models()
    return runtime


def parent(runtime):
    runtime.provisioning.create_agent(
        AgentCreateRequest(
            agent_id="central",
            display_name="Central",
            role="coordinator",
            autonomy_level="manual",
        ),
        context=runtime.context(),
    )
    path = runtime.data_dir.resolve("agents/central/CONFIG.yaml")
    config = load_structured_file(path)
    config["preferred_tools"] = ["read", "search"]
    config["allowed_tools"] = ["read", "search"]
    dump_structured_file(path, config)


def spec(mission_id: str = "mission-1", task_id: str = "task-1"):
    return EphemeralAgentSpec(
        mission_id=mission_id,
        task_id=task_id,
        parent_agent_id="central",
        role="research specialist",
        objective="Collect bounded evidence",
        required_capabilities=["research"],
        allowed_tools=["read", "write"],
        denied_tools=["write"],
        autonomy_ceiling="manual",
        risk_ceiling="low",
        created_by="swarm",
        correlation_id="trace-1",
    )


def test_ephemeral_lifecycle_worker_result_cleanup_and_restart() -> None:
    with tempfile.TemporaryDirectory() as directory:
        data_dir = Path(directory) / "data"
        runtime = runtime_at(data_dir)
        parent(runtime)
        runtime.worker_registry.register(
            WorkerDescriptor(
                worker_id="worker-1",
                agent_id="central",
                status="idle",
                capabilities=["research"],
                tools=["read"],
            )
        )

        instance = runtime.ephemeral_agents.create_instance(spec(), authority="swarm")
        assert instance.ephemeral_agent_id.startswith("ephemeral:mission-1:")
        assert instance.state is EphemeralAgentState.READY
        assert instance.tool_scope == ["read"]
        assert not (data_dir / "agents" / instance.ephemeral_agent_id).exists()

        assigned = runtime.ephemeral_agents.assign_worker(
            instance.ephemeral_agent_id, "worker-1"
        )
        assert assigned.state is EphemeralAgentState.ASSIGNED
        running = runtime.ephemeral_agents.start(instance.ephemeral_agent_id, "attempt-1")
        assert running.state is EphemeralAgentState.RUNNING
        runtime.ephemeral_agents.heartbeat(instance.ephemeral_agent_id)
        result = runtime.ephemeral_agents.complete(
            instance.ephemeral_agent_id,
            output_reference="artifact:verified-result",
            attempt_ids=["attempt-1"],
            verification={"approved": True},
            evidence=[{"kind": "test"}],
        )
        assert result.status == "completed"
        destroyed = runtime.ephemeral_agents.destroy(instance.ephemeral_agent_id)
        assert destroyed.state is EphemeralAgentState.DESTROYED
        assert destroyed.context_reference is None
        assert runtime.ephemeral_agents.contexts.list_all() == ()
        assert runtime.ephemeral_agents.get_result(instance.ephemeral_agent_id) == result

        restarted = runtime_at(data_dir)
        assert restarted.ephemeral_agents.get(instance.ephemeral_agent_id).state is EphemeralAgentState.DESTROYED
        assert restarted.ephemeral_agents.reconcile() == []
        assert not list((data_dir / "agents").glob("ephemeral:*"))


def test_ephemeral_authority_policy_resource_and_recursion_guards() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = runtime_at(Path(directory) / "data")
        parent(runtime)
        with pytest.raises(EphemeralAgentError):
            runtime.ephemeral_agents.create_instance(spec(), authority="api")
        with pytest.raises(EphemeralAgentError):
            runtime.ephemeral_agents.create_instance(
                EphemeralAgentSpec(
                    **{
                        **spec().__dict__,
                        "spec_id": "recursive",
                        "created_by": "ephemeral:mission:child",
                    }
                ),
                authority="mission",
            )
        runtime.ephemeral_agents.resource_pressure = Pressure(
            Capacity(False, "critical pressure", "critical")
        )
        with pytest.raises(EphemeralAgentResourceUnavailable):
            runtime.ephemeral_agents.create_instance(spec(), authority="mission")


def test_ephemeral_expiry_reconcile_is_idempotent_and_does_not_repeat_work() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = runtime_at(Path(directory) / "data")
        parent(runtime)
        runtime.ephemeral_agents.create_instance(spec(), authority="mission")
        future = datetime.now(UTC) + timedelta(hours=2)

        reconciled = runtime.ephemeral_agents.reconcile(future)
        assert reconciled[0].state is EphemeralAgentState.DESTROYED
        assert runtime.ephemeral_agents.reconcile(future) == []
        cleanup = runtime.ephemeral_agents.cleanup(dry_run=True)
        assert cleanup.destroyed == 0


def test_workforce_planner_avoids_simple_swarm_and_bounds_complex_work() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = runtime_at(Path(directory) / "data")
        parent(runtime)
        simple = runtime.missions.create_mission(
            "Simple", objective="One straightforward task", owner_agent_id="central"
        )
        simple_plan = runtime.planner.create_plan(
            simple.mission_id,
            simple.objective,
            tasks=[MissionTask(simple.mission_id, "Simple", "Do it")],
        )
        simple_decision = runtime.workforce_planner.plan(
            simple, simple_plan, parent_agent_id="central", strategy="parallel"
        )
        assert not simple_decision.required

        complex_mission = runtime.missions.create_mission(
            "Complex", objective="Parallel specialist work", owner_agent_id="central"
        )
        complex_plan = runtime.planner.create_plan(
            complex_mission.mission_id,
            complex_mission.objective,
            tasks=[
                MissionTask(
                    complex_mission.mission_id,
                    f"Specialist {index}",
                    f"Work stream {index}",
                    task_id=f"task-{index}",
                    required_capabilities=["research"],
                    required_tools=["read"],
                )
                for index in range(3)
            ],
        )
        runtime.workforce_planner.resource_pressure = Pressure(
            Capacity(True, pressure_level="high", recommended_concurrency=1)
        )
        decision = runtime.workforce_planner.plan(
            complex_mission,
            complex_plan,
            parent_agent_id="central",
            strategy="parallel",
        )
        assert decision.required
        assert len(decision.agents) == 3
        assert decision.max_concurrency == 1
        assert decision.strategy == "sequential"
        assert "resource_pressure_reduced_concurrency" in decision.warnings
