from __future__ import annotations

from synapse.core.exceptions import NotFound
from synapse.tools.base import ToolSpec
from synapse.tools.errors import ToolError
from synapse.tools.models import RegisteredTool, ToolDefinition, ToolHandler


class RuntimeToolRegistry:
    """The single canonical tool descriptor registry. It never executes tools."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        if not definition.tool_id:
            raise ToolError("tool_schema_invalid", "Tool definition requires tool_id.")
        self._validate_schema(definition.input_schema)
        existing = self._tools.get(definition.tool_id)
        if existing and existing.definition != definition:
            raise ToolError(
                "execution_conflict", f"Conflicting tool id: {definition.tool_id}", status_code=409
            )
        self._tools[definition.tool_id] = RegisteredTool(definition, handler)

    def unregister(self, tool_id: str) -> ToolDefinition:
        try:
            return self._tools.pop(tool_id).definition
        except KeyError as exc:
            raise NotFound(f"Tool not found: {tool_id}") from exc

    @staticmethod
    def _validate_schema(schema: dict) -> None:
        if not isinstance(schema, dict) or schema.get("type", "object") != "object":
            raise ToolError("tool_schema_invalid", "Tool input schema must be an object schema")
        if "properties" in schema and not isinstance(schema["properties"], dict):
            raise ToolError("tool_schema_invalid", "Tool schema properties must be an object")
        if "required" in schema and not isinstance(schema["required"], list):
            raise ToolError("tool_schema_invalid", "Tool schema required must be a list")

    def list_tools(self, *, include_compatibility: bool = False) -> list[ToolDefinition]:
        return [
            item.definition
            for item in sorted(
                self._tools.values(), key=lambda registered: registered.definition.tool_id
            )
            if include_compatibility
            or not (
                item.definition.metadata.get("legacy_catalog")
                or item.definition.metadata.get("internal_tool")
            )
        ]

    def list_registered_tools(self) -> list[ToolDefinition]:
        return self.list_tools(include_compatibility=True)

    def list_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=item.tool_id,
                description=item.description,
                permission=item.required_permission or "tools.execute",
                risk_level=item.risk_level,
            )
            for item in self.list_registered_tools()
            if item.metadata.get("legacy_catalog")
        ]

    def get_spec(self, tool_id: str) -> ToolSpec:
        definition = self.get_tool(tool_id).definition
        return ToolSpec(
            name=definition.tool_id,
            description=definition.description,
            permission=definition.required_permission or "tools.execute",
            risk_level=definition.risk_level,
        )

    def get_tool(self, tool_id: str) -> RegisteredTool:
        tool = self._tools.get(tool_id)
        if not tool:
            raise NotFound(f"Tool not found: {tool_id}")
        return tool

    def has_tool(self, tool_id: str) -> bool:
        return tool_id in self._tools
