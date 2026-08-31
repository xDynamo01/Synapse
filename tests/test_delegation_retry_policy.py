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
            "name": "Synapse V2 Delegation Retry Test",
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


def write_retry_policy(runtime, **updates) -> None:
    policy = {
        "enabled": True,
        "max_attempts_default": 3,
        "max_attempts_by_priority": {"critical": 2, "high": 3, "normal": 3, "low": 2},
        "allow_retry_failed_tasks": True,
        "allow_retry_completed_tasks": False,
        "require_approval_for_critical_retry": True,
        "require_approval_after_attempts": 2,
        "reset_task_status_on_retry": True,
        "default_retry_status": "accepted",
    }
    policy.update(updates)
    write_json(runtime.data_dir.resolve("config/delegation_retry_policy.yaml"), {"delegation_retry": policy})


def create_task(runtime, priority: str = "normal"):
    return runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title=f"{priority} retry task",
        description="retry work",
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
        priority=priority,
    )


def fail_once(runtime, task):
    execution = runtime.delegation_execution.start_execution(
        runtime.delegation_execution.create_execution(task.task_id).execution_id
    )
    runtime.delegation_execution.fail_execution(execution.execution_id, "failed")
    return runtime.delegation.fail_task(runtime.context(), task.task_id, reason="failed")


class DelegationRetryPolicyTests(unittest.TestCase):
    def test_agent_registry_infers_required_identity_fields_from_fixture(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        identity = runtime.identities.load_identity("artemis")

        self.assertEqual(identity.id, "artemis")
        self.assertEqual(identity.role, "orchestrator")
        self.assertTrue(identity.can_delegate)

    def test_default_policy_loads(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        policy = runtime.delegation_retry.load_policy()

        self.assertTrue(policy.enabled)
        self.assertEqual(policy.max_attempts_default, 3)

    def test_retry_allowed_for_failed_task_below_limit(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = fail_once(runtime, create_task(runtime))

        decision = runtime.delegation_retry.evaluate_retry(
            task,
            runtime.delegation_execution.list_task_executions(task.task_id),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.attempt_count, 1)

    def test_retry_blocked_above_limit(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime, priority="low")
        for _ in range(2):
            execution = runtime.delegation_execution.start_execution(
                runtime.delegation_execution.create_execution(task.task_id).execution_id
            )
            runtime.delegation_execution.fail_execution(execution.execution_id, "failed")
        task = runtime.delegation.fail_task(runtime.context(), task.task_id, reason="failed")

        decision = runtime.delegation_retry.evaluate_retry(
            task,
            runtime.delegation_execution.list_task_executions(task.task_id),
        )

        self.assertTrue(decision.blocked)
        self.assertIn("reached max attempts", decision.blocked_reasons[0])

    def test_completed_cannot_retry_by_default(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        task = runtime.delegation.complete_task(runtime.context(), task.task_id, result="done")

        decision = runtime.delegation_retry.evaluate_retry(task, [])

        self.assertTrue(decision.blocked)
        self.assertIn("retry for completed tasks is disabled", decision.blocked_reasons)

    def test_critical_retry_requires_approval(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = fail_once(runtime, create_task(runtime, priority="critical"))

        decision = runtime.delegation_retry.evaluate_retry(
            task,
            runtime.delegation_execution.list_task_executions(task.task_id),
        )

        self.assertTrue(decision.requires_approval)
        self.assertFalse(decision.allowed)

    def test_request_retry_changes_status(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = fail_once(runtime, create_task(runtime))

        result = runtime.delegation.request_retry(task.task_id, context=runtime.context())

        self.assertEqual(result["status"], "allowed")
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "accepted")

    def test_request_retry_does_not_create_execution(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = fail_once(runtime, create_task(runtime))
        before = len(runtime.delegation_execution.list_task_executions(task.task_id))

        runtime.delegation.request_retry(task.task_id, context=runtime.context())
        after = len(runtime.delegation_execution.list_task_executions(task.task_id))

        self.assertEqual(after, before)

    def test_worker_creates_new_execution_after_retry(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = fail_once(runtime, create_task(runtime))
        runtime.delegation.request_retry(task.task_id, context=runtime.context())

        runtime.worker.process_next_delegation(runtime.context(), "researcher")
        runtime.worker.process_next_delegation(runtime.context(), "researcher")
        executions = runtime.delegation_execution.list_task_executions(task.task_id)

        self.assertEqual(len(executions), 2)
        self.assertEqual(executions[-1].status, "running")

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = fail_once(runtime, create_task(runtime))

        policy = runtime.commands.execute(runtime.context(), "/delegation-retry-policy")
        check = runtime.commands.execute(runtime.context(), f"/delegation-retry-check {task.task_id}")
        retry = runtime.commands.execute(runtime.context(), f"/retry-delegation {task.task_id}")

        self.assertEqual(policy.status, "ok")
        self.assertEqual(check.data["decision"]["allowed"], True)
        self.assertEqual(retry.data["status"], "allowed")

    def test_api_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = fail_once(runtime, create_task(runtime))
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        policy = client.get("/api/delegation-retry-policy")
        check = client.post(f"/api/delegations/{task.task_id}/retry-check")
        retry = client.post(f"/api/delegations/{task.task_id}/retry")

        self.assertEqual(policy.status_code, 200)
        self.assertEqual(check.status_code, 200)
        self.assertTrue(check.json()["allowed"])
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["status"], "allowed")


if __name__ == "__main__":
    unittest.main()
