from __future__ import annotations

from dataclasses import asdict, dataclass, field

from synapse.capabilities.registry import CapabilityRegistry
from synapse.core.data_dir import DataDir
from synapse.core.serialization import load_structured_file


@dataclass(frozen=True)
class AgentProvisioningPolicy:
    default_autonomy_level: str = "manual"
    max_direct_create_autonomy_level: str = "manual"
    require_approval_for_high_risk_capabilities: bool = True
    require_approval_for_critical_capabilities: bool = True
    sensitive_capabilities: list[str] = field(
        default_factory=lambda: [
            "filesystem.write",
            "scheduler.run",
            "approval.review",
        ]
    )
    sensitive_tools: list[str] = field(
        default_factory=lambda: ["write_file", "delete_file", "camera_control"]
    )
    blocked_capabilities: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    require_forbidden_tools_for_sensitive_agents: bool = True
    allow_direct_create: bool = True
    allow_direct_update: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgentProvisioningRiskDecision:
    allowed: bool
    requires_approval: bool
    risk_level: str
    reasons: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    sensitive_capabilities_detected: list[str] = field(default_factory=list)
    sensitive_tools_detected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class AgentProvisioningPolicyRuntime:
    def __init__(self, data_dir: DataDir, capabilities: CapabilityRegistry):
        self.data_dir = data_dir
        self.capabilities = capabilities

    def load_policy(self) -> AgentProvisioningPolicy:
        raw = load_structured_file(self.data_dir.resolve("config/agent_provisioning_policy.yaml"))
        policy = raw.get("agent_provisioning", raw)
        return AgentProvisioningPolicy(
            default_autonomy_level=str(policy.get("default_autonomy_level", "manual")),
            max_direct_create_autonomy_level=str(
                policy.get("max_direct_create_autonomy_level", "manual")
            ),
            require_approval_for_high_risk_capabilities=bool(
                policy.get("require_approval_for_high_risk_capabilities", True)
            ),
            require_approval_for_critical_capabilities=bool(
                policy.get("require_approval_for_critical_capabilities", True)
            ),
            sensitive_capabilities=[str(item) for item in policy.get("sensitive_capabilities", [])]
            or AgentProvisioningPolicy().sensitive_capabilities,
            sensitive_tools=[str(item) for item in policy.get("sensitive_tools", [])]
            or AgentProvisioningPolicy().sensitive_tools,
            blocked_capabilities=[str(item) for item in policy.get("blocked_capabilities", [])],
            blocked_tools=[str(item) for item in policy.get("blocked_tools", [])],
            require_forbidden_tools_for_sensitive_agents=bool(
                policy.get("require_forbidden_tools_for_sensitive_agents", True)
            ),
            allow_direct_create=bool(policy.get("allow_direct_create", True)),
            allow_direct_update=bool(policy.get("allow_direct_update", True)),
        )

    def evaluate_create(
        self,
        *,
        capabilities_allow: list[str],
        autonomy_level: str | None,
        preferred_tools: list[str],
        forbidden_tools: list[str],
        can_delegate: bool = False,
        permissions: list[str] | None = None,
    ) -> AgentProvisioningRiskDecision:
        return self._evaluate(
            action="create",
            capabilities_allow=capabilities_allow,
            autonomy_level=autonomy_level,
            preferred_tools=preferred_tools,
            forbidden_tools=forbidden_tools,
            can_delegate=can_delegate,
            permissions=permissions or [],
        )

    def evaluate_update(
        self,
        *,
        capabilities_allow: list[str],
        autonomy_level: str | None,
        preferred_tools: list[str],
        forbidden_tools: list[str],
        preferred_tools_were_provided: bool,
        permissions: list[str] | None = None,
    ) -> AgentProvisioningRiskDecision:
        return self._evaluate(
            action="update",
            capabilities_allow=capabilities_allow,
            autonomy_level=autonomy_level,
            preferred_tools=preferred_tools,
            forbidden_tools=forbidden_tools,
            check_empty_forbidden=preferred_tools_were_provided,
            permissions=permissions or [],
        )

    def _evaluate(
        self,
        *,
        action: str,
        capabilities_allow: list[str],
        autonomy_level: str | None,
        preferred_tools: list[str],
        forbidden_tools: list[str],
        check_empty_forbidden: bool = True,
        can_delegate: bool = False,
        permissions: list[str] | None = None,
    ) -> AgentProvisioningRiskDecision:
        policy = self.load_policy()
        reasons: list[str] = []
        blocked_reasons: list[str] = []
        sensitive_capabilities: list[str] = []
        sensitive_tools: list[str] = []
        risk_level = "low"

        sensitive_permission_prefixes = (
            "admin",
            "approvals.",
            "filesystem.",
            "shell.",
            "communication.",
            "agents.create",
        )
        for permission in permissions or []:
            if permission.startswith(sensitive_permission_prefixes):
                reasons.append(f"permission {permission} is sensitive")
                risk_level = self._max_risk(risk_level, "high")

        blocked_capabilities = set(policy.blocked_capabilities)
        for capability_id in capabilities_allow:
            if capability_id in blocked_capabilities:
                blocked_reasons.append(f"capability {capability_id} is blocked")
                continue
            capability = self._capability_or_none(capability_id)
            if not capability:
                continue
            if capability_id in set(policy.sensitive_capabilities):
                sensitive_capabilities.append(capability_id)
                reasons.append(f"capability {capability_id} is sensitive")
                risk_level = self._max_risk(risk_level, "high")
            if (
                capability.risk_level == "high"
                and policy.require_approval_for_high_risk_capabilities
            ):
                sensitive_capabilities.append(capability_id)
                reasons.append(f"capability {capability_id} is high risk")
                risk_level = self._max_risk(risk_level, "high")
            if (
                capability.risk_level == "critical"
                and policy.require_approval_for_critical_capabilities
            ):
                sensitive_capabilities.append(capability_id)
                reasons.append(f"capability {capability_id} is critical risk")
                risk_level = self._max_risk(risk_level, "critical")

        blocked_tools = set(policy.blocked_tools)
        for tool_name in preferred_tools:
            if tool_name in blocked_tools:
                blocked_reasons.append(f"tool {tool_name} is blocked")
            if tool_name in set(policy.sensitive_tools):
                sensitive_tools.append(tool_name)
                reasons.append(f"tool {tool_name} is sensitive")
                risk_level = self._max_risk(risk_level, "high")

        if autonomy_level and self._autonomy_order(autonomy_level) > self._autonomy_order(
            policy.max_direct_create_autonomy_level
        ):
            reasons.append(f"autonomy_level {autonomy_level} exceeds direct create limit")
            risk_level = self._max_risk(risk_level, "high")

        if can_delegate:
            reasons.append("delegation authority requires approval")
            risk_level = self._max_risk(risk_level, "high")

        if (
            check_empty_forbidden
            and policy.require_forbidden_tools_for_sensitive_agents
            and sensitive_tools
            and not forbidden_tools
        ):
            reasons.append("sensitive preferred tools require explicit forbidden_tools")
            risk_level = self._max_risk(risk_level, "high")

        if action == "create" and not policy.allow_direct_create:
            reasons.append("direct agent creation is disabled by policy")
            risk_level = self._max_risk(risk_level, "medium")
        if action == "update" and not policy.allow_direct_update:
            reasons.append("direct agent update is disabled by policy")
            risk_level = self._max_risk(risk_level, "medium")

        return AgentProvisioningRiskDecision(
            allowed=not blocked_reasons,
            requires_approval=bool(reasons) and not blocked_reasons,
            risk_level=risk_level if reasons or blocked_reasons else "low",
            reasons=_unique(reasons),
            blocked_reasons=_unique(blocked_reasons),
            sensitive_capabilities_detected=_unique(sensitive_capabilities),
            sensitive_tools_detected=_unique(sensitive_tools),
        )

    def _capability_or_none(self, capability_id: str):
        try:
            return self.capabilities.get(capability_id)
        except Exception:
            return None

    @staticmethod
    def _max_risk(left: str, right: str) -> str:
        order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        return left if order[left] >= order[right] else right

    @staticmethod
    def _autonomy_order(value: str) -> int:
        order = {"manual": 0, "assisted": 1, "supervised": 1, "autonomous": 2}
        return order.get(value, 2)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
