from __future__ import annotations

from dataclasses import replace
from typing import Any

from synapse.core.exceptions import PermissionDenied, ValidationError
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.observability.correlation import current_correlation
from synapse.resources.models import ResourceAction, ResourceRef, ResourceScope

RESOURCE_PERMISSION_MAP = {
    ("file", "read"): "filesystem.read",
    ("file", "list"): "filesystem.list",
    ("file", "create"): "filesystem.write",
    ("file", "update"): "filesystem.write",
    ("file", "delete"): "filesystem.write",
    ("approval", "approve"): "approvals.approve",
    ("approval", "reject"): "approvals.reject",
    ("notification", "read"): "notifications.read",
    ("notification", "delete"): "notifications.delete",
}


def check_resource_access(
    agent_id: str,
    action: str | ResourceAction,
    resource_ref: ResourceRef,
    context: PermissionContext,
    *,
    permission_manager: PermissionManager,
    required_permission: str | None = None,
    effective_policy: Any | None = None,
) -> ResourceScope:
    action_name = str(action)
    ResourceAction(action_name)
    _check_effective_policy(action_name, resource_ref, effective_policy)

    correlation = current_correlation()
    scope = ResourceScope(
        agent_id=agent_id,
        action=action_name,
        resource_ref=resource_ref,
        correlation_id=correlation.correlation_id if correlation else None,
        device_id=context.device_id,
    )
    permission = required_permission or _permission_for(resource_ref.resource_type, action_name)
    scoped_context = replace(context, resource_scope=scope)
    permission_manager.require(scoped_context, permission)
    return scope


def _permission_for(resource_type: str, action: str) -> str:
    permission = RESOURCE_PERMISSION_MAP.get((resource_type, action))
    if not permission:
        raise ValidationError(
            f"No permission mapping for resource access: {resource_type}.{action}"
        )
    return permission


def _check_effective_policy(
    action: str,
    resource_ref: ResourceRef,
    effective_policy: Any | None,
) -> None:
    if effective_policy is None:
        return
    tool_name = resource_ref.metadata.get("tool_name")
    forbidden_tools = set(getattr(effective_policy, "forbidden_tools", []) or [])
    if tool_name and tool_name in forbidden_tools:
        raise PermissionDenied(f"Tool is forbidden by effective policy: {tool_name}")
    allowed_tools = set(getattr(effective_policy, "allowed_tools", []) or [])
    if tool_name and allowed_tools and tool_name not in allowed_tools:
        raise PermissionDenied(f"Tool is not allowed by effective policy: {tool_name}")
