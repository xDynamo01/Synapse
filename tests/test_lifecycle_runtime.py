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
            "name": "Synapse V2 Lifecycle Test",
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


def send_message(runtime, to_agent: str = "researcher", body: str = "Process me"):
    return runtime.communication.send_agent_message(
        runtime.context(),
        from_agent_id="artemis",
        to_agent_id=to_agent,
        subject="Lifecycle test",
        body=body,
    )


class LifecycleRuntimeTests(unittest.TestCase):
    def test_boot_persists_lifecycle(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        lifecycle = runtime.lifecycle.boot("artemis")

        self.assertEqual(lifecycle.state, "idle")
        self.assertEqual(lifecycle.boot_count, 1)
        self.assertTrue(runtime.data_dir.resolve("lifecycle/artemis.yaml").exists())
        self.assertEqual(runtime.presence.get("artemis").state, "idle")

    def test_wake_alters_state(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        lifecycle = runtime.lifecycle.wake("artemis", "test wake")

        self.assertEqual(lifecycle.state, "working")
        self.assertEqual(lifecycle.reason, "test wake")
        self.assertEqual(lifecycle.wake_count, 1)
        self.assertEqual(runtime.presence.get("artemis").state, "working")

    def test_sleep_alters_state(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.lifecycle.wake("artemis", "before sleep")

        lifecycle = runtime.lifecycle.sleep("artemis")

        self.assertEqual(lifecycle.state, "idle")
        self.assertEqual(lifecycle.sleep_count, 1)
        self.assertEqual(runtime.presence.get("artemis").state, "idle")

    def test_shutdown_alters_state(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        lifecycle = runtime.lifecycle.shutdown("artemis")

        self.assertEqual(lifecycle.state, "shutdown")
        self.assertEqual(runtime.presence.get("artemis").state, "offline")

    def test_error_increments_error_count(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        first = runtime.lifecycle.error("artemis", "first")
        second = runtime.lifecycle.error("artemis", "second")

        self.assertEqual(first.error_count, 1)
        self.assertEqual(second.error_count, 2)
        self.assertEqual(second.last_error, "second")
        self.assertEqual(runtime.presence.get("artemis").state, "error")

    def test_worker_wakes_agent_and_returns_to_idle(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        send_message(runtime)

        runtime.worker.process_inbox(runtime.context(), "researcher")
        lifecycle = runtime.lifecycle.get("researcher")

        self.assertEqual(lifecycle.state, "idle")
        self.assertEqual(lifecycle.wake_count, 1)
        self.assertEqual(lifecycle.sleep_count, 1)
        self.assertEqual(runtime.presence.get("researcher").state, "idle")

    def test_scheduler_triggers_wake_for_inbox_job(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        send_message(runtime)
        runtime.scheduler.enqueue(
            runtime.context(),
            "process_agent_inbox",
            {"agent_id": "researcher"},
        )

        runtime.scheduler.run_next(runtime.context())
        lifecycle = runtime.lifecycle.get("researcher")

        self.assertEqual(lifecycle.state, "idle")
        self.assertEqual(lifecycle.wake_count, 1)

    def test_lifecycle_events_are_emitted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.lifecycle.boot("artemis")
        runtime.lifecycle.wake("artemis", "events")
        runtime.lifecycle.sleep("artemis")
        runtime.lifecycle.shutdown("artemis")
        runtime.lifecycle.error("artemis", "events error")

        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("agent.booted", event_types)
        self.assertIn("agent.woken", event_types)
        self.assertIn("agent.sleeping", event_types)
        self.assertIn("agent.shutdown", event_types)
        self.assertIn("agent.error", event_types)
        self.assertIn("agent.lifecycle_changed", event_types)

    def test_lifecycle_persists_after_restart(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.lifecycle.wake("artemis", "before restart")

        restarted = create_runtime(settings)
        lifecycle = restarted.lifecycle.get("artemis")

        self.assertEqual(lifecycle.state, "working")
        self.assertEqual(lifecycle.wake_count, 1)

    def test_lifecycle_commands_work(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        wake = runtime.commands.execute(runtime.context(), "/wake artemis")
        detail = runtime.commands.execute(runtime.context(), "/lifecycle artemis")
        sleep = runtime.commands.execute(runtime.context(), "/sleep artemis")

        self.assertEqual(wake.status, "ok")
        self.assertEqual(detail.data["lifecycle"]["state"], "working")
        self.assertEqual(sleep.data["lifecycle"]["state"], "idle")

    def test_lifecycle_api_works(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        woke = client.post("/api/lifecycle/artemis/wake")
        detail = client.get("/api/lifecycle/artemis")
        slept = client.post("/api/lifecycle/artemis/sleep")
        listed = client.get("/api/lifecycle")

        self.assertEqual(woke.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["state"], "working")
        self.assertEqual(slept.json()["state"], "idle")
        self.assertEqual(listed.status_code, 200)


if __name__ == "__main__":
    unittest.main()
