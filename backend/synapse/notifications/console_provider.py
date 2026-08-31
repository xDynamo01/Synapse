from __future__ import annotations

from synapse.notifications.models import Notification


class ConsoleNotificationProvider:
    name = "console"

    def __init__(self):
        self._notifications: dict[str, Notification] = {}

    def send(self, notification: Notification) -> Notification:
        self._notifications[notification.id] = notification
        print(f"[{notification.severity}] {notification.title}: {notification.message}")
        return notification

    def mark_read(self, notification_id: str) -> Notification:
        notification = self._notifications[notification_id]
        self._notifications[notification_id] = Notification(
            id=notification.id,
            title=notification.title,
            message=notification.message,
            severity=notification.severity,
            source=notification.source,
            category=notification.category,
            created_at=notification.created_at,
            read=True,
            read_at=notification.read_at,
            correlation_id=notification.correlation_id,
            metadata=notification.metadata,
        )
        return self._notifications[notification_id]

    def list_notifications(self) -> list[Notification]:
        return list(self._notifications.values())

    def list_unread(self) -> list[Notification]:
        return [
            notification for notification in self._notifications.values() if not notification.read
        ]

    def health_check(self) -> dict[str, object]:
        return {"provider": self.name, "status": "ok"}
