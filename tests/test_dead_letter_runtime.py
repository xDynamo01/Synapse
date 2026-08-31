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


def update_agent_config(settings: Settings, agent_id: str, **updates) -> None:
    path = settings.data_dir / "agents" / agent_id / "CONFIG.yaml"
    config = load_structured_file(path)
    config.update(updates)
    write_json(path, config)


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
        "system": {"name": "Synapse V2 Dead Letter Test", "mode": "test"},
        "models": {"default_provider": "mock", "providers": {"mock": {"model": "synapse-test"}}},
    }
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)
    seed_delegation_pair(settings.data_dir)
    update_agent_config(
        settings,
        "artemis",
        permissions=DEFAULT_PERMISSIONS,
        capabilities={"allow": ["agent.task.delegation"], "deny": []},
    )
    update_agent_config(settings, "researcher", permissions=DEFAULT_PERMISSIONS)
    return directory, create_runtime(settings)


def create_task(runtime, title: str = "Problematic delegation"):
    return runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title=title,
        description="Needs manual handling.",
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
    )


class DeadLetterRuntimeTests(unittest.TestCase):
    def test_create_entry(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)

        entry = runtime.dead_letter.create_entry(task.task_id, reason="manual_move")

        self.assertEqual(entry.task_id, task.task_id)
        self.assertEqual(entry.status, "open")
        self.assertTrue(runtime.data_dir.resolve(f"dead_letter/{entry.dlq_id}.yaml").exists())

    def test_list_entries(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        entry = runtime.dead_letter.create_entry(task.task_id)

        entries = runtime.dead_letter.list_entries()

        self.assertEqual([item.dlq_id for item in entries], [entry.dlq_id])
        self.assertEqual(runtime.dead_letter.list_open_entries()[0].dlq_id, entry.dlq_id)

    def test_review_restore_close_entry(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        entry = runtime.dead_letter.create_entry(task.task_id)

        reviewed = runtime.dead_letter.review_entry(entry.dlq_id)
        self.assertEqual(reviewed.status, "reviewed")
        restored = runtime.dead_letter.restore_entry(entry.dlq_id)
        self.assertEqual(restored.status, "restored")
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "accepted")

        second_task = create_task(runtime, title="Close task")
        second = runtime.dead_letter.create_entry(second_task.task_id)
        closed = runtime.dead_letter.close_entry(second.dlq_id)
        self.assertEqual(closed.status, "closed")

    def test_task_exits_operational_flow(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)

        runtime.dead_letter.move_to_dead_letter(task.task_id)

        self.assertEqual(runtime.delegation_inbox.get_pending_tasks("researcher"), [])
        self.assertEqual(runtime.delegation_inbox.get_active_tasks("researcher"), [])
        self.assertIsNone(runtime.worker.process_next_delegation(runtime.context(), "researcher"))

    def test_restored_task_returns_to_flow(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        entry = runtime.dead_letter.move_to_dead_letter(task.task_id)

        runtime.dead_letter.restore_entry(entry.dlq_id)

        active = runtime.delegation_inbox.get_active_tasks("researcher")
        self.assertEqual([item.task_id for item in active], [task.task_id])
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "accepted")

    def test_health_and_readiness_include_dead_letter(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        for index in range(3):
            task = create_task(runtime, title=f"DLQ {index}")
            runtime.dead_letter.create_entry(task.task_id)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertEqual(health.dead_letter_open_count, 3)
        self.assertIn("dead_letter.open", [check.id for check in readiness.checks])

    def test_scheduler_review_scan_job(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        runtime.dead_letter.create_entry(task.task_id)

        runtime.scheduler.enqueue(runtime.context(), "dead_letter_review_scan", {})
        completed = runtime.scheduler.run_next(runtime.context())

        self.assertEqual(completed.status, "completed")

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)

        moved = runtime.commands.execute(runtime.context(), f"/move-to-dead-letter {task.task_id}")
        self.assertEqual(moved.status, "ok")
        dlq_id = moved.data["entry"]["dlq_id"]
        listed = runtime.commands.execute(runtime.context(), "/dead-letter")
        self.assertEqual(listed.status, "ok")
        reviewed = runtime.commands.execute(runtime.context(), f"/review-dead-letter {dlq_id}")
        self.assertEqual(reviewed.data["entry"]["status"], "reviewed")
        restored = runtime.commands.execute(runtime.context(), f"/restore-dead-letter {dlq_id}")
        self.assertEqual(restored.data["entry"]["status"], "restored")

    def test_api_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:
            self.skipTest(f"FastAPI unavailable: {exc}")
        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        created = client.post("/api/dead-letter", json={"task_id": task.task_id})
        self.assertEqual(created.status_code, 200)
        dlq_id = created.json()["dlq_id"]
        self.assertEqual(client.get("/api/dead-letter").status_code, 200)
        self.assertEqual(client.get(f"/api/dead-letter/{dlq_id}").status_code, 200)
        self.assertEqual(client.post(f"/api/dead-letter/{dlq_id}/review").status_code, 200)
        self.assertEqual(client.post(f"/api/dead-letter/{dlq_id}/restore").status_code, 200)


if __name__ == "__main__":
    unittest.main()
