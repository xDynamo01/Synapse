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
from synapse.observability.correlation import correlation_scope, new_correlation

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
    "approvals.approve",
    "approvals.reject",
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
            "agent:hermes": DEFAULT_PERMISSIONS,
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Notification Test",
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


class NotificationRuntimeTests(unittest.TestCase):
    def test_create_notification_persists(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        notification = runtime.notifications.create_notification(
            title="Test",
            message="Created",
            severity="info",
            source="test",
            category="system",
        )

        self.assertTrue(runtime.data_dir.resolve(f"notifications/{notification.id}.yaml").exists())
        self.assertEqual(runtime.notifications.get(notification.id).title, "Test")

    def test_list_notifications_and_unread_work(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.notifications.create_notification("One", "Unread", category="system")
        read = runtime.notifications.create_notification("Two", "Read", category="system")
        runtime.notifications.mark_read(read.id)

        self.assertEqual(len(runtime.notifications.list_notifications()), 2)
        self.assertEqual(len(runtime.notifications.list_unread()), 1)

    def test_mark_read_works(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        notification = runtime.notifications.create_notification("Read me", "Message")

        read = runtime.notifications.mark_read(notification.id)

        self.assertTrue(read.read)
        self.assertIsNotNone(read.read_at)

    def test_delete_notification_works(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        notification = runtime.notifications.create_notification("Delete", "Message")

        runtime.notifications.delete_notification(notification.id)

        self.assertEqual(runtime.notifications.list_notifications(), [])

    def test_approval_generates_notification(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.approvals.create_request(
            context=runtime.context(actor_id="artemis", actor_type="agent"),
            tool_name="write_file",
            tool_args={"path": "projects/x.txt", "content": "x"},
            risk_level="high",
            reason="Needs approval",
            tool_call_id="call-1",
        )

        notification = runtime.notifications.list_unread()[0]
        self.assertEqual(notification.title, "Approval Required")
        self.assertEqual(notification.category, "approval")

    def test_communication_briefing_generates_notification(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.communication_runtime.generate_briefing("hermes")

        titles = [notification.title for notification in runtime.notifications.list_unread()]
        self.assertIn("Email Briefing Available", titles)

    def test_job_failed_generates_notification(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.scheduler.enqueue(runtime.context(), "unknown_job", {})

        runtime.scheduler.run_next(runtime.context())

        notification = runtime.notifications.list_unread()[0]
        self.assertEqual(notification.title, "Job Failed")
        self.assertEqual(notification.category, "scheduler")

    def test_daemon_error_generates_notification(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        def fail(_context):
            raise RuntimeError("daemon boom")

        runtime.scheduler.run_all_pending = fail
        runtime.daemon.run_once(runtime.context())

        notification = runtime.notifications.list_unread()[0]
        self.assertEqual(notification.title, "Daemon Error")
        self.assertEqual(notification.severity, "critical")

    def test_correlation_id_is_preserved(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        correlation = new_correlation(source="test")

        with correlation_scope(correlation):
            runtime.events.emit("job.failed", "test", {"failed_reason": "correlated"})

        notification = runtime.notifications.list_unread()[0]
        self.assertEqual(notification.correlation_id, correlation.correlation_id)
        trace_records = runtime.events.trace_records(correlation.correlation_id)
        self.assertTrue(any(record["kind"] == "notification" for record in trace_records))

    def test_api_works(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        notification = runtime.notifications.create_notification("API", "Message")
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        listed = client.get("/api/notifications")
        unread = client.get("/api/notifications/unread")
        detail = client.get(f"/api/notifications/{notification.id}")
        read = client.post(f"/api/notifications/{notification.id}/read")
        deleted = client.delete(f"/api/notifications/{notification.id}")

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(unread.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(read.json()["read"], True)
        self.assertEqual(deleted.json()["deleted"], True)

    def test_commands_work(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        notification = runtime.notifications.create_notification("Command", "Message")

        listed = runtime.commands.execute(runtime.context(), "/notifications")
        unread = runtime.commands.execute(runtime.context(), "/notifications unread")
        read = runtime.commands.execute(
            runtime.context(),
            f"/read-notification {notification.id}",
        )

        self.assertEqual(listed.status, "ok")
        self.assertEqual(unread.status, "ok")
        self.assertEqual(read.data["notification"]["read"], True)

    def test_restart_preserves_notifications(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        notification = runtime.notifications.create_notification("Restart", "Message")

        restarted = create_runtime(settings)
        persisted = restarted.notifications.get(notification.id)

        self.assertEqual(persisted.title, "Restart")


if __name__ == "__main__":
    unittest.main()
