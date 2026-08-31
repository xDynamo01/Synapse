from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from synapse.core.data_dir import DataDir
from synapse.core.exceptions import NotFound
from synapse.notifications.models import Notification
from synapse.storage.collection import FileCollection
from synapse.storage.errors import StorageRecordNotFound


class LocalNotificationProvider:
    name = "local"

    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir
        self.collection = FileCollection(
            collection_id="notifications",
            root=data_dir.resolve("notifications"),
            current_schema_version=1,
            validator=_validate_notification,
            schema_version=lambda payload: int(payload.get("schema_version", 1)),
            revision=lambda _payload: 1,
            recovery_policy="quarantine_record",
        )

    def send(self, notification: Notification) -> Notification:
        self.collection.put(notification.id, asdict(notification))
        return notification

    def get(self, notification_id: str) -> Notification:
        try:
            return self._from_payload(dict(self.collection.get(notification_id).payload))
        except StorageRecordNotFound as exc:
            raise NotFound(f"Notification not found: {notification_id}") from exc

    def mark_read(self, notification_id: str) -> Notification:
        current = self.get(notification_id)
        updated = Notification(
            id=current.id,
            title=current.title,
            message=current.message,
            severity=current.severity,
            source=current.source,
            category=current.category,
            schema_version=current.schema_version,
            record_type=current.record_type,
            created_at=current.created_at,
            updated_at=datetime.now(UTC).isoformat(),
            read=True,
            read_at=current.read_at or datetime.now(UTC).isoformat(),
            correlation_id=current.correlation_id,
            metadata=current.metadata,
        )
        return self.send(updated)

    def delete(self, notification_id: str) -> None:
        if not self.collection.delete(notification_id).deleted:
            raise NotFound(f"Notification not found: {notification_id}")

    def delete_existing(self, notification_id: str) -> bool:
        return self.collection.delete(notification_id).deleted

    def list_notifications(self) -> list[Notification]:
        return [self._from_payload(dict(record.payload)) for record in self.collection.list_all()]

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
    def _from_payload(raw: dict) -> Notification:
        raw.setdefault("read", False)
        raw.setdefault("read_at", None)
        raw.setdefault("correlation_id", None)
        raw.setdefault("metadata", {})
        raw.setdefault("schema_version", 1)
        raw.setdefault("record_type", "notification")
        raw.setdefault("updated_at", raw.get("created_at"))
        return Notification(**raw)


def _validate_notification(payload: Mapping[str, object]) -> None:
    required = {"id", "title", "message", "severity", "source", "category"}
    if not required <= payload.keys():
        raise ValueError("notification record is incomplete")
