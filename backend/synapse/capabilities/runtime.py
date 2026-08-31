from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.capabilities.models import Capability, CapabilityDecision
from synapse.capabilities.registry import CapabilityRegistry
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext
from synapse.observability.correlation import current_correlation


class CapabilityRuntime:
    def __init__(
        self,
        registry: CapabilityRegistry,
        policies,
        event_bus: EventBus,
        data_dir: DataDir,
    ) -> None:
        self.registry = registry
        self.policies = policies
        self.event_bus = event_bus
        self.data_dir = data_dir

    def list_capabilities(self) -> list[Capability]:
        return self.registry.list_capabilities()

    def get_capability(self, capability_id: str) -> Capability:
        return self.registry.get(capability_id)

    def agent_capabilities(
        self,
        agent_id: str,
        context: PermissionContext | None = None,
    ) -> list[Capability]:
        context = context or PermissionContext(actor_id=agent_id, actor_type="agent")
        policy = self.policies.resolve(context, agent_id)
        allowed = set(policy.allowed_capabilities)
        return [
            capability
            for capability in self.list_capabilities()
            if capability.capability_id in allowed
        ]

    def check_agent_capability(
        self,
        agent_id: str,
        capability_id: str,
        resource_scope: Any | None = None,
        context: PermissionContext | None = None,
    ) -> CapabilityDecision:
        capability = self.get_capability(capability_id)
        context = context or PermissionContext(actor_id=agent_id, actor_type="agent")
        policy = self.policies.resolve(context, agent_id)
        decisions = policy.capability_decisions
        raw_decision = decisions.get(
            capability_id,
            {"allowed": False, "reason": "capability_not_resolved"},
        )
        allowed = bool(raw_decision.get("allowed", False))
        reason = str(raw_decision.get("reason", "unknown"))
        resource_payload = _resource_scope_payload(resource_scope)
        resource_type = resource_payload.get("resource_type") if resource_payload else None
        if (
            allowed
            and resource_type
            and capability.allowed_resource_types
            and resource_type not in set(capability.allowed_resource_types)
        ):
            allowed = False
            reason = "resource_type_not_allowed"
        decision = CapabilityDecision(
            agent_id=agent_id,
            capability_id=capability_id,
            allowed=allowed,
            reason=reason,
            resource_scope=resource_payload,
        )
        self._emit_decision(decision)
        return decision

    def explain_agent_capability(
        self,
        agent_id: str,
        capability_id: str,
        context: PermissionContext | None = None,
    ) -> dict[str, Any]:
        capability = self.get_capability(capability_id)
        decision = self.check_agent_capability(
            agent_id=agent_id,
            capability_id=capability_id,
            context=context,
        )
        return {
            "capability": asdict(capability),
            "decision": asdict(decision),
        }

    def capability_for_tool(self, tool_name: str) -> Capability | None:
        return self.registry.capability_for_tool(tool_name)

    def _emit_decision(self, decision: CapabilityDecision) -> None:
        payload = asdict(decision)
        correlation = current_correlation()
        if correlation:
            payload["correlation_id"] = correlation.correlation_id
        self.event_bus.emit("capability.checked", decision.agent_id, payload)


def _resource_scope_payload(resource_scope: Any | None) -> dict[str, Any] | None:
    if resource_scope is None:
        return None
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
            }
        )
    payload = {key: value for key, value in payload.items() if value is not None}
    return payload or None
