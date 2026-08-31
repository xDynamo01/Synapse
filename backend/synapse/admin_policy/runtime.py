from __future__ import annotations

from synapse.admin_policy.models import ADMIN_ACTIONS, AdminDecision, AdminPolicy
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.core.serialization import load_structured_file


class AdminPolicyRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        permissions: PermissionManager,
        event_bus: EventBus | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.permissions = permissions
        self.event_bus = event_bus

    def load_policy(self) -> AdminPolicy:
        raw = load_structured_file(self.data_dir.resolve("config/admin_policy.yaml"))
        policy_raw = raw.get("admin_policy", raw)
        if not isinstance(policy_raw, dict):
            policy_raw = {}
        return AdminPolicy(
            allow_user_admin_actions=bool(policy_raw.get("allow_user_admin_actions", True)),
            require_approval_for_archive=bool(
                policy_raw.get("require_approval_for_archive", False)
            ),
            require_approval_for_deactivate=bool(
                policy_raw.get("require_approval_for_deactivate", False)
            ),
            require_approval_for_restore=bool(
                policy_raw.get("require_approval_for_restore", False)
            ),
            protected_agents=[str(item).lower() for item in policy_raw.get("protected_agents", [])],
            blocked_admin_actions=[
                str(item) for item in policy_raw.get("blocked_admin_actions", [])
            ],
            admin_capabilities_required={
                str(key): str(value)
                for key, value in policy_raw.get("admin_capabilities_required", {}).items()
            },
        )

    def check(
        self,
        context: PermissionContext | None,
        action: str,
        agent_id: str,
    ) -> AdminDecision:
        policy = self.load_policy()
        normalized_agent_id = agent_id.lower()
        reasons: list[str] = []
        blocked_reasons: list[str] = []
        requires_approval = False
        required_permission = policy.admin_capabilities_required.get(action)

        if action not in ADMIN_ACTIONS:
            blocked_reasons.append(f"unknown admin action: {action}")

        if action in policy.blocked_admin_actions:
            blocked_reasons.append(f"admin action is blocked by policy: {action}")

        if context and context.actor_type == "user" and not policy.allow_user_admin_actions:
            blocked_reasons.append("user admin actions are disabled by policy")

        if required_permission and context:
            permission_decision = self.permissions.is_allowed(context, required_permission)
            if permission_decision.allowed:
                reasons.append(f"permission granted: {required_permission}")
            else:
                blocked_reasons.append(
                    f"{context.actor_type}:{context.actor_id} lacks permission {required_permission}"
                )
        elif required_permission and context is None:
            blocked_reasons.append(f"admin action requires permission {required_permission}")

        if normalized_agent_id in policy.protected_agents:
            if action == "agent.archive" and policy.require_approval_for_archive:
                requires_approval = True
                reasons.append("protected agent archive requires approval")
            elif action == "agent.deactivate" and policy.require_approval_for_deactivate:
                requires_approval = True
                reasons.append("protected agent deactivate requires approval")
            elif action == "agent.restore" and policy.require_approval_for_restore:
                requires_approval = True
                reasons.append("protected agent restore requires approval")
            elif action in {"agent.archive", "agent.deactivate"}:
                blocked_reasons.append(f"protected agent cannot run {action} without approval")

        if action == "agent.archive" and policy.require_approval_for_archive:
            requires_approval = True
            reasons.append("archive requires approval")
        if action == "agent.deactivate" and policy.require_approval_for_deactivate:
            requires_approval = True
            reasons.append("deactivate requires approval")
        if action == "agent.restore" and policy.require_approval_for_restore:
            requires_approval = True
            reasons.append("restore requires approval")

        decision = AdminDecision(
            action=action,
            agent_id=normalized_agent_id,
            allowed=not blocked_reasons and not requires_approval,
            requires_approval=requires_approval and not blocked_reasons,
            reasons=reasons,
            blocked_reasons=blocked_reasons,
            required_permission=required_permission,
        )
        if self.event_bus:
            self.event_bus.emit("admin.policy.checked", normalized_agent_id, decision.to_dict())
        return decision

    def current_policy(self) -> dict:
        return self.load_policy().to_dict()
