from __future__ import annotations

from typing import Any, Protocol

from synapse.desktop_automation.models import (
    ApplicationInfo,
    AutomationAction,
    ElementSelector,
    UIElement,
    WindowInfo,
)


class DesktopProvider(Protocol):
    name: str
    semantic: bool
    fallback_kind: str | None

    def health(self) -> dict[str, Any]: ...

    def list_applications(self) -> list[ApplicationInfo]: ...

    def list_windows(self) -> list[WindowInfo]: ...

    def accessibility_tree(self, window_id: str, max_nodes: int = 500) -> UIElement: ...

    def find_elements(self, selector: ElementSelector, limit: int = 20) -> list[UIElement]: ...

    def perform(
        self, action: AutomationAction, element: UIElement | None = None
    ) -> dict[str, Any]: ...


class ClipboardProvider(Protocol):
    def clipboard_get(self) -> str | None: ...

    def clipboard_set(self, value: str) -> None: ...

    def clipboard_clear(self) -> None: ...
