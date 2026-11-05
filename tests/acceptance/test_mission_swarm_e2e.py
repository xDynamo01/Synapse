from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.missions.models import MissionTask, WorkerDescriptor
from synapse.scheduler.lock import SchedulerLock


@dataclass
class ControlledExecutionAdapter:
    reviews: list[bool] | None = None

    def execute(self, attempt, task, mission, worker, context) -> dict[str, Any]:
        output: dict[str, Any] = {
            "task_id": task.task_id,
            "attempt_number": attempt.attempt_number,
            "dependency_outputs": attempt.input_snapshot.get("dependency_outputs", []),
        }
        if task.metadata.get("reviewer"):
            approved = self.reviews.pop(0) if self.reviews else True
            output["review"] = {"approved": approved, "feedback": None if approved else "revise"}
        return {
            "output": output,
            "structured_output": output,
            "artifacts": [],
            "tool_call_ids": [],
            "model_selection": {"provider": "controlled-test-adapter", "model": "deterministic"},
            "context_trace_id": attempt.correlation_id,
            "warnings": [],
            "error": None,
            "metrics": {"calls": 1},
            "evidence": [{"kind": "controlled_adapter", "attempt_id": attempt.attempt_id}],
            "status": "completed",
        }


def new_runtime(path: Path, adapter: ControlledExecutionAdapter | None = None):
    settings = Settings(
        project_root=Path(__file__).resolve().parents[2],
        data_dir=path,
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    runtime = create_runtime(settings)
    if adapter:
        runtime.worker_execution.executor = adapter.execute
    return runtime


def register_workers(runtime, count: int) -> None:
    for index in range(count):
        runtime.data_dir.ensure_file(f"agents/agent-{index}/CONFIG.yaml", json.dumps({
            "id": f"agent-{index}", "name": f"Agent {index}", "role": "worker",
            "preferred_model": "mock/deterministic",
        }))
        runtime.worker_registry.register(
            WorkerDescriptor(
                worker_id=f"worker-{index}",
                agent_id=f"agent-{index}",
                status="idle",
                capabilities=["work"],
            )
        )


def plan_mission(runtime, task_specs: list[dict[str, Any]], metadata: dict[str, Any] | None = None):
    mission = runtime.missions.create_mission("Acceptance mission", objective="Execute verified work", metadata=metadata or {})
    tasks = [MissionTask(mission.mission_id, **spec) for spec in task_specs]
    plan = runtime.planner.create_plan(mission.mission_id, mission.objective, tasks=tasks)
    runtime.missions.attach_plan(mission.mission_id, plan.plan_id)
    return mission, plan


def test_simple_mission_restart_and_trace() -> None:
    with tempfile.TemporaryDirectory() as directory:
        data_dir = Path(directory) / "data"
        adapter = ControlledExecutionAdapter()
        runtime = new_runtime(data_dir, adapter)
        register_workers(runtime, 1)
        mission, _ = plan_mission(
            runtime,
            [{"title": "Task", "objective": "Do task", "task_id": "task", "required_capabilities": ["work"]}],
        )

        runtime.missions.dispatch_ready_tasks(mission.mission_id, execute=False)
        restarted = new_runtime(data_dir, adapter)
        attempt = restarted.attempts.list(mission_id=mission.mission_id)[0]
        restarted.worker_execution.execute_attempt(attempt.attempt_id)
        completed = restarted.missions.refresh_progress(mission.mission_id)

        assert completed.status == "completed"
        assert completed.progress == 100
        assert len(restarted.attempts.list(mission_id=mission.mission_id)) == 1
        assert restarted.mission_trace.summarize(mission.mission_id)["total_events"] > 0


def test_parallel_three_tasks_two_workers_incremental() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = new_runtime(Path(directory) / "data", ControlledExecutionAdapter())
        register_workers(runtime, 2)
        mission, _ = plan_mission(
            runtime,
            [
                {"title": f"Task {index}", "objective": f"Work {index}", "task_id": f"task-{index}", "required_capabilities": ["work"]}
                for index in range(3)
            ],
            {"max_concurrency": 2},
        )

        first = runtime.missions.dispatch_ready_tasks(mission.mission_id, 2)
        second = runtime.missions.dispatch_ready_tasks(mission.mission_id, 2)

        assert len(first.dispatched) == 2
        assert len(second.dispatched) == 1
        assert len(runtime.attempts.list(mission_id=mission.mission_id)) == 3
        assert runtime.missions.get_mission(mission.mission_id).status == "completed"


def test_pipeline_persists_handoff_and_resumes_after_restart() -> None:
    with tempfile.TemporaryDirectory() as directory:
        data_dir = Path(directory) / "data"
        adapter = ControlledExecutionAdapter()
        runtime = new_runtime(data_dir, adapter)
        register_workers(runtime, 1)
        mission, _ = plan_mission(
            runtime,
            [
                {"title": "A", "objective": "A", "task_id": "a", "required_capabilities": ["work"]},
                {"title": "B", "objective": "B", "task_id": "b", "dependencies": ["a"], "required_capabilities": ["work"]},
                {"title": "C", "objective": "C", "task_id": "c", "dependencies": ["b"], "required_capabilities": ["work"]},
            ],
        )

        runtime.missions.dispatch_ready_tasks(mission.mission_id, 1)
        restarted = new_runtime(data_dir, adapter)
        restarted.missions.dispatch_ready_tasks(mission.mission_id, 1)
        restarted.missions.dispatch_ready_tasks(mission.mission_id, 1)
        attempts = restarted.attempts.list(mission_id=mission.mission_id)

        assert [attempt.task_id for attempt in attempts] == ["a", "b", "c"]
        assert attempts[1].input_snapshot["dependency_outputs"][0]["task_id"] == "a"
        assert attempts[2].input_snapshot["dependency_outputs"][0]["task_id"] == "b"
        assert restarted.missions.get_mission(mission.mission_id).status == "completed"


def test_leader_worker_swarm_runs_real_attempts_and_consolidates() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = new_runtime(Path(directory) / "data", ControlledExecutionAdapter())
        register_workers(runtime, 1)
        mission, _ = plan_mission(
            runtime,
            [{"title": "Worker task", "objective": "Work", "task_id": "work", "required_capabilities": ["work"]}],
        )
        swarm = runtime.swarm.create(mission.mission_id, "leader_worker", "leader", ["agent-0"])

        result = runtime.swarm.run(swarm.swarm_id)

        assert result["status"] == "completed"
        assert len(runtime.attempts.list(mission_id=mission.mission_id)) == 1
        assert result["result"]["outputs"][0]["task_id"] == "work"


def test_review_loop_preserves_rejection_and_second_approval() -> None:
    with tempfile.TemporaryDirectory() as directory:
        adapter = ControlledExecutionAdapter(reviews=[False, True])
        runtime = new_runtime(Path(directory) / "data", adapter)
        for name in ("producer", "reviewer"):
            runtime.data_dir.ensure_file(f"agents/{name}/CONFIG.yaml", json.dumps({
                "id": name, "name": name, "role": "worker", "preferred_model": "mock/deterministic",
            }))
        runtime.worker_registry.register(WorkerDescriptor("producer-worker", "producer", "idle", ["produce"]))
        runtime.worker_registry.register(WorkerDescriptor("reviewer-worker", "reviewer", "idle", ["review"]))
        mission, _ = plan_mission(
            runtime,
            [
                {
                    "title": "Produce",
                    "objective": "Produce result",
                    "task_id": "produce",
                    "required_capabilities": ["produce"],
                    "metadata": {"producer": True},
                },
                {
                    "title": "Review",
                    "objective": "Review result",
                    "task_id": "review",
                    "dependencies": ["produce"],
                    "required_capabilities": ["review"],
                    "metadata": {"reviewer": True},
                },
            ],
        )
        swarm = runtime.swarm.create(
            mission.mission_id,
            "review_loop",
            None,
            ["producer", "reviewer"],
            {"max_iterations": 2},
        )

        statuses = [runtime.swarm.run(swarm.swarm_id)["status"] for _ in range(4)]
        attempts = runtime.attempts.list(mission_id=mission.mission_id)
        persisted = runtime.swarm.get(swarm.swarm_id)

        assert statuses == ["running", "running", "running", "completed"]
        assert [attempt.task_id for attempt in attempts] == ["produce", "review", "produce", "review"]
        assert attempts[2].attempt_number == 2
        assert persisted.metadata["review_history"][0]["feedback"][0]["approved"] is False
        assert runtime.missions.get_mission(mission.mission_id).status == "completed"


def test_parallel_swarm_runs_in_two_bounded_batches() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = new_runtime(Path(directory) / "data", ControlledExecutionAdapter())
        register_workers(runtime, 2)
        mission, _ = plan_mission(
            runtime,
            [
                {"title": f"P{index}", "objective": f"Parallel {index}", "task_id": f"p{index}", "required_capabilities": ["work"]}
                for index in range(3)
            ],
        )
        swarm = runtime.swarm.create(
            mission.mission_id,
            "parallel",
            None,
            ["agent-0", "agent-1"],
            {"max_parallelism": 2, "allow_worker_reuse": True},
        )

        first = runtime.swarm.run(swarm.swarm_id)
        second = runtime.swarm.run(swarm.swarm_id)

        assert first["status"] == "running"
        assert second["status"] == "completed"
        assert [item["task_id"] for item in second["result"]["outputs"]] == ["p0", "p1", "p2"]


def test_pipeline_swarm_runs_ordered_persisted_attempts() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = new_runtime(Path(directory) / "data", ControlledExecutionAdapter())
        register_workers(runtime, 1)
        mission, _ = plan_mission(
            runtime,
            [
                {"title": "A", "objective": "A", "task_id": "a", "required_capabilities": ["work"]},
                {"title": "B", "objective": "B", "task_id": "b", "dependencies": ["a"], "required_capabilities": ["work"]},
                {"title": "C", "objective": "C", "task_id": "c", "dependencies": ["b"], "required_capabilities": ["work"]},
            ],
        )
        swarm = runtime.swarm.create(mission.mission_id, "pipeline", None, ["agent-0"])

        results = [runtime.swarm.run(swarm.swarm_id) for _ in range(3)]
        attempts = runtime.attempts.list(mission_id=mission.mission_id)

        assert [result["status"] for result in results] == ["running", "running", "completed"]
        assert [attempt.task_id for attempt in attempts] == ["a", "b", "c"]
        assert attempts[2].input_snapshot["dependency_outputs"][0]["provenance"].endswith("task:b")


def test_daemon_isolates_broken_mission_and_completes_next() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = new_runtime(Path(directory) / "data", ControlledExecutionAdapter())
        register_workers(runtime, 1)
        broken = runtime.missions.create_mission("Broken", status="running")
        healthy, _ = plan_mission(
            runtime,
            [{"title": "Healthy", "objective": "Complete", "task_id": "healthy", "required_capabilities": ["work"]}],
        )
        runtime.missions.update_mission(healthy.mission_id, status="running")
        runtime.worker_execution.executor = ControlledExecutionAdapter().execute

        status = runtime.daemon.run_once()

        assert status.last_error is None
        assert runtime.missions.get_mission(broken.mission_id).status == "running"
        assert runtime.missions.get_mission(healthy.mission_id).status == "completed"
        errors = [event for event in runtime.events.tail(100) if event.type == "daemon.mission.error"]
        assert errors[-1].payload["mission_id"] == broken.mission_id


def test_task_reassign_cancel_and_revision_are_operational() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = new_runtime(Path(directory) / "data", ControlledExecutionAdapter())
        register_workers(runtime, 2)
        mission, _ = plan_mission(
            runtime,
            [{"title": "Mutable", "objective": "Mutate safely", "task_id": "mutable", "required_capabilities": ["work"]}],
        )

        assigned = runtime.missions.assign_task(
            mission.mission_id,
            "mutable",
            "worker-0",
            expected_revision=1,
        )
        first_attempt = runtime.attempts.active_for_task("mutable")
        reassigned = runtime.missions.assign_task(
            mission.mission_id,
            "mutable",
            "worker-1",
            expected_revision=assigned.revision,
            reassign=True,
        )
        second_attempt = runtime.attempts.active_for_task("mutable")

        assert runtime.attempts.get(first_attempt.attempt_id).status == "cancelled"
        assert second_attempt.worker_id == "worker-1"
        with pytest.raises(Exception, match="revision conflict"):
            runtime.missions.cancel_task(
                mission.mission_id,
                "mutable",
                expected_revision=assigned.revision,
            )
        cancelled = runtime.missions.cancel_task(
            mission.mission_id,
            "mutable",
            expected_revision=reassigned.revision,
        )
        assert cancelled.status == "cancelled"
        assert runtime.attempts.get(second_attempt.attempt_id).status == "cancelled"


def test_scheduler_lock_renew_and_stale_recovery_are_safe() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = new_runtime(Path(directory) / "data")
        first = SchedulerLock(runtime.data_dir, runtime.events, owner_id="owner-1", timeout_seconds=1)
        competing = SchedulerLock(runtime.data_dir, runtime.events, owner_id="owner-2", timeout_seconds=1)

        assert first.acquire() is True
        assert first.acquire() is True
        assert competing.acquire() is False
        with pytest.raises(RuntimeError, match="Active scheduler lock"):
            competing.recover_stale()
        renewed = first.renew()
        assert renewed.generation >= 2
        time.sleep(1.1)
        assert competing.recover_stale() is True
        assert competing.recover_stale() is True
        assert competing.acquire() is True
        assert competing.release() is True


def test_recovery_apply_is_operational_and_idempotent() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = new_runtime(Path(directory) / "data", ControlledExecutionAdapter())
        register_workers(runtime, 1)
        mission, _ = plan_mission(
            runtime,
            [{"title": "Recover", "objective": "Recover", "task_id": "recover", "required_capabilities": ["work"]}],
        )
        runtime.missions.update_mission(mission.mission_id, status="running")
        runtime.missions.dispatch_ready_tasks(mission.mission_id, execute=False)
        attempt = runtime.attempts.active_for_task("recover")
        runtime.attempts.transition(attempt.attempt_id, "assigned")
        runtime.attempts.transition(attempt.attempt_id, "accepted")
        runtime.attempts.transition(attempt.attempt_id, "running")
        runtime.attempts.transition(attempt.attempt_id, "failed", error={"type": "controlled"})

        assert runtime.commands.execute(runtime.context(), f"/recovery-show {attempt.attempt_id}").status == "ok"
        assert runtime.commands.execute(runtime.context(), f"/recovery-options {attempt.attempt_id}").status == "ok"
        assert runtime.commands.execute(runtime.context(), f"/recovery-list {mission.mission_id}").data["items"]

        applied = runtime.mission_recovery.apply(
            attempt.attempt_id,
            "pause_mission",
            idempotency_key="pause-after-failure",
        )
        repeated = runtime.mission_recovery.apply(
            attempt.attempt_id,
            "pause_mission",
            idempotency_key="pause-after-failure",
        )

        assert applied.status == "paused"
        assert repeated.revision == applied.revision
        assert runtime.attempts.get(attempt.attempt_id).error["type"] == "controlled"


def test_planning_commands_use_versioned_planner_and_dag() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = new_runtime(Path(directory) / "data", ControlledExecutionAdapter())
        mission = runtime.missions.create_mission("Command planning")
        first_tasks = [
            {"title": "A", "objective": "A", "task_id": "a"},
            {"title": "B", "objective": "B", "task_id": "b", "dependencies": ["a"]},
        ]
        encoded = json.dumps(first_tasks)

        validated = runtime.commands.execute(
            runtime.context(),
            f"/mission-plan-validate {mission.mission_id} {encoded}",
        )
        created = runtime.commands.execute(
            runtime.context(),
            f"/mission-plan {mission.mission_id} {encoded}",
        )
        plan_id = created.data["plan_id"]
        replacement_tasks = [
            {"title": "Only", "objective": "Only", "task_id": "only"}
        ]
        replaced = runtime.commands.execute(
            runtime.context(),
            f"/mission-plan-replace {mission.mission_id} {plan_id} 1 {json.dumps(replacement_tasks)}",
        )
        history = runtime.commands.execute(
            runtime.context(),
            f"/mission-plan-history {mission.mission_id}",
        )
        ready = runtime.commands.execute(
            runtime.context(),
            f"/mission-ready-tasks {mission.mission_id}",
        )
        graph = runtime.commands.execute(
            runtime.context(),
            f"/mission-dependency-graph {mission.mission_id}",
        )

        assert validated.data["valid"] is True
        assert replaced.data["version"] == 2
        assert len(history.data["plans"]) == 2
        assert ready.data["tasks"][0]["task_id"] == "only"
        assert graph.data["topological_order"] == ["only"]


def test_dlq_review_restore_creates_one_new_attempt_and_preserves_entry() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = new_runtime(Path(directory) / "data", ControlledExecutionAdapter())
        register_workers(runtime, 1)
        mission, _ = plan_mission(
            runtime,
            [{"title": "DLQ", "objective": "Restore", "task_id": "dlq-task", "required_capabilities": ["work"]}],
        )
        runtime.missions.dispatch_ready_tasks(mission.mission_id, execute=False)
        attempt = runtime.attempts.active_for_task("dlq-task")
        runtime.attempts.transition(attempt.attempt_id, "timed_out", error={"type": "timeout"})
        entry = runtime.mission_recovery.dead_letter_attempt(attempt.attempt_id, "timeout_exceeded")
        runtime.dead_letter.review_entry(entry.dlq_id)

        restored = runtime.mission_recovery.restore_dead_letter(entry.dlq_id)
        repeated = runtime.mission_recovery.restore_dead_letter(entry.dlq_id)
        persisted = runtime.dead_letter.get_entry(entry.dlq_id)

        assert restored.attempt_id != attempt.attempt_id
        assert repeated.attempt_id == restored.attempt_id
        assert persisted.status == "restored"
        assert persisted.metadata["restored_attempt_id"] == restored.attempt_id
        assert len(runtime.attempts.list(task_id="dlq-task")) == 2
