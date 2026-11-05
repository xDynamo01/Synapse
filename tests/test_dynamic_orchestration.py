"""Behavioral regression for the NORMAL/SWARM boundary; no heavy models."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from unittest.mock import patch

import pytest

from synapse.core.exceptions import ValidationError
from synapse.core.execution_policy import ExecutionRegime, ResourcePolicy
from synapse.missions.models import MissionTask, WorkerDescriptor
from synapse.model_providers.synapse_local import SynapseLocalModelAdapter
from synapse.models.errors import ModelError
from synapse.mom.contracts import Operation, Output, Route
from synapse.mom.selection import classify_operation, requires_plan
from test_local_chat_runtime import runtime_in_tempdir
from test_synapse_local_concurrency import pool


def reserve(adapter, owner="swarm-a", models=("a", "b"), **overrides):
    values = dict(ram_bytes=200, vram_bytes=100, available_ram=1000, available_vram=1000)
    adapter.reserve_models(owner, models, **{**values, **overrides})


def test_swarm_residency_survives_both_policy_changes_and_idle_eviction(tmp_path, monkeypatch):
    adapter, created = pool(tmp_path, monkeypatch, 2)
    try:
        reserve(adapter)
        assert len(created) == 2
        for policy in (ResourcePolicy.ECONOMICAL, ResourcePolicy.RESPONSIVE):
            adapter.set_resource_policy(policy)
            assert all(server.process.alive for server in created)
            assert adapter.residency_status()["execution_regime"] == ExecutionRegime.SWARM
        with pytest.raises(ModelError, match="capacity"):
            with adapter._lease("other", 0.02):
                pytest.fail("Reserved idle model was evicted")
        adapter.set_resource_policy(ResourcePolicy.ECONOMICAL)
        adapter.release_models("swarm-a")
        assert not adapter._servers
        assert adapter.residency_status()["execution_regime"] == ExecutionRegime.NORMAL
    finally:
        adapter.shutdown()


@pytest.mark.parametrize("overrides", [dict(available_ram=199), dict(available_vram=99)])
def test_insufficient_resources_change_nothing(tmp_path, monkeypatch, overrides):
    adapter, created = pool(tmp_path, monkeypatch, 2)
    try:
        with pytest.raises(ModelError, match="Insufficient"):
            reserve(adapter, **overrides)
        assert not created and not adapter._reservations
    finally:
        adapter.shutdown()


def test_transition_and_release_defer_while_busy(tmp_path, monkeypatch):
    adapter, _ = pool(tmp_path, monkeypatch, 2)
    try:
        with adapter._lease("a", 1):
            with pytest.raises(ModelError, match="Wait for active"):
                reserve(adapter)
        reserve(adapter)
        with adapter._lease("a", 1):
            with pytest.raises(ModelError, match="still busy"):
                adapter.release_models("swarm-a")
            adapter.set_resource_policy(ResourcePolicy.ECONOMICAL)
        assert set(adapter._servers) == {"a", "b"}
    finally:
        adapter.shutdown()


def test_partial_initialization_rolls_back_only_new_acquisitions(tmp_path, monkeypatch):
    adapter, created = pool(tmp_path, monkeypatch, 2)
    with adapter._lease("a", 1):
        pass
    original = adapter._ensure_server

    def fail_second(model, timeout):
        if model == "b":
            raise RuntimeError("load failed")
        return original(model, timeout)

    monkeypatch.setattr(adapter, "_ensure_server", fail_second)
    try:
        with pytest.raises(RuntimeError, match="load failed"):
            reserve(adapter)
        assert created[0].process.alive and set(adapter._servers) == {"a"}
        assert not adapter._reservations
    finally:
        adapter.shutdown()


def test_shared_model_remains_reserved_until_last_owner(tmp_path, monkeypatch):
    adapter, _ = pool(tmp_path, monkeypatch, 2)
    try:
        reserve(adapter, models=("a",))
        reserve(adapter, owner="swarm-b", models=("a",))
        adapter.set_resource_policy(ResourcePolicy.ECONOMICAL)
        adapter.release_models("swarm-a")
        assert "a" in adapter._servers
        adapter.release_models("swarm-b")
        assert not adapter._servers
    finally:
        adapter.shutdown()


def test_economical_policy_waits_for_normal_inference(tmp_path, monkeypatch):
    adapter, _ = pool(tmp_path, monkeypatch)
    try:
        with adapter._lease("a", 1) as server:
            adapter.set_resource_policy(ResourcePolicy.ECONOMICAL)
            assert server.process.alive
        assert not server.process.alive
    finally:
        adapter.shutdown()


def test_restart_does_not_invent_recovered_residency(tmp_path, monkeypatch):
    adapter, _ = pool(tmp_path, monkeypatch, 2)
    reserve(adapter)
    restarted = SynapseLocalModelAdapter(adapter.data_dir, max_loaded_models=2)
    monkeypatch.setattr(restarted, "_resolve_model_path", adapter._resolve_model_path)
    try:
        assert restarted.residency_status()["transition_status"] == "RECOVERY_REQUIRED"
        restarted.set_resource_policy(ResourcePolicy.ECONOMICAL)
        with pytest.raises(ModelError, match="Reconcile"):
            with restarted._lease("a", 1):
                pytest.fail("Unreconciled process was replaced")
        with pytest.raises(ModelError, match="reconciliation"):
            restarted.release_models("swarm-a")
    finally:
        adapter.shutdown()
        restarted.shutdown()


def test_reservation_cannot_race_with_a_busy_lease(tmp_path, monkeypatch):
    adapter, _ = pool(tmp_path, monkeypatch, 2)
    barrier = Barrier(2, timeout=3)

    def normal():
        with adapter._lease("a", 1):
            barrier.wait()
            barrier.wait()

    try:
        with ThreadPoolExecutor(1) as executor:
            future = executor.submit(normal)
            barrier.wait()
            with pytest.raises(ModelError, match="Wait for active"):
                reserve(adapter)
            barrier.wait()
            future.result()
    finally:
        adapter.shutdown()


def test_contextual_routing_and_parallelism_do_not_imply_swarm():
    assert classify_operation("Agora deixe ele mais seguro", "coding") == Operation.CODING
    assert classify_operation("Bom dia", "coding") == Operation.CONVERSATION
    assert requires_plan("Desenvolva backend e frontend com testes")
    assert not requires_plan("Explique Python")
    assert not requires_plan("Olá\n\nDesenvolva backend e frontend")
    assert ExecutionRegime.NORMAL != ResourcePolicy.RESPONSIVE


@pytest.fixture
def runtime():
    directory, _, runtime = runtime_in_tempdir()
    runtime.primary_agent.set_primary(runtime.context(), "artemis")
    try:
        yield runtime
    finally:
        directory.cleanup()


def test_disabled_legacy_flag_does_not_disable_routing_and_manual_wins(runtime):
    routes = (Route(operation=Operation.CODING, provider="mock", model="coder"),
              Route(operation=Operation.CONVERSATION, provider="mock", model="dialogue"))
    runtime.mom.configure(runtime.context(), "default", False, routes, 0)
    selected = runtime.mom.select_for_chat(runtime.context(), "artemis", "Escreva código", "default")
    assert selected[1].model == "coder"
    conversation = runtime.chat.send_message(runtime.context(), "artemis", "Olá")
    assert conversation.model["model"] == "dialogue"
    manual = runtime.chat.send_message(runtime.context(), "artemis", "Escreva código",
                                       model_provider_override="mock", model_override="manual")
    assert manual.model["model"] == "manual"
    assert not runtime.missions.list_missions()


def test_policy_is_revision_checked_and_persisted(runtime):
    saved = runtime.mom.configure(runtime.context(), "default", True, (), 0, ResourcePolicy.ECONOMICAL)
    assert saved.resource_policy == ResourcePolicy.ECONOMICAL
    assert runtime.mom.configurations.read("default").resource_policy == ResourcePolicy.ECONOMICAL
    assert runtime.models.adapters["synapse_local"].resource_policy == ResourcePolicy.ECONOMICAL
    assert runtime.mom.resource_status(runtime.context())["execution_regime"] == "NORMAL"


def test_parallel_normal_mission_keeps_both_completions_and_dependency_gate(runtime):
    mission = runtime.missions.create_mission("Parallel normal")
    tasks = [MissionTask(mission.mission_id, key, key, task_id=key) for key in ("a", "b")]
    tasks.append(MissionTask(mission.mission_id, "join", "join", task_id="c", dependencies=["a", "b"]))
    plan = runtime.planner.create_plan(mission.mission_id, "parallel", tasks=tasks)
    runtime.missions.attach_plan(mission.mission_id, plan.plan_id)
    for key in ("a", "b"):
        runtime.worker_registry.register(WorkerDescriptor(key, key, "idle"))
    barrier = Barrier(2, timeout=5)

    def execute(attempt, task, mission, worker, context):
        barrier.wait()
        return {"output": task.task_id}

    runtime.worker_execution.executor = execute
    first = runtime.missions.dispatch_ready_tasks(mission.mission_id, 2)
    assert len(first.dispatched) == 2
    current = runtime.planner.get_plan(mission.mission_id, plan.plan_id)
    assert [task.status for task in current.tasks] == ["completed", "completed", "pending"]
    assert not runtime.swarm.list()
    assert runtime.mom.resource_status(runtime.context())["execution_regime"] == "NORMAL"


def test_replanning_invalidates_downstream_but_preserves_unaffected_results(runtime):
    mission = runtime.missions.create_mission("Replan")
    tasks = [MissionTask(mission.mission_id, key, key, task_id=key,
                         status="completed", result={"output": key}) for key in ("a", "b", "c")]
    tasks[1] = replace(tasks[1], dependencies=["a"])
    plan = runtime.planner.create_plan(mission.mission_id, "Replan", tasks=tasks)
    proposal = runtime.planner.replace_plan(mission.mission_id, plan.plan_id, plan.version,
                                            [replace(tasks[0], objective="changed"), *tasks[1:]])
    assert [task.status for task in proposal.tasks] == ["pending", "pending", "completed"]
    assert proposal.tasks[2].result == {"output": "c"}
    assert runtime.planner.get_plan(mission.mission_id, plan.plan_id).tasks[0].status == "completed"


def test_generated_plan_is_not_authority_to_run(runtime):
    mission = runtime.missions.create_mission("Review first", metadata={"requires_plan_review": True})
    plan = runtime.planner.create_plan(mission.mission_id, "Review", tasks=[
        MissionTask(mission.mission_id, "a", "a")])
    runtime.missions.attach_plan(mission.mission_id, plan.plan_id)
    with patch.object(runtime.worker_execution, "execute_attempt") as execute:
        with pytest.raises(ValidationError, match="Review"):
            runtime.missions.dispatch_ready_tasks(mission.mission_id)
        execute.assert_not_called()


def test_plan_review_cannot_replace_paused_swarm_plan(runtime):
    mission = runtime.missions.create_mission("Reserved plan")
    plan = runtime.planner.create_plan(mission.mission_id, "Reserved", tasks=[
        MissionTask(mission.mission_id, "a", "a")])
    runtime.missions.attach_plan(mission.mission_id, plan.plan_id)
    swarm = runtime.swarm.create(mission.mission_id, "parallel", "artemis", ["artemis"])
    runtime.swarm.pause(swarm.swarm_id)
    current = runtime.missions.get_mission(mission.mission_id)
    with pytest.raises(ValidationError, match="Release Swarm"):
        runtime.missions.accept_plan(mission.mission_id, plan.plan_id, current.revision)
    assert runtime.missions.get_mission(mission.mission_id).revision == current.revision


def test_invalid_swarm_plan_does_not_acquire_residency(runtime):
    mission = runtime.missions.create_mission("No plan")
    swarm = runtime.swarm.create(mission.mission_id, "parallel", "artemis", ["artemis"])
    with patch.object(runtime.swarm.residency, "prepare") as prepare:
        with pytest.raises(Exception, match="active plan"):
            runtime.swarm.run(swarm.swarm_id)
        prepare.assert_not_called()
    assert runtime.swarm.get(swarm.swarm_id).status == "created"


def test_chat_planning_uses_existing_mission_and_replanning_keeps_active_plan(runtime):
    runtime.mom.configure(runtime.context(), "default", True, (
        Route(operation=Operation.REASONING, provider="mock", model="planner"),
        Route(operation=Operation.CODING, provider="mock", model="coder"),
    ), 0)
    proposal = Output(provider="mock", model="planner", content='''{"tasks":[
        {"id":"backend","title":"Backend","objective":"Implement backend",
         "capability":"coding","acceptance_criteria":["Tests pass"]},
        {"id":"frontend","title":"Frontend","objective":"Implement frontend",
         "capability":"coding","dependencies":["backend"],"acceptance_criteria":["Build passes"]}
    ]}''')
    with patch.object(runtime.chat.complex_missions.inference, "generate", return_value=proposal):
        turn = runtime.chat.send_message(runtime.context(), "artemis",
                                         "Desenvolva backend e frontend com testes")
        mission = runtime.missions.list_missions()[0]
        assert mission.metadata["execution_regime"] == "NORMAL"
        assert mission.metadata["requires_plan_review"] is True
        assert not runtime.swarm.list()
        plan = runtime.planner.get_plan(mission.mission_id, mission.plan_id)
        assert plan.tasks[1].dependencies == [plan.tasks[0].task_id]
        assert plan.tasks[0].verification_policy["require_tool_evidence"] is True
        runtime.chat.complex_missions.prepare(runtime.context(), "artemis",
            "Replaneje com uma interface mais simples", mission.metadata["chat_session_id"], None)
        assert runtime.missions.get_mission(mission.mission_id).plan_id == plan.plan_id
        assert len(runtime.missions.list_missions()) == 1
        assert turn.command == {"type": "mission_plan", "mission_id": mission.mission_id}
        local = runtime.chat.local_chat(runtime.context(),
            "Desenvolva backend e frontend com testes", agent_id="artemis")
        assert local.conversation_id is not None
        assert "Missão planejada" in local.response


def test_cancelled_swarm_returns_mission_to_normal_admission(runtime):
    mission = runtime.missions.create_mission("Normal after Swarm")
    plan = runtime.planner.create_plan(mission.mission_id, "Task", tasks=[
        MissionTask(mission.mission_id, "a", "a")])
    runtime.missions.attach_plan(mission.mission_id, plan.plan_id)
    swarm = runtime.swarm.create(mission.mission_id, "parallel", "artemis", ["artemis"])
    runtime.swarm.cancel(swarm.swarm_id)
    runtime.worker_registry.register(WorkerDescriptor("other", "other", "idle"))
    runtime.worker_execution.executor = lambda *args: {"output": "complete"}
    result = runtime.missions.dispatch_ready_tasks(mission.mission_id)
    assert len(result.dispatched) == 1
    assert runtime.mom.resource_status(runtime.context())["execution_regime"] == "NORMAL"
