from synapse.models.adapters import OpenAICompatibleAdapter
from synapse.models.types import ModelRequest


def test_local_tool_turn_has_native_receipt_and_bounded_reasoning():
    request = ModelRequest(agent_id="worker", provider="openai_compatible", model="local",
        user_message="Inspect the file", tools=[{"name": "read_file"}],
        metadata={"synapse_local_server": "http://127.0.0.1:1234"},
        context={"tool_execution_results": [{"request": {"id": "read-1", "name": "read_file",
            "arguments": {"path": "app.py"}}, "success": True, "status": "executed",
            "result": {"content": "answer = 41"}}]})
    payload = OpenAICompatibleAdapter._payload(request, stream=False)
    assert payload["messages"][-2]["tool_calls"][0]["id"] == "read-1"
    assert payload["messages"][-1]["role"] == "tool"
    assert "answer = 41" in payload["messages"][-1]["content"]
    assert payload["reasoning_budget"] == 0
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}


def test_remote_provider_does_not_receive_local_engine_options():
    request = ModelRequest(agent_id="worker", provider="openai_compatible", model="remote",
                           user_message="Hello", context={}, tools=[{"name": "read_file"}])
    payload = OpenAICompatibleAdapter._payload(request, stream=False)
    assert "reasoning_budget" not in payload
    assert "chat_template_kwargs" not in payload
