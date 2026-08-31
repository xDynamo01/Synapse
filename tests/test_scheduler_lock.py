from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.serialization import dump_structured_file
from synapse.scheduler.lock import SchedulerLock, SchedulerLockState

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
            "agent:researcher": DEFAULT_PERMISSIONS,
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Scheduler Lock Test",
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


class SchedulerLockTests(unittest.TestCase):
    def test_acquire_and_release_lock(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        acquired = runtime.scheduler.lock.acquire()
        released = runtime.scheduler.lock.release()

        self.assertTrue(acquired)
        self.assertTrue(released)
        self.assertFalse(runtime.scheduler.lock.is_locked())

    def test_second_runner_is_blocked(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.scheduler.lock.acquire()
        second = SchedulerLock(
            runtime.data_dir,
            runtime.events,
            owner_id="second-runner",
        )

        acquired = second.acquire()

        self.assertFalse(acquired)
        runtime.scheduler.lock.release()

    def test_stale_lock_is_recovered(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        dump_structured_file(
            runtime.data_dir.resolve("locks/scheduler.lock"),
            asdict(
                SchedulerLockState(
                    locked=True,
                    owner_id="old-runner",
                    acquired_at=old,
                    path=str(runtime.data_dir.resolve("locks/scheduler.lock")),
                )
            ),
        )
        second = SchedulerLock(
            runtime.data_dir,
            runtime.events,
            owner_id="second-runner",
            timeout_seconds=1,
        )

        acquired = second.acquire()

        self.assertTrue(acquired)
        self.assertEqual(second.status().owner_id, "second-runner")
        event_types = [event.type for event in runtime.events.tail(limit=40)]
        self.assertIn("scheduler.lock_stale_recovered", event_types)
        second.release()

    def test_run_all_pending_does_not_execute_without_lock(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.scheduler.enqueue(runtime.context(), "notification_cleanup", {})
        other = SchedulerLock(runtime.data_dir, runtime.events, owner_id="other-runner")
        other.acquire()

        runtime = create_runtime(settings)
        jobs = runtime.scheduler.run_all_pending(runtime.context())

        self.assertEqual(jobs, [])
        self.assertEqual(runtime.scheduler.list_jobs()[0].status, "pending")
        other.release()

    def test_daemon_respects_scheduler_lock(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.scheduler.enqueue(runtime.context(), "notification_cleanup", {})
        other = SchedulerLock(runtime.data_dir, runtime.events, owner_id="other-runner")
        other.acquire()

        runtime = create_runtime(settings)
        status = runtime.daemon.run_once(runtime.context())

        self.assertEqual(status.last_jobs_run, [])
        self.assertEqual(runtime.scheduler.list_jobs()[0].status, "pending")
        other.release()

    def test_lock_events_are_emitted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.scheduler.lock.acquire()
        second = SchedulerLock(runtime.data_dir, runtime.events, owner_id="second")
        second.acquire()
        runtime.scheduler.lock.release()

        event_types = [event.type for event in runtime.events.tail(limit=80)]
        self.assertIn("scheduler.lock_acquired", event_types)
        self.assertIn("scheduler.lock_skipped", event_types)
        self.assertIn("scheduler.lock_released", event_types)

    def test_restart_does_not_break_valid_lock(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.scheduler.lock.acquire()

        restarted = create_runtime(settings)
        status = restarted.scheduler.lock_status()
        jobs = restarted.scheduler.run_all_pending(restarted.context())

        self.assertTrue(status["locked"])
        self.assertEqual(status["owner_id"], runtime.scheduler.lock.owner_id)
        self.assertEqual(jobs, [])
        runtime.scheduler.lock.release()

    def test_scheduler_lock_command_and_api_work(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.scheduler.lock.acquire()
        command = runtime.commands.execute(runtime.context(), "/scheduler-lock")
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).get("/api/scheduler/lock")

        self.assertEqual(command.status, "ok")
        self.assertTrue(command.data["lock"]["locked"])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["locked"])
        runtime.scheduler.lock.release()


if __name__ == "__main__":
    unittest.main()
