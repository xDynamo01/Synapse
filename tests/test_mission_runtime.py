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
        "system": {"name": "Synapse V2 Mission Test", "mode": "test"},
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


def create_mission(runtime, status: str = "active"):
    return runtime.missions.create_mission(
        title="Investigate issue",
        description="Group related delegation work.",
        status=status,
        priority="high",
        owner_agent_id="artemis",
        created_by="local_owner",
    )


def create_delegation(runtime, mission_id: str | None = None):
    return runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title="Research topic",
        description="Find relevant notes.",
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
        priority="high",
        mission_id=mission_id,
    )


class MissionRuntimeTests(unittest.TestCase):
    def test_create_mission(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        mission = create_mission(runtime)

        self.assertEqual(mission.status, "active")
        self.assertEqual(mission.priority, "high")
        self.assertTrue(runtime.data_dir.resolve(f"missions/{mission.mission_id}.yaml").exists())

    def test_get_update_archive_mission(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)

        updated = runtime.missions.update_mission(
            mission.mission_id,
            title="Updated mission",
            status="paused",
        )
        archived = runtime.missions.archive_mission(mission.mission_id)

        self.assertEqual(runtime.missions.get_mission(mission.mission_id).title, "Updated mission")
        self.assertEqual(updated.status, "paused")
        self.assertEqual(archived.status, "archived")

    def test_link_unlink_and_list_mission_tasks(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_delegation(runtime)

        link = runtime.missions.link_task(mission.mission_id, task.task_id)
        listed = runtime.missions.list_mission_tasks(mission.mission_id)
        removed = runtime.missions.unlink_task(mission.mission_id, task.task_id)

        self.assertEqual(link.task_id, task.task_id)
        self.assertEqual([item.task_id for item in listed], [task.task_id])
        self.assertEqual(removed.task_id, task.task_id)
        self.assertEqual(runtime.missions.list_mission_tasks(mission.mission_id), [])

    def test_mission_summary(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        pending = create_delegation(runtime)
        running = create_delegation(runtime)
        failed = create_delegation(runtime)
        dlq = create_delegation(runtime)
        runtime.delegation.accept_task(runtime.context(), running.task_id)
        runtime.delegation.fail_task(runtime.context(), failed.task_id, reason="failed")
        runtime.dead_letter.move_to_dead_letter(dlq.task_id)
        for task in [pending, running, failed, dlq]:
            runtime.missions.link_task(mission.mission_id, task.task_id)

        summary = runtime.missions.summarize_mission(mission.mission_id)

        self.assertEqual(summary.total_tasks, 4)
        self.assertEqual(summary.pending_tasks, 2)
        self.assertEqual(summary.running_tasks, 1)
        self.assertEqual(summary.failed_tasks, 1)
        self.assertEqual(summary.dlq_tasks, 1)

    def test_delegation_can_have_mission_id(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)

        task = create_delegation(runtime, mission_id=mission.mission_id)

        self.assertEqual(task.mission_id, mission.mission_id)
        self.assertEqual(runtime.delegation.get_task(task.task_id).mission_id, mission.mission_id)

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        created = runtime.commands.execute(runtime.context(), '/create-mission "Command mission"')
        mission_id = created.data["mission"]["mission_id"]
        task = create_delegation(runtime)

        link = runtime.commands.execute(
            runtime.context(),
            f"/link-mission-task {mission_id} {task.task_id}",
        )
        summary = runtime.commands.execute(runtime.context(), f"/mission-summary {mission_id}")
        listed = runtime.commands.execute(runtime.context(), "/missions")
        detail = runtime.commands.execute(runtime.context(), f"/mission {mission_id}")

        self.assertEqual(created.status, "ok")
        self.assertEqual(link.status, "ok")
        self.assertEqual(summary.data["summary"]["total_tasks"], 1)
        self.assertEqual(listed.status, "ok")
        self.assertEqual(detail.data["mission"]["mission_id"], mission_id)

    def test_api_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:
            self.skipTest(f"FastAPI unavailable: {exc}")
        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_delegation(runtime)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        created = client.post("/api/missions", json={"title": "API mission", "status": "active"})
        self.assertEqual(created.status_code, 200)
        mission_id = created.json()["mission_id"]
        self.assertEqual(client.get("/api/missions").status_code, 200)
        self.assertEqual(client.get(f"/api/missions/{mission_id}").status_code, 200)
        self.assertEqual(
            client.post(f"/api/missions/{mission_id}/tasks", json={"task_id": task.task_id}).status_code,
            200,
        )
        self.assertEqual(client.get(f"/api/missions/{mission_id}/tasks").status_code, 200)
        self.assertEqual(client.get(f"/api/missions/{mission_id}/summary").status_code, 200)

    def test_health_includes_active_missions(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        create_mission(runtime)

        health = runtime.health.summary()

        self.assertEqual(health.active_missions_count, 1)


if __name__ == "__main__":
    unittest.main()
