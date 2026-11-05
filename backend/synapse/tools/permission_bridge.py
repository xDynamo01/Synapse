from __future__ import annotations

from dataclasses import asdict, replace
from uuid import uuid4

from synapse.approvals.manager import ApprovalManager
from synapse.capabilities.runtime import CapabilityRuntime
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.decisions.models import DecisionRequest
from synapse.decisions.runtime import DecisionRuntime
from synapse.policies.effective import EffectivePolicyRuntime
from synapse.resources import ResourceScope, check_resource_access
from synapse.tools.models import ToolDefinition, ToolExecutionDecision, ToolExecutionRequest


class ToolPermissionBridge:
    def __init__(
        self,
        permissions: PermissionManager,
        approvals: ApprovalManager,
        decisions: DecisionRuntime,
        policies: EffectivePolicyRuntime,
        capabilities: CapabilityRuntime,
        event_bus: EventBus,
    ) -> None:
        self.permissions = permissions
        self.approvals = approvals
        self.decisions = decisions
        self.policies = policies
        self.capabilities = capabilities
        self.event_bus = event_bus

    def evaluate(
        self,
        definition: ToolDefinition,
        request: ToolExecutionRequest,
    ) -> ToolExecutionDecision:
        actor_id = request.agent_id or request.caller or "tool_runtime"
        actor_type = "agent" if request.agent_id else request.caller_type
        context = PermissionContext(actor_id=actor_id, actor_type=actor_type)
        resource_scope = self._resource_scope(definition, request, context)
        if resource_scope:
            context = replace(context, resource_scope=resource_scope)

        if definition.metadata.get("legacy_catalog") and not request.agent_id and actor_type != "agent":
            if definition.required_permission:
                self.permissions.require(context, definition.required_permission)
            decision = ToolExecutionDecision(
                allowed=True,
                blocked=False,
                requires_approval=False,
                reasons=[
                    f"permission granted: {definition.required_permission}"
                    if definition.required_permission
                    else "no explicit permission required"
                ],
                policy_metadata={"compatibility": "legacy_user_tool"},
            )
            self._emit(definition, request, decision)
            return decision

        decision_metadata = {
            "tool_id": definition.tool_id,
            "resource_ref": asdict(request.resource_ref) if request.resource_ref else None,
            "risk_level": definition.risk_level,
        }
        if not definition.metadata.get("legacy_catalog"):
            decision_metadata["tool_definition"] = asdict(definition)
        decision_result = self.decisions.evaluate(
            DecisionRequest(
                actor_type=actor_type,
                actor_id=actor_id,
                target_agent_id=request.agent_id,
                category="tool_execution",
                action=definition.tool_id,
                capability_id=definition.required_capability,
                resource_scope=resource_scope,
                correlation_id=request.correlation_id,
                metadata=decision_metadata,
            )
        )
        reasons = list(decision_result.reasons)
        blocked_reasons = list(decision_result.blocked_reasons)
        requires_approval = decision_result.requires_approval or definition.approval_required
        approval_id = None

        if definition.resource_scope_required and request.resource_ref is None:
            blocked_reasons.append("resource scope is required")

        if blocked_reasons:
            decision = ToolExecutionDecision(
                allowed=False,
                blocked=True,
                requires_approval=False,
                reasons=reasons,
                blocked_reasons=_unique(blocked_reasons),
                policy_metadata={"decision": decision_result.to_dict()},
            )
            self._emit(definition, request, decision)
            return decision

        if request.approval_id:
            self.approvals.assert_approved_for_tool(
                request.approval_id,
                actor_id,
                definition.tool_id,
                request.arguments,
                definition.risk_level,
            )
            decision = ToolExecutionDecision(
                allowed=True,
                blocked=False,
                requires_approval=False,
                reasons=[*reasons, "approved call binding validated"],
                approval_id=request.approval_id,
                policy_metadata={"decision": decision_result.to_dict()},
            )
            self._emit(definition, request, decision)
            return decision

        if requires_approval:
            if not request.dry_run:
                approval = self.approvals.create_request(
                    context=context,
                    tool_name=definition.tool_id,
                    tool_args=request.arguments,
                    risk_level=definition.risk_level,
                    reason=f"Tool {definition.tool_id} risk level {definition.risk_level} requires approval.",
                    tool_call_id=request.id or str(uuid4()),
                    session_id=request.conversation_id,
                    project_id=request.mission_id,
                )
                approval_id = approval.id
            decision = ToolExecutionDecision(
                allowed=False,
                blocked=False,
                requires_approval=True,
                reasons=[*reasons, "approval required"],
                approval_id=approval_id,
                policy_metadata={"decision": decision_result.to_dict()},
            )
            self._emit(definition, request, decision)
            return decision

        decision = ToolExecutionDecision(
            allowed=True,
            blocked=False,
            requires_approval=False,
            reasons=reasons or ["allowed"],
            policy_metadata={"decision": decision_result.to_dict()},
        )
        self._emit(definition, request, decision)
        return decision

    def _resource_scope(
        self,
        definition: ToolDefinition,
        request: ToolExecutionRequest,
        context: PermissionContext,
    ) -> ResourceScope | None:
        if not request.resource_ref:
            return None
        return check_resource_access(
            agent_id=request.agent_id or request.caller,
            action="execute",
            resource_ref=request.resource_ref,
            context=context,
            permission_manager=self.permissions,
            required_permission=definition.required_permission,
            effective_policy=self.policies.resolve(context, request.agent_id)
            if request.agent_id
            else None,
        )

    def _emit(
        self,
        definition: ToolDefinition,
        request: ToolExecutionRequest,
        decision: ToolExecutionDecision,
    ) -> None:
        self.event_bus.emit(
            "tool.permission_decided",
            request.agent_id or request.caller,
            {
                "tool_id": definition.tool_id,
                "allowed": decision.allowed,
                "blocked": decision.blocked,
                "requires_approval": decision.requires_approval,
                "approval_id": decision.approval_id,
                "agent_id": request.agent_id,
                "caller_type": request.caller_type,
                "correlation_id": request.correlation_id,
            },
        )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
