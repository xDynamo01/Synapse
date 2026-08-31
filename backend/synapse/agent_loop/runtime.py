from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from synapse.agent_loop.errors import (
    ActionExecutionFailed,
    ActionNotSupported,
    LoopInvalidState,
    LoopLockActive,
)
from synapse.agent_loop.memory import MemoryCommitPolicy
from synapse.agent_loop.models import (
    VALID_TRANSITIONS,
    ActionResult,
    AgentLoopState,
    CycleResult,
    now_iso,
)
from synapse.agent_loop.ports import Notification, NotificationSink
from synapse.attention.decision import DecisionRuntime
from synapse.attention.errors import DecisionExpired
from synapse.attention.models import AttentionItem, Decision
from synapse.attention.runtime import AttentionRuntime
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import dump_json, load_structured_file
from synapse.world_state.models import WorldStateUpdate
from synapse.world_state.runtime import WorldStateRuntime

if TYPE_CHECKING:
    from synapse.tools.contracts import ToolExecutionPort


class AgentLoopRuntime:
    """Bounded coordinator. Domain side effects are routed only through canonical runtimes."""

    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        world_state: WorldStateRuntime,
        attention: AttentionRuntime,
        decision_runtime: DecisionRuntime,
        *,
        chat_runtime: Any | None = None,
        tool_runtime: ToolExecutionPort | None = None,
        mission_runtime: Any | None = None,
        approval_runtime: Any | None = None,
        notification_sink: NotificationSink | None = None,
        insight_runtime: Any | None = None,
        desktop_runtime: Any | None = None,
        memory_policy: MemoryCommitPolicy | None = None,
        default_actor_id: str = "local-user",
        max_work_per_cycle: int = 1,
        cycle_interval_seconds: int = 30,
    ) -> None:
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.world_state = world_state
        self.attention = attention
        self.decision_runtime = decision_runtime
        self.chat_runtime = chat_runtime
        self.tool_runtime = tool_runtime
        self.mission_runtime = mission_runtime
        self.approval_runtime = approval_runtime
        self.notification_sink = notification_sink
        self.insight_runtime = insight_runtime
        self.desktop_runtime = desktop_runtime
        self.memory_policy = memory_policy or MemoryCommitPolicy()
        self.default_actor_id = default_actor_id
        self.max_work_per_cycle = max(1, max_work_per_cycle)
        self.cycle_interval_seconds = max(1, cycle_interval_seconds)
        self.root = data_dir.resolve("agent_loop")
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.cycles_path = self.root / "cycles.jsonl"
        self.decisions_root = self.root / "decisions"
        self.executions_root = self.root / "executions"
        self.lock_path = self.root / "cycle.lock"
        self.decisions_root.mkdir(parents=True, exist_ok=True)
        self.executions_root.mkdir(parents=True, exist_ok=True)
        self._mutex = RLock()
        if not self.state_path.exists():
            dump_json(self.state_path, asdict(AgentLoopState()))

    def status(self) -> AgentLoopState:
        raw = load_structured_file(self.state_path)
        allowed = AgentLoopState.__dataclass_fields__
        return AgentLoopState(**{key: value for key, value in raw.items() if key in allowed})

    def start(self) -> AgentLoopState:
        state = self.status()
        if state.state in {
            "idle",
            "observing",
            "evaluating",
            "deciding",
            "executing",
            "verifying",
            "committing",
        }:
            return state
        state = self._transition("starting")
        return self._transition("idle", error=None)

    def pause(self) -> AgentLoopState:
        state = self._transition("paused")
        self.event_bus.emit("loop.paused", "agent_loop", {"loop_id": state.loop_id})
        return state

    def resume(self) -> AgentLoopState:
        return self._transition("idle")

    def stop(self) -> AgentLoopState:
        state = self.status()
        if state.state == "stopped":
            return state
        self._transition("stopping")
        self.lock_path.unlink(missing_ok=True)
        return self._transition("stopped")

    def run_cycle(self, trigger: str | None = None) -> CycleResult:
        with self._mutex:
            state = self.status()
            if state.state in {"stopped", "failed"}:
                self.start()
            elif state.state == "paused":
                raise LoopInvalidState("Agent Loop is paused")
            self._acquire_lock()
        cycle_id = str(uuid4())
        started = now_iso()
        self.event_bus.emit(
            "loop.cycle_started", "agent_loop", {"cycle_id": cycle_id, "trigger": trigger}
        )
        try:
            self.world_state.reconcile_state()
            self._transition("observing", last_cycle_at=started)
            self._transition("evaluating")
            resumed = self._approved_execution()
            item = resumed[0] if resumed else self.attention.next_eligible()
            if item is None:
                return self._complete_cycle(
                    CycleResult(
                        cycle_id=cycle_id,
                        trigger=trigger,
                        started_at=started,
                        completed_at=now_iso(),
                        world_state_revision=self.world_state.snapshot().revision,
                    )
                )
            self.attention.mark_processing(item.id)
            self._transition("deciding", current_attention_id=item.id)
            decision = (
                resumed[1]
                if resumed
                else self.decision_runtime.decide(item, self.world_state.snapshot())
            )
            if not resumed and self.insight_runtime is not None:
                guidance = self.insight_runtime.agent_loop_guidance()
                if not guidance["sufficient"] and decision.disposition != "record_only":
                    decision = replace(
                        decision,
                        disposition="record_only",
                        reason=f"{decision.reason} Resource pressure limited autonomy: {guidance['reason']}",
                        selected_action=None,
                        approval_required=False,
                        metadata={
                            **decision.metadata,
                            "resource_pressure": {
                                "maximum_disposition": guidance["maximum_disposition"],
                                "reason": guidance["reason"],
                                "evidence": [asdict(item) for item in guidance["evidence"]],
                            },
                        },
                    )
            self._persist_decision(decision)
            self._transition("deciding", current_decision_id=decision.id)
            if decision.approval_required:
                action_result = self._request_approval(item, decision)
                self._transition("awaiting_approval")
                self.attention.defer(item.id)
                return self._complete_cycle(
                    CycleResult(
                        cycle_id=cycle_id,
                        trigger=trigger,
                        attention_item_id=item.id,
                        decision_id=decision.id,
                        disposition=decision.disposition,
                        action_result=action_result,
                        started_at=started,
                        completed_at=now_iso(),
                        world_state_revision=self.world_state.snapshot().revision,
                    ),
                    final_state="idle",
                )
            action_result = self._execute_idempotent(item, decision)
            self._transition("committing")
            context = PermissionContext(actor_id=self.default_actor_id, actor_type="user")
            commit = self.memory_policy.commit(item, decision, action_result, context=context)
            if decision.disposition == "defer":
                self.attention.defer(item.id)
            elif action_result.status == "completed" and action_result.verification.get(
                "verified", False
            ):
                self.attention.resolve(item.id)
            else:
                self.attention.fail(item.id, "action_verification_failed")
            self._update_world_state(item, decision, action_result)
            return self._complete_cycle(
                CycleResult(
                    cycle_id=cycle_id,
                    trigger=trigger,
                    attention_item_id=item.id,
                    decision_id=decision.id,
                    disposition=decision.disposition,
                    action_result=action_result,
                    commit_result=commit,
                    started_at=started,
                    completed_at=now_iso(),
                    world_state_revision=self.world_state.snapshot().revision,
                )
            )
        except Exception as exc:
            self.event_bus.emit(
                "loop.degraded",
                "agent_loop",
                {"cycle_id": cycle_id, "error_code": getattr(exc, "code", type(exc).__name__)},
            )
            self._force_state(
                "degraded",
                error={"code": getattr(exc, "code", type(exc).__name__), "message": str(exc)},
            )
            result = CycleResult(
                cycle_id=cycle_id,
                status="failed",
                trigger=trigger,
                errors=[{"code": getattr(exc, "code", type(exc).__name__), "message": str(exc)}],
                started_at=started,
                completed_at=now_iso(),
                world_state_revision=self.world_state.snapshot().revision,
            )
            self._append_cycle(result)
            return result
        finally:
            self._release_lock()

    def list_cycles(self, limit: int = 100) -> list[CycleResult]:
        if not self.cycles_path.exists():
            return []
        rows = self.cycles_path.read_text(encoding="utf-8").splitlines()[-max(0, limit) :]
        results = []
        for row in rows:
            raw = json.loads(row)
            if raw.get("action_result"):
                raw["action_result"] = ActionResult(**raw["action_result"])
            if raw.get("commit_result"):
                from synapse.agent_loop.models import CommitResult

                raw["commit_result"] = CommitResult(**raw["commit_result"])
            results.append(CycleResult(**raw))
        return results

    def pending_approvals(self) -> list[Any]:
        return self.approval_runtime.list_pending() if self.approval_runtime else []

    def health(self) -> dict[str, Any]:
        state = self.status()
        return {
            "status": "degraded" if state.state in {"degraded", "failed"} else "healthy",
            "state": state.state,
            "lock_active": self.lock_path.exists(),
            "last_cycle": state.last_cycle_at,
            "last_error": state.error,
            "scheduler_integration": "one_shot_ready",
            "notification_sink": self.notification_sink is not None,
            "adapters": {
                "chat": self.chat_runtime is not None,
                "tools": self.tool_runtime is not None,
                "missions": self.mission_runtime is not None,
                "approvals": self.approval_runtime is not None,
                "desktop_automation": self.desktop_runtime is not None,
            },
        }

    def recover_stale_lock(self, stale_after_seconds: int = 300) -> bool:
        if not self.lock_path.exists():
            return False
        raw = load_structured_file(self.lock_path)
        created = _instant(str(raw.get("created_at", "1970-01-01T00:00:00+00:00")))
        if (datetime.now(UTC) - created).total_seconds() <= stale_after_seconds:
            return False
        self.lock_path.unlink(missing_ok=True)
        self.event_bus.emit(
            "loop.lock_recovered", "agent_loop", {"previous_owner": raw.get("owner")}
        )
        return True

    def _execute_idempotent(self, item: AttentionItem, decision: Decision) -> ActionResult:
        if decision.expires_at and _instant(decision.expires_at) <= datetime.now(UTC):
            raise DecisionExpired(f"Decision expired: {decision.id}")
        path = self.executions_root / f"{decision.id}.json"
        if path.exists():
            raw = load_structured_file(path)
            if raw.get("action_result"):
                return ActionResult(**raw["action_result"])
            if raw.get("status") != "authorized":
                return ActionResult(
                    status="failed",
                    output_reference=None,
                    evidence=[{"execution_ledger": str(path), "state": raw.get("status")}],
                    side_effects=[],
                    errors=[
                        {
                            "code": "execution_outcome_unknown",
                            "message": "Execution started before restart; action was not repeated.",
                        }
                    ],
                    verification={"verified": False, "reason": "outcome_unknown_after_restart"},
                    started_at=str(raw.get("started_at", now_iso())),
                    completed_at=now_iso(),
                    trace_id=decision.trace_id,
                )
        dump_json(
            path,
            {
                "status": "started",
                "started_at": now_iso(),
                "decision_id": decision.id,
                "trace_id": decision.trace_id,
            },
        )
        self._transition("executing")
        self.event_bus.emit(
            "loop.action_started",
            "agent_loop",
            {"decision_id": decision.id, "trace_id": decision.trace_id},
        )
        try:
            result = self._execute(item, decision)
            self._transition("verifying")
            dump_json(
                path,
                {
                    "status": "completed",
                    "decision_id": decision.id,
                    "action_result": asdict(result),
                },
            )
            self.event_bus.emit(
                "loop.action_completed",
                "agent_loop",
                {
                    "decision_id": decision.id,
                    "status": result.status,
                    "trace_id": decision.trace_id,
                },
            )
            return result
        except Exception as exc:
            result = ActionResult(
                status="failed",
                output_reference=None,
                evidence=[],
                side_effects=[],
                errors=[{"code": getattr(exc, "code", type(exc).__name__), "message": str(exc)}],
                verification={"verified": False},
                started_at=now_iso(),
                completed_at=now_iso(),
                trace_id=decision.trace_id,
            )
            dump_json(
                path,
                {"status": "failed", "decision_id": decision.id, "action_result": asdict(result)},
            )
            self.event_bus.emit(
                "loop.action_failed",
                "agent_loop",
                {
                    "decision_id": decision.id,
                    "error_code": result.errors[0]["code"],
                    "trace_id": decision.trace_id,
                },
            )
            return result

    def _execute(self, item: AttentionItem, decision: Decision) -> ActionResult:
        started = now_iso()
        disposition = decision.disposition
        if disposition in {"ignore", "record_only", "defer"}:
            return ActionResult(
                "completed",
                None,
                [{"disposition": disposition}],
                [],
                [],
                {"verified": True},
                started,
                now_iso(),
                decision.trace_id,
            )
        if disposition in {"notify", "suggest", "escalate"}:
            if self.notification_sink is None:
                raise ActionExecutionFailed("Notification sink is unavailable")
            saved = self.notification_sink.notify(
                Notification(
                    type=item.type,
                    title=item.title,
                    summary=item.summary,
                    severity=item.severity,
                    entity_refs=item.entity_refs,
                    expires_at=item.expires_at,
                    correlation_id=item.correlation_id,
                    metadata={"attention_item_id": item.id},
                )
            )
            ref = {"notification_id": getattr(saved, "id", None)}
            return ActionResult(
                "completed",
                ref,
                [ref],
                ["notification_persisted"],
                [],
                {"verified": bool(ref["notification_id"])},
                started,
                now_iso(),
                decision.trace_id,
            )
        if disposition == "respond":
            if self.chat_runtime is None:
                raise ActionExecutionFailed("ChatRuntime is unavailable")
            action = decision.selected_action or {}
            agent_id = decision.selected_agent or str(action.get("agent_id") or "")
            if not agent_id:
                raise ActionExecutionFailed("Response agent is required")
            result = self.chat_runtime.send_message(
                PermissionContext(actor_id=self.default_actor_id, actor_type="user"),
                agent_id,
                str(action.get("message") or item.summary),
                project_id=action.get("project_id"),
                session_id=action.get("session_id"),
            )
            session_id = result.session.id
            persisted = self.chat_runtime.get_session(session_id)
            ref = {"session_id": session_id}
            return ActionResult(
                "completed",
                ref,
                [{"message_count": len(persisted.messages)}],
                ["chat_message_persisted"],
                [],
                {"verified": len(persisted.messages) > 0},
                started,
                now_iso(),
                decision.trace_id,
            )
        if disposition == "execute_reversible_action":
            action = decision.selected_action or {}
            desktop_plan_id = str(action.get("desktop_plan_id") or "")
            if desktop_plan_id:
                if self.desktop_runtime is None:
                    raise ActionExecutionFailed("DesktopRuntime is unavailable")
                if not self.desktop_runtime.is_reversible(desktop_plan_id):
                    raise ActionExecutionFailed(
                        "Agent Loop may execute only reversible desktop plans"
                    )
                from synapse.tools.identities import DESKTOP_EXECUTE
                from synapse.tools.models import ToolExecutionRequest

                tool_runtime = cast("ToolExecutionPort", self.tool_runtime)
                execution = tool_runtime.execute(
                    ToolExecutionRequest(
                        tool_id=DESKTOP_EXECUTE,
                        arguments={"plan_id": desktop_plan_id},
                        caller=decision.selected_agent or "agent_loop",
                        caller_type="agent",
                        correlation_id=item.correlation_id,
                        idempotency_key=decision.id,
                        metadata={"selected_agent": decision.selected_agent},
                    )
                )
                result = execution.output
                ref = {"desktop_plan_id": desktop_plan_id}
                verified = result.get("status") in {"completed", "dry_run"} and all(
                    action.get("verification", {}).get("verified", False)
                    for action in result.get("actions", [])
                )
                return ActionResult(
                    str(result.get("status", execution.status)),
                    ref,
                    [{"desktop_plan_id": desktop_plan_id, "status": result.get("status")}],
                    ["desktop_automation_delegated"] if result.get("status") == "completed" else [],
                    []
                    if verified
                    else [{"code": result.get("error_code") or result.get("status")}],
                    {"verified": verified},
                    started,
                    now_iso(),
                    decision.trace_id,
                )
            if self.tool_runtime is None:
                raise ActionExecutionFailed("ToolRuntime is unavailable")
            if hasattr(self.tool_runtime, "get_tool"):
                definition = self.tool_runtime.get_tool(str(action.get("tool_id", "")))
                reversible = bool(
                    getattr(definition, "supports_rollback", False)
                    or definition.metadata.get("reversible", False)
                )
                if not reversible:
                    raise ActionExecutionFailed("Tool is not declared reversible")
            from synapse.tools.models import ToolExecutionRequest

            result = self.tool_runtime.execute(
                ToolExecutionRequest(
                    tool_id=str(action.get("tool_id", "")),
                    arguments=dict(action.get("arguments", {})),
                    caller="agent_loop",
                    caller_type="agent",
                    agent_id=decision.selected_agent,
                    correlation_id=item.correlation_id,
                    idempotency_key=decision.id,
                )
            )
            ref = {"call_id": result.call_id, "tool_id": result.tool_id}
            verified = bool(result.success and result.status == "completed")
            return ActionResult(
                result.status,
                ref,
                [result.output],
                list(result.side_effects),
                [] if result.success else [{"code": "tool_failed", "message": result.error}],
                {"verified": verified},
                started,
                now_iso(),
                decision.trace_id,
            )
        if disposition == "start_mission":
            if self.mission_runtime is None:
                raise ActionExecutionFailed("MissionRuntime is unavailable")
            action = decision.selected_action or {}
            mission = self.mission_runtime.create_mission(
                title=str(action.get("title") or item.title),
                description=str(action.get("description") or item.summary),
                objective=str(action.get("objective") or item.summary),
                status="ready",
                priority=str(action.get("priority") or "normal"),
                owner_agent_id=decision.selected_agent,
                created_by="agent_loop",
                metadata={"attention_item_id": item.id, "decision_id": decision.id},
            )
            ref = {"mission_id": mission.mission_id}
            persisted = self.mission_runtime.get_mission(mission.mission_id)
            return ActionResult(
                "completed",
                ref,
                [ref],
                ["mission_created"],
                [],
                {"verified": persisted.mission_id == mission.mission_id},
                started,
                now_iso(),
                decision.trace_id,
            )
        raise ActionNotSupported(f"Unsupported disposition: {disposition}")

    def _request_approval(self, item: AttentionItem, decision: Decision) -> ActionResult:
        started = now_iso()
        if self.approval_runtime is None:
            return ActionResult(
                "awaiting_approval",
                None,
                [],
                [],
                [{"code": "approval_runtime_unavailable"}],
                {"verified": False},
                started,
                now_iso(),
                decision.trace_id,
            )
        action = decision.selected_action or {}
        request = self.approval_runtime.create_request(
            PermissionContext(actor_id=self.default_actor_id, actor_type="user"),
            tool_name=str(action.get("tool_id") or decision.disposition),
            tool_args=dict(action.get("arguments", {})),
            risk_level=_approval_risk(decision.risk),
            reason=decision.reason,
            tool_call_id=decision.id,
        )
        ref = {"approval_id": request.id}
        dump_json(
            self.executions_root / f"{decision.id}.json",
            {
                "status": "awaiting_approval",
                "decision_id": decision.id,
                "attention_item_id": item.id,
                "approval_id": request.id,
                "started_at": started,
            },
        )
        return ActionResult(
            "awaiting_approval",
            ref,
            [ref],
            ["approval_requested"],
            [],
            {"verified": True},
            started,
            now_iso(),
            decision.trace_id,
        )

    def _approved_execution(self) -> tuple[AttentionItem, Decision] | None:
        if self.approval_runtime is None:
            return None
        for path in sorted(self.executions_root.glob("*.json")):
            raw = load_structured_file(path)
            if raw.get("status") != "awaiting_approval":
                continue
            try:
                approval = self.approval_runtime.get_status(str(raw["approval_id"]))
            except Exception:
                continue
            if approval.status == "pending":
                continue
            item = self.attention.get_item(str(raw["attention_item_id"]))
            decision_raw = load_structured_file(self.decisions_root / f"{raw['decision_id']}.json")
            decision = Decision(**decision_raw)
            if decision.expires_at and _instant(decision.expires_at) <= datetime.now(UTC):
                dump_json(path, {**raw, "status": "expired", "completed_at": now_iso()})
                self.attention.fail(item.id, "decision_expired")
                continue
            if approval.status != "approved":
                dump_json(path, {**raw, "status": "rejected", "completed_at": now_iso()})
                self.attention.resolve(item.id)
                continue
            approved_disposition = str(
                decision.metadata.get("requested_disposition", "record_only")
            )
            if approved_disposition not in {
                "respond",
                "execute_reversible_action",
                "start_mission",
            }:
                approved_disposition = "record_only"
            authorized = replace(
                decision,
                disposition=approved_disposition,
                approval_required=False,
                metadata={
                    **decision.metadata,
                    "approval_id": approval.id,
                    "approval_status": "approved",
                },
            )
            dump_json(path, {**raw, "status": "authorized", "authorized_at": now_iso()})
            return item, authorized
        return None

    def _update_world_state(
        self, item: AttentionItem, decision: Decision, result: ActionResult
    ) -> None:
        self.world_state.apply_state_update(
            WorldStateUpdate(
                id=f"loop-result:{decision.id}",
                source="agent_loop",
                entity_type="attention_summary",
                operation="merge",
                values={
                    "last_attention_id": item.id,
                    "last_decision_id": decision.id,
                    "last_disposition": decision.disposition,
                    "last_result_status": result.status,
                    "updated_at": now_iso(),
                },
                timestamp=now_iso(),
                correlation_id=item.correlation_id,
                provenance={"trace_id": decision.trace_id},
            )
        )

    def _complete_cycle(self, result: CycleResult, final_state: str = "idle") -> CycleResult:
        next_at = (datetime.now(UTC) + timedelta(seconds=self.cycle_interval_seconds)).isoformat()
        completed = replace(result, next_cycle_at=next_at)
        self._append_cycle(completed)
        self._force_state(
            final_state,
            previous_state=self.status().state,
            last_cycle_at=completed.completed_at,
            next_cycle_at=next_at,
            current_attention_id=None,
            current_decision_id=None,
            current_execution_ref=None,
            error=None,
        )
        self.event_bus.emit(
            "loop.cycle_completed",
            "agent_loop",
            {
                "cycle_id": result.cycle_id,
                "status": result.status,
                "attention_item_id": result.attention_item_id,
            },
        )
        return completed

    def _transition(self, target: str, **changes: Any) -> AgentLoopState:
        current = self.status()
        if target == current.state:
            return self._force_state(target, **changes) if changes else current
        if target not in VALID_TRANSITIONS.get(current.state, set()):
            raise LoopInvalidState(f"Invalid loop transition: {current.state} -> {target}")
        return self._force_state(target, previous_state=current.state, **changes)

    def _force_state(self, target: str, **changes: Any) -> AgentLoopState:
        current = self.status()
        updated = replace(current, state=target, revision=current.revision + 1, **changes)
        dump_json(self.state_path, asdict(updated))
        self.event_bus.emit(
            "loop.state_changed",
            "agent_loop",
            {
                "loop_id": updated.loop_id,
                "state": target,
                "previous_state": updated.previous_state,
                "revision": updated.revision,
            },
        )
        return updated

    def _persist_decision(self, decision: Decision) -> None:
        dump_json(self.decisions_root / f"{decision.id}.json", asdict(decision))

    def _append_cycle(self, result: CycleResult) -> None:
        with self.cycles_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(result), sort_keys=True) + "\n")

    def _acquire_lock(self) -> None:
        self.recover_stale_lock()
        try:
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise LoopLockActive("Another Agent Loop cycle owns the lock") from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"owner": os.getpid(), "created_at": now_iso()}, handle)

    def _release_lock(self) -> None:
        self.lock_path.unlink(missing_ok=True)


def _instant(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)


def _approval_risk(value: str) -> str:
    return {"informational": "low", "critical": "critical"}.get(
        value, value if value in {"low", "medium", "high", "critical"} else "high"
    )
