from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from synapse.mission_control.models import (
    MissionControlAgentWorkload,
    MissionControlAttentionPanel,
    MissionControlMissionCard,
    MissionControlOverview,
    MissionControlWorkQueue,
)

if TYPE_CHECKING:
    from synapse.agents.admin import AgentAdminRuntime
    from synapse.delegation.runtime import DelegationRuntime
    from synapse.delegation_inbox.runtime import DelegationInboxRuntime
    from synapse.missions.context import MissionContextRuntime
    from synapse.missions.runtime import MissionRuntime
    from synapse.missions.supervision import MissionSupervisionRuntime


ACTIVE_TASK_STATUSES = {"pending", "accepted", "in_progress"}


class MissionControlRuntime:
    def __init__(
        self,
        missions: MissionRuntime,
        mission_context: MissionContextRuntime,
        mission_supervision: MissionSupervisionRuntime,
        delegation_inbox: DelegationInboxRuntime,
        delegation: DelegationRuntime,
        admin: AgentAdminRuntime | None = None,
        attempts: Any | None = None,
        workers: Any | None = None,
        swarm: Any | None = None,
        dead_letter: Any | None = None,
    ) -> None:
        self.missions = missions
        self.mission_context = mission_context
        self.mission_supervision = mission_supervision
        self.delegation_inbox = delegation_inbox
        self.delegation = delegation
        self.admin = admin
        self.attempts = attempts
        self.workers = workers
        self.swarm = swarm
        self.dead_letter = dead_letter
        self.scheduler: Any | None = None
        self.daemon: Any | None = None

    def operational_snapshot(self) -> dict[str, Any]:
        missions = [
            mission for mission in self.missions.list_missions() if mission.status != "archived"
        ]
        attempts = self.attempts.list() if self.attempts else []
        workers = self.workers.list() if self.workers else []
        swarms = self.swarm.list() if self.swarm else []
        dead_letters = self.dead_letter.list_open_entries() if self.dead_letter else []
        now = datetime.now(UTC)
        categories = {
            "active_missions": [item.mission_id for item in missions if item.status == "running"],
            "queued_missions": [
                item.mission_id for item in missions if item.status in {"planned", "ready", "draft"}
            ],
            "paused_missions": [item.mission_id for item in missions if item.status == "paused"],
            "blocked_missions": [item.mission_id for item in missions if item.status == "blocked"],
            "overdue_missions": [
                item.mission_id
                for item in missions
                if item.deadline
                and datetime.fromisoformat(item.deadline) <= now
                and item.status not in {"completed", "cancelled", "failed"}
            ],
            "failed_missions": [item.mission_id for item in missions if item.status == "failed"],
            "waiting_approval_attempts": [
                item.attempt_id for item in attempts if item.status == "waiting_approval"
            ],
            "active_attempts": [
                item.attempt_id
                for item in attempts
                if item.status
                in {"assigned", "accepted", "running", "waiting_tool", "waiting_model"}
            ],
            "recovery_queue": [
                item.attempt_id for item in attempts if item.status == "recovery_pending"
            ],
            "stale_workers": [item.worker_id for item in workers if item.status == "offline"],
            "overloaded_workers": [item.worker_id for item in workers if item.workload >= 0.9],
            "dead_letters": [item.dlq_id for item in dead_letters],
            "swarms": [
                {"swarm_id": item.swarm_id, "status": item.status, "mission_id": item.mission_id}
                for item in swarms
            ],
        }
        attention: list[dict[str, Any]] = []
        for key in (
            "blocked_missions",
            "overdue_missions",
            "failed_missions",
            "waiting_approval_attempts",
            "recovery_queue",
            "stale_workers",
            "dead_letters",
        ):
            for entity_id in categories[key]:
                attention.append(
                    {
                        "reason": key,
                        "severity": "critical"
                        if key in {"failed_missions", "dead_letters"}
                        else "warning",
                        "entity_id": entity_id,
                        "trace_reference": f"mission:{entity_id}" if "mission" in key else None,
                        "suggested_action": self._suggested_action(key),
                        "approval_required": key == "waiting_approval_attempts",
                    }
                )
        return {
            **categories,
            "scheduler": {"pending_jobs": len(self.scheduler.queue.list(status="pending"))}
            if self.scheduler
            else None,
            "daemon": asdict(self.daemon.status()) if self.daemon else None,
            "attention_items": attention,
        }

    @staticmethod
    def _suggested_action(reason: str) -> str:
        return {
            "blocked_missions": "inspect_dependencies",
            "overdue_missions": "evaluate_timeout",
            "failed_missions": "evaluate_recovery",
            "waiting_approval_attempts": "review_approval",
            "recovery_queue": "apply_recovery",
            "stale_workers": "replace_worker",
            "dead_letters": "review_dead_letter",
        }[reason]

    def get_overview(self) -> MissionControlOverview:
        supervision = self.mission_supervision.build_summary()
        cards = [
            asdict(self.get_mission_card(mission.mission_id))
            for mission in self.missions.list_missions()
            if mission.status != "archived"
        ]
        attention = self.get_attention_panel()
        active_missions = len(
            [mission for mission in self.missions.list_missions() if mission.status == "active"]
        )
        return MissionControlOverview(
            total_missions=supervision.total_missions,
            active_missions=active_missions,
            warning_missions=supervision.warning_missions,
            critical_missions=supervision.critical_missions,
            attention_required_count=supervision.attention_required_count,
            mission_cards=cards,
            global_attention_items=attention.items,
        )

    def get_mission_card(self, mission_id: str) -> MissionControlMissionCard:
        mission = self.missions.get_mission(mission_id)
        context = self.mission_context.build_context(mission_id, emit_event=False)
        supervision = self.mission_supervision.evaluate_mission(mission_id, emit_event=False)
        return MissionControlMissionCard(
            mission_id=mission.mission_id,
            title=mission.title,
            status=mission.status,
            priority=mission.priority,
            health=context.summary.health,
            progress_percent=context.summary.progress_percent,
            total_tasks=context.delegation_count,
            active_tasks=len(context.active_tasks),
            completed_tasks=len(context.completed_tasks),
            failed_tasks=len(context.failed_tasks),
            dlq_tasks=context.dlq_count,
            attention_required=supervision.attention_required,
            top_recommendations=self._top_recommendations(
                context.summary.recommendations,
                supervision.metadata.get("attention_items", []),
            ),
        )

    def get_attention_panel(self) -> MissionControlAttentionPanel:
        items = [asdict(item) for item in self.mission_supervision.list_attention_items()]
        return MissionControlAttentionPanel(
            total_items=len(items),
            critical_items=len([item for item in items if item.get("severity") == "critical"]),
            warning_items=len([item for item in items if item.get("severity") == "warning"]),
            items=items,
        )

    def get_work_queue(self, agent_id: str | None = None) -> MissionControlWorkQueue:
        items: list[dict[str, Any]] = []
        for current_agent_id in self._work_queue_agent_ids(agent_id):
            entries = self.delegation_inbox.get_active_tasks(current_agent_id)
            for entry in entries:
                task = self.delegation.get_task(entry.task_id)
                items.append(
                    {
                        "agent_id": current_agent_id,
                        "task_id": task.task_id,
                        "title": task.title,
                        "status": task.status,
                        "priority": task.priority,
                        "requester_agent_id": task.requester_agent_id,
                        "assignee_agent_id": task.assignee_agent_id,
                        "mission_id": task.mission_id,
                        "conversation_id": task.conversation_id,
                        "updated_at": task.updated_at,
                    }
                )
        items = sorted(
            items,
            key=lambda item: (str(item["agent_id"]), str(item["updated_at"]), str(item["task_id"])),
        )
        return MissionControlWorkQueue(
            agent_id=agent_id.strip().lower() if agent_id else None,
            total_items=len(items),
            items=items,
        )

    def get_agent_workload(self) -> MissionControlAgentWorkload:
        agents = []
        for agent_id in self._all_agent_ids():
            summary = self.delegation_inbox.get_inbox_summary(agent_id)
            admin_entry = self._admin_entry(agent_id)
            agents.append(
                {
                    "agent_id": agent_id,
                    "display_name": admin_entry.get("display_name", agent_id),
                    "status": admin_entry.get("status"),
                    "is_archived": admin_entry.get("is_archived", False),
                    "pending_tasks": summary.pending_count,
                    "accepted_tasks": summary.accepted_count,
                    "in_progress_tasks": summary.in_progress_count,
                    "failed_tasks": summary.failed_count,
                    "total_tasks": summary.total_count,
                }
            )
        agents = sorted(agents, key=lambda item: str(item["agent_id"]))
        return MissionControlAgentWorkload(total_agents=len(agents), agents=agents)

    def _work_queue_agent_ids(self, agent_id: str | None) -> list[str]:
        if agent_id:
            return [agent_id.strip().lower()]
        return self._all_agent_ids()

    def _all_agent_ids(self) -> list[str]:
        agent_ids: set[str] = set()
        if self.admin:
            agent_ids.update(
                entry.agent_id for entry in self.admin.list_agents(include_archived=False)
            )
        for task in self.delegation.list_tasks():
            agent_ids.add(task.assignee_agent_id)
        return sorted(agent_ids)

    def _admin_entry(self, agent_id: str) -> dict[str, Any]:
        if not self.admin:
            return {}
        try:
            entries = {
                entry.agent_id: asdict(entry)
                for entry in self.admin.list_agents(include_archived=True)
            }
            return entries.get(agent_id, {})
        except Exception:
            return {}

    @staticmethod
    def _top_recommendations(
        context_recommendations: list[str],
        attention_items: list[dict[str, Any]],
    ) -> list[str]:
        recommendations: list[str] = []
        for recommendation in context_recommendations:
            if recommendation not in recommendations:
                recommendations.append(recommendation)
        for item in attention_items:
            recommendation = str(item.get("recommendation", "")).strip()
            if recommendation and recommendation not in recommendations:
                recommendations.append(recommendation)
        return recommendations[:3]
