from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.desktop_automation.models import (
    ActionPreview,
    AutomationAction,
    AutomationPlan,
    ElementSelector,
    RiskAssessment,
    VerificationSpec,
    now_iso,
)

ALLOWED_ACTIONS = {
    "application.launch",
    "window.focus",
    "window.minimize",
    "window.restore",
    "window.maximize",
    "window.close",
    "element.invoke",
    "element.set_value",
    "element.toggle",
    "element.select",
    "element.expand",
    "element.collapse",
    "element.focus",
    "input.click",
    "input.type",
    "input.hotkey",
    "input.scroll",
    "input.drag_drop",
    "clipboard.set",
    "clipboard.clear",
}

_COMMON_ARGUMENTS = {"risk", "critical_dialog", "administrative", "destructive", "data_class"}
_ARGUMENTS_BY_ACTION = {
    "element.set_value": {"value"},
    "input.type": {"value"},
    "input.hotkey": {"keys"},
    "input.scroll": {"delta"},
    "input.drag_drop": {"target_selector"},
    "clipboard.set": {"value", "digest", "value_ref", "value_length"},
}


class AutomationPlannerRuntime:
    def __init__(self, data_dir: DataDir) -> None:
        self.data_dir = data_dir
        self.root = data_dir.resolve("desktop_automation/plans")
        self.results_root = data_dir.resolve("desktop_automation/results")
        self.history_path = data_dir.resolve("desktop_automation/history/transitions.jsonl")
        self.root.mkdir(parents=True, exist_ok=True)
        self.results_root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        actor_id: str,
        objective: str,
        actions: list[AutomationAction],
        *,
        dry_run: bool = False,
    ) -> AutomationPlan:
        if not actor_id.strip() or not objective.strip():
            raise ValidationError("Automation actor and objective are required")
        if not 1 <= len(actions) <= 100:
            raise ValidationError("Automation plans require between 1 and 100 actions")
        normalized = [self._validate_action(action) for action in actions]
        plan = AutomationPlan(actor_id, objective[:500], normalized, dry_run=dry_run)
        return self.save(plan)

    def get(self, plan_id: str) -> AutomationPlan:
        path = self._path(plan_id)
        if not path.exists():
            raise NotFound(f"Automation plan not found: {plan_id}")
        return _plan(load_structured_file(path))

    def list(self, limit: int = 100) -> list[AutomationPlan]:
        paths = sorted(
            self.root.glob("*.yaml"), key=lambda path: path.stat().st_mtime, reverse=True
        )
        return [_plan(load_structured_file(path)) for path in paths[: max(0, min(limit, 500))]]

    def save(self, plan: AutomationPlan) -> AutomationPlan:
        dump_structured_file(self._path(plan.id), asdict(plan))
        self._record_history(plan)
        self._trim(self.root, 500)
        return plan

    def transition(self, plan: AutomationPlan, status: str, **updates: Any) -> AutomationPlan:
        updated = replace(
            plan,
            status=status,
            revision=plan.revision + 1,
            updated_at=now_iso(),
            **updates,
        )
        return self.save(updated)

    def save_result(self, plan_id: str, result: Any) -> None:
        dump_structured_file(self.results_root / f"{plan_id}.yaml", asdict(result))
        self._trim(self.results_root, 500)

    def _validate_action(self, action: AutomationAction) -> AutomationAction:
        if action.kind not in ALLOWED_ACTIONS:
            raise ValidationError(f"Unsupported automation action: {action.kind}")
        if not 1 <= action.max_attempts <= 5:
            raise ValidationError("Action max_attempts must be between 1 and 5")
        allowed_arguments = _COMMON_ARGUMENTS | _ARGUMENTS_BY_ACTION.get(action.kind, set())
        unknown_arguments = (
            set(action.arguments)
            - allowed_arguments
            - {
                "value_ref",
                "value_length",
                "digest",
                "selector_value_ref",
                "verification_value_ref",
            }
        )
        if unknown_arguments:
            raise ValidationError(
                f"Unsupported arguments for {action.kind}: {sorted(unknown_arguments)}"
            )
        if (
            action.kind.startswith(("element.", "input."))
            and action.kind != "input.hotkey"
            and action.selector is None
        ):
            raise ValidationError(f"Semantic selector is required for {action.kind}")
        if action.kind == "input.drag_drop":
            target = action.arguments.get("target_selector")
            allowed_selector_keys = set(ElementSelector.__dataclass_fields__)
            if (
                not isinstance(target, dict)
                or set(target) - allowed_selector_keys
                or target.get("value")
            ):
                raise ValidationError(
                    "Drag-and-drop requires a non-sensitive semantic target_selector"
                )
        if action.kind == "input.scroll":
            delta = int(action.arguments.get("delta", 0))
            if delta == 0 or not -20 <= delta <= 20:
                raise ValidationError("Scroll delta must be between -20 and 20 and non-zero")
        verification = action.verification or _default_verification(action)
        if verification is None:
            raise ValidationError(f"Explicit verification is required for {action.kind}")
        return replace(action, verification=verification)

    def _path(self, plan_id: str) -> Path:
        return self.root / f"{plan_id}.yaml"

    @staticmethod
    def _trim(root: Path, limit: int) -> None:
        paths = sorted(root.glob("*.yaml"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in paths[limit:]:
            path.unlink(missing_ok=True)

    def _record_history(self, plan: AutomationPlan) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "plan_id": plan.id,
            "actor_id": plan.actor_id,
            "status": plan.status,
            "revision": plan.revision,
            "current_action": plan.current_action,
            "updated_at": plan.updated_at,
        }
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        lines = self.history_path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 2000:
            self.history_path.write_text("\n".join(lines[-2000:]) + "\n", encoding="utf-8")


def _default_verification(action: AutomationAction) -> VerificationSpec | None:
    if action.kind == "application.launch":
        return VerificationSpec(
            "application.running",
            selector=ElementSelector(name=action.application),
            expected=True,
        )
    if action.kind == "window.focus":
        return VerificationSpec("window.foreground", expected=True, window_id=action.window_id)
    states = {
        "window.minimize": "minimized",
        "window.restore": "normal",
        "window.maximize": "maximized",
    }
    if action.kind in states:
        return VerificationSpec(
            "window.state", expected=states[action.kind], window_id=action.window_id
        )
    if action.kind == "window.close":
        return VerificationSpec("window.exists", expected=False, window_id=action.window_id)
    if action.kind == "element.focus":
        return VerificationSpec("element.focused", action.selector, True)
    if action.kind == "element.set_value":
        return VerificationSpec("element.value", action.selector, action.arguments.get("value"))
    if action.kind == "clipboard.set":
        return VerificationSpec("clipboard.digest", expected=action.arguments.get("digest"))
    if action.kind == "clipboard.clear":
        return VerificationSpec("clipboard.digest", expected=None)
    return None


def _selector(raw: dict[str, Any] | None) -> ElementSelector | None:
    return ElementSelector(**raw) if raw else None


def _verification(raw: dict[str, Any] | None) -> VerificationSpec | None:
    if not raw:
        return None
    return VerificationSpec(
        kind=str(raw["kind"]),
        selector=_selector(raw.get("selector")),
        expected=raw.get("expected"),
        window_id=raw.get("window_id"),
    )


def _action(raw: dict[str, Any]) -> AutomationAction:
    return AutomationAction(
        kind=str(raw["kind"]),
        selector=_selector(raw.get("selector")),
        application=raw.get("application"),
        window_id=raw.get("window_id"),
        arguments=dict(raw.get("arguments", {})),
        verification=_verification(raw.get("verification")),
        fallback_allowed=bool(raw.get("fallback_allowed", True)),
        max_attempts=int(raw.get("max_attempts", 2)),
        id=str(raw["id"]),
    )


def _preview(raw: dict[str, Any]) -> ActionPreview:
    return ActionPreview(
        action_id=str(raw["action_id"]),
        kind=str(raw["kind"]),
        target=dict(raw.get("target", {})),
        risk=RiskAssessment(**raw["risk"]),
        expected=dict(raw.get("expected", {})),
        provider_order=list(raw.get("provider_order", [])),
    )


def _plan(raw: dict[str, Any]) -> AutomationPlan:
    return AutomationPlan(
        actor_id=str(raw["actor_id"]),
        objective=str(raw["objective"]),
        actions=[_action(item) for item in raw.get("actions", [])],
        status=str(raw.get("status", "draft")),
        dry_run=bool(raw.get("dry_run", False)),
        previews=[_preview(item) for item in raw.get("previews", [])],
        approval_id=raw.get("approval_id"),
        current_action=int(raw.get("current_action", 0)),
        revision=int(raw.get("revision", 1)),
        id=str(raw["id"]),
        created_at=str(raw["created_at"]),
        updated_at=str(raw["updated_at"]),
    )
