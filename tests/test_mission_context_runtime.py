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
        "system": {"name": "Synapse V2 Mission Context Test", "mode": "test"},
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


def create_mission(runtime, conversation_id: str | None = None):
    return runtime.missions.create_mission(
        title="Mission context",
        description="Consolidate mission state.",
        status="active",
        priority="high",
        owner_agent_id="artemis",
        conversation_id=conversation_id,
    )


def create_task(runtime, mission_id: str, conversation_id: str | None = None):
    task = runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title="Mission task",
        description="Do mission work.",
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
        priority="high",
        mission_id=mission_id,
        conversation_id=conversation_id,
    )
    runtime.missions.link_task(mission_id, task.task_id)
    return task


class MissionContextRuntimeTests(unittest.TestCase):
    def test_empty_mission_context(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)

        context = runtime.mission_context.build_context(mission.mission_id)

        self.assertEqual(context.delegation_count, 0)
        self.assertEqual(context.summary.progress_percent, 0.0)
        self.assertEqual(context.summary.health, "healthy")

    def test_mission_with_tasks_and_progress(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        completed = create_task(runtime, mission.mission_id)
        pending = create_task(runtime, mission.mission_id)
        runtime.delegation.complete_task(runtime.context(), completed.task_id, result="done")

        context = runtime.mission_context.build_context(mission.mission_id)

        self.assertEqual(context.delegation_count, 2)
        self.assertEqual(context.summary.progress_percent, 50.0)
        self.assertEqual([task["task_id"] for task in context.completed_tasks], [completed.task_id])
        self.assertEqual([task["task_id"] for task in context.pending_tasks], [pending.task_id])

    def test_health_healthy(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.delegation.complete_task(runtime.context(), task.task_id, result="done")

        self.assertEqual(runtime.mission_context.mission_health(mission.mission_id), "healthy")

    def test_health_warning_for_failed_task(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.delegation_execution.create_execution(task.task_id)
        runtime.delegation.fail_task(runtime.context(), task.task_id, reason="failed")

        context = runtime.mission_context.build_context(mission.mission_id)

        self.assertEqual(context.summary.health, "warning")
        self.assertEqual(len(context.recovery_candidates), 1)

    def test_health_critical_for_dlq_and_recovery(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.dead_letter.move_to_dead_letter(task.task_id)

        context = runtime.mission_context.build_context(mission.mission_id)

        self.assertEqual(context.summary.health, "critical")
        self.assertEqual(context.dlq_count, 1)
        self.assertEqual(len(context.recovery_candidates), 1)

    def test_conversations_linked(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = runtime.conversations.create_conversation(
            runtime.context(),
            ["artemis", "researcher"],
            title="Mission conversation",
        )
        mission = create_mission(runtime, conversation_id=conversation.conversation_id)
        create_task(runtime, mission.mission_id, conversation_id=conversation.conversation_id)

        context = runtime.mission_context.build_context(mission.mission_id)

        self.assertEqual(len(context.linked_conversations), 1)
        self.assertEqual(
            context.linked_conversations[0]["conversation"]["conversation_id"],
            conversation.conversation_id,
        )

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.dead_letter.move_to_dead_letter(task.task_id)

        context = runtime.commands.execute(runtime.context(), f"/mission-context {mission.mission_id}")
        health = runtime.commands.execute(runtime.context(), f"/mission-health {mission.mission_id}")
        recovery = runtime.commands.execute(runtime.context(), f"/mission-recovery {mission.mission_id}")

        self.assertEqual(context.status, "ok")
        self.assertEqual(context.data["context"]["summary"]["health"], "critical")
        self.assertEqual(health.data["health"], "critical")
        self.assertEqual(len(recovery.data["recovery_candidates"]), 1)

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

        self.assertEqual(client.get(f"/api/missions/{mission.mission_id}/context").status_code, 200)
        self.assertEqual(client.get(f"/api/missions/{mission.mission_id}/health").status_code, 200)
        self.assertEqual(client.get(f"/api/missions/{mission.mission_id}/recovery").status_code, 200)

    def test_health_and_readiness_include_critical_missions(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        mission = create_mission(runtime)
        task = create_task(runtime, mission.mission_id)
        runtime.dead_letter.move_to_dead_letter(task.task_id)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertEqual(health.missions_with_critical_context, 1)
        self.assertIn("missions.context_critical", [check.id for check in readiness.checks])


if __name__ == "__main__":
    unittest.main()
