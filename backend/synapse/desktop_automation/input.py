from __future__ import annotations

from typing import Any


class InputRuntime:
    """Last-resort element-relative input; never selected before semantic providers."""

    def __init__(self, provider: Any) -> None:
        self.provider = provider

    def perform(self, action: Any, element: Any | None = None) -> dict[str, Any]:
        return self.provider.perform(action, element)

    def health(self) -> dict[str, Any]:
        return {"provider": self.provider.name, "fallback_only": True}
