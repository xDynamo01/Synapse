from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synapse.core.events import EventBus
from synapse.core.exceptions import PermissionDenied
from synapse.core.serialization import load_structured_file


@dataclass(frozen=True)
class PermissionContext:
    actor_id: str
    actor_type: str = "user"
    device_id: str | None = None
    autonomy: str = "manual"
    resource_scope: Any | None = None

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
        self.subjects, self.denies = self._load_permissions()

    def _load_permissions(self) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        path = self.data_dir / "config" / "permissions.yaml"
        raw = load_structured_file(path)
        subjects = raw.get("subjects", {})
        denies = raw.get("denies", {})
        if not isinstance(subjects, dict):
            subjects = {}
        if not isinstance(denies, dict):
            denies = {}

        normalized: dict[str, set[str]] = {}
        for subject, permissions in subjects.items():
            if isinstance(permissions, list):
                normalized[str(subject)] = {str(item) for item in permissions}
            elif isinstance(permissions, dict):
                normalized[str(subject)] = {str(item) for item in permissions.get("allow", [])}

        normalized_denies: dict[str, set[str]] = {}
        for subject, permissions in denies.items():
            if isinstance(permissions, list):
                normalized_denies[str(subject)] = {str(item) for item in permissions}
        for subject, permissions in subjects.items():
            if isinstance(permissions, dict):
                normalized_denies[str(subject)] = {
                    str(item) for item in permissions.get("deny", [])
                }
        return normalized, normalized_denies

    def permissions_for(self, context: PermissionContext) -> set[str]:
        permissions: set[str] = set()
        for key in context.subject_keys:
            permissions.update(self.subjects.get(key, set()))
        return permissions

    def denied_permissions_for(self, context: PermissionContext) -> set[str]:
        permissions: set[str] = set()
        for key in context.subject_keys:
            permissions.update(self.denies.get(key, set()))
        return permissions

    def is_allowed(self, context: PermissionContext, permission: str) -> PermissionDecision:
        denied_permissions = self.denied_permissions_for(context)
        if "*" in denied_permissions or permission in denied_permissions:
            return PermissionDecision(
                allowed=False,
                permission=permission,
                actor_id=context.actor_id,
                actor_type=context.actor_type,
                reason="explicit_deny",
            )

        permissions = self.permissions_for(context)
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
        payload = {
            "allowed": decision.allowed,
            "permission": permission,
            "actor_type": context.actor_type,
            "reason": decision.reason,
        }
        payload.update(_resource_scope_payload(context.resource_scope))
        self.event_bus.emit(
            "permission.decision",
            context.actor_id,
            payload,
        )
        if not decision.allowed:
            raise PermissionDenied(
                f"{context.actor_type}:{context.actor_id} lacks permission {permission}"
            )
        return decision


def _resource_scope_payload(resource_scope: Any | None) -> dict[str, Any]:
    if resource_scope is None:
        return {}
    resource_ref = getattr(resource_scope, "resource_ref", None)
    payload = {
        "agent_id": getattr(resource_scope, "agent_id", None),
        "action": getattr(resource_scope, "action", None),
        "correlation_id": getattr(resource_scope, "correlation_id", None),
        "device_id": getattr(resource_scope, "device_id", None),
    }
    if resource_ref is not None:
        payload.update(
            {
                "resource_type": getattr(resource_ref, "resource_type", None),
                "resource_id": getattr(resource_ref, "resource_id", None),
                "path": getattr(resource_ref, "path", None),
                "owner_agent_id": getattr(resource_ref, "owner_agent_id", None),
                "project_id": getattr(resource_ref, "project_id", None),
            }
        )
    return {key: value for key, value in payload.items() if value is not None}
