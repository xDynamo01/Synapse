from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.agents.registry import AgentRegistry
from synapse.approvals.manager import ApprovalManager
from synapse.core.config import ConfigStore
from synapse.core.permissions import PermissionContext
from synapse.memory.store import MemoryStore
from synapse.tasks.runtime import TaskRuntime
from synapse.tools.base import ToolRegistry


@dataclass(frozen=True)
class CommandResult:
    command: str
    status: str
    output: str
    data: dict[str, Any] = field(default_factory=dict)


class CommandRuntime:
    def __init__(
        self,
        config: ConfigStore,
        agents: AgentRegistry,
        memory: MemoryStore,
        tasks: TaskRuntime,
        tools: ToolRegistry,
        approvals: ApprovalManager,
    ):
        self.config = config
        self.agents = agents
        self.memory = memory
        self.tasks = tasks
        self.tools = tools
        self.approvals = approvals

    def execute(
        self,
        context: PermissionContext,
        text: str,
        source_agent_id: str | None = None,
    ) -> CommandResult:
        command_line = text.strip()
        if not command_line.startswith("/"):
            return CommandResult(
                command="message",
                status="error",
                output="Command Runtime only handles slash commands.",
            )

        command, _, rest = command_line.partition(" ")
        command = command.lower()
        argument_text = rest.strip()

        if command == "/help":
            return self._help()
        if command == "/agents":
            return self._agents()
        if command == "/tasks":
            return self._tasks()
        if command == "/memory":
            return self._memory(context)
        if command == "/call":
            return self._call(context, argument_text, source_agent_id)
        if command == "/task":
            return self._task(context, argument_text)
        if command == "/remember":
            return self._remember(context, argument_text)
        if command == "/search":
            return self._search(context, argument_text)
        if command == "/approvals":
            return self._approvals()
        if command == "/approve":
            return self._approve(context, argument_text)
        if command == "/reject":
            return self._reject(context, argument_text)

        return CommandResult(command=command, status="error", output=f"Unknown command: {command}")

    def _help(self) -> CommandResult:
        commands = [
            "/help",
            "/agents",
            "/tasks",
            "/memory",
            "/call",
            "/task",
            "/remember",
            "/search",
            "/approvals",
            "/approve",
            "/reject",
        ]
        return CommandResult(
            command="/help",
            status="ok",
            output="\n".join(commands),
            data={"commands": commands},
        )

    def _agents(self) -> CommandResult:
        agents = [asdict(agent) for agent in self.agents.list_agents()]
        return CommandResult(
            command="/agents",
            status="ok",
            output=f"{len(agents)} agent(s)",
            data={"agents": agents},
        )

    def _tasks(self) -> CommandResult:
        tasks = [asdict(task) for task in self.tasks.list_tasks()]
        return CommandResult(
            command="/tasks",
            status="ok",
            output=f"{len(tasks)} task(s)",
            data={"tasks": tasks},
        )

    def _memory(self, context: PermissionContext) -> CommandResult:
        files = {
            "SYSTEM.md": self.memory.read_global(context, "SYSTEM.md"),
            "USER.md": self.memory.read_global(context, "USER.md"),
            "MEMORY.md": self.memory.read_global(context, "MEMORY.md"),
        }
        return CommandResult(
            command="/memory",
            status="ok",
            output="Loaded global memory files.",
            data={"memory": files},
        )

    def _call(
        self,
        context: PermissionContext,
        argument_text: str,
        source_agent_id: str | None,
    ) -> CommandResult:
        to_agent_id, _, body = argument_text.partition(" ")
        if not to_agent_id or not body.strip():
            return CommandResult(
                command="/call",
                status="error",
                output="Usage: /call <agent> <message>",
            )

        from_agent_id = source_agent_id or self._default_agent_id()
        message = self.tools.execute(
            "send_agent_message",
            context,
            {
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
                "subject": "Command Runtime call",
                "body": body.strip(),
            },
        )
        return CommandResult(
            command="/call",
            status="ok",
            output=f"Message sent to {to_agent_id}.",
            data={"message": message},
        )

    def _task(self, context: PermissionContext, argument_text: str) -> CommandResult:
        title, agent_id = self._parse_task_arguments(argument_text)
        if not title:
            return CommandResult(
                command="/task",
                status="error",
                output="Usage: /task <title> --agent <agent>",
            )

        metadata: dict[str, str] = {}
        if agent_id:
            metadata["agent_id"] = agent_id
            metadata["assigned_agent"] = agent_id

        task = self.tools.execute(
            "create_task",
            context,
            {
                "title": title,
                "description": "",
                "metadata": metadata,
            },
        )
        return CommandResult(
            command="/task",
            status="ok",
            output=f"Task created: {title}",
            data={"task": task},
        )

    def _remember(self, context: PermissionContext, text: str) -> CommandResult:
        if not text:
            return CommandResult(
                command="/remember",
                status="error",
                output="Usage: /remember <text>",
            )
        self.memory.append_global(context, "MEMORY.md", text)
        return CommandResult(
            command="/remember",
            status="ok",
            output="Saved to global memory.",
            data={"file": "MEMORY.md"},
        )

    def _search(self, context: PermissionContext, query: str) -> CommandResult:
        if not query:
            return CommandResult(
                command="/search",
                status="error",
                output="Usage: /search <query>",
            )
        result = self.tools.execute("web_search", context, {"query": query})
        status = "not_implemented" if result.get("status") == "unconfigured" else "ok"
        return CommandResult(
            command="/search",
            status=status,
            output=result.get("message", "Search executed."),
            data={"search": result},
        )

    def _approvals(self) -> CommandResult:
        pending = [asdict(approval) for approval in self.approvals.list_pending()]
        return CommandResult(
            command="/approvals",
            status="ok",
            output=f"{len(pending)} pending approval(s)",
            data={"approvals": pending},
        )

    def _approve(self, context: PermissionContext, approval_id: str) -> CommandResult:
        if not approval_id:
            return CommandResult(
                command="/approve",
                status="error",
                output="Usage: /approve <approval_id>",
            )
        approval = self.approvals.approve(context, approval_id)
        return CommandResult(
            command="/approve",
            status="ok",
            output=f"Approved {approval_id}.",
            data={"approval": asdict(approval)},
        )

    def _reject(self, context: PermissionContext, approval_id: str) -> CommandResult:
        if not approval_id:
            return CommandResult(
                command="/reject",
                status="error",
                output="Usage: /reject <approval_id>",
            )
        approval = self.approvals.reject(context, approval_id)
        return CommandResult(
            command="/reject",
            status="ok",
            output=f"Rejected {approval_id}.",
            data={"approval": asdict(approval)},
        )

    def _default_agent_id(self) -> str:
        system = self.config.load_system().get("system", {})
        return str(system.get("default_agent_id", "orchestrator"))

    @staticmethod
    def _parse_task_arguments(argument_text: str) -> tuple[str, str | None]:
        marker = " --agent "
        if marker not in argument_text:
            return argument_text.strip(), None
        title, _, agent_id = argument_text.partition(marker)
        return title.strip(), agent_id.strip() or None
