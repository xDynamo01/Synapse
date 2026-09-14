from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import time
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acceptance.agent_kinds_support import runtime_at
from synapse.api.routers.frontend_boundary import validate_frontend_attachment_metadata
from synapse.api.routes import router
from synapse.audio.models import TextToSpeechResult, TranscriptResult
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import load_structured_file
from synapse.model_hub.models import ModelCatalogEntry, ModelProviderInfo


def client_for(runtime) -> TestClient:
    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(router, prefix="/api")
    return TestClient(app)


def install_frontend_test_model(runtime, *, provider: str = "mock", model: str = "synapse-test"):
    provider_info = ModelProviderInfo(
        provider_id=provider,
        display_name=provider.title(),
        status="available",
        endpoint=None,
        active=True,
        default_model=model,
        model_count=1,
        last_refreshed_at="2026-08-21T00:00:00+00:00",
    )
    model_info = ModelCatalogEntry(
        id=f"{provider}:{model}",
        name=model,
        provider=provider,
        runtime=provider,
        origin="test",
        type="chat",
        availability_state="configured/test",
        chat_usable=True,
        status="available",
        is_default=True,
    )
    runtime.model_hub.list_providers = lambda: [provider_info]
    runtime.model_hub.list_catalog = lambda: [model_info]
    runtime.model_hub.update_defaults(default_provider=provider, default_chat_model=model)
    return {"provider": provider, "model": model}


