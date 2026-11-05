from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from typing import Any, Protocol

from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.registry import AgentRegistry
from synapse.approvals.manager import RISK_LEVELS, ApprovalManager
from synapse.auth.devices import DeviceRegistry
from synapse.capabilities.registry import CapabilityRegistry
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.policies.models import (
    AUTONOMY_LEVELS,
    POLICY_EFFECTS,
    POLICY_SCOPES,
    EffectivePolicy,
    PolicyRule,
)
from synapse.tools.base import ToolSpec


class ToolSpecRegistry(Protocol):
    def list_specs(self) -> list[ToolSpec]: ...


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
    allowed_capabilities: list[str] = field(default_factory=list)
    denied_capabilities: list[str] = field(default_factory=list)
    capability_decisions: dict[str, dict[str, Any]] = field(default_factory=dict)

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
        tools: ToolSpecRegistry,
        permissions: PermissionManager,
        approvals: ApprovalManager,
        devices: DeviceRegistry,
        capabilities: CapabilityRegistry | None = None,
    ):
        self.agents = agents
        self.identities = identities
        self.tools = tools
        self.permissions = permissions
        self.approvals = approvals
        self.devices = devices
        self.capabilities = capabilities
        self.rules_root = agents.data_dir.resolve("policies/rules")
        self.history_root = agents.data_dir.resolve("policies/history")
        self.rules_root.mkdir(parents=True, exist_ok=True)
        self.history_root.mkdir(parents=True, exist_ok=True)

    def list_rules(self, scope: str | None = None, subject: str | None = None) -> list[PolicyRule]:
        rules = [self._read_rule(path) for path in sorted(self.rules_root.glob("*.yaml"))]
        if scope:
            rules = [rule for rule in rules if rule.scope == scope]
        if subject:
            rules = [rule for rule in rules if rule.subject == subject]
        return rules

    def get_rule(self, rule_id: str) -> PolicyRule:
        path = self.rules_root / f"{rule_id}.yaml"
        if not path.exists():
            raise NotFound(f"policy_not_found: {rule_id}")
        return self._read_rule(path)

    def create_rule(self, rule: PolicyRule) -> PolicyRule:
        self.validate_rule(rule)
        path = self.rules_root / f"{rule.id}.yaml"
        if path.exists():
            raise ValidationError(f"policy_conflict: {rule.id}")
        dump_structured_file(path, asdict(rule))
        self._write_history(rule, "created")
        return rule

    def update_rule(
        self, rule_id: str, updates: dict[str, Any], expected_revision: int
    ) -> PolicyRule:
        current = self.get_rule(rule_id)
        if current.revision != expected_revision:
            raise ValidationError("policy_conflict: revision mismatch")
        immutable = {"id", "created_at", "revision"}
        values = {key: value for key, value in updates.items() if key not in immutable}
        updated = replace(
            current,
            **values,
            revision=current.revision + 1,
            updated_at=datetime.now(UTC).isoformat(),
        )
        self.validate_rule(updated)
        dump_structured_file(self.rules_root / f"{rule_id}.yaml", asdict(updated))
        self._write_history(updated, "updated")
        return updated

    def delete_rule(self, rule_id: str, expected_revision: int | None = None) -> PolicyRule:
        current = self.get_rule(rule_id)
        if expected_revision is not None and current.revision != expected_revision:
            raise ValidationError("policy_conflict: revision mismatch")
        (self.rules_root / f"{rule_id}.yaml").unlink()
        self._write_history(current, "deleted")
        return current

    def validate_rule(self, rule: PolicyRule) -> None:
        if rule.scope not in POLICY_SCOPES:
            raise ValidationError(f"policy_invalid: invalid scope {rule.scope}")
        if rule.effect not in POLICY_EFFECTS:
            raise ValidationError(f"policy_invalid: invalid effect {rule.effect}")
        if not all(
            (rule.subject.strip(), rule.action.strip(), rule.resource.strip(), rule.source.strip())
        ):
            raise ValidationError(
                "policy_invalid: subject, action, resource and source are required"
            )
        if rule.expires_at:
            try:
                datetime.fromisoformat(rule.expires_at)
            except ValueError as exc:
                raise ValidationError("policy_invalid: expires_at must be ISO-8601") from exc

    def evaluate_policy(
        self,
        subject: str,
        action: str,
        resource: str,
        context: dict[str, Any] | None = None,
    ) -> EffectivePolicy:
        context = context or {}
        matched = [
            rule
            for rule in self.list_rules()
            if not self._expired(rule)
            and rule.subject in {subject, "*"}
            and fnmatchcase(action, rule.action)
            and fnmatchcase(resource, rule.resource)
            and self._conditions_match(rule.conditions, context)
        ]
        scope_rank = {
            name: index
            for index, name in enumerate(
                (
                    "system",
                    "user",
                    "agent",
                    "conversation",
                    "mission",
                    "task",
                    "tool",
                    "model",
                    "voice",
                    "perception",
                )
            )
        }
        effect_rank = {
            "deny": 0,
            "require_approval": 1,
            "require_confirmation": 2,
            "constrain": 3,
            "allow": 4,
            "audit_only": 5,
        }
        matched.sort(
            key=lambda item: (
                effect_rank[item.effect],
                scope_rank[item.scope],
                item.priority,
                item.id,
            )
        )
        winner = matched[0] if matched else None
        decision = winner.effect if winner else "deny"
        constraints: dict[str, Any] = {}
        for rule in matched:
            if rule.effect == "constrain":
                constraints.update(
                    rule.conditions.get("constraints", rule.metadata.get("constraints", {}))
                )
        reasons = [f"matched:{rule.id}:{rule.effect}" for rule in matched]
        if not matched:
            reasons.append("default_deny")
        requested_autonomy = context.get("autonomy_level")
        autonomy_ceiling = constraints.get("autonomy_ceiling")
        if requested_autonomy and autonomy_ceiling:
            try:
                exceeds = AUTONOMY_LEVELS.index(requested_autonomy) > AUTONOMY_LEVELS.index(
                    autonomy_ceiling
                )
            except ValueError:
                exceeds = True
            if exceeds:
                decision = (
                    "require_approval"
                    if any(rule.effect == "require_approval" for rule in matched)
                    else "deny"
                )
                reasons.append("autonomy_ceiling_exceeded")
        return EffectivePolicy(
            subject=subject,
            action=action,
            resource=resource,
            decision=decision,
            matched_rules=[asdict(rule) for rule in matched],
            winning_rule=asdict(winner) if winner else None,
            constraints=constraints,
            approval_required=decision == "require_approval",
            reasons=reasons,
            warnings=[],
        )

    def explain_policy(
        self, subject: str, action: str, resource: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return asdict(self.evaluate_policy(subject, action, resource, context))

    def rule_history(self, rule_id: str) -> list[dict[str, Any]]:
        return [
            load_structured_file(path)
            for path in sorted(self.history_root.glob(f"{rule_id}-*.yaml"))
        ]

    @staticmethod
    def _expired(rule: PolicyRule) -> bool:
        return bool(
            rule.expires_at and datetime.fromisoformat(rule.expires_at) <= datetime.now(UTC)
        )

    @staticmethod
    def _conditions_match(conditions: dict[str, Any], context: dict[str, Any]) -> bool:
        required = conditions.get("when", {})
        return not required or all(context.get(key) == value for key, value in required.items())

    def _read_rule(self, path) -> PolicyRule:
        return PolicyRule(**load_structured_file(path))

    def _write_history(self, rule: PolicyRule, operation: str) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        dump_structured_file(
            self.history_root / f"{rule.id}-{stamp}.yaml",
            {
                "operation": operation,
                "rule": asdict(rule),
                "recorded_at": datetime.now(UTC).isoformat(),
            },
        )

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
        if self.capabilities:
            for capability in self.capabilities.list_capabilities():
                known_permissions.update(capability.required_permissions)
        agent_context = PermissionContext(
            actor_id=agent_id,
            actor_type="agent",
            device_id=context.device_id,
            autonomy=identity.autonomy_profile,
        )

        global_permissions = self.permissions.permissions_for(agent_context)
        global_denies = self.permissions.denied_permissions_for(agent_context)
        config_permissions = set(agent.permissions)
        # The configured primary agent is the Synapse control plane entry point.
        # It must be able to see and invoke the registered Synapse capabilities;
        # explicit denies, tool forbids and approval policy still apply below.
        if agent.role.strip().lower() == "primary_agent":
            config_permissions = {"*"}
        allowed_permissions = self._bounded_permissions(
            config_permissions=config_permissions,
            global_permissions=global_permissions,
            known_permissions=known_permissions | ({"tools.execute"} if agent.role.strip().lower() == "primary_agent" else set()),
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
        capability_decisions = self._capability_decisions(
            agent_id=agent_id,
            raw_config=raw_config,
            allowed_permissions=allowed_permissions,
            forbidden_tools=forbidden_tools,
        )
        allowed_capabilities = [
            capability_id
            for capability_id, decision in capability_decisions.items()
            if decision["allowed"]
        ]
        denied_capabilities = [
            capability_id
            for capability_id, decision in capability_decisions.items()
            if not decision["allowed"]
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
            allowed_capabilities=sorted(allowed_capabilities),
            denied_capabilities=sorted(denied_capabilities),
            capability_decisions=capability_decisions,
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

    def _capability_decisions(
        self,
        agent_id: str,
        raw_config: dict[str, Any],
        allowed_permissions: set[str],
        forbidden_tools: set[str],
    ) -> dict[str, dict[str, Any]]:
        if not self.capabilities:
            return {}
        agent_allow, agent_deny = self._capability_config(raw_config.get("capabilities", {}))
        global_allow, global_deny = self._global_capability_config()
        decisions: dict[str, dict[str, Any]] = {}
        for capability in self.capabilities.list_capabilities():
            capability_id = capability.capability_id
            required_permissions = set(capability.required_permissions)
            tools = set(capability.metadata.get("tools", []))
            if not capability.enabled:
                decisions[capability_id] = {"allowed": False, "reason": "capability_disabled"}
            elif capability_id in global_deny:
                decisions[capability_id] = {"allowed": False, "reason": "global_deny"}
            elif capability_id in agent_deny:
                decisions[capability_id] = {"allowed": False, "reason": "agent_deny"}
            elif tools.intersection(forbidden_tools):
                decisions[capability_id] = {"allowed": False, "reason": "tool_forbidden"}
            elif global_allow and capability_id not in global_allow:
                decisions[capability_id] = {"allowed": False, "reason": "global_not_allowed"}
            elif required_permissions and not required_permissions.issubset(allowed_permissions):
                decisions[capability_id] = {
                    "allowed": False,
                    "reason": "missing_required_permission",
                }
            elif capability_id in agent_allow:
                decisions[capability_id] = {"allowed": True, "reason": "agent_allow"}
            elif required_permissions:
                decisions[capability_id] = {"allowed": True, "reason": "permission_fallback"}
            else:
                decisions[capability_id] = {"allowed": False, "reason": "not_configured"}
            decisions[capability_id]["required_permissions"] = sorted(required_permissions)
        return decisions

    def _global_capability_config(self) -> tuple[set[str], set[str]]:
        raw = load_structured_file(self.agents.data_dir.resolve("config/capabilities.yaml"))
        capabilities = raw.get("capabilities", raw)
        return self._capability_config(capabilities)

    @staticmethod
    def _capability_config(raw: Any) -> tuple[set[str], set[str]]:
        if not isinstance(raw, dict):
            return set(), set()
        return (
            EffectivePolicyRuntime._capability_list(raw.get("allow", [])),
            EffectivePolicyRuntime._capability_list(raw.get("deny", [])),
        )

    @staticmethod
    def _capability_list(value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            return {value}
        if isinstance(value, list):
            return {str(item) for item in value}
        return {str(value)}

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
