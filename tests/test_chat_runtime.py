from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.chat.runtime import ChatMessage, ChatTurnResult
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.permissions import PermissionContext


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def agent_config(agent_id: str, role: str) -> str:
    return json.dumps(
        {
            "id": agent_id,
            "name": agent_id.title(),
            "role": role,
            "preferred_model": "mock/synapse-test",
            "autonomy": "manual",
            "skills": ["chat", "message_agents", "create_tasks"],
            "permissions": [
                "filesystem.read",
                "filesystem.write",
                "filesystem.list",
                "filesystem.search",
                "agents.message",
                "tasks.create",
                "tasks.update",
                "web.search",
            ],
        },
        indent=2,
    )


def runtime_in_tempdir():
    directory = tempfile.TemporaryDirectory()
    root = Path(directory.name)
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=root / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    runtime = create_runtime(settings)
    permissions = {
        "subjects": {
            "local_owner": ["*"],
            "user:local_owner": ["*"],
            "agent:artemis": [
                "filesystem.read",
                "filesystem.write",
                "agents.message",
                "tasks.create",
                "tasks.update",
                "web.search",
            ],
            "agent:researcher": [
                "filesystem.read",
                "filesystem.write",
                "agents.message",
                "tasks.create",
                "tasks.update",
                "web.search",
            ],
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Chat Test",
            "mode": "test",
            "default_agent_id": "artemis",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    write(settings.data_dir / "config" / "permissions.yaml", json.dumps(permissions, indent=2))
    write(settings.data_dir / "config" / "system.yaml", json.dumps(system, indent=2))
    write(settings.data_dir / "memory" / "SYSTEM.md", "# System\nUse deterministic test mode.\n")
    write(settings.data_dir / "memory" / "USER.md", "# User\nArthur likes local-first systems.\n")
    write(settings.data_dir / "memory" / "MEMORY.md", "# Global Memory\nChat runtime test memory.\n")

    for agent_id, role in {
        "artemis": "Primary personal agent.",
        "researcher": "Research support agent.",
    }.items():
        base = settings.data_dir / "agents" / agent_id
        write(base / "CONFIG.yaml", agent_config(agent_id, role))
        write(base / "SOUL.md", f"# {agent_id.title()}\n{role}\n")
        write(base / "MEMORY.md", f"# {agent_id.title()} Memory\nPersistent {agent_id} memory.\n")
        write(base / "SKILLS.md", f"# {agent_id.title()} Skills\n- chat\n- message_agents\n")
        write(base / "INBOX.md", "# Inbox\n")

    runtime = create_runtime(settings)
    return directory, settings, runtime


class ChatRuntimeTests(unittest.TestCase):
    def test_user_chats_with_artemis_using_mock_model_and_persists_session(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            agent_id="artemis",
            user_message="Hello Artemis",
        )

        self.assertIn("Mock response for artemis", result.response)
        self.assertEqual(result.model["provider"], "mock")
        self.assertIsNotNone(result.context)
        self.assertEqual(result.context["agent_id"], "artemis")
        session = runtime.chat.get_session(result.session_id)
        self.assertEqual([message.role for message in session.messages], ["user", "assistant"])
        self.assertEqual(session.messages[0].content, "Hello Artemis")
        self.assertTrue(runtime.data_dir.resolve(f"chats/sessions/{result.session_id}.json").exists())

    def test_context_loader_is_called_and_chat_history_stays_out_of_memory(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            agent_id="artemis",
            user_message="This should remain chat history only",
        )

        event_types = [event.type for event in runtime.events.tail(limit=50)]
        self.assertIn("context.loaded", event_types)
        self.assertIn("chat.context_loaded", event_types)
        self.assertEqual(result.context["history"], [])
        memory_text = "\n".join(
            runtime.data_dir.resolve(path).read_text(encoding="utf-8")
            for path in ["memory/SYSTEM.md", "memory/USER.md", "memory/MEMORY.md"]
        )
        self.assertNotIn("This should remain chat history only", memory_text)

    def test_chat_events_are_emitted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.chat.send_message(runtime.context(), "artemis", "Emit chat events")

        event_types = [event.type for event in runtime.events.tail(limit=50)]
        self.assertIn("chat.message_received", event_types)
        self.assertIn("chat.context_loaded", event_types)
        self.assertIn("chat.response_generated", event_types)
        self.assertIn("chat.session_persisted", event_types)

    def test_chat_command_call_creates_real_agent_message(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            agent_id="artemis",
            user_message="/call researcher confirm chat command path",
        )

        self.assertEqual(result.command["status"], "ok")
        messages = runtime.communication.list_messages(runtime.context(), "researcher")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].from_agent, "artemis")
        self.assertEqual(messages[0].to_agent, "researcher")
        self.assertIn("confirm chat command path", messages[0].body)

    def test_runtime_restart_preserves_chat_session(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        first = runtime.chat.send_message(runtime.context(), "artemis", "First turn")
        restarted = create_runtime(settings)
        session = restarted.chat.get_session(first.session_id)

        self.assertEqual(len(session.messages), 2)
        self.assertEqual(session.messages[0].content, "First turn")

        second = restarted.chat.send_message(
            restarted.context(),
            "artemis",
            "Second turn",
            session_id=first.session_id,
        )
        self.assertEqual(len(second.context["history"]), 2)
        self.assertEqual(second.context["history"][0]["content"], "First turn")

    def test_api_chat_endpoint_delegates_to_chat_runtime(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        @dataclass
        class FakeChat:
            calls: list[dict[str, Any]] = field(default_factory=list)

            def send_message(
                self,
                context: PermissionContext,
                agent_id: str,
                user_message: str,
                project_id: str | None = None,
                session_id: str | None = None,
            ) -> ChatTurnResult:
                self.calls.append(
                    {
                        "context": context,
                        "agent_id": agent_id,
                        "user_message": user_message,
                        "project_id": project_id,
                        "session_id": session_id,
                    }
                )
                return ChatTurnResult(
                    session_id=session_id or "api-session",
                    agent_id=agent_id,
                    response="delegated",
                    message=ChatMessage(role="assistant", content="delegated"),
                    model={"provider": "mock", "model": "api"},
                )

        class FakeRuntime:
            def __init__(self) -> None:
                self.chat = FakeChat()

            def context(self, actor_id: str | None = None, actor_type: str = "user"):
                return PermissionContext(actor_id=actor_id or "fallback", actor_type=actor_type)

        fake_runtime = FakeRuntime()
        app = FastAPI()
        app.state.runtime = fake_runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).post(
            "/api/chat",
            headers={"x-actor-id": "api-user", "x-actor-type": "user"},
            json={
                "agent_id": "artemis",
                "message": "hello over api",
                "project_id": "project-a",
                "session_id": "session-a",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["response"], "delegated")
        self.assertEqual(len(fake_runtime.chat.calls), 1)
        call = fake_runtime.chat.calls[0]
        self.assertEqual(call["context"].actor_id, "api-user")
        self.assertEqual(call["agent_id"], "artemis")
        self.assertEqual(call["user_message"], "hello over api")
        self.assertEqual(call["project_id"], "project-a")
        self.assertEqual(call["session_id"], "session-a")


if __name__ == "__main__":
    unittest.main()

