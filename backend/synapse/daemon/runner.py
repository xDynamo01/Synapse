from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol, cast

from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext
from synapse.daemon.identity import RunnerIdentityStore
from synapse.daemon.status import DaemonStatus, DaemonStatusStore
from synapse.observability.correlation import correlation_scope, new_correlation
from synapse.scheduler.runtime import SchedulerRuntime


class MissionView(Protocol):
    mission_id: str
    status: str
    metadata: Mapping[str, object]


class MissionRuntimePort(Protocol):
    def list_missions(self) -> Sequence[MissionView]: ...

    def dispatch_ready_tasks(
        self, mission_id: str, max_concurrency: int, *, execute: bool
    ) -> object: ...


class MissionRecoveryPort(Protocol):
    def scan_timeouts(self) -> object: ...


class AgentLoopStatusView(Protocol):
    state: str


class AgentLoopPort(Protocol):
    def status(self) -> AgentLoopStatusView: ...

    def run_cycle(self, *, trigger: str) -> object: ...


class DaemonRunner:
    def __init__(
        self,
        scheduler: SchedulerRuntime,
        status_store: DaemonStatusStore,
        event_bus: EventBus,
        runner_identity: RunnerIdentityStore | None = None,
        actor_id: str = "daemon",
        missions: MissionRuntimePort | None = None,
        mission_recovery: MissionRecoveryPort | None = None,
    ):
        self.scheduler = scheduler
        self.status_store = status_store
        self.event_bus = event_bus
        self.runner_identity = runner_identity
        self.actor_id = actor_id
        self.missions = missions
        self.mission_recovery = mission_recovery
        self.agent_loop: AgentLoopPort | None = None
        self._running = False

    def start_loop(self, interval_seconds: float = 5.0) -> None:
        self._running = True
        if self.runner_identity:
            self.runner_identity.mark_online()
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
        if self.runner_identity:
            self.runner_identity.mark_online()
            self.runner_identity.heartbeat()
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
                if hasattr(self.scheduler, "enqueue_due_recurring_jobs"):
                    self.scheduler.enqueue_due_recurring_jobs(context)
                jobs = self.scheduler.run_all_pending(context)
                if self.missions:
                    for mission in self.missions.list_missions():
                        if mission.status == "running":
                            try:
                                self.missions.dispatch_ready_tasks(
                                    mission.mission_id,
                                    int(
                                        cast(
                                            str | bytes | bytearray | int | float,
                                            mission.metadata.get("max_concurrency", 1),
                                        )
                                    ),
                                    execute=True,
                                )
                            except Exception as mission_exc:
                                self.event_bus.emit(
                                    "daemon.mission.error",
                                    context.actor_id,
                                    {
                                        "mission_id": mission.mission_id,
                                        "error": str(mission_exc),
                                        "error_type": type(mission_exc).__name__,
                                    },
                                )
                if self.mission_recovery:
                    self.mission_recovery.scan_timeouts()
                if self.agent_loop and self.agent_loop.status().state not in {"paused", "stopped"}:
                    self.agent_loop.run_cycle(trigger="daemon.tick")
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
                if self.runner_identity:
                    self.runner_identity.mark_error()
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
        if self.runner_identity:
            self.runner_identity.mark_offline()
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