def create_ready_primary(client: TestClient, runtime) -> dict:
    selection = install_frontend_test_model(runtime)
    response = client.post(
        "/api/frontend/first-agent",
        json={
            "agent_id": "synapse",
            "display_name": "Synapse",
            "role": "primary_agent",
            "default_provider": selection["provider"],
            "default_model": selection["model"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def valid_wav_base64() -> str:
    output = io.BytesIO()
    sample_rate = 16_000
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for index in range(int(sample_rate * 0.12)):
            sample = int(math.sin(2 * math.pi * 440 * index / sample_rate) * 8000)
            frames.extend(sample.to_bytes(2, "little", signed=True))
        wav_file.writeframes(bytes(frames))
    return base64.b64encode(output.getvalue()).decode("ascii")


def test_settings_personality_persists_without_changing_agent_identity(tmp_path):
    runtime = runtime_at(tmp_path)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    before = client.get("/api/agents/synapse").json()
    result = client.patch("/api/agents/synapse", json={
        "display_name": "Aurora", "system_prompt": "Responda em português, com clareza e sem emojis."
    })
    assert result.status_code == 200, result.text
    assert result.json()["updated"] is True
    restarted = client_for(runtime_at(tmp_path))
    after = restarted.get("/api/agents/synapse").json()
    assert after["display_name"] == "Aurora"
    assert after["system_prompt"] == "Responda em português, com clareza e sem emojis."
    assert after["agent_id"] == before["agent_id"]
    assert after["preferred_model"] == before["preferred_model"]
    soul = runtime.data_dir.resolve("agents/synapse/SOUL.md").read_text(encoding="utf-8")
    assert "Aurora" in soul
    assert after["system_prompt"] in soul


def test_settings_voice_preview_uses_requested_voice_and_returns_audio(tmp_path):
    runtime = runtime_at(tmp_path)
    client = client_for(runtime)
    with patch.object(runtime.audio, "synthesize", return_value=TextToSpeechResult(
        output_ref="inline://tts/preview", audio_base64=valid_wav_base64(), audio_format="audio/wav"
    )) as synthesize:
        response = client.post("/api/audio/synthesize", json={
            "text": "Eu sou Aurora.", "provider_id": "piper", "voice_id": "pt_BR-cadu-medium", "language": "pt-BR"
        })
    assert response.status_code == 200, response.text
    assert response.json()["audio_base64"]
    assert synthesize.call_args.args[0].voice_id == "pt_BR-cadu-medium"
    assert synthesize.call_args.args[0].text == "Eu sou Aurora."


class ControlledTtsAdapter:
    def synthesize(self, request) -> TextToSpeechResult:
        return TextToSpeechResult(
            output_ref=f"controlled://tts/{request.session_id}",
            provider_id=request.provider_id or "mock_tts",
            voice_id=request.voice_id,
            audio_base64=valid_wav_base64(),
            audio_format="audio/wav",
            duration_ms=120,
            metadata={"controlled": True},
        )


class RepeatedEchoSttAdapter:
    def transcribe(self, request) -> TranscriptResult:
        return TranscriptResult(
            text=(
                "O que é o que é o que é o que é o que é o que é "
                "o que é o que é o que é o que é o que é"
            ),
            status="success",
            language=request.language or "pt-BR",
            provider_id=request.provider_id or "mock_stt_adapter",
        )


class LowConfidenceSttAdapter:
    def transcribe(self, request) -> TranscriptResult:
        return TranscriptResult(
            text="Ainda não é a gente.", confidence=0.10407962094303848,
            status="success", language="pt-BR",
            provider_id=request.provider_id or "mock_stt_adapter",
        )


class ProjectRetrievalSttAdapter:
    def transcribe(self, request) -> TranscriptResult:
        return TranscriptResult(
            text="pesquise nos arquivos desse projeto onde definimos fencing",
            status="success",
            language=request.language or "pt-BR",
            provider_id=request.provider_id or "mock_stt_adapter",
        )


def test_no_agent_requires_onboarding_and_lists_provider_model_options(tmp_path: Path) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    install_frontend_test_model(runtime)
    client = client_for(runtime)

    response = client.get("/api/frontend/bootstrap")

    assert response.status_code == 200
    payload = response.json()
    assert payload["onboarding_required"] is True
    assert payload["usable_primary_agent"] is False
    assert payload["primary_agent_state"] == "primary_agent_required"
    assert payload["provider_model_options"][0]["provider_id"] == "mock"


def test_existing_usable_primary_agent_skips_onboarding_and_restart_restores(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    runtime = runtime_at(data_dir, clean=True)
    client = client_for(runtime)
    created = create_ready_primary(client, runtime)

    bootstrap = client.get("/api/frontend/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["onboarding_required"] is False
    conversation_id = created["primary_profile"]["conversation_id"]
    assert bootstrap.json()["conversation"]["conversation_id"] == conversation_id

    restarted = runtime_at(data_dir)
    install_frontend_test_model(restarted)
    restarted_client = client_for(restarted)
    restored = restarted_client.get("/api/frontend/bootstrap")

    assert restored.status_code == 200
    assert restored.json()["onboarding_required"] is False
    assert restored.json()["conversation"]["conversation_id"] == conversation_id


def test_create_first_agent_sets_usable_primary_and_rejects_invalid_model(
    tmp_path: Path,
) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    install_frontend_test_model(runtime)
    client = client_for(runtime)

    invalid = client.post(
        "/api/frontend/first-agent",
        json={
            "agent_id": "badmodel",
            "display_name": "Bad Model",
            "role": "primary_agent",
            "default_provider": "missing",
            "default_model": "missing-model",
        },
    )
    assert invalid.status_code == 422
    assert "invalid_model_selection" in invalid.text

    created = create_ready_primary(client, runtime)

    assert created["status"] == "ready"
    assert created["primary_profile"]["agent_id"] == "synapse"
    assert client.get("/api/frontend/bootstrap").json()["usable_primary_agent"] is True


def test_create_first_agent_enables_selected_lmstudio_provider(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    runtime = runtime_at(data_dir, clean=True)
    install_frontend_test_model(
        runtime,
        provider="lmstudio",
        model="local-release-model",
    )
    client = client_for(runtime)

    response = client.post(
        "/api/frontend/first-agent",
        json={
            "agent_id": "synapse",
            "display_name": "Synapse",
            "role": "primary_agent",
            "default_provider": "lmstudio",
            "default_model": "local-release-model",
        },
    )

    assert response.status_code == 200, response.text
    lmstudio_config = load_structured_file(data_dir / "config" / "lmstudio_provider.yaml")
    assert lmstudio_config["lmstudio"]["enabled"] is True
    assert lmstudio_config["lmstudio"]["default_model"] == "local-release-model"


def test_no_provider_model_options_is_recoverable_bootstrap_state(tmp_path: Path) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    runtime.model_hub.list_providers = lambda: []
    runtime.model_hub.list_catalog = lambda: []
    client = client_for(runtime)

    response = client.get("/api/frontend/bootstrap")

    assert response.status_code == 200
    payload = response.json()
    assert payload["onboarding_required"] is True
    assert payload["provider_model_options"] == []
    assert payload["degraded"][0]["code"] == "no_provider_model_options"


def test_first_agent_name_only_creates_primary_without_model(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    runtime.model_hub.list_providers = lambda: []
    runtime.model_hub.list_catalog = lambda: []
    client = client_for(runtime)

    response = client.post(
        "/api/frontend/first-agent",
        json={"agent_id": "synapse", "display_name": "Synapse", "workspace_id": "default"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["agent"]["preferred_model"] is None
    assert payload["degraded"][0]["code"] == "model_configuration_required"


def test_first_agent_name_only_uses_governed_default_model_not_first_option(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    provider = ModelProviderInfo(
        provider_id="lmstudio",
        display_name="LM Studio",
        status="available",
        endpoint="http://127.0.0.1:1234/v1",
        active=True,
        default_model="loaded-default",
        model_count=2,
        last_refreshed_at="2026-08-21T00:00:00+00:00",
    )
    runtime.model_hub.list_providers = lambda: [provider]
    runtime.model_hub.list_catalog = lambda: [
        ModelCatalogEntry(
            id="lmstudio:slow-agent-model",
            name="slow-agent-model",
            provider="lmstudio",
            runtime="lmstudio",
            origin="server",
            type="chat",
            availability_state="server/listed",
            chat_usable=True,
            status="available",
            is_default=False,
        ),
        ModelCatalogEntry(
            id="lmstudio:loaded-default",
            name="loaded-default",
            provider="lmstudio",
            runtime="lmstudio",
            origin="settings",
            type="chat",
            availability_state="configured/default",
            chat_usable=True,
            status="available",
            is_default=True,
        ),
    ]
    client = client_for(runtime)

    response = client.post(
        "/api/frontend/first-agent",
        json={"agent_id": "synapse", "display_name": "Synapse", "workspace_id": "default"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["agent"]["preferred_model"] == "lmstudio/loaded-default"


def test_text_conversation_send_stream_history_and_restart_restore(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    runtime = runtime_at(data_dir, clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)

    opened = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "project_id": "project-a", "session_id": "session-a"},
    )
    assert opened.status_code == 200, opened.text
    conversation_id = opened.json()["conversation"]["conversation_id"]

    turn = client.post(
        f"/api/frontend/conversations/{conversation_id}/turns",
        json={
            "content": "hello",
            "workspace_id": "default",
            "project_id": "project-a",
            "session_id": "session-a",
        },
    )
    assert turn.status_code == 200, turn.text
    assert turn.json()["result"]["response"]
    assert [item["role"] for item in turn.json()["history"]] == ["user", "assistant"]

    stream = client.post(
        f"/api/frontend/conversations/{conversation_id}/turns/stream",
        json={
            "content": "stream hello",
            "workspace_id": "default",
            "project_id": "project-a",
            "session_id": "session-a",
        },
    )
    assert stream.status_code == 200
    events = [json.loads(line) for line in stream.text.splitlines()]
    assert [event["type"] for event in events] == [
        "turn_started",
        "generation_started",
        "chunk_received",
        "generation_completed",
    ]
    assert all(event["schema"] == "frontend-v2-text-stream-event-v1" for event in events)

    restarted = runtime_at(data_dir)
    install_frontend_test_model(restarted)
    restarted_client = client_for(restarted)
    history = restarted_client.get(
        f"/api/frontend/conversations/{conversation_id}/history"
        "?workspace_id=default&project_id=project-a&session_id=session-a"
    )

    assert history.status_code == 200, history.text
    assert len(history.json()["messages"]) == 4
    assert history.json()["pagination"]["returned"] == 4
    assert history.json()["summary"]["conversation_id"] == conversation_id


def test_frontend_launch_opens_new_empty_active_conversation_and_indexes_history(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    runtime = runtime_at(data_dir, clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)

    first = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    assert first.status_code == 200, first.text
    first_id = first.json()["conversation"]["conversation_id"]
    first_turn = client.post(
        f"/api/frontend/conversations/{first_id}/turns",
        json={"content": "first persisted", "workspace_id": "default"},
    )
    assert first_turn.status_code == 200, first_turn.text

    second = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    assert second.status_code == 200, second.text
    second_id = second.json()["conversation"]["conversation_id"]
    assert second_id != first_id
    second_turn = client.post(
        f"/api/frontend/conversations/{second_id}/turns",
        json={"content": "second persisted", "workspace_id": "default"},
    )
    assert second_turn.status_code == 200, second_turn.text

    launch = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    assert launch.status_code == 200, launch.text
    assert launch.json()["conversation"]["conversation_id"] not in {first_id, second_id}
    assert launch.json()["messages"] == []

    index = client.get("/api/frontend/conversations", params={"workspace_id": "default"})
    assert index.status_code == 200, index.text
    indexed = index.json()["conversations"]
    indexed_ids = {item["conversation"]["conversation_id"] for item in indexed}
    assert {first_id, second_id}.issubset(indexed_ids)
    by_id = {item["conversation"]["conversation_id"]: item for item in indexed}
    assert by_id[first_id]["message_count"] == 2
    assert by_id[second_id]["message_count"] == 2
    assert by_id[first_id]["preview"]
    assert by_id[second_id]["preview"]


def test_frontend_history_open_renders_only_selected_conversation(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)

    first = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"}).json()
    first_id = first["conversation"]["conversation_id"]
    assert client.post(
        f"/api/frontend/conversations/{first_id}/turns",
        json={"content": "only first", "workspace_id": "default"},
    ).status_code == 200

    second = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"}).json()
    second_id = second["conversation"]["conversation_id"]
    assert client.post(
        f"/api/frontend/conversations/{second_id}/turns",
        json={"content": "only second", "workspace_id": "default"},
    ).status_code == 200

    first_restore = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "conversation_id": first_id},
    )
    assert first_restore.status_code == 200, first_restore.text
    assert {message["conversation_id"] for message in first_restore.json()["messages"]} == {first_id}
    assert "only second" not in json.dumps(first_restore.json()["messages"])

    second_restore = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "conversation_id": second_id},
    )
    assert second_restore.status_code == 200, second_restore.text
    assert {message["conversation_id"] for message in second_restore.json()["messages"]} == {second_id}
    assert "only first" not in json.dumps(second_restore.json()["messages"])


def test_frontend_history_delete_is_scoped_and_persistent(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)

    keep = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "project_id": "project-keep"},
    ).json()
    keep_id = keep["conversation"]["conversation_id"]
    assert client.post(
        f"/api/frontend/conversations/{keep_id}/turns",
        json={"content": "keep this", "workspace_id": "default", "project_id": "project-keep"},
    ).status_code == 200

    remove = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "project_id": "project-remove"},
    ).json()
    remove_id = remove["conversation"]["conversation_id"]
    assert client.post(
        f"/api/frontend/conversations/{remove_id}/turns",
        json={"content": "delete this", "workspace_id": "default", "project_id": "project-remove"},
    ).status_code == 200

    rejected = client.delete(
        f"/api/frontend/conversations/{remove_id}",
        params={"workspace_id": "default", "project_id": "project-remove", "confirmed": "false"},
    )
    assert rejected.status_code == 409

    wrong_scope = client.delete(
        f"/api/frontend/conversations/{remove_id}",
        params={"workspace_id": "default", "project_id": "project-keep", "confirmed": "true"},
    )
    assert wrong_scope.status_code == 422

    deleted = client.delete(
        f"/api/frontend/conversations/{remove_id}",
        params={"workspace_id": "default", "project_id": "project-remove", "confirmed": "true"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True
    assert deleted.json()["conversation_id"] == remove_id

    removed_history = client.get(
        f"/api/frontend/conversations/{remove_id}/history",
        params={"workspace_id": "default", "project_id": "project-remove"},
    )
    assert removed_history.status_code == 404

    keep_index = client.get(
        "/api/frontend/conversations",
        params={"workspace_id": "default", "project_id": "project-keep"},
    )
    assert keep_index.status_code == 200, keep_index.text
    visible_keep_ids = [
        item["conversation"]["conversation_id"]
        for item in keep_index.json()["conversations"]
        if item["message_count"] > 0
    ]
    assert visible_keep_ids == [keep_id]


def test_frontend_history_delete_removes_legacy_unscoped_visible_item(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)

    legacy = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default"},
    ).json()
    legacy_id = legacy["conversation"]["conversation_id"]
    assert client.post(
        f"/api/frontend/conversations/{legacy_id}/turns",
        json={"content": "legacy visible item", "workspace_id": "default"},
    ).status_code == 200

    scoped_index = client.get(
        "/api/frontend/conversations",
        params={"workspace_id": "default", "project_id": "current-project"},
    )
    assert scoped_index.status_code == 200, scoped_index.text
    assert [
        item["conversation"]["conversation_id"]
        for item in scoped_index.json()["conversations"]
        if item["message_count"] > 0
    ] == [legacy_id]

    deleted = client.delete(
        f"/api/frontend/conversations/{legacy_id}",
        params={"workspace_id": "default", "project_id": "current-project", "confirmed": "true"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True

    refreshed = client.get(
        "/api/frontend/conversations",
        params={"workspace_id": "default", "project_id": "current-project"},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert [
        item
        for item in refreshed.json()["conversations"]
        if item["message_count"] > 0
    ] == []


def test_frontend_clear_history_deletes_only_current_scope(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)

    scoped_ids = []
    for content in ("first scoped", "second scoped"):
        opened = client.post(
            "/api/frontend/conversations/open",
            json={"workspace_id": "default", "project_id": "project-a"},
        ).json()
        conversation_id = opened["conversation"]["conversation_id"]
        scoped_ids.append(conversation_id)
        assert client.post(
            f"/api/frontend/conversations/{conversation_id}/turns",
            json={"content": content, "workspace_id": "default", "project_id": "project-a"},
        ).status_code == 200

    other = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "project_id": "project-b"},
    ).json()
    other_id = other["conversation"]["conversation_id"]
    assert client.post(
        f"/api/frontend/conversations/{other_id}/turns",
        json={"content": "other scope", "workspace_id": "default", "project_id": "project-b"},
    ).status_code == 200

    cleared = client.delete(
        "/api/frontend/conversations",
        params={"workspace_id": "default", "project_id": "project-a", "confirmed": "true"},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["deleted"] == 2
    assert set(cleared.json()["conversation_ids"]) == set(scoped_ids)

    scoped_index = client.get(
        "/api/frontend/conversations",
        params={"workspace_id": "default", "project_id": "project-a"},
    )
    assert scoped_index.status_code == 200, scoped_index.text
    assert [
        item
        for item in scoped_index.json()["conversations"]
        if item["message_count"] > 0
    ] == []

    other_index = client.get(
        "/api/frontend/conversations",
        params={"workspace_id": "default", "project_id": "project-b"},
    )
    assert other_index.status_code == 200, other_index.text
    visible_other_ids = [
        item["conversation"]["conversation_id"]
        for item in other_index.json()["conversations"]
        if item["message_count"] > 0
    ]
    assert visible_other_ids == [other_id]


def test_frontend_history_pagination_returns_recent_then_older_without_duplicates(
    tmp_path: Path,
) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "project_id": "project-a", "session_id": "session-a"},
    )
    conversation_id = opened.json()["conversation"]["conversation_id"]

    for index in range(8):
        turn = client.post(
            f"/api/frontend/conversations/{conversation_id}/turns",
            json={
                "content": f"message {index}",
                "workspace_id": "default",
                "project_id": "project-a",
                "session_id": "session-a",
            },
        )
        assert turn.status_code == 200, turn.text

    recent = client.post(
        "/api/frontend/conversations/open",
        json={
            "workspace_id": "default",
            "project_id": "project-a",
            "session_id": "session-a",
            "conversation_id": conversation_id,
            "history_limit": 5,
        },
    )
    assert recent.status_code == 200, recent.text
    recent_payload = recent.json()
    assert len(recent_payload["messages"]) == 5
    assert recent_payload["pagination"]["has_older"] is True

    older = client.get(
        f"/api/frontend/conversations/{conversation_id}/history",
        params={
            "workspace_id": "default",
            "project_id": "project-a",
            "session_id": "session-a",
            "offset": recent_payload["pagination"]["previous_offset"],
            "limit": 5,
        },
    )
    assert older.status_code == 200, older.text
    recent_ids = {message["message_id"] for message in recent_payload["messages"]}
    older_ids = {message["message_id"] for message in older.json()["messages"]}
    assert recent_ids.isdisjoint(older_ids)


def test_frontend_turn_cancellation_boundary_emits_cancelled_event(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    conversation_id = opened.json()["conversation"]["conversation_id"]
    key = "cancel-before-stream"

    cancelled = client.post(
        f"/api/frontend/conversations/{conversation_id}/turns/cancel",
        json={"workspace_id": "default", "idempotency_key": key},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancel_requested"

    stream = client.post(
        f"/api/frontend/conversations/{conversation_id}/turns/stream",
        json={"content": "do not complete", "workspace_id": "default", "idempotency_key": key},
    )
    assert stream.status_code == 200
    events = [json.loads(line) for line in stream.text.splitlines()]
    assert [event["type"] for event in events] == ["generation_cancelled"]


def test_conversation_boundary_enforces_project_and_session_scope(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "project_id": "project-a", "session_id": "session-a"},
    )
    conversation_id = opened.json()["conversation"]["conversation_id"]

    mismatch = client.post(
        f"/api/frontend/conversations/{conversation_id}/turns",
        json={
            "content": "wrong scope",
            "workspace_id": "default",
            "project_id": "project-b",
            "session_id": "session-a",
        },
    )

    assert mismatch.status_code == 422
    assert "scope_mismatch" in mismatch.text


def test_frontend_voice_transcription_uses_real_stt_boundary_without_sending_message(
    tmp_path: Path,
) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    runtime.voice.update_settings(stt_provider_id="mock_stt_adapter", store_raw_audio=False)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "project_id": "project-a", "session_id": "session-a"},
    )
    conversation_id = opened.json()["conversation"]["conversation_id"]

    transcription = client.post(
        "/api/frontend/voice/transcriptions",
        json={
            "audio_base64": valid_wav_base64(),
            "audio_format": "audio/wav",
            "workspace_id": "default",
            "project_id": "project-a",
            "session_id": "session-a",
            "conversation_id": conversation_id,
        },
    )

    assert transcription.status_code == 200, transcription.text
    payload = transcription.json()
    assert payload["schema"] == "frontend-v2-voice-transcription-v1"
    assert payload["transcript"] == "mock transcript"
    assert payload["retrieval_intent"]["intent"] == "none"
    assert payload["retrieval_intent"]["source"] == "none"
    assert payload["conversation_id"] == conversation_id
    assert runtime.voice.get_recording(payload["recording_id"]).audio_ref is None
    assert client.get(
        f"/api/frontend/conversations/{conversation_id}/history",
        params={"workspace_id": "default", "project_id": "project-a", "session_id": "session-a"},
    ).json()["messages"] == []


def test_frontend_voice_transcription_reports_explicit_project_retrieval_intent(
    tmp_path: Path,
) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    runtime.voice.update_settings(stt_provider_id="mock_stt_adapter", store_raw_audio=False)
    runtime.speech_adapters._runtime_adapters["mock_stt_adapter"] = ProjectRetrievalSttAdapter()
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "project_id": "project-a", "session_id": "session-a"},
    )
    conversation_id = opened.json()["conversation"]["conversation_id"]

    transcription = client.post(
        "/api/frontend/voice/transcriptions",
        json={
            "audio_base64": valid_wav_base64(),
            "audio_format": "audio/wav",
            "workspace_id": "default",
            "project_id": "project-a",
            "session_id": "session-a",
            "conversation_id": conversation_id,
        },
    )

    assert transcription.status_code == 200, transcription.text
    intent = transcription.json()["retrieval_intent"]
    assert intent["intent"] == "project_knowledge"
    assert intent["source"] == "voice_explicit"
    assert intent["query"] == "onde definimos fencing"


def test_frontend_voice_transcription_then_text_send_uses_same_conversation(
    tmp_path: Path,
) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    runtime.voice.update_settings(stt_provider_id="mock_stt_adapter", store_raw_audio=False)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    conversation_id = opened.json()["conversation"]["conversation_id"]

    transcription = client.post(
        "/api/frontend/voice/transcriptions",
        json={
            "audio_base64": valid_wav_base64(),
            "audio_format": "audio/wav",
            "workspace_id": "default",
            "conversation_id": conversation_id,
        },
    ).json()
    turn = client.post(
        f"/api/frontend/conversations/{conversation_id}/turns",
        json={"content": transcription["transcript"], "workspace_id": "default"},
    )

    assert turn.status_code == 200, turn.text
    assert [message["role"] for message in turn.json()["history"]] == ["user", "assistant"]
    assert turn.json()["history"][0]["payload"]["body"] == "mock transcript"


def test_frontend_voice_conversation_turn_persists_text_and_returns_tts_audio(
    tmp_path: Path,
) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    runtime.voice.update_settings(
        stt_provider_id="mock_stt_adapter",
        tts_provider_id="mock_tts",
        store_raw_audio=False,
    )
    runtime.speech_adapters._runtime_adapters["mock_tts_adapter"] = ControlledTtsAdapter()
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    conversation_id = opened.json()["conversation"]["conversation_id"]

    turn = client.post(
        "/api/frontend/voice/conversation-turn",
        json={
            "audio_base64": valid_wav_base64(),
            "audio_format": "audio/wav",
            "workspace_id": "default",
            "conversation_id": conversation_id,
            "language": "pt-BR",
            "idempotency_key": "voice-turn-1",
        },
    )

    assert turn.status_code == 200, turn.text
    payload = turn.json()
    assert payload["schema"] == "frontend-v2-voice-conversation-turn-v1"
    assert payload["transcript"] == "mock transcript"
    assert payload["response"]
    assert payload["tts"]["status"] == "completed"
    assert payload["tts"]["audio_base64"]
    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]
    recording = runtime.voice.get_recording(payload["recording_id"])
    assert recording.audio_ref is None
    assert recording.language == "pt-BR"
    assert recording.metadata["vad_filter"] is False
    assert recording.metadata["frontend_vad"] is True


def test_frontend_voice_conversation_tts_failure_preserves_text_history(
    tmp_path: Path,
) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    runtime.voice.update_settings(stt_provider_id="mock_stt_adapter", tts_provider_id="mock_tts")
    runtime.speech_adapters.synthesize = lambda request: (_ for _ in ()).throw(
        ValidationError("tts_unavailable: no TTS provider")
    )
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    conversation_id = opened.json()["conversation"]["conversation_id"]

    failed = client.post(
        "/api/frontend/voice/conversation-turn",
        json={
            "audio_base64": valid_wav_base64(),
            "audio_format": "audio/wav",
            "workspace_id": "default",
            "conversation_id": conversation_id,
        },
    )
    history = client.get(
        f"/api/frontend/conversations/{conversation_id}/history",
        params={"workspace_id": "default"},
    )

    assert failed.status_code == 200, failed.text
    payload = failed.json()
    assert payload["tts"]["status"] == "failed"
    assert payload["tts"]["audio_base64"] is None
    assert payload["degraded"][0]["code"] == "tts_unavailable"
    assert [message["role"] for message in history.json()["messages"]] == ["user", "assistant"]


@pytest.mark.parametrize("adapter,expected_status", [
    (RepeatedEchoSttAdapter(), "ignored_echo"),
    (LowConfidenceSttAdapter(), "needs_repetition"),
])
def test_frontend_voice_conversation_ignores_repeated_audio_echo_before_chat_history(
    tmp_path: Path,
    adapter,
    expected_status,
) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    runtime.voice.update_settings(stt_provider_id="mock_stt_adapter", tts_provider_id="mock_tts")
    runtime.speech_adapters._runtime_adapters["mock_stt_adapter"] = adapter
    runtime.speech_adapters._runtime_adapters["mock_tts_adapter"] = ControlledTtsAdapter()
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    conversation_id = opened.json()["conversation"]["conversation_id"]

    ignored = client.post(
        "/api/frontend/voice/conversation-turn",
        json={
            "audio_base64": valid_wav_base64(),
            "audio_format": "audio/wav",
            "workspace_id": "default",
            "conversation_id": conversation_id,
            "language": "pt-BR",
            "idempotency_key": "voice-turn-echo-loop",
        },
    )
    history = client.get(
        f"/api/frontend/conversations/{conversation_id}/history",
        params={"workspace_id": "default"},
    )

    assert ignored.status_code == 200, ignored.text
    payload = ignored.json()
    assert payload["status"] == expected_status
    assert payload["response"] == ""
    assert payload["tts"]["status"] == "skipped"
    assert payload["tts"]["audio_base64"] is None
    assert payload["degraded"] == []
    assert payload["messages"] == []
    assert history.json()["messages"] == []


def test_frontend_voice_conversation_replaces_error_session_before_recording(
    tmp_path: Path,
) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    runtime.voice.update_settings(
        stt_provider_id="mock_stt_adapter",
        tts_provider_id="mock_tts",
        store_raw_audio=False,
    )
    runtime.speech_adapters._runtime_adapters["mock_tts_adapter"] = ControlledTtsAdapter()
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    conversation_id = opened.json()["conversation"]["conversation_id"]
    broken_session = runtime.voice.create_session(
        agent_id="synapse",
        conversation_id=conversation_id,
        metadata={"source": "frontend_v2_conversation_mode"},
    )
    runtime.voice.transition_session(broken_session.session_id, "listening")
    runtime.voice.transition_session(broken_session.session_id, "recording")
    runtime.voice.transition_session(broken_session.session_id, "processing")
    runtime.voice.transition_session(broken_session.session_id, "error", error="previous_failure")

    turn = client.post(
        "/api/frontend/voice/conversation-turn",
        json={
            "audio_base64": valid_wav_base64(),
            "audio_format": "audio/wav",
            "workspace_id": "default",
            "conversation_id": conversation_id,
            "voice_session_id": broken_session.session_id,
            "idempotency_key": "voice-turn-after-error",
        },
    )

    assert turn.status_code == 200, turn.text
    payload = turn.json()
    assert payload["voice_session_id"] != broken_session.session_id
    assert runtime.voice.get_session(broken_session.session_id).status == "error"
    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]


