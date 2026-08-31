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
        {
            "subjects": {
                "local_owner": ["*"],
                "user:local_owner": ["*"],
                "agent:orchestrator": ["*"],
            }
        },
    )
    write_json(
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {
                "name": "Synapse V2 Readiness Test",
                "mode": "test",
                "default_agent_id": "orchestrator",
            },
            "models": {
                "default_provider": "mock",
                "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
            },
        },
    )
    return directory, settings, create_runtime(settings)


def write_readiness_policy(settings: Settings, updates: dict) -> None:
    policy = {
        "readiness": {
            "require_daemon": False,
            "require_scheduler": True,
            "require_capabilities": True,
            "pending_approvals_state": "action_required",
            "failed_jobs_state": "degraded",
            "critical_notifications_state": "action_required",
            "stale_lock_state": "action_required",
        }
    }
    policy["readiness"].update(updates)
    write_json(settings.data_dir / "config" / "readiness_policy.yaml", policy)


class ReadinessRuntimeTests(unittest.TestCase):
    def test_system_ready(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        summary = runtime.readiness.evaluate()

        self.assertEqual(summary.state, "ready")

    def test_critical_notification_requires_action(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.notifications.create_notification(
            title="Critical",
            message="Critical",
            severity="critical",
            category="system",
        )

        summary = runtime.readiness.evaluate()

        self.assertEqual(summary.state, "action_required")
        self.assertIn("notifications.critical_unread", {check.id for check in summary.checks})

    def test_failed_jobs_degrade_readiness(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.scheduler.enqueue(runtime.context(), "unknown_job", {})
        runtime.scheduler.run_next(runtime.context())

        summary = runtime.readiness.evaluate()

        self.assertEqual(summary.state, "degraded")
        self.assertIn("jobs.failed", {check.id for check in summary.checks})

    def test_no_capabilities_is_not_ready(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.health.capabilities = None

        summary = runtime.readiness.evaluate()

        self.assertEqual(summary.state, "not_ready")
        self.assertIn("capabilities.empty", {check.id for check in summary.checks})

    def test_pending_approvals_require_action(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.approvals.create_request(
            context=runtime.context(actor_id="orchestrator", actor_type="agent"),
            tool_name="write_file",
            tool_args={"path": "projects/x.txt"},
            risk_level="high",
            reason="readiness test",
            tool_call_id="call-readiness",
        )

        summary = runtime.readiness.evaluate()

        self.assertEqual(summary.state, "action_required")
        self.assertIn("approvals.pending", {check.id for check in summary.checks})

    def test_policy_changes_severity(self) -> None:
        directory, settings, _ = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_readiness_policy(settings, {"critical_notifications_state": "not_ready"})
        runtime = create_runtime(settings)
        runtime.notifications.create_notification(
            title="Critical",
            message="Critical",
            severity="critical",
            category="system",
        )

        summary = runtime.readiness.evaluate()

        self.assertEqual(summary.state, "not_ready")

    def test_readiness_command_works(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.commands.execute(runtime.context(), "/readiness")
        issues = runtime.commands.execute(runtime.context(), "/readiness-issues")
        actions = runtime.commands.execute(runtime.context(), "/readiness-actions")

        self.assertEqual(result.status, "ok")
        self.assertIn("readiness", result.data)
        self.assertEqual(issues.status, "ok")
        self.assertEqual(actions.status, "ok")

    def test_readiness_api_works(self) -> None:
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

        readiness = TestClient(app).get("/api/readiness")
        issues = TestClient(app).get("/api/readiness/issues")
        actions = TestClient(app).get("/api/readiness/actions")

        self.assertEqual(readiness.status_code, 200)
        self.assertIn("state", readiness.json())
        self.assertEqual(issues.status_code, 200)
        self.assertEqual(actions.status_code, 200)

    def test_health_still_works(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertIn(health.status, {"ok", "info", "warning", "critical"})
        self.assertEqual(readiness.health_status, health.status)


if __name__ == "__main__":
    unittest.main()
