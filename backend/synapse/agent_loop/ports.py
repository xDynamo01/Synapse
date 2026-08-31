from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from synapse.observability.redaction import redact


@dataclass(frozen=True)
class Notification:
    type: str
    title: str
    summary: str
    severity: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    entity_refs: list[dict[str, str]] = field(default_factory=list)
    expires_at: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))


class NotificationSink(Protocol):
    def notify(self, notification: Notification) -> Any: ...


class LocalNotificationSink:
    """Frontend-neutral adapter backed by the canonical local inbox runtime."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def notify(self, notification: Notification) -> Any:
        severity = {
            "informational": "info",
            "low": "info",
            "medium": "warning",
            "high": "warning",
        }.get(notification.severity, notification.severity)
        return self.runtime.create_notification(
            title=notification.title,
            message=notification.summary,
            severity=severity,
            source="agent_loop",
            category="system",
            metadata=redact(
                {
                    "notification_type": notification.type,
                    "actions": notification.actions,
                    "entity_refs": notification.entity_refs,
                    "expires_at": notification.expires_at,
                    **notification.metadata,
                }
            ),
            correlation_id=notification.correlation_id,
        )
