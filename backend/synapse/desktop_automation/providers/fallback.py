from __future__ import annotations

from typing import Any

from synapse.desktop_automation.errors import ActionFailed, TargetNotFound
from synapse.desktop_automation.models import AutomationAction, ElementSelector, UIElement


class _VisualFallbackProvider:
    semantic = False

    def __init__(self, screen: Any, fallback_kind: str) -> None:
        self.screen = screen
        self.fallback_kind = fallback_kind
        self.name = f"fallback_{fallback_kind}"

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "available": self.screen.available(self.fallback_kind),
            "semantic": False,
            "fallback": self.fallback_kind,
        }

    def list_applications(self):
        return []

    def list_windows(self):
        return []

    def accessibility_tree(self, window_id: str, max_nodes: int = 500) -> UIElement:
        raise TargetNotFound("Visual fallback does not expose an accessibility tree")

    def find_elements(self, selector: ElementSelector, limit: int = 20) -> list[UIElement]:
        return self.screen.find(selector, mode=self.fallback_kind, limit=limit)

    def perform(self, action: AutomationAction, element: UIElement | None = None) -> dict[str, Any]:
        raise ActionFailed("Visual providers locate and verify; InputRuntime performs the fallback")


class OCRFallbackProvider(_VisualFallbackProvider):
    def __init__(self, screen: Any) -> None:
        super().__init__(screen, "ocr")


class VisionFallbackProvider(_VisualFallbackProvider):
    def __init__(self, screen: Any) -> None:
        super().__init__(screen, "vision")
