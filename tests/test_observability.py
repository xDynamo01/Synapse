from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from factories.agents import seed_test_agent
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.observability.correlation import correlation_scope, new_correlation

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
    for agent_id, role in (("artemis", "orchestrator"), ("researcher", "researcher")):
        seed_test_agent(
            settings.data_dir,
            agent_id,
            role=role,
            extra={"permissions": DEFAULT_PERMISSIONS},
        )
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
            "name": "Synapse V2 Observability Test",
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
    return directory, settings, create_runtime(settings)


def send_message(runtime):
    return runtime.communication.send_agent_message(
        runtime.context(),
        from_agent_id="artemis",
        to_agent_id="researcher",
        subject="Observability test",
        body="Process me",
    )


class ObservabilityTests(unittest.TestCase):
    def test_chat_creates_correlation_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.chat.send_message(runtime.context(), "artemis", "hello")

        events = runtime.events.tail(limit=80)
        chat_events = [event for event in events if event.type.startswith("chat.")]
        self.assertTrue(chat_events)
        correlation_ids = {event.correlation_id for event in chat_events}
        self.assertEqual(len(correlation_ids), 1)
        self.assertIsNotNone(next(iter(correlation_ids)))

    def test_tool_call_preserves_chat_correlation_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.chat.send_message(runtime.context(), "artemis", "tool:read_file path=memory/MEMORY.md")

        events = runtime.events.tail(limit=120)
        chat_event = next(event for event in events if event.type == "chat.message_received")
        tool_event = next(event for event in events if event.type == "tool.executed")
        self.assertEqual(tool_event.correlation_id, chat_event.correlation_id)

    def test_approval_created_has_same_correlation_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:write_file path=projects/observe.txt content=blocked",
        )

        events = runtime.events.tail(limit=120)
        chat_event = next(event for event in events if event.type == "chat.message_received")
        approval_event = next(event for event in events if event.type == "approval.requested")
        self.assertEqual(approval_event.correlation_id, chat_event.correlation_id)

    def test_job_process_agent_inbox_has_traceable_correlation_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        send_message(runtime)
        job = runtime.scheduler.enqueue(
            runtime.context(),
            "process_agent_inbox",
            {"agent_id": "researcher"},
        )

        runtime.scheduler.run_next(runtime.context())

        events = runtime.events.trace(job.correlation_id)
        event_types = [event.type for event in events]
        self.assertIn("job.started", event_types)
        self.assertIn("worker.message_processed", event_types)

    def test_daemon_tick_generates_correlation_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.daemon.run_once(runtime.context())

        tick = next(event for event in runtime.events.tail(limit=50) if event.type == "daemon.tick")
        self.assertIsNotNone(tick.correlation_id)
        self.assertEqual(tick.source, "daemon")

    def test_trace_command_returns_flow_events(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.chat.send_message(runtime.context(), "artemis", "hello trace")
        correlation_id = next(
            event.correlation_id
            for event in runtime.events.tail(limit=80)
            if event.type == "chat.message_received"
        )

        result = runtime.commands.execute(runtime.context(), f"/trace {correlation_id}")

        self.assertEqual(result.status, "ok")
        event_types = [event["type"] for event in result.data["events"]]
        self.assertIn("chat.message_received", event_types)
        self.assertIn("chat.session_persisted", event_types)

    def test_trace_api_returns_flow_events(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.chat.send_message(runtime.context(), "artemis", "hello api trace")
        correlation_id = next(
            event.correlation_id
            for event in runtime.events.tail(limit=80)
            if event.type == "chat.message_received"
        )
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).get(f"/api/trace/{correlation_id}")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()["events"]), 1)
        self.assertEqual(response.json()["events"][0]["correlation_id"], correlation_id)

    def test_legacy_events_without_correlation_do_not_break_reading(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        with runtime.events.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "id": "legacy-event",
                        "type": "legacy.event",
                        "actor_id": "legacy",
                        "payload": {},
                        "timestamp": "2026-06-14T00:00:00+00:00",
                    }
                )
                + "\n"
            )

        events = runtime.events.tail(limit=10)

        legacy = next(event for event in events if event.id == "legacy-event")
        self.assertIsNone(legacy.correlation_id)
        self.assertEqual(legacy.source, "legacy")

    def test_create_task_persists_correlation_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        correlation = new_correlation(source="test")

        with correlation_scope(correlation):
            task = runtime.tasks.create_task(runtime.context(), "Correlated task")

        persisted = runtime.tasks.get_task(task.id)
        self.assertEqual(persisted.correlation_id, correlation.correlation_id)
        self.assertEqual(persisted.source, "test")

    def test_send_agent_message_persists_correlation_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        correlation = new_correlation(source="test")

        with correlation_scope(correlation):
            message = send_message(runtime)

        persisted = runtime.communication.list_messages(runtime.context(), "researcher")[0]
        self.assertEqual(persisted.id, message.id)
        self.assertEqual(persisted.correlation_id, correlation.correlation_id)

    def test_approval_request_persists_correlation_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        correlation = new_correlation(source="test")

        with correlation_scope(correlation):
            approval = runtime.approvals.create_request(
                context=runtime.context(actor_id="artemis", actor_type="agent"),
                tool_name="write_file",
                tool_args={"path": "projects/a.txt"},
                risk_level="high",
                reason="test",
                tool_call_id="tool-call",
            )

        persisted = runtime.approvals.get_status(approval.id)
        self.assertEqual(persisted.correlation_id, correlation.correlation_id)
        self.assertEqual(persisted.source, "test")

    def test_job_persists_correlation_metadata(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        correlation = new_correlation(source="test", causation_id="cause", parent_id="parent")

        with correlation_scope(correlation):
            job = runtime.scheduler.enqueue(
                runtime.context(),
                "process_agent_inbox",
                {"agent_id": "researcher"},
            )

        persisted = runtime.scheduler.get_job(job.id)
        self.assertEqual(persisted.correlation_id, correlation.correlation_id)
        self.assertEqual(persisted.causation_id, "cause")
        self.assertEqual(persisted.parent_id, "parent")
        self.assertEqual(persisted.source, "test")

    def test_chat_session_message_persists_correlation_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(runtime.context(), "artemis", "durable chat")
        session = runtime.chat.get_session(result.session_id)

        self.assertIsNotNone(session.correlation_id)
        self.assertTrue(all(message.correlation_id for message in session.messages))
        self.assertEqual(session.messages[0].correlation_id, session.messages[1].correlation_id)

    def test_trace_includes_durable_records(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        result = runtime.chat.send_message(runtime.context(), "artemis", "trace records")
        correlation_id = runtime.chat.get_session(result.session_id).correlation_id

        trace = runtime.commands.execute(runtime.context(), f"/trace {correlation_id}")

        self.assertEqual(trace.status, "ok")
        kinds = {record["kind"] for record in trace.data["records"]}
        self.assertIn("chat_session", kinds)
        self.assertIn("chat_message", kinds)

    def test_legacy_durable_records_without_correlation_still_load(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task_path = runtime.data_dir.resolve("tasks/active/legacy-task.json")
        task_path.write_text(
            json.dumps(
                {
                    "id": "legacy-task",
                    "title": "Legacy",
                    "created_by": "legacy",
                    "description": "",
                    "status": "active",
                    "metadata": {},
                    "created_at": "2026-06-14T00:00:00+00:00",
                    "updated_at": "2026-06-14T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )

        task = runtime.tasks.get_task("legacy-task")

        self.assertIsNone(task.correlation_id)


if __name__ == "__main__":
    unittest.main()
