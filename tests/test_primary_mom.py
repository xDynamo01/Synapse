import json
from dataclasses import asdict
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError as PayloadError

from acceptance.agent_kinds_support import runtime_at
from synapse.api.routes import router
from synapse.core.app import create_runtime
from synapse.core.exceptions import PermissionDenied, ValidationError
from synapse.models.adapters import build_chat_messages
from synapse.models.types import ModelResponse
from synapse.mom.contracts import Operation, Route
from synapse.mom.selection import classify_operation
from synapse.storage.errors import StorageCorrupted, StorageRevisionConflict
from test_frontend_v2_boundary import client_for, create_ready_primary
from test_local_chat_runtime import runtime_in_tempdir


@pytest.fixture
def setup():
    directory, settings, runtime = runtime_in_tempdir()
    runtime.primary_agent.set_primary(runtime.context(), "artemis")
    try:
        yield settings, runtime
    finally:
        directory.cleanup()


def routes():
    return (Route(operation=Operation.CODING, provider="mock", model="code-model"),
            Route(operation=Operation.REVIEW, provider="mock", model="review-model"))


@pytest.mark.parametrize(("message", "operation"), [
    ("Oi, como você está?", Operation.CONVERSATION),
    ("Escreva uma função Python para ordenar nomes", Operation.CODING),
    ("Resuma este código\n\n```python print(1)```", Operation.SUMMARY),
    ("Revise este código", Operation.REVIEW),
    ("Compare as estratégias", Operation.REASONING),
    ("Olá\n\nresuma codigo plano", Operation.CONVERSATION),
    ("Review this implementation", Operation.REVIEW),
    ("Calculate the total", Operation.REASONING),
])
def test_local_intent_routing(message, operation):
    assert classify_operation(message) == operation


def test_primary_chat_keeps_generalist_for_conversation_and_specialist_context(setup):
    _, runtime = setup
    context = runtime.context()
    configured = routes() + (Route(operation=Operation.CONVERSATION, provider="mock", model="dialogue-model"),)
    runtime.mom.configure(context, "default", True, configured, 0)
    runtime.memory.response_style(context, "Não use emojis")
    with patch.object(runtime.models, "generate_request", wraps=runtime.models.generate_request) as generate:
        first = runtime.chat.submit_turn(context, content="Oi, meu nome é Lia", target_agent_id="artemis",
                                         model_provider_id="mock", model_name="generalist")
        second = runtime.chat.submit_turn(context, content="Escreva uma função Python", target_agent_id="artemis",
                                          conversation_id=first.session_id)
    assert first.model["model"] == "generalist"
    assert "mom" not in first.model
    assert generate.call_count == 2
    assert second.model["model"] == "code-model"
    assert second.model["mom"]["operation"] == "coding"
    request = generate.call_args_list[-1].args[0]
    messages = str(build_chat_messages(request))
    assert "Lia" in messages
    assert "Não use emojis" in messages
    assert request.agent_id == "artemis"


def test_direct_chat_routes_before_legacy_model_resolution(setup):
    _, runtime = setup
    runtime.mom.configure(runtime.context(), "default", True, routes(), 0)
    with patch.object(runtime.chat, "_resolve_local_chat_model", side_effect=AssertionError("legacy routing used")):
        result = runtime.chat.local_chat(runtime.context(), "Crie uma função Python")
    assert result.model["model"] == "code-model"
    assert result.model["mom"]["operation"] == "coding"


def test_chat_missing_route_never_falls_back_and_worker_is_unchanged(setup):
    _, runtime = setup
    runtime.mom.configure(runtime.context(), "default", True, routes(), 0)
    with patch.object(runtime.models, "generate_request") as generate:
        with pytest.raises(ValidationError, match="Settings > MoM"):
            runtime.chat.send_message(runtime.context(), "artemis", "Resuma o texto")
        generate.assert_not_called()
    worker = runtime.chat.send_message(runtime.context(), "researcher", "Escreva código")
    assert worker.model["model"] == "synapse-test"
    assert "mom" not in worker.model


def test_legacy_enabled_flag_does_not_disable_permanent_chat_routing(setup):
    settings, runtime = setup
    context = runtime.context()
    runtime.mom.configure(context, "default", True, routes(), 0)
    original = runtime.models.generate_request

    def disable_and_generate(request):
        runtime.mom.configure(context, "default", False, routes(), 1)
        return original(request)

    with patch.object(runtime.models, "generate_request", side_effect=disable_and_generate):
        result = runtime.chat.submit_turn(context, content="Escreva código Python", target_agent_id="artemis")
    assert result.model["model"] == "code-model"
    restarted = create_runtime(settings)
    assert not restarted.mom.get_configuration(context).enabled
    result = restarted.chat.submit_turn(context, content="Escreva código Python", target_agent_id="artemis")
    assert result.model["model"] == "code-model"
    assert result.model["mom"]["operation"] == "coding"


