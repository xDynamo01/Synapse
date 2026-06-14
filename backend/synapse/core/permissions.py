from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from synapse.core.events import EventBus
from synapse.core.exceptions import PermissionDenied
from synapse.core.serialization import load_structured_file


@dataclass(frozen=True)
class PermissionContext:
    actor_id: str
    actor_type: str = "user"
    device_id: str | None = None
    autonomy: str = "manual"

    @property
    def subject_keys(self) -> tuple[str, str]:
        return (self.actor_id, f"{self.actor_type}:{self.actor_id}")


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    permission: str
    actor_id: str
    actor_type: str
    reason: str


class PermissionManager:
    def __init__(self, data_dir: Path, event_bus: EventBus):
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.subjects = self._load_subjects()

    def _load_subjects(self) -> dict[str, set[str]]:
        path = self.data_dir / "config" / "permissions.yaml"
        raw = load_structured_file(path)
        subjects = raw.get("subjects", {})
        if not isinstance(subjects, dict):
            return {}

        normalized: dict[str, set[str]] = {}
        for subject, permissions in subjects.items():
            if isinstance(permissions, list):
                normalized[str(subject)] = {str(item) for item in permissions}
        return normalized

    def is_allowed(self, context: PermissionContext, permission: str) -> PermissionDecision:
        permissions: set[str] = set()
        for key in context.subject_keys:
            permissions.update(self.subjects.get(key, set()))

        if "*" in permissions or permission in permissions:
            return PermissionDecision(
                allowed=True,
                permission=permission,
                actor_id=context.actor_id,
                actor_type=context.actor_type,
                reason="granted",
            )

        return PermissionDecision(
            allowed=False,
            permission=permission,
            actor_id=context.actor_id,
            actor_type=context.actor_type,
            reason="missing_permission",
        )

    def require(self, context: PermissionContext, permission: str) -> PermissionDecision:
        decision = self.is_allowed(context, permission)
        self.event_bus.emit(
            "permission.decision",
            context.actor_id,
            {
                "allowed": decision.allowed,
                "permission": permission,
                "actor_type": context.actor_type,
                "reason": decision.reason,
            },
        )
        if not decision.allowed:
            raise PermissionDenied(
                f"{context.actor_type}:{context.actor_id} lacks permission {permission}"
            )
        return decision

