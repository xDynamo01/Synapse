from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from synapse.agents.admin import AgentAdminRuntime
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.dead_letter.runtime import DeadLetterRuntime
from synapse.delegation.timeout_policy import DelegationTimeoutPolicyRuntime
from synapse.delegation_inbox.runtime import DelegationInboxRuntime
from synapse.lifecycle.runtime import LifecycleRuntime
from synapse.notifications.runtime import NotificationRuntime
from synapse.observability.correlation import (
    correlation_scope,
    current_correlation,
    new_correlation,
)
from synapse.presence.runtime import PresenceRuntime
from synapse.retention.runtime import RetentionRuntime
from synapse.scheduler.jobs import RECURRING_JOB_TYPES, Job, RecurringJobDefinition
from synapse.scheduler.lock import SchedulerLock
from synapse.scheduler.queue import JobQueue
from synapse.workers.agent_worker import AgentWorker


class SchedulerRuntime:
    def __init__(
        self,
        queue: JobQueue,
        worker: AgentWorker,
        event_bus: EventBus,
        presence: PresenceRuntime | None = None,
        lifecycle: LifecycleRuntime | None = None,
        notifications: NotificationRuntime | None = None,
        lock: SchedulerLock | None = None,
        admin: AgentAdminRuntime | None = None,
        retention: RetentionRuntime | None = None,
        delegation_inbox: DelegationInboxRuntime | None = None,
        delegation_timeout: DelegationTimeoutPolicyRuntime | None = None,
        dead_letter: DeadLetterRuntime | None = None,
    ):
        self.queue = queue
        self.worker = worker
        self.event_bus = event_bus
        self.presence = presence
        self.lifecycle = lifecycle
        self.notifications = notifications
        self.lock = lock
        self.admin = admin
        self.retention = retention
        self.delegation_inbox = delegation_inbox
        self.delegation_timeout = delegation_timeout
        self.dead_letter = dead_letter
        self.missions: Any | None = None
        self.agent_loop: Any | None = None

    def enqueue(
        self,
        context: PermissionContext,
        job_type: str,
        payload: dict[str, Any],
        priority: int = 100,
        max_attempts: int = 3,
        scheduled_for: str | None = None,
        correlation_id: str | None = None,
        target: str | None = None,
        idempotency_key: str | None = None,
        schedule: str = "one_shot",
        misfire_policy: str = "run_once",
    ) -> Job:
        if idempotency_key:
            existing = next(
                (
                    item
                    for item in self.queue.list_jobs()
                    if item.idempotency_key == idempotency_key
                    and item.status not in {"completed", "failed", "cancelled"}
                ),
                None,
            )
            if existing:
                return existing
        correlation = current_correlation()
        if correlation_id and (correlation is None or correlation.correlation_id != correlation_id):
            correlation = new_correlation(source="scheduler", correlation_id=correlation_id)
        correlation = correlation or new_correlation(source="scheduler")
        job = Job(
            type=job_type,
            payload=payload,
            priority=priority,
            max_attempts=max_attempts,
            scheduled_for=scheduled_for,
            correlation_id=correlation_id or correlation.correlation_id,
            causation_id=correlation.causation_id,
            parent_id=correlation.parent_id,
            source=correlation.source,
            target=target,
            idempotency_key=idempotency_key,
            schedule=schedule,
            next_run_at=scheduled_for,
            misfire_policy=misfire_policy,
        )
        self.queue.add(job)
        with correlation_scope(correlation.child(source="scheduler", job_id=job.id)):
            self.event_bus.emit("job.enqueued", context.actor_id, asdict(job))
        return job

    def list_jobs(self, status: str | None = None) -> list[Job]:
        return self.queue.list_jobs(status=status)

    def get_job(self, job_id: str) -> Job:
        return self.queue.get(job_id)

    def cancel_job(self, context: PermissionContext, job_id: str) -> Job:
        job = self.queue.get(job_id)
        if job.status in {"completed", "failed"}:
            raise ValidationError(f"Cannot cancel job with status {job.status}: {job_id}")
        updated = self.queue.save(job.with_updates(status="cancelled"))
        self.event_bus.emit("job.cancelled", context.actor_id, asdict(updated))
        return updated

    def pause_job(self, context: PermissionContext, job_id: str) -> Job:
        job = self.queue.get(job_id)
        if job.status == "paused":
            return job
        if job.status != "pending":
            raise ValidationError(f"Cannot pause job with status {job.status}: {job_id}")
        updated = self.queue.save(job.with_updates(status="paused"))
        self.event_bus.emit("job.paused", context.actor_id, asdict(updated))
        return updated

    def resume_job(self, context: PermissionContext, job_id: str) -> Job:
        job = self.queue.get(job_id)
        if job.status == "pending":
            return job
        if job.status != "paused":
            raise ValidationError(f"Cannot resume job with status {job.status}: {job_id}")
        updated = self.queue.save(job.with_updates(status="pending"))
        self.event_bus.emit("job.resumed", context.actor_id, asdict(updated))
        return updated

    def run_next(self, context: PermissionContext) -> Job | None:
        if self.lock and not self.lock.acquire():
            return None
        try:
            return self._run_next_locked(context)
        finally:
            if self.lock:
                self.lock.release()

    def _run_next_locked(self, context: PermissionContext) -> Job | None:
        job = self.queue.next_pending()
        if not job:
            return None
        return self._run_job(context, job)

    def run_all_pending(self, context: PermissionContext) -> list[Job]:
        if self.lock and not self.lock.acquire():
            return []
        completed: list[Job] = []
        try:
            while True:
                job = self._run_next_locked(context)
                if not job:
                    break
                completed.append(job)
            return completed
        finally:
            if self.lock:
                self.lock.release()

    def lock_status(self):
        if not self.lock:
            return {"locked": False, "owner_id": None, "acquired_at": None, "stale": False}
        return asdict(self.lock.status())

    def recover_stale_lock(self) -> dict[str, Any]:
        if not self.lock:
            return {"recovered": True, "locked": False}
        recovered = self.lock.recover_stale()
        return {"recovered": recovered, "lock": asdict(self.lock.status())}

    def retry_failed(self, context: PermissionContext) -> list[Job]:
        retried: list[Job] = []
        for job in self.queue.list_jobs(status="failed"):
            if job.attempts >= job.max_attempts:
                continue
            updated = self.queue.save(
                job.with_updates(
                    status="pending",
                    started_at=None,
                    completed_at=None,
                    failed_reason=None,
                )
            )
            self.event_bus.emit("job.retried", context.actor_id, asdict(updated))
            retried.append(updated)
        return retried

    def load_recurring_jobs(self) -> list[RecurringJobDefinition]:
        policy = load_structured_file(self.queue.data_dir.resolve("config/scheduler_policy.yaml"))
        configured = policy.get("recurring_jobs", [])
        if not isinstance(configured, list):
            raise ValidationError("scheduler_policy.yaml recurring_jobs must be a list")

        loaded: list[RecurringJobDefinition] = []
        for item in configured:
            if not isinstance(item, dict):
                raise ValidationError("recurring job definition must be an object")
            definition = self._recurring_from_policy(item)
            state = self._load_recurring_state(definition.id)
            if state:
                definition = definition.with_updates(
                    last_run_at=state.last_run_at,
                    next_run_at=state.next_run_at,
                    created_at=state.created_at,
                )
            if not definition.next_run_at:
                definition = definition.with_updates(next_run_at=datetime.now(UTC).isoformat())
                self._save_recurring_state(definition)
            loaded.append(definition)

        self.event_bus.emit(
            "recurring.loaded",
            "scheduler",
            {"count": len(loaded), "jobs": [asdict(job) for job in loaded]},
        )
        return loaded

    def enqueue_due_recurring_jobs(
        self,
        context: PermissionContext,
    ) -> list[Job]:
        if self.lock and not self.lock.acquire():
            return []
        try:
            return self._enqueue_due_recurring_jobs_locked(context)
        finally:
            if self.lock:
                self.lock.release()

    def _enqueue_due_recurring_jobs_locked(
        self,
        context: PermissionContext,
    ) -> list[Job]:
        enqueued: list[Job] = []
        for definition in self.load_recurring_jobs():
            try:
                if not definition.enabled:
                    self.event_bus.emit(
                        "recurring.skipped",
                        context.actor_id,
                        {"id": definition.id, "reason": "disabled"},
                    )
                    continue
                if not definition.is_due():
                    self.event_bus.emit(
                        "recurring.skipped",
                        context.actor_id,
                        {
                            "id": definition.id,
                            "reason": "not_due",
                            "next_run_at": definition.next_run_at,
                        },
                    )
                    continue
                self.event_bus.emit("recurring.due", context.actor_id, asdict(definition))
                correlation = current_correlation()
                job = self.enqueue(
                    context=context,
                    job_type=definition.type,
                    payload={
                        **definition.payload,
                        "recurring_id": definition.id,
                    },
                    priority=definition.priority,
                    max_attempts=definition.max_attempts,
                    correlation_id=correlation.correlation_id if correlation else None,
                )
                now = datetime.now(UTC)
                next_run = now + self._interval_delta(definition.interval_minutes)
                updated = definition.with_updates(
                    last_run_at=now.isoformat(),
                    next_run_at=next_run.isoformat(),
                )
                self._save_recurring_state(updated)
                self.event_bus.emit(
                    "recurring.enqueued",
                    context.actor_id,
                    {"recurring": asdict(updated), "job": asdict(job)},
                )
                enqueued.append(job)
            except Exception as exc:
                self.event_bus.emit(
                    "recurring.failed",
                    context.actor_id,
                    {
                        "id": definition.id,
                        "error": str(exc) or type(exc).__name__,
                        "error_type": type(exc).__name__,
                    },
                )
        return enqueued

    def _run_job(self, context: PermissionContext, job: Job) -> Job:
        correlation = current_correlation()
        if correlation is None or correlation.correlation_id != job.correlation_id:
            correlation = new_correlation(
                source="scheduler",
                correlation_id=job.correlation_id,
                job_id=job.id,
            )
        with correlation_scope(correlation.child(source="scheduler", job_id=job.id)):
            running = self.queue.save(
                job.with_updates(
                    status="running",
                    attempts=job.attempts + 1,
                    started_at=datetime.now(UTC).isoformat(),
                    completed_at=None,
                    failed_reason=None,
                )
            )
            self.event_bus.emit("job.started", context.actor_id, asdict(running))
            try:
                agent_id = self._agent_id_for_job(running)
                if agent_id and self.lifecycle:
                    self.lifecycle.wake(agent_id, f"scheduled job {running.id}")
                if agent_id and self.presence:
                    self.presence.set_state(
                        agent_id,
                        "working",
                        f"Running job {running.type}",
                        {
                            "current_job_id": running.id,
                            "actor_id": context.actor_id,
                        },
                    )
                result = self._execute(context, running)
                completed = self.queue.save(
                    running.with_updates(
                        status="completed",
                        completed_at=datetime.now(UTC).isoformat(),
                        failed_reason=None,
                        payload={**running.payload, "result": result},
                    )
                )
                self.event_bus.emit("job.completed", context.actor_id, asdict(completed))
                if agent_id and self.presence:
                    self.presence.set_state(
                        agent_id,
                        "idle",
                        f"Completed job {running.type}",
                        {
                            "current_job_id": running.id,
                            "actor_id": context.actor_id,
                        },
                    )
                return completed
            except Exception as exc:
                failed = self.queue.save(
                    running.with_updates(
                        status="failed",
                        failed_reason=str(exc) or type(exc).__name__,
                    )
                )
                self.event_bus.emit("job.failed", context.actor_id, asdict(failed))
                agent_id = self._agent_id_for_job(running)
                if agent_id and self.presence:
                    self.presence.set_state(
                        agent_id,
                        "error",
                        f"Failed job {running.type}",
                        {
                            "current_job_id": running.id,
                            "actor_id": context.actor_id,
                        },
                    )
                return failed

    def _execute(self, context: PermissionContext, job: Job) -> dict[str, Any]:
        if job.type == "process_agent_inbox":
            agent_id = str(job.payload.get("agent_id", "")).strip()
            if not agent_id:
                raise ValidationError("process_agent_inbox requires payload.agent_id")
            inbox_results = self.worker.process_inbox(context, agent_id)
            failures = [result for result in inbox_results if result.status == "failed"]
            if failures:
                raise ValidationError(f"Worker failed to process {len(failures)} message(s).")
            return {"results": [asdict(result) for result in inbox_results]}
        if job.type == "process_agent_delegations":
            agent_id = str(job.payload.get("agent_id", "")).strip()
            if not agent_id:
                raise ValidationError("process_agent_delegations requires payload.agent_id")
            limit = int(job.payload.get("limit", 1))
            delegation_results = self.worker.process_delegations(context, agent_id, limit=limit)
            delegation_failures = [
                result for result in delegation_results if result.status == "failed"
            ]
            if delegation_failures:
                raise ValidationError(
                    f"Worker failed to process {len(delegation_failures)} delegation(s)."
                )
            return {"results": [asdict(result) for result in delegation_results]}
        if job.type == "notification_cleanup":
            if not self.notifications:
                raise ValidationError("notification_cleanup requires NotificationRuntime")
            notification_cleanup = self.notifications.cleanup_notifications()
            return {"cleanup": asdict(notification_cleanup)}
        if job.type == "agent_admin_request_cleanup":
            if not self.admin:
                raise ValidationError("agent_admin_request_cleanup requires AgentAdminRuntime")
            dry_run = bool(job.payload.get("dry_run", False))
            admin_cleanup = self.admin.cleanup_admin_action_requests(dry_run=dry_run)
            return {"cleanup": asdict(admin_cleanup)}
        if job.type == "retention_cleanup_domain":
            if not self.retention:
                raise ValidationError("retention_cleanup_domain requires RetentionRuntime")
            domain_id = str(job.payload.get("domain_id", "")).strip()
            if not domain_id:
                raise ValidationError("retention_cleanup_domain requires payload.domain_id")
            dry_run = bool(job.payload.get("dry_run", True))
            retention_cleanup = self.retention.cleanup_domain(domain_id, dry_run=dry_run)
            return {"cleanup": asdict(retention_cleanup)}
        if job.type == "delegation_inbox_rebuild":
            if not self.delegation_inbox:
                raise ValidationError("delegation_inbox_rebuild requires DelegationInboxRuntime")
            agent_id = str(job.payload.get("agent_id", "")).strip()
            if agent_id:
                entries = self.delegation_inbox.rebuild_agent_inbox(agent_id)
                return {"agent_id": agent_id, "entries": [asdict(entry) for entry in entries]}
            rebuilt = self.delegation_inbox.rebuild_all_inboxes()
            return {
                "agents": {
                    agent_id: [asdict(entry) for entry in entries]
                    for agent_id, entries in rebuilt.items()
                }
            }
        if job.type == "delegation_timeout_scan":
            if not self.delegation_timeout:
                raise ValidationError(
                    "delegation_timeout_scan requires DelegationTimeoutPolicyRuntime"
                )
            dry_run = bool(job.payload.get("dry_run", True))
            return {
                "timeout_scan": asdict(self.delegation_timeout.run_timeout_scan(dry_run=dry_run))
            }
        if job.type == "dead_letter_review_scan":
            if not self.dead_letter:
                raise ValidationError("dead_letter_review_scan requires DeadLetterRuntime")
            return {"dead_letter": self.dead_letter.review_scan()}
        if job.type == "mission_dispatch":
            if not self.missions:
                raise ValidationError("mission_dispatch requires MissionRuntime")
            mission_id = job.target or str(job.payload.get("mission_id", ""))
            if not mission_id:
                raise ValidationError("mission_dispatch requires target mission_id")
            return {
                "mission_dispatch": asdict(
                    self.missions.dispatch_ready_tasks(
                        mission_id,
                        job.payload.get("max_concurrency"),
                        execute=bool(job.payload.get("execute", True)),
                    )
                )
            }
        if job.type == "agent_loop_cycle":
            if not self.agent_loop:
                raise ValidationError("agent_loop_cycle requires AgentLoopRuntime")
            return {"cycle": asdict(self.agent_loop.run_cycle(trigger="scheduler.job"))}
        raise ValidationError(f"Unknown job type: {job.type}")

    def _recurring_from_policy(self, raw: dict[str, Any]) -> RecurringJobDefinition:
        job_type = str(raw.get("type", "")).strip()
        if job_type not in RECURRING_JOB_TYPES:
            raise ValidationError(f"Invalid recurring job type: {job_type}")
        interval = int(raw.get("interval_minutes", 0))
        if interval < 1:
            raise ValidationError("Recurring job interval_minutes must be at least 1")
        recurring_id = str(raw.get("id") or job_type).strip()
        if not recurring_id:
            raise ValidationError("Recurring job id is required")
        return RecurringJobDefinition(
            id=recurring_id,
            type=job_type,
            payload=dict(raw.get("payload", {})),
            interval_minutes=interval,
            enabled=bool(raw.get("enabled", True)),
            priority=int(raw.get("priority", 100)),
            max_attempts=int(raw.get("max_attempts", 3)),
            next_run_at=raw.get("next_run_at"),
            last_run_at=raw.get("last_run_at"),
        )

    def _load_recurring_state(self, recurring_id: str) -> RecurringJobDefinition | None:
        path = self._recurring_state_path(recurring_id)
        if not path.exists():
            return None
        return RecurringJobDefinition(**load_structured_file(path))

    def _save_recurring_state(self, definition: RecurringJobDefinition) -> None:
        dump_structured_file(self._recurring_state_path(definition.id), asdict(definition))

    def _recurring_state_path(self, recurring_id: str) -> Path:
        return self.queue.data_dir.resolve(f"scheduler/recurring/{recurring_id}.yaml")

    @staticmethod
    def _interval_delta(interval_minutes: int):
        from datetime import timedelta

        return timedelta(minutes=interval_minutes)

    @staticmethod
    def _agent_id_for_job(job: Job) -> str | None:
        if job.type in {"process_agent_inbox", "process_agent_delegations"}:
            agent_id = str(job.payload.get("agent_id", "")).strip()
            return agent_id or None
        return None