def test_frontend_voice_transcription_rejects_empty_invalid_scope_and_unavailable_stt(
    tmp_path: Path,
) -> None:
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = runtime_at(tmp_path / "data", clean=True)
    runtime.voice.update_settings(stt_provider_id="mock_stt_adapter")
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "project_id": "project-a", "session_id": "session-a"},
    )
    conversation_id = opened.json()["conversation"]["conversation_id"]

    empty = client.post(
        "/api/frontend/voice/transcriptions",
        json={"audio_base64": "", "audio_format": "audio/wav", "workspace_id": "default"},
    )
    invalid = client.post(
        "/api/frontend/voice/transcriptions",
        json={"audio_base64": "not-base64", "audio_format": "audio/wav", "workspace_id": "default"},
    )
    wrong_scope = client.post(
        "/api/frontend/voice/transcriptions",
        json={
            "audio_base64": valid_wav_base64(),
            "audio_format": "audio/wav",
            "workspace_id": "default",
            "project_id": "project-b",
            "session_id": "session-a",
            "conversation_id": conversation_id,
        },
    )
    runtime.audio.transcribe = lambda request: (_ for _ in ()).throw(
        ValidationError("stt_unavailable: no STT provider")
    )
    unavailable = client.post(
        "/api/frontend/voice/transcriptions",
        json={"audio_base64": valid_wav_base64(), "audio_format": "audio/wav", "workspace_id": "default"},
    )

    assert empty.status_code == 422
    assert invalid.status_code == 422
    assert "invalid_audio" in invalid.text
    assert wrong_scope.status_code == 422
    assert "scope_mismatch" in wrong_scope.text
    assert unavailable.status_code == 422
    assert "stt_unavailable" in unavailable.text


