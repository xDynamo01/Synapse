from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.missions.dag import TaskGraph
from synapse.missions.errors import AttemptConflict, DependencyCycle, NoWorkerAvailable, PlanInvalid
from synapse.missions.models import MissionTask, WorkerDescriptor


def runtime_in_tempdir():
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=Path(__file__).resolve().parents[1],
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    return directory, create_runtime(settings)


def test_planner_persists_manual_plan_and_validates_dag() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        mission = runtime.missions.create_mission("Plan work", objective="Deliver verified work")
        first = MissionTask(mission.mission_id, "Research", "Research facts", task_id="research")
        second = MissionTask(mission.mission_id, "Write", "Write result", dependencies=["research"], task_id="write")
        plan = runtime.planner.create_plan(mission.mission_id, mission.objective, tasks=[first, second])

        assert plan.validation_result and plan.validation_result.valid
        assert runtime.planner.get_plan(mission.mission_id, plan.plan_id).tasks[1].dependencies == ["research"]
        assert TaskGraph(plan.tasks).topological_order() == ["research", "write"]


def test_planner_rejects_empty_duplicate_missing_and_cycle() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        mission = runtime.missions.create_mission("Invalid plans")
        with pytest.raises(PlanInvalid, match="at least one"):
            runtime.planner.create_plan(mission.mission_id, mission.objective, tasks=[])
        duplicate = [
            MissionTask(mission.mission_id, "A", "A", task_id="same"),
            MissionTask(mission.mission_id, "B", "B", task_id="same"),
        ]
        with pytest.raises(PlanInvalid, match="unique"):
            runtime.planner.create_plan(mission.mission_id, mission.objective, tasks=duplicate)
        missing = MissionTask(mission.mission_id, "A", "A", dependencies=["missing"], task_id="a")
        with pytest.raises(PlanInvalid, match="missing dependencies"):
            runtime.planner.create_plan(mission.mission_id, mission.objective, tasks=[missing])
        cyclic = [
            MissionTask(mission.mission_id, "A", "A", dependencies=["b"], task_id="a"),
            MissionTask(mission.mission_id, "B", "B", dependencies=["a"], task_id="b"),
        ]
        with pytest.raises(PlanInvalid, match="cycle"):
            runtime.planner.create_plan(mission.mission_id, mission.objective, tasks=cyclic)


def test_graph_fan_out_fan_in_and_unlock() -> None:
    tasks = [
        MissionTask("m", "Root", "Root", status="completed", task_id="root"),
        MissionTask("m", "Left", "Left", dependencies=["root"], task_id="left"),
        MissionTask("m", "Right", "Right", dependencies=["root"], task_id="right"),
        MissionTask("m", "Join", "Join", dependencies=["left", "right"], task_id="join"),
    ]
    graph = TaskGraph(tasks)
    assert [task.task_id for task in graph.ready_tasks()] == ["left", "right"]
    assert [task.task_id for task in graph.unlock_after_completion("root")] == ["left", "right"]
    with pytest.raises(DependencyCycle):
        graph.add_dependency("root", "join")


def test_worker_registry_selection_heartbeat_and_stale() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        runtime.worker_registry.register(WorkerDescriptor("worker-b", "agent-b", "idle", ["research"], workload=0.7))
        runtime.worker_registry.register(WorkerDescriptor("worker-a", "agent-a", "idle", ["research"], workload=0.2))
        task = MissionTask("m", "Research", "Research", required_capabilities=["research"])
        selected = runtime.worker_scheduler.select_worker(task)
        assert selected.selected_worker == "worker-a"
        assert selected.reason
        assert runtime.worker_registry.heartbeat("worker-a").last_heartbeat
        runtime.worker_registry.update("worker-a", status="offline")
        runtime.worker_registry.update("worker-b", status="offline")
        with pytest.raises(NoWorkerAvailable):
            runtime.worker_scheduler.select_worker(task)


def test_verifier_requires_real_evidence() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        assert runtime.result_verifier.verify({"output": "done"}).status == "passed"
        assert runtime.result_verifier.verify({"output": ""}).status == "failed"
        result = runtime.result_verifier.verify({"output": '{"ok": true}'}, {"checks": ["json_schema"], "json_schema": {"required": ["ok"]}})
        assert result.status == "passed"


