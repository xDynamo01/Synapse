from __future__ import annotations

import hashlib
from typing import Any

from synapse.desktop_automation.models import VerificationResult, VerificationSpec


class VerificationRuntime:
    def __init__(self, applications: Any, windows: Any, ui: Any, clipboard: Any) -> None:
        self.applications = applications
        self.windows = windows
        self.ui = ui
        self.clipboard = clipboard

    def verify(self, spec: VerificationSpec, *, observed_hint: Any = None) -> VerificationResult:
        try:
            observed, evidence = self._observe(spec, observed_hint)
            verified = observed == spec.expected
            return VerificationResult(
                verified=verified,
                kind=spec.kind,
                expected=_safe_value(spec.kind, spec.expected),
                observed=_safe_value(spec.kind, observed),
                evidence=evidence,
                reason=None if verified else "observed_state_did_not_match",
            )
        except Exception as exc:
            return VerificationResult(
                False,
                spec.kind,
                _safe_value(spec.kind, spec.expected),
                None,
                [{"error_type": type(exc).__name__}],
                "verification_observation_failed",
            )

    def _observe(self, spec: VerificationSpec, hint: Any) -> tuple[Any, list[dict[str, Any]]]:
        if spec.kind == "action.performed":
            observed = bool((hint or {}).get("performed"))
            return observed, [{"source": "provider_result", "performed": observed}]
        if spec.kind == "application.running":
            name = spec.selector.name if spec.selector else None
            applications = self.applications.find(str(name or ""))
            return bool(applications), [
                {"source": "application_runtime", "matches": len(applications)}
            ]
        if spec.kind.startswith("window."):
            windows = self.windows.list()
            window = next((item for item in windows if item.window_id == spec.window_id), None)
            if spec.kind == "window.exists":
                return window is not None, [
                    {"source": "window_runtime", "window_id": spec.window_id}
                ]
            if window is None:
                return None, [{"source": "window_runtime", "missing": True}]
            field = {"window.foreground": "foreground", "window.state": "state"}[spec.kind]
            return getattr(window, field), [
                {"source": "window_runtime", "window_id": window.window_id}
            ]
        if spec.kind.startswith("element."):
            if spec.selector is None:
                return None, [{"source": "ui_automation", "selector_missing": True}]
            _provider, elements = self.ui.find(spec.selector, 1)
            element = elements[0]
            if spec.kind == "element.exists":
                return True, [{"source": element.provider, "element_id": element.element_id}]
            field = {
                "element.focused": "focused",
                "element.value": "value",
                "element.selected": "selected",
                "element.expanded": "expanded",
                "element.toggled": "toggled",
            }[spec.kind]
            return getattr(element, field), [
                {"source": element.provider, "element_id": element.element_id}
            ]
        if spec.kind == "clipboard.digest":
            current = self.clipboard.get()
            return current["digest"], [{"source": "clipboard_runtime", "length": current["length"]}]
        raise ValueError(f"Unsupported verification kind: {spec.kind}")


def _safe_value(kind: str, value: Any) -> Any:
    if kind == "element.value" and isinstance(value, str):
        return {
            "redacted": True,
            "length": len(value),
            "digest": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        }
    if isinstance(value, str) and len(value) > 80:
        return {"redacted": True, "length": len(value)}
    return value
