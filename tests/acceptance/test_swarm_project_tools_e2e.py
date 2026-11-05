from dataclasses import asdict

import pytest

from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.models.types import ModelResponse
from synapse.tools.calls import ToolCallRequest

from .test_swarm_chat_execution_e2e import chat_runtime


def project_runtime(tmp_path):
    runtime = chat_runtime(tmp_path)
    config_path = runtime.data_dir.resolve("agents/central/CONFIG.yaml")
    config = load_structured_file(config_path)
    config.update(role="primary_agent", permissions=[], preferred_tools=[], allowed_tools=[])
    dump_structured_file(config_path, config)
    dump_structured_file(runtime.data_dir.resolve("config/filesystem_tools.yaml"), {"allowed_roots": [str(tmp_path)]})
    project = tmp_path / "sample-project"
    project.mkdir()
    source = project / "app.py"
    source.write_text("answer = 41\n", encoding="utf-8")
    return runtime, project, source


def test_project_refusal_with_zero_tool_calls_cannot_complete(tmp_path, monkeypatch):
    runtime, project, source = project_runtime(tmp_path)
    monkeypatch.setattr(runtime.models, "generate", lambda **kwargs: ModelResponse(
        content="Não tenho acesso ao sistema de arquivos. Cole o código aqui.", provider="mock", model="test"))
    with pytest.raises(Exception, match="verification failed"):
        runtime.chat.submit_turn(runtime.context(), content=f"faça um swarm, analise e concerte esse projeto {project}", target_agent_id="central")
    assert runtime.swarm.list()[0].status == "failed"
    assert runtime.missions.list_missions()[0].status != "completed"
    assert source.read_text(encoding="utf-8") == "answer = 41\n"
    assert not any(item.result_reference for item in runtime.ephemeral_agents.list())


@pytest.mark.parametrize("recover", [True, False])
def test_listing_only_gets_bounded_verification_feedback(tmp_path, monkeypatch, recover):
    runtime, project, source = project_runtime(tmp_path)
    requests = []

    def generate(**kwargs):
        requests.append(kwargs)
        receipts = kwargs["context"].get("tool_execution_results", [])
        if not receipts:
            return ModelResponse(content="", provider="mock", model="test", tool_calls=[
                ToolCallRequest("list_directory", {"path": str(project)})])
        if (recover and "verifier rejected" in kwargs["user_message"]
                and not any(item["request"]["name"] == "read_file" for item in receipts)):
            return ModelResponse(content="", provider="mock", model="test", tool_calls=[
                ToolCallRequest("read_file", {"path": str(source)})])
        return ModelResponse(content="Inspeção concluída.", provider="mock", model="test")

    monkeypatch.setattr(runtime.models, "generate", generate)
    command = f"faça um swarm para analisar o projeto {project}"
    if recover:
        result = runtime.chat.submit_turn(runtime.context(), content=command, target_agent_id="central")
        assert result.command["request"]["execution_status"] == "completed"
        assert all(attempt.verification_result["status"] == "passed" for attempt in runtime.attempts.list())
    else:
        with pytest.raises(Exception, match="verification failed"):
            runtime.chat.submit_turn(runtime.context(), content=command, target_agent_id="central")
        assert runtime.swarm.list()[0].status == "failed"
        assert len(requests) == 6
        assert sum("verifier rejected" in request["user_message"] for request in requests) == 2
    assert any("verifier rejected" in request["user_message"] for request in requests)


@pytest.mark.parametrize("cancel_before_approval", [False, True])
@pytest.mark.parametrize("agent_count", [2, 4])
def test_project_read_then_approved_edit_then_readback_completes(tmp_path, monkeypatch, cancel_before_approval, agent_count):
    runtime, project, source = project_runtime(tmp_path)
    seen = []

    def generate(**kwargs):
        tools = {item["name"] for item in kwargs["tools"]}
        assert "read_file" in tools
        receipts = kwargs["context"].get("tool_execution_results", [])
        seen.append((tools, receipts))
        repair = "apply the requested repair" in kwargs["user_message"]
        names = [item["request"]["name"] for item in receipts]
        if not names:
            call = ToolCallRequest("list_directory", {"path": str(project)})
        elif names[-1] == "list_directory" or names[-1] == "edit_file":
            call = ToolCallRequest("read_file", {"path": str(source)})
        elif repair and "edit_file" not in names:
            assert "edit_file" in tools
            call = ToolCallRequest("edit_file", {"path": str(source), "old_text": "41", "new_text": "42"})
        else:
            return ModelResponse(content="Nenhuma alteração foi necessária." if repair else "Li o arquivo; a resposta está incorreta.", provider="mock", model="test")
        return ModelResponse(content="", provider="mock", model="test", tool_calls=[call])

    monkeypatch.setattr(runtime.models, "generate", generate)
    command = (f"esse projeto {project} , tem varios erros, ele nao converte nada, "
               f"faça um swarm com {agent_count} agentes para consertar esse projeto, utilize os modelos "
               "mais recomendados para cada açao, use o modo economico para nao sobrecarregar o sistema")
    result = runtime.chat.submit_turn(runtime.context(), content=command, target_agent_id="central")
    interaction = result.command["request"]
    assert interaction["status"] == "waiting_approval", interaction
    assert interaction["execution_status"] != "completed"
    assert source.read_text(encoding="utf-8") == "answer = 41\n"
    assert "ainda não foi concluída" in result.response
    instances = runtime.ephemeral_agents.list()
    assert len(instances) == agent_count
    assert not interaction["explicit_models"]
    assert all("read_file" in instance.tool_scope for instance in instances)
    assert any("edit_file" in instance.tool_scope for instance in instances)
    approval_id = interaction["approval_ids"][0]
    if cancel_before_approval:
        runtime.missions.cancel(interaction["mission_id"])
        with pytest.raises(Exception, match="no longer executable"):
            runtime.approval_resume.approve_and_resume(runtime.context(), approval_id)
        assert source.read_text(encoding="utf-8") == "answer = 41\n"
        return
    _, receipt = runtime.approval_resume.approve_and_resume(runtime.context(), approval_id)
    assert receipt.success, asdict(receipt)
    assert source.read_text(encoding="utf-8") == "answer = 42\n"
    swarm = runtime.swarm.get(interaction["swarm_id"])
    assert swarm.status == "completed", swarm
    finished = runtime.chat.swarm_interactions.get(interaction["request_id"])
    assert finished.status == "completed"
    assert not finished.approval_ids
    assert "Edição aplicada" in "\n".join(finished.outputs)
    assert "Nenhuma alteração foi necessária" not in "\n".join(finished.outputs)
    attempts = runtime.attempts.list(mission_id=interaction["mission_id"])
    assert all(attempt.verification_result["status"] == "passed" for attempt in attempts)
    assert all(item.state.value == "destroyed" for item in runtime.ephemeral_agents.list())
    assert sum(item["request"]["name"] == "edit_file" for attempt in attempts for item in [e["value"] for e in attempt.result["evidence"]]) == 1

    replay = runtime.approval_resume.resume(runtime.context(), approval_id)
    assert not replay.success
    assert source.read_text(encoding="utf-8") == "answer = 42\n"