def test_frontend_turn_and_stream_use_saved_mom_routes_after_restart(tmp_path):
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    runtime.mom.configure(runtime.context(), "default", True, routes(), 0)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    assert opened.status_code == 200, opened.text
    conversation_id = opened.json()["conversation"]["conversation_id"]
    turn = client.post(f"/api/frontend/conversations/{conversation_id}/turns", json={
        "content": "Escreva um script Python", "workspace_id": "default",
        "model_provider_id": "obsolete", "model_name": "obsolete",
    })
    assert turn.status_code == 404, turn.text  # Explicit manual selection is never silently replaced.
    turn = client.post(f"/api/frontend/conversations/{conversation_id}/turns", json={
        "content": "Escreva um script Python", "workspace_id": "default",
    })
    assert turn.status_code == 200, turn.text
    assert turn.json()["result"]["model"]["model"] == "code-model"
    restarted = runtime_at(tmp_path / "data")
    restarted_client = client_for(restarted)
    with patch.object(restarted.models, "generate_request", wraps=restarted.models.generate_request) as generate:
        stream = restarted_client.post(f"/api/frontend/conversations/{conversation_id}/turns/stream", json={
            "content": "Revise o código", "workspace_id": "default",
        })
    assert stream.status_code == 200, stream.text
    events = [json.loads(line) for line in stream.text.splitlines()]
    assert events[-1]["type"] == "generation_completed", stream.text
    # The stream envelope does not expose model metadata; inspect the request
    # admitted by the canonical router rather than changing the stream contract.
    assert generate.call_args.args[0].model == "review-model"


def test_frontend_uses_saved_generalist_with_mom_on_and_off(tmp_path):
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    saved = client.post("/api/models/default", json={"default_provider": "mock", "default_chat_model": "generalist"})
    assert saved.status_code == 200, saved.text
    runtime.mom.configure(runtime.context(), "default", True, routes(), 0)
    restarted = runtime_at(tmp_path / "data")
    client = client_for(restarted)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    conversation_id = opened.json()["conversation"]["conversation_id"]
    for message in ("Oi", "Escreva código Python"):
        if message != "Oi":
            restarted.mom.configure(restarted.context(), "default", False, routes(), 1)
        turn = client.post(f"/api/frontend/conversations/{conversation_id}/turns", json={"content": message})
        assert turn.status_code == 200, turn.text
        assert turn.json()["result"]["model"]["model"] == ("generalist" if message == "Oi" else "code-model")


def test_primary_routes_by_operation_and_retains_identity_after_restart(setup):
    settings, runtime = setup
    context = runtime.context()
    primary_before = asdict(runtime.agents.get("artemis"))
    worker_before = asdict(runtime.agents.get("researcher"))
    assert not runtime.mom.get_configuration(context).enabled
    runtime.memory.response_style(context, "Não use emojis")
    config = runtime.mom.configure(context, "default", True, routes(), 0)
    assert config.revision == 1
    restarted = create_runtime(settings)
    assert restarted.mom.get_configuration(context) == config
    with patch.object(restarted.models, "generate_request", wraps=restarted.models.generate_request) as generate:
        code = restarted.mom.execute(context, Operation.CODING, "Write hello world")
        review = restarted.mom.execute(context, Operation.REVIEW, "Review this answer")
    assert (code.model, review.model) == ("code-model", "review-model")
    assert code.operation_id != review.operation_id
    assert code.primary_agent_id == review.primary_agent_id == "artemis"
    for call in generate.call_args_list:
        request = call.args[0]
        assert request.agent_id == "artemis"
        assert request.tools == []
        messages = build_chat_messages(request)
        assert "Não use emojis" not in messages[0]["content"]
        assert "Não use emojis" in messages[-1]["content"]
    assert asdict(restarted.agents.get("artemis")) == primary_before
    assert asdict(restarted.agents.get("researcher")) == worker_before


def test_worker_cannot_access_mom_even_with_read_permission(setup):
    _, runtime = setup
    runtime.mom.configure(runtime.context(), "default", True, routes(), 0)
    worker = runtime.context("researcher", actor_type="agent")
    with patch.object(runtime.models, "generate_request") as generate:
        with pytest.raises(PermissionDenied):
            runtime.mom.execute(worker, Operation.CODING, "work")
        with pytest.raises(PermissionDenied):
            runtime.mom.get_configuration(worker)
        with pytest.raises(PermissionDenied):
            runtime.mom.configure(runtime.context("artemis", actor_type="agent"),
                                  "default", True, routes(), 1)
        generate.assert_not_called()


