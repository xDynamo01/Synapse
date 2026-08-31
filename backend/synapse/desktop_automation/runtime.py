from __future__ import annotations

import hashlib
import platform
from dataclasses import asdict, replace
from typing import Any

from synapse.core.events import EventBus
from synapse.desktop_automation.application import ApplicationRuntime
from synapse.desktop_automation.clipboard import ClipboardRuntime
from synapse.desktop_automation.errors import (
    ActionFailed,
    AutomationCancelled,
    AutomationDenied,
    VerificationFailed,
)
from synapse.desktop_automation.governance import DesktopGovernanceRuntime
from synapse.desktop_automation.input import InputRuntime
from synapse.desktop_automation.models import (
    ActionPreview,
    ActionResult,
    AutomationAction,
    AutomationPlan,
    AutomationResult,
    VerificationResult,
    VerificationSpec,
    now_iso,
)
from synapse.desktop_automation.planner import AutomationPlannerRuntime
from synapse.desktop_automation.providers.factory import platform_desktop_provider
from synapse.desktop_automation.providers.fallback import (
    OCRFallbackProvider,
    VisionFallbackProvider,
)
from synapse.desktop_automation.providers.input import platform_input_provider
from synapse.desktop_automation.risk import RiskAnalysisRuntime
from synapse.desktop_automation.screen import ScreenRuntime
from synapse.desktop_automation.ui_automation import UIAutomationRuntime
from synapse.desktop_automation.verification import VerificationRuntime
from synapse.desktop_automation.window import WindowRuntime


