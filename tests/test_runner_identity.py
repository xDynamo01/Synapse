from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings


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
    write_json(
        settings.data_dir / "config" / "permissions.yaml",
        {"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}},
    )
    write_json(
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {"name": "Runner Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    return directory, settings, create_runtime(settings)


class RunnerIdentityTests(unittest.TestCase):
    def test_runner_identity_is_created_and_persisted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        identity = runtime.runner_identity.load()

        self.assertTrue(identity.runner_id)
        self.assertEqual(identity.role, "daemon")
        self.assertTrue(runtime.data_dir.resolve("daemon/runner.yaml").exists())

    def test_heartbeat_updates_last_seen_at(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        before = runtime.runner_identity.load()

        after = runtime.runner_identity.heartbeat()

        self.assertEqual(after.runner_id, before.runner_id)
        self.assertGreaterEqual(
            datetime.fromisoformat(after.last_seen_at),
            datetime.fromisoformat(before.last_seen_at),
        )

    def test_daemon_run_once_updates_heartbeat(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        before = runtime.runner_identity.load()

        runtime.daemon.run_once(runtime.context())
        after = runtime.runner_identity.load()

        self.assertEqual(after.status, "online")
        self.assertGreaterEqual(
            datetime.fromisoformat(after.last_seen_at),
            datetime.fromisoformat(before.last_seen_at),
        )

    def test_scheduler_lock_uses_runner_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        identity = runtime.runner_identity.load()

        runtime.scheduler.lock.acquire()
        lock = runtime.scheduler.lock.status()

        self.assertEqual(lock.owner_id, identity.runner_id)
        runtime.scheduler.lock.release()

    def test_mark_offline_persists_status(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.runner_identity.mark_online()
        offline = runtime.runner_identity.mark_offline()

        self.assertEqual(offline.status, "offline")
        self.assertEqual(runtime.runner_identity.load().status, "offline")

    def test_commands_work(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        status = runtime.commands.execute(runtime.context(), "/runner-status")
        heartbeat = runtime.commands.execute(runtime.context(), "/runner-heartbeat")

        self.assertEqual(status.status, "ok")
        self.assertEqual(heartbeat.status, "ok")
        self.assertEqual(
            status.data["runner"]["runner_id"],
            heartbeat.data["runner"]["runner_id"],
        )

    def test_api_works(self) -> None:
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

        status = client.get("/api/daemon/runner")
        heartbeat = client.post("/api/daemon/runner/heartbeat")

        self.assertEqual(status.status_code, 200)
        self.assertEqual(heartbeat.status_code, 200)
        self.assertEqual(status.json()["runner_id"], heartbeat.json()["runner_id"])

    def test_restart_preserves_runner_id(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        identity = runtime.runner_identity.load()

        restarted = create_runtime(settings)
        restarted_identity = restarted.runner_identity.load()

        self.assertEqual(restarted_identity.runner_id, identity.runner_id)


if __name__ == "__main__":
    unittest.main()
