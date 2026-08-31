from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, cast

from synapse.agents.admin import AgentAdminRuntime
from synapse.agents.communication import AgentCommunication
from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.models import AgentMessage
from synapse.agents.runtime import AgentRuntime
from synapse.context.loader import ContextLoader
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import load_structured_file
from synapse.delegation.autonomy_policy import DelegationAutonomyPolicyRuntime
from synapse.delegation.models import DelegationCompletionSignal, DelegationTask
from synapse.delegation.runtime import DelegationRuntime
from synapse.delegation.scheduling_policy import DelegationSchedulingPolicyRuntime
from synapse.delegation_execution.runtime import DelegationExecutionRuntime
from synapse.delegation_inbox.runtime import DelegationInboxRuntime
from synapse.lifecycle.runtime import LifecycleRuntime
from synapse.policies.effective import EffectivePolicyRuntime
from synapse.presence.runtime import PresenceRuntime

if TYPE_CHECKING:
    from synapse.context_fusion.runtime import ContextFusionRuntime


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
class DelegationProcessResult:
    agent_id: str
    task_id: str
    status: str
    action: str
    response: str | None = None
    message: dict[str, Any] | None = None
    completion_signal: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
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
        lifecycle: LifecycleRuntime | None = None,
        admin: AgentAdminRuntime | None = None,
        delegation: DelegationRuntime | None = None,
        delegation_inbox: DelegationInboxRuntime | None = None,
        delegation_scheduling: DelegationSchedulingPolicyRuntime | None = None,
        delegation_autonomy: DelegationAutonomyPolicyRuntime | None = None,
        delegation_execution: DelegationExecutionRuntime | None = None,
        identities: AgentIdentityRuntime | None = None,
        context_fusion: ContextFusionRuntime | None = None,
    ):
        self.communication = communication
        self.context_loader = context_loader
        self.agent_runtime = agent_runtime
        self.policies = policies
        self.event_bus = event_bus
        self.presence = presence
        self.lifecycle = lifecycle
        self.admin = admin
        self.delegation = delegation
        self.delegation_inbox = delegation_inbox
        self.delegation_scheduling = delegation_scheduling
        self.delegation_autonomy = delegation_autonomy
        self.delegation_execution = delegation_execution
        self.identities = identities
        self.context_fusion = context_fusion
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
        if self.admin:
            self.admin.assert_agent_runnable(agent_id)
        worker_context = self._agent_context(context, agent_id)
        pending = self.communication.list_messages(worker_context, agent_id, status="pending")
        if limit is not None:
            pending = pending[:limit]
        if (
            pending
            and self.lifecycle
            and self.lifecycle.get(agent_id).state not in {"waking", "working"}
        ):
            self.lifecycle.wake(agent_id, "pending inbox messages")
        self._set_presence(agent_id, "working", "Checking inbox", actor_id=worker_context.actor_id)
        self.event_bus.emit(
            "worker.inbox_checked",
            worker_context.actor_id,
            {"agent_id": agent_id, "pending": len(pending), "limit": limit},
        )

        results = [self._process_message(context, agent_id, message) for message in pending]
        failures = len([item for item in results if item.status == "failed"])
        if failures:
            if self.lifecycle:
                self.lifecycle.error(agent_id, f"{failures} inbox message(s) failed")
            self._set_presence(
                agent_id,
                "error",
                f"{failures} inbox message(s) failed",
                actor_id=worker_context.actor_id,
            )
        else:
            if self.lifecycle:
                self.lifecycle.sleep(agent_id)
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

    def multimodal_context_policy(self) -> dict[str, Any]:
        default = {
            "enabled": True,
            "include_for_conversations": True,
            "include_for_missions": True,
            "include_for_sessions": True,
            "max_signals_per_context": 50,
            "attach_health_summary": True,
            "attach_readiness_summary": True,
        }
        if not self.context_fusion:
            return default
        raw = load_structured_file(
            self.context_loader.data_dir.resolve("config/multimodal_context_policy.yaml")
        )
        policy = dict(default)
        policy.update(raw.get("multimodal_context", raw))
        return policy

    def preview_context(
        self,
        context: PermissionContext,
        agent_id: str,
        conversation_id: str,
    ) -> dict[str, Any]:
        worker_context = self._agent_context(context, agent_id)
        conversation_context = self._load_conversation_context(
            worker_context,
            conversation_id,
            message_id="preview",
        )
        multimodal_context = self._build_multimodal_context(
            worker_context,
            agent_id=agent_id,
            conversation_id=conversation_id,
            mission_id=self._mission_id_for_conversation(conversation_id),
            multimodal_session_id=self._multimodal_session_id_for_conversation(conversation_id),
            correlation_id=None,
            causation_id=None,
            source="preview",
        )
        return self.context_loader.load(
            worker_context,
            agent_id,
            conversation_context=conversation_context,
            multimodal_context=multimodal_context,
        ).to_dict()

    def process_delegations(
        self,
        context: PermissionContext,
        agent_id: str,
        limit: int = 1,
    ) -> list[DelegationProcessResult]:
        if self.admin:
            self.admin.assert_agent_runnable(agent_id)
        if not self.delegation:
            return []
        worker_context = self._agent_context(context, agent_id)
        normalized_agent_id = agent_id.lower()
        if self.delegation_inbox:
            active_entries = self.delegation_inbox.get_active_tasks(normalized_agent_id)
            assigned = [self.delegation.get_task(entry.task_id) for entry in active_entries]
        else:
            assigned = [
                task
                for task in self.delegation.list_tasks()
                if task.assignee_agent_id == normalized_agent_id
                and task.status in {"pending", "accepted", "in_progress"}
            ]
        assigned = self._order_delegations(worker_context, normalized_agent_id, assigned)[:limit]
        return [self._process_delegation(worker_context, task) for task in assigned]

    def process_next_delegation(
        self,
        context: PermissionContext,
        agent_id: str,
    ) -> DelegationProcessResult | None:
        results = self.process_delegations(context, agent_id, limit=1)
        return results[0] if results else None

    def _order_delegations(
        self,
        context: PermissionContext,
        agent_id: str,
        tasks: list[DelegationTask],
    ) -> list[DelegationTask]:
        if not self.delegation_scheduling:
            return tasks
        try:
            return self.delegation_scheduling.sort_tasks(tasks)
        except Exception as exc:
            self.event_bus.emit(
                "delegation.scheduling.failed",
                context.actor_id,
                {
                    "agent_id": agent_id,
                    "error": str(exc) or type(exc).__name__,
                    "fallback": "original_order",
                },
            )
            return tasks

    def _process_delegation(
        self,
        context: PermissionContext,
        task: DelegationTask,
    ) -> DelegationProcessResult:
        delegation = cast("DelegationRuntime", self.delegation)
        self.event_bus.emit(
            "worker.delegation.loaded",
            context.actor_id,
            {"agent_id": task.assignee_agent_id, "task_id": task.task_id, "status": task.status},
        )
        try:
            if task.status == "pending":
                decision = self._delegation_autonomy_decision(context, task, "accept")
                if decision and decision.requires_approval:
                    self.event_bus.emit(
                        "worker.delegation.autonomy_requires_approval",
                        context.actor_id,
                        {
                            "agent_id": task.assignee_agent_id,
                            "task_id": task.task_id,
                            "action": "accept",
                            "decision": decision.to_dict(),
                        },
                    )
                    return DelegationProcessResult(
                        agent_id=task.assignee_agent_id,
                        task_id=task.task_id,
                        status=task.status,
                        action="autonomy_requires_approval",
                    )
                if decision and not decision.allowed:
                    self.event_bus.emit(
                        "worker.delegation.acceptance_skipped",
                        context.actor_id,
                        {
                            "agent_id": task.assignee_agent_id,
                            "task_id": task.task_id,
                            "reason": "; ".join(decision.blocked_reasons),
                            "decision": decision.to_dict(),
                        },
                    )
                    return DelegationProcessResult(
                        agent_id=task.assignee_agent_id,
                        task_id=task.task_id,
                        status=task.status,
                        action="skipped_pending",
                    )
                accepted = delegation.accept_task(context, task.task_id)
                self.event_bus.emit(
                    "worker.delegation.accepted", context.actor_id, asdict(accepted)
                )
                return DelegationProcessResult(
                    agent_id=task.assignee_agent_id,
                    task_id=task.task_id,
                    status=accepted.status,
                    action="accepted",
                )
            if task.status == "accepted":
                decision = self._delegation_autonomy_decision(context, task, "start")
                if decision and decision.requires_approval:
                    self.event_bus.emit(
                        "worker.delegation.autonomy_requires_approval",
                        context.actor_id,
                        {
                            "agent_id": task.assignee_agent_id,
                            "task_id": task.task_id,
                            "action": "start",
                            "decision": decision.to_dict(),
                        },
                    )
                    return DelegationProcessResult(
                        agent_id=task.assignee_agent_id,
                        task_id=task.task_id,
                        status=task.status,
                        action="autonomy_requires_approval",
                    )
                if decision and not decision.allowed:
                    self.event_bus.emit(
                        "worker.delegation.autonomy_blocked",
                        context.actor_id,
                        {
                            "agent_id": task.assignee_agent_id,
                            "task_id": task.task_id,
                            "action": "start",
                            "decision": decision.to_dict(),
                        },
                    )
                    return DelegationProcessResult(
                        agent_id=task.assignee_agent_id,
                        task_id=task.task_id,
                        status=task.status,
                        action="autonomy_blocked",
                    )
                started = delegation.start_task(context, task.task_id)
                self.event_bus.emit("worker.delegation.started", context.actor_id, asdict(started))
                return DelegationProcessResult(
                    agent_id=task.assignee_agent_id,
                    task_id=task.task_id,
                    status=started.status,
                    action="started",
                )
            if task.status == "in_progress":
                return self._run_delegation(context, task)
            return DelegationProcessResult(
                agent_id=task.assignee_agent_id,
                task_id=task.task_id,
                status=task.status,
                action="ignored",
            )
        except Exception as exc:
            self.event_bus.emit(
                "worker.delegation.failed",
                context.actor_id,
                {
                    "agent_id": task.assignee_agent_id,
                    "task_id": task.task_id,
                    "error": str(exc) or type(exc).__name__,
                },
            )
            return DelegationProcessResult(
                agent_id=task.assignee_agent_id,
                task_id=task.task_id,
                status="failed",
                action="failed",
                error=str(exc) or type(exc).__name__,
            )

    def _delegation_autonomy_decision(
        self,
        context: PermissionContext,
        task: DelegationTask,
        action: str,
    ):
        if not self.delegation_autonomy or not self.identities:
            return None
        identity = self.identities.load_identity(task.assignee_agent_id)
        effective_policy = self.policies.resolve(context, task.assignee_agent_id)
        if action == "accept":
            return self.delegation_autonomy.evaluate_accept(task, identity, effective_policy)
        if action == "start":
            return self.delegation_autonomy.evaluate_start(task, identity, effective_policy)
        if action == "reject":
            return self.delegation_autonomy.evaluate_reject(task, identity, effective_policy)
        return None

    def _run_delegation(
        self,
        context: PermissionContext,
        task: DelegationTask,
    ) -> DelegationProcessResult:
        execution = None
        if self.delegation_execution:
            execution = self.delegation_execution.start_execution(
                self.delegation_execution.create_execution(task.task_id).execution_id
            )
        conversation_context = None
        if task.conversation_id and self.context_fusion:
            conversation_context = asdict(
                self.context_fusion.build_context(
                    conversation_id=task.conversation_id,
                    agent_id=task.assignee_agent_id,
                    mission_id=task.mission_id,
                    permission_context=context,
                )
            )
        delegation_context = {
            "task_id": task.task_id,
            "title": task.title,
            "description": task.description,
            "requester_agent_id": task.requester_agent_id,
            "assignee_agent_id": task.assignee_agent_id,
            "priority": task.priority,
            "status": task.status,
            "conversation_id": task.conversation_id,
            "conversation_context": conversation_context,
            "correlation_id": task.correlation_id,
            "causation_id": task.causation_id,
        }
        multimodal_context = self._build_multimodal_context(
            context,
            agent_id=task.assignee_agent_id,
            conversation_id=task.conversation_id,
            mission_id=task.mission_id,
            multimodal_session_id=self._multimodal_session_id_for_task(task),
            correlation_id=task.correlation_id,
            causation_id=task.causation_id,
            source="delegation",
        )
        loaded_context = self.context_loader.load(
            context,
            task.assignee_agent_id,
            history=[
                {
                    "role": "delegation",
                    "content": f"{task.title}\n\n{task.description}",
                }
            ],
            conversation_context=conversation_context,
            delegation_context=delegation_context,
            multimodal_context=multimodal_context,
        )
        try:
            agent_result = self.agent_runtime.run(
                context=context,
                agent_id=task.assignee_agent_id,
                loaded_context=loaded_context,
                user_message=task.description or task.title,
                original_message_id=task.task_id,
            )
        except Exception as exc:
            if execution and self.delegation_execution:
                self.delegation_execution.fail_execution(
                    execution.execution_id,
                    error_message=str(exc) or type(exc).__name__,
                )
            raise
        completion_signal = self._completion_signal_from_response(
            context,
            task,
            agent_result.response,
        )
        message = None
        if task.conversation_id:
            message = self.communication.send_agent_message(
                context=context,
                from_agent_id=task.assignee_agent_id,
                to_agent_id=task.requester_agent_id,
                subject=f"Delegation response: {task.title}",
                body=agent_result.response,
                conversation_id=task.conversation_id,
                correlation_id=task.correlation_id,
                causation_id=task.task_id,
            )
            self.event_bus.emit(
                "worker.delegation.response_created",
                context.actor_id,
                {
                    "task_id": task.task_id,
                    "conversation_id": task.conversation_id,
                    "message_id": message.id,
                },
            )
        return DelegationProcessResult(
            agent_id=task.assignee_agent_id,
            task_id=task.task_id,
            status=task.status,
            action="responded",
            response=agent_result.response,
            message=asdict(message) if message else None,
            completion_signal=asdict(completion_signal) if completion_signal else None,
            execution=asdict(execution) if execution else None,
        )

    def _completion_signal_from_response(
        self,
        context: PermissionContext,
        task: DelegationTask,
        response: str,
    ) -> DelegationCompletionSignal | None:
        if not self.delegation:
            return None
        payload = self._extract_json_object(response)
        if not isinstance(payload, dict):
            return None
        raw_signal = payload.get("delegation_completion")
        if not isinstance(raw_signal, dict):
            return None
        if raw_signal.get("task_id") and raw_signal.get("task_id") != task.task_id:
            self.event_bus.emit(
                "worker.delegation.completion_ignored",
                context.actor_id,
                {
                    "task_id": task.task_id,
                    "provided_task_id": raw_signal.get("task_id"),
                    "reason": "task_id_mismatch",
                },
            )
            return None
        status = str(raw_signal.get("status") or "").strip()
        summary = str(raw_signal.get("summary") or "").strip()
        return self.delegation.submit_completion_signal(
            context=context,
            task_id=task.task_id,
            status=status,
            summary=summary,
            result=raw_signal.get("result"),
            failure_reason=raw_signal.get("failure_reason"),
            needs_followup=bool(raw_signal.get("needs_followup", status == "needs_followup")),
            followup_message=raw_signal.get("followup_message"),
            created_by_agent_id=task.assignee_agent_id,
            metadata={"source": "agent_runtime"},
        )

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                payload, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None

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
            conversation_id = self._conversation_id_for_message(message.id)
            conversation_context = None
            if conversation_id:
                conversation_context = self._load_conversation_context(
                    worker_context,
                    conversation_id,
                    message.id,
                )
            multimodal_context = self._build_multimodal_context(
                worker_context,
                agent_id=agent_id,
                conversation_id=conversation_id,
                mission_id=self._mission_id_for_conversation(conversation_id),
                multimodal_session_id=self._multimodal_session_id_for_conversation(conversation_id),
                correlation_id=message.correlation_id,
                causation_id=message.causation_id,
                source="message",
            )
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
                conversation_context=conversation_context,
                multimodal_context=multimodal_context,
            )
            agent_result = self.agent_runtime.run(
                context=worker_context,
                agent_id=agent_id,
                loaded_context=loaded_context,
                user_message=message.body,
                original_message_id=message.id,
            )
            reply = self._reply_if_allowed(
                worker_context,
                agent_id,
                message,
                agent_result.response,
                conversation_id=conversation_id,
            )
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
            if self._conversation_id_for_message(message.id):
                self.event_bus.emit(
                    "worker.conversation_processing_failed",
                    worker_context.actor_id,
                    {
                        "agent_id": agent_id,
                        "message_id": message.id,
                        "error": str(exc) or type(exc).__name__,
                    },
                )
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
        conversation_id: str | None = None,
    ) -> AgentMessage | None:
        if not response.strip() or message.from_agent == agent_id:
            return None
        policy = self.policies.resolve(context, agent_id)
        can_send = "send_agent_message" in set(policy.allowed_tools)
        explicitly_prefers_messages = "send_agent_message" in set(policy.preferred_tools)
        if not can_send or not (policy.can_delegate or explicitly_prefers_messages):
            return None
        reply = self.communication.send_agent_message(
            context=context,
            from_agent_id=agent_id,
            to_agent_id=message.from_agent,
            subject=f"Re: {message.subject}",
            body=response,
            task_id=message.task_id,
            conversation_id=conversation_id,
            correlation_id=message.correlation_id,
            causation_id=message.id,
        )
        if conversation_id:
            self.event_bus.emit(
                "worker.conversation_reply_sent",
                context.actor_id,
                {
                    "conversation_id": conversation_id,
                    "message_id": message.id,
                    "reply_id": reply.id,
                    "from_agent": agent_id,
                    "to_agent": message.from_agent,
                },
            )
        return reply

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

    def _conversation_id_for_message(self, message_id: str) -> str | None:
        conversations = self.communication.conversations
        if not conversations:
            return None
        try:
            return conversations.message_status(message_id).conversation_id
        except Exception:
            return None

    def _load_conversation_context(
        self,
        context: PermissionContext,
        conversation_id: str,
        message_id: str,
    ) -> dict[str, Any]:
        if not self.context_fusion:
            return {}
        try:
            conversation_context = asdict(
                self.context_fusion.build_context(
                    conversation_id=conversation_id,
                    permission_context=context,
                )
            )
        except Exception:
            conversations = self.communication.conversations
            if not conversations:
                return {}
            conversation_context = conversations.build_conversation_context(conversation_id)
        self.event_bus.emit(
            "worker.conversation_context_loaded",
            context.actor_id,
            {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "message_count": (
                    len(conversation_context.get("snapshot", {}).get("latest_messages", []))
                    if "snapshot" in conversation_context
                    else conversation_context.get("message_count", 0)
                ),
            },
        )
        return conversation_context

    def _build_multimodal_context(
        self,
        context: PermissionContext,
        agent_id: str,
        conversation_id: str | None = None,
        mission_id: str | None = None,
        multimodal_session_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        source: str = "worker",
    ) -> dict[str, Any] | None:
        policy = self.multimodal_context_policy()
        payload_base = {
            "agent_id": agent_id,
            "conversation_id": conversation_id,
            "mission_id": mission_id,
            "multimodal_session_id": multimodal_session_id,
            "source": source,
            "correlation_id": correlation_id,
            "causation_id": causation_id,
        }
        if not self.context_fusion:
            self._emit_multimodal_context_event(
                context,
                "agent.multimodal_context.skipped",
                {**payload_base, "reason": "context_fusion_unavailable"},
            )
            return None
        if not policy.get("enabled", True):
            self._emit_multimodal_context_event(
                context,
                "agent.multimodal_context.skipped",
                {**payload_base, "reason": "policy_disabled"},
            )
            return None

        effective_conversation_id = (
            conversation_id if policy.get("include_for_conversations", True) else None
        )
        effective_mission_id = mission_id if policy.get("include_for_missions", True) else None
        effective_session_id = (
            multimodal_session_id if policy.get("include_for_sessions", True) else None
        )
        if not any([effective_conversation_id, effective_mission_id, effective_session_id]):
            self._emit_multimodal_context_event(
                context,
                "agent.multimodal_context.skipped",
                {**payload_base, "reason": "no_supported_context_source"},
            )
            return None
        try:
            result = self.context_fusion.build_context(
                conversation_id=effective_conversation_id,
                multimodal_session_id=effective_session_id,
                mission_id=effective_mission_id,
                persist_snapshot=False,
            )
            payload = asdict(result)
            self._apply_multimodal_context_policy(payload, policy)
            self._emit_multimodal_context_event(
                context,
                "agent.multimodal_context.attached",
                {
                    **payload_base,
                    "context_id": payload["snapshot"]["interaction_context"]["context_id"],
                    "complete": payload["consistency"]["complete"],
                    "warnings": payload["consistency"]["warnings"],
                },
            )
            return payload
        except Exception as exc:
            self._emit_multimodal_context_event(
                context,
                "agent.multimodal_context.failed",
                {**payload_base, "error": str(exc) or type(exc).__name__},
            )
            return None

    @staticmethod
    def _apply_multimodal_context_policy(payload: dict[str, Any], policy: dict[str, Any]) -> None:
        snapshot = payload.get("snapshot", {})
        if not policy.get("attach_health_summary", True):
            snapshot["health_summary"] = None
        if not policy.get("attach_readiness_summary", True):
            snapshot["readiness_summary"] = None
        max_signals = int(policy.get("max_signals_per_context", 50))
        signal_group = snapshot.get("signal_group") or {}
        for key in (
            "speech_signals",
            "voice_signals",
            "face_signals",
            "body_signals",
            "system_signals",
        ):
            values = signal_group.get(key)
            if isinstance(values, list) and max_signals >= 0:
                signal_group[key] = values[-max_signals:] if max_signals else []
        speech_features = snapshot.get("speech_features")
        if isinstance(speech_features, list) and max_signals >= 0:
            snapshot["speech_features"] = speech_features[-max_signals:] if max_signals else []

    def _emit_multimodal_context_event(
        self,
        context: PermissionContext,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self.event_bus.emit(event_type, context.actor_id, payload)

    def _mission_id_for_conversation(self, conversation_id: str | None) -> str | None:
        if not conversation_id or not self.communication.conversations:
            return None
        try:
            metadata = self.communication.conversations.get_conversation(conversation_id).metadata
        except Exception:
            return None
        value = metadata.get("mission_id")
        return str(value) if value else None

    def _multimodal_session_id_for_conversation(self, conversation_id: str | None) -> str | None:
        if not conversation_id or not self.communication.conversations:
            return None
        try:
            metadata = self.communication.conversations.get_conversation(conversation_id).metadata
        except Exception:
            return None
        value = metadata.get("multimodal_session_id")
        return str(value) if value else None

    @staticmethod
    def _multimodal_session_id_for_task(task: DelegationTask) -> str | None:
        value = (
            task.metadata.get("multimodal_session_id") if isinstance(task.metadata, dict) else None
        )
        return str(value) if value else None

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
