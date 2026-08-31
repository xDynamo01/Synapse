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
            "name": "Synapse V2 Delegation Execution Test",
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


def agent_context(runtime, agent_id: str):
    return runtime.context(actor_id=agent_id, actor_type="agent")


def create_task(runtime, description: str = "Execute this delegated work."):
    task = runtime.delegation.create_task(
        context=agent_context(runtime, "artemis"),
        title="Execution work",
        description=description,
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
    )
    runtime.delegation.accept_task(runtime.context(), task.task_id)
    return runtime.delegation.start_task(runtime.context(), task.task_id)


class DelegationExecutionRuntimeTests(unittest.TestCase):
    def test_create_execution(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)

        execution = runtime.delegation_execution.create_execution(task.task_id)

        self.assertEqual(execution.status, "pending")
        self.assertEqual(execution.attempt_number, 1)
        self.assertTrue(
            runtime.data_dir.resolve(
                f"delegation_execution/{execution.execution_id}.yaml"
            ).exists()
        )

    def test_start_execution(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        execution = runtime.delegation_execution.create_execution(task.task_id)

        started = runtime.delegation_execution.start_execution(execution.execution_id)

        self.assertEqual(started.status, "running")

    def test_complete_execution(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        execution = runtime.delegation_execution.start_execution(
            runtime.delegation_execution.create_execution(task.task_id).execution_id
        )

        completed = runtime.delegation_execution.complete_execution(
            execution.execution_id,
            result_summary="Done",
        )

        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.result_summary, "Done")

    def test_fail_execution(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        execution = runtime.delegation_execution.start_execution(
            runtime.delegation_execution.create_execution(task.task_id).execution_id
        )

        failed = runtime.delegation_execution.fail_execution(
            execution.execution_id,
            error_message="Model error",
        )

        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error_message, "Model error")

    def test_cancel_execution(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        execution = runtime.delegation_execution.create_execution(task.task_id)

        cancelled = runtime.delegation_execution.cancel_execution(execution.execution_id)

        self.assertEqual(cancelled.status, "cancelled")

    def test_latest_and_multiple_executions(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        first = runtime.delegation_execution.create_execution(task.task_id)
        second = runtime.delegation_execution.create_execution(task.task_id)

        latest = runtime.delegation_execution.latest_execution(task.task_id)

        self.assertEqual(first.attempt_number, 1)
        self.assertEqual(second.attempt_number, 2)
        self.assertEqual(latest.execution_id, second.execution_id)

    def test_worker_creates_execution(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)

        result = runtime.worker.process_next_delegation(runtime.context(), "researcher")
        executions = runtime.delegation_execution.list_task_executions(task.task_id)

        self.assertEqual(result.action, "responded")
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "running")
        self.assertEqual(result.execution["execution_id"], executions[0].execution_id)

    def test_completion_signal_updates_execution(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        runtime.worker.process_next_delegation(runtime.context(), "researcher")
        runtime.delegation.submit_completion_signal(
            agent_context(runtime, "researcher"),
            task.task_id,
            "completed",
            "Execution complete.",
            result="Final result",
        )

        runtime.delegation.apply_completion_signal(runtime.context(), task.task_id)
        latest = runtime.delegation_execution.latest_execution(task.task_id)

        self.assertEqual(latest.status, "completed")
        self.assertEqual(latest.result_summary, "Final result")

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        execution = runtime.delegation_execution.create_execution(task.task_id)

        listed = runtime.commands.execute(
            runtime.context(),
            f"/delegation-executions {task.task_id}",
        )
        detail = runtime.commands.execute(
            runtime.context(),
            f"/delegation-execution {execution.execution_id}",
        )

        self.assertEqual(listed.status, "ok")
        self.assertEqual(listed.data["executions"][0]["execution_id"], execution.execution_id)
        self.assertEqual(detail.status, "ok")

    def test_api_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        execution = runtime.delegation_execution.create_execution(task.task_id)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        listed = client.get(f"/api/delegations/{task.task_id}/executions")
        detail = client.get(f"/api/delegation-executions/{execution.execution_id}")

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["execution_id"], execution.execution_id)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["execution_id"], execution.execution_id)


if __name__ == "__main__":
    unittest.main()
