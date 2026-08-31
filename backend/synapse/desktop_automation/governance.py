from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.core.permissions import PermissionContext
from synapse.desktop_automation.errors import AutomationDenied
from synapse.desktop_automation.models import AutomationAction, AutomationPlan, RiskAssessment
from synapse.observability.redaction import redact


class DesktopGovernanceRuntime:
    def __init__(self, policies: Any, approvals: Any, audit: Any, risk: Any, events: Any) -> None:
        self.policies = policies
        self.approvals = approvals
        self.audit = audit
        self.risk = risk
        self.events = events

    def evaluate(self, plan: AutomationPlan) -> list[tuple[AutomationAction, RiskAssessment, Any]]:
        decisions = []
        for action in plan.actions:
            risk = self.risk.assess(action, plan.actor_id)
            policy = self.policies.evaluate_policy(
                plan.actor_id,
                "desktop.automation.execute",
                f"desktop:{action.kind}",
                {"risk": risk.level, "plan_id": plan.id, "dry_run": plan.dry_run},
            )
            decisions.append((action, risk, policy))
        return decisions

    def authorize(self, plan: AutomationPlan, approval_id: str | None = None) -> str | None:
        decisions = self.evaluate(plan)
        for action, risk, policy in decisions:
            if risk.prohibited:
                self.audit_action(plan, action, "blocked", risk.reasons[-1])
                raise AutomationDenied("Sensitive authentication input is never automated")
            if policy.decision == "deny":
                self.audit_action(plan, action, "blocked", "policy_denied")
                raise AutomationDenied("Existing PolicyRuntime denied desktop automation")
        needs_approval = any(
            risk.approval_required
            or policy.approval_required
            or policy.decision in {"require_approval", "require_confirmation"}
            for _action, risk, policy in decisions
        )
        if not needs_approval:
            return None
        if approval_id:
            approval = self.approvals.get_status(approval_id)
            if approval.status != "approved":
                raise AutomationDenied(f"Approval is not approved: {approval.status}")
            return approval.id
        highest = max(
            (risk.level for _action, risk, _policy in decisions),
            key=lambda value: {"low": 0, "medium": 1, "high": 2, "critical": 3}[value],
        )
        request = self.approvals.create_request(
            PermissionContext(actor_id=plan.actor_id, actor_type="agent"),
            tool_name="desktop_automation",
            tool_args={
                "plan_id": plan.id,
                "action_kinds": [action.kind for action in plan.actions],
                "action_count": len(plan.actions),
            },
            risk_level=highest,
            reason="Desktop automation requires governed approval.",
            tool_call_id=plan.id,
        )
        return request.id

    def audit_action(
        self,
        plan: AutomationPlan,
        action: AutomationAction,
        status: str,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        safe = redact(details or {})
        self.audit.append_record(
            plan.actor_id,
            f"desktop:{action.kind}",
            status="success" if status == "completed" else status,
            actor_agent_id=plan.actor_id,
            actor_type="agent",
            reason=reason,
            details={"plan_id": plan.id, "action_id": action.id, **safe},
        )
        self.events.emit(
            f"desktop.action_{status}",
            plan.actor_id,
            {"plan_id": plan.id, "action_id": action.id, "kind": action.kind, **safe},
        )

    def decision_view(self, plan: AutomationPlan) -> list[dict[str, Any]]:
        return [
            {"action_id": action.id, "risk": asdict(risk), "policy": asdict(policy)}
            for action, risk, policy in self.evaluate(plan)
        ]
