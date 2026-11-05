from dataclasses import asdict

from synapse.core.permissions import PermissionContext
from synapse.memory.consolidation import MemoryCandidate
from synapse.memory.store import MemoryStore
from synapse.tools.models import ToolDefinition, ToolExecutionRequest
from synapse.tools.runtime import ToolRuntime


def register_agent_memory_tools(tools: ToolRuntime, memory: MemoryStore) -> None:
    """Expose agent-owned memory through the existing permission-checked tool runtime."""

    def remember(request: ToolExecutionRequest) -> dict[str, object]:
        context = PermissionContext(actor_id=request.caller, actor_type=request.caller_type)
        record = memory.create(
            context,
            scope="workspace" if request.metadata.get("workspace_id") else "agent",
            owner_id=request.caller,
            workspace_id=request.metadata.get("workspace_id"),
            source="agent_tool",
            content=str(request.arguments["content"]),
            kind=str(request.arguments.get("kind", "fact")),
            supersedes=request.arguments.get("supersedes"),
            expected_revision=request.arguments.get("expected_revision"),
        )
        return {"memory_id": record.id, "status": record.status, "content": record.content}

    def recall(request: ToolExecutionRequest) -> dict[str, object]:
        context = PermissionContext(actor_id=request.caller, actor_type=request.caller_type)
        requested = request.arguments.get("workspace_ids")
        workspaces = (
            requested
            if isinstance(requested, list)
            else (
                [str(request.metadata["workspace_id"])]
                if request.metadata.get("workspace_id")
                else []
            )
        )
        result = memory.retrieve_memory(
            context,
            query=str(request.arguments["query"]),
            scopes=["agent", "workspace", "episodic", "working"],
            filters={
                "workspace_ids": workspaces,
                "cross_workspace": request.arguments.get("cross_workspace") is True,
            },
            owner_ids=[request.caller],
            limit=10,
            budget=2000,
        )
        return dict(asdict(result))

    def consolidate(request: ToolExecutionRequest) -> dict[str, object]:
        context = PermissionContext(actor_id=request.caller, actor_type=request.caller_type)
        memory.consolidator.submit(
            context,
            MemoryCandidate(
                content=str(request.arguments["content"]),
                source=f"agent_tool:{request.id or request.caller}",
                kind=str(request.arguments.get("kind", "fact")),
                owner_id=request.caller,
                workspace_id=request.metadata.get("workspace_id"),
                supersedes=request.arguments.get("supersedes"),
                expected_revision=request.arguments.get("expected_revision"),
                explicitly_requested=True,
                verified=False,
            ),
        )
        return {
            "status": "queued",
            "persisted": False,
            "message": "Consolidation queued; use recall to verify persistence.",
        }

    for name, description, argument, permission, handler in (
        (
            "consolidate_memory",
            "Queue an explicitly requested memory without blocking the conversation. Pending is not saved; verify with recall.",
            "content",
            "filesystem.write",
            consolidate,
        ),
        (
            "remember",
            "Save information explicitly requested by the user in your persistent agent memory.",
            "content",
            "filesystem.write",
            remember,
        ),
        (
            "recall",
            "Search your own persistent agent memory for information requested by the user.",
            "query",
            "filesystem.read",
            recall,
        ),
    ):
        tools.register(
            ToolDefinition(
                tool_id=name,
                display_name=name.title(),
                description=description,
                category="memory",
                required_permission=permission,
                approval_required=name in {"remember", "consolidate_memory"},
                input_schema={
                    "type": "object",
                    "properties": {
                        argument: {"type": "string", "minLength": 1},
                        **(
                            {
                                "workspace_ids": {"type": "array", "items": {"type": "string"}},
                                "cross_workspace": {"type": "boolean"},
                            }
                            if name == "recall"
                            else {
                                "kind": {
                                    "type": "string",
                                    "enum": [
                                        "fact",
                                        "decision",
                                        "summary",
                                        "episode",
                                        "result",
                                        "reference",
                                    ],
                                },
                                "supersedes": {"type": "string"},
                                "expected_revision": {"type": "integer", "minimum": 1},
                            }
                        ),
                    },
                    "required": [argument],
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
                metadata={"legacy_catalog": True},
            ),
            handler,
        )

    def discover(request: ToolExecutionRequest) -> dict[str, object]:
        context = PermissionContext(actor_id=request.caller, actor_type=request.caller_type)
        result: dict[str, object] = {"scopes": memory.discover_scopes(context)}
        workspace = request.arguments.get("workspace_id")
        if workspace:
            records = [
                entry for entry in memory.discover(context) if entry["workspace_id"] == workspace
            ]
            offset = max(0, int(request.arguments.get("offset", 0)))
            result.update(
                {
                    "records": records[offset : offset + 100],
                    "total": len(records),
                    "next_offset": offset + 100 if offset + 100 < len(records) else None,
                }
            )
        return result

    tools.register(
        ToolDefinition(
            tool_id="memory_index",
            display_name="Memory index",
            description="Discover authorized memory scopes and record references without loading their contents.",
            category="memory",
            required_permission="filesystem.read",
            input_schema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            metadata={"legacy_catalog": True},
        ),
        discover,
    )
