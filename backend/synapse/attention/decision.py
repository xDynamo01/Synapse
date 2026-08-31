from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from synapse.attention.models import DISPOSITIONS, PROACTIVE_MODES, AttentionItem, Decision
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_json, dump_structured_file, load_structured_file
from synapse.world_state.models import WorldStateSnapshot


class GovernanceRuntime(Protocol):
    def evaluate(self, request: Any) -> Any: ...


class DecisionRuntime:
    """Chooses a disposition. Execution is deliberately outside this class."""

    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        governance: GovernanceRuntime | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.governance = governance

    def decide(self, item: AttentionItem, world_state: WorldStateSnapshot) -> Decision:
        policy = self.load_policy()
        mode = policy["mode"]
        requested = self._requested_disposition(item)
        disposition, reason = self._bound_disposition(requested, item, world_state, policy)
        selected_action = item.metadata.get("selected_action")
        disposition, reason = self._apply_operational_limits(
            disposition, reason, item, world_state, policy, selected_action
        )
        governance_result = self._govern(item, disposition, selected_action)
        if disposition in {"execute_reversible_action", "start_mission", "respond"}:
            if not governance_result.get("allowed", False):
                disposition = (
                    "require_approval"
                    if governance_result.get("requires_approval")
                    else "record_only"
                )
                reason = "Platform Governance did not explicitly authorize execution."
        approval_required = disposition == "require_approval" or item.severity == "critical"
        if item.severity == "critical" and disposition not in {"escalate", "require_approval"}:
            disposition = "require_approval"
            reason = "Critical items always require approval."
            approval_required = True
        decision = Decision(
            attention_item_id=item.id,
            disposition=disposition,
            reason=reason,
            policy_result=governance_result,
            autonomy_level=mode,
            risk=str(item.metadata.get("risk_level", item.severity)),
            selected_agent=item.metadata.get("selected_agent"),
            selected_action=selected_action if isinstance(selected_action, dict) else None,
            approval_required=approval_required,
            expires_at=(datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
            metadata={"requested_disposition": requested},
        )
        self.event_bus.emit(
            "decision.created",
            "attention_decision",
            {
                "decision_id": decision.id,
                "attention_item_id": item.id,
                "disposition": decision.disposition,
                "approval_required": decision.approval_required,
                "trace_id": decision.trace_id,
            },
        )
        if approval_required:
            self.event_bus.emit(
                "decision.awaiting_approval",
                "attention_decision",
                {
                    "decision_id": decision.id,
                    "attention_item_id": item.id,
                    "trace_id": decision.trace_id,
                },
            )
        self._record_decision(decision, item)
        return decision

    def load_policy(self) -> dict[str, Any]:
        raw = load_structured_file(self.data_dir.resolve("config/proactive_behavior.yaml"))
        policy = raw.get("proactive_behavior", raw)
        mode = str(policy.get("mode", "observe"))
        if mode not in PROACTIVE_MODES:
            raise ValidationError(f"Invalid proactive mode: {mode}")
        return {
            "mode": mode,
            "max_proactive_actions_per_hour": int(policy.get("max_proactive_actions_per_hour", 2)),
            "cooldown_seconds": int(policy.get("cooldown_seconds", 300)),
            "allowed_dispositions": list(
                policy.get("allowed_dispositions", ["record_only", "notify"])
            ),
            "quiet_hours": dict(policy.get("quiet_hours", {})),
            "notification_budget_per_hour": int(policy.get("notification_budget_per_hour", 4)),
            "mission_concurrency": int(policy.get("mission_concurrency", 1)),
            "tool_risk_ceiling": str(policy.get("tool_risk_ceiling", "low")),
        }

    def update_policy(
        self,
        *,
        mode: str,
        allowed_dispositions: list[str] | None = None,
        max_proactive_actions_per_hour: int | None = None,
    ) -> dict[str, Any]:
        """Persist the policy fields exposed by the existing HTTP adapter."""

        if mode not in PROACTIVE_MODES:
            raise ValidationError(f"Invalid proactive mode: {mode}")
        policy = self.load_policy()
        policy["mode"] = mode
        if allowed_dispositions is not None:
            policy["allowed_dispositions"] = allowed_dispositions
        if max_proactive_actions_per_hour is not None:
            policy["max_proactive_actions_per_hour"] = max_proactive_actions_per_hour
        dump_structured_file(
            self.data_dir.resolve("config/proactive_behavior.yaml"),
            {"proactive_behavior": policy},
        )
        return self.load_policy()

    @staticmethod
    def _requested_disposition(item: AttentionItem) -> str:
        for disposition in item.suggested_dispositions:
            if disposition in DISPOSITIONS:
                return disposition
        return "record_only"

    @staticmethod
    def _bound_disposition(
        requested: str,
        item: AttentionItem,
        state: WorldStateSnapshot,
        policy: dict[str, Any],
    ) -> tuple[str, str]:
        mode = policy["mode"]
        if mode == "off":
            return "ignore", "Proactive behavior is disabled."
        dnd = bool(state.user_state.get("do_not_disturb"))
        if dnd and item.severity != "critical":
            return "defer", "Do Not Disturb defers non-critical attention."
        if requested not in set(policy["allowed_dispositions"]):
            return "record_only", "Disposition is outside the configured proactive allowlist."
        if mode == "observe":
            return "record_only", "Observe mode never initiates a side effect."
        if mode == "suggest" and requested not in {
            "ignore",
            "record_only",
            "notify",
            "suggest",
            "defer",
        }:
            return "suggest", "Suggest mode cannot execute actions."
        if mode == "assist" and requested in {"execute_reversible_action", "start_mission"}:
            return "require_approval", "Assist mode requires approval for execution."
        return requested, "Disposition is within configured autonomy and DND limits."

    def _govern(
        self, item: AttentionItem, disposition: str, selected_action: Any
    ) -> dict[str, Any]:
        if disposition not in {"execute_reversible_action", "start_mission", "respond"}:
            return {
                "allowed": True,
                "requires_approval": disposition == "require_approval",
                "scope": "non_execution",
            }
        if self.governance is None:
            return {
                "allowed": False,
                "requires_approval": False,
                "reason": "governance_unavailable",
            }
        if hasattr(self.governance, "evaluate_proactive"):
            try:
                result = self.governance.evaluate_proactive(
                    {
                        "subject": item.metadata.get("selected_agent") or "agent_loop",
                        "action": disposition,
                        "resource": selected_action or {},
                        "risk": item.metadata.get("risk_level", item.severity),
                        "correlation_id": item.correlation_id,
                    }
                )
                if isinstance(result, dict):
                    return result
                return result.to_dict() if hasattr(result, "to_dict") else asdict(result)
            except Exception as exc:
                return {"allowed": False, "requires_approval": False, "reason": type(exc).__name__}
        if disposition != "execute_reversible_action" or not isinstance(selected_action, dict):
            return {
                "allowed": False,
                "requires_approval": True,
                "reason": "explicit_domain_policy_required",
            }
        try:
            from synapse.decisions.models import DecisionRequest

            result = self.governance.evaluate(
                DecisionRequest(
                    actor_type="agent_loop",
                    actor_id=item.metadata.get("selected_agent") or "agent_loop",
                    target_agent_id=item.metadata.get("selected_agent"),
                    category="tool_execution",
                    action=str(selected_action.get("tool_id", "")),
                    correlation_id=item.correlation_id,
                    metadata={"resource_ref": selected_action.get("resource_ref")},
                )
            )
            return result.to_dict() if hasattr(result, "to_dict") else asdict(result)
        except Exception as exc:
            return {"allowed": False, "requires_approval": False, "reason": type(exc).__name__}

    def _apply_operational_limits(
        self,
        disposition: str,
        reason: str,
        item: AttentionItem,
        state: WorldStateSnapshot,
        policy: dict[str, Any],
        selected_action: Any,
    ) -> tuple[str, str]:
        if item.severity == "critical":
            return disposition, reason
        now = datetime.now(UTC)
        quiet = policy.get("quiet_hours", {})
        start = quiet.get("start")
        end = quiet.get("end")
        if start and end and _in_quiet_hours(now.strftime("%H:%M"), str(start), str(end)):
            return "defer", "Configured quiet hours defer non-critical proactive behavior."
        if state.user_state.get("presence") in {"away", "offline"} and disposition in {
            "notify",
            "suggest",
            "ask_user",
            "respond",
            "execute_reversible_action",
            "start_mission",
        }:
            return "defer", "User presence does not permit proactive interruption."
        if disposition == "start_mission":
            active = len(
                [
                    mission
                    for mission in state.missions.values()
                    if mission.get("status") in {"ready", "running", "active"}
                ]
            )
            if active >= policy["mission_concurrency"]:
                return "defer", "Mission concurrency limit reached."
        if disposition == "execute_reversible_action":
            risk = str(item.metadata.get("risk_level", item.severity))
            order = {"informational": 0, "low": 0, "medium": 1, "high": 2, "critical": 3}
            if order.get(risk, 3) > order.get(policy["tool_risk_ceiling"], 0):
                return "require_approval", "Tool risk exceeds the proactive risk ceiling."
            if isinstance(selected_action, dict) and selected_action.get("reversible") is False:
                return "require_approval", "Irreversible actions are never automatic."
        ledger = load_structured_file(self.data_dir.resolve("agent_loop/proactive_ledger.json"))
        records = [
            record
            for record in ledger.get("records", [])
            if _record_time(record) >= now - timedelta(hours=1)
        ]
        proactive = {
            "notify",
            "suggest",
            "ask_user",
            "respond",
            "execute_reversible_action",
            "start_mission",
            "escalate",
        }
        if disposition in proactive and len(records) >= policy["max_proactive_actions_per_hour"]:
            return "defer", "Hourly proactive action limit reached."
        notifications = [
            record
            for record in records
            if record.get("disposition") in {"notify", "suggest", "escalate"}
        ]
        if (
            disposition in {"notify", "suggest", "escalate"}
            and len(notifications) >= policy["notification_budget_per_hour"]
        ):
            return "defer", "Hourly notification budget reached."
        previous = [
            record
            for record in records
            if record.get("attention_key") == (item.deduplication_key or item.id)
        ]
        if disposition in proactive and previous:
            elapsed = (now - max(_record_time(record) for record in previous)).total_seconds()
            if elapsed < policy["cooldown_seconds"]:
                return "defer", "Per-item proactive cooldown is active."
        return disposition, reason

    def _record_decision(self, decision: Decision, item: AttentionItem) -> None:
        proactive = {
            "notify",
            "suggest",
            "ask_user",
            "respond",
            "execute_reversible_action",
            "start_mission",
            "escalate",
        }
        if decision.disposition not in proactive:
            return
        path = self.data_dir.resolve("agent_loop/proactive_ledger.json")
        raw = load_structured_file(path)
        records = list(raw.get("records", []))
        records.append(
            {
                "decision_id": decision.id,
                "attention_key": item.deduplication_key or item.id,
                "disposition": decision.disposition,
                "created_at": decision.created_at,
            }
        )
        dump_json(path, {"records": records[-10_000:]})


def _record_time(record: dict[str, Any]) -> datetime:
    instant = datetime.fromisoformat(str(record.get("created_at")))
    return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)


def _in_quiet_hours(current: str, start: str, end: str) -> bool:
    if start <= end:
        return start <= current < end
    return current >= start or current < end