def test_primary_replacement_requires_explicit_rebinding(setup):
    _, runtime = setup
    context = runtime.context()
    runtime.mom.configure(context, "default", True, routes(), 0)
    runtime.primary_agent.replace_primary(context, "researcher")
    with pytest.raises(ValidationError, match="changed"):
        runtime.mom.execute(context, Operation.CODING, "work")
    config = runtime.mom.configure(context, "default", True, routes(), 1)
    assert config.primary_agent_id == "researcher"
    assert runtime.mom.execute(context, Operation.CODING, "work").primary_agent_id == "researcher"


def test_missing_disabled_routes_and_revision_conflict_fail_without_generation(setup):
    _, runtime = setup
    context = runtime.context()
    with patch.object(runtime.models, "generate_request") as generate:
        with pytest.raises(ValidationError, match="not enabled"):
            runtime.mom.execute(context, Operation.CODING, "work")
        runtime.mom.configure(context, "default", True, routes(), 0)
        with pytest.raises(StorageRevisionConflict):
            runtime.mom.configure(context, "default", True, routes(), 0)
        with pytest.raises(ValidationError, match="No Primary MoM route"):
            runtime.mom.execute(context, Operation.SUMMARY, "work")
        with pytest.raises(PayloadError):
            runtime.mom.configure(context, "default", True, (routes()[0], routes()[0]), 1)
        with pytest.raises(ValidationError, match="not registered"):
            runtime.mom.configure(context, "default", True,
                                  (Route(operation=Operation.CODING, provider="unknown", model="x"),), 1)
        generate.assert_not_called()


def test_activity_has_route_identity_without_prompt_or_answer(setup):
    _, runtime = setup
    context = runtime.context()
    runtime.mom.configure(context, "default", True, routes(), 0)
    events = []
    runtime.events.add_listener(events.append)
    runtime.mom.execute(context, Operation.REVIEW, "private input")
    with patch.object(runtime.models, "generate_request", side_effect=RuntimeError("private failure")):
        with pytest.raises(RuntimeError):
            runtime.mom.execute(context, Operation.CODING, "private input")
    activity = [event for event in events if event.type.startswith("mom.operation.")]
    assert [event.type.rsplit(".", 1)[-1] for event in activity] == ["started", "completed", "started", "failed"]
    assert all(event.payload["agent_id"] == "artemis" for event in activity)
    assert all("private" not in str(event.payload) for event in activity)


def test_api_configuration_and_operation_cannot_target_worker(setup):
    _, runtime = setup
    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        path = "/api/primary/mom/configuration"
        assert client.get(path).json()["enabled"] is False
        assert client.put(path, json={"enabled": True, "routes": [r.model_dump(mode="json") for r in routes()],
                                      "expected_revision": 0}).status_code == 200
        payload = {"operation": "coding", "message": "work"}
        result = client.post("/api/primary/mom/operations", json=payload)
        assert result.status_code == 200, result.text
        assert result.json()["primary_agent_id"] == "artemis"
        assert client.post("/api/primary/mom/operations", json={**payload, "agent_id": "researcher"}).status_code == 422
        assert client.post("/api/primary/mom/operations", json=payload,
                           headers={"X-Actor-Id": "researcher", "X-Actor-Type": "agent"}).status_code == 403


def test_route_mismatch_is_failure_not_success(setup):
    _, runtime = setup
    runtime.mom.configure(runtime.context(), "default", True, routes(), 0)
    with patch.object(runtime.models, "generate_request",
                      return_value=ModelResponse(content="wrong", provider="mock", model="other-model")):
        with pytest.raises(ValidationError, match="did not match"):
            runtime.mom.execute(runtime.context(), Operation.CODING, "work")


def test_corrupt_configuration_fails_closed_without_fallback(setup):
    settings, runtime = setup
    runtime.mom.configure(runtime.context(), "default", True, routes(), 0)
    path = settings.data_dir / "mom/configurations/default.yaml"
    path.write_text("payload: [unterminated", encoding="utf-8")
    with patch.object(runtime.models, "generate_request") as generate:
        with pytest.raises(StorageCorrupted):
            runtime.mom.execute(runtime.context(), Operation.CODING, "work")
        generate.assert_not_called()


def test_primary_can_execute_but_paused_primary_cannot(setup):
    _, runtime = setup
    runtime.mom.configure(runtime.context(), "default", True, routes(), 0)
    primary = runtime.context("artemis", actor_type="agent")
    assert runtime.mom.execute(primary, Operation.CODING, "work").primary_agent_id == "artemis"
    runtime.primary_agent.pause_interaction(runtime.context())
    with patch.object(runtime.models, "generate_request") as generate:
        with pytest.raises(ValidationError, match="active"):
            runtime.mom.execute(primary, Operation.CODING, "work")
        generate.assert_not_called()
