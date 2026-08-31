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
    "delegation.create",
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
            "name": "Synapse V2 Delegation Worker Test",
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
        delegate_extra={
            "permissions": DEFAULT_PERMISSIONS,
            "preferred_tools": ["web_search", "read_file", "send_agent_message"],
            "forbidden_tools": ["write_file"],
        },
    )
    return directory, settings, create_runtime(settings)


def create_conversation(runtime):
    return runtime.conversations.create_conversation(
        runtime.context(),
        ["artemis", "researcher"],
        title="Delegation worker",
    )


def create_delegation(runtime, conversation_id: str | None = None):
    return runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title="Research task",
        description="Prepare a concise response.",
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
        conversation_id=conversation_id,
    )


class DelegationAwareWorkerTests(unittest.TestCase):
    def test_worker_finds_pending_delegation_but_does_not_auto_accept_manual_autonomy(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)

        results = runtime.worker.process_delegations(runtime.context(), "researcher")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].task_id, task.task_id)
        self.assertEqual(results[0].action, "skipped_pending")
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "pending")

    def test_accepted_delegation_becomes_in_progress(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)
        runtime.delegation.accept_task(runtime.context(), task.task_id)

        results = runtime.worker.process_delegations(runtime.context(), "researcher")

        self.assertEqual(results[0].action, "started")
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "in_progress")

    def test_in_progress_delegation_calls_agent_runtime_and_creates_conversation_message(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = create_conversation(runtime)
        task = create_delegation(runtime, conversation.conversation_id)
        runtime.delegation.accept_task(runtime.context(), task.task_id)
        runtime.delegation.start_task(runtime.context(), task.task_id)

        results = runtime.worker.process_delegations(runtime.context(), "researcher")
        messages = runtime.conversations.list_conversation_messages(conversation.conversation_id)

        self.assertEqual(results[0].action, "responded")
        self.assertIn("Mock response for researcher", results[0].response)
        self.assertIsNotNone(results[0].message)
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "in_progress")
        self.assertTrue(
            any(message.payload.get("subject", "").startswith("Delegation response") for message in messages)
        )
        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("worker.delegation.loaded", event_types)
        self.assertIn("worker.delegation.response_created", event_types)

    def test_archived_agent_does_not_process_delegation(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        create_delegation(runtime)
        runtime.admin.archive_agent("researcher", runtime.context(), _skip_policy=True)

        with self.assertRaisesRegex(Exception, "archived"):
            runtime.worker.process_delegations(runtime.context(), "researcher")

    def test_scheduler_job_processes_delegations(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)
        runtime.delegation.accept_task(runtime.context(), task.task_id)
        runtime.scheduler.enqueue(
            runtime.context(),
            "process_agent_delegations",
            {"agent_id": "researcher"},
        )

        completed = runtime.scheduler.run_next(runtime.context())

        self.assertEqual(completed.status, "completed")
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "in_progress")

    def test_command_process_delegations_and_enqueue(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)
        runtime.delegation.accept_task(runtime.context(), task.task_id)

        processed = runtime.commands.execute(runtime.context(), "/process-delegations researcher")
        enqueued = runtime.commands.execute(runtime.context(), "/enqueue-delegations researcher")

        self.assertEqual(processed.status, "ok")
        self.assertEqual(processed.data["results"][0]["action"], "started")
        self.assertEqual(enqueued.status, "ok")
        self.assertEqual(enqueued.data["job"]["type"], "process_agent_delegations")

    def test_api_process_and_enqueue_delegations(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)
        runtime.delegation.accept_task(runtime.context(), task.task_id)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        processed = client.post("/api/agents/researcher/process-delegations", json={"limit": 1})
        enqueued = client.post("/api/agents/researcher/enqueue-delegations", json={"limit": 1})

        self.assertEqual(processed.status_code, 200)
        self.assertEqual(processed.json()[0]["action"], "started")
        self.assertEqual(enqueued.status_code, 200)
        self.assertEqual(enqueued.json()["type"], "process_agent_delegations")


if __name__ == "__main__":
    unittest.main()
