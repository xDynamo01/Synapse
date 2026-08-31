from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.resources import ResourceRef, check_resource_access


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    permission: str
    risk_level: str = "low"


class Tool(Protocol):
    spec: ToolSpec

    def run(self, context: PermissionContext, **kwargs: Any) -> dict[str, Any]: ...


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

        resource_ref = _resource_ref_for_tool(name, arguments or {})
        if resource_ref:
            check_resource_access(
                agent_id=context.actor_id,
                action=_resource_action_for_tool(name),
                resource_ref=resource_ref,
                context=context,
                permission_manager=self.permissions,
                required_permission=tool.spec.permission,
            )
        else:
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


def _resource_ref_for_tool(name: str, arguments: dict[str, Any]) -> ResourceRef | None:
    if name == "read_file":
        return ResourceRef(
            "file", path=str(arguments.get("path", "")), metadata={"tool_name": name}
        )
    if name == "write_file":
        return ResourceRef(
            "file", path=str(arguments.get("path", "")), metadata={"tool_name": name}
        )
    if name == "list_directory":
        return ResourceRef(
            "file",
            path=str(arguments.get("path", ".")),
            metadata={"tool_name": name},
        )
    if name == "search_files":
        return ResourceRef(
            "file",
            path=str(arguments.get("path", ".")),
            metadata={"tool_name": name},
        )
    return None


def _resource_action_for_tool(name: str) -> str:
    if name == "read_file":
        return "read"
    if name == "write_file":
        return "update"
    if name in {"list_directory", "search_files"}:
        return "list"
    return "execute"
