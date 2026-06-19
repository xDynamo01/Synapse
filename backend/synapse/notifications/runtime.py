from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import Event, EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import load_structured_file
from synapse.notifications.local_provider import LocalNotificationProvider
from synapse.notifications.models import (
    NOTIFICATION_CATEGORIES,
    NOTIFICATION_SEVERITIES,
    Notification,
    NotificationCleanupResult,
)
from synapse.notifications.provider import NotificationProvider
from synapse.observability.correlation import current_correlation


class NotificationRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        provider: LocalNotificationProvider,
        extra_providers: list[NotificationProvider] | None = None,
    ):
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.provider = provider
        self.extra_providers = extra_providers or []
        self.event_bus.add_listener(self.handle_event)

    def create_notification(
        self,
        title: str,
        message: str,
        severity: str = "info",
        source: str = "runtime",
        category: str = "unknown",
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> Notification:
        if severity not in NOTIFICATION_SEVERITIES:
            raise ValidationError(f"Invalid notification severity: {severity}")
        if category not in NOTIFICATION_CATEGORIES:
            raise ValidationError(f"Invalid notification category: {category}")
        correlation = current_correlation()
        notification = Notification(
            title=title,
            message=message,
            severity=severity,
            source=source,
            category=category,
            metadata=metadata or {},
            correlation_id=correlation_id or (correlation.correlation_id if correlation else None),
        )
        saved = self.provider.send(notification)
        for provider in self.extra_providers:
            provider.send(saved)
        self.event_bus.emit("notification.created", "notifications", asdict(saved))
        return saved

    def get(self, notification_id: str) -> Notification:
        return self.provider.get(notification_id)

    def list_notifications(self) -> list[Notification]:
        return self.provider.list_notifications()

    def list_unread(self) -> list[Notification]:
        return self.provider.list_unread()

    def mark_read(self, notification_id: str) -> Notification:
        notification = self.provider.mark_read(notification_id)
        self.event_bus.emit("notification.read", "notifications", asdict(notification))
        return notification

    def delete_notification(self, notification_id: str) -> None:
        notification = self.provider.get(notification_id)
        self.provider.delete(notification_id)
        self.event_bus.emit("notification.deleted", "notifications", asdict(notification))

    def cleanup_notifications(self) -> NotificationCleanupResult:
        policy: dict[str, Any] = {}
        try:
            policy = self._load_policy()
            self.event_bus.emit("notification.cleanup_started", "notifications", {"policy": policy})
            result = self._cleanup_with_policy(policy)
            self.event_bus.emit(
                "notification.cleanup_completed",
                "notifications",
                asdict(result),
            )
            return result
        except Exception as exc:
            self.event_bus.emit(
                "notification.cleanup_failed",
                "notifications",
                {
                    "error": str(exc) or type(exc).__name__,
                    "error_type": type(exc).__name__,
                    "policy": policy,
                },
            )
            raise

    def health_check(self) -> dict[str, object]:
        return {
            "provider": self.provider.health_check(),
            "extra_providers": [provider.health_check() for provider in self.extra_providers],
        }

    def handle_event(self, event: Event) -> None:
        if event.type.startswith("notification."):
            return
        mapping = self._notification_for_event(event)
        if not mapping:
            return
        self.create_notification(
            title=mapping["title"],
            message=mapping["message"],
            severity=mapping["severity"],
            source=event.type,
            category=mapping["category"],
            metadata={"event": asdict(event)},
            correlation_id=event.correlation_id,
        )

    def _notification_for_event(self, event: Event) -> dict[str, str] | None:
        if event.type in {"approval.created", "approval.requested"}:
            return {
                "title": "Approval Required",
                "message": str(event.payload.get("reason", "A human approval is required.")),
                "severity": "warning",
                "category": "approval",
            }
        if event.type == "approval.approved":
            return {
                "title": "Approval Approved",
                "message": "An approval request was approved.",
                "severity": "success",
                "category": "approval",
            }
        if event.type == "approval.rejected":
            return {
                "title": "Approval Rejected",
                "message": "An approval request was rejected.",
                "severity": "warning",
                "category": "approval",
            }
        if event.type == "communication.briefing_generated":
            return {
                "title": "Email Briefing Available",
                "message": str(event.payload.get("summary", "A communication briefing is available.")),
                "severity": "info",
                "category": "communication",
            }
        if event.type == "job.failed":
            return {
                "title": "Job Failed",
                "message": str(event.payload.get("failed_reason", "A scheduler job failed.")),
                "severity": "warning",
                "category": "scheduler",
            }
        if event.type == "daemon.error":
            return {
                "title": "Daemon Error",
                "message": str(event.payload.get("error", "Daemon runtime reported an error.")),
                "severity": "critical",
                "category": "daemon",
            }
        if event.type == "agent.error":
            return {
                "title": "Agent Error",
                "message": str(event.payload.get("last_error", "Agent entered error state.")),
                "severity": "critical",
                "category": "agent",
            }
        if event.type == "tool.failed":
            return {
                "title": "Tool Failed",
                "message": str(event.payload.get("error", "A tool failed.")),
                "severity": "warning",
                "category": "system",
            }
        if event.type == "worker.message_failed":
            return {
                "title": "Worker Message Failed",
                "message": str(event.payload.get("error", "Worker failed to process a message.")),
                "severity": "warning",
                "category": "agent",
            }
        return None

    def _cleanup_with_policy(self, policy: dict[str, Any]) -> NotificationCleanupResult:
        notifications = self.list_notifications()
        retention_days = int(policy["retention_days"])
        max_total = int(policy["max_total_notifications"])
        preserve_unread = bool(policy["preserve_unread"])
        preserve_critical = bool(policy["preserve_critical"])
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        deleted_ids: set[str] = set()
        preserved_unread = 0
        preserved_critical = 0
        preserved_recent = 0
        retention_deleted = 0

        for notification in notifications:
            if preserve_unread and not notification.read:
                preserved_unread += 1
                continue
            if preserve_critical and notification.severity == "critical":
                preserved_critical += 1
                continue
            created_at = datetime.fromisoformat(notification.created_at)
            if created_at >= cutoff:
                preserved_recent += 1
                continue
            if self.provider.delete_existing(notification.id):
                deleted_ids.add(notification.id)
                retention_deleted += 1

        remaining = [
            notification
            for notification in self.list_notifications()
            if notification.id not in deleted_ids
        ]
        eligible_for_limit = [
            notification
            for notification in remaining
            if not (preserve_unread and not notification.read)
            and not (preserve_critical and notification.severity == "critical")
        ]
        eligible_for_limit.sort(key=lambda item: item.created_at)
        max_total_deleted = 0
        while len(self.list_notifications()) > max_total and eligible_for_limit:
            notification = eligible_for_limit.pop(0)
            if self.provider.delete_existing(notification.id):
                deleted_ids.add(notification.id)
                max_total_deleted += 1

        remaining_count = len(self.list_notifications())
        return NotificationCleanupResult(
            scanned=len(notifications),
            deleted=len(deleted_ids),
            preserved_unread=preserved_unread,
            preserved_critical=preserved_critical,
            preserved_recent=preserved_recent,
            max_total_deleted=max_total_deleted,
            retention_deleted=retention_deleted,
            remaining=remaining_count,
            policy=policy,
        )

    def _load_policy(self) -> dict[str, Any]:
        raw = load_structured_file(self.data_dir.resolve("config/notification_policy.yaml"))
        policy = raw.get("notifications", raw)
        return {
            "retention_days": int(policy.get("retention_days", 30)),
            "max_total_notifications": int(policy.get("max_total_notifications", 500)),
            "preserve_unread": bool(policy.get("preserve_unread", True)),
            "preserve_critical": bool(policy.get("preserve_critical", True)),
        }
