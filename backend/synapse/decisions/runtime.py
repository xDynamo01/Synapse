from __future__ import annotations

from typing import Any

from synapse.admin_policy.runtime import AdminPolicyRuntime
from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.provisioning_policy import AgentProvisioningPolicyRuntime
from synapse.capabilities.runtime import CapabilityRuntime
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.decisions.models import DECISION_CATEGORIES, DecisionRequest, DecisionResult
from synapse.delegation.autonomy_policy import DelegationAutonomyPolicyRuntime
from synapse.delegation.runtime import DelegationRuntime
from synapse.observability.correlation import CorrelationContext
from synapse.policies.effective import EffectivePolicyRuntime
from synapse.tools.base import ToolRegistry


class DecisionRuntime:
    def __init__(
        self,
        event_bus: EventBus,
        permissions: PermissionManager,
        effective_policy: EffectivePolicyRuntime,
        capabilities: CapabilityRuntime,
        provisioning_policy: AgentProvisioningPolicyRuntime,
        admin_policy: AdminPolicyRuntime,
        tools: ToolRegistry,
        delegation_autonomy: DelegationAutonomyPolicyRuntime | None = None,
        delegation: DelegationRuntime | None = None,
        identities: AgentIdentityRuntime | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.permissions = permissions
        self.effective_policy = effective_policy
        self.capabilities = capabilities
        self.provisioning_policy = provisioning_policy
        self.admin_policy = admin_policy
        self.tools = tools
        self.delegation_autonomy = delegation_autonomy
        self.delegation = delegation
        self.identities = identities

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        category = request.category or self._infer_category(request)
        if category not in DECISION_CATEGORIES:
            result = DecisionResult(
                allowed=False,
                blocked=True,
                requires_approval=False,
                risk_level="low",
                blocked_reasons=[f"unknown decision category: {category}"],
                source_policies=["DecisionRuntime"],
                evaluated_components=["DecisionRuntime"],
                metadata={"category": category, "action": request.action},
            )
            self._emit(request, category, result)
            return result
        if category == "capability":
            result = self.evaluate_capability(request)
        elif category == "tool_execution":
            result = self.evaluate_tool(request)
        elif category == "agent_provisioning":
            result = self.evaluate_provisioning(request)
        elif category == "delegation_autonomy":
            result = self.evaluate_delegation_autonomy(request)
        else:
            result = self.evaluate_admin_action(request)
        self._emit(request, category, result)
        return result

    def evaluate_capability(self, request: DecisionRequest) -> DecisionResult:
        capability_id = request.capability_id or request.action
        agent_id = self._agent_id(request)
        context = self._context(request, agent_id)
        capability = self.capabilities.get_capability(capability_id)
        decision = self.capabilities.check_agent_capability(
            agent_id=agent_id,
            capability_id=capability_id,
            resource_scope=request.resource_scope,
            context=context,
        )
        policy = self.effective_policy.resolve(context, agent_id)
        blocked_reasons = [] if decision.allowed else [decision.reason]
        return DecisionResult(
            allowed=decision.allowed,
            blocked=not decision.allowed,
            requires_approval=False,
            risk_level=capability.risk_level,
            reasons=[decision.reason] if decision.allowed else [],
            blocked_reasons=blocked_reasons,
            source_policies=["CapabilityRuntime", "EffectivePolicyRuntime"],
            evaluated_components=["CapabilityRuntime", "EffectivePolicyRuntime"],
            metadata={
                "category": "capability",
                "capability_id": capability_id,
                "agent_id": agent_id,
                "allowed_capabilities": policy.allowed_capabilities,
                "decision": decision.reason,
            },
        )

    def evaluate_tool(self, request: DecisionRequest) -> DecisionResult:
        tool_name = request.action
        agent_id = self._agent_id(request)
        context = self._context(request, agent_id)
        runtime_definition = request.metadata.get("tool_definition")
        if runtime_definition:
            permission = runtime_definition.get("required_permission")
            risk_level_default = str(runtime_definition.get("risk_level", "low"))
            required_capability = runtime_definition.get("required_capability")
        else:
            spec = self.tools.get_spec(tool_name)
            permission = spec.permission
            risk_level_default = spec.risk_level
            required_capability = None
        policy = (
            self.effective_policy.resolve(context, agent_id)
            if (not runtime_definition or request.target_agent_id)
            else None
        )
        reasons: list[str] = []
        blocked_reasons: list[str] = []
        evaluated = ["PermissionManager", "EffectivePolicyRuntime"]
        source_policies = ["PermissionManager", "EffectivePolicyRuntime"]

        if permission:
            permission_decision = self.permissions.is_allowed(context, str(permission))
            policy_permission_allowed = bool(
                request.target_agent_id
                and policy
                and str(permission) in set(policy.allowed_permissions)
            )
            if permission_decision.allowed or policy_permission_allowed:
                reasons.append(f"permission granted: {permission}")
            else:
                blocked_reasons.append(f"missing permission: {permission}")
        else:
            reasons.append("no explicit permission required")

        if policy and not runtime_definition and not policy.allows_tool(tool_name):
            blocked_reasons.append(f"effective policy blocks tool: {tool_name}")
        if (
            policy
            and not runtime_definition
            and permission
            and str(permission) not in set(policy.allowed_permissions)
        ):
            blocked_reasons.append(f"effective policy does not allow permission: {permission}")

        capability = (
            self.capabilities.get_capability(str(required_capability))
            if required_capability
            else self.capabilities.capability_for_tool(tool_name)
        )
        capability_payload: dict[str, Any] | None = None
        if capability:
            evaluated.append("CapabilityRuntime")
            source_policies.append("CapabilityRuntime")
            capability_decision = self.capabilities.check_agent_capability(
                agent_id=agent_id,
                capability_id=capability.capability_id,
                context=context,
            )
            capability_payload = {
                "capability_id": capability.capability_id,
                "allowed": capability_decision.allowed,
                "reason": capability_decision.reason,
            }
            if capability_decision.allowed:
                reasons.append(f"capability allowed: {capability.capability_id}")
            else:
                blocked_reasons.append(
                    f"capability {capability.capability_id} blocked: {capability_decision.reason}"
                )

        risk_level = (
            policy.risk_level_for(tool_name, risk_level_default) if policy else risk_level_default
        )
        requires_approval = not blocked_reasons and bool(
            policy and policy.requires_approval_for(risk_level)
        )
        approval_required_by = "ApprovalPolicy" if requires_approval else None
        return DecisionResult(
            allowed=not blocked_reasons and not requires_approval,
            blocked=bool(blocked_reasons),
            requires_approval=requires_approval,
            risk_level=risk_level,
            reasons=reasons,
            blocked_reasons=_unique(blocked_reasons),
            source_policies=_unique(source_policies),
            evaluated_components=_unique(evaluated),
            approval_required_by=approval_required_by,
            metadata={
                "category": "tool_execution",
                "tool": tool_name,
                "permission": permission,
                "agent_id": agent_id,
                "capability": capability_payload,
                "runtime_tool": bool(runtime_definition),
                "resource_ref": request.metadata.get("resource_ref"),
                "effective_policy_used": policy is not None,
            },
        )

    def evaluate_provisioning(self, request: DecisionRequest) -> DecisionResult:
        metadata = request.metadata or {}
        action = request.action or "create"
        if action == "update":
            risk = self.provisioning_policy.evaluate_update(
                capabilities_allow=list(metadata.get("capabilities_allow", [])),
                autonomy_level=metadata.get("autonomy_level"),
                preferred_tools=list(metadata.get("preferred_tools", [])),
                forbidden_tools=list(metadata.get("forbidden_tools", [])),
                preferred_tools_were_provided="preferred_tools" in metadata,
            )
        else:
            risk = self.provisioning_policy.evaluate_create(
                capabilities_allow=list(metadata.get("capabilities_allow", [])),
                autonomy_level=metadata.get("autonomy_level"),
                preferred_tools=list(metadata.get("preferred_tools", [])),
                forbidden_tools=list(metadata.get("forbidden_tools", [])),
            )
        return DecisionResult(
            allowed=risk.allowed and not risk.requires_approval,
            blocked=not risk.allowed,
            requires_approval=risk.requires_approval,
            risk_level=risk.risk_level,
            reasons=risk.reasons,
            blocked_reasons=risk.blocked_reasons,
            source_policies=["AgentProvisioningPolicyRuntime"],
            evaluated_components=["AgentProvisioningPolicyRuntime"],
            approval_required_by="AgentProvisioningPolicyRuntime"
            if risk.requires_approval
            else None,
            metadata={"category": "agent_provisioning", "risk_decision": risk.to_dict()},
        )

    def evaluate_admin_action(self, request: DecisionRequest) -> DecisionResult:
        agent_id = request.target_agent_id or request.metadata.get("agent_id") or request.action
        action = request.action
        context = self._context(request, request.actor_id or agent_id)
        decision = self.admin_policy.check(context, action, str(agent_id))
        return DecisionResult(
            allowed=decision.allowed,
            blocked=not decision.allowed and not decision.requires_approval,
            requires_approval=decision.requires_approval,
            risk_level="medium" if decision.requires_approval else "low",
            reasons=decision.reasons,
            blocked_reasons=decision.blocked_reasons,
            source_policies=["AdminPolicyRuntime"],
            evaluated_components=["AdminPolicyRuntime"],
            approval_required_by="AdminPolicyRuntime" if decision.requires_approval else None,
            metadata={"category": "admin_action", "admin_decision": decision.to_dict()},
        )

    def evaluate_delegation_autonomy(self, request: DecisionRequest) -> DecisionResult:
        if not self.delegation_autonomy or not self.delegation or not self.identities:
            return DecisionResult(
                allowed=False,
                blocked=True,
                requires_approval=False,
                risk_level="low",
                blocked_reasons=["delegation autonomy decision runtime is not configured"],
                source_policies=["DecisionRuntime"],
                evaluated_components=["DecisionRuntime"],
                metadata={"category": "delegation_autonomy"},
            )
        task_id = str(request.metadata.get("task_id") or request.target_agent_id or "").strip()
        if not task_id:
            return DecisionResult(
                allowed=False,
                blocked=True,
                requires_approval=False,
                risk_level="low",
                blocked_reasons=["task_id is required"],
                source_policies=["DecisionRuntime"],
                evaluated_components=["DecisionRuntime"],
                metadata={"category": "delegation_autonomy"},
            )
        task = self.delegation.get_task(task_id)
        context = self._context(request, task.assignee_agent_id)
        identity = self.identities.load_identity(task.assignee_agent_id)
        effective_policy = self.effective_policy.resolve(context, task.assignee_agent_id)
        if request.action == "accept":
            decision = self.delegation_autonomy.evaluate_accept(task, identity, effective_policy)
        elif request.action == "start":
            decision = self.delegation_autonomy.evaluate_start(task, identity, effective_policy)
        else:
            decision = self.delegation_autonomy.evaluate_reject(task, identity, effective_policy)
        return DecisionResult(
            allowed=decision.allowed,
            blocked=decision.blocked,
            requires_approval=decision.requires_approval,
            risk_level=decision.risk_level,
            reasons=decision.reasons,
            blocked_reasons=decision.blocked_reasons,
            source_policies=["DelegationAutonomyPolicyRuntime"],
            evaluated_components=["DelegationAutonomyPolicyRuntime"],
            approval_required_by="DelegationAutonomyPolicyRuntime"
            if decision.requires_approval
            else None,
            metadata={"category": "delegation_autonomy", "decision": decision.to_dict()},
        )

    def explain_decision(self, request: DecisionRequest) -> dict[str, Any]:
        result = self.evaluate(request)
        return {
            "request": {
                "category": request.category,
                "action": request.action,
                "actor_type": request.actor_type,
                "actor_id": request.actor_id,
                "target_agent_id": request.target_agent_id,
                "capability_id": request.capability_id,
                "correlation_id": request.correlation_id,
                "metadata": request.metadata,
            },
            "result": result.to_dict(),
            "summary": self._summary(result),
        }

    def _emit(self, request: DecisionRequest, category: str, result: DecisionResult) -> None:
        payload = {
            "category": category,
            "action": request.action,
            "actor": {
                "actor_type": request.actor_type,
                "actor_id": request.actor_id,
            },
            "allowed": result.allowed,
            "blocked": result.blocked,
            "requires_approval": result.requires_approval,
            "source_policies": result.source_policies,
            "correlation_id": request.correlation_id,
        }
        correlation = (
            CorrelationContext(
                correlation_id=request.correlation_id,
                source="decision_runtime",
                agent_id=request.target_agent_id,
            )
            if request.correlation_id
            else None
        )
        actor_id = request.actor_id or request.target_agent_id or "decision_runtime"
        self.event_bus.emit("decision.evaluated", actor_id, payload, correlation=correlation)
        if result.blocked:
            self.event_bus.emit("decision.blocked", actor_id, payload, correlation=correlation)
        if result.requires_approval:
            self.event_bus.emit(
                "decision.requires_approval",
                actor_id,
                payload,
                correlation=correlation,
            )

    @staticmethod
    def _summary(result: DecisionResult) -> str:
        if result.blocked:
            return "blocked: " + "; ".join(result.blocked_reasons)
        if result.requires_approval:
            return f"requires approval by {result.approval_required_by}"
        if result.allowed:
            return "allowed"
        return "not allowed"

    @staticmethod
    def _infer_category(request: DecisionRequest) -> str:
        if request.capability_id:
            return "capability"
        if request.action.startswith("agent."):
            return "admin_action"
        return "tool_execution"

    @staticmethod
    def _agent_id(request: DecisionRequest) -> str:
        return request.target_agent_id or request.actor_id or "decision_runtime"

    @staticmethod
    def _context(request: DecisionRequest, fallback_actor_id: str) -> PermissionContext:
        return PermissionContext(
            actor_id=request.actor_id or fallback_actor_id,
            actor_type=request.actor_type,
            resource_scope=request.resource_scope,
        )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
