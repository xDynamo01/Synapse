from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from factories.agents import seed_test_agent
from synapse.agents.provisioning import AgentCreateRequest
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
    for agent_id, role in (
        ("artemis", "orchestrator"),
        ("atlas", "worker"),
        ("vigil", "worker"),
    ):
        seed_test_agent(settings.data_dir, agent_id, role=role, extra={"permissions": ["*"]})
    permissions = {
        "subjects": {
            "local_owner": ["*"],
            "user:local_owner": ["*"],
            "agent:artemis": ["*"],
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Health Test",
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


def write_scheduler_policy(settings: Settings) -> None:
    write_json(
        settings.data_dir / "config" / "scheduler_policy.yaml",
        {
            "scheduler_lock": {"timeout_seconds": 300},
            "recurring_jobs": [
                {
                    "id": "health-cleanup",
                    "type": "notification_cleanup",
                    "payload": {},
                    "interval_minutes": 60,
                    "next_run_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
                }
            ],
        },
    )


class HealthRuntimeTests(unittest.TestCase):
    def test_health_summary_returns_runner_daemon_and_lock(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        summary = runtime.health.summary()

        self.assertTrue(summary.runner["runner_id"])
        self.assertIn("total_ticks", summary.daemon)
        self.assertIn("locked", summary.scheduler_lock)

    def test_health_counts_pending_and_failed_jobs(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.scheduler.enqueue(runtime.context(), "unknown_job", {})
        runtime.scheduler.run_next(runtime.context())
        runtime.scheduler.enqueue(runtime.context(), "notification_cleanup", {})

        summary = runtime.health.summary()

        self.assertEqual(summary.pending_jobs, 1)
        self.assertEqual(summary.failed_jobs, 1)

    def test_health_counts_pending_approvals(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.approvals.create_request(
            context=runtime.context(actor_id="artemis", actor_type="agent"),
            tool_name="write_file",
            tool_args={"path": "projects/x.txt"},
            risk_level="high",
            reason="test",
            tool_call_id="call-health",
        )

        summary = runtime.health.summary()

        self.assertEqual(summary.approvals_pending, 1)

    def test_health_counts_unread_critical_notifications(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.notifications.create_notification(
            title="Critical",
            message="Critical",
            severity="critical",
            category="system",
        )

        summary = runtime.health.summary()

        self.assertEqual(summary.unread_critical_notifications, 1)

    def test_health_lists_agents_in_error_or_offline(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        for agent in runtime.agents.list_agents():
            runtime.presence.set_state(agent.id, "idle")
        runtime.presence.set_state("atlas", "error", "health test")
        runtime.presence.clear("vigil")

        summary = runtime.health.summary()

        states = {item["agent_id"]: item["state"] for item in summary.agents_attention}
        self.assertEqual(states["atlas"], "error")
        self.assertEqual(states["vigil"], "offline")

    def test_health_counts_due_recurring_jobs(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_scheduler_policy(settings)

        summary = runtime.health.summary()

        self.assertEqual(summary.recurring_jobs_due, 1)

    def test_health_api_works(self) -> None:
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

        response = TestClient(app).get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-synapse-service"], "synapse-backend")
        self.assertIn("runner", response.json())
        self.assertIn("daemon", response.json())

    def test_health_command_works(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.commands.execute(runtime.context(), "/health")

        self.assertEqual(result.status, "ok")
        self.assertIn("runner", result.data["health"])

    def test_health_includes_pending_provisioning_requests(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(
            AgentCreateRequest(
                agent_id="writer",
                display_name="Writer",
                role="writer",
                capabilities_allow=["filesystem.write"],
                preferred_tools=["write_file"],
            ),
            context=runtime.context(),
        )

        summary = runtime.health.summary()

        self.assertEqual(summary.pending_agent_provisioning_requests, 1)

    def test_health_includes_pending_admin_action_requests(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
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
        runtime.admin.request_admin_action(
            "agent.deactivate",
            "artemis",
            context=runtime.context(),
        )

        summary = runtime.health.summary()

        self.assertEqual(summary.pending_admin_action_requests, 1)

    def test_health_includes_retention_and_migration_status(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        summary = runtime.health.summary()

        self.assertTrue(summary.retention["available"])
        self.assertGreaterEqual(summary.retention["total_domains"], 2)
        self.assertTrue(summary.migrations["available"])
        self.assertIn("current_versions", summary.migrations)

    def test_health_includes_capability_count(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        summary = runtime.health.summary()

        self.assertGreater(summary.capability_count, 0)
        self.assertTrue(summary.decision_runtime_available)

    def test_health_reflects_archived_and_inactive_agents(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.admin.archive_agent("atlas", runtime.context(), _skip_policy=True)
        runtime.admin.deactivate_agent("vigil", runtime.context(), _skip_policy=True)

        summary = runtime.health.summary()

        self.assertGreaterEqual(summary.archived_agents, 1)
        self.assertGreaterEqual(summary.inactive_agents, 2)

    def test_health_checked_event_is_emitted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.health.summary()

        event_types = [event.type for event in runtime.events.tail(limit=50)]
        self.assertIn("health.checked", event_types)


if __name__ == "__main__":
    unittest.main()
