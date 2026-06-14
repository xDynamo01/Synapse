from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings

DEFAULT_PERMISSIONS = [
    "filesystem.read",
    "filesystem.write",
    "filesystem.list",
    "filesystem.search",
    "agents.message",
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
            "name": "Synapse V2 Scheduler Test",
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
    return directory, settings, create_runtime(settings)


def send_message(runtime, to_agent: str = "researcher", body: str = "Process me"):
    return runtime.communication.send_agent_message(
        runtime.context(),
        from_agent_id="artemis",
        to_agent_id=to_agent,
        subject="Scheduler test",
        body=body,
    )


class SchedulerTests(unittest.TestCase):
    def test_enqueue_creates_pending_persisted_job(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        job = runtime.scheduler.enqueue(
            runtime.context(),
            "process_agent_inbox",
            {"agent_id": "researcher"},
        )

        self.assertEqual(job.status, "pending")
        self.assertTrue(runtime.data_dir.resolve(f"jobs/{job.id}.yaml").exists())
        persisted = runtime.scheduler.get_job(job.id)
        self.assertEqual(persisted.payload["agent_id"], "researcher")
        self.assertEqual(persisted.status, "pending")

    def test_run_next_executes_process_agent_inbox_job(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = send_message(runtime)
        job = runtime.scheduler.enqueue(
            runtime.context(),
            "process_agent_inbox",
            {"agent_id": "researcher"},
        )

        completed = runtime.scheduler.run_next(runtime.context())

        self.assertEqual(completed.id, job.id)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.attempts, 1)
        self.assertIsNotNone(completed.started_at)
        self.assertIsNotNone(completed.completed_at)
        processed = runtime.communication.list_messages(runtime.context(), "researcher")[0]
        self.assertEqual(processed.id, message.id)
        self.assertEqual(processed.status, "processed")

    def test_job_transitions_pending_running_completed_are_emitted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        send_message(runtime)
        runtime.scheduler.enqueue(runtime.context(), "process_agent_inbox", {"agent_id": "researcher"})

        runtime.scheduler.run_next(runtime.context())

        event_types = [event.type for event in runtime.events.tail(limit=120)]
        self.assertIn("job.enqueued", event_types)
        self.assertIn("job.started", event_types)
        self.assertIn("job.completed", event_types)

    def test_failure_marks_failed_and_increments_attempts(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        job = runtime.scheduler.enqueue(runtime.context(), "unknown_job", {}, max_attempts=2)

        failed = runtime.scheduler.run_next(runtime.context())

        self.assertEqual(failed.id, job.id)
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.attempts, 1)
        self.assertIn("Unknown job type", failed.failed_reason)
        event_types = [event.type for event in runtime.events.tail(limit=50)]
        self.assertIn("job.failed", event_types)

    def test_retry_failed_returns_job_to_pending_when_attempts_remain(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.scheduler.enqueue(runtime.context(), "unknown_job", {}, max_attempts=2)
        runtime.scheduler.run_next(runtime.context())

        retried = runtime.scheduler.retry_failed(runtime.context())

        self.assertEqual(len(retried), 1)
        self.assertEqual(retried[0].status, "pending")
        self.assertEqual(retried[0].attempts, 1)
        self.assertIsNone(retried[0].failed_reason)
        event_types = [event.type for event in runtime.events.tail(limit=80)]
        self.assertIn("job.retried", event_types)

    def test_cancel_job_prevents_execution(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        send_message(runtime)
        job = runtime.scheduler.enqueue(
            runtime.context(),
            "process_agent_inbox",
            {"agent_id": "researcher"},
        )

        cancelled = runtime.scheduler.cancel_job(runtime.context(), job.id)
        ran = runtime.scheduler.run_next(runtime.context())

        self.assertEqual(cancelled.status, "cancelled")
        self.assertIsNone(ran)
        self.assertEqual(
            runtime.communication.list_messages(runtime.context(), "researcher")[0].status,
            "pending",
        )

    def test_enqueue_inbox_command_creates_job(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.commands.execute(runtime.context(), "/enqueue-inbox Researcher")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["job"]["type"], "process_agent_inbox")
        self.assertEqual(result.data["job"]["payload"]["agent_id"], "researcher")

    def test_run_jobs_command_executes_jobs(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        send_message(runtime)
        runtime.commands.execute(runtime.context(), "/enqueue-inbox researcher")

        result = runtime.commands.execute(runtime.context(), "/run-jobs")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["jobs"][0]["status"], "completed")
        self.assertEqual(
            runtime.communication.list_messages(runtime.context(), "researcher")[0].status,
            "processed",
        )

    def test_api_lists_and_executes_jobs(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        send_message(runtime)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        enqueued = client.post(
            "/api/jobs",
            headers={"x-actor-id": "local_owner", "x-actor-type": "user"},
            json={"type": "process_agent_inbox", "payload": {"agent_id": "researcher"}},
        )
        listed = client.get("/api/jobs")
        ran = client.post(
            "/api/jobs/run",
            headers={"x-actor-id": "local_owner", "x-actor-type": "user"},
        )

        self.assertEqual(enqueued.status_code, 200)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(ran.status_code, 200)
        self.assertEqual(ran.json()[0]["status"], "completed")

    def test_job_state_persists_after_runtime_recreation(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        job = runtime.scheduler.enqueue(
            runtime.context(),
            "process_agent_inbox",
            {"agent_id": "researcher"},
        )

        restarted = create_runtime(settings)
        persisted = restarted.scheduler.get_job(job.id)

        self.assertEqual(persisted.id, job.id)
        self.assertEqual(persisted.status, "pending")
        self.assertEqual(len(restarted.scheduler.list_jobs()), 1)


if __name__ == "__main__":
    unittest.main()
