from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import PermissionDenied, SynapseError
from synapse.model_providers.models import LMStudioChatResult
from synapse.models.adapters import build_chat_messages
from synapse.models.types import ModelResponse
from synapse.retrieval_intent import (
    RetrievalIntent,
    detect_text_retrieval_intent,
    detect_voice_retrieval_intent,
)

DEFAULT_AGENT_PERMISSIONS = [
    "filesystem.read",
    "filesystem.list",
    "agents.message",
    "tasks.create",
]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def agent_config(agent_id: str) -> dict:
    return {
        "id": agent_id,
        "name": agent_id.title(),
        "role": "local chat test agent",
        "preferred_model": "mock/synapse-test",
        "autonomy": "manual",
        "skills": ["chat"],
        "permissions": DEFAULT_AGENT_PERMISSIONS,
    }


def runtime_in_tempdir():
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    create_runtime(settings)
    write_json(
        settings.data_dir / "config" / "permissions.yaml",
        {
            "subjects": {
                "local_owner": ["*"],
                "user:local_owner": ["*"],
                "user:another_user": ["filesystem.read"],
                "agent:artemis": DEFAULT_AGENT_PERMISSIONS,
                "agent:researcher": DEFAULT_AGENT_PERMISSIONS,
            }
        },
    )
    write_json(
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {
                "name": "Synapse V2 Local Chat Test",
                "mode": "test",
                "default_agent_id": "artemis",
            },
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    for agent_id in ("artemis", "researcher"):
        base = settings.data_dir / "agents" / agent_id
        write_json(base / "CONFIG.yaml", agent_config(agent_id))
        write_text(base / "SOUL.md", f"# {agent_id.title()}\nLocal chat test agent.\n")
        write_text(base / "MEMORY.md", f"# {agent_id.title()} Memory\n")
        write_text(base / "SKILLS.md", "# Skills\n- chat\n")
        write_text(base / "INBOX.md", "# Inbox\n")
    return directory, settings, create_runtime(settings)


def enable_lmstudio(settings: Settings, default_model: str | None = "local-model") -> None:
    write_json(
        settings.data_dir / "config" / "lmstudio_provider.yaml",
        {
            "lmstudio": {
                "enabled": True,
                "base_url": "http://127.0.0.1:1234/v1",
                "timeout_seconds": 1,
                "default_model": default_model,
                "metadata": {},
            }
        },
    )


def enable_local_chat(settings: Settings) -> None:
    write_json(
        settings.data_dir / "config" / "local_chat_policy.yaml",
        {
            "local_chat": {
                "enabled": True,
                "provider_id": "lmstudio_local",
                "require_explicit_provider": True,
                "persist_conversations": True,
                "max_context_messages": 5,
                "include_conversation_summary": True,
                "include_multimodal_context": False,
            }
        },
    )


def mock_lmstudio(runtime, content: str = "local model response") -> None:
    runtime.lmstudio._http_get_json = lambda url, timeout: {  # type: ignore[method-assign]
        "data": [{"id": "local-model"}]
    }
    runtime.lmstudio._native_chat_completion = lambda config, chat_request, model, timeout: LMStudioChatResult(  # type: ignore[method-assign]
        model=model,
        content=content,
        finish_reason="stop",
        latency_ms=42,
        raw_metadata={},
    )


class FakeSynapseLocalAdapter:
    provider = "synapse_local"

    def generate(self, request_payload):
        return ModelResponse(
            content="synapse local response",
            provider="synapse_local",
            model=request_payload.model,
            metadata={"fake": True},
        )

    def list_models(self, request_payload):
        del request_payload
        return ["local-gguf"]

    def stream(self, request_payload):
        del request_payload
        return []

    def cancel(self, generation_id):
        del generation_id

    def capabilities(self):
        return {"text_generation"}


class LocalChatRuntimeTests(unittest.TestCase):
    def test_synapse_identity_and_style_survive_restart_and_model_route(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        config = agent_config("artemis")
        config["system_prompt"] = "Seja objetiva e não repita apresentações."
        write_json(settings.data_dir / "agents/artemis/CONFIG.yaml", config)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime)
        with patch.object(runtime.models, "generate_request", wraps=runtime.models.generate_request) as generate:
            runtime.chat.local_chat(runtime.context(), "Não use mais emojis")
            request = generate.call_args.args[0]
        self.assertEqual(request.agent_id, "artemis")
        self.assertIn("Seja objetiva", request.context["agent_identity"]["personality"])
        self.assertIn("Não use emojis", build_chat_messages(request)[0]["content"])

        restarted = create_runtime(settings)
        mock_lmstudio(restarted)
        with patch.object(restarted.models, "generate_request", wraps=restarted.models.generate_request) as generate:
            restarted.chat.local_chat(restarted.context(), "Quais são suas funcionalidades?")
            request = generate.call_args.args[0]
        prompt = build_chat_messages(request)[0]["content"]
        self.assertIn("Não use emojis", prompt)
        self.assertIn("Your Synapse agent name is Artemis", prompt)
        self.assertIn("list_directory", prompt)
        self.assertTrue(request.tools)
        self.assertIn("not your product identity", prompt)
        self.assertIn("Histórico de conversas", prompt)
        with patch.object(restarted.models, "generate_request", wraps=restarted.models.generate_request) as generate:
            restarted.chat.local_chat(restarted.context(), "oi", agent_id="artemis")
            self.assertIn("Não use emojis", build_chat_messages(generate.call_args.args[0])[0]["content"])

        store = restarted.memory
        self.assertIsNotNone(store)
        self.assertIn("Não use emojis", store.response_style(restarted.context(), "Não use emojis"))
        self.assertIn("permitidos", store.response_style(restarted.context(), "Pode usar emojis novamente"))
        preferences = [item for item in store.list(restarted.context(), scope="user")
                       if item.source == "explicit_response_style"]
        self.assertEqual(len(preferences), 1)
        self.assertEqual(store.response_style(restarted.context("another_user"), "oi"), "")
        with self.assertRaises(PermissionDenied):
            store.response_style(restarted.context("another_user"), "Não use emojis")
        for command in ("Por favor não mande mensagens com emotes",
                        "Prefiro respostas sem emojis", "Não conversar mais com emotes"):
            self.assertIn("Não use emojis", store.response_style(restarted.context(), command))

    def test_quoted_and_generated_text_cannot_create_response_preferences(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        for text in ('Traduza: "Não use emojis"', '"Não use emojis"',
                     'Documento: não use emojis', 'Não use emojis?'):
            self.assertEqual(runtime.memory.response_style(runtime.context(), text), "")
        self.assertEqual(runtime.memory.response_style(
            runtime.context("artemis", actor_type="agent"), "Não use emojis"), "")

    def test_local_chat_policy_default_disabled(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        policy = runtime.chat.load_local_chat_policy()

        self.assertFalse(policy["enabled"])
        self.assertEqual(policy["provider_id"], "lmstudio_local")

    def test_local_chat_command_fails_when_disabled(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.commands.execute(runtime.context(), '/local-chat "hello"')

        self.assertEqual(result.status, "error")
        self.assertIn("local_chat.enabled", result.output)

    def test_local_chat_uses_model_router_and_persists_conversation(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime)

        result = runtime.chat.local_chat(runtime.context(), "hello")

        self.assertEqual(result.response, "local model response")
        self.assertEqual(result.model["provider"], "lmstudio")
        self.assertEqual(result.model["model"], "local-model")
        self.assertIsNotNone(result.conversation_id)
        messages = runtime.conversations.list_conversation_messages(result.conversation_id or "")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].payload["role"], "user")
        self.assertEqual(messages[1].payload["role"], "assistant")
        session = runtime.chat.get_session(result.session_id)
        self.assertEqual(len(session.messages), 2)

    def test_project_knowledge_is_not_retrieved_for_ordinary_chat(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime)
        runtime.memory.create(
            runtime.context(),
            scope="knowledge",
            owner_id="local_owner",
            source="project_document:doc:v1:chunk1",
            content="Projeto secreto: usar motor X.",
            tags=["project_knowledge", "project:synapse"],
            metadata={
                "document_id": "doc",
                "version_id": "v1",
                "chunk_id": "chunk1",
                "trusted_instruction": False,
            },
        )

        with patch.object(runtime.models, "generate_request", wraps=runtime.models.generate_request) as generate:
            runtime.chat.local_chat(runtime.context(), "oi", project_id="synapse")

        request = generate.call_args.args[0]
        fused = request.context["conversation_context"]
        scopes = {
            item["scope"]
            for item in fused["items"]
            if item["source_type"] == "memory"
        }
        self.assertNotIn("knowledge", scopes)

    def test_project_knowledge_is_retrieved_only_for_project_or_file_research_intent(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime)
        runtime.memory.create(
            runtime.context(),
            scope="knowledge",
            owner_id="local_owner",
            source="project_document:doc:v1:chunk1",
            content="Projeto secreto: usar motor X.",
            tags=["project_knowledge", "project:synapse"],
            metadata={
                "document_id": "doc",
                "version_id": "v1",
                "chunk_id": "chunk1",
                "trusted_instruction": False,
            },
        )

        with patch.object(runtime.models, "generate_request", wraps=runtime.models.generate_request) as generate:
            runtime.chat.local_chat(
                runtime.context(),
                "pesquise nos arquivos armazenados qual motor usar",
                project_id="synapse",
            )

        request = generate.call_args.args[0]
        fused = request.context["conversation_context"]
        knowledge = [
            item
            for item in fused["items"]
            if item["source_type"] == "memory" and item["scope"] == "knowledge"
        ]
        self.assertEqual(len(knowledge), 1)
        self.assertEqual(knowledge[0]["content"], "Projeto secreto: usar motor X.")
        self.assertTrue(knowledge[0]["metadata"]["rag_retrieval"])
        self.assertFalse(knowledge[0]["metadata"]["trusted_instruction"])

    def test_project_id_alone_and_generic_project_phrasing_do_not_enable_rag(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime)
        runtime.memory.create(
            runtime.context(),
            scope="knowledge",
            owner_id="local_owner",
            source="uploaded_file",
            content="Projeto secreto: usar motor X.",
        )

        for message in (
            "qual a capital do Japão?",
            "me explique RAG",
            "como funciona esse projeto?",
            "o que você acha desse projeto?",
        ):
            with patch.object(runtime.models, "generate_request", wraps=runtime.models.generate_request) as generate:
                runtime.chat.local_chat(runtime.context(), message, project_id="synapse")
            fused = generate.call_args.args[0].context["conversation_context"]
            self.assertNotIn(
                "knowledge",
                {
                    item["scope"]
                    for item in fused["items"]
                    if item["source_type"] == "memory"
                },
            )

    def test_project_slash_command_normalizes_query_and_requires_project_scope(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime)
        runtime.memory.create(
            runtime.context(),
            scope="knowledge",
            owner_id="local_owner",
            source="uploaded_file",
            content="fencing fica no contrato de execução",
        )

        with self.assertRaisesRegex(Exception, "missing_project_scope"):
            runtime.chat.local_chat(runtime.context(), "/project onde definimos fencing?")
        with self.assertRaisesRegex(Exception, "empty_retrieval_query"):
            runtime.chat.local_chat(runtime.context(), "/project", project_id="synapse")

        with patch.object(runtime.models, "generate_request", wraps=runtime.models.generate_request) as generate:
            runtime.chat.local_chat(
                runtime.context(),
                "/project onde definimos fencing?",
                project_id="synapse",
            )

        request = generate.call_args.args[0]
        self.assertEqual(request.user_message, "onde definimos fencing?")
        intent = request.context["conversation_context"]["snapshot"]["metadata"]["retrieval_intent"]
        self.assertEqual(intent["intent"], "project_knowledge")
        self.assertEqual(intent["source"], "slash")
        self.assertEqual(intent["query"], "onde definimos fencing?")

    def test_voice_and_slash_retrieval_intents_are_equivalent_but_conservative(self) -> None:
        slash = detect_text_retrieval_intent("/project onde definimos rollback?")
        voice = detect_voice_retrieval_intent(
            "pesquise nos arquivos desse projeto onde definimos rollback"
        )

        self.assertEqual(slash.intent, RetrievalIntent.PROJECT_KNOWLEDGE)
        self.assertEqual(voice.intent, RetrievalIntent.PROJECT_KNOWLEDGE)
        self.assertEqual(slash.query, "onde definimos rollback?")
        self.assertEqual(voice.query, "onde definimos rollback")
        self.assertEqual(detect_voice_retrieval_intent("me explique fencing").intent,
                         RetrievalIntent.NONE)
        self.assertEqual(detect_voice_retrieval_intent("o que você acha desse projeto?").intent,
                         RetrievalIntent.NONE)

    def test_local_chat_respects_model_hub_selection(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        runtime.model_hub.update_defaults(
            default_chat_model="local-model",
            default_provider="lmstudio",
            preferred_runtime="lmstudio",
        )
        mock_lmstudio(runtime)

        result = runtime.chat.local_chat(
            runtime.context(),
            "hello",
            model_provider_id="lmstudio",
            model_name="local-model",
        )

        self.assertEqual(result.model["provider"], "lmstudio")
        self.assertEqual(result.model["model"], "local-model")

    def test_local_chat_can_route_to_synapse_local_adapter(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_json(
            settings.data_dir / "config" / "local_chat_policy.yaml",
            {
                "local_chat": {
                    "enabled": True,
                    "provider_id": "synapse_local",
                    "require_explicit_provider": True,
                    "persist_conversations": True,
                    "max_context_messages": 5,
                    "include_conversation_summary": True,
                    "include_multimodal_context": False,
                }
            },
        )
        runtime = create_runtime(settings)
        runtime.models.adapters["synapse_local"] = FakeSynapseLocalAdapter()
        runtime.provider_settings.update_setting(
            "synapse_local",
            enabled=True,
            endpoint=str(settings.data_dir / "models"),
        )

        result = runtime.chat.local_chat(
            runtime.context(),
            "hello",
            model_provider_id="synapse_local",
            model_name="local-gguf",
        )

        self.assertEqual(result.response, "synapse local response")
        self.assertEqual(result.model["provider"], "synapse_local")
        self.assertEqual(result.model["model"], "local-gguf")

    def test_model_hub_defaults_enable_local_chat_flow(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        runtime.model_hub.update_defaults(
            default_chat_model="local-model",
            default_provider="lmstudio",
            preferred_runtime="lmstudio",
        )
        mock_lmstudio(runtime, "synced response")

        result = runtime.chat.local_chat(runtime.context(), "oi")

        self.assertEqual(result.response, "synced response")
        self.assertEqual(result.model["provider"], "lmstudio")
        self.assertEqual(result.model["model"], "local-model")
        self.assertTrue(runtime.chat.load_local_chat_policy()["enabled"])

    def test_existing_conversation_id_is_reused(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime)
        conversation = runtime.conversations.create_conversation(
            runtime.context(),
            ["artemis"],
            title="Existing local chat",
        )

        result = runtime.chat.local_chat(
            runtime.context(),
            "reuse this conversation",
            conversation_id=conversation.conversation_id,
        )

        self.assertEqual(result.conversation_id, conversation.conversation_id)
        self.assertEqual(
            len(runtime.conversations.list_conversation_messages(conversation.conversation_id)),
            2,
        )

    def test_agent_local_chat_uses_agent_id(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime)

        result = runtime.chat.local_chat(runtime.context(), "hello researcher", agent_id="researcher")

        self.assertEqual(result.agent_id, "researcher")

    def test_default_model_missing_fails_controlled(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings, default_model=None)
        enable_local_chat(settings)
        runtime = create_runtime(settings)

        with self.assertRaises(SynapseError):
            runtime.chat.local_chat(runtime.context(), "hello")

    def test_lmstudio_unavailable_fails_controlled(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)

        def fail_get(url: str, timeout: int) -> dict:
            raise OSError("connection refused")

        runtime.lmstudio._http_get_json = fail_get  # type: ignore[method-assign]

        with self.assertRaises(SynapseError):
            runtime.chat.local_chat(runtime.context(), "hello")

    def test_commands(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime, "command response")

        local = runtime.commands.execute(runtime.context(), '/local-chat "hello"')
        agent = runtime.commands.execute(runtime.context(), '/local-chat-agent researcher "hello"')
        conversation_id = local.data["conversation_id"]
        conversation = runtime.commands.execute(
            runtime.context(),
            f'/local-chat-conversation {conversation_id} "again"',
        )

        self.assertEqual(local.status, "ok")
        self.assertEqual(agent.status, "ok")
        self.assertEqual(conversation.status, "ok")
        self.assertEqual(conversation.data["conversation_id"], conversation_id)

    def test_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime, "api response")
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        local = client.post("/api/local-chat", json={"message": "hello"})
        self.assertEqual(local.status_code, 200)
        self.assertEqual(local.json()["response"], "api response")
        agent = client.post("/api/agents/researcher/local-chat", json={"message": "hello"})
        self.assertEqual(agent.status_code, 200)
        conversation_id = local.json()["conversation_id"]
        conversation = client.post(
            f"/api/conversations/{conversation_id}/local-chat",
            json={"message": "again"},
        )
        self.assertEqual(conversation.status_code, 200)
        self.assertEqual(conversation.json()["conversation_id"], conversation_id)

    def test_health_and_readiness_include_local_chat(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        enable_local_chat(settings)
        runtime = create_runtime(settings)
        mock_lmstudio(runtime)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.local_chat_available)
        self.assertIn("local_chat.ready", [check.id for check in readiness.checks])


if __name__ == "__main__":
    unittest.main()
