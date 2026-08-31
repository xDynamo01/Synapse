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
        "system": {"name": "Synapse V2 Mission Control Test", "mode": "test"},
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


def create_mission(runtime, title: str = "Mission Control mission"):
    return runtime.missions.create_mission(
        title=title,
        description="Mission control facade test.",
        status="active",
        priority="high",
        owner_agent_id="artemis",
    )


def create_task(runtime, mission_id: str, priority: str = "high"):
    task = runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title="Mission control task",
        description="Do work.",
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
        priority=priority,
        mission_id=mission_id,
    )
    runtime.missions.link_task(mission_id, task.task_id)
    return task


class MissionControlRuntimeTests(unittest.TestCase):
    def test_overview_with_healthy_mission(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.delegation.complete_task(runtime.context(), task.task_id, result="done")

        overview = runtime.mission_control.get_overview()

        self.assertEqual(overview.total_missions, 1)
        self.assertEqual(overview.warning_missions, 0)
        self.assertEqual(overview.critical_missions, 0)
        self.assertEqual(overview.mission_cards[0]["health"], "healthy")

    def test_overview_with_warning_mission(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.delegation.fail_task(runtime.context(), task.task_id, reason="failed")

        overview = runtime.mission_control.get_overview()

        self.assertEqual(overview.warning_missions, 1)
        self.assertEqual(overview.attention_required_count, 1)

    def test_overview_with_critical_mission(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.dead_letter.move_to_dead_letter(task.task_id)

        overview = runtime.mission_control.get_overview()

        self.assertEqual(overview.critical_missions, 1)
        self.assertEqual(overview.mission_cards[0]["dlq_tasks"], 1)

    def test_mission_card(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.delegation.complete_task(runtime.context(), task.task_id, result="done")

        card = runtime.mission_control.get_mission_card(mission.mission_id)

        self.assertEqual(card.mission_id, mission.mission_id)
        self.assertEqual(card.progress_percent, 100.0)
        self.assertEqual(card.completed_tasks, 1)

    def test_attention_panel(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.dead_letter.move_to_dead_letter(task.task_id)

        panel = runtime.mission_control.get_attention_panel()

        self.assertGreaterEqual(panel.total_items, 1)
        self.assertIn("dead_letter_present", [item["attention_type"] for item in panel.items])

    def test_work_queue(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)

        queue = runtime.mission_control.get_work_queue("researcher")

        self.assertEqual(queue.agent_id, "researcher")
        self.assertEqual(queue.total_items, 1)
        self.assertEqual(queue.items[0]["task_id"], task.task_id)

    def test_agent_workload(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        create_task(runtime, mission.mission_id)

        workload = runtime.mission_control.get_agent_workload()

        agents = {agent["agent_id"]: agent for agent in workload.agents}
        self.assertIn("researcher", agents)
        self.assertEqual(agents["researcher"]["pending_tasks"], 1)

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        create_task(runtime, mission.mission_id)

        overview = runtime.commands.execute(runtime.context(), "/mission-control")
        card = runtime.commands.execute(runtime.context(), f"/mission-control-card {mission.mission_id}")
        attention = runtime.commands.execute(runtime.context(), "/mission-control-attention")
        queue = runtime.commands.execute(runtime.context(), "/mission-control-work-queue researcher")

        self.assertEqual(overview.status, "ok")
        self.assertEqual(card.status, "ok")
        self.assertEqual(attention.status, "ok")
        self.assertEqual(queue.status, "ok")
        self.assertEqual(queue.data["work_queue"]["total_items"], 1)

    def test_api_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:
            self.skipTest(f"FastAPI unavailable: {exc}")
        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        create_task(runtime, mission.mission_id)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        self.assertEqual(client.get("/api/mission-control/overview").status_code, 200)
        self.assertEqual(
            client.get(f"/api/mission-control/missions/{mission.mission_id}").status_code,
            200,
        )
        self.assertEqual(client.get("/api/mission-control/attention").status_code, 200)
        self.assertEqual(client.get("/api/mission-control/work-queue?agent_id=researcher").status_code, 200)
        self.assertEqual(client.get("/api/mission-control/agents/workload").status_code, 200)


if __name__ == "__main__":
    unittest.main()
