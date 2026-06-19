from __future__ import annotations

from dataclasses import dataclass

from synapse.agents.communication import AgentCommunication
from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.registry import AgentRegistry
from synapse.agents.runtime import AgentRuntime
from synapse.approvals.manager import ApprovalManager
from synapse.approvals.resume import ApprovalResumeRuntime
from synapse.auth.devices import DeviceRegistry
from synapse.chat.runtime import ChatRuntime
from synapse.commands.runtime import CommandRuntime
from synapse.context.loader import ContextLoader
from synapse.core.config import ConfigStore, Settings
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.model_router import ModelRouter
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.daemon.runner import DaemonRunner
from synapse.daemon.status import DaemonStatusStore
from synapse.memory.store import MemoryStore
from synapse.policies.effective import EffectivePolicyRuntime
from synapse.presence.runtime import PresenceRuntime
from synapse.scheduler.queue import JobQueue
from synapse.scheduler.runtime import SchedulerRuntime
from synapse.tasks.runtime import TaskRuntime
from synapse.tools.base import ToolRegistry
from synapse.tools.builtin import register_builtin_tools
from synapse.tools.router import ToolRouter
from synapse.workers.agent_worker import AgentWorker


@dataclass
class RuntimeContainer:
    settings: Settings
    data_dir: DataDir
    config: ConfigStore
    events: EventBus
    permissions: PermissionManager
    models: ModelRouter
    agents: AgentRegistry
    identities: AgentIdentityRuntime
    agent_runtime: AgentRuntime
    communication: AgentCommunication
    presence: PresenceRuntime
    devices: DeviceRegistry
    approvals: ApprovalManager
    approval_resume: ApprovalResumeRuntime
    policies: EffectivePolicyRuntime
    memory: MemoryStore
    context_loader: ContextLoader
    tasks: TaskRuntime
    tools: ToolRegistry
    tool_router: ToolRouter
    worker: AgentWorker
    scheduler: SchedulerRuntime
    daemon: DaemonRunner
    commands: CommandRuntime
    chat: ChatRuntime

    def context(
        self,
        actor_id: str | None = None,
        actor_type: str = "user",
        device_id: str | None = None,
    ) -> PermissionContext:
        return PermissionContext(
            actor_id=actor_id or self.settings.default_actor_id,
            actor_type=actor_type,
            device_id=device_id,
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
    identities = AgentIdentityRuntime(data_dir)
    communication = AgentCommunication(data_dir, agents, permissions, events)
    presence = PresenceRuntime(data_dir, events)
    devices = DeviceRegistry(data_dir, events)
    approvals = ApprovalManager(data_dir, permissions, devices, events)
    memory = MemoryStore(data_dir, permissions, events)
    tasks = TaskRuntime(data_dir, permissions, events)
    tools = ToolRegistry(permissions, events)
    register_builtin_tools(tools, data_dir, communication, tasks)
    policies = EffectivePolicyRuntime(agents, identities, tools, permissions, approvals, devices)
    context_loader = ContextLoader(data_dir, permissions, events, agents, identities, policies, tasks)
    tool_router = ToolRouter(tools, permissions, approvals, events, presence)
    agent_runtime = AgentRuntime(agents, policies, models, tool_router, events, presence)
    worker = AgentWorker(communication, context_loader, agent_runtime, policies, events, presence)
    job_queue = JobQueue(data_dir)
    scheduler = SchedulerRuntime(job_queue, worker, events, presence)
    daemon = DaemonRunner(scheduler, DaemonStatusStore(data_dir), events)
    approval_resume = ApprovalResumeRuntime(approvals, tool_router, policies)
    commands = CommandRuntime(
        config,
        events,
        agents,
        identities,
        policies,
        memory,
        tasks,
        tools,
        approvals,
        approval_resume,
        worker,
        scheduler,
        daemon,
        presence,
    )
    chat = ChatRuntime(data_dir, events, context_loader, agent_runtime, commands, presence)

    events.emit("runtime.started", settings.default_actor_id, {"data_dir": str(data_dir.root)})

    return RuntimeContainer(
        settings=settings,
        data_dir=data_dir,
        config=config,
        events=events,
        permissions=permissions,
        models=models,
        agents=agents,
        identities=identities,
        agent_runtime=agent_runtime,
        communication=communication,
        presence=presence,
        devices=devices,
        approvals=approvals,
        approval_resume=approval_resume,
        policies=policies,
        memory=memory,
        context_loader=context_loader,
        tasks=tasks,
        tools=tools,
        tool_router=tool_router,
        worker=worker,
        scheduler=scheduler,
        daemon=daemon,
        commands=commands,
        chat=chat,
    )