def test_stream_backend_failure_is_frontend_safe_error_event(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    conversation_id = opened.json()["conversation"]["conversation_id"]

    stream = client.post(
        f"/api/frontend/conversations/{conversation_id}/turns/stream",
        json={
            "content": "fail safely",
            "workspace_id": "missing-workspace",
        },
    )

    assert stream.status_code == 200
    event = json.loads(stream.text.splitlines()[0])
    assert event["type"] == "generation_failed"
    assert event["error"]["code"] == "ValidationError"
    assert "scope_mismatch" in event["error"]["message"]


def test_frontend_attachment_staging_registers_backend_owned_identity(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    conversation_id = opened.json()["conversation"]["conversation_id"]
    content = b"attachment text"

    response = client.post(
        f"/api/frontend/conversations/{conversation_id}/attachments/stage",
        json={
            "filename": "note.txt",
            "mime_type": "text/plain",
            "size": len(content),
            "content_base64": base64.b64encode(content).decode("ascii"),
            "workspace_id": "default",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    attachment = payload["attachment"]
    assert payload["schema"] == "frontend-v2-attachment-stage-result-v1"
    assert attachment["filename"] == "note.txt"
    assert attachment["checksum"] == hashlib.sha256(content).hexdigest()
    assert attachment["storage_ref"].startswith(f"conversations/{conversation_id}/attachments/storage/")
    assert payload["knowledge_ingestion"]["status"] == "missing_project_scope"
    assert str(tmp_path) not in response.text


def test_frontend_attachment_staging_accepts_safe_unicode_filename(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    conversation_id = opened.json()["conversation"]["conversation_id"]
    content = "Project Files smoke evidence 2026".encode("utf-8")

    response = client.post(
        f"/api/frontend/conversations/{conversation_id}/attachments/stage",
        json={
            "filename": "Arthur Santos Ahl - evidência.txt",
            "mime_type": "text/plain",
            "size": len(content),
            "content_base64": base64.b64encode(content).decode("ascii"),
            "workspace_id": "default",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["attachment"]["filename"] == "Arthur Santos Ahl - evidência.txt"


def test_frontend_attachment_staging_rejects_path_like_unicode_filename() -> None:
    try:
        validate_frontend_attachment_metadata("folder:evidência.txt", "text/plain", 7)
    except ValidationError as exc:
        assert "attachment_invalid: unsupported filename" in str(exc)
    else:
        raise AssertionError("path-like attachment filename was accepted")


def test_frontend_text_attachment_is_indexed_as_project_knowledge(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "project_id": "project-a"},
    )
    conversation_id = opened.json()["conversation"]["conversation_id"]
    content = b"briefing motor vector db para o projeto"

    response = client.post(
        f"/api/frontend/conversations/{conversation_id}/attachments/stage",
        json={
            "filename": "briefing.txt",
            "mime_type": "text/plain",
            "size": len(content),
            "content_base64": base64.b64encode(content).decode("ascii"),
            "workspace_id": "default",
            "project_id": "project-a",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["knowledge_ingestion"]["status"] == "scheduled"
    records = []
    for _ in range(20):
        records = [
            item
            for item in runtime.memory.list(runtime.context(), scope="knowledge")
            if item.source.startswith("project_document:")
        ]
        if records:
            break
        time.sleep(0.05)
    assert len(records) == 1
    assert records[0].content == "briefing motor vector db para o projeto"
    assert records[0].metadata["conversation_id"] == conversation_id
    assert records[0].metadata["project_id"] == "project-a"


def test_frontend_attachment_refs_follow_text_turn_and_history(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    opened = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    conversation_id = opened.json()["conversation"]["conversation_id"]
    staged = client.post(
        f"/api/frontend/conversations/{conversation_id}/attachments/stage",
        json={
            "filename": "data.json",
            "mime_type": "application/json",
            "size": 7,
            "content_base64": base64.b64encode(b'{"a":1}').decode("ascii"),
            "workspace_id": "default",
        },
    ).json()["attachment"]

    response = client.post(
        f"/api/frontend/conversations/{conversation_id}/turns",
        json={
            "workspace_id": "default",
            "content": "Use this file.",
            "attachments": [{"attachment_id": staged["attachment_id"]}],
        },
    )

    assert response.status_code == 200, response.text
    history = client.get(
        f"/api/frontend/conversations/{conversation_id}/history",
        params={"workspace_id": "default"},
    ).json()
    user_messages = [item for item in history["messages"] if item["role"] == "user"]
    assert user_messages[-1]["attachments"][0]["attachment_id"] == staged["attachment_id"]
    assert user_messages[-1]["attachments"][0]["storage_ref"] == staged["storage_ref"]


def test_frontend_attachment_validation_and_scope_fail_closed(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    create_ready_primary(client, runtime)
    first = client.post("/api/frontend/conversations/open", json={"workspace_id": "default"})
    first_id = first.json()["conversation"]["conversation_id"]
    second = client.post(
        "/api/frontend/conversations/open",
        json={"workspace_id": "default", "project_id": "project-b"},
    )
    second_id = second.json()["conversation"]["conversation_id"]

    empty = client.post(
        f"/api/frontend/conversations/{first_id}/attachments/stage",
        json={
            "filename": "empty.txt",
            "mime_type": "text/plain",
            "size": 0,
            "content_base64": "",
            "workspace_id": "default",
        },
    )
    assert empty.status_code == 422

    unsupported = client.post(
        f"/api/frontend/conversations/{first_id}/attachments/stage",
        json={
            "filename": "run.exe",
            "mime_type": "application/x-msdownload",
            "size": 4,
            "content_base64": base64.b64encode(b"nope").decode("ascii"),
            "workspace_id": "default",
        },
    )
    assert unsupported.status_code == 422

    staged = client.post(
        f"/api/frontend/conversations/{first_id}/attachments/stage",
        json={
            "filename": "safe.txt",
            "mime_type": "text/plain",
            "size": 4,
            "content_base64": base64.b64encode(b"safe").decode("ascii"),
            "workspace_id": "default",
        },
    ).json()["attachment"]
    leaked = client.post(
        f"/api/frontend/conversations/{second_id}/turns",
        json={
            "workspace_id": "default",
            "project_id": "project-b",
            "content": "wrong scope",
            "attachments": [{"attachment_id": staged["attachment_id"]}],
        },
    )
    assert leaked.status_code == 422
