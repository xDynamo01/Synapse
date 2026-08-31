from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.agents.provisioning import AgentCreateRequest
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.serialization import dump_structured_file, load_structured_file


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def runtime_in_tempdir(retention_updates: dict | None = None):
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
            "system": {
                "name": "Synapse V2 Admin Request Retention Test",
                "mode": "test",
                "default_agent_id": "managed",
            },
            "models": {
                "default_provider": "mock",
                "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
            },
        },
    )
    write_json(
        settings.data_dir / "config" / "admin_policy.yaml",
        {
            "admin_policy": {
                "allow_user_admin_actions": True,
                "require_approval_for_archive": True,
                "require_approval_for_deactivate": True,
                "require_approval_for_restore": True,
                "protected_agents": [],
                "blocked_admin_actions": [],
                "admin_capabilities_required": {},
            }
        },
    )
    retention = {
        "agent_admin_retention": {
            "enabled": True,
            "delete_applied_after_days": 1,
            "delete_rejected_after_days": 1,
            "delete_failed_after_days": 1,
            "delete_cancelled_after_days": 1,
            "preserve_awaiting_approval": True,
            "preserve_approved_not_applied": True,
            "max_requests": 500,
            "dry_run_default": True,
        }
    }
    if retention_updates:
        retention["agent_admin_retention"].update(retention_updates)
    write_json(settings.data_dir / "config" / "agent_admin_retention_policy.yaml", retention)
    runtime = create_runtime(settings)
    runtime.provisioning.create_agent(
        AgentCreateRequest(agent_id="managed", display_name="Managed", role="assistant")
    )
    return directory, settings, runtime


def make_request(runtime, action: str = "agent.deactivate"):
    return runtime.admin.request_admin_action(action, "managed", context=runtime.context())


def make_old(settings: Settings, request_id: str, days: int = 10) -> None:
    path = settings.data_dir / "agent_admin_requests" / f"{request_id}.yaml"
    raw = load_structured_file(path)
    old = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    raw["created_at"] = old
    raw["updated_at"] = old
    dump_structured_file(path, raw)


class AdminRequestRetentionTests(unittest.TestCase):
    def test_dry_run_does_not_delete(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = make_request(runtime)
        runtime.admin.approve_admin_action_request(request.id, runtime.context())
        runtime.admin.apply_admin_action_request(request.id, runtime.context())
        make_old(settings, request.id)

        result = runtime.admin.cleanup_admin_action_requests(dry_run=True)

        self.assertEqual(result.deleted, 0)
        self.assertIn(request.id, result.candidates)
        self.assertIsNotNone(runtime.admin.get_admin_action_request(request.id))

    def test_apply_deletes_expired_request(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = make_request(runtime)
        runtime.admin.approve_admin_action_request(request.id, runtime.context())
        runtime.admin.apply_admin_action_request(request.id, runtime.context())
        make_old(settings, request.id)

        result = runtime.admin.cleanup_admin_action_requests(dry_run=False)

        self.assertEqual(result.deleted, 1)
        self.assertFalse((settings.data_dir / "agent_admin_requests" / f"{request.id}.yaml").exists())

    def test_awaiting_approval_is_preserved(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = make_request(runtime)
        make_old(settings, request.id)

        result = runtime.admin.cleanup_admin_action_requests(dry_run=False)

        self.assertEqual(result.deleted, 0)
        self.assertTrue((settings.data_dir / "agent_admin_requests" / f"{request.id}.yaml").exists())

    def test_approved_not_applied_is_preserved(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = make_request(runtime)
        runtime.admin.approve_admin_action_request(request.id, runtime.context())
        make_old(settings, request.id)

        result = runtime.admin.cleanup_admin_action_requests(dry_run=False)

        self.assertEqual(result.deleted, 0)
        self.assertTrue((settings.data_dir / "agent_admin_requests" / f"{request.id}.yaml").exists())

    def test_max_requests_is_respected(self) -> None:
        directory, _, runtime = runtime_in_tempdir(
            {
                "delete_applied_after_days": 999,
                "max_requests": 1,
            }
        )
        self.addCleanup(directory.cleanup)
        request_ids = []
        for _ in range(3):
            request = make_request(runtime)
            runtime.admin.approve_admin_action_request(request.id, runtime.context())
            runtime.admin.apply_admin_action_request(request.id, runtime.context())
            runtime.admin.activate_agent("managed", runtime.context(), _skip_policy=True)
            request_ids.append(request.id)

        result = runtime.admin.cleanup_admin_action_requests(dry_run=False)

        self.assertEqual(result.deleted, 2)
        self.assertEqual(len(runtime.admin.list_admin_action_requests()), 1)

    def test_cleanup_command_dry_run(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = make_request(runtime)
        runtime.admin.approve_admin_action_request(request.id, runtime.context())
        runtime.admin.apply_admin_action_request(request.id, runtime.context())
        make_old(settings, request.id)

        result = runtime.commands.execute(runtime.context(), "/admin-request-cleanup")

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.data["cleanup"]["dry_run"])
        self.assertTrue((settings.data_dir / "agent_admin_requests" / f"{request.id}.yaml").exists())

    def test_cleanup_endpoint(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))

        from synapse.api.routes import router

        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = make_request(runtime)
        runtime.admin.approve_admin_action_request(request.id, runtime.context())
        runtime.admin.apply_admin_action_request(request.id, runtime.context())
        make_old(settings, request.id)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        status = client.get("/api/agent-admin/requests/retention")
        cleanup = client.post("/api/agent-admin/requests/cleanup", json={"dry_run": False})

        self.assertEqual(status.status_code, 200)
        self.assertEqual(cleanup.status_code, 200)
        self.assertEqual(cleanup.json()["deleted"], 1)

    def test_scheduler_job_executes_cleanup(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = make_request(runtime)
        runtime.admin.approve_admin_action_request(request.id, runtime.context())
        runtime.admin.apply_admin_action_request(request.id, runtime.context())
        make_old(settings, request.id)
        job = runtime.scheduler.enqueue(
            runtime.context(),
            "agent_admin_request_cleanup",
            {"dry_run": False},
        )

        completed = runtime.scheduler.run_next(runtime.context())

        self.assertEqual(completed.id, job.id)
        self.assertEqual(completed.status, "completed")
        self.assertFalse((settings.data_dir / "agent_admin_requests" / f"{request.id}.yaml").exists())


if __name__ == "__main__":
    unittest.main()
