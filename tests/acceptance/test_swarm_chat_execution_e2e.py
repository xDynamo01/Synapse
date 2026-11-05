from types import SimpleNamespace

import pytest

from synapse.core.serialization import dump_structured_file
from synapse.models.types import ModelResponse
from synapse.tools.calls import ToolCallRequest

from .agent_kinds_support import provision, runtime_at


def chat_runtime(tmp_path):
    runtime = runtime_at(tmp_path / "data", clean=True)
    provision(runtime, "central")
    dump_structured_file(runtime.data_dir.resolve("config/permissions.yaml"), {
        "subjects": {"user:local_owner": ["*"], "local_owner": ["*"],
                     "agent:central": ["filesystem.read", "agents.message"]}})
    runtime.permissions.subjects["agent:central"] = {"filesystem.read", "agents.message"}
    runtime.primary_agent.set_primary(runtime.context(), "central")
    runtime.ephemeral_agents.model_capability = SimpleNamespace(
        recommend_route=lambda *args: SimpleNamespace(
            provider_id="mock", model_id="synapse-test", status="recommended",
            reason="test inference", estimated_ram_gb=0, estimated_vram_gb=0))
    return runtime


def test_chat_creates_executes_verifies_and_retires_temporary_agents(tmp_path, monkeypatch):
    runtime = chat_runtime(tmp_path)
    seen = []

    def generate(**kwargs):
        seen.append(kwargs)
        return ModelResponse(content="1. Organizar mesa\n2. Revisar agenda", provider="mock", model="synapse-test")

    monkeypatch.setattr(runtime.models, "generate", generate)
    assert runtime.worker_registry.list() == []
    result = runtime.chat.submit_turn(runtime.context(), content="Faça um swarm para criar uma to-do list básica",
                                      target_agent_id="central", idempotency_key="todo")
    assert len(seen) == 2
    assert all(item["context"]["agent_id"].startswith("ephemeral:") for item in seen)
    assert all(item["context"]["memory"] == [] and item["tools"] == [] for item in seen)
    assert all("faça um swarm" not in item["user_message"].lower() for item in seen)
    mission = runtime.missions.list_missions()[0]
    assert mission.status == "completed"
    assert all(item.state.value == "destroyed" for item in runtime.ephemeral_agents.list())
    assert all(item.status == "unavailable" for item in runtime.worker_registry.list())
    assert all(item.verification_result["status"] == "passed" for item in runtime.attempts.list())
    assert "Organizar mesa" in result.response
    assert len(runtime.agents.list_agents()) == 1


def test_failed_inference_cleans_up_workforce_and_does_not_claim_completion(tmp_path, monkeypatch):
    runtime = chat_runtime(tmp_path)

    def fail(**kwargs):
        raise RuntimeError("inference unavailable")

    monkeypatch.setattr(runtime.models, "generate", fail)
    with pytest.raises(Exception, match="inference unavailable"):
        runtime.chat.submit_turn(runtime.context(), content="Faça um swarm para criar uma lista",
                                 target_agent_id="central")
    assert runtime.swarm.list()[0].status == "failed"
    assert all(item.state.value == "destroyed" for item in runtime.ephemeral_agents.list())
    assert all(item.status == "unavailable" for item in runtime.worker_registry.list())


def test_provisioning_failure_rolls_back_partial_workforce(tmp_path, monkeypatch):
    runtime = chat_runtime(tmp_path)
    original = runtime.ephemeral_agents.create_instance
    calls = 0
    def create(spec, *, authority):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("resource capacity exhausted")
        return original(spec, authority=authority)
    monkeypatch.setattr(runtime.ephemeral_agents, "create_instance", create)
    with pytest.raises(RuntimeError, match="capacity exhausted"):
        runtime.chat.submit_turn(runtime.context(), content="Faça um swarm para criar uma lista",
                                 target_agent_id="central")
    assert all(item.state.value == "destroyed" for item in runtime.ephemeral_agents.list())
    assert all(item.status == "unavailable" for item in runtime.worker_registry.list())
    assert runtime.attempts.list() == []


def test_unverified_output_never_completes_ephemeral_agent(tmp_path, monkeypatch):
    runtime = chat_runtime(tmp_path)
    monkeypatch.setattr(runtime.models, "generate", lambda **kwargs: ModelResponse(
        content="", provider="mock", model="synapse-test"))
    with pytest.raises(Exception, match="verification failed"):
        runtime.chat.submit_turn(runtime.context(), content="Faça um swarm para criar uma lista",
                                 target_agent_id="central")
    assert all(item.status == "failed" for item in runtime.attempts.list())
    assert all(item.result_reference is None for item in runtime.ephemeral_agents.list())


def test_single_concurrent_slot_drains_all_tasks(tmp_path, monkeypatch):
    runtime = chat_runtime(tmp_path)
    runtime.workforce_planner.resource_pressure.capacity.recommended_concurrency = 1
    monkeypatch.setattr(runtime.models, "generate", lambda **kwargs: ModelResponse(
        content="Lista concluída", provider="mock", model="synapse-test"))
    result = runtime.chat.submit_turn(runtime.context(), content="Faça um swarm para criar uma lista",
                                     target_agent_id="central")
    assert "Lista concluída" in result.response
    assert len(runtime.attempts.list()) == 2
    assert runtime.missions.list_missions()[0].status == "completed"


def test_text_only_swarm_does_not_require_parent_filesystem_permissions(tmp_path, monkeypatch):
    runtime = chat_runtime(tmp_path)
    runtime.permissions.subjects["agent:central"] = set()
    monkeypatch.setattr(runtime.models, "generate", lambda **kwargs: ModelResponse(
        content="Lista concluída", provider="mock", model="synapse-test"))
    runtime.chat.submit_turn(runtime.context(), content="Faça um swarm para criar uma lista",
                             target_agent_id="central")
    assert runtime.missions.list_missions()[0].status == "completed"


def test_out_of_scope_tool_call_cannot_be_hidden_by_a_text_response(tmp_path, monkeypatch):
    runtime = chat_runtime(tmp_path)
    monkeypatch.setattr(runtime.models, "generate", lambda **kwargs: ModelResponse(
        content="Pretend success", provider="mock", model="synapse-test",
        tool_calls=[ToolCallRequest("filesystem.write", {"path": "outside.txt", "content": "bad"})]))
    with pytest.raises(RuntimeError, match="tool_execution_failed"):
        runtime.chat.submit_turn(runtime.context(), content="Faça um swarm para criar uma lista",
                                 target_agent_id="central")
    assert all(item.status == "failed" for item in runtime.attempts.list())
    assert all(item.result_reference is None for item in runtime.ephemeral_agents.list())
