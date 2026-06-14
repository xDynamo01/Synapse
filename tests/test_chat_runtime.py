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
from synapse.core.exceptions import PermissionDenied
from synapse.core.permissions import PermissionContext


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


DEFAULT_AGENT_PERMISSIONS = [
    "filesystem.read",
    "filesystem.write",
    "filesystem.list",
    "filesystem.search",
    "agents.message",
    "tasks.create",
    "tasks.update",
    "web.search",
]


def agent_config(
    agent_id: str,
    role: str,
    permissions: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "id": agent_id,
            "name": agent_id.title(),
            "role": role,
            "preferred_model": "mock/synapse-test",
            "autonomy": "manual",
            "skills": ["chat", "message_agents", "create_tasks"],
            "permissions": permissions or DEFAULT_AGENT_PERMISSIONS,
        },
        indent=2,
    )


def runtime_in_tempdir(
    artemis_permissions: list[str] | None = None,
    researcher_permissions: list[str] | None = None,
):
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
                *(artemis_permissions or DEFAULT_AGENT_PERMISSIONS),
            ],
            "agent:researcher": [
                *(researcher_permissions or DEFAULT_AGENT_PERMISSIONS),
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
        permissions = artemis_permissions if agent_id == "artemis" else researcher_permissions
        write(base / "CONFIG.yaml", agent_config(agent_id, role, permissions))
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

            def context(
                self,
                actor_id: str | None = None,
                actor_type: str = "user",
                device_id: str | None = None,
            ):
                return PermissionContext(
                    actor_id=actor_id or "fallback",
                    actor_type=actor_type,
                    device_id=device_id,
                )

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

    def test_agent_tool_call_read_file_with_permission_returns_content(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:read_file path=memory/MEMORY.md",
        )

        tool_results = result.message.metadata["tool_results"]
        self.assertEqual(tool_results[0]["request"]["name"], "read_file")
        self.assertTrue(tool_results[0]["success"])
        self.assertIn("Chat runtime test memory", tool_results[0]["result"]["content"])
        self.assertIn("read_file:executed", result.response)

    def test_agent_tool_call_read_file_without_permission_is_blocked(self) -> None:
        permissions = [
            permission
            for permission in DEFAULT_AGENT_PERMISSIONS
            if permission != "filesystem.read"
        ]
        directory, _, runtime = runtime_in_tempdir(artemis_permissions=permissions)
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:read_file path=memory/MEMORY.md",
        )

        tool_result = result.message.metadata["tool_results"][0]
        self.assertFalse(tool_result["success"])
        self.assertIn("lacks permission filesystem.read", tool_result["error"])
        self.assertIn("read_file:failed", result.response)

    def test_agent_tool_call_path_traversal_is_blocked(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:read_file path=../outside.txt",
        )

        tool_result = result.message.metadata["tool_results"][0]
        self.assertFalse(tool_result["success"])
        self.assertIn("Path escapes DATA_DIR", tool_result["error"])

    def test_agent_tool_call_create_task_persists_task(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:create_task title='Tool Created Task' description='Created through tool call'",
        )

        tool_result = result.message.metadata["tool_results"][0]
        self.assertTrue(tool_result["success"])
        task_id = tool_result["result"]["id"]
        self.assertTrue(runtime.data_dir.resolve(f"tasks/active/{task_id}.json").exists())
        self.assertEqual(runtime.tasks.get_task(task_id).title, "Tool Created Task")

    def test_agent_tool_call_send_agent_message_creates_structured_message(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            (
                "tool:send_agent_message from_agent_id=artemis to_agent_id=researcher "
                "subject='Tool Message' body='hello via tool'"
            ),
        )

        tool_result = result.message.metadata["tool_results"][0]
        self.assertTrue(tool_result["success"])
        message_id = tool_result["result"]["id"]
        messages = runtime.communication.list_messages(runtime.context(), "researcher")
        self.assertEqual(messages[0].id, message_id)
        self.assertEqual(messages[0].body, "hello via tool")

    def test_tool_call_events_are_emitted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.chat.send_message(runtime.context(), "artemis", "tool:list_directory path=memory")

        event_types = [event.type for event in runtime.events.tail(limit=80)]
        self.assertIn("tool.requested", event_types)
        self.assertIn("tool.permission_checked", event_types)
        self.assertIn("tool.executed", event_types)

    def test_api_chat_endpoint_executes_tool_call_flow(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).post(
            "/api/chat",
            headers={"x-actor-id": "local_owner", "x-actor-type": "user"},
            json={"agent_id": "artemis", "message": "tool:read_file path=memory/MEMORY.md"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        tool_results = payload["message"]["metadata"]["tool_results"]
        self.assertTrue(tool_results[0]["success"])
        self.assertIn("Chat runtime test memory", tool_results[0]["result"]["content"])

    def test_low_risk_tool_executes_without_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:list_directory path=memory",
        )

        tool_result = result.message.metadata["tool_results"][0]
        self.assertEqual(tool_result["status"], "executed")
        self.assertTrue(tool_result["success"])
        self.assertEqual(runtime.approvals.list_pending(), [])

    def test_high_risk_tool_creates_pending_approval_and_does_not_execute(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:write_file path=projects/high-risk.txt content=blocked",
        )

        tool_result = result.message.metadata["tool_results"][0]
        self.assertEqual(tool_result["status"], "awaiting_approval")
        self.assertFalse(tool_result["success"])
        approval_id = tool_result["approval_id"]
        approval = runtime.approvals.get_status(approval_id)
        self.assertEqual(approval.status, "pending")
        self.assertEqual(approval.risk_level, "high")
        self.assertFalse(runtime.data_dir.resolve("projects/high-risk.txt").exists())

    def test_approved_request_allows_high_risk_tool_execution(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        first = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:write_file path=projects/approved.txt content=approved",
        )
        approval_id = first.message.metadata["tool_results"][0]["approval_id"]
        runtime.approvals.approve(runtime.context(), approval_id)

        second = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            f"tool:write_file path=projects/approved.txt content=approved approval_id={approval_id}",
        )

        tool_result = second.message.metadata["tool_results"][0]
        self.assertEqual(tool_result["status"], "executed")
        self.assertTrue(tool_result["success"])
        self.assertEqual(
            runtime.data_dir.resolve("projects/approved.txt").read_text(encoding="utf-8"),
            "approved",
        )

    def test_rejected_request_blocks_high_risk_tool_execution(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        first = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:write_file path=projects/rejected.txt content=rejected",
        )
        approval_id = first.message.metadata["tool_results"][0]["approval_id"]
        runtime.approvals.reject(runtime.context(), approval_id)

        second = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            f"tool:write_file path=projects/rejected.txt content=rejected approval_id={approval_id}",
        )

        tool_result = second.message.metadata["tool_results"][0]
        self.assertEqual(tool_result["status"], "failed")
        self.assertFalse(tool_result["success"])
        self.assertIn("rejected", tool_result["error"])
        self.assertFalse(runtime.data_dir.resolve("projects/rejected.txt").exists())

    def test_approval_events_are_emitted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:write_file path=projects/events.txt content=events",
        )
        approval_id = result.message.metadata["tool_results"][0]["approval_id"]
        runtime.approvals.approve(runtime.context(), approval_id)
        second = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            f"tool:write_file path=projects/events.txt content=events approval_id={approval_id}",
        )

        event_types = [event.type for event in runtime.events.tail(limit=120)]
        self.assertIn("approval.requested", event_types)
        self.assertIn("approval.approved", event_types)
        self.assertIn("tool.requested", event_types)
        self.assertIn("tool.permission_checked", event_types)
        self.assertIn("tool.executed", event_types)
        self.assertEqual(second.message.metadata["tool_results"][0]["status"], "executed")

    def test_command_runtime_approvals_lists_pending(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:write_file path=projects/pending.txt content=pending",
        )
        result = runtime.commands.execute(runtime.context(), "/approvals")

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.data["approvals"]), 1)
        self.assertEqual(result.data["approvals"][0]["status"], "pending")

    def test_command_runtime_approve_changes_status(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        first = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:write_file path=projects/command-approved.txt content=ok",
        )
        approval_id = first.message.metadata["tool_results"][0]["approval_id"]
        result = runtime.commands.execute(runtime.context(), f"/approve {approval_id}")

        self.assertEqual(result.status, "ok")
        self.assertEqual(runtime.approvals.get_status(approval_id).status, "approved")

    def test_command_runtime_reject_changes_status(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        first = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:write_file path=projects/command-rejected.txt content=no",
        )
        approval_id = first.message.metadata["tool_results"][0]["approval_id"]
        result = runtime.commands.execute(runtime.context(), f"/reject {approval_id}")

        self.assertEqual(result.status, "ok")
        self.assertEqual(runtime.approvals.get_status(approval_id).status, "rejected")

    def test_device_without_permission_cannot_approve(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        first = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:write_file path=projects/device-denied.txt content=denied",
        )
        approval_id = first.message.metadata["tool_results"][0]["approval_id"]
        runtime.devices.register_device(
            "viewer",
            trusted=True,
            permissions=["view_notifications"],
            actor_id="local_owner",
        )
        context = runtime.context(actor_id="local_owner", actor_type="user", device_id="viewer")

        with self.assertRaises(PermissionDenied):
            runtime.commands.execute(context, f"/approve {approval_id}")

        self.assertEqual(runtime.approvals.get_status(approval_id).status, "pending")


if __name__ == "__main__":
    unittest.main()
