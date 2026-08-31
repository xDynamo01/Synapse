from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.agents.provisioning import AgentCreateRequest
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import NotFound


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
            "system": {
                "name": "Synapse V2 Retention Registry Test",
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
                "require_approval_for_deactivate": True,
                "require_approval_for_archive": True,
                "require_approval_for_restore": True,
                "protected_agents": [],
                "blocked_admin_actions": [],
                "admin_capabilities_required": {},
            }
        },
    )
    runtime = create_runtime(settings)
    runtime.provisioning.create_agent(
        AgentCreateRequest(agent_id="managed", display_name="Managed", role="assistant")
    )
    return directory, runtime


class RetentionRegistryTests(unittest.TestCase):
    def test_list_domains(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        domains = runtime.retention.list_domains()
        domain_ids = {domain.domain_id for domain in domains}

        self.assertIn("notifications", domain_ids)
        self.assertIn("agent_admin_requests", domain_ids)

    def test_get_existing_domain(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        domain = runtime.retention.get_domain("notifications")

        self.assertEqual(domain.domain_id, "notifications")
        self.assertTrue(domain.supports_dry_run)

    def test_missing_domain_raises(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        with self.assertRaises(NotFound):
            runtime.retention.get_domain("missing")

    def test_cleanup_notifications_via_registry_dry_run(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.notifications.create_notification(
            title="Test",
            message="Notification",
            severity="info",
            source="test",
            category="system",
        )

        result = runtime.retention.cleanup_domain("notifications", dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.deleted, 0)
        self.assertEqual(len(runtime.notifications.list_notifications()), 1)

    def test_cleanup_agent_admin_requests_via_registry_dry_run(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = runtime.admin.request_admin_action(
            "agent.deactivate",
            "managed",
            context=runtime.context(),
        )

        result = runtime.retention.cleanup_domain("agent_admin_requests", dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.deleted, 0)
        self.assertIsNotNone(runtime.admin.get_admin_action_request(request.id))

    def test_cleanup_all_dry_run(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        results = runtime.retention.cleanup_all()

        self.assertEqual({result.domain_id for result in results}, {"notifications", "agent_admin_requests"})
        self.assertTrue(all(result.dry_run for result in results))

    def test_retention_command(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        status = runtime.commands.execute(runtime.context(), "/retention")
        detail = runtime.commands.execute(runtime.context(), "/retention-domain notifications")

        self.assertEqual(status.status, "ok")
        self.assertEqual(detail.status, "ok")
        self.assertNotIn("/retention-cleanup", runtime.commands.registry.names)
        self.assertNotIn("/retention-cleanup-all", runtime.commands.registry.names)

    def test_retention_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        status = client.get("/api/retention")
        domain = client.get("/api/retention/domains/notifications")
        cleanup = client.post(
            "/api/retention/domains/notifications/cleanup",
            json={"dry_run": True},
        )

        self.assertEqual(status.status_code, 200)
        self.assertEqual(domain.status_code, 200)
        self.assertEqual(cleanup.status_code, 404)

    def test_scheduler_job_retention_cleanup_domain(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        job = runtime.scheduler.enqueue(
            runtime.context(),
            "retention_cleanup_domain",
            {"domain_id": "notifications", "dry_run": True},
        )

        completed = runtime.scheduler.run_next(runtime.context())

        self.assertEqual(completed.id, job.id)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.payload["result"]["cleanup"]["domain_id"], "notifications")


if __name__ == "__main__":
    unittest.main()
