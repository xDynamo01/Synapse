from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from synapse.core.events import EventBus

if TYPE_CHECKING:
    from synapse.dead_letter.runtime import DeadLetterRuntime
    from synapse.delegation_recovery.runtime import DelegationRecoveryRuntime
    from synapse.health.contracts import HealthSnapshotSource
    from synapse.missions.context import MissionContextRuntime
    from synapse.missions.runtime import MissionRuntime
    from synapse.readiness.contracts import ReadinessSnapshotSource


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class MissionSupervisionState:
    mission_id: str
    status: str
    severity: str
    health: str
    attention_required: bool
    generated_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MissionAttentionItem:
    mission_id: str
    attention_type: str
    severity: str
    recommendation: str
    description: str
    created_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class MissionSupervisionSummary:
    total_missions: int
    healthy_missions: int
    warning_missions: int
    critical_missions: int
    attention_required_count: int
    generated_at: str = field(default_factory=now_iso)


class MissionSupervisionRuntime:
    def __init__(
        self,
        events: EventBus,
        missions: MissionRuntime,
        mission_context: MissionContextRuntime,
        recovery: DelegationRecoveryRuntime,
        dead_letter: DeadLetterRuntime,
        health: HealthSnapshotSource | None = None,
        readiness: ReadinessSnapshotSource | None = None,
    ):
        self.events = events
        self.missions = missions
        self.mission_context = mission_context
        self.recovery = recovery
        self.dead_letter = dead_letter
        self.health = health
        self.readiness = readiness

    def evaluate_mission(
        self,
        mission_id: str,
        emit_event: bool = True,
    ) -> MissionSupervisionState:
        try:
            context = self.mission_context.build_context(mission_id, emit_event=False)
            severity = context.summary.health
            attention_items = self._attention_items_for_context(context)
            if severity == "healthy" and attention_items:
                severity = "warning"
            state = MissionSupervisionState(
                mission_id=mission_id,
                status=str(context.mission.get("status", "unknown")),
                severity=severity,
                health=context.summary.health,
                attention_required=severity != "healthy" or bool(attention_items),
                metadata={
                    "attention_items": [asdict(item) for item in attention_items],
                    "progress_percent": context.summary.progress_percent,
                    "delegation_count": context.delegation_count,
                    "dlq_count": context.dlq_count,
                    "recovery_candidates_count": len(context.recovery_candidates),
                    "timeout_candidates_count": len(context.timeout_candidates),
                    "failed_tasks_count": len(context.failed_tasks),
                    "health_available": self.health is not None,
                    "readiness_available": self.readiness is not None,
                },
            )
            if emit_event:
                self.events.emit(
                    "mission.supervision.generated", "mission_supervision", asdict(state)
                )
            return state
        except Exception as exc:
            self.events.emit(
                "mission.supervision.failed",
                "mission_supervision",
                {"mission_id": mission_id, "error": str(exc) or type(exc).__name__},
            )
            raise

    def list_attention_items(self) -> list[MissionAttentionItem]:
        items: list[MissionAttentionItem] = []
        for mission in self.missions.list_missions():
            if mission.status == "archived":
                continue
            context = self.mission_context.build_context(mission.mission_id, emit_event=False)
            items.extend(self._attention_items_for_context(context))
        return items

    def build_summary(self) -> MissionSupervisionSummary:
        states = [
            self.evaluate_mission(mission.mission_id, emit_event=False)
            for mission in self.missions.list_missions()
            if mission.status != "archived"
        ]
        healthy = len([state for state in states if state.severity == "healthy"])
        warning = len([state for state in states if state.severity == "warning"])
        critical = len([state for state in states if state.severity == "critical"])
        attention = len([state for state in states if state.attention_required])
        return MissionSupervisionSummary(
            total_missions=len(states),
            healthy_missions=healthy,
            warning_missions=warning,
            critical_missions=critical,
            attention_required_count=attention,
        )

    def list_missions_requiring_attention(self) -> list[MissionSupervisionState]:
        return [
            state
            for state in [
                self.evaluate_mission(mission.mission_id, emit_event=False)
                for mission in self.missions.list_missions()
                if mission.status != "archived"
            ]
            if state.attention_required
        ]

    def mission_status(self, mission_id: str) -> MissionSupervisionState:
        return self.evaluate_mission(mission_id)

    def warning_missions_count(self) -> int:
        return self.build_summary().warning_missions

    def critical_missions_count(self) -> int:
        return self.build_summary().critical_missions

    def _attention_items_for_context(self, context) -> list[MissionAttentionItem]:
        mission_id = str(context.mission["mission_id"])
        items: list[MissionAttentionItem] = []
        for candidate in context.timeout_candidates:
            items.append(
                MissionAttentionItem(
                    mission_id=mission_id,
                    attention_type="timeout_detected",
                    severity="critical" if candidate.get("requires_human_review") else "warning",
                    recommendation="manual_review",
                    description=f"Timeout candidate detected for task {candidate.get('task_id')}.",
                )
            )
        for decision in context.recovery_candidates:
            recommendation = str(decision.get("recommendation", "manual_review"))
            risk_level = str(decision.get("risk_level", "medium"))
            items.append(
                MissionAttentionItem(
                    mission_id=mission_id,
                    attention_type="recovery_required",
                    severity="critical" if risk_level == "critical" else "warning",
                    recommendation=recommendation,
                    description=f"Recovery recommendation {recommendation} for task {decision.get('task_id')}.",
                )
            )
        if context.dlq_count:
            items.append(
                MissionAttentionItem(
                    mission_id=mission_id,
                    attention_type="dead_letter_present",
                    severity="critical",
                    recommendation="restore_from_dlq",
                    description=f"{context.dlq_count} delegation(s) are in the dead letter queue.",
                )
            )
        if context.failed_tasks:
            items.append(
                MissionAttentionItem(
                    mission_id=mission_id,
                    attention_type="failed_tasks",
                    severity="warning",
                    recommendation="investigate_failure",
                    description=f"{len(context.failed_tasks)} delegation task(s) failed.",
                )
            )
        if context.summary.health == "critical":
            items.append(
                MissionAttentionItem(
                    mission_id=mission_id,
                    attention_type="mission_blocked",
                    severity="critical",
                    recommendation="manual_review",
                    description="Mission has critical context and needs human review.",
                )
            )
        return items
