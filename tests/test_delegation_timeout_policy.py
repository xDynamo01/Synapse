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
from synapse.core.serialization import dump_structured_file

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
        "system": {"name": "Synapse V2 Delegation Timeout Test", "mode": "test"},
        "models": {"default_provider": "mock", "providers": {"mock": {"model": "synapse-test"}}},
    }
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)
    seed_delegation_pair(
        settings.data_dir,
        delegator_extra={"permissions": DEFAULT_PERMISSIONS},
        delegate_extra={"permissions": DEFAULT_PERMISSIONS},
    )
    return directory, create_runtime(settings)


def create_running(runtime, priority: str = "normal", minutes_old: int = 120):
    task = runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title="Timeout task",
        description="timeout work",
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
        priority=priority,
    )
    task = runtime.delegation.accept_task(runtime.context(), task.task_id)
    task = runtime.delegation.start_task(runtime.context(), task.task_id)
    execution = runtime.delegation_execution.start_execution(
        runtime.delegation_execution.create_execution(task.task_id).execution_id
    )
    old = (datetime.now(UTC) - timedelta(minutes=minutes_old)).isoformat()
    execution = runtime.delegation_execution.get_execution(execution.execution_id)
    payload = {**execution.__dict__, "started_at": old}
    dump_structured_file(
        runtime.data_dir.resolve(f"delegation_execution/{execution.execution_id}.yaml"),
        payload,
    )
    return task, runtime.delegation_execution.get_execution(execution.execution_id)


def write_timeout_policy(runtime, **updates) -> None:
    policy = {
        "enabled": True,
        "default_timeout_minutes": 60,
        "timeout_by_priority": {"critical": 30, "high": 45, "normal": 60, "low": 120},
        "timeout_by_status": {"in_progress": 60},
        "mark_execution_failed_on_timeout": True,
        "mark_task_failed_on_timeout": False,
        "require_human_review_for_critical": True,
        "dry_run_default": True,
        "max_timeouts_per_run": 50,
    }
    policy.update(updates)
    write_json(
        runtime.data_dir.resolve("config/delegation_timeout_policy.yaml"),
        {"delegation_timeout": policy},
    )


class DelegationTimeoutPolicyTests(unittest.TestCase):
    def test_default_policy_loads(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        self.assertTrue(runtime.delegation_timeout.load_policy().enabled)

    def test_fixture_provides_minimal_agent_identity(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        identity = runtime.identities.load_identity("artemis")
        self.assertEqual(identity.id, "artemis")
        self.assertEqual(identity.name, "Artemis")
        self.assertEqual(identity.role, "orchestrator")
        self.assertTrue(identity.can_delegate)

    def test_running_execution_old_becomes_candidate(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task, execution = create_running(runtime, minutes_old=120)
        candidate = runtime.delegation_timeout.evaluate_timeout(task, execution)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.reason, "execution_running_timeout")

    def test_recent_execution_not_candidate(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task, execution = create_running(runtime, minutes_old=1)
        self.assertIsNone(runtime.delegation_timeout.evaluate_timeout(task, execution))

    def test_dry_run_does_not_alter(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task, execution = create_running(runtime, minutes_old=120)
        result = runtime.delegation_timeout.apply_timeout(task.task_id, dry_run=True)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(runtime.delegation_execution.get_execution(execution.execution_id).status, "running")
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "in_progress")

    def test_apply_marks_execution_failed(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task, execution = create_running(runtime, minutes_old=120)
        runtime.delegation_timeout.apply_timeout(task.task_id, dry_run=False)
        self.assertEqual(runtime.delegation_execution.get_execution(execution.execution_id).status, "failed")

    def test_apply_marks_task_failed_when_policy_enabled(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_timeout_policy(runtime, mark_task_failed_on_timeout=True)
        task, _ = create_running(runtime, minutes_old=120)
        runtime.delegation_timeout.apply_timeout(task.task_id, dry_run=False)
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "failed")

    def test_critical_requires_review_and_does_not_apply(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task, execution = create_running(runtime, priority="critical", minutes_old=120)
        result = runtime.delegation_timeout.apply_timeout(task.task_id, dry_run=False)
        self.assertEqual(result.skipped, [task.task_id])
        self.assertEqual(runtime.delegation_execution.get_execution(execution.execution_id).status, "running")

    def test_scheduler_job_runs_dry_run(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        create_running(runtime, minutes_old=120)
        runtime.scheduler.enqueue(runtime.context(), "delegation_timeout_scan", {"dry_run": True})
        completed = runtime.scheduler.run_next(runtime.context())
        self.assertEqual(completed.status, "completed")

    def test_command_timeout_scan(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        create_running(runtime, minutes_old=120)
        result = runtime.commands.execute(runtime.context(), "/delegation-timeout-scan")
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.data["result"]["candidates"]), 1)

    def test_api_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:
            self.skipTest(f"FastAPI unavailable: {exc}")
        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task, _ = create_running(runtime, minutes_old=120)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)
        self.assertEqual(client.get("/api/delegation-timeout-policy").status_code, 200)
        self.assertEqual(client.post(f"/api/delegations/{task.task_id}/timeout-check").status_code, 200)
        self.assertEqual(client.post("/api/delegations/timeout-scan", json={"dry_run": True}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
