from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.agents.identity import AgentIdentity
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.serialization import load_structured_file
from synapse.delegation.models import DelegationTask
from synapse.policies.effective import AgentEffectivePolicy

DEFAULT_DELEGATION_AUTONOMY_POLICY: dict[str, Any] = {
    "enabled": True,
    "allow_auto_accept": False,
    "allow_auto_start": True,
    "allow_auto_reject": False,
    "max_auto_priority": "high",
    "require_approval_for_critical": True,
    "allowed_requester_agents": [],
    "blocked_requester_agents": [],
    "require_capability_match": False,
    "require_due_at_for_auto_accept": False,
    "manual_autonomy_blocks_auto_accept": True,
    "conservative_default": True,
}

PRIORITY_RANK = {"low": 1, "normal": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class DelegationAutonomyPolicy:
    enabled: bool = True
    allow_auto_accept: bool = False
    allow_auto_start: bool = True
    allow_auto_reject: bool = False
    max_auto_priority: str = "high"
    require_approval_for_critical: bool = True
    allowed_requester_agents: list[str] = field(default_factory=list)
    blocked_requester_agents: list[str] = field(default_factory=list)
    require_capability_match: bool = False
    require_due_at_for_auto_accept: bool = False
    manual_autonomy_blocks_auto_accept: bool = True
    conservative_default: bool = True


@dataclass(frozen=True)
class DelegationAutonomyDecision:
    allowed: bool
    requires_approval: bool
    blocked: bool
    action: str
    reasons: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    risk_level: str = "low"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DelegationAutonomyPolicyRuntime:
    def __init__(self, data_dir: DataDir, events: EventBus):
        self.data_dir = data_dir
        self.events = events

    def load_policy(self) -> DelegationAutonomyPolicy:
        raw = load_structured_file(self.data_dir.resolve("config/delegation_autonomy_policy.yaml"))
        policy_raw = raw.get("delegation_autonomy", raw)
        merged = dict(DEFAULT_DELEGATION_AUTONOMY_POLICY)
        merged.update(policy_raw)
        merged["allowed_requester_agents"] = [
            str(item).lower() for item in merged.get("allowed_requester_agents", [])
        ]
        merged["blocked_requester_agents"] = [
            str(item).lower() for item in merged.get("blocked_requester_agents", [])
        ]
        return DelegationAutonomyPolicy(**merged)

    def evaluate_accept(
        self,
        task: DelegationTask,
        assignee_identity: AgentIdentity,
        effective_policy: AgentEffectivePolicy,
    ) -> DelegationAutonomyDecision:
        return self._evaluate("accept", task, assignee_identity, effective_policy)

    def evaluate_start(
        self,
        task: DelegationTask,
        assignee_identity: AgentIdentity,
        effective_policy: AgentEffectivePolicy,
    ) -> DelegationAutonomyDecision:
        return self._evaluate("start", task, assignee_identity, effective_policy)

    def evaluate_reject(
        self,
        task: DelegationTask,
        assignee_identity: AgentIdentity,
        effective_policy: AgentEffectivePolicy,
    ) -> DelegationAutonomyDecision:
        return self._evaluate("reject", task, assignee_identity, effective_policy)

    def explain_decision(
        self,
        task_id: str,
        action: str,
        task: DelegationTask,
        assignee_identity: AgentIdentity,
        effective_policy: AgentEffectivePolicy,
    ) -> DelegationAutonomyDecision:
        if task_id != task.task_id:
            return DelegationAutonomyDecision(
                allowed=False,
                requires_approval=False,
                blocked=True,
                action=action,
                blocked_reasons=["task_id does not match task"],
                metadata={"task_id": task_id, "actual_task_id": task.task_id},
            )
        return self._evaluate(action, task, assignee_identity, effective_policy)

    def _evaluate(
        self,
        action: str,
        task: DelegationTask,
        assignee_identity: AgentIdentity,
        effective_policy: AgentEffectivePolicy,
    ) -> DelegationAutonomyDecision:
        policy = self.load_policy()
        reasons: list[str] = []
        blocked_reasons: list[str] = []
        risk_level = task.priority if task.priority in PRIORITY_RANK else "low"
        metadata = {
            "task_id": task.task_id,
            "assignee_agent_id": task.assignee_agent_id,
            "requester_agent_id": task.requester_agent_id,
            "autonomy_profile": effective_policy.autonomy_profile,
            "identity_autonomy_profile": assignee_identity.autonomy_profile,
            "policy_enabled": policy.enabled,
        }

        if not policy.enabled:
            decision = DelegationAutonomyDecision(
                allowed=True,
                requires_approval=False,
                blocked=False,
                action=action,
                reasons=["policy disabled; fallback allowed"],
                risk_level=risk_level,
                metadata=metadata,
            )
            self._emit(task, decision)
            return decision

        if task.requester_agent_id in set(policy.blocked_requester_agents):
            blocked_reasons.append(f"blocked requester agent: {task.requester_agent_id}")
        if policy.allowed_requester_agents and task.requester_agent_id not in set(
            policy.allowed_requester_agents
        ):
            blocked_reasons.append(f"requester agent not allowed: {task.requester_agent_id}")

        if action == "accept":
            self._evaluate_accept(policy, task, effective_policy, blocked_reasons, reasons)
        elif action == "start":
            self._evaluate_start(policy, blocked_reasons, reasons)
        elif action == "reject":
            self._evaluate_reject(policy, blocked_reasons, reasons)
        else:
            blocked_reasons.append(f"unsupported delegation autonomy action: {action}")

        if policy.require_capability_match:
            required = str(task.metadata.get("required_capability", "")).strip()
            if required and required not in set(effective_policy.allowed_capabilities):
                blocked_reasons.append(f"missing required capability: {required}")
            elif required:
                reasons.append(f"required capability allowed: {required}")

        priority_rank = PRIORITY_RANK.get(task.priority, 0)
        max_rank = PRIORITY_RANK.get(policy.max_auto_priority, 0)
        requires_approval = False
        if (
            not blocked_reasons
            and task.priority == "critical"
            and policy.require_approval_for_critical
        ):
            requires_approval = True
            reasons.append("critical delegation requires approval")
        elif not blocked_reasons and max_rank and priority_rank > max_rank:
            blocked_reasons.append(
                f"priority {task.priority} exceeds max auto priority {policy.max_auto_priority}"
            )

        allowed = not blocked_reasons and not requires_approval
        decision = DelegationAutonomyDecision(
            allowed=allowed,
            requires_approval=requires_approval,
            blocked=bool(blocked_reasons),
            action=action,
            reasons=reasons or (["delegation autonomy allowed"] if allowed else []),
            blocked_reasons=blocked_reasons,
            risk_level=risk_level,
            metadata=metadata,
        )
        self._emit(task, decision)
        return decision

    @staticmethod
    def _evaluate_accept(
        policy: DelegationAutonomyPolicy,
        task: DelegationTask,
        effective_policy: AgentEffectivePolicy,
        blocked_reasons: list[str],
        reasons: list[str],
    ) -> None:
        if not policy.allow_auto_accept:
            blocked_reasons.append("auto accept is disabled")
        if (
            policy.manual_autonomy_blocks_auto_accept
            and effective_policy.autonomy_profile == "manual"
        ):
            blocked_reasons.append("manual autonomy blocks auto accept")
        if policy.require_due_at_for_auto_accept and not task.due_at:
            blocked_reasons.append("due_at is required for auto accept")
        if not blocked_reasons:
            reasons.append("auto accept allowed by policy")

    @staticmethod
    def _evaluate_start(
        policy: DelegationAutonomyPolicy,
        blocked_reasons: list[str],
        reasons: list[str],
    ) -> None:
        if not policy.allow_auto_start:
            blocked_reasons.append("auto start is disabled")
        if not blocked_reasons:
            reasons.append("auto start allowed by policy")

    @staticmethod
    def _evaluate_reject(
        policy: DelegationAutonomyPolicy,
        blocked_reasons: list[str],
        reasons: list[str],
    ) -> None:
        if not policy.allow_auto_reject:
            blocked_reasons.append("auto reject is disabled")
        if not blocked_reasons:
            reasons.append("auto reject allowed by policy")

    def _emit(self, task: DelegationTask, decision: DelegationAutonomyDecision) -> None:
        payload = {"task": {"task_id": task.task_id}, "decision": decision.to_dict()}
        self.events.emit("delegation.autonomy.evaluated", task.assignee_agent_id, payload)
        if decision.allowed:
            self.events.emit("delegation.autonomy.allowed", task.assignee_agent_id, payload)
        elif decision.requires_approval:
            self.events.emit(
                "delegation.autonomy.requires_approval",
                task.assignee_agent_id,
                payload,
            )
        elif decision.blocked:
            self.events.emit("delegation.autonomy.blocked", task.assignee_agent_id, payload)
