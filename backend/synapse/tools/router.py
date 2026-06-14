from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Iterable

from synapse.approvals.manager import ApprovalManager
from synapse.core.events import EventBus
from synapse.core.exceptions import PermissionDenied, SynapseError
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.tools.base import ToolRegistry
from synapse.tools.calls import ToolCallPlan, ToolCallRequest, ToolCallResult

if TYPE_CHECKING:
    from synapse.policies.effective import AgentEffectivePolicy


class ToolRouter:
    def __init__(
        self,
        registry: ToolRegistry,
        permissions: PermissionManager,
        approvals: ApprovalManager,
        event_bus: EventBus,
    ):
        self.registry = registry
        self.permissions = permissions
        self.approvals = approvals
        self.event_bus = event_bus

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
            if policy and not policy.allows_tool(call.name):
                return self._failed_result(
                    context,
                    call,
                    PermissionDenied(
                        f"Agent effective policy blocks tool {call.name} for {policy.agent_id}"
                    ),
                )
            if policy is not None:
                allowed = set(policy.allowed_permissions)
                if spec.permission not in allowed:
                    return self._failed_result(
                        context,
                        call,
                        PermissionDenied(
                            f"Agent effective policy does not allow permission {spec.permission}"
                        ),
                    )
            elif allowed_permissions is not None:
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
            risk_level = policy.risk_level_for(call.name, spec.risk_level) if policy else spec.risk_level
            approval_result = self._approval_result_if_required(
                context,
                call,
                risk_level,
                session_id=session_id,
                original_message_id=original_message_id,
                project_id=project_id,
                policy=policy,
            )
            if approval_result:
                return approval_result
            result = self.registry.execute(call.name, context, call.arguments)
            tool_result = ToolCallResult(
                request=call,
                success=True,
                status="executed",
                result=result,
                approval_id=call.approval_id,
            )
            self.event_bus.emit(
                "tool.executed",
                context.actor_id,
                {
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "success": True,
                },
            )
            if call.approval_id:
                self.approvals.mark_resumed(context, call.approval_id, asdict(tool_result))
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

    def _approval_result_if_required(
        self,
        context: PermissionContext,
        call: ToolCallRequest,
        risk_level: str,
        session_id: str | None = None,
        original_message_id: str | None = None,
        project_id: str | None = None,
        policy: AgentEffectivePolicy | None = None,
    ) -> ToolCallResult | None:
        if call.approval_id:
            self.approvals.assert_approved_for_tool(
                approval_id=call.approval_id,
                agent_id=context.actor_id,
                tool_name=call.name,
                tool_args=call.arguments,
                risk_level=risk_level,
            )
            return None

        if policy is not None:
            if not policy.requires_approval_for(risk_level):
                return None
        elif not self.approvals.requires_approval(
            agent_id=context.actor_id,
            risk_level=risk_level,
            permission_explicitly_granted=True,
        ):
            return None

        approval = self.approvals.create_request(
            context=context,
            tool_name=call.name,
            tool_args=call.arguments,
            risk_level=risk_level,
            reason=f"Tool {call.name} risk level {risk_level} requires human approval.",
            tool_call_id=call.id,
            session_id=session_id,
            original_message_id=original_message_id,
            project_id=project_id,
        )
        return ToolCallResult(
            request=call,
            success=False,
            status="awaiting_approval",
            result={"approval_id": approval.id, "approval_status": approval.status},
            approval_id=approval.id,
        )

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
        return ToolCallResult(request=call, success=False, status="failed", error=error)
