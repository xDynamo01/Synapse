from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.missions.attempts import TERMINAL_ATTEMPT_STATUSES
from synapse.missions.models import TaskAttempt, now_iso


@dataclass(frozen=True)
class RetryDecision:
    allowed: bool
    strategy: str
    reason: str
    delay_seconds: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    reason: str
    required_approval: bool = False
    target_worker: str | None = None
    target_agent: str | None = None
    target_model: str | None = None
    delay_seconds: int = 0
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class MissionRecoveryRuntime:
    def __init__(
        self,
        missions: Any,
        planner: Any,
        attempts: Any,
        workers: Any,
        scheduler: Any,
        events: EventBus,
        dead_letter: Any | None = None,
    ):
        self.missions = missions
        self.planner = planner
        self.attempts = attempts
        self.workers = workers
        self.scheduler = scheduler
        self.events = events
        self.dead_letter = dead_letter
        self._applied: dict[str, Any] = {}

    def scan_timeouts(
        self, now: datetime | None = None, stale_after_seconds: int = 120
    ) -> dict[str, list[str]]:
        now = now or datetime.now(UTC)
        timed_out_attempts: list[str] = []
        timed_out_missions: list[str] = []
        for attempt in self.attempts.list():
            if attempt.status in TERMINAL_ATTEMPT_STATUSES or not attempt.timeout_at:
                continue
            if datetime.fromisoformat(attempt.timeout_at) <= now:
                self.attempts.transition(
                    attempt.attempt_id,
                    "timed_out",
                    error={"type": "timeout", "message": "Attempt deadline exceeded."},
                )
                timed_out_attempts.append(attempt.attempt_id)
        for mission in self.missions.list_missions():
            if mission.status not in {"running", "blocked"} or not mission.deadline:
                continue
            if datetime.fromisoformat(mission.deadline) <= now:
                self.missions._persist(
                    replace(
                        mission,
                        status="failed",
                        completed_at=now_iso(),
                        revision=mission.revision + 1,
                        updated_at=now_iso(),
                    ),
                    "mission.failed",
                )
                timed_out_missions.append(mission.mission_id)
        stale = self.workers.expire_stale(stale_after_seconds, now)
        result = {
            "attempts": timed_out_attempts,
            "missions": timed_out_missions,
            "workers": [item.worker_id for item in stale],
        }
        self.events.emit("mission.timeout_scan.completed", "mission-recovery", result)
        return result

    def evaluate_retry(
        self, attempt: TaskAttempt, policy: dict[str, Any] | None = None
    ) -> RetryDecision:
        policy = policy or {}
        if attempt.status not in {"failed", "timed_out", "recovery_pending"}:
            return RetryDecision(
                False, "no_retry", f"Attempt status {attempt.status} is not retryable."
            )
        mission = self.missions.get_mission(attempt.mission_id)
        plan = self.planner.get_plan(attempt.mission_id, mission.plan_id)
        task = next(item for item in plan.tasks if item.task_id == attempt.task_id)
        if attempt.attempt_number >= task.max_attempts:
            return RetryDecision(False, "no_retry", "Maximum attempts reached.")
        if not policy.get("idempotent", task.metadata.get("idempotent", True)):
            return RetryDecision(False, "no_retry", "Task is not declared idempotent.")
        if policy.get("irreversible_side_effect") or task.metadata.get("irreversible_side_effect"):
            return RetryDecision(
                False, "no_retry", "Irreversible side effect prevents automatic retry."
            )
        worker = self.workers.get(attempt.worker_id)
        strategy = (
            "retry_same_worker" if worker.status in {"idle", "sleeping"} else "retry_other_worker"
        )
        delay = min(300, 2 ** max(0, attempt.attempt_number - 1))
        return RetryDecision(True, strategy, "Retry policy permits a new immutable attempt.", delay)

    def schedule_retry(self, attempt_id: str, policy: dict[str, Any] | None = None) -> TaskAttempt:
        previous = self.attempts.get(attempt_id)
        decision = self.evaluate_retry(previous, policy)
        if not decision.allowed:
            raise ValidationError(f"Retry not allowed: {decision.reason}")
        if previous.status in {"failed", "timed_out"}:
            previous = self.attempts.transition(
                previous.attempt_id, "recovery_pending", recovery_action=decision.strategy
            )
        mission = self.missions.get_mission(previous.mission_id)
        plan = self.planner.get_plan(previous.mission_id, mission.plan_id)
        task = next(item for item in plan.tasks if item.task_id == previous.task_id)
        candidates = None
        if decision.strategy == "retry_other_worker":
            candidates = [
                item for item in self.workers.list() if item.worker_id != previous.worker_id
            ]
        selection = self.scheduler.select_worker(task, candidates=candidates)
        retry_at = datetime.now(UTC) + timedelta(seconds=decision.delay_seconds)
        created = self.attempts.create(
            previous.mission_id,
            previous.task_id,
            selection.selected_worker,
            selection.selected_agent,
            correlation_id=previous.correlation_id,
            input_snapshot=previous.input_snapshot,
            idempotency_key=f"retry:{previous.attempt_id}",
        )
        created = self.attempts.transition(
            created.attempt_id,
            "assigned",
            metadata={
                **created.metadata,
                "retry_of": previous.attempt_id,
                "not_before": retry_at.isoformat(),
            },
        )
        with self.planner.lock:
            current = self.planner.get_plan(previous.mission_id, mission.plan_id)
            updated_tasks = [replace(item, status="assigned", assigned_worker_id=selection.selected_worker,
                                     assigned_agent_id=selection.selected_agent, revision=item.revision + 1,
                                     error=previous.error, updated_at=now_iso())
                             if item.task_id == previous.task_id else item for item in current.tasks]
            self.planner.save_plan(replace(current, tasks=updated_tasks))
        self.events.emit(
            "recovery.applied",
            created.agent_id,
            {
                "attempt_id": created.attempt_id,
                "previous_attempt_id": previous.attempt_id,
                "decision": asdict(decision),
            },
        )
        return created

    def evaluate(self, attempt_id: str) -> RecoveryDecision:
        attempt = self.attempts.get(attempt_id)
        retry = self.evaluate_retry(attempt)
        action = retry.strategy if retry.allowed else "dead_letter"
        return RecoveryDecision(
            action=action, reason=retry.reason, delay_seconds=retry.delay_seconds
        )

    def dead_letter_attempt(self, attempt_id: str, reason: str = "max_retries_exceeded") -> Any:
        if not self.dead_letter:
            raise ValidationError("Dead letter runtime is unavailable.")
        attempt = self.attempts.get(attempt_id)
        if attempt.status not in {"failed", "timed_out", "recovery_pending", "dead_lettered"}:
            raise ValidationError(f"Attempt cannot enter dead letter from {attempt.status}.")
        entry = self.dead_letter.create_attempt_entry(attempt, reason, error=attempt.error)
        if attempt.status != "dead_lettered":
            self.attempts.transition(attempt_id, "dead_lettered", recovery_action="dead_letter")
        return entry

    def apply(
        self,
        attempt_id: str,
        action: str,
        *,
        options: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        key = idempotency_key or f"{attempt_id}:{action}"
        if key in self._applied:
            return self._applied[key]
        attempt = self.attempts.get(attempt_id)
        options = options or {}
        if action in {"retry_same_worker", "retry_other_worker", "retry_other_agent"}:
            result = self.schedule_retry(attempt_id, {"idempotent": True})
        elif action in {"change_model", "change_provider", "reduce_scope"}:
            mission = self.missions.get_mission(attempt.mission_id)
            task = self.missions.get_task(attempt.mission_id, attempt.task_id)
            metadata = dict(task.metadata)
            if action == "change_model":
                if not options.get("model"):
                    raise ValidationError("change_model requires an authorized model.")
                metadata["model"] = options["model"]
            elif action == "change_provider":
                if not options.get("provider"):
                    raise ValidationError("change_provider requires an authorized provider.")
                metadata["provider"] = options["provider"]
            else:
                metadata["reduced_scope"] = options.get("scope", True)
            self.missions.update_task(
                mission.mission_id,
                task.task_id,
                metadata=metadata,
                expected_revision=task.revision,
            )
            result = self.schedule_retry(attempt_id, {"idempotent": True})
        elif action == "pause_mission":
            result = self.missions.pause(attempt.mission_id)
        elif action == "require_intervention":
            result = (
                attempt
                if attempt.status == "recovery_pending"
                else self.attempts.transition(
                    attempt_id,
                    "recovery_pending",
                    recovery_action="require_intervention",
                )
            )
        elif action == "dead_letter":
            result = self.dead_letter_attempt(attempt_id)
        elif action in {"replan"}:
            result = self.missions.pause(attempt.mission_id)
        else:
            raise ValidationError(f"Unsupported recovery action: {action}")
        self._applied[key] = result
        self.events.emit(
            "recovery.applied",
            attempt.agent_id,
            {
                "mission_id": attempt.mission_id,
                "task_id": attempt.task_id,
                "attempt_id": attempt_id,
                "action": action,
                "idempotency_key": key,
            },
        )
        return result

    def restore_dead_letter(self, dlq_id: str) -> Any:
        if not self.dead_letter:
            raise ValidationError("Dead letter runtime is unavailable.")
        entry = self.dead_letter.get_entry(dlq_id)
        restored_id = entry.metadata.get("restored_attempt_id")
        if restored_id:
            return self.attempts.get(restored_id)
        if not entry.attempt_id or not entry.mission_id:
            raise ValidationError("Dead letter entry is not linked to a mission attempt.")
        previous = self.attempts.get(entry.attempt_id)
        task = self.missions.get_task(entry.mission_id, entry.task_id)
        selection = self.scheduler.select_worker(task)
        restored = self.attempts.create(
            entry.mission_id,
            entry.task_id,
            selection.selected_worker,
            selection.selected_agent,
            correlation_id=entry.correlation_id,
            input_snapshot=previous.input_snapshot,
            idempotency_key=f"dlq-restore:{dlq_id}",
        )
        restored = self.attempts.transition(
            restored.attempt_id,
            "assigned",
            metadata={**restored.metadata, "restored_from_dlq": dlq_id},
        )
        self.dead_letter.restore_attempt_entry(dlq_id, restored.attempt_id)
        return restored
