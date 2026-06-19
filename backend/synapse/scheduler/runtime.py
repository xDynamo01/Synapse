from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext
from synapse.lifecycle.runtime import LifecycleRuntime
from synapse.observability.correlation import (
    correlation_scope,
    current_correlation,
    new_correlation,
)
from synapse.presence.runtime import PresenceRuntime
from synapse.scheduler.jobs import Job
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
    ):
        self.queue = queue
        self.worker = worker
        self.event_bus = event_bus
        self.presence = presence
        self.lifecycle = lifecycle

    def enqueue(
        self,
        context: PermissionContext,
        job_type: str,
        payload: dict[str, Any],
        priority: int = 100,
        max_attempts: int = 3,
        scheduled_for: str | None = None,
        correlation_id: str | None = None,
    ) -> Job:
        correlation = current_correlation()
        if correlation_id and (
            correlation is None or correlation.correlation_id != correlation_id
        ):
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

    def run_next(self, context: PermissionContext) -> Job | None:
        job = self.queue.next_pending()
        if not job:
            return None
        return self._run_job(context, job)

    def run_all_pending(self, context: PermissionContext) -> list[Job]:
        completed: list[Job] = []
        while True:
            job = self.run_next(context)
            if not job:
                break
            completed.append(job)
        return completed

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
            results = self.worker.process_inbox(context, agent_id)
            failures = [result for result in results if result.status == "failed"]
            if failures:
                raise ValidationError(f"Worker failed to process {len(failures)} message(s).")
            return {"results": [asdict(result) for result in results]}
        raise ValidationError(f"Unknown job type: {job.type}")

    @staticmethod
    def _agent_id_for_job(job: Job) -> str | None:
        if job.type == "process_agent_inbox":
            agent_id = str(job.payload.get("agent_id", "")).strip()
            return agent_id or None
        return None
