from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
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
    "communication.read",
    "communication.summarize",
    "communication.draft",
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
            "agent:researcher": DEFAULT_PERMISSIONS,
            "agent:hermes": DEFAULT_PERMISSIONS,
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Recurring Scheduler Test",
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


def write_scheduler_policy(settings: Settings, recurring_jobs: list[dict]) -> None:
    write_json(
        settings.data_dir / "config" / "scheduler_policy.yaml",
        {"recurring_jobs": recurring_jobs},
    )


def past(minutes: int = 5) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def future(minutes: int = 5) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


class SchedulerRecurringTests(unittest.TestCase):
    def test_load_recurring_jobs_from_policy(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_scheduler_policy(
            settings,
            [
                {
                    "id": "cleanup",
                    "type": "notification_cleanup",
                    "payload": {},
                    "interval_minutes": 60,
                }
            ],
        )

        jobs = runtime.scheduler.load_recurring_jobs()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, "cleanup")
        self.assertEqual(jobs[0].type, "notification_cleanup")

    def test_due_recurring_job_is_enqueued_and_state_persisted(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_scheduler_policy(
            settings,
            [
                {
                    "id": "cleanup",
                    "type": "notification_cleanup",
                    "payload": {},
                    "interval_minutes": 60,
                    "next_run_at": past(),
                }
            ],
        )

        enqueued = runtime.scheduler.enqueue_due_recurring_jobs(runtime.context())

        self.assertEqual(len(enqueued), 1)
        self.assertEqual(enqueued[0].type, "notification_cleanup")
        state = runtime.scheduler.load_recurring_jobs()[0]
        self.assertIsNotNone(state.last_run_at)
        self.assertIsNotNone(state.next_run_at)
        self.assertTrue(runtime.data_dir.resolve("scheduler/recurring/cleanup.yaml").exists())

    def test_not_due_recurring_job_is_skipped(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_scheduler_policy(
            settings,
            [
                {
                    "id": "cleanup",
                    "type": "notification_cleanup",
                    "payload": {},
                    "interval_minutes": 60,
                    "next_run_at": future(),
                }
            ],
        )

        enqueued = runtime.scheduler.enqueue_due_recurring_jobs(runtime.context())

        self.assertEqual(enqueued, [])
        event_types = [event.type for event in runtime.events.tail(limit=40)]
        self.assertIn("recurring.skipped", event_types)

    def test_recurring_state_persists_after_restart(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_scheduler_policy(
            settings,
            [
                {
                    "id": "cleanup",
                    "type": "notification_cleanup",
                    "payload": {},
                    "interval_minutes": 60,
                    "next_run_at": past(),
                }
            ],
        )
        runtime.scheduler.enqueue_due_recurring_jobs(runtime.context())

        restarted = create_runtime(settings)
        state = restarted.scheduler.load_recurring_jobs()[0]

        self.assertIsNotNone(state.last_run_at)
        self.assertGreater(datetime.fromisoformat(state.next_run_at), datetime.now(UTC))

    def test_supported_job_types_are_enqueued(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_scheduler_policy(
            settings,
            [
                {
                    "id": "cleanup",
                    "type": "notification_cleanup",
                    "payload": {},
                    "interval_minutes": 60,
                    "next_run_at": past(),
                },
                {
                    "id": "email",
                    "type": "check_email",
                    "payload": {"provider": "mock", "agent_id": "hermes"},
                    "interval_minutes": 60,
                    "next_run_at": past(),
                },
                {
                    "id": "inbox",
                    "type": "process_agent_inbox",
                    "payload": {"agent_id": "researcher"},
                    "interval_minutes": 60,
                    "next_run_at": past(),
                },
            ],
        )

        enqueued = runtime.scheduler.enqueue_due_recurring_jobs(runtime.context())

        self.assertEqual([job.type for job in enqueued], [
            "notification_cleanup",
            "check_email",
            "process_agent_inbox",
        ])

    def test_recurring_commands_work(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_scheduler_policy(
            settings,
            [
                {
                    "id": "cleanup",
                    "type": "notification_cleanup",
                    "payload": {},
                    "interval_minutes": 60,
                    "next_run_at": past(),
                }
            ],
        )

        listed = runtime.commands.execute(runtime.context(), "/recurring-jobs")
        ran = runtime.commands.execute(runtime.context(), "/run-recurring")

        self.assertEqual(listed.status, "ok")
        self.assertEqual(len(listed.data["recurring_jobs"]), 1)
        self.assertEqual(ran.status, "ok")
        self.assertEqual(ran.data["jobs"][0]["type"], "notification_cleanup")

    def test_recurring_api_works(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_scheduler_policy(
            settings,
            [
                {
                    "id": "cleanup",
                    "type": "notification_cleanup",
                    "payload": {},
                    "interval_minutes": 60,
                    "next_run_at": past(),
                }
            ],
        )
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        listed = client.get("/api/scheduler/recurring")
        ran = client.post("/api/scheduler/recurring/run")

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(ran.status_code, 200)
        self.assertEqual(ran.json()[0]["type"], "notification_cleanup")

    def test_daemon_enqueues_and_runs_due_recurring_jobs(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_scheduler_policy(
            settings,
            [
                {
                    "id": "cleanup",
                    "type": "notification_cleanup",
                    "payload": {},
                    "interval_minutes": 60,
                    "next_run_at": past(),
                }
            ],
        )

        status = runtime.daemon.run_once(runtime.context())

        self.assertEqual(len(status.last_jobs_run), 1)
        self.assertEqual(status.last_jobs_run[0]["type"], "notification_cleanup")

    def test_existing_one_off_jobs_still_work(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        job = runtime.scheduler.enqueue(runtime.context(), "notification_cleanup", {})

        completed = runtime.scheduler.run_next(runtime.context())

        self.assertEqual(completed.id, job.id)
        self.assertEqual(completed.status, "completed")

    def test_recurring_failed_event_for_invalid_definition(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_scheduler_policy(
            settings,
            [
                {
                    "id": "bad",
                    "type": "unknown",
                    "payload": {},
                    "interval_minutes": 60,
                    "next_run_at": past(),
                }
            ],
        )

        with self.assertRaises(Exception):
            runtime.scheduler.load_recurring_jobs()


if __name__ == "__main__":
    unittest.main()
