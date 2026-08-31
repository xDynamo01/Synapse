from __future__ import annotations

from typing import Protocol

from synapse.notifications.models import Notification


class NotificationProvider(Protocol):
    name: str

    def send(self, notification: Notification) -> Notification: ...

    def mark_read(self, notification_id: str) -> Notification: ...

    def list_notifications(self) -> list[Notification]: ...

    def list_unread(self) -> list[Notification]: ...

    def health_check(self) -> dict[str, object]: ...
