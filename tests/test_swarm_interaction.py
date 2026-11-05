from types import SimpleNamespace

import pytest

from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.swarm.interaction import SwarmInteractionRuntime


class Events:
    def __init__(self):
        self.items = []

    def emit(self, event_type, actor_id, payload):
        self.items.append((event_type, actor_id, payload))


class Missions:
    def __init__(self):
        self.created = []
        self.attached = []

    def create_mission(self, **payload):
        self.created.append(payload)
        return SimpleNamespace(mission_id="mission-1")

    def attach_plan(self, mission_id, plan_id):
        self.attached.append((mission_id, plan_id))


class Planner:
    def __init__(self):
        self.calls = []

    def create_plan(self, mission_id, objective, **payload):
        self.calls.append((mission_id, objective, payload))
        return SimpleNamespace(plan_id="plan-1")


class Swarms:
    def __init__(self, *, fail=False):
        self.created = []
        self.provisioned = []
        self.fail = fail

    def create(self, **payload):
        self.created.append(payload)
        return SimpleNamespace(swarm_id="swarm-1")

    def provision_workforce(self, swarm_id):
        self.provisioned.append(swarm_id)
        if self.fail:
            raise RuntimeError("provision failed")
        return [SimpleNamespace(worker_id="worker-1")]

    def get(self, swarm_id):
        return SimpleNamespace(swarm_id=swarm_id)

    def run(self, swarm_id):
        return {"status": "completed", "swarm_id": swarm_id}


class EphemeralAgents:
    @staticmethod
    def limits():
        return {
            "max_ephemeral_agents_per_mission": 6,
            "max_child_agents_per_agent": 6,
            "max_concurrent_ephemeral_agents": 6,
        }


class PrimaryAgent:
    @staticmethod
    def get_primary(workspace_id):
        assert workspace_id == "workspace-a"
        return SimpleNamespace(agent_id="artemis")


def runtime(tmp_path, *, swarms=None):
    events = Events()
    missions = Missions()
    planner = Planner()
    swarm_runtime = swarms or Swarms()
    value = SwarmInteractionRuntime(
        DataDir(tmp_path), events, missions, planner, swarm_runtime,
        EphemeralAgents(), PrimaryAgent(),
    )
    return value, events, missions, planner, swarm_runtime


def prepare(value, text, *, idempotency_key=None):
    return value.prepare(
        text=text,
        conversation_id="conversation-1",
        workspace_id="workspace-a",
        project_id="project-a",
        session_id="session-a",
        actor_id="user-a",
        idempotency_key=idempotency_key,
    )


def test_ordinary_conversation_has_no_swarm_side_effect(tmp_path):
    value, _, missions, _, swarms = runtime(tmp_path)
    assert prepare(value, "Analise este arquivo") is None
    assert missions.created == []
    assert swarms.created == []


def test_explicit_command_is_accepted_and_persisted_before_execution(tmp_path):
    value, _, missions, _, swarms = runtime(tmp_path)
    interaction = prepare(value, "Use um Swarm para analisar o projeto")
    assert interaction is not None
    assert interaction.status == "accepted"
    assert interaction.recommended_agents == 2
    assert value.get(interaction.request_id) == interaction
    assert missions.created == []
    assert swarms.created == []


def test_accepting_recommendation_creates_real_mission_plan_and_swarm(tmp_path):
    value, _, missions, planner, swarms = runtime(tmp_path)
    interaction = prepare(value, "Use um Swarm para analisar o projeto")
    result = value.execute_accepted(interaction.request_id)

    assert result.status == "completed"
    assert result.mission_id == "mission-1"
    assert result.swarm_id == "swarm-1"
    assert result.execution_status == "completed"
    assert missions.created[0]["conversation_id"] == "conversation-1"
    tasks = planner.calls[0][2]["tasks"]
    assert len(tasks) == result.recommended_agents
    assert all(task.metadata["requires_ephemeral"] for task in tasks)
    assert swarms.provisioned == ["swarm-1"]


def test_explicit_models_are_assigned_to_specialist_tasks(tmp_path):
    value, _, _, planner, _ = runtime(tmp_path)
    interaction = prepare(value, "Use um Swarm com modelos Qwen e DeepSeek")
    assert interaction.status == "accepted"
    result = value.execute_accepted(interaction.request_id)
    tasks = planner.calls[0][2]["tasks"]
    assert result.recommended_agents == 2
    assert [task.metadata["model"] for task in tasks] == ["Qwen", "DeepSeek"]


def test_each_explicit_model_receives_an_agent_even_when_count_is_lower(tmp_path):
    value, _, _, planner, _ = runtime(tmp_path)
    interaction = prepare(value, "Crie 1 agente para o Swarm com modelos Qwen e DeepSeek")
    assert interaction.status == "pending"
    assert interaction.requested_agents == 1
    assert interaction.recommended_agents == 2

    result = value.resolve(interaction.request_id, "keep_requested")
    tasks = planner.calls[0][2]["tasks"]
    assert result.recommended_agents == 2
    assert [task.metadata["model"] for task in tasks] == ["Qwen", "DeepSeek"]


def test_cancelled_confirmation_cannot_be_replayed(tmp_path):
    value, _, missions, _, swarms = runtime(tmp_path)
    interaction = prepare(value, "Use um Swarm com 99 agentes")
    result = value.resolve(interaction.request_id, "cancel")
    assert result.status == "cancelled"
    with pytest.raises(ValidationError):
        value.resolve(interaction.request_id, "accept_recommended")
    assert missions.created == []
    assert swarms.created == []


def test_partial_failure_is_persisted_and_not_retried(tmp_path):
    value, _, missions, _, _ = runtime(tmp_path, swarms=Swarms(fail=True))
    interaction = prepare(value, "Use um Swarm com 2 agentes")
    assert interaction.status == "accepted"
    with pytest.raises(RuntimeError, match="provision failed"):
        value.execute_accepted(interaction.request_id)
    failed = value.get(interaction.request_id)
    assert failed.status == "failed"
    assert failed.mission_id == "mission-1"
    assert failed.swarm_id == "swarm-1"
    assert len(missions.created) == 1
    with pytest.raises(ValidationError):
        value.execute_accepted(interaction.request_id)
    assert len(missions.created) == 1


def test_idempotent_retry_reuses_interaction_without_duplicate_swarm(tmp_path):
    value, _, missions, _, swarms = runtime(tmp_path)
    first = prepare(value, "Use um Swarm com 2 agentes", idempotency_key="turn-1")
    repeated = prepare(value, "Use um Swarm com 2 agentes", idempotency_key="turn-1")
    assert repeated.request_id == first.request_id

    value.execute_accepted(first.request_id)
    completed = prepare(value, "Use um Swarm com 2 agentes", idempotency_key="turn-1")
    assert completed.status == "completed"
    assert len(missions.created) == 1
    assert len(swarms.created) == 1


def test_conversation_has_only_one_pending_confirmation(tmp_path):
    value, _, missions, _, _ = runtime(tmp_path)
    first = prepare(value, "Use um Swarm com 99 agentes para analisar")
    repeated = prepare(value, "Use um Swarm para documentar")
    assert repeated.request_id == first.request_id
    assert repeated.task == first.task
    assert missions.created == []
