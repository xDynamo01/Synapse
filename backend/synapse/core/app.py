from __future__ import annotations

from dataclasses import dataclass

from synapse.agents.communication import AgentCommunication
from synapse.agents.presence import PresenceStore
from synapse.agents.registry import AgentRegistry
from synapse.agents.runtime import AgentRuntime
from synapse.auth.devices import DeviceRegistry
from synapse.chat.runtime import ChatRuntime
from synapse.commands.runtime import CommandRuntime
from synapse.context.loader import ContextLoader
from synapse.core.config import ConfigStore, Settings
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.model_router import ModelRouter
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.memory.store import MemoryStore
from synapse.tasks.runtime import TaskRuntime
from synapse.tools.base import ToolRegistry
from synapse.tools.builtin import register_builtin_tools
from synapse.tools.router import ToolRouter


@dataclass
class RuntimeContainer:
    settings: Settings
    data_dir: DataDir
    config: ConfigStore
    events: EventBus
    permissions: PermissionManager
    models: ModelRouter
    agents: AgentRegistry
    agent_runtime: AgentRuntime
    communication: AgentCommunication
    presence: PresenceStore
    devices: DeviceRegistry
    memory: MemoryStore
    context_loader: ContextLoader
    tasks: TaskRuntime
    tools: ToolRegistry
    tool_router: ToolRouter
    commands: CommandRuntime
    chat: ChatRuntime

    def context(self, actor_id: str | None = None, actor_type: str = "user") -> PermissionContext:
        return PermissionContext(
            actor_id=actor_id or self.settings.default_actor_id,
            actor_type=actor_type,
        )


def create_runtime(settings: Settings | None = None) -> RuntimeContainer:
    settings = settings or Settings.from_env()
    data_dir = DataDir(settings.data_dir)
    data_dir.bootstrap()

    config = ConfigStore(data_dir.root)
    events = EventBus(data_dir.root)
    permissions = PermissionManager(data_dir.root, events)
    models = ModelRouter(config.load_system())
    agents = AgentRegistry(data_dir)
    communication = AgentCommunication(data_dir, agents, permissions, events)
    presence = PresenceStore(data_dir, events)
    devices = DeviceRegistry(data_dir, events)
    memory = MemoryStore(data_dir, permissions, events)
    tasks = TaskRuntime(data_dir, permissions, events)
    context_loader = ContextLoader(data_dir, permissions, events, agents, tasks)
    tools = ToolRegistry(permissions, events)
    register_builtin_tools(tools, data_dir, communication, tasks)
    tool_router = ToolRouter(tools, permissions, events)
    agent_runtime = AgentRuntime(agents, models, tools, tool_router, events)
    commands = CommandRuntime(config, agents, memory, tasks, tools)
    chat = ChatRuntime(data_dir, events, context_loader, agent_runtime, commands)

    events.emit("runtime.started", settings.default_actor_id, {"data_dir": str(data_dir.root)})

    return RuntimeContainer(
        settings=settings,
        data_dir=data_dir,
        config=config,
        events=events,
        permissions=permissions,
        models=models,
        agents=agents,
        agent_runtime=agent_runtime,
        communication=communication,
        presence=presence,
        devices=devices,
        memory=memory,
        context_loader=context_loader,
        tasks=tasks,
        tools=tools,
        tool_router=tool_router,
        commands=commands,
        chat=chat,
    )
