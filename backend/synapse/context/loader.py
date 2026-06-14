from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.registry import AgentRegistry
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.tasks.runtime import Task, TaskRuntime


@dataclass(frozen=True)
class ContextSection:
    kind: str
    name: str
    source: str
    content: str
    order: int


@dataclass(frozen=True)
class TaskContext:
    id: str
    title: str
    status: str
    source: str
    order: int
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HistoryContext:
    role: str
    content: str
    order: int


@dataclass(frozen=True)
class LoadedContext:
    agent_id: str
    project_id: str | None
    agent_identity: dict[str, Any]
    memory: list[ContextSection]
    identity: list[ContextSection]
    project: list[ContextSection]
    tasks: list[TaskContext]
    history: list[HistoryContext]
    sections: list[ContextSection | TaskContext | HistoryContext]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "agent_identity": self.agent_identity,
            "memory": [asdict(item) for item in self.memory],
            "identity": [asdict(item) for item in self.identity],
            "project": [asdict(item) for item in self.project],
            "tasks": [asdict(item) for item in self.tasks],
            "history": [asdict(item) for item in self.history],
            "sections": [asdict(item) for item in self.sections],
        }


class ContextLoader:
    def __init__(
        self,
        data_dir: DataDir,
        permissions: PermissionManager,
        event_bus: EventBus,
        agents: AgentRegistry,
        identities: AgentIdentityRuntime,
        tasks: TaskRuntime,
    ):
        self.data_dir = data_dir
        self.permissions = permissions
        self.event_bus = event_bus
        self.agents = agents
        self.identities = identities
        self.tasks = tasks

    def load(
        self,
        context: PermissionContext,
        agent_id: str,
        project_id: str | None = None,
        history: list[str | dict[str, str]] | None = None,
        max_history_items: int = 5,
    ) -> LoadedContext:
        self.permissions.require(context, "filesystem.read")
        self.agents.get(agent_id)
        agent_identity = self.identities.load_identity(agent_id).to_dict()

        order = 0
        memory: list[ContextSection] = []
        identity: list[ContextSection] = []
        project: list[ContextSection] = []
        task_contexts: list[TaskContext] = []
        history_contexts: list[HistoryContext] = []
        sections: list[ContextSection | TaskContext | HistoryContext] = []

        def add_file(kind: str, name: str, relative_path: str) -> None:
            nonlocal order
            path = self.data_dir.resolve(relative_path)
            if not path.exists():
                return
            section = ContextSection(
                kind=kind,
                name=name,
                source=relative_path.replace("\\", "/"),
                content=path.read_text(encoding="utf-8"),
                order=order,
            )
            order += 1
            sections.append(section)
            if kind == "memory":
                memory.append(section)
            elif kind == "identity":
                identity.append(section)
            elif kind == "project":
                project.append(section)

        add_file("memory", "system", "memory/SYSTEM.md")
        add_file("memory", "user", "memory/USER.md")
        add_file("memory", "global", "memory/MEMORY.md")
        add_file("identity", "agent_soul", f"agents/{agent_id}/SOUL.md")
        add_file("memory", "agent_memory", f"agents/{agent_id}/MEMORY.md")
        add_file("identity", "agent_skills", f"agents/{agent_id}/SKILLS.md")

        if project_id:
            add_file("project", "project", f"projects/{project_id}/PROJECT.md")
            add_file("project", "project_memory", f"projects/{project_id}/MEMORY.md")

        for task in self._relevant_tasks(agent_id, project_id):
            task_context = TaskContext(
                id=task.id,
                title=task.title,
                description=task.description,
                status=task.status,
                metadata=task.metadata,
                source=f"tasks/{task.status}/{task.id}.json",
                order=order,
            )
            order += 1
            task_contexts.append(task_context)
            sections.append(task_context)

        for item in self._history_items(history or [], max_history_items):
            history_context = HistoryContext(
                role=item["role"],
                content=item["content"],
                order=order,
            )
            order += 1
            history_contexts.append(history_context)
            sections.append(history_context)

        loaded = LoadedContext(
            agent_id=agent_id,
            project_id=project_id,
            agent_identity=agent_identity,
            memory=memory,
            identity=identity,
            project=project,
            tasks=task_contexts,
            history=history_contexts,
            sections=sections,
        )
        self.event_bus.emit(
            "context.loaded",
            context.actor_id,
            {
                "agent_id": agent_id,
                "project_id": project_id,
                "sections": len(sections),
                "history_items": len(history_contexts),
            },
        )
        return loaded

    def _relevant_tasks(self, agent_id: str, project_id: str | None) -> list[Task]:
        relevant: list[Task] = []
        for task in self.tasks.list_tasks():
            if self._is_relevant_task(task, agent_id, project_id):
                relevant.append(task)
        return sorted(relevant, key=lambda task: (task.status, task.created_at, task.id))

    @staticmethod
    def _is_relevant_task(task: Task, agent_id: str, project_id: str | None) -> bool:
        metadata = task.metadata
        agent_values = {
            metadata.get("agent"),
            metadata.get("agent_id"),
            metadata.get("assigned_agent"),
            metadata.get("assigned_agent_id"),
        }
        if agent_id in agent_values:
            return True
        if project_id and metadata.get("project_id") == project_id:
            return True
        return False

    @staticmethod
    def _history_items(
        history: list[str | dict[str, str]],
        max_history_items: int,
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in history[-max_history_items:]:
            if isinstance(item, str):
                normalized.append({"role": "unknown", "content": item})
            else:
                normalized.append(
                    {
                        "role": str(item.get("role", "unknown")),
                        "content": str(item.get("content", "")),
                    }
                )
        return normalized
