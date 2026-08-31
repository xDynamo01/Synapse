from __future__ import annotations

from typing import Any

from synapse.desktop_automation.models import AutomationAction, RiskAssessment

_LEVELS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class RiskAnalysisRuntime:
    def __init__(self, approvals: Any) -> None:
        self.approvals = approvals

    def assess(self, action: AutomationAction, actor_id: str) -> RiskAssessment:
        reasons = ["external_desktop_side_effect"]
        level = "medium"
        prohibited = False
        kind = action.kind
        metadata = action.arguments
        target_type = " ".join(
            filter(
                None,
                [
                    action.selector.role if action.selector else None,
                    action.selector.control_type if action.selector else None,
                    str(metadata.get("data_class", "")),
                ],
            )
        ).casefold()
        if any(
            token in target_type
            for token in ("password", "credential", "secret", "mfa", "biometric")
        ):
            prohibited = True
            level = "critical"
            reasons.append("sensitive_authentication_input_prohibited")
        if kind in {"window.close", "application.launch", "input.hotkey"}:
            level = _higher(level, "high")
            reasons.append("lifecycle_or_global_input")
        if kind in {"element.invoke", "element.toggle", "element.select", "input.click"}:
            level = _higher(level, str(metadata.get("risk", "medium")))
        if any(
            bool(metadata.get(key)) for key in ("critical_dialog", "administrative", "destructive")
        ):
            level = "critical"
            reasons.append("critical_or_administrative_action")
        approval_required = self.approvals.requires_approval(actor_id, level, False)
        return RiskAssessment(level, reasons, approval_required, prohibited)


def _higher(left: str, right: str) -> str:
    safe_right = right if right in _LEVELS else "medium"
    return max((left, safe_right), key=lambda item: _LEVELS[item])
