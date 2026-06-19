from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from synapse.core.data_dir import DataDir
from synapse.core.exceptions import NotFound
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.notifications.models import Notification


class LocalNotificationProvider:
    name = "local"

    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    def send(self, notification: Notification) -> Notification:
        dump_structured_file(self._path(notification.id), asdict(notification))
        return notification

    def get(self, notification_id: str) -> Notification:
        path = self._path(notification_id)
        if not path.exists():
            raise NotFound(f"Notification not found: {notification_id}")
        return self._read(path)

    def mark_read(self, notification_id: str) -> Notification:
        current = self.get(notification_id)
        updated = Notification(
            id=current.id,
            title=current.title,
            message=current.message,
            severity=current.severity,
            source=current.source,
            category=current.category,
            created_at=current.created_at,
            read=True,
            read_at=current.read_at or datetime.now(UTC).isoformat(),
            correlation_id=current.correlation_id,
            metadata=current.metadata,
        )
        return self.send(updated)

    def delete(self, notification_id: str) -> None:
        path = self._path(notification_id)
        if not path.exists():
            raise NotFound(f"Notification not found: {notification_id}")
        path.unlink()

    def list_notifications(self) -> list[Notification]:
        notifications_dir = self.data_dir.resolve("notifications")
        return [self._read(path) for path in sorted(notifications_dir.glob("*.yaml"))]

    def list_unread(self) -> list[Notification]:
        return [notification for notification in self.list_notifications() if not notification.read]

    def health_check(self) -> dict[str, object]:
        return {
            "provider": self.name,
            "status": "ok",
            "notifications": len(self.list_notifications()),
        }

    def _path(self, notification_id: str) -> Path:
        return self.data_dir.resolve(f"notifications/{notification_id}.yaml")

    @staticmethod
    def _read(path: Path) -> Notification:
        raw = load_structured_file(path)
        raw.setdefault("read", False)
        raw.setdefault("read_at", None)
        raw.setdefault("correlation_id", None)
        raw.setdefault("metadata", {})
        return Notification(**raw)
