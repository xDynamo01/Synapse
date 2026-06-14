from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.agents.communication import AgentCommunication
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ToolExecutionError, ValidationError
from synapse.core.permissions import PermissionContext
from synapse.tasks.runtime import TaskRuntime
from synapse.tools.base import ToolRegistry, ToolSpec


class ReadFileTool:
    spec = ToolSpec(
        name="read_file",
        description="Read a UTF-8 text file inside DATA_DIR.",
        permission="filesystem.read",
        risk_level="low",
    )

    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    def run(self, context: PermissionContext, **kwargs: Any) -> dict[str, Any]:
        path = self.data_dir.resolve(str(kwargs["path"]))
        return {"path": str(path), "content": path.read_text(encoding="utf-8")}


class WriteFileTool:
    spec = ToolSpec(
        name="write_file",
        description="Write or append a UTF-8 text file inside DATA_DIR.",
        permission="filesystem.write",
        risk_level="high",
    )

    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    def run(self, context: PermissionContext, **kwargs: Any) -> dict[str, Any]:
        path = self.data_dir.resolve(str(kwargs["path"]))
        content = str(kwargs.get("content", ""))
        append = bool(kwargs.get("append", False))
        path.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(content)
        else:
            path.write_text(content, encoding="utf-8")
        return {"path": str(path), "bytes": len(content.encode("utf-8")), "append": append}


class ListDirectoryTool:
    spec = ToolSpec(
        name="list_directory",
        description="List files and directories inside DATA_DIR.",
        permission="filesystem.list",
        risk_level="low",
    )

    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    def run(self, context: PermissionContext, **kwargs: Any) -> dict[str, Any]:
        path = self.data_dir.resolve(str(kwargs.get("path", ".")))
        if not path.is_dir():
            raise ValidationError(f"Not a directory: {path}")
        entries = [
            {"name": item.name, "type": "directory" if item.is_dir() else "file"}
            for item in sorted(path.iterdir(), key=lambda entry: entry.name.lower())
        ]
        return {"path": str(path), "entries": entries}


class SearchFilesTool:
    spec = ToolSpec(
        name="search_files",
        description="Search text files inside DATA_DIR by pattern and optional query.",
        permission="filesystem.search",
        risk_level="low",
    )

    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    def run(self, context: PermissionContext, **kwargs: Any) -> dict[str, Any]:
        root = self.data_dir.resolve(str(kwargs.get("path", ".")))
        pattern = str(kwargs.get("pattern", "*"))
        query = kwargs.get("query")
        max_results = int(kwargs.get("max_results", 50))
        if not root.is_dir():
            raise ValidationError(f"Not a directory: {root}")

        results: list[dict[str, Any]] = []
        for path in root.rglob(pattern):
            if len(results) >= max_results:
                break
            if not path.is_file():
                continue
            if query is None:
                results.append({"path": str(path.relative_to(self.data_dir.root))})
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if str(query) in text:
                results.append({"path": str(path.relative_to(self.data_dir.root))})
        return {"results": results}


class WebSearchTool:
    spec = ToolSpec(
        name="web_search",
        description="Search the web through a configured provider.",
        permission="web.search",
        risk_level="medium",
    )

    def run(self, context: PermissionContext, **kwargs: Any) -> dict[str, Any]:
        query = str(kwargs.get("query", "")).strip()
        if not query:
            raise ValidationError("web_search requires query")
        return {
            "status": "unconfigured",
            "query": query,
            "results": [],
            "message": "No local web search provider is configured yet.",
        }


class SendAgentMessageTool:
    spec = ToolSpec(
        name="send_agent_message",
        description="Send a persistent message to another agent inbox.",
        permission="agents.message",
        risk_level="medium",
    )

    def __init__(self, communication: AgentCommunication):
        self.communication = communication

    def run(self, context: PermissionContext, **kwargs: Any) -> dict[str, Any]:
        message = self.communication.send_agent_message(
            context=context,
            from_agent_id=str(kwargs["from_agent_id"]),
            to_agent_id=str(kwargs["to_agent_id"]),
            body=str(kwargs["body"]),
            subject=kwargs.get("subject"),
            task_id=kwargs.get("task_id"),
        )
        return asdict(message)


class CreateTaskTool:
    spec = ToolSpec(
        name="create_task",
        description="Create a persistent task in DATA_DIR/tasks/active.",
        permission="tasks.create",
        risk_level="low",
    )

    def __init__(self, task_runtime: TaskRuntime):
        self.task_runtime = task_runtime

    def run(self, context: PermissionContext, **kwargs: Any) -> dict[str, Any]:
        task = self.task_runtime.create_task(
            context=context,
            title=str(kwargs["title"]),
            description=str(kwargs.get("description", "")),
            metadata=dict(kwargs.get("metadata", {})),
        )
        return asdict(task)


class UpdateTaskTool:
    spec = ToolSpec(
        name="update_task",
        description="Update a persistent task status or metadata.",
        permission="tasks.update",
        risk_level="medium",
    )

    def __init__(self, task_runtime: TaskRuntime):
        self.task_runtime = task_runtime

    def run(self, context: PermissionContext, **kwargs: Any) -> dict[str, Any]:
        task_id = kwargs.get("task_id")
        if not task_id:
            raise ToolExecutionError("update_task requires task_id")
        task = self.task_runtime.update_task(
            context=context,
            task_id=str(task_id),
            status=kwargs.get("status"),
            note=kwargs.get("note"),
            metadata=kwargs.get("metadata"),
        )
        return asdict(task)


def register_builtin_tools(
    registry: ToolRegistry,
    data_dir: DataDir,
    communication: AgentCommunication,
    task_runtime: TaskRuntime,
) -> None:
    registry.register(ReadFileTool(data_dir))
    registry.register(WriteFileTool(data_dir))
    registry.register(ListDirectoryTool(data_dir))
    registry.register(SearchFilesTool(data_dir))
    registry.register(WebSearchTool())
    registry.register(SendAgentMessageTool(communication))
    registry.register(CreateTaskTool(task_runtime))
    registry.register(UpdateTaskTool(task_runtime))
