from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound
from synapse.core.permissions import PermissionContext, PermissionManager


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    permission: str


class Tool(Protocol):
    spec: ToolSpec

    def run(self, context: PermissionContext, **kwargs: Any) -> dict[str, Any]:
        ...


class ToolRegistry:
    def __init__(self, permissions: PermissionManager, event_bus: EventBus):
        self.permissions = permissions
        self.event_bus = event_bus
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.spec.name] = tool

    def list_specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in sorted(self._tools.values(), key=lambda item: item.spec.name)]

    def get_spec(self, name: str) -> ToolSpec:
        tool = self._tools.get(name)
        if not tool:
            raise NotFound(f"Tool not found: {name}")
        return tool.spec

    def execute(
        self,
        name: str,
        context: PermissionContext,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            raise NotFound(f"Tool not found: {name}")

        self.permissions.require(context, tool.spec.permission)
        self.event_bus.emit("tool.started", context.actor_id, {"tool": name})
        try:
            result = tool.run(context, **(arguments or {}))
        except Exception as exc:
            self.event_bus.emit(
                "tool.failed",
                context.actor_id,
                {"tool": name, "error": type(exc).__name__, "message": str(exc)},
            )
            raise

        self.event_bus.emit("tool.succeeded", context.actor_id, {"tool": name})
        return result