class DesktopRuntime:
    """Governed orchestrator. Every side effect is planned, authorized, and verified."""

    def __init__(
        self,
        data_dir: Any,
        events: EventBus,
        policies: Any,
        approvals: Any,
        audit: Any,
        vision: Any,
        perception: Any | None = None,
        insight: Any | None = None,
        provider: Any | None = None,
        input_provider: Any | None = None,
        visual_providers: list[Any] | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        self.provider = provider or platform_desktop_provider()
        self.applications = ApplicationRuntime(self.provider)
        self.windows = WindowRuntime(self.provider)
        self.screen = ScreenRuntime(vision)
        self.input = InputRuntime(input_provider or platform_input_provider(platform.system()))
        fallbacks = (
            visual_providers
            if visual_providers is not None
            else [OCRFallbackProvider(self.screen), VisionFallbackProvider(self.screen)]
        )
        self.ui_automation = UIAutomationRuntime([self.provider, *fallbacks], self.input)
        self.clipboard = ClipboardRuntime(self.provider, events)
        self.verification = VerificationRuntime(
            self.applications,
            self.windows,
            self.ui_automation,
            self.clipboard,
        )
        self.planner = AutomationPlannerRuntime(data_dir)
        self.risk = RiskAnalysisRuntime(approvals)
        self.governance = DesktopGovernanceRuntime(policies, approvals, audit, self.risk, events)
        self.perception = perception
        self.insight = insight
        self._transient: dict[str, str] = {}
        self._rollback: dict[str, list[tuple[str, Any]]] = {}

    def state(self) -> dict[str, Any]:
        return {
            "provider": self.provider.health(),
            "input": self.input.health(),
            "fallbacks": [provider.health() for provider in self.ui_automation.providers[1:]],
            "applications": len(self.applications.list()),
            "windows": len(self.windows.list()),
            "read_only_discovery": True,
        }

    def create_plan(
        self,
        actor_id: str,
        objective: str,
        actions: list[AutomationAction],
        *,
        dry_run: bool = False,
    ) -> AutomationPlan:
        safe_actions = [self._externalize(self._ensure_verification(action)) for action in actions]
        plan = self.planner.create(actor_id, objective, safe_actions, dry_run=dry_run)
        self.events.emit(
            "desktop.plan_created",
            actor_id,
            {"plan_id": plan.id, "action_count": len(plan.actions), "dry_run": dry_run},
        )
        return plan

    def preview(self, plan_id: str) -> AutomationPlan:
        plan = self.planner.get(plan_id)
        decision_by_action = {
            action.id: (risk, policy) for action, risk, policy in self.governance.evaluate(plan)
        }
        previews = []
        for action in plan.actions:
            risk, policy = decision_by_action[action.id]
            previews.append(
                ActionPreview(
                    action_id=action.id,
                    kind=action.kind,
                    target=_target_view(action),
                    risk=replace(
                        risk,
                        approval_required=(
                            risk.approval_required
                            or policy.approval_required
                            or policy.decision in {"require_approval", "require_confirmation"}
                        ),
                    ),
                    expected={
                        "verification": action.verification.kind if action.verification else None,
                        "policy_decision": policy.decision,
                    },
                    provider_order=self.ui_automation.provider_order(),
                )
            )
        return self.planner.transition(plan, "previewed", previews=previews)

    def execute(self, plan_id: str, *, approval_id: str | None = None) -> AutomationResult:
        plan = self.planner.get(plan_id)
        if plan.status == "cancelled":
            return AutomationResult(
                plan.id, "cancelled", [], error_code="desktop_automation_cancelled"
            )
        if not plan.previews:
            plan = self.preview(plan.id)
        if plan.dry_run:
            result = AutomationResult(plan.id, "dry_run", [])
            self.planner.transition(plan, "dry_run_completed")
            self.planner.save_result(plan.id, result)
            self._transient_cleanup(plan)
            return result
        try:
            authorization = self.governance.authorize(plan, approval_id or plan.approval_id)
        except AutomationDenied:
            result = AutomationResult(plan.id, "denied", [], error_code="desktop_automation_denied")
            self.planner.transition(plan, "denied")
            self.planner.save_result(plan.id, result)
            self._transient_cleanup(plan)
            return result
        if authorization and not (approval_id or plan.approval_id):
            plan = self.planner.transition(plan, "awaiting_approval", approval_id=authorization)
            result = AutomationResult(plan.id, "awaiting_approval", [], approval_id=authorization)
            self.planner.save_result(plan.id, result)
            return result
        plan = self.planner.transition(
            plan,
            "executing",
            approval_id=authorization or approval_id or plan.approval_id,
        )
        results: list[ActionResult] = []
        rollback_stack: list[tuple[str, Any]] = self._rollback.setdefault(plan.id, [])
        try:
            for index in range(plan.current_action, len(plan.actions)):
                persisted = self.planner.get(plan.id)
                if persisted.status == "cancelled":
                    raise AutomationCancelled("Automation was cancelled")
                safe_action = plan.actions[index]
                action = self._hydrate(safe_action)
                rollback = self._prepare_rollback(action)
                if rollback:
                    rollback_stack.append(rollback)
                action_result = self._execute_action(plan, action)
                results.append(action_result)
                if not action_result.verification.verified:
                    raise VerificationFailed("Mandatory action verification failed")
                plan = self.planner.transition(plan, "executing", current_action=index + 1)
            result = AutomationResult(plan.id, "completed", results, approval_id=plan.approval_id)
            self.planner.transition(plan, "completed", current_action=len(plan.actions))
            self._transient_cleanup(plan)
        except Exception as exc:
            rollback_results = self._rollback_plan(plan, rollback_stack)
            status = "cancelled" if isinstance(exc, AutomationCancelled) else "failed"
            result = AutomationResult(
                plan.id,
                status,
                results,
                rollback_results,
                plan.approval_id,
                getattr(exc, "code", type(exc).__name__),
            )
            current = self.planner.get(plan.id)
            self.planner.transition(current, status, current_action=0)
            self._rollback[plan.id] = []
        self.planner.save_result(plan.id, result)
        self.events.emit(
            "desktop.plan_completed",
            plan.actor_id,
            {"plan_id": plan.id, "status": result.status, "actions": len(result.actions)},
        )
        return result

    def cancel(self, plan_id: str) -> AutomationPlan:
        plan = self.planner.get(plan_id)
        if plan.status in {"completed", "failed", "cancelled", "denied", "dry_run_completed"}:
            return plan
        cancelled = self.planner.transition(plan, "cancelled")
        self._transient_cleanup(cancelled)
        self.events.emit("desktop.plan_cancelled", plan.actor_id, {"plan_id": plan.id})
        return cancelled

    def recover(self, plan_id: str, *, approval_id: str | None = None) -> AutomationResult:
        plan = self.planner.get(plan_id)
        if plan.status != "failed":
            raise ActionFailed("Only a failed automation can be recovered")
        recovered = self.planner.transition(plan, "previewed")
        return self.execute(recovered.id, approval_id=approval_id)

    def verify(self, spec: VerificationSpec) -> VerificationResult:
        return self.verification.verify(self._hydrate_verification(spec))

    def health(self) -> dict[str, Any]:
        provider = self.provider.health()
        return {
            "status": "healthy" if provider.get("available") else "degraded",
            "provider": provider,
            "fallback_only_input": True,
            "verification_required": True,
        }

    def is_reversible(self, plan_id: str) -> bool:
        plan = self.planner.get(plan_id)
        return bool(plan.actions) and all(
            self._rollback_available(action) for action in plan.actions
        )

    def _execute_action(self, plan: AutomationPlan, action: AutomationAction) -> ActionResult:
        started = now_iso()
        last_verification = VerificationResult(False, "unknown", None, None)
        provider_name: str | None = None
        evidence: list[dict[str, Any]] = []
        attempts = 0
        for attempt in range(1, action.max_attempts + 1):
            attempts = attempt
            try:
                provider_name, output, element = self._perform(action)
                evidence.append(
                    {
                        "provider": provider_name,
                        "performed": bool(output.get("performed")),
                        "element_id": element.element_id if element else None,
                    }
                )
                last_verification = self.verification.verify(
                    self._hydrate_verification(action.verification),
                    observed_hint=output,
                )
                if last_verification.verified:
                    result = ActionResult(
                        action.id,
                        "completed",
                        provider_name,
                        attempt,
                        last_verification,
                        evidence,
                        rollback={"available": self._rollback_available(action)},
                        started_at=started,
                        completed_at=now_iso(),
                    )
                    self.governance.audit_action(
                        plan,
                        action,
                        "completed",
                        details={"provider": provider_name, "attempts": attempt, "verified": True},
                    )
                    return result
                if not _retry_safe(action):
                    break
            except Exception as exc:
                evidence.append({"attempt": attempt, "error_type": type(exc).__name__})
                if attempt >= action.max_attempts or not _retry_safe(action):
                    break
        self.governance.audit_action(
            plan,
            action,
            "failed",
            "verification_or_provider_failed",
            {"provider": provider_name, "attempts": len(evidence)},
        )
        return ActionResult(
            action.id,
            "failed",
            provider_name,
            attempts,
            last_verification,
            evidence,
            rollback={"available": self._rollback_available(action)},
            error_code="desktop_action_unverified",
            started_at=started,
            completed_at=now_iso(),
        )

    def _perform(self, action: AutomationAction):
        if action.kind == "clipboard.set":
            output = self.clipboard.set(str(action.arguments.get("value", "")))
            return "clipboard", {"performed": True, **output}, None
        if action.kind == "clipboard.clear":
            self.clipboard.clear()
            return "clipboard", {"performed": True}, None
        if action.kind.startswith(("element.", "input.")):
            return self.ui_automation.perform(action)
        return self.provider.name, self.provider.perform(action), None

    def _prepare_rollback(self, action: AutomationAction) -> tuple[str, Any] | None:
        if action.kind.startswith("clipboard."):
            return "clipboard", self.clipboard.snapshot()
        if action.kind in {"window.minimize", "window.maximize"}:
            return "action", AutomationAction(
                "window.restore",
                window_id=action.window_id,
                verification=VerificationSpec(
                    "window.state", expected="normal", window_id=action.window_id
                ),
                max_attempts=1,
            )
        if action.kind == "element.toggle":
            return "action", replace(action, max_attempts=1)
        if action.kind == "element.expand":
            return "action", replace(action, kind="element.collapse", max_attempts=1)
        if action.kind == "element.collapse":
            return "action", replace(action, kind="element.expand", max_attempts=1)
        return None

    def _rollback_plan(
        self, plan: AutomationPlan, stack: list[tuple[str, Any]]
    ) -> list[dict[str, Any]]:
        results = []
        for kind, payload in reversed(stack):
            try:
                if kind == "clipboard":
                    completed = self.clipboard.restore(payload)
                else:
                    self._perform(self._hydrate(payload))
                    completed = True
                results.append({"kind": kind, "completed": completed})
            except Exception as exc:
                results.append({"kind": kind, "completed": False, "error_type": type(exc).__name__})
        self.events.emit(
            "desktop.rollback_completed",
            plan.actor_id,
            {"plan_id": plan.id, "results": results},
        )
        return results

    def _ensure_verification(self, action: AutomationAction) -> AutomationAction:
        if action.verification is not None:
            return action
        if action.kind == "element.set_value":
            return replace(
                action,
                verification=VerificationSpec(
                    "element.value", action.selector, action.arguments.get("value")
                ),
            )
        if action.kind == "clipboard.set":
            value = str(action.arguments.get("value", ""))
            return replace(
                action,
                verification=VerificationSpec("clipboard.digest", expected=_digest(value)),
            )
        return action

    def _externalize(self, action: AutomationAction) -> AutomationAction:
        value = action.arguments.get("value")
        arguments = dict(action.arguments)
        selector = action.selector
        verification = action.verification
        if value is not None:
            token = f"transient:{action.id}:value"
            text = str(value)
            self._transient[token] = text
            arguments = {key: item for key, item in arguments.items() if key != "value"}
            arguments.update(
                {"value_ref": token, "value_length": len(text), "digest": _digest(text)}
            )
            if verification is not None and verification.expected == value:
                verification = replace(verification, expected={"transient_ref": token})
        if selector is not None and selector.value is not None:
            token = f"transient:{action.id}:selector"
            self._transient[token] = selector.value
            arguments["selector_value_ref"] = token
            selector = replace(selector, value=None)
        if (
            verification is not None
            and verification.selector is not None
            and verification.selector.value is not None
        ):
            token = f"transient:{action.id}:verification-selector"
            self._transient[token] = verification.selector.value
            arguments["verification_value_ref"] = token
            verification = replace(
                verification, selector=replace(verification.selector, value=None)
            )
        if (
            verification is not None
            and verification.kind == "element.value"
            and isinstance(verification.expected, str)
        ):
            token = f"transient:{action.id}:verification"
            self._transient[token] = verification.expected
            verification = replace(verification, expected={"transient_ref": token})
        return replace(action, selector=selector, arguments=arguments, verification=verification)

    def _hydrate(self, action: AutomationAction) -> AutomationAction:
        token = action.arguments.get("value_ref")
        arguments = dict(action.arguments)
        if token:
            if token not in self._transient:
                raise ActionFailed("Transient action payload is unavailable after restart")
            arguments["value"] = self._transient[token]
        selector = action.selector
        selector_token = action.arguments.get("selector_value_ref")
        if selector is not None and selector_token:
            if selector_token not in self._transient:
                raise ActionFailed("Transient selector payload is unavailable after restart")
            selector = replace(selector, value=self._transient[selector_token])
        verification = self._hydrate_verification(action.verification)
        verification_token = action.arguments.get("verification_value_ref")
        if verification.selector is not None and verification_token:
            if verification_token not in self._transient:
                raise ActionFailed("Transient verification selector is unavailable after restart")
            verification = replace(
                verification,
                selector=replace(verification.selector, value=self._transient[verification_token]),
            )
        return replace(
            action,
            selector=selector,
            arguments=arguments,
            verification=verification,
        )

    def _hydrate_verification(self, spec: VerificationSpec | None) -> VerificationSpec:
        if spec is None:
            raise VerificationFailed("Action has no verification")
        expected = spec.expected
        if isinstance(expected, dict) and expected.get("transient_ref"):
            token = expected["transient_ref"]
            if token not in self._transient:
                raise VerificationFailed("Transient verification payload is unavailable")
            return replace(spec, expected=self._transient[token])
        return spec

    def _transient_cleanup(self, plan: AutomationPlan) -> None:
        for action in plan.actions:
            for key in ("value_ref", "selector_value_ref", "verification_value_ref"):
                token = action.arguments.get(key)
                if token:
                    self._transient.pop(str(token), None)
            if action.verification and isinstance(action.verification.expected, dict):
                token = action.verification.expected.get("transient_ref")
                if token:
                    self._transient.pop(str(token), None)
        self._rollback.pop(plan.id, None)

    @staticmethod
    def _rollback_available(action: AutomationAction) -> bool:
        return action.kind.startswith("clipboard.") or action.kind in {
            "window.minimize",
            "window.maximize",
            "element.toggle",
            "element.expand",
            "element.collapse",
        }


def _retry_safe(action: AutomationAction) -> bool:
    return action.kind in {
        "window.focus",
        "window.minimize",
        "window.restore",
        "window.maximize",
        "element.focus",
        "element.set_value",
        "input.click",
        "input.type",
        "clipboard.set",
        "clipboard.clear",
    }


def _target_view(action: AutomationAction) -> dict[str, Any]:
    return {
        "application": action.application,
        "window_id": action.window_id,
        "selector": asdict(action.selector) if action.selector else None,
        "fallback_allowed": action.fallback_allowed,
    }


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
