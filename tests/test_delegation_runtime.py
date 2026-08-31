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


def runtime_in_tempdir(allow_delegation: bool = True):
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    create_runtime(settings)
    requester_permissions = list(DEFAULT_PERMISSIONS)
    if not allow_delegation:
        requester_permissions.remove("delegation.create")
    permissions = {
        "subjects": {
            "local_owner": ["*"],
            "user:local_owner": ["*"],
            "agent:artemis": requester_permissions,
            "agent:researcher": DEFAULT_PERMISSIONS,
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Delegation Test",
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
        delegator_extra={
            "permissions": requester_permissions,
            "capabilities": (
                {"allow": ["agent.task.delegation"], "deny": []}
                if allow_delegation
                else {}
            ),
        },
        delegate_extra={"permissions": DEFAULT_PERMISSIONS},
    )
    return directory, create_runtime(settings)


def create_delegation(runtime, conversation_id: str | None = None):
    return runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title="Research topic",
        description="Find relevant notes.",
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
        priority="high",
        conversation_id=conversation_id,
    )


class DelegationRuntimeTests(unittest.TestCase):
    def test_create_delegation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        task = create_delegation(runtime)

        self.assertEqual(task.status, "pending")
        self.assertEqual(task.priority, "high")
        self.assertTrue(runtime.data_dir.resolve(f"delegation/{task.task_id}.yaml").exists())

    def test_lifecycle_accept_start_complete(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)

        accepted = runtime.delegation.accept_task(runtime.context(), task.task_id)
        started = runtime.delegation.start_task(runtime.context(), task.task_id)
        completed = runtime.delegation.complete_task(runtime.context(), task.task_id, result="Done")

        self.assertEqual(accepted.status, "accepted")
        self.assertEqual(started.status, "in_progress")
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.metadata["result"], "Done")

    def test_reject_and_fail_delegation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        rejected_task = create_delegation(runtime)
        failed_task = create_delegation(runtime)

        rejected = runtime.delegation.reject_task(runtime.context(), rejected_task.task_id, "No")
        failed = runtime.delegation.fail_task(runtime.context(), failed_task.task_id, "Blocked")

        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(rejected.metadata["reason"], "No")
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.metadata["reason"], "Blocked")

    def test_archived_agent_cannot_receive_delegation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.admin.archive_agent("researcher", runtime.context(), _skip_policy=True)

        with self.assertRaisesRegex(Exception, "archived"):
            create_delegation(runtime)

    def test_deactivated_agent_cannot_receive_delegation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.admin.deactivate_agent("researcher", runtime.context(), _skip_policy=True)

        with self.assertRaisesRegex(Exception, "not active"):
            create_delegation(runtime)

    def test_delegation_links_to_conversation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = runtime.conversations.create_conversation(
            runtime.context(),
            ["artemis", "researcher"],
            title="Delegation thread",
        )

        task = create_delegation(runtime, conversation.conversation_id)
        messages = runtime.conversations.list_conversation_messages(conversation.conversation_id)

        self.assertEqual(task.conversation_id, conversation.conversation_id)
        self.assertGreaterEqual(len(messages), 1)
        self.assertEqual(messages[-1].payload["subject"], "Delegation created")

    def test_capability_is_required(self) -> None:
        directory, runtime = runtime_in_tempdir(allow_delegation=False)
        self.addCleanup(directory.cleanup)

        with self.assertRaisesRegex(Exception, "agent.task.delegation"):
            create_delegation(runtime)

    def test_events_are_emitted(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)
        runtime.delegation.accept_task(runtime.context(), task.task_id)
        runtime.delegation.reject_task(runtime.context(), task.task_id)
        runtime.delegation.start_task(runtime.context(), task.task_id)
        runtime.delegation.complete_task(runtime.context(), task.task_id)
        runtime.delegation.fail_task(runtime.context(), task.task_id)
        runtime.delegation.cancel_task(runtime.context(), task.task_id)

        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("delegation.created", event_types)
        self.assertIn("delegation.accepted", event_types)
        self.assertIn("delegation.rejected", event_types)
        self.assertIn("delegation.started", event_types)
        self.assertIn("delegation.completed", event_types)
        self.assertIn("delegation.failed", event_types)
        self.assertIn("delegation.cancelled", event_types)

    def test_commands_work(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        created = runtime.commands.execute(
            runtime.context(actor_id="artemis", actor_type="agent"),
            '/create-delegation artemis researcher "Research topic" "Find notes" --priority high',
        )
        task_id = created.data["delegation"]["task_id"]
        listed = runtime.commands.execute(runtime.context(), "/delegations")
        detail = runtime.commands.execute(runtime.context(), f"/delegation {task_id}")
        accepted = runtime.commands.execute(runtime.context(), f"/accept-delegation {task_id}")
        started = runtime.commands.execute(runtime.context(), f"/start-delegation {task_id}")
        completed = runtime.commands.execute(runtime.context(), f"/complete-delegation {task_id}")

        self.assertEqual(created.status, "ok")
        self.assertEqual(listed.status, "ok")
        self.assertEqual(detail.status, "ok")
        self.assertEqual(accepted.data["delegation"]["status"], "accepted")
        self.assertEqual(started.data["delegation"]["status"], "in_progress")
        self.assertEqual(completed.data["delegation"]["status"], "completed")

    def test_api_works(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        created = client.post(
            "/api/delegations",
            json={
                "title": "Research topic",
                "description": "Find notes.",
                "requester_agent_id": "artemis",
                "assignee_agent_id": "researcher",
                "priority": "normal",
            },
            headers={"x-actor-id": "artemis", "x-actor-type": "agent"},
        )
        task_id = created.json()["task_id"]
        listed = client.get("/api/delegations")
        detail = client.get(f"/api/delegations/{task_id}")
        accepted = client.post(f"/api/delegations/{task_id}/accept")
        started = client.post(f"/api/delegations/{task_id}/start")
        completed = client.post(f"/api/delegations/{task_id}/complete", json={"result": "Done"})

        self.assertEqual(created.status_code, 200)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(accepted.json()["status"], "accepted")
        self.assertEqual(started.json()["status"], "in_progress")
        self.assertEqual(completed.json()["status"], "completed")


if __name__ == "__main__":
    unittest.main()
