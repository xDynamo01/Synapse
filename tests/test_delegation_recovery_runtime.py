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
        "system": {"name": "Synapse V2 Delegation Recovery Test", "mode": "test"},
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


def create_task(runtime, title: str = "Recoverable task", priority: str = "normal"):
    return runtime.delegation.create_task(
        context=runtime.context(actor_id="artemis", actor_type="agent"),
        title=title,
        description="Recover this delegation.",
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
        priority=priority,
    )


def fail_task_with_attempts(runtime, attempts: int = 1, priority: str = "normal"):
    task = create_task(runtime, priority=priority)
    for _ in range(attempts):
        execution = runtime.delegation_execution.create_execution(task.task_id)
        execution = runtime.delegation_execution.start_execution(execution.execution_id)
        runtime.delegation_execution.fail_execution(execution.execution_id, "failed")
    runtime.delegation.fail_task(runtime.context(), task.task_id, reason="failed")
    return runtime.delegation.get_task(task.task_id)


def timed_out_critical_task(runtime):
    task = create_task(runtime, priority="critical")
    runtime.delegation.accept_task(runtime.context(), task.task_id)
    task = runtime.delegation.start_task(runtime.context(), task.task_id)
    execution = runtime.delegation_execution.create_execution(task.task_id)
    execution = runtime.delegation_execution.start_execution(execution.execution_id)
    old = (datetime.now(UTC) - timedelta(minutes=120)).isoformat()
    dump_structured_file(
        runtime.data_dir.resolve(f"delegation_execution/{execution.execution_id}.yaml"),
        {**execution.__dict__, "started_at": old},
    )
    return runtime.delegation.get_task(task.task_id)


class DelegationRecoveryRuntimeTests(unittest.TestCase):
    def test_healthy_task_continue_processing(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)

        decision = runtime.delegation_recovery.evaluate_task(task.task_id)

        self.assertEqual(decision.recommendation, "continue_processing")
        self.assertFalse(decision.timeout_detected)
        self.assertFalse(decision.dlq_present)

    def test_retry_recommended_for_failed_task_when_allowed(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = fail_task_with_attempts(runtime, attempts=1)

        decision = runtime.delegation_recovery.evaluate_task(task.task_id)

        self.assertEqual(decision.recommendation, "retry_task")
        self.assertTrue(decision.retry_allowed)

    def test_dead_letter_recommended_when_retry_blocked(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = fail_task_with_attempts(runtime, attempts=3)

        decision = runtime.delegation_recovery.evaluate_task(task.task_id)

        self.assertEqual(decision.recommendation, "move_to_dead_letter")
        self.assertFalse(decision.retry_allowed)

    def test_manual_review_recommended_for_open_dead_letter(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        runtime.dead_letter.move_to_dead_letter(task.task_id)

        decision = runtime.delegation_recovery.evaluate_task(task.task_id)

        self.assertEqual(decision.recommendation, "manual_review")
        self.assertTrue(decision.dlq_present)

    def test_restore_recommended_for_reviewed_dead_letter(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        entry = runtime.dead_letter.move_to_dead_letter(task.task_id)
        runtime.dead_letter.review_entry(entry.dlq_id)

        decision = runtime.delegation_recovery.evaluate_task(task.task_id)

        self.assertEqual(decision.recommendation, "restore_from_dead_letter")

    def test_critical_timeout_recommends_manual_review(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = timed_out_critical_task(runtime)

        decision = runtime.delegation_recovery.evaluate_task(task.task_id)

        self.assertEqual(decision.recommendation, "manual_review")
        self.assertEqual(decision.risk_level, "critical")
        self.assertTrue(decision.timeout_detected)

    def test_summary_counts_candidates(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        fail_task_with_attempts(runtime, attempts=3)
        create_task(runtime)

        summary = runtime.delegation_recovery.summarize_recovery_state()

        self.assertEqual(summary["recovery_candidates_count"], 1)
        self.assertEqual(summary["by_recommendation"]["move_to_dead_letter"], 1)

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = fail_task_with_attempts(runtime, attempts=1)

        result = runtime.commands.execute(runtime.context(), f"/recovery {task.task_id}")
        summary = runtime.commands.execute(runtime.context(), "/recovery-summary")
        opened = runtime.commands.execute(runtime.context(), "/recovery-open")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["decision"]["recommendation"], "retry_task")
        self.assertEqual(summary.status, "ok")
        self.assertEqual(opened.status, "ok")

    def test_api_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:
            self.skipTest(f"FastAPI unavailable: {exc}")
        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = fail_task_with_attempts(runtime, attempts=1)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        self.assertEqual(client.get(f"/api/recovery/{task.task_id}").status_code, 200)
        self.assertEqual(client.get("/api/recovery/summary").status_code, 200)
        self.assertEqual(client.get("/api/recovery/open").status_code, 200)

    def test_health_and_readiness_include_recovery(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        for index in range(3):
            fail_task_with_attempts(runtime, attempts=3, priority="normal")

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertEqual(health.recovery_candidates_count, 3)
        self.assertIn("recovery.candidates", [check.id for check in readiness.checks])


if __name__ == "__main__":
    unittest.main()
