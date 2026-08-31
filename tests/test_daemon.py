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
            "name": "Synapse V2 Daemon Test",
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
    seed_delegation_pair(settings.data_dir)
    return directory, settings, create_runtime(settings)


def send_message(runtime):
    return runtime.communication.send_agent_message(
        runtime.context(),
        from_agent_id="artemis",
        to_agent_id="researcher",
        subject="Daemon test",
        body="Process via daemon",
    )


class BrokenScheduler:
    def run_all_pending(self, context):
        raise RuntimeError("controlled daemon failure")


class DaemonTests(unittest.TestCase):
    def test_run_once_executes_pending_jobs(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        send_message(runtime)
        runtime.scheduler.enqueue(
            runtime.context(),
            "process_agent_inbox",
            {"agent_id": "researcher"},
        )

        status = runtime.daemon.run_once(runtime.context())

        self.assertEqual(status.total_ticks, 1)
        self.assertEqual(len(status.last_jobs_run), 1)
        self.assertEqual(status.last_jobs_run[0]["status"], "completed")
        self.assertEqual(
            runtime.communication.list_messages(runtime.context(), "researcher")[0].status,
            "processed",
        )

    def test_daemon_status_is_persisted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        status = runtime.daemon.run_once(runtime.context())

        self.assertTrue(runtime.data_dir.resolve("daemon/status.yaml").exists())
        persisted = runtime.daemon.status()
        self.assertEqual(persisted.total_ticks, status.total_ticks)
        self.assertIsNotNone(persisted.last_tick_at)

    def test_daemon_tick_event_is_emitted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.daemon.run_once(runtime.context())

        event_types = [event.type for event in runtime.events.tail(limit=50)]
        self.assertIn("daemon.tick", event_types)

    def test_daemon_error_event_is_emitted_for_controlled_failure(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.daemon.scheduler = BrokenScheduler()

        status = runtime.daemon.run_once(runtime.context())

        self.assertIn("controlled daemon failure", status.last_error)
        event_types = [event.type for event in runtime.events.tail(limit=50)]
        self.assertIn("daemon.error", event_types)

    def test_daemon_run_once_command_executes_cycle(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        send_message(runtime)
        runtime.commands.execute(runtime.context(), "/enqueue-inbox researcher")

        result = runtime.commands.execute(runtime.context(), "/daemon-run-once")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["daemon"]["total_ticks"], 1)
        self.assertEqual(len(result.data["daemon"]["last_jobs_run"]), 1)

    def test_api_daemon_run_once_works(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        send_message(runtime)
        runtime.scheduler.enqueue(runtime.context(), "process_agent_inbox", {"agent_id": "researcher"})
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).post(
            "/api/daemon/run-once",
            headers={"x-actor-id": "local_owner", "x-actor-type": "user"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_ticks"], 1)
        self.assertEqual(response.json()["last_jobs_run"][0]["status"], "completed")

    def test_daemon_state_persists_after_runtime_recreation(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.daemon.run_once(runtime.context())

        restarted = create_runtime(settings)

        self.assertEqual(restarted.daemon.status().total_ticks, 1)
        self.assertIsNotNone(restarted.daemon.status().last_tick_at)


if __name__ == "__main__":
    unittest.main()
