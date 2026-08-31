"""Consumer-owned Search tool boundary; no provider or egress implementation."""

from __future__ import annotations

from typing import Protocol


class SearchToolPort(Protocol):
    def search(
        self, actor_id: str, actor_type: str, arguments: dict[str, object]
    ) -> dict[str, object]: ...


class UnconfiguredSearchTool:
    """Factual absence of a composed Search consumer, not a legacy execution path."""

    def search(
        self, actor_id: str, actor_type: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        del actor_id, actor_type, arguments
        return {
            "status": "unconfigured",
            "results": [],
            "message": "Search provider is not configured.",
            "provider_configured": False,
            "provider_authorized": None,
            "provider_reachable": None,
        }