def test_run_mission_assigns_ready_work_idempotently_and_lifecycle() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        mission = runtime.missions.create_mission("Run", objective="Run safely")
        task = MissionTask(mission.mission_id, "Work", "Do work", required_capabilities=["work"], task_id="work")
        plan = runtime.planner.create_plan(mission.mission_id, mission.objective, tasks=[task])
        runtime.missions.attach_plan(mission.mission_id, plan.plan_id)
        runtime.worker_registry.register(WorkerDescriptor("worker", "agent", "idle", ["work"]))

        running = runtime.missions.run_mission(mission.mission_id)
        assert running.status == "running"
        assigned = runtime.planner.get_plan(mission.mission_id, plan.plan_id).tasks[0]
        assert assigned.assigned_worker_id == "worker"
        assert runtime.missions.run_mission(mission.mission_id).progress == 0
        assert runtime.missions.pause(mission.mission_id).status == "paused"
        assert runtime.missions.pause(mission.mission_id).status == "paused"
        assert runtime.missions.resume(mission.mission_id).status == "running"
        assert runtime.missions.cancel(mission.mission_id).status == "cancelled"
        assert runtime.missions.cancel(mission.mission_id).status == "cancelled"


def test_swarm_strategies_are_real_and_bounded() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        mission = runtime.missions.create_mission("Swarm")
        for strategy in runtime.swarm.STRATEGIES:
            swarm = runtime.swarm.create(mission.mission_id, strategy, "leader", ["worker", "reviewer"], {"max_iterations": 2})
            assert runtime.swarm.get(swarm.swarm_id).strategy == strategy
            assert runtime.swarm.pause(swarm.swarm_id).status == "paused"
            assert runtime.swarm.resume(swarm.swarm_id).status == "running"
            assert runtime.swarm.cancel(swarm.swarm_id).status == "cancelled"


def test_attempt_history_is_idempotent_and_revision_checked() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        first = runtime.attempts.create("mission", "task", "worker", "agent", idempotency_key="dispatch-1")
        assert runtime.attempts.create("mission", "task", "worker", "agent", idempotency_key="dispatch-1") == first
        with pytest.raises(AttemptConflict):
            runtime.attempts.create("mission", "task", "worker", "agent", idempotency_key="dispatch-2")
        assigned = runtime.attempts.transition(first.attempt_id, "assigned", expected_revision=1)
        with pytest.raises(AttemptConflict):
            runtime.attempts.transition(first.attempt_id, "accepted", expected_revision=1)
        accepted = runtime.attempts.transition(first.attempt_id, "accepted", expected_revision=assigned.revision)
        assert accepted.revision == 3


def test_worker_execution_verifies_result_and_releases_worker() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        mission = runtime.missions.create_mission("Execute", objective="Execute once")
        task = MissionTask(mission.mission_id, "Work", "Do work", required_capabilities=["work"], task_id="work")
        plan = runtime.planner.create_plan(mission.mission_id, mission.objective, tasks=[task])
        runtime.missions.attach_plan(mission.mission_id, plan.plan_id)
        runtime.worker_registry.register(WorkerDescriptor("worker", "agent", "idle", ["work"]))
        runtime.missions.run_mission(mission.mission_id)
        attempt = runtime.attempts.list(task_id="work")[0]
        runtime.worker_execution.executor = lambda _attempt, _task, _mission, _worker, _context: {
            "output": "verified"
        }

        completed = runtime.worker_execution.execute_attempt(attempt.attempt_id)

        assert completed.status == "completed"
        assert completed.verification_result["status"] == "passed"
        assert runtime.worker_registry.get("worker").status == "idle"
        assert runtime.planner.get_plan(mission.mission_id, plan.plan_id).tasks[0].status == "completed"


def test_timeout_scan_is_idempotent_and_retry_preserves_history() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        mission = runtime.missions.create_mission("Recover", objective="Recover safely")
        task = MissionTask(mission.mission_id, "Retry", "Retry work", required_capabilities=["work"], task_id="retry")
        plan = runtime.planner.create_plan(mission.mission_id, mission.objective, tasks=[task])
        runtime.missions.attach_plan(mission.mission_id, plan.plan_id)
        runtime.worker_registry.register(WorkerDescriptor("worker", "agent", "idle", ["work"]))
        expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        attempt = runtime.attempts.create(mission.mission_id, task.task_id, "worker", "agent", timeout_at=expired)

        first_scan = runtime.mission_recovery.scan_timeouts()
        second_scan = runtime.mission_recovery.scan_timeouts()
        retry = runtime.mission_recovery.schedule_retry(attempt.attempt_id)

        assert first_scan["attempts"] == [attempt.attempt_id]
        assert second_scan["attempts"] == []
        assert retry.attempt_id != attempt.attempt_id
        assert retry.attempt_number == 2
        assert runtime.attempts.get(attempt.attempt_id).status == "recovery_pending"
        assert len(runtime.attempts.list(task_id=task.task_id)) == 2


