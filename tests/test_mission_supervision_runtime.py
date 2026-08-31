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
        "system": {"name": "Synapse V2 Mission Supervision Test", "mode": "test"},
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


def create_mission(runtime, title: str = "Supervised mission"):
    return runtime.missions.create_mission(
        title=title,
        description="Supervise mission state.",
        status="active",
        priority="high",
        owner_agent_id="artemis",
    )


def create_task(runtime, mission_id: str):
    task = runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title="Mission supervision task",
        description="Do work.",
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
        priority="high",
        mission_id=mission_id,
    )
    runtime.missions.link_task(mission_id, task.task_id)
    return task


class MissionSupervisionRuntimeTests(unittest.TestCase):
    def test_healthy_mission(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.delegation.complete_task(runtime.context(), task.task_id, result="done")

        state = runtime.mission_supervision.evaluate_mission(mission.mission_id)

        self.assertEqual(state.severity, "healthy")
        self.assertFalse(state.attention_required)

    def test_warning_mission(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.delegation_execution.create_execution(task.task_id)
        runtime.delegation.fail_task(runtime.context(), task.task_id, reason="failed")

        state = runtime.mission_supervision.evaluate_mission(mission.mission_id)

        self.assertEqual(state.severity, "warning")
        self.assertTrue(state.attention_required)

    def test_critical_mission(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.dead_letter.move_to_dead_letter(task.task_id)

        state = runtime.mission_supervision.evaluate_mission(mission.mission_id)

        self.assertEqual(state.severity, "critical")
        self.assertTrue(state.attention_required)

    def test_dlq_generates_attention_item(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.dead_letter.move_to_dead_letter(task.task_id)

        items = runtime.mission_supervision.list_attention_items()

        self.assertIn("dead_letter_present", [item.attention_type for item in items])

    def test_recovery_generates_attention_item(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.delegation_execution.create_execution(task.task_id)
        runtime.delegation.fail_task(runtime.context(), task.task_id, reason="failed")

        items = runtime.mission_supervision.list_attention_items()

        self.assertIn("recovery_required", [item.attention_type for item in items])

    def test_summary_aggregates_missions(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        healthy = create_mission(runtime, "Healthy mission")
        healthy_task = create_task(runtime, healthy.mission_id)
        runtime.delegation.complete_task(runtime.context(), healthy_task.task_id, result="done")
        warning = create_mission(runtime, "Warning mission")
        warning_task = create_task(runtime, warning.mission_id)
        runtime.delegation.fail_task(runtime.context(), warning_task.task_id, reason="failed")
        critical = create_mission(runtime, "Critical mission")
        critical_task = create_task(runtime, critical.mission_id)
        runtime.dead_letter.move_to_dead_letter(critical_task.task_id)

        summary = runtime.mission_supervision.build_summary()

        self.assertEqual(summary.total_missions, 3)
        self.assertEqual(summary.healthy_missions, 1)
        self.assertEqual(summary.warning_missions, 1)
        self.assertEqual(summary.critical_missions, 1)
        self.assertEqual(summary.attention_required_count, 2)

    def test_mission_status(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)

        state = runtime.mission_supervision.mission_status(mission.mission_id)

        self.assertEqual(state.mission_id, mission.mission_id)
        self.assertEqual(state.status, "active")

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.dead_letter.move_to_dead_letter(task.task_id)

        supervision = runtime.commands.execute(runtime.context(), "/mission-supervision")
        attention = runtime.commands.execute(runtime.context(), "/mission-attention")
        status = runtime.commands.execute(runtime.context(), f"/mission-status {mission.mission_id}")

        self.assertEqual(supervision.status, "ok")
        self.assertEqual(attention.status, "ok")
        self.assertEqual(status.data["state"]["severity"], "critical")

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
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        self.assertEqual(client.get("/api/mission-supervision").status_code, 200)
        self.assertEqual(client.get("/api/mission-attention").status_code, 200)
        self.assertEqual(client.get(f"/api/missions/{mission.mission_id}/status").status_code, 200)

    def test_health_and_readiness_include_supervision(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.dead_letter.move_to_dead_letter(task.task_id)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertEqual(health.missions_critical_count, 1)
        self.assertIn("missions.require_attention", [check.id for check in readiness.checks])


if __name__ == "__main__":
    unittest.main()
