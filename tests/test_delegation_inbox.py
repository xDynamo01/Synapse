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
from synapse.core.serialization import load_structured_file

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
            "name": "Synapse V2 Delegation Inbox Test",
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
    return directory, create_runtime(settings)


def create_delegation(runtime):
    return runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title="Indexed work",
        description="Track this in the delegation inbox.",
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
    )


class DelegationInboxAgentRegistryTests(unittest.TestCase):
    def test_agent_registry_infers_missing_agent_id_from_path(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        config_path = runtime.data_dir.resolve("agents/researcher/CONFIG.yaml")
        raw = load_structured_file(config_path)
        raw.pop("id", None)
        write_json(config_path, raw)

        agent = runtime.agents.get("researcher")

        self.assertEqual(agent.id, "researcher")


class DelegationInboxRuntimeTests(unittest.TestCase):
    def test_create_inbox_from_delegation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)

        entries = runtime.delegation_inbox.get_agent_inbox("researcher")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].task_id, task.task_id)
        self.assertEqual(entries[0].status, "pending")
        self.assertTrue(runtime.data_dir.resolve("delegation_inbox/researcher.yaml").exists())

    def test_pending_task_appears_in_inbox(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)

        pending = runtime.delegation_inbox.get_pending_tasks("researcher")

        self.assertEqual([entry.task_id for entry in pending], [task.task_id])

    def test_accepted_task_updates_inbox(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)

        runtime.delegation.accept_task(runtime.context(), task.task_id)
        summary = runtime.delegation_inbox.get_inbox_summary("researcher")

        self.assertEqual(summary.accepted_count, 1)
        self.assertEqual(summary.pending_count, 0)

    def test_in_progress_task_updates_inbox(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)

        runtime.delegation.accept_task(runtime.context(), task.task_id)
        runtime.delegation.start_task(runtime.context(), task.task_id)
        summary = runtime.delegation_inbox.get_inbox_summary("researcher")

        self.assertEqual(summary.in_progress_count, 1)

    def test_completed_task_updates_inbox(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)

        runtime.delegation.complete_task(runtime.context(), task.task_id, result="Done")
        summary = runtime.delegation_inbox.get_inbox_summary("researcher")

        self.assertEqual(summary.completed_count, 1)

    def test_failed_task_updates_inbox(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)

        runtime.delegation.fail_task(runtime.context(), task.task_id, reason="Failed")
        summary = runtime.delegation_inbox.get_inbox_summary("researcher")

        self.assertEqual(summary.failed_count, 1)

    def test_rebuild_agent_inbox(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)
        runtime.data_dir.resolve("delegation_inbox/researcher.yaml").unlink()

        entries = runtime.delegation_inbox.rebuild_agent_inbox("researcher")

        self.assertEqual([entry.task_id for entry in entries], [task.task_id])

    def test_rebuild_all_inboxes(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)
        runtime.data_dir.resolve("delegation_inbox/researcher.yaml").unlink()

        rebuilt = runtime.delegation_inbox.rebuild_all_inboxes()

        self.assertIn("researcher", rebuilt)
        self.assertEqual(rebuilt["researcher"][0].task_id, task.task_id)

    def test_inbox_is_not_source_of_truth(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)
        runtime.data_dir.resolve("delegation_inbox/researcher.yaml").write_text(
            '{"agent_id": "researcher", "entries": []}',
            encoding="utf-8",
        )

        loaded = runtime.delegation.get_task(task.task_id)
        entries = runtime.delegation_inbox.get_agent_inbox("researcher")

        self.assertEqual(loaded.task_id, task.task_id)
        self.assertEqual(entries, [])

    def test_corruption_followed_by_rebuild(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)
        runtime.data_dir.resolve("delegation_inbox/researcher.yaml").write_text(
            "entries: [",
            encoding="utf-8",
        )

        status = runtime.delegation_inbox.status()
        entries = runtime.delegation_inbox.rebuild_agent_inbox("researcher")

        self.assertIn("researcher", status["corrupted_agents"])
        self.assertEqual(entries[0].task_id, task.task_id)

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        create_delegation(runtime)

        inbox = runtime.commands.execute(runtime.context(), "/delegation-inbox researcher")
        summary = runtime.commands.execute(runtime.context(), "/delegation-summary researcher")
        rebuild = runtime.commands.execute(runtime.context(), "/rebuild-delegation-inbox researcher")
        rebuild_all = runtime.commands.execute(runtime.context(), "/rebuild-all-delegation-inboxes")

        self.assertEqual(inbox.status, "ok")
        self.assertEqual(summary.data["summary"]["total_count"], 1)
        self.assertEqual(rebuild.status, "ok")
        self.assertEqual(rebuild_all.status, "ok")

    def test_api_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        create_delegation(runtime)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        inbox = client.get("/api/delegation-inbox/researcher")
        summary = client.get("/api/delegation-inbox/researcher/summary")
        rebuild = client.post("/api/delegation-inbox/researcher/rebuild")
        rebuild_all = client.post("/api/delegation-inbox/rebuild-all")

        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(len(inbox.json()), 1)
        self.assertEqual(summary.json()["total_count"], 1)
        self.assertEqual(rebuild.status_code, 200)
        self.assertEqual(rebuild_all.status_code, 200)

    def test_scheduler_job_rebuilds_inbox(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        create_delegation(runtime)
        runtime.data_dir.resolve("delegation_inbox/researcher.yaml").unlink()
        job = runtime.scheduler.enqueue(
            runtime.context(),
            "delegation_inbox_rebuild",
            {"agent_id": "researcher"},
        )

        completed = runtime.scheduler.run_next(runtime.context())

        self.assertEqual(completed.id, job.id)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(runtime.delegation_inbox.get_inbox_summary("researcher").total_count, 1)

    def test_health_includes_delegation_inbox(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        create_delegation(runtime)

        health = runtime.health.summary()

        self.assertTrue(health.delegation_inbox["available"])
        self.assertEqual(health.delegation_inbox["agents_indexed"], 1)


if __name__ == "__main__":
    unittest.main()