def test_mission_trace_is_filterable_and_redacted() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        mission = runtime.missions.create_mission("Trace")
        runtime.events.emit(
            "attempt.created",
            "agent",
            {
                "mission_id": mission.mission_id,
                "task_id": "task",
                "attempt_id": "attempt",
                "status": "created",
                "prompt": "private prompt",
                "metadata": {"token": "secret"},
            },
        )

        trace = runtime.mission_trace.list(mission.mission_id, event_type="attempt.created")

        assert len(trace) == 1
        assert "private prompt" not in str(trace[0])
        assert "secret" not in str(trace[0])
        assert runtime.mission_trace.summarize(mission.mission_id)["total_events"] >= 2


def test_multiworker_dispatch_respects_concurrency_and_unique_workers() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        mission = runtime.missions.create_mission("Parallel dispatch", metadata={"max_concurrency": 2})
        tasks = [
            MissionTask(mission.mission_id, f"Task {index}", f"Work {index}", required_capabilities=["work"], task_id=f"task-{index}")
            for index in range(3)
        ]
        plan = runtime.planner.create_plan(mission.mission_id, mission.objective, tasks=tasks)
        runtime.missions.attach_plan(mission.mission_id, plan.plan_id)
        runtime.worker_registry.register(WorkerDescriptor("worker-a", "agent-a", "idle", ["work"]))
        runtime.worker_registry.register(WorkerDescriptor("worker-b", "agent-b", "idle", ["work"]))

        result = runtime.missions.dispatch_ready_tasks(mission.mission_id, 2, execute=False)
        attempts = runtime.attempts.list(mission_id=mission.mission_id)

        assert len(result.dispatched) == 2
        assert {attempt.worker_id for attempt in attempts} == {"worker-a", "worker-b"}
        assert result.skipped == [{"task_id": "task-2", "reason": "concurrency_limit"}]
        repeated = runtime.missions.dispatch_ready_tasks(mission.mission_id, 2, execute=False)
        assert repeated.dispatched == []
        assert len(runtime.attempts.list(mission_id=mission.mission_id)) == 2


def test_attempt_dead_letter_is_idempotent_redacted_and_archivable() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        attempt = runtime.attempts.create("mission", "task", "worker", "agent", input_snapshot={"secret": "value"})
        runtime.attempts.transition(attempt.attempt_id, "timed_out")

        entry = runtime.mission_recovery.dead_letter_attempt(attempt.attempt_id, "timeout_exceeded")
        repeated = runtime.mission_recovery.dead_letter_attempt(attempt.attempt_id, "timeout_exceeded")

        assert repeated.dlq_id == entry.dlq_id
        assert entry.mission_id == "mission"
        assert entry.attempt_id == attempt.attempt_id
        assert "value" not in str(entry.payload_redacted)
        assert runtime.attempts.get(attempt.attempt_id).status == "dead_lettered"
        runtime.dead_letter.close_entry(entry.dlq_id)
        assert runtime.dead_letter.archive_entry(entry.dlq_id).status == "archived"


def test_scheduler_job_idempotency_pause_resume_and_restart() -> None:
    directory, runtime = runtime_in_tempdir()
    with directory:
        context = runtime.context()
        job = runtime.scheduler.enqueue(
            context,
            "mission_dispatch",
            {"mission_id": "mission", "execute": False},
            target="mission",
            idempotency_key="dispatch-mission",
        )
        repeated = runtime.scheduler.enqueue(
            context,
            "mission_dispatch",
            {"mission_id": "mission", "execute": False},
            target="mission",
            idempotency_key="dispatch-mission",
        )
        assert repeated.id == job.id
        assert runtime.scheduler.pause_job(context, job.id).status == "paused"
        assert runtime.scheduler.resume_job(context, job.id).status == "pending"
        restarted = create_runtime(runtime.settings)
        assert restarted.scheduler.get_job(job.id).idempotency_key == "dispatch-mission"
