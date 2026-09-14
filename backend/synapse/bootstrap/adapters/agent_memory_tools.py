from dataclasses import asdict

from synapse.core.permissions import PermissionContext
from synapse.memory.store import MemoryStore
from synapse.tools.models import ToolDefinition, ToolExecutionRequest
from synapse.tools.runtime import ToolRuntime


def register_agent_memory_tools(tools: ToolRuntime, memory: MemoryStore) -> None:
    """Expose agent-owned memory through the existing permission-checked tool runtime."""
    def remember(request: ToolExecutionRequest) -> dict[str, object]:
        context = PermissionContext(actor_id=request.caller, actor_type=request.caller_type)
        record = memory.create(
            context, scope="agent", owner_id=request.caller,
            source="agent_tool", content=str(request.arguments["content"]),
        )
        return {"memory_id": record.id, "status": record.status, "content": record.content}

    def recall(request: ToolExecutionRequest) -> dict[str, object]:
        context = PermissionContext(actor_id=request.caller, actor_type=request.caller_type)
        result = memory.retrieve_memory(
            context, query=str(request.arguments["query"]), scopes=["agent"],
            owner_ids=[request.caller], limit=10, budget=2000,
        )
        return dict(asdict(result))

    for name, description, argument, permission, handler in (
        ("remember", "Save information explicitly requested by the user in your persistent agent memory.",
         "content", "filesystem.write", remember),
        ("recall", "Search your own persistent agent memory for information requested by the user.",
         "query", "filesystem.read", recall),
    ):
        tools.register(
            ToolDefinition(
                tool_id=name, display_name=name.title(), description=description,
                category="memory", required_permission=permission,
                input_schema={"type": "object", "properties": {argument: {"type": "string", "minLength": 1}},
                              "required": [argument], "additionalProperties": False},
                output_schema={"type": "object"}, metadata={"legacy_catalog": True},
            ), handler,
        )
