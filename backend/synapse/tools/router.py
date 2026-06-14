from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from synapse.core.events import EventBus
from synapse.core.exceptions import PermissionDenied, SynapseError
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.tools.base import ToolRegistry
from synapse.tools.calls import ToolCallPlan, ToolCallRequest, ToolCallResult


class ToolRouter:
    def __init__(
        self,
        registry: ToolRegistry,
        permissions: PermissionManager,
        event_bus: EventBus,
    ):
        self.registry = registry
        self.permissions = permissions
        self.event_bus = event_bus

    def execute_plan(
        self,
        context: PermissionContext,
        plan: ToolCallPlan,
        allowed_permissions: Iterable[str] | None = None,
    ) -> list[ToolCallResult]:
        return [
            self.execute_call(context, call, allowed_permissions=allowed_permissions)
            for call in plan.calls
        ]

    def execute_call(
        self,
        context: PermissionContext,
        call: ToolCallRequest,
        allowed_permissions: Iterable[str] | None = None,
    ) -> ToolCallResult:
        self.event_bus.emit("tool.requested", context.actor_id, asdict(call))
        try:
            spec = self.registry.get_spec(call.name)
            decision = self.permissions.require(context, spec.permission)
            self.event_bus.emit(
                "tool.permission_checked",
                context.actor_id,
                {
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "permission": spec.permission,
                    "allowed": decision.allowed,
                },
            )
            if allowed_permissions is not None:
                allowed = set(allowed_permissions)
                if "*" not in allowed and spec.permission not in allowed:
                    return self._failed_result(
                        context,
                        call,
                        PermissionDenied(
                            f"{context.actor_type}:{context.actor_id} is not allowed "
                            f"to use tool {call.name}"
                        ),
                    )
            result = self.registry.execute(call.name, context, call.arguments)
            tool_result = ToolCallResult(request=call, success=True, result=result)
            self.event_bus.emit(
                "tool.executed",
                context.actor_id,
                {
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "success": True,
                },
            )
            return tool_result
        except PermissionDenied as exc:
            self.event_bus.emit(
                "tool.permission_checked",
                context.actor_id,
                {
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "allowed": False,
                    "error": str(exc),
                },
            )
            return self._failed_result(context, call, exc)
        except Exception as exc:
            return self._failed_result(context, call, exc)

    def _failed_result(
        self,
        context: PermissionContext,
        call: ToolCallRequest,
        exc: Exception,
    ) -> ToolCallResult:
        error = str(exc) or type(exc).__name__
        self.event_bus.emit(
            "tool.failed",
            context.actor_id,
            {
                "tool_call_id": call.id,
                "tool": call.name,
                "success": False,
                "error": error,
                "error_type": type(exc).__name__,
            },
        )
        if isinstance(exc, SynapseError):
            error = str(exc)
        return ToolCallResult(request=call, success=False, error=error)
