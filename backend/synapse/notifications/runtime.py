from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.core.events import Event, EventBus
from synapse.core.exceptions import ValidationError
from synapse.notifications.local_provider import LocalNotificationProvider
from synapse.notifications.models import (
    NOTIFICATION_CATEGORIES,
    NOTIFICATION_SEVERITIES,
    Notification,
)
from synapse.notifications.provider import NotificationProvider
from synapse.observability.correlation import current_correlation


class NotificationRuntime:
    def __init__(
        self,
        event_bus: EventBus,
        provider: LocalNotificationProvider,
        extra_providers: list[NotificationProvider] | None = None,
    ):
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
