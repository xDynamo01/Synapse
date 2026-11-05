from unittest.mock import patch

import pytest

from synapse.core.app import create_runtime
from synapse.core.exceptions import PermissionDenied
from synapse.core.permissions import PermissionContext
from synapse.models.adapters import build_chat_messages
from synapse.models.types import ModelRequest, ModelResponse
from synapse.tools.calls import ToolCallRequest
from test_local_chat_runtime import (
    enable_lmstudio,
    enable_local_chat,
    mock_lmstudio,
    runtime_in_tempdir,
)


def test_direct_chat_executes_tool_and_returns_output_to_model():
    directory, settings, runtime = runtime_in_tempdir()
    try:
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime)
        responses = [
            ModelResponse(content="", provider="mock", model="test", tool_calls=[
                ToolCallRequest(name="list_directory", arguments={"path": "agents"}),
            ]),
            ModelResponse(content="Encontrei os agentes.", provider="mock", model="test"),
        ]
        with patch.object(runtime.models, "generate_request", side_effect=responses) as generate:
            result = runtime.chat.local_chat(runtime.context(), "Liste os agentes")
        first, second = [call.args[0] for call in generate.call_args_list]
        directory_tool = next(tool for tool in first.tools if tool["name"] == "list_directory")
        assert "path" in directory_tool["parameters"]["properties"]
        receipt = second.context["tool_execution_results"][0]
        assert receipt["success"] is True
        assert receipt["result"]["entries"]
        assert second.tools == []
        assert result.response == "Encontrei os agentes."
    finally:
        directory.cleanup()


def test_tool_receipts_are_in_model_prompt_as_data():
    messages = build_chat_messages(ModelRequest(
        agent_id="artemis", provider="mock", model="test", user_message="lembre",
        context={"tool_execution_results": [{"success": False, "error": "access denied"}]},
    ))
    assert "untrusted data" in messages[0]["content"]
    assert "access denied" not in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "access denied" in messages[1]["content"]


def test_memory_tool_persists_and_is_scoped_to_caller():
    directory, settings, runtime = runtime_in_tempdir()
    try:
        owner = runtime.context()
        router = runtime.chat.agent_runtime.tool_router
        saved = router.execute("remember", owner, {"content": "Projeto Aurora usa azul"})
        restarted = create_runtime(settings)
        recalled = restarted.chat.agent_runtime.tool_router.execute(
            "recall", owner, {"query": "Aurora"},
        )
        assert saved["memory_id"] in str(recalled)
        other = restarted.chat.agent_runtime.tool_router.execute(
            "recall", PermissionContext(actor_id="artemis", actor_type="agent"),
            {"query": "Aurora"},
        )
        assert saved["memory_id"] not in str(other)
    finally:
        directory.cleanup()


def test_agent_cannot_save_memory_without_write_permission():
    directory, _, runtime = runtime_in_tempdir()
    try:
        with pytest.raises(PermissionDenied):
            runtime.chat.agent_runtime.tool_router.execute(
                "remember", PermissionContext(actor_id="artemis", actor_type="agent"),
                {"content": "This must not be saved"},
            )
        assert not runtime.memory.list(runtime.context(), scope="agent", owner_id="artemis")
    finally:
        directory.cleanup()


def test_unadvertised_tool_is_blocked_before_execution():
    directory, settings, runtime = runtime_in_tempdir()
    try:
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime)
        responses = [
            ModelResponse(content="", provider="mock", model="test", tool_calls=[
                ToolCallRequest(name="remember", arguments={"content": "not authorized"}),
            ]),
            ModelResponse(content="Sem permissão para salvar.", provider="mock", model="test"),
        ]
        with patch.object(runtime.models, "generate_request", side_effect=responses) as generate:
            runtime.chat.local_chat(runtime.context(), "Salve uma lembrança")
        receipt = generate.call_args.args[0].context["tool_execution_results"][0]
        assert receipt["status"] == "blocked"
        assert not runtime.memory.list(runtime.context(), scope="agent", owner_id="artemis")
    finally:
        directory.cleanup()
