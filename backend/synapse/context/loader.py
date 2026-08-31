from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.registry import AgentRegistry
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.policies.effective import EffectivePolicyRuntime
from synapse.project_governance.contracts import ProjectContextReadPort
from synapse.project_governance.errors import ProjectNotFound
from synapse.skills.contracts import SkillResolutionPort
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
    agent_policy: dict[str, Any]
    memory: list[ContextSection]
    identity: list[ContextSection]
    project: list[ContextSection]
    tasks: list[TaskContext]
    history: list[HistoryContext]
    sections: list[ContextSection | TaskContext | HistoryContext]
    conversation_context: dict[str, Any] | None = None
    delegation_context: dict[str, Any] | None = None
    multimodal_context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "agent_identity": self.agent_identity,
            "agent_policy": self.agent_policy,
            "memory": [asdict(item) for item in self.memory],
            "identity": [asdict(item) for item in self.identity],
            "project": [asdict(item) for item in self.project],
            "tasks": [asdict(item) for item in self.tasks],
            "history": [asdict(item) for item in self.history],
            "sections": [asdict(item) for item in self.sections],
            "conversation_context": self.conversation_context,
            "delegation_context": self.delegation_context,
            "multimodal_context": self.multimodal_context,
        }


class ContextLoader:
    def __init__(
        self,
        data_dir: DataDir,
        permissions: PermissionManager,
        event_bus: EventBus,
        agents: AgentRegistry,
        identities: AgentIdentityRuntime,
        policies: EffectivePolicyRuntime,
        tasks: TaskRuntime,
        skill_context: SkillResolutionPort | None = None,
        project_context: ProjectContextReadPort | None = None,
    ):
        self.data_dir = data_dir
        self.permissions = permissions
        self.event_bus = event_bus
        self.agents = agents
        self.identities = identities
        self.policies = policies
        self.tasks = tasks
        self.skill_context = skill_context
        self.project_context = project_context

    def load(
        self,
        context: PermissionContext,
        agent_id: str,
        project_id: str | None = None,
        history: Sequence[str | dict[str, str]] | None = None,
        max_history_items: int = 5,
        conversation_context: dict[str, Any] | None = None,
        delegation_context: dict[str, Any] | None = None,
        multimodal_context: dict[str, Any] | None = None,
    ) -> LoadedContext:
        self.permissions.require(context, "filesystem.read")
        self.agents.get(agent_id)
        agent_identity = self.identities.load_identity(agent_id).to_dict()
        agent_policy = self.policies.resolve(context, agent_id).to_dict()

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

        if self.skill_context:
            for loaded_skill in self.skill_context.load_assigned(
                agent_id, project_id=project_id, context_budget=4000
            ):
                section = ContextSection(
                    kind="skill",
                    name=f"{loaded_skill.skill_id}@{loaded_skill.version}",
                    source=f"skill:{loaded_skill.skill_id}@{loaded_skill.version}",
                    content=loaded_skill.instructions,
                    order=order,
                )
                order += 1
                sections.append(section)

        if project_id:
            if self.project_context:
                try:
                    governed = self.project_context.read_project_context(project_id, budget=4000)
                except ProjectNotFound:
                    add_file("project", "project", f"projects/{project_id}/PROJECT.md")
                    add_file("project", "project_memory", f"projects/{project_id}/MEMORY.md")
                else:
                    section = ContextSection(
                        kind="project",
                        name="governed_project_context",
                        source=f"project:{project_id}@{governed.project_revision}",
                        content=json.dumps(asdict(governed), default=str, sort_keys=True),
                        order=order,
                    )
                    order += 1
                    project.append(section)
                    sections.append(section)
            else:
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
            agent_policy=agent_policy,
            memory=memory,
            identity=identity,
            project=project,
            tasks=task_contexts,
            history=history_contexts,
            sections=sections,
            conversation_context=conversation_context,
            delegation_context=delegation_context,
            multimodal_context=multimodal_context,
        )
        self.event_bus.emit(
            "context.loaded",
            context.actor_id,
            {
                "agent_id": agent_id,
                "project_id": project_id,
                "sections": len(sections),
                "history_items": len(history_contexts),
                "conversation_context": conversation_context is not None,
                "delegation_context": delegation_context is not None,
                "multimodal_context": multimodal_context is not None,
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
        history: Sequence[str | dict[str, str]],
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
