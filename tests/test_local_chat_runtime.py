from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import SynapseError

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
    runtime.lmstudio._http_post_json = lambda url, payload, timeout: {  # type: ignore[method-assign]
        "model": payload["model"],
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
    }


class LocalChatRuntimeTests(unittest.TestCase):
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
