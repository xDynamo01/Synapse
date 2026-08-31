from __future__ import annotations

import hashlib
from dataclasses import asdict, replace
from typing import Any

from synapse.desktop_automation.errors import ActionFailed, ProviderUnavailable, TargetNotFound
from synapse.desktop_automation.models import AutomationAction, ElementSelector, UIElement


class UIAutomationRuntime:
    def __init__(self, providers: list[Any], input_runtime: Any) -> None:
        self.providers = providers
        self.input = input_runtime

    def tree(self, window_id: str, max_nodes: int = 500) -> UIElement:
        primary = self.providers[0]
        return self.public_element(primary.accessibility_tree(window_id, max_nodes=max_nodes))

    def find(self, selector: ElementSelector, limit: int = 20) -> tuple[Any, list[UIElement]]:
        errors = []
        for provider in self.providers:
            try:
                return provider, provider.find_elements(selector, limit)
            except (ProviderUnavailable, TargetNotFound) as exc:
                errors.append({"provider": provider.name, "error": type(exc).__name__})
        raise TargetNotFound(f"Element was not found by configured providers: {errors}")

    def perform(self, action: AutomationAction) -> tuple[str, dict[str, Any], UIElement | None]:
        if action.selector is None:
            if action.kind.startswith("input."):
                return self.input.provider.name, self.input.perform(action), None
            return self.providers[0].name, self.providers[0].perform(action), None
        failures = []
        for provider in self.providers:
            if not provider.semantic and not action.fallback_allowed:
                break
            try:
                element = provider.find_elements(action.selector, 1)[0]
                if action.kind.startswith("input."):
                    runtime_action = action
                    if action.kind == "input.drag_drop":
                        target_selector = ElementSelector(**action.arguments["target_selector"])
                        _target_provider, targets = self.find(target_selector, 1)
                        if targets[0].bounds is None:
                            raise ActionFailed("Drag target has no current bounds")
                        runtime_action = replace(
                            action,
                            arguments={
                                **action.arguments,
                                "target_bounds": asdict(targets[0].bounds),
                            },
                        )
                    return provider.name, self.input.perform(runtime_action, element), element
                if provider.semantic:
                    return provider.name, provider.perform(action, element), element
                return provider.name, self.input.perform(action, element), element
            except (ActionFailed, ProviderUnavailable, TargetNotFound) as exc:
                failures.append({"provider": provider.name, "error": type(exc).__name__})
        raise ActionFailed(f"No provider could perform the action: {failures}")

    def provider_order(self) -> list[str]:
        return [provider.name for provider in self.providers]

    def public_element(self, element: UIElement) -> UIElement:
        value = element.value
        redacted = None
        if value is not None:
            redacted = f"[REDACTED_VALUE length={len(value)} sha256={hashlib.sha256(value.encode('utf-8')).hexdigest()}]"
        return replace(
            element,
            value=redacted,
            children=[self.public_element(child) for child in element.children],
        )
