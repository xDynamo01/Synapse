from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.agents.communication import AgentCommunication
from synapse.agents.models import AgentMessage
from synapse.agents.runtime import AgentRuntime
from synapse.context.loader import ContextLoader
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext
from synapse.policies.effective import EffectivePolicyRuntime
from synapse.presence.runtime import PresenceRuntime


@dataclass(frozen=True)
class InboxProcessResult:
    agent_id: str
    message_id: str
    status: str
    response: str | None = None
    reply: dict[str, Any] | None = None
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class WorkerStatus:
    agents_checked: int = 0
    messages_processed: int = 0
    messages_failed: int = 0
    last_agent_id: str | None = None
    last_error: str | None = None


class AgentWorker:
    def __init__(
        self,
        communication: AgentCommunication,
        context_loader: ContextLoader,
        agent_runtime: AgentRuntime,
        policies: EffectivePolicyRuntime,
        event_bus: EventBus,
        presence: PresenceRuntime | None = None,
    ):
        self.communication = communication
        self.context_loader = context_loader
        self.agent_runtime = agent_runtime
        self.policies = policies
        self.event_bus = event_bus
        self.presence = presence
        self._status = WorkerStatus()

    def list_inbox(
        self,
        context: PermissionContext,
        agent_id: str,
        status: str | None = None,
    ) -> list[AgentMessage]:
        worker_context = self._agent_context(context, agent_id)
        return self.communication.list_messages(worker_context, agent_id, status=status)

    def process_inbox(
        self,
        context: PermissionContext,
        agent_id: str,
        limit: int | None = None,
    ) -> list[InboxProcessResult]:
        worker_context = self._agent_context(context, agent_id)
        pending = self.communication.list_messages(worker_context, agent_id, status="pending")
        if limit is not None:
            pending = pending[:limit]
        self._set_presence(agent_id, "working", "Checking inbox", actor_id=worker_context.actor_id)
        self.event_bus.emit(
            "worker.inbox_checked",
            worker_context.actor_id,
            {"agent_id": agent_id, "pending": len(pending), "limit": limit},
        )

        results = [self._process_message(context, agent_id, message) for message in pending]
        failures = len([item for item in results if item.status == "failed"])
        if failures:
            self._set_presence(
                agent_id,
                "error",
                f"{failures} inbox message(s) failed",
                actor_id=worker_context.actor_id,
            )
        else:
            self._set_presence(
                agent_id,
                "idle",
                "Inbox processing completed",
                actor_id=worker_context.actor_id,
            )
        self._status = WorkerStatus(
            agents_checked=self._status.agents_checked + 1,
            messages_processed=self._status.messages_processed
            + len([item for item in results if item.status == "processed"]),
            messages_failed=self._status.messages_failed + failures,
            last_agent_id=agent_id,
            last_error=next((item.error for item in results if item.error), None),
        )
        return results

    def status(self) -> WorkerStatus:
        return self._status

    def _process_message(
        self,
        caller_context: PermissionContext,
        agent_id: str,
        message: AgentMessage,
    ) -> InboxProcessResult:
        worker_context = self._agent_context(caller_context, agent_id)
        self._set_presence(
            agent_id,
            "working",
            f"Processing message {message.id}",
            actor_id=worker_context.actor_id,
        )
        self.event_bus.emit(
            "worker.message_processing_started",
            worker_context.actor_id,
            {"agent_id": agent_id, "message_id": message.id, "from_agent": message.from_agent},
        )
        try:
            self.communication.mark_read(worker_context, agent_id, message.id)
            loaded_context = self.context_loader.load(
                worker_context,
                agent_id,
                history=[
                    {
                        "role": "agent_message",
                        "content": self._message_prompt(message),
                    }
                ],
            )
            agent_result = self.agent_runtime.run(
                context=worker_context,
                agent_id=agent_id,
                loaded_context=loaded_context,
                user_message=message.body,
                original_message_id=message.id,
            )
            reply = self._reply_if_allowed(worker_context, agent_id, message, agent_result.response)
            self.communication.mark_processed(worker_context, agent_id, message.id)
            result = InboxProcessResult(
                agent_id=agent_id,
                message_id=message.id,
                status="processed",
                response=agent_result.response,
                reply=asdict(reply) if reply else None,
                tool_results=[asdict(tool_result) for tool_result in agent_result.tool_results],
            )
            self.event_bus.emit("worker.message_processed", worker_context.actor_id, asdict(result))
            return result
        except Exception as exc:
            self.communication.mark_failed(worker_context, agent_id, message.id)
            self._set_presence(
                agent_id,
                "error",
                f"Failed processing message {message.id}",
                actor_id=worker_context.actor_id,
            )
            result = InboxProcessResult(
                agent_id=agent_id,
                message_id=message.id,
                status="failed",
                error=str(exc) or type(exc).__name__,
            )
            self.event_bus.emit("worker.message_failed", worker_context.actor_id, asdict(result))
            return result

    def _reply_if_allowed(
        self,
        context: PermissionContext,
        agent_id: str,
        message: AgentMessage,
        response: str,
    ) -> AgentMessage | None:
        if not response.strip() or message.from_agent == agent_id:
            return None
        policy = self.policies.resolve(context, agent_id)
        can_send = "send_agent_message" in set(policy.allowed_tools)
        explicitly_prefers_messages = "send_agent_message" in set(policy.preferred_tools)
        if not can_send or not (policy.can_delegate or explicitly_prefers_messages):
            return None
        return self.communication.send_agent_message(
            context=context,
            from_agent_id=agent_id,
            to_agent_id=message.from_agent,
            subject=f"Re: {message.subject}",
            body=response,
            task_id=message.task_id,
        )

    @staticmethod
    def _agent_context(context: PermissionContext, agent_id: str) -> PermissionContext:
        return PermissionContext(
            actor_id=agent_id,
            actor_type="agent",
            device_id=context.device_id,
            autonomy="worker",
        )

    @staticmethod
    def _message_prompt(message: AgentMessage) -> str:
        return (
            f"From: {message.from_agent}\n"
            f"Subject: {message.subject}\n"
            f"Task: {message.task_id or ''}\n\n"
            f"{message.body}"
        )

    def _set_presence(
        self,
        agent_id: str,
        state: str,
        activity: str,
        actor_id: str | None = None,
    ) -> None:
        if not self.presence:
            return
        self.presence.set_state(
            agent_id,
            state,
            activity,
            {"actor_id": actor_id or agent_id},
        )
