from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.agent_loop.ports import Notification as AgentLoopNotification
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.notifications.models import Notification
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


def write_policy(settings: Settings, **updates) -> None:
    policy = {
        "notifications": {
            "retention_days": 30,
            "max_total_notifications": 500,
            "preserve_unread": True,
            "preserve_critical": True,
            **updates,
        }
    }
    write_json(settings.data_dir / "config" / "notification_policy.yaml", policy)


def make_notification(
    runtime,
    title: str,
    days_old: int = 0,
    read: bool = True,
    severity: str = "info",
) -> Notification:
    created_at = (datetime.now(UTC) - timedelta(days=days_old)).isoformat()
    notification = Notification(
        title=title,
        message=title,
        severity=severity,
        source="test",
        category="system",
        read=read,
        read_at=created_at if read else None,
        created_at=created_at,
    )
    return runtime.notifications.provider.send(notification)


class NotificationRuntimeTests(unittest.TestCase):
    def test_agent_loop_notification_sink_is_frontend_neutral_and_restart_safe(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        saved = runtime.agent_loop.notification_sink.notify(
            AgentLoopNotification(
                type="attention_required",
                title="Review attention item",
                summary="A canonical attention item needs review.",
                severity="medium",
                entity_refs=[{"type": "attention_item", "id": "attention-1"}],
                correlation_id="correlation-1",
                metadata={"attention_item_id": "attention-1", "api_key": "sk-secret123"},
            )
        )

        self.assertTrue(runtime.data_dir.resolve(f"notifications/{saved.id}.yaml").exists())
        self.assertEqual(runtime.notifications.get(saved.id).correlation_id, "correlation-1")
        self.assertEqual(runtime.notifications.list_unread()[0].id, saved.id)
        self.assertEqual(saved.metadata["attention_item_id"], "attention-1")
        self.assertEqual(saved.metadata["entity_refs"][0]["id"], "attention-1")
        self.assertEqual(saved.metadata["api_key"], "[REDACTED]")

        restarted = create_runtime(settings)
        persisted = restarted.notifications.get(saved.id)
        self.assertEqual(persisted.source, "agent_loop")
        acknowledged = restarted.notifications.mark_read(saved.id, restarted.context())
        self.assertTrue(acknowledged.read)
        restarted.notifications.delete_notification(saved.id, restarted.context())
        self.assertEqual(restarted.notifications.list_notifications(), [])

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

    def test_cleanup_deletes_old_read_notifications(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_policy(settings, retention_days=1)
        old = make_notification(runtime, "old", days_old=10, read=True)
        recent = make_notification(runtime, "recent", days_old=0, read=True)

        result = runtime.notifications.cleanup_notifications()

        self.assertEqual(result.deleted, 1)
        ids = {notification.id for notification in runtime.notifications.list_notifications()}
        self.assertNotIn(old.id, ids)
        self.assertIn(recent.id, ids)

    def test_cleanup_preserves_unread_and_critical(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_policy(settings, retention_days=1, preserve_unread=True, preserve_critical=True)
        unread = make_notification(runtime, "unread", days_old=10, read=False)
        critical = make_notification(runtime, "critical", days_old=10, read=True, severity="critical")
        old = make_notification(runtime, "old", days_old=10, read=True)

        result = runtime.notifications.cleanup_notifications()

        ids = {notification.id for notification in runtime.notifications.list_notifications()}
        self.assertEqual(result.deleted, 1)
        self.assertIn(unread.id, ids)
        self.assertIn(critical.id, ids)
        self.assertNotIn(old.id, ids)

    def test_cleanup_enforces_max_total_notifications(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_policy(
            settings,
            retention_days=999,
            max_total_notifications=2,
            preserve_unread=False,
            preserve_critical=False,
        )
        for index in range(5):
            make_notification(runtime, f"n{index}", days_old=5 - index, read=True)

        result = runtime.notifications.cleanup_notifications()

        self.assertEqual(result.max_total_deleted, 3)
        self.assertEqual(len(runtime.notifications.list_notifications()), 2)

    def test_cleanup_events_are_emitted(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_policy(settings, retention_days=1)
        make_notification(runtime, "old", days_old=10, read=True)

        runtime.notifications.cleanup_notifications()

        event_types = [event.type for event in runtime.events.tail(limit=80)]
        self.assertIn("notification.cleanup_started", event_types)
        self.assertIn("notification.cleanup_completed", event_types)

    def test_scheduler_runs_notification_cleanup(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_policy(settings, retention_days=1)
        make_notification(runtime, "old", days_old=10, read=True)
        runtime.scheduler.enqueue(runtime.context(), "notification_cleanup", {})

        completed = runtime.scheduler.run_next(runtime.context())

        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.payload["result"]["cleanup"]["deleted"], 1)

    def test_daemon_runs_notification_cleanup(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_policy(settings, retention_days=1)
        make_notification(runtime, "old", days_old=10, read=True)
        runtime.scheduler.enqueue(runtime.context(), "notification_cleanup", {})

        status = runtime.daemon.run_once(runtime.context())

        self.assertEqual(status.last_jobs_run[0]["status"], "completed")
        self.assertEqual(len(runtime.notifications.list_notifications()), 0)

    def test_cleanup_api_and_command_work(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_policy(settings, retention_days=1)
        make_notification(runtime, "api-old", days_old=10, read=True)
        command_old = make_notification(runtime, "command-old", days_old=10, read=True)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        api_result = client.post("/api/notifications/cleanup")
        command_result = runtime.commands.execute(runtime.context(), "/notifications cleanup")

        self.assertEqual(api_result.status_code, 200)
        self.assertGreaterEqual(api_result.json()["deleted"], 1)
        self.assertEqual(command_result.status, "ok")
        ids = {notification.id for notification in runtime.notifications.list_notifications()}
        self.assertNotIn(command_old.id, ids)

    def test_cleanup_failed_event_is_emitted(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_policy(settings, retention_days="invalid")

        with self.assertRaises(ValueError):
            runtime.notifications.cleanup_notifications()

        event_types = [event.type for event in runtime.events.tail(limit=80)]
        self.assertIn("notification.cleanup_failed", event_types)


if __name__ == "__main__":
    unittest.main()
