from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.registry import AgentRegistry
from synapse.approvals.manager import ApprovalManager
from synapse.approvals.resume import ApprovalResumeRuntime
from synapse.communication.runtime import CommunicationRuntime
from synapse.core.config import ConfigStore
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext
from synapse.daemon.runner import DaemonRunner
from synapse.lifecycle.runtime import LifecycleRuntime
from synapse.memory.store import MemoryStore
from synapse.notifications.runtime import NotificationRuntime
from synapse.policies.effective import EffectivePolicyRuntime
from synapse.presence.runtime import PresenceRuntime
from synapse.scheduler.runtime import SchedulerRuntime
from synapse.tasks.runtime import TaskRuntime
from synapse.tools.base import ToolRegistry
from synapse.workers.agent_worker import AgentWorker


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
        events: EventBus,
        agents: AgentRegistry,
        identities: AgentIdentityRuntime,
        policies: EffectivePolicyRuntime,
        memory: MemoryStore,
        tasks: TaskRuntime,
        tools: ToolRegistry,
        approvals: ApprovalManager,
        approval_resume: ApprovalResumeRuntime,
        worker: AgentWorker,
        scheduler: SchedulerRuntime,
        daemon: DaemonRunner,
        presence: PresenceRuntime,
        lifecycle: LifecycleRuntime,
        communication_runtime: CommunicationRuntime,
        notifications: NotificationRuntime,
    ):
        self.config = config
        self.events = events
        self.agents = agents
        self.identities = identities
        self.policies = policies
        self.memory = memory
        self.tasks = tasks
        self.tools = tools
        self.approvals = approvals
        self.approval_resume = approval_resume
        self.worker = worker
        self.scheduler = scheduler
        self.daemon = daemon
        self.presence = presence
        self.lifecycle = lifecycle
        self.communication_runtime = communication_runtime
        self.notifications = notifications

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
            return self._agents(argument_text)
        if command == "/agent":
            return self._agent(argument_text)
        if command == "/policy":
            return self._policy(context, argument_text)
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
        if command == "/inbox":
            return self._inbox(context, argument_text)
        if command == "/process-inbox":
            return self._process_inbox(context, argument_text)
        if command == "/worker-status":
            return self._worker_status()
        if command == "/jobs":
            return self._jobs(argument_text)
        if command == "/enqueue-inbox":
            return self._enqueue_inbox(context, argument_text)
        if command == "/run-jobs":
            return self._run_jobs(context)
        if command == "/cancel-job":
            return self._cancel_job(context, argument_text)
        if command == "/daemon-status":
            return self._daemon_status()
        if command == "/daemon-run-once":
            return self._daemon_run_once(context)
        if command == "/trace":
            return self._trace(argument_text)
        if command == "/presence":
            return self._presence(argument_text)
        if command == "/lifecycle":
            return self._lifecycle(argument_text)
        if command == "/wake":
            return self._wake(argument_text)
        if command == "/sleep":
            return self._sleep(argument_text)
        if command == "/check-email":
            return self._check_email(argument_text)
        if command == "/email-summary":
            return self._email_summary(argument_text)
        if command == "/email-drafts":
            return self._email_drafts(argument_text)
        if command == "/email-read":
            return self._email_read(argument_text)
        if command == "/notifications":
            return self._notifications(argument_text)
        if command == "/read-notification":
            return self._read_notification(argument_text)

        return CommandResult(command=command, status="error", output=f"Unknown command: {command}")

    def _help(self) -> CommandResult:
        commands = [
            "/help",
            "/agents",
            "/agent",
            "/policy",
            "/tasks",
            "/memory",
            "/call",
            "/task",
            "/remember",
            "/search",
            "/approvals",
            "/approve",
            "/reject",
            "/inbox",
            "/process-inbox",
            "/worker-status",
            "/jobs",
            "/enqueue-inbox",
            "/run-jobs",
            "/cancel-job",
            "/daemon-status",
            "/daemon-run-once",
            "/trace",
            "/presence",
            "/lifecycle",
            "/wake",
            "/sleep",
            "/check-email",
            "/email-summary",
            "/email-drafts",
            "/email-read",
            "/notifications",
            "/read-notification",
        ]
        return CommandResult(
            command="/help",
            status="ok",
            output="\n".join(commands),
            data={"commands": commands},
        )

    def _agents(self, argument_text: str = "") -> CommandResult:
        if argument_text.strip().lower() == "detail":
            identities = [
                agent_identity.to_dict()
                for agent_identity in [
                    self.identities.load_identity(agent.id) for agent in self.agents.list_agents()
                ]
            ]
            return CommandResult(
                command="/agents",
                status="ok",
                output=f"{len(identities)} agent identity record(s)",
                data={"agents": identities},
            )
        agents = [asdict(agent) for agent in self.agents.list_agents()]
        return CommandResult(
            command="/agents",
            status="ok",
            output=f"{len(agents)} agent(s)",
            data={"agents": agents},
        )

    def _agent(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip()
        if not agent_id:
            return CommandResult(
                command="/agent",
                status="error",
                output="Usage: /agent <id>",
            )
        identity = self.identities.load_identity(agent_id.lower())
        return CommandResult(
            command="/agent",
            status="ok",
            output=f"{identity.name}: {identity.role}",
            data={"agent": identity.to_dict()},
        )

    def _policy(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip()
        if not agent_id:
            return CommandResult(
                command="/policy",
                status="error",
                output="Usage: /policy <agent_id>",
            )
        policy = self.policies.resolve(context, agent_id.lower())
        return CommandResult(
            command="/policy",
            status="ok",
            output=f"Effective policy for {policy.agent_id}.",
            data={"policy": policy.to_dict()},
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
        approval, tool_result = self.approval_resume.approve_and_resume(context, approval_id)
        status = "resumed" if tool_result.success else "approved"
        output = (
            f"Approved and executed {approval_id}."
            if tool_result.success
            else f"Approved {approval_id}, but resume did not execute."
        )
        return CommandResult(
            command="/approve",
            status=status,
            output=output,
            data={"approval": asdict(approval), "tool_result": asdict(tool_result)},
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

    def _inbox(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/inbox",
                status="error",
                output="Usage: /inbox <agent_id>",
            )
        messages = [asdict(message) for message in self.worker.list_inbox(context, agent_id)]
        return CommandResult(
            command="/inbox",
            status="ok",
            output=f"{len(messages)} inbox message(s) for {agent_id}.",
            data={"messages": messages},
        )

    def _process_inbox(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/process-inbox",
                status="error",
                output="Usage: /process-inbox <agent_id>",
            )
        results = [asdict(result) for result in self.worker.process_inbox(context, agent_id)]
        return CommandResult(
            command="/process-inbox",
            status="ok",
            output=f"Processed {len(results)} inbox message(s) for {agent_id}.",
            data={"results": results},
        )

    def _worker_status(self) -> CommandResult:
        status = asdict(self.worker.status())
        return CommandResult(
            command="/worker-status",
            status="ok",
            output="Worker status loaded.",
            data={"worker": status},
        )

    def _jobs(self, argument_text: str = "") -> CommandResult:
        status = argument_text.strip() or None
        jobs = [asdict(job) for job in self.scheduler.list_jobs(status=status)]
        return CommandResult(
            command="/jobs",
            status="ok",
            output=f"{len(jobs)} job(s).",
            data={"jobs": jobs},
        )

    def _enqueue_inbox(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/enqueue-inbox",
                status="error",
                output="Usage: /enqueue-inbox <agent_id>",
            )
        job = self.scheduler.enqueue(
            context,
            "process_agent_inbox",
            {"agent_id": agent_id},
        )
        return CommandResult(
            command="/enqueue-inbox",
            status="ok",
            output=f"Enqueued inbox processing for {agent_id}.",
            data={"job": asdict(job)},
        )

    def _run_jobs(self, context: PermissionContext) -> CommandResult:
        jobs = [asdict(job) for job in self.scheduler.run_all_pending(context)]
        return CommandResult(
            command="/run-jobs",
            status="ok",
            output=f"Ran {len(jobs)} job(s).",
            data={"jobs": jobs},
        )

    def _cancel_job(self, context: PermissionContext, argument_text: str) -> CommandResult:
        job_id = argument_text.strip()
        if not job_id:
            return CommandResult(
                command="/cancel-job",
                status="error",
                output="Usage: /cancel-job <job_id>",
            )
        job = self.scheduler.cancel_job(context, job_id)
        return CommandResult(
            command="/cancel-job",
            status="ok",
            output=f"Cancelled job {job_id}.",
            data={"job": asdict(job)},
        )

    def _daemon_status(self) -> CommandResult:
        status = asdict(self.daemon.status())
        return CommandResult(
            command="/daemon-status",
            status="ok",
            output="Daemon status loaded.",
            data={"daemon": status},
        )

    def _daemon_run_once(self, context: PermissionContext) -> CommandResult:
        status = self.daemon.run_once(context)
        return CommandResult(
            command="/daemon-run-once",
            status="ok",
            output=f"Daemon tick completed with {len(status.last_jobs_run)} job(s).",
            data={"daemon": asdict(status)},
        )

    def _trace(self, correlation_id: str) -> CommandResult:
        correlation_id = correlation_id.strip()
        if not correlation_id:
            return CommandResult(
                command="/trace",
                status="error",
                output="Usage: /trace <correlation_id>",
            )
        events = [asdict(event) for event in self.events.trace(correlation_id)]
        records = self.events.trace_records(correlation_id)
        return CommandResult(
            command="/trace",
            status="ok",
            output=(
                f"{len(events)} event(s), {len(records)} durable record(s) "
                f"for correlation {correlation_id}."
            ),
            data={"events": events, "records": records},
        )

    def _presence(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if agent_id:
            presence = self.presence.get(agent_id)
            return CommandResult(
                command="/presence",
                status="ok",
                output=f"Presence for {agent_id}: {presence.state}",
                data={"presence": asdict(presence)},
            )
        presences = [asdict(presence) for presence in self.presence.list_all()]
        return CommandResult(
            command="/presence",
            status="ok",
            output=f"{len(presences)} presence record(s).",
            data={"presence": presences},
        )

    def _lifecycle(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if agent_id:
            lifecycle = self.lifecycle.get(agent_id)
            return CommandResult(
                command="/lifecycle",
                status="ok",
                output=f"Lifecycle for {agent_id}: {lifecycle.state}",
                data={"lifecycle": asdict(lifecycle)},
            )
        lifecycles = [asdict(lifecycle) for lifecycle in self.lifecycle.list_all()]
        return CommandResult(
            command="/lifecycle",
            status="ok",
            output=f"{len(lifecycles)} lifecycle record(s).",
            data={"lifecycle": lifecycles},
        )

    def _wake(self, argument_text: str) -> CommandResult:
        agent_id, _, reason = argument_text.strip().partition(" ")
        if not agent_id:
            return CommandResult(
                command="/wake",
                status="error",
                output="Usage: /wake <agent_id>",
            )
        lifecycle = self.lifecycle.wake(agent_id.lower(), reason.strip() or "command wake")
        return CommandResult(
            command="/wake",
            status="ok",
            output=f"Woke {agent_id.lower()}.",
            data={"lifecycle": asdict(lifecycle)},
        )

    def _sleep(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/sleep",
                status="error",
                output="Usage: /sleep <agent_id>",
            )
        lifecycle = self.lifecycle.sleep(agent_id)
        return CommandResult(
            command="/sleep",
            status="ok",
            output=f"Put {agent_id} into idle lifecycle state.",
            data={"lifecycle": asdict(lifecycle)},
        )

    def _check_email(self, argument_text: str) -> CommandResult:
        provider = argument_text.strip() or "mock"
        briefing = self.communication_runtime.generate_briefing(
            agent_id="hermes",
            provider=provider,
        )
        return CommandResult(
            command="/check-email",
            status="ok",
            output=briefing.summary,
            data={"briefing": asdict(briefing)},
        )

    def _email_summary(self, argument_text: str) -> CommandResult:
        provider = argument_text.strip() or "mock"
        summary = self.communication_runtime.daily_summary(provider=provider)
        return CommandResult(
            command="/email-summary",
            status="ok",
            output=str(summary["summary"]),
            data={"summary": summary},
        )

    def _email_drafts(self, argument_text: str) -> CommandResult:
        provider = argument_text.strip() or "mock"
        drafts = [
            asdict(draft)
            for draft in self.communication_runtime.list_drafts(provider=provider)
        ]
        return CommandResult(
            command="/email-drafts",
            status="ok",
            output=f"{len(drafts)} email draft(s).",
            data={"drafts": drafts},
        )

    def _email_read(self, argument_text: str) -> CommandResult:
        message_id = argument_text.strip()
        if not message_id:
            return CommandResult(
                command="/email-read",
                status="error",
                output="Usage: /email-read <id>",
            )
        message = self.communication_runtime.read_message(message_id=message_id)
        return CommandResult(
            command="/email-read",
            status="ok",
            output=message.subject,
            data={"message": asdict(message)},
        )

    def _notifications(self, argument_text: str) -> CommandResult:
        argument = argument_text.strip().lower()
        if argument == "cleanup":
            result = self.notifications.cleanup_notifications()
            return CommandResult(
                command="/notifications",
                status="ok",
                output=f"Notification cleanup deleted {result.deleted} notification(s).",
                data={"cleanup": asdict(result)},
            )
        unread_only = argument == "unread"
        notifications = (
            self.notifications.list_unread()
            if unread_only
            else self.notifications.list_notifications()
        )
        payload = [asdict(notification) for notification in notifications]
        return CommandResult(
            command="/notifications",
            status="ok",
            output=f"{len(payload)} notification(s).",
            data={"notifications": payload},
        )

    def _read_notification(self, notification_id: str) -> CommandResult:
        notification_id = notification_id.strip()
        if not notification_id:
            return CommandResult(
                command="/read-notification",
                status="error",
                output="Usage: /read-notification <id>",
            )
        notification = self.notifications.mark_read(notification_id)
        return CommandResult(
            command="/read-notification",
            status="ok",
            output=f"Notification read: {notification.title}",
            data={"notification": asdict(notification)},
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
