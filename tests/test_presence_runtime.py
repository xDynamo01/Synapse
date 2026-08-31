from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from factories.agents import seed_delegation_pair
from synapse.core.app import create_runtime
from synapse.core.config import Settings

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
    permissions = {
        "subjects": {
            "local_owner": ["*"],
            "user:local_owner": ["*"],
            "agent:artemis": DEFAULT_PERMISSIONS,
            "agent:researcher": DEFAULT_PERMISSIONS,
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Presence Test",
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
    seed_delegation_pair(
        settings.data_dir,
        delegator_extra={"permissions": DEFAULT_PERMISSIONS},
        delegate_extra={"permissions": DEFAULT_PERMISSIONS},
    )
    return directory, settings, create_runtime(settings)


def send_message(runtime, to_agent: str = "researcher", body: str = "Process me"):
    return runtime.communication.send_agent_message(
        runtime.context(),
        from_agent_id="artemis",
        to_agent_id=to_agent,
        subject="Presence test",
        body=body,
    )


class PresenceRuntimeTests(unittest.TestCase):
    def test_set_state_persists_presence(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        presence = runtime.presence.set_state(
            "artemis",
            "thinking",
            "Testing presence",
            {"current_session_id": "session-1"},
        )

        self.assertEqual(presence.state, "thinking")
        self.assertEqual(presence.current_session_id, "session-1")
        self.assertTrue(runtime.data_dir.resolve("presence/artemis.yaml").exists())

    def test_get_after_recreating_runtime_keeps_state(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.presence.set_state("artemis", "working", "Before restart")

        restarted = create_runtime(settings)
        presence = restarted.presence.get("artemis")

        self.assertEqual(presence.state, "working")
        self.assertEqual(presence.activity, "Before restart")

    def test_list_all_returns_agents_with_presence(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.presence.set_state("artemis", "idle")
        runtime.presence.set_state("researcher", "working")

        presences = runtime.presence.list_all()

        self.assertEqual([presence.agent_id for presence in presences], ["artemis", "researcher"])

    def test_chat_updates_artemis_presence(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(runtime.context(), "artemis", "Hello")
        presence = runtime.presence.get("artemis")

        self.assertEqual(presence.state, "idle")
        self.assertEqual(presence.current_session_id, result.session_id)
        event_types = [event.type for event in runtime.events.tail(limit=120)]
        self.assertIn("presence.updated", event_types)

    def test_approval_pending_sets_agent_waiting_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:write_file path=projects/presence-approval.txt content=blocked",
        )
        approval_id = result.message.metadata["tool_results"][0]["approval_id"]
        presence = runtime.presence.get("artemis")

        self.assertEqual(presence.state, "waiting_approval")
        self.assertEqual(presence.current_approval_id, approval_id)

    def test_worker_updates_presence_during_processing(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        send_message(runtime)

        runtime.worker.process_inbox(runtime.context(), "researcher")
        presence = runtime.presence.get("researcher")

        self.assertEqual(presence.state, "idle")
        event_payloads = [
            event.payload
            for event in runtime.events.tail(limit=160)
            if event.type == "presence.updated"
            and event.payload.get("agent_id") == "researcher"
        ]
        self.assertIn("working", [payload["state"] for payload in event_payloads])

    def test_presence_updated_event_includes_correlation_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.chat.send_message(runtime.context(), "artemis", "Correlated presence")

        event = next(
            event
            for event in runtime.events.tail(limit=120)
            if event.type == "presence.updated" and event.payload["agent_id"] == "artemis"
        )
        self.assertIsNotNone(event.correlation_id)
        self.assertEqual(event.payload["correlation_id"], event.correlation_id)

    def test_presence_command_returns_states(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.presence.set_state("artemis", "idle")

        all_result = runtime.commands.execute(runtime.context(), "/presence")
        agent_result = runtime.commands.execute(runtime.context(), "/presence artemis")

        self.assertEqual(all_result.status, "ok")
        self.assertEqual(agent_result.status, "ok")
        self.assertEqual(agent_result.data["presence"]["state"], "idle")

    def test_presence_api_works(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.presence.set_state("artemis", "idle")
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        listed = client.get("/api/presence")
        artemis = client.get("/api/presence/artemis")

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(artemis.status_code, 200)
        self.assertEqual(artemis.json()["state"], "idle")


if __name__ == "__main__":
    unittest.main()
