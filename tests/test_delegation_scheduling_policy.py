from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
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
            "name": "Synapse V2 Delegation Scheduling Test",
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


def create_task(runtime, title: str, priority: str = "normal", due_at: str | None = None):
    return runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title=title,
        description=title,
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
        priority=priority,
        due_at=due_at,
    )


class DelegationSchedulingPolicyTests(unittest.TestCase):
    def test_load_default_policy(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        policy = runtime.delegation_scheduling.load_policy()

        self.assertTrue(policy.enabled)
        self.assertEqual(policy.priority_weights["critical"], 400)

    def test_critical_comes_before_normal(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        normal = create_task(runtime, "Normal", "normal")
        critical = create_task(runtime, "Critical", "critical")

        decision = runtime.delegation_scheduling.select_next_task(
            "researcher",
            [normal, critical],
        )

        self.assertEqual(decision.selected_task_id, critical.task_id)

    def test_overdue_due_at_increases_priority(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        overdue = create_task(
            runtime,
            "Overdue",
            "normal",
            (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        )
        future = create_task(
            runtime,
            "Future",
            "normal",
            (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        )

        decision = runtime.delegation_scheduling.select_next_task(
            "researcher",
            [future, overdue],
        )

        self.assertEqual(decision.selected_task_id, overdue.task_id)
        self.assertIn("due_at:overdue", decision.queue[0].reasons)

    def test_fifo_preserved_on_same_score(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        first = create_task(runtime, "First", "normal")
        second = create_task(runtime, "Second", "normal")

        decision = runtime.delegation_scheduling.select_next_task(
            "researcher",
            [second, first],
        )

        self.assertEqual(decision.ordered_task_ids, [first.task_id, second.task_id])

    def test_worker_uses_policy_to_select_delegation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        normal = create_task(runtime, "Normal", "normal")
        critical = create_task(runtime, "Critical", "critical")
        runtime.delegation.accept_task(runtime.context(), normal.task_id)
        runtime.delegation.accept_task(runtime.context(), critical.task_id)

        result = runtime.worker.process_next_delegation(runtime.context(), "researcher")

        self.assertEqual(result.task_id, critical.task_id)
        self.assertEqual(result.action, "autonomy_requires_approval")
        self.assertEqual(runtime.delegation.get_task(critical.task_id).status, "accepted")

    def test_disabled_policy_falls_back_to_existing_order(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_json(
            runtime.data_dir.resolve("config/delegation_scheduling_policy.yaml"),
            {
                "delegation_scheduling": {
                    "enabled": False,
                    "status_order": ["in_progress", "accepted", "pending"],
                    "priority_weights": {
                        "critical": 400,
                        "high": 300,
                        "normal": 200,
                        "low": 100,
                    },
                    "due_at_weight": 50,
                    "aging_weight": 1,
                    "max_items_per_agent_cycle": 1,
                    "allow_critical_first": True,
                    "preserve_fifo_within_same_score": True,
                }
            },
        )
        first = create_task(runtime, "First normal", "normal")
        second = create_task(runtime, "Second critical", "critical")
        runtime.delegation.accept_task(runtime.context(), first.task_id)
        runtime.delegation.accept_task(runtime.context(), second.task_id)

        result = runtime.worker.process_next_delegation(runtime.context(), "researcher")

        self.assertEqual(result.task_id, first.task_id)

    def test_command_delegation_next(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        create_task(runtime, "Normal", "normal")
        critical = create_task(runtime, "Critical", "critical")

        result = runtime.commands.execute(runtime.context(), "/delegation-next researcher")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["decision"]["selected_task_id"], critical.task_id)

    def test_api_next_endpoint(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        create_task(runtime, "Normal", "normal")
        critical = create_task(runtime, "Critical", "critical")
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        response = client.get("/api/delegation-inbox/researcher/next")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected_task_id"], critical.task_id)


if __name__ == "__main__":
    unittest.main()
