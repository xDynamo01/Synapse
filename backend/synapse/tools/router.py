from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from synapse.core.events import EventBus
from synapse.core.exceptions import PermissionDenied, ToolExecutionError
from synapse.core.permissions import PermissionContext
from synapse.tools.calls import ToolCallPlan, ToolCallRequest, ToolCallResult
from synapse.tools.models import ToolExecutionRequest

if TYPE_CHECKING:
    from synapse.policies.effective import AgentEffectivePolicy
    from synapse.tools.contracts import ToolExecutionPort


class ToolRouter:
    """Compatibility adapter from legacy model-tool DTOs to ToolRuntime."""

    def __init__(
        self,
        _legacy_registry: Any,
        _permissions: Any,
        _approvals: Any,
        event_bus: EventBus,
        _presence: Any | None = None,
        _capabilities: Any | None = None,
        tools: ToolExecutionPort | None = None,
    ) -> None:
        self.tools = tools
        self.event_bus = event_bus

    def bind(self, tools: ToolExecutionPort) -> None:
        if self.tools is not None and self.tools is not tools:
            raise RuntimeError("ToolRouter is already bound to another ToolRuntime")
        self.tools = tools

    def execute(
        self,
        name: str,
        context: PermissionContext,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runtime = self._runtime()
        result = runtime.execute_tool_call(
            self._request(context, ToolCallRequest(name=name, arguments=arguments or {})),
            options={"raise_errors": True},
        )
        if not result.success:
            decision = result.metadata.get("decision", {})
            if decision.get("blocked"):
                raise PermissionDenied(result.error or "Tool execution denied")
            raise ToolExecutionError(result.error or f"Tool execution failed: {name}")
        return result.output

    def execute_plan(
        self,
        context: PermissionContext,
        plan: ToolCallPlan,
        allowed_permissions: Iterable[str] | None = None,
        session_id: str | None = None,
        original_message_id: str | None = None,
        project_id: str | None = None,
        policy: AgentEffectivePolicy | None = None,
    ) -> list[ToolCallResult]:
        return [
            self.execute_call(
                context,
                call,
                allowed_permissions=allowed_permissions,
                session_id=session_id,
                original_message_id=original_message_id,
                project_id=project_id,
                policy=policy,
            )
            for call in plan.calls
        ]

    def execute_call(
        self,
        context: PermissionContext,
        call: ToolCallRequest,
        allowed_permissions: Iterable[str] | None = None,
        session_id: str | None = None,
        original_message_id: str | None = None,
        project_id: str | None = None,
        policy: AgentEffectivePolicy | None = None,
    ) -> ToolCallResult:
        del allowed_permissions, original_message_id, policy
        self.event_bus.emit("tool.requested", context.actor_id, call.__dict__)
        result = self._runtime().execute_tool_call(
            self._request(
                context,
                call,
                conversation_id=session_id,
                mission_id=project_id,
            )
        )
        spec = self._runtime().registry.get_spec(call.name)
        decision = result.metadata.get("decision", {})
        blocked_reasons = decision.get("blocked_reasons", [])
        permission_denied = any(
            str(reason).startswith("missing permission:") for reason in blocked_reasons
        )
        compatibility_error = (
            f"{context.actor_type}:{context.actor_id} lacks permission {spec.permission}"
            if permission_denied
            else result.error
        )
        self.event_bus.emit(
            "tool.permission_checked",
            context.actor_id,
            {
                "tool_call_id": call.id,
                "tool": call.name,
                "permission": spec.permission,
                "allowed": not permission_denied,
                **({"error": compatibility_error} if permission_denied else {}),
            },
        )
        approval_id = result.metadata.get("approval_id") or call.approval_id
        if result.success:
            legacy = ToolCallResult(
                request=call,
                success=True,
                status="executed",
                result=result.output,
                approval_id=approval_id,
            )
            self.event_bus.emit(
                "tool.executed",
                context.actor_id,
                {"tool_call_id": call.id, "tool": call.name, "success": True},
            )
            return legacy
        status = "awaiting_approval" if result.status == "awaiting_approval" else "failed"
        legacy = ToolCallResult(
            request=call,
            success=False,
            status=status,
            result=(
                {"approval_id": approval_id, "approval_status": "pending"}
                if status == "awaiting_approval"
                else None
            ),
            error=compatibility_error,
            approval_id=approval_id,
        )
        if status == "failed":
            self.event_bus.emit(
                "tool.failed",
                context.actor_id,
                {
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "success": False,
                    "error": compatibility_error,
                    "error_type": result.metadata.get("error_type"),
                },
            )
        return legacy

    def list_specs(self):
        return self._runtime().registry.list_specs()

    def get_spec(self, tool_id: str):
        return self._runtime().registry.get_spec(tool_id)

    def _runtime(self) -> ToolExecutionPort:
        if self.tools is None:
            raise ToolExecutionError("Canonical ToolRuntime is unavailable")
        return self.tools

    @staticmethod
    def _request(
        context: PermissionContext,
        call: ToolCallRequest,
        *,
        conversation_id: str | None = None,
        mission_id: str | None = None,
    ) -> ToolExecutionRequest:
        return ToolExecutionRequest(
            tool_id=call.name,
            arguments=dict(call.arguments),
            caller=context.actor_id,
            caller_type=context.actor_type,
            agent_id=context.actor_id if context.actor_type == "agent" else None,
            conversation_id=conversation_id,
            mission_id=mission_id,
            approval_id=call.approval_id,
            id=call.id,
            requester=context.actor_id,
            metadata={"source": "legacy_tool_router"},
        )
