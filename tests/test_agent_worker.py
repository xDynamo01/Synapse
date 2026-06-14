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
from synapse.core.serialization import load_structured_file

DEFAULT_PERMISSIONS = [
    "filesystem.read",
    "filesystem.write",
    "filesystem.list",
    "filesystem.search",
    "agents.message",
    "tasks.create",
    "tasks.update",
    "web.search",
]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def update_agent_config(settings: Settings, agent_id: str, **updates) -> None:
    path = settings.data_dir / "agents" / agent_id / "CONFIG.yaml"
    config = load_structured_file(path)
    config.update(updates)
    write_json(path, config)


def runtime_in_tempdir(
    researcher_permissions: list[str] | None = None,
    atlas_permissions: list[str] | None = None,
    researcher_preferred_tools: list[str] | None = None,
    researcher_forbidden_tools: list[str] | None = None,
):
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    create_runtime(settings)
    permissions = {
        "subjects": {
            "local_owner": ["*"],
            "user:local_owner": ["*"],
            "agent:artemis": DEFAULT_PERMISSIONS,
            "agent:researcher": researcher_permissions or DEFAULT_PERMISSIONS,
            "agent:atlas": atlas_permissions or DEFAULT_PERMISSIONS,
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Worker Test",
            "mode": "test",
            "default_agent_id": "artemis",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)
    update_agent_config(
        settings,
        "researcher",
        permissions=researcher_permissions or DEFAULT_PERMISSIONS,
        preferred_tools=researcher_preferred_tools or ["web_search", "read_file"],
        forbidden_tools=researcher_forbidden_tools or ["write_file"],
    )
    update_agent_config(
        settings,
        "atlas",
        permissions=atlas_permissions or DEFAULT_PERMISSIONS,
        preferred_tools=["read_file", "list_directory"],
        forbidden_tools=["send_agent_message", "write_file"],
    )
    return directory, settings, create_runtime(settings)


class AgentWorkerTests(unittest.TestCase):
    def send_message(self, runtime, to_agent: str, body: str, from_agent: str = "artemis"):
        return runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id=from_agent,
            to_agent_id=to_agent,
            subject="Worker test",
            body=body,
        )

    def test_researcher_receives_pending_message(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        message = self.send_message(runtime, "researcher", "Summarize this")

        inbox = runtime.worker.list_inbox(runtime.context(), "researcher", status="pending")
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0].id, message.id)
        self.assertEqual(inbox[0].status, "pending")

    def test_process_inbox_marks_read_then_processed(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = self.send_message(runtime, "researcher", "Process this")

        result = runtime.commands.execute(runtime.context(), "/process-inbox Researcher")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["results"][0]["status"], "processed")
        processed = runtime.communication.list_messages(runtime.context(), "researcher")[0]
        self.assertEqual(processed.id, message.id)
        self.assertEqual(processed.status, "processed")
        transitions = [
            event.payload
            for event in runtime.events.tail(limit=100)
            if event.type == "agent.message.status_changed"
        ]
        self.assertIn("read", [item["to_status"] for item in transitions])
        self.assertIn("processed", [item["to_status"] for item in transitions])

    def test_response_is_sent_back_when_policy_allows_autonomous_message(self) -> None:
        directory, _, runtime = runtime_in_tempdir(
            researcher_preferred_tools=["web_search", "read_file", "send_agent_message"],
        )
        self.addCleanup(directory.cleanup)
        self.send_message(runtime, "researcher", "Reply to Artemis")

        results = runtime.worker.process_inbox(runtime.context(), "researcher")

        self.assertEqual(results[0].status, "processed")
        self.assertIsNotNone(results[0].reply)
        artemis_messages = runtime.communication.list_messages(runtime.context(), "artemis")
        self.assertEqual(len(artemis_messages), 1)
        self.assertEqual(artemis_messages[0].from_agent, "researcher")
        self.assertIn("Mock response for researcher", artemis_messages[0].body)

    def test_worker_events_are_emitted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        self.send_message(runtime, "researcher", "Emit worker events")

        runtime.worker.process_inbox(runtime.context(), "researcher")

        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("worker.inbox_checked", event_types)
        self.assertIn("worker.message_processing_started", event_types)
        self.assertIn("worker.message_processed", event_types)

    def test_agent_without_delegate_policy_does_not_send_autonomous_reply(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        self.send_message(runtime, "atlas", "Do not reply autonomously")

        results = runtime.worker.process_inbox(runtime.context(), "atlas")

        self.assertEqual(results[0].status, "processed")
        self.assertIsNone(results[0].reply)
        artemis_messages = runtime.communication.list_messages(runtime.context(), "artemis")
        self.assertEqual(artemis_messages, [])

    def test_tool_call_inside_worker_respects_effective_policy(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        self.send_message(
            runtime,
            "researcher",
            "tool:write_file path=projects/worker-blocked.txt content=no",
        )

        results = runtime.worker.process_inbox(runtime.context(), "researcher")

        self.assertEqual(results[0].status, "processed")
        self.assertEqual(results[0].tool_results[0]["status"], "blocked")
        self.assertFalse(runtime.data_dir.resolve("projects/worker-blocked.txt").exists())

    def test_processing_failure_marks_message_failed(self) -> None:
        permissions = [
            permission for permission in DEFAULT_PERMISSIONS if permission != "filesystem.read"
        ]
        directory, _, runtime = runtime_in_tempdir(researcher_permissions=permissions)
        self.addCleanup(directory.cleanup)
        self.send_message(runtime, "researcher", "This should fail during context load")

        results = runtime.worker.process_inbox(runtime.context(), "researcher")

        self.assertEqual(results[0].status, "failed")
        self.assertIn("filesystem.read", results[0].error)
        failed = runtime.communication.list_messages(runtime.context(), "researcher")[0]
        self.assertEqual(failed.status, "failed")
        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("worker.message_failed", event_types)

    def test_api_process_inbox_works(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        self.send_message(runtime, "researcher", "Process through API")
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).post(
            "/api/agents/researcher/process-inbox",
            headers={"x-actor-id": "local_owner", "x-actor-type": "user"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["status"], "processed")
        self.assertEqual(runtime.communication.list_messages(runtime.context(), "researcher")[0].status, "processed")

    def test_worker_status_command(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        self.send_message(runtime, "researcher", "status")
        runtime.commands.execute(runtime.context(), "/process-inbox researcher")

        result = runtime.commands.execute(runtime.context(), "/worker-status")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["worker"]["last_agent_id"], "researcher")
        self.assertEqual(result.data["worker"]["messages_processed"], 1)


if __name__ == "__main__":
    unittest.main()
