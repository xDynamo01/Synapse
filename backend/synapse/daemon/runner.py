from __future__ import annotations

import time
from dataclasses import asdict
from datetime import UTC, datetime

from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext
from synapse.daemon.status import DaemonStatus, DaemonStatusStore
from synapse.observability.correlation import correlation_scope, new_correlation
from synapse.scheduler.runtime import SchedulerRuntime


class DaemonRunner:
    def __init__(
        self,
        scheduler: SchedulerRuntime,
        status_store: DaemonStatusStore,
        event_bus: EventBus,
        actor_id: str = "daemon",
    ):
        self.scheduler = scheduler
        self.status_store = status_store
        self.event_bus = event_bus
        self.actor_id = actor_id
        self._running = False

    def start_loop(self, interval_seconds: float = 5.0) -> None:
        self._running = True
        now = self._now()
        current = self.status()
        self.status_store.save(
            DaemonStatus(
                running=True,
                last_tick_at=current.last_tick_at,
                total_ticks=current.total_ticks,
                last_error=current.last_error,
                last_jobs_run=current.last_jobs_run,
                started_at=current.started_at or now,
                stopped_at=None,
            )
        )
        while self._running:
            self.run_once()
            time.sleep(interval_seconds)

    def run_once(self, context: PermissionContext | None = None) -> DaemonStatus:
        context = context or PermissionContext(actor_id=self.actor_id, actor_type="system")
        current = self.status()
        tick_at = self._now()
        correlation = new_correlation(source="daemon")
        with correlation_scope(correlation):
            self.event_bus.emit(
                "daemon.tick",
                context.actor_id,
                {"tick_at": tick_at, "total_ticks": current.total_ticks + 1},
            )
            try:
                jobs = self.scheduler.run_all_pending(context)
                job_payloads = [asdict(job) for job in jobs]
                updated = DaemonStatus(
                    running=current.running,
                    last_tick_at=tick_at,
                    total_ticks=current.total_ticks + 1,
                    last_error=None,
                    last_jobs_run=job_payloads,
                    started_at=current.started_at,
                    stopped_at=current.stopped_at,
                )
                return self.status_store.save(updated)
            except Exception as exc:
                error = str(exc) or type(exc).__name__
                self.event_bus.emit(
                    "daemon.error",
                    context.actor_id,
                    {"tick_at": tick_at, "error": error, "error_type": type(exc).__name__},
                )
                updated = DaemonStatus(
                    running=current.running,
                    last_tick_at=tick_at,
                    total_ticks=current.total_ticks + 1,
                    last_error=error,
                    last_jobs_run=[],
                    started_at=current.started_at,
                    stopped_at=current.stopped_at,
                )
                return self.status_store.save(updated)

    def stop(self) -> DaemonStatus:
        self._running = False
        current = self.status()
        return self.status_store.save(
            DaemonStatus(
                running=False,
                last_tick_at=current.last_tick_at,
                total_ticks=current.total_ticks,
                last_error=current.last_error,
                last_jobs_run=current.last_jobs_run,
                started_at=current.started_at,
                stopped_at=self._now(),
            )
        )

    def status(self) -> DaemonStatus:
        return self.status_store.load()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
