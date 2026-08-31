from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from synapse.agents.registry import AgentRegistry
from synapse.capabilities.runtime import CapabilityRuntime
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, PermissionDenied, ValidationError
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.delegation.models import (
    COMPLETION_STATUSES,
    TASK_PRIORITIES,
    TASK_STATUSES,
    DelegationCompletionSignal,
    DelegationTask,
)
from synapse.observability.correlation import current_correlation_fields

if TYPE_CHECKING:
    from synapse.agents.admin import AgentAdminRuntime
    from synapse.agents.audit import AgentAuditRuntime
    from synapse.agents.communication import AgentCommunication
    from synapse.conversations.runtime import ConversationRuntime
    from synapse.delegation.retry_policy import DelegationRetryPolicyRuntime
    from synapse.delegation_execution.runtime import DelegationExecutionRuntime
    from synapse.delegation_inbox.runtime import DelegationInboxRuntime


class DelegationRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        agents: AgentRegistry,
        capabilities: CapabilityRuntime,
        events: EventBus,
        admin: AgentAdminRuntime | None = None,
        audit: AgentAuditRuntime | None = None,
        communication: AgentCommunication | None = None,
        conversations: ConversationRuntime | None = None,
        inbox: DelegationInboxRuntime | None = None,
        executions: DelegationExecutionRuntime | None = None,
        retry_policy: DelegationRetryPolicyRuntime | None = None,
    ):
        self.data_dir = data_dir
        self.agents = agents
        self.capabilities = capabilities
        self.events = events
        self.admin = admin
        self.audit = audit
        self.communication = communication
        self.conversations = conversations
        self.inbox = inbox
        self.executions = executions
        self.retry_policy = retry_policy

    def create_task(
        self,
        context: PermissionContext,
        title: str,
        description: str,
        requester_agent_id: str,
        assignee_agent_id: str,
        priority: str = "normal",
        conversation_id: str | None = None,
        mission_id: str | None = None,
        due_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DelegationTask:
        requester = requester_agent_id.strip().lower()
        assignee = assignee_agent_id.strip().lower()
        if not title.strip():
            raise ValidationError("Delegation title is required.")
        if priority not in TASK_PRIORITIES:
            raise ValidationError(f"Invalid delegation priority: {priority}")
        self.agents.get(requester)
        self.agents.get(assignee)
        self._assert_assignee_runnable(assignee)
        self._require_delegation_capability(requester, context)
        if conversation_id and self.conversations:
            conversation = self.conversations.get_conversation(conversation_id)
            missing = [
                agent_id
                for agent_id in [requester, assignee]
                if agent_id not in set(conversation.participants)
            ]
            if missing:
                raise ValidationError(
                    f"Delegation agent(s) are not conversation participants: {', '.join(missing)}"
                )
        fields = current_correlation_fields()
        task = DelegationTask(
            title=title.strip(),
            description=description,
            requester_agent_id=requester,
            assignee_agent_id=assignee,
            priority=priority,
            conversation_id=conversation_id,
            mission_id=mission_id,
            due_at=due_at,
            correlation_id=fields.get("correlation_id"),
            causation_id=fields.get("causation_id"),
            metadata=metadata or {},
        )
        self._write_task(task)
        self._emit("delegation.created", context, task)
        self._audit(task, "delegation.created", "success", context)
        self._conversation_message(context, task, "Delegation created")
        return task

    def get_task(self, task_id: str) -> DelegationTask:
        path = self._task_path(task_id)
        if not path.exists():
            raise NotFound(f"Delegation task not found: {task_id}")
        return self._read_task(path)

    def list_tasks(self, status: str | None = None) -> list[DelegationTask]:
        if status and status not in TASK_STATUSES:
            raise ValidationError(f"Invalid delegation status: {status}")
        root = self.data_dir.resolve("delegation")
        tasks = [self._read_task(path) for path in sorted(root.glob("*.yaml"))]
        if status:
            tasks = [task for task in tasks if task.status == status]
        return sorted(tasks, key=lambda task: (task.updated_at, task.task_id))

    def accept_task(self, context: PermissionContext, task_id: str) -> DelegationTask:
        return self._transition(context, task_id, "accepted", "delegation.accepted")

    def reject_task(
        self,
        context: PermissionContext,
        task_id: str,
        reason: str | None = None,
    ) -> DelegationTask:
        return self._transition(
            context,
            task_id,
            "rejected",
            "delegation.rejected",
            {"reason": reason} if reason else None,
        )

    def start_task(self, context: PermissionContext, task_id: str) -> DelegationTask:
        return self._transition(context, task_id, "in_progress", "delegation.started")

    def complete_task(
        self,
        context: PermissionContext,
        task_id: str,
        result: str | None = None,
    ) -> DelegationTask:
        return self._transition(
            context,
            task_id,
            "completed",
            "delegation.completed",
            {"result": result} if result else None,
        )

    def fail_task(
        self,
        context: PermissionContext,
        task_id: str,
        reason: str | None = None,
    ) -> DelegationTask:
        return self._transition(
            context,
            task_id,
            "failed",
            "delegation.failed",
            {"reason": reason} if reason else None,
        )

    def cancel_task(
        self,
        context: PermissionContext,
        task_id: str,
        reason: str | None = None,
    ) -> DelegationTask:
        return self._transition(
            context,
            task_id,
            "cancelled",
            "delegation.cancelled",
            {"reason": reason} if reason else None,
        )

    def restore_from_dead_letter(
        self,
        context: PermissionContext,
        task_id: str,
        status: str = "accepted",
        dead_letter_id: str | None = None,
    ) -> DelegationTask:
        if status not in {"pending", "accepted", "in_progress"}:
            raise ValidationError(f"Invalid dead letter restore status: {status}")
        metadata = {"dead_letter_id": dead_letter_id} if dead_letter_id else None
        return self._transition(
            context,
            task_id,
            status,
            "delegation.dead_letter.restored",
            metadata,
        )

    def request_retry(
        self,
        task_id: str,
        requested_by_agent_id: str | None = None,
        reason: str | None = None,
        context: PermissionContext | None = None,
    ) -> dict[str, Any]:
        if not self.retry_policy:
            raise ValidationError("Delegation retry policy runtime is not configured.")
        if not self.executions:
            raise ValidationError("Delegation execution runtime is required for retry decisions.")
        task = self.get_task(task_id)
        executions = self.executions.list_task_executions(task_id)
        decision = self.retry_policy.evaluate_retry(task, executions)
        actor_id = (
            requested_by_agent_id or (context.actor_id if context else None) or "delegation_retry"
        )
        if decision.blocked:
            raise ValidationError("; ".join(decision.blocked_reasons))
        payload: dict[str, Any] = {
            "decision": decision.to_dict(),
            "delegation": asdict(task),
            "status": "requires_approval" if decision.requires_approval else "allowed",
        }
        if decision.requires_approval:
            self.events.emit(
                "delegation.retry.requested",
                actor_id,
                {
                    "task_id": task_id,
                    "status": "requires_approval",
                    "reason": reason,
                    "decision": decision.to_dict(),
                },
            )
            return payload

        policy = self.retry_policy.load_policy()
        updated = task
        if policy.reset_task_status_on_retry:
            retry_context = context or PermissionContext(actor_id=actor_id, actor_type="agent")
            updated = self._transition(
                retry_context,
                task_id,
                policy.default_retry_status,
                "delegation.retry.requested",
                {"retry_reason": reason} if reason else None,
            )
        self.events.emit(
            "delegation.retry.requested",
            actor_id,
            {
                "task_id": task_id,
                "status": "allowed",
                "reason": reason,
                "decision": decision.to_dict(),
            },
        )
        payload["delegation"] = asdict(updated)
        return payload

    def submit_completion_signal(
        self,
        context: PermissionContext,
        task_id: str,
        status: str,
        summary: str,
        result: str | None = None,
        failure_reason: str | None = None,
        needs_followup: bool = False,
        followup_message: str | None = None,
        created_by_agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DelegationCompletionSignal:
        task = self.get_task(task_id)
        if task.status in {"completed", "failed", "rejected", "cancelled"}:
            raise ValidationError(f"Cannot submit completion for finalized delegation: {task_id}")
        if status not in COMPLETION_STATUSES:
            raise ValidationError(f"Invalid completion status: {status}")
        actor_agent_id = (created_by_agent_id or context.actor_id or "").strip().lower()
        if actor_agent_id != task.assignee_agent_id:
            raise PermissionDenied("Only the delegation assignee can submit completion signals.")
        if not summary.strip():
            raise ValidationError("Completion summary is required.")
        signal = DelegationCompletionSignal(
            task_id=task.task_id,
            status=status,
            summary=summary.strip(),
            result=result,
            failure_reason=failure_reason,
            needs_followup=needs_followup or status == "needs_followup",
            followup_message=followup_message,
            created_by_agent_id=actor_agent_id,
            correlation_id=task.correlation_id,
            causation_id=task.causation_id,
            metadata=metadata or {},
        )
        self._write_completion(signal)
        self.events.emit("delegation.completion_submitted", context.actor_id, asdict(signal))
        if status == "needs_followup":
            self.events.emit("delegation.followup_requested", context.actor_id, asdict(signal))
        self._completion_conversation_message(
            context, task, signal, "Delegation completion submitted"
        )
        return signal

    def get_completion_signal(self, task_id: str) -> DelegationCompletionSignal | None:
        self.get_task(task_id)
        path = self._completion_path(task_id)
        if not path.exists():
            return None
        raw = load_structured_file(path)
        raw.setdefault("result", None)
        raw.setdefault("failure_reason", None)
        raw.setdefault("needs_followup", raw.get("status") == "needs_followup")
        raw.setdefault("followup_message", None)
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("metadata", {})
        return DelegationCompletionSignal(**raw)

    def apply_completion_signal(
        self,
        context: PermissionContext,
        task_id: str,
    ) -> DelegationTask:
        task = self.get_task(task_id)
        signal = self.get_completion_signal(task_id)
        if not signal:
            raise NotFound(f"Delegation completion signal not found: {task_id}")
        try:
            if signal.status == "completed":
                updated = self.complete_task(
                    context, task_id, result=signal.result or signal.summary
                )
                if self.executions:
                    self.executions.complete_latest_for_task(
                        task_id,
                        result_summary=signal.result or signal.summary,
                    )
            elif signal.status == "failed":
                updated = self.fail_task(
                    context, task_id, reason=signal.failure_reason or signal.summary
                )
                if self.executions:
                    self.executions.fail_latest_for_task(
                        task_id,
                        error_message=signal.failure_reason or signal.summary,
                    )
            elif signal.status == "needs_followup":
                metadata = dict(task.metadata)
                metadata["followup_message"] = signal.followup_message or signal.summary
                updated = DelegationTask(
                    task_id=task.task_id,
                    title=task.title,
                    description=task.description,
                    status="in_progress",
                    priority=task.priority,
                    requester_agent_id=task.requester_agent_id,
                    assignee_agent_id=task.assignee_agent_id,
                    conversation_id=task.conversation_id,
                    created_at=task.created_at,
                    updated_at=datetime.now(UTC).isoformat(),
                    due_at=task.due_at,
                    correlation_id=task.correlation_id,
                    causation_id=task.causation_id,
                    metadata=metadata,
                )
                self._write_task(updated)
                self.events.emit("delegation.followup_requested", context.actor_id, asdict(signal))
            else:
                raise ValidationError(f"Invalid completion status: {signal.status}")
            self.events.emit(
                "delegation.completion_applied",
                context.actor_id,
                {"signal": asdict(signal), "delegation": asdict(updated)},
            )
            self._completion_conversation_message(
                context, updated, signal, "Delegation completion applied"
            )
            return updated
        except Exception as exc:
            self.events.emit(
                "delegation.completion_failed",
                context.actor_id,
                {"task_id": task_id, "error": str(exc) or type(exc).__name__},
            )
            raise

    def _transition(
        self,
        context: PermissionContext,
        task_id: str,
        status: str,
        event_type: str,
        metadata_update: dict[str, Any] | None = None,
    ) -> DelegationTask:
        current = self.get_task(task_id)
        metadata = dict(current.metadata)
        if metadata_update:
            metadata.update(metadata_update)
        updated = DelegationTask(
            task_id=current.task_id,
            title=current.title,
            description=current.description,
            status=status,
            priority=current.priority,
            requester_agent_id=current.requester_agent_id,
            assignee_agent_id=current.assignee_agent_id,
            conversation_id=current.conversation_id,
            mission_id=current.mission_id,
            created_at=current.created_at,
            updated_at=datetime.now(UTC).isoformat(),
            due_at=current.due_at,
            correlation_id=current.correlation_id,
            causation_id=current.causation_id,
            metadata=metadata,
        )
        self._write_task(updated)
        self._emit(event_type, context, updated)
        self._audit(updated, event_type, "success", context)
        self._conversation_message(
            context, updated, event_type.replace("delegation.", "Delegation ")
        )
        return updated

    def _require_delegation_capability(
        self,
        requester_agent_id: str,
        context: PermissionContext,
    ) -> None:
        decision = self.capabilities.check_agent_capability(
            requester_agent_id,
            "agent.task.delegation",
            context=PermissionContext(
                actor_id=requester_agent_id,
                actor_type="agent",
                device_id=context.device_id,
                autonomy=context.autonomy,
            ),
        )
        if not decision.allowed:
            raise PermissionDenied(
                f"Agent lacks capability agent.task.delegation: {decision.reason}"
            )

    def _assert_assignee_runnable(self, agent_id: str) -> None:
        if self.admin:
            self.admin.assert_agent_runnable(agent_id)

    def _emit(self, event_type: str, context: PermissionContext, task: DelegationTask) -> None:
        self.events.emit(event_type, context.actor_id, asdict(task))

    def _audit(
        self,
        task: DelegationTask,
        action: str,
        status: str,
        context: PermissionContext,
    ) -> None:
        if not self.audit:
            return
        details = {"delegation": asdict(task)}
        self.audit.append_record(
            task.requester_agent_id,
            action,
            status,
            actor_agent_id=context.actor_id,
            actor_type=context.actor_type,
            details=details,
        )
        if task.assignee_agent_id != task.requester_agent_id:
            self.audit.append_record(
                task.assignee_agent_id,
                action,
                status,
                actor_agent_id=context.actor_id,
                actor_type=context.actor_type,
                details=details,
            )

    def _conversation_message(
        self,
        context: PermissionContext,
        task: DelegationTask,
        subject: str,
    ) -> None:
        if not task.conversation_id or not self.communication:
            return
        try:
            self.communication.send_agent_message(
                context=context,
                from_agent_id=task.requester_agent_id,
                to_agent_id=task.assignee_agent_id,
                subject=subject,
                body=f"{task.title}\n\nStatus: {task.status}\n\n{task.description}",
                conversation_id=task.conversation_id,
                correlation_id=task.correlation_id,
                causation_id=task.causation_id or task.task_id,
            )
        except Exception:
            return

    def _completion_conversation_message(
        self,
        context: PermissionContext,
        task: DelegationTask,
        signal: DelegationCompletionSignal,
        subject: str,
    ) -> None:
        if not task.conversation_id or not self.communication:
            return
        try:
            self.communication.send_agent_message(
                context=context,
                from_agent_id=signal.created_by_agent_id,
                to_agent_id=task.requester_agent_id,
                subject=subject,
                body=(f"{task.title}\n\nCompletion status: {signal.status}\n\n{signal.summary}"),
                conversation_id=task.conversation_id,
                correlation_id=signal.correlation_id,
                causation_id=signal.causation_id or task.task_id,
            )
        except Exception:
            return

    def _task_path(self, task_id: str) -> Path:
        return self.data_dir.resolve(f"delegation/{task_id}.yaml")

    def _completion_path(self, task_id: str) -> Path:
        return self.data_dir.resolve(f"delegation/{task_id}.completion.yaml")

    def _write_task(self, task: DelegationTask) -> None:
        dump_structured_file(self._task_path(task.task_id), asdict(task))
        if self.inbox:
            self.inbox.update_from_task(task)

    def _write_completion(self, signal: DelegationCompletionSignal) -> None:
        dump_structured_file(self._completion_path(signal.task_id), asdict(signal))

    @staticmethod
    def _read_task(path: Path) -> DelegationTask:
        raw = load_structured_file(path)
        raw.setdefault("status", "pending")
        raw.setdefault("priority", "normal")
        raw.setdefault("conversation_id", None)
        raw.setdefault("mission_id", None)
        raw.setdefault("due_at", None)
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("metadata", {})
        raw.setdefault("updated_at", raw.get("created_at", datetime.now(UTC).isoformat()))
        return DelegationTask(**raw)
