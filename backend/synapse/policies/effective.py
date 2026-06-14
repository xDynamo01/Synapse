from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.registry import AgentRegistry
from synapse.approvals.manager import RISK_LEVELS, ApprovalManager
from synapse.auth.devices import DeviceRegistry
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.core.serialization import load_structured_file
from synapse.tools.base import ToolRegistry, ToolSpec


@dataclass(frozen=True)
class AgentEffectivePolicy:
    agent_id: str
    allowed_tools: list[str]
    forbidden_tools: list[str]
    preferred_tools: list[str]
    autonomy_profile: str
    approval_required_for: list[str]
    can_delegate: bool
    default_model: str | None
    risk_overrides: dict[str, str] = field(default_factory=dict)
    device_constraints: dict[str, Any] | None = None
    allowed_permissions: list[str] = field(default_factory=list)
    denied_permissions: list[str] = field(default_factory=list)
    allowed_tool_specs: list[dict[str, Any]] = field(default_factory=list)

    def allows_tool(self, tool_name: str) -> bool:
        return tool_name in set(self.allowed_tools) and tool_name not in set(self.forbidden_tools)

    def risk_level_for(self, tool_name: str, default: str) -> str:
        return self.risk_overrides.get(tool_name, default)

    def requires_approval_for(self, risk_level: str) -> bool:
        return risk_level in set(self.approval_required_for)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EffectivePolicyRuntime:
    def __init__(
        self,
        agents: AgentRegistry,
        identities: AgentIdentityRuntime,
        tools: ToolRegistry,
        permissions: PermissionManager,
        approvals: ApprovalManager,
        devices: DeviceRegistry,
    ):
        self.agents = agents
        self.identities = identities
        self.tools = tools
        self.permissions = permissions
        self.approvals = approvals
        self.devices = devices

    def resolve(
        self,
        context: PermissionContext,
        agent_id: str,
    ) -> AgentEffectivePolicy:
        agent = self.agents.get(agent_id)
        identity = self.identities.load_identity(agent_id)
        raw_config = self._raw_agent_config(agent_id)
        specs = self.tools.list_specs()
        known_permissions = {spec.permission for spec in specs}
        agent_context = PermissionContext(
            actor_id=agent_id,
            actor_type="agent",
            device_id=context.device_id,
            autonomy=identity.autonomy_profile,
        )

        global_permissions = self.permissions.permissions_for(agent_context)
        global_denies = self.permissions.denied_permissions_for(agent_context)
        config_permissions = set(agent.permissions)
        allowed_permissions = self._bounded_permissions(
            config_permissions=config_permissions,
            global_permissions=global_permissions,
            known_permissions=known_permissions,
        )
        denied_permissions = self._expand_permissions(global_denies, known_permissions)
        allowed_permissions -= denied_permissions

        device_constraints = self._device_constraints(context.device_id, known_permissions)
        if device_constraints and device_constraints["applied"]:
            allowed_permissions &= set(device_constraints["allowed_permissions"])

        forbidden_tools = self._explicit_forbidden_tools(identity.forbidden_tools, raw_config)
        risk_overrides = self._risk_overrides(raw_config)
        allowed_tool_specs = self._allowed_tool_specs(
            specs=specs,
            allowed_permissions=allowed_permissions,
            forbidden_tools=forbidden_tools,
            risk_overrides=risk_overrides,
        )
        allowed_tools = [tool["name"] for tool in allowed_tool_specs]
        approval_required_for = [
            risk_level
            for risk_level in sorted(RISK_LEVELS, key=self._risk_order)
            if self.approvals.requires_approval(
                agent_id=agent_id,
                risk_level=risk_level,
                permission_explicitly_granted=True,
            )
        ]

        return AgentEffectivePolicy(
            agent_id=agent_id,
            allowed_tools=allowed_tools,
            forbidden_tools=sorted(forbidden_tools),
            preferred_tools=identity.preferred_tools,
            autonomy_profile=identity.autonomy_profile,
            approval_required_for=approval_required_for,
            can_delegate=identity.can_delegate,
            default_model=identity.default_model or agent.preferred_model,
            risk_overrides=risk_overrides,
            device_constraints=device_constraints,
            allowed_permissions=sorted(allowed_permissions),
            denied_permissions=sorted(denied_permissions),
            allowed_tool_specs=allowed_tool_specs,
        )

    def _raw_agent_config(self, agent_id: str) -> dict[str, Any]:
        return load_structured_file(self.agents.data_dir.resolve(f"agents/{agent_id}/CONFIG.yaml"))

    def _bounded_permissions(
        self,
        config_permissions: set[str],
        global_permissions: set[str],
        known_permissions: set[str],
    ) -> set[str]:
        global_ceiling = (
            set(known_permissions)
            if "*" in global_permissions
            else set(global_permissions).intersection(known_permissions)
        )
        if "*" in config_permissions:
            return global_ceiling
        return set(config_permissions).intersection(global_ceiling)

    def _expand_permissions(self, permissions: set[str], known_permissions: set[str]) -> set[str]:
        if "*" in permissions:
            return set(known_permissions)
        return set(permissions).intersection(known_permissions)

    def _device_constraints(
        self,
        device_id: str | None,
        known_permissions: set[str],
    ) -> dict[str, Any] | None:
        if not device_id:
            return None
        device = self.devices.get_device(device_id, missing_ok=True)
        if not device:
            return {
                "device_id": device_id,
                "trusted": False,
                "revoked": False,
                "permissions": [],
                "allowed_permissions": [],
                "applied": True,
                "reason": "unknown_device",
            }
        if device.revoked or not device.trusted:
            return {
                "device_id": device.device_id,
                "trusted": device.trusted,
                "revoked": device.revoked,
                "permissions": device.permissions,
                "allowed_permissions": [],
                "applied": True,
                "reason": "untrusted_or_revoked",
            }
        if "*" in device.permissions:
            return {
                "device_id": device.device_id,
                "trusted": device.trusted,
                "revoked": device.revoked,
                "permissions": device.permissions,
                "allowed_permissions": sorted(known_permissions),
                "applied": True,
                "reason": "device_permission_ceiling",
            }
        tool_permissions = set(device.permissions).intersection(known_permissions)
        return {
            "device_id": device.device_id,
            "trusted": device.trusted,
            "revoked": device.revoked,
            "permissions": device.permissions,
            "allowed_permissions": sorted(tool_permissions or known_permissions),
            "applied": bool(tool_permissions),
            "reason": "device_permission_ceiling" if tool_permissions else "no_tool_constraint",
        }

    @staticmethod
    def _explicit_forbidden_tools(
        identity_forbidden_tools: list[str],
        raw_config: dict[str, Any],
    ) -> set[str]:
        blocked = set(identity_forbidden_tools)
        for key in ("forbidden_tools", "blocked_tools", "denied_tools"):
            value = raw_config.get(key, [])
            if isinstance(value, str):
                blocked.add(value)
            elif isinstance(value, list):
                blocked.update(str(item) for item in value)
        return blocked

    @staticmethod
    def _risk_overrides(raw_config: dict[str, Any]) -> dict[str, str]:
        overrides = raw_config.get("risk_overrides", {})
        if not isinstance(overrides, dict):
            return {}
        return {str(tool_name): str(risk_level) for tool_name, risk_level in overrides.items()}

    @staticmethod
    def _allowed_tool_specs(
        specs: list[ToolSpec],
        allowed_permissions: set[str],
        forbidden_tools: set[str],
        risk_overrides: dict[str, str],
    ) -> list[dict[str, Any]]:
        allowed = []
        for spec in specs:
            if spec.name in forbidden_tools or spec.permission not in allowed_permissions:
                continue
            payload = asdict(spec)
            payload["risk_level"] = risk_overrides.get(spec.name, spec.risk_level)
            allowed.append(payload)
        return allowed

    @staticmethod
    def _risk_order(risk_level: str) -> int:
        order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        return order.get(risk_level, 99)
