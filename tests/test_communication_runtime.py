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
    "communication.read",
    "communication.summarize",
    "communication.draft",
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
            "agent:hermes": DEFAULT_PERMISSIONS,
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Communication Test",
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


class CommunicationRuntimeTests(unittest.TestCase):
    def test_mock_provider_returns_emails(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        messages = runtime.communication_runtime.list_messages()

        self.assertGreaterEqual(len(messages), 4)
        self.assertIn("Amazon", messages[0].subject)

    def test_read_message_works(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        message = runtime.communication_runtime.read_message("mock-amazon-recruitment")

        self.assertEqual(message.id, "mock-amazon-recruitment")
        self.assertEqual(message.provider, "mock")

    def test_classify_message_works(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        classification = runtime.communication_runtime.classify_message("mock-rws-project")

        self.assertEqual(classification["category"], "project")

    def test_summarize_message_works(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        summary = runtime.communication_runtime.summarize_message("mock-amazon-recruitment")

        self.assertIn("applying", summary["summary"].lower())

    def test_create_and_list_drafts_work(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        draft = runtime.communication_runtime.create_draft(
            subject="Reply to recruiter",
            recipients=["recruiting@amazon.example"],
            body="Thanks, I am available.",
            created_by_agent="hermes",
        )
        drafts = runtime.communication_runtime.list_drafts()

        self.assertEqual(draft.status, "draft")
        self.assertEqual(drafts[0].id, draft.id)
        self.assertTrue(
            runtime.data_dir.resolve(f"communication/mock/drafts/{draft.id}.yaml").exists()
        )

    def test_hermes_processes_emails_and_generates_briefing(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        briefing = runtime.communication_runtime.generate_briefing("hermes")

        self.assertEqual(briefing.agent_id, "hermes")
        self.assertGreaterEqual(briefing.total_messages, 4)
        self.assertGreaterEqual(briefing.categories["recruitment"], 1)
        self.assertTrue(briefing.important)
        self.assertEqual(runtime.presence.get("hermes").state, "idle")
        self.assertEqual(runtime.lifecycle.get("hermes").state, "idle")

    def test_scheduler_executes_check_email(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        job = runtime.scheduler.enqueue(
            runtime.context(),
            "check_email",
            {"provider": "mock", "agent_id": "hermes"},
        )

        completed = runtime.scheduler.run_next(runtime.context())

        self.assertEqual(completed.id, job.id)
        self.assertEqual(completed.status, "completed")
        self.assertIn("briefing", completed.payload["result"])

    def test_daemon_executes_check_email(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.scheduler.enqueue(
            runtime.context(),
            "check_email",
            {"provider": "mock", "agent_id": "hermes"},
        )

        status = runtime.daemon.run_once(runtime.context())

        self.assertEqual(len(status.last_jobs_run), 1)
        self.assertEqual(status.last_jobs_run[0]["status"], "completed")

    def test_presence_and_lifecycle_are_updated(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.communication_runtime.generate_briefing("hermes")

        self.assertEqual(runtime.presence.get("hermes").state, "idle")
        lifecycle = runtime.lifecycle.get("hermes")
        self.assertEqual(lifecycle.state, "idle")
        self.assertGreaterEqual(lifecycle.wake_count, 1)
        self.assertGreaterEqual(lifecycle.sleep_count, 1)

    def test_correlation_id_is_preserved(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        correlation = new_correlation(source="test")

        with correlation_scope(correlation):
            briefing = runtime.communication_runtime.generate_briefing("hermes")

        events = runtime.events.trace(correlation.correlation_id)
        self.assertEqual(briefing.correlation_id, correlation.correlation_id)
        self.assertIn("communication.briefing_generated", [event.type for event in events])

    def test_tools_work_through_registry_for_hermes(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        context = runtime.context(actor_id="hermes", actor_type="agent")

        message = runtime.tools.execute(
            "read_email",
            context,
            {"message_id": "mock-amazon-recruitment"},
        )
        draft = runtime.tools.execute(
            "create_email_draft",
            context,
            {
                "subject": "Draft via tool",
                "recipients": ["test@example.local"],
                "body": "Hello",
            },
        )

        self.assertEqual(message["id"], "mock-amazon-recruitment")
        self.assertEqual(draft["status"], "draft")

    def test_commands_work(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        check = runtime.commands.execute(runtime.context(), "/check-email")
        summary = runtime.commands.execute(runtime.context(), "/email-summary")
        read = runtime.commands.execute(runtime.context(), "/email-read mock-amazon-recruitment")
        drafts = runtime.commands.execute(runtime.context(), "/email-drafts")

        self.assertEqual(check.status, "ok")
        self.assertEqual(summary.status, "ok")
        self.assertEqual(read.data["message"]["id"], "mock-amazon-recruitment")
        self.assertEqual(drafts.status, "ok")

    def test_api_works(self) -> None:
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
        client = TestClient(app)

        messages = client.get("/api/communication/messages")
        message = client.get("/api/communication/messages/mock-amazon-recruitment")
        draft = client.post(
            "/api/communication/drafts",
            json={
                "subject": "API draft",
                "recipients": ["api@example.local"],
                "body": "Draft body",
            },
        )
        drafts = client.get("/api/communication/drafts")
        summary = client.get("/api/communication/summary")

        self.assertEqual(messages.status_code, 200)
        self.assertEqual(message.status_code, 200)
        self.assertEqual(draft.status_code, 200)
        self.assertEqual(draft.json()["status"], "draft")
        self.assertEqual(drafts.status_code, 200)
        self.assertEqual(summary.status_code, 200)
        self.assertGreaterEqual(summary.json()["total_messages"], 4)


if __name__ == "__main__":
    unittest.main()
