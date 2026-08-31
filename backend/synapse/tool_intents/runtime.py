from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.observability.correlation import current_correlation_fields
from synapse.tool_intents.models import (
    TOOL_INTENT_SOURCES,
    TOOL_INTENT_STATUSES,
    ToolIntent,
    ToolIntentReview,
)
from synapse.tools.contracts import ToolExecutionPort
from synapse.tools.models import ToolExecutionRequest

if TYPE_CHECKING:
    from synapse.execution_router.runtime import ExecutionRouterRuntime


class ToolIntentRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        tools: ToolExecutionPort,
        default_actor_id: str = "local_owner",
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        self.tools = tools
        self.default_actor_id = default_actor_id
        self.root = self.data_dir.resolve("tool_intents")
        self.root.mkdir(parents=True, exist_ok=True)
        self.execution_router: ExecutionRouterRuntime | None = None

    def create_intent(
        self,
        tool_id: str,
        proposed_arguments: dict[str, Any] | None = None,
        source: str = "user",
        source_agent_id: str | None = None,
        conversation_id: str | None = None,
        mission_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolIntent:
        if source not in TOOL_INTENT_SOURCES:
            raise ValidationError(f"Invalid tool intent source: {source}")
        definition = self.tools.get_tool(tool_id)
        fields = current_correlation_fields()
        decision = self._decision(
            tool_id,
            proposed_arguments or {},
            source,
            source_agent_id,
            conversation_id,
            mission_id,
            correlation_id or fields.get("correlation_id"),
            causation_id or fields.get("causation_id"),
        )
        intent = ToolIntent(
            tool_id=tool_id,
            proposed_arguments=proposed_arguments or {},
            source=source,
            source_agent_id=source_agent_id,
            conversation_id=conversation_id,
            mission_id=mission_id,
            correlation_id=correlation_id or fields.get("correlation_id"),
            causation_id=causation_id or fields.get("causation_id"),
            metadata=metadata or {},
            decision_snapshot=decision,
            tool_snapshot={
                "tool_id": definition.tool_id,
                "display_name": definition.display_name,
                "description": definition.description,
                "category": definition.category,
                "required_capability": definition.required_capability,
                "required_permission": definition.required_permission,
                "risk_level": definition.risk_level,
                "approval_required": definition.approval_required,
            },
        )
        self._write(intent)
        self._emit("tool_intent.created", intent)
        return intent

    def get_intent(self, intent_id: str) -> ToolIntent:
        path = self._path(intent_id)
        if not path.exists():
            raise NotFound(f"Tool intent not found: {intent_id}")
        return self._read(path)

    def list_intents(self, status: str | None = None) -> list[ToolIntent]:
        if status and status not in TOOL_INTENT_STATUSES:
            raise ValidationError(f"Invalid tool intent status: {status}")
        intents = [self._read(path) for path in sorted(self.root.glob("*.yaml"))]
        if status:
            intents = [intent for intent in intents if intent.status == status]
        return sorted(intents, key=lambda intent: (intent.created_at, intent.intent_id))

    def list_pending_intents(self) -> list[ToolIntent]:
        return [
            intent for intent in self.list_intents() if intent.status in {"proposed", "reviewed"}
        ]

    def review_intent(
        self,
        intent_id: str,
        decision: str = "reviewed",
        reasons: list[str] | None = None,
        reviewed_by: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolIntent:
        if decision not in {"reviewed", "approved", "rejected"}:
            raise ValidationError(f"Invalid tool intent review decision: {decision}")
        intent = self.get_intent(intent_id)
        self._assert_reviewable(intent)
        refreshed_decision = self._decision(
            intent.tool_id,
            intent.proposed_arguments,
            intent.source,
            intent.source_agent_id,
            intent.conversation_id,
            intent.mission_id,
            intent.correlation_id,
            intent.causation_id,
        )
        review = ToolIntentReview(
            intent_id=intent.intent_id,
            decision=decision,
            reasons=reasons or [],
            reviewed_by=reviewed_by,
            metadata=metadata or {},
        )
        updated = replace(
            intent,
            status=decision,
            decision_snapshot=refreshed_decision,
            review=asdict(review),
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._write(updated)
        self._emit(f"tool_intent.{decision}", updated)
        return updated

    def approve_intent(
        self,
        intent_id: str,
        reviewed_by: str | None = None,
        reasons: list[str] | None = None,
    ) -> ToolIntent:
        return self.review_intent(intent_id, "approved", reasons, reviewed_by)

    def reject_intent(
        self,
        intent_id: str,
        reviewed_by: str | None = None,
        reasons: list[str] | None = None,
    ) -> ToolIntent:
        return self.review_intent(intent_id, "rejected", reasons, reviewed_by)

    def cancel_intent(self, intent_id: str, cancelled_by: str | None = None) -> ToolIntent:
        intent = self.get_intent(intent_id)
        if intent.status in {"executed", "failed", "rejected", "cancelled"}:
            raise ValidationError(f"Tool intent cannot be cancelled from status: {intent.status}")
        updated = replace(
            intent,
            status="cancelled",
            review={
                "intent_id": intent.intent_id,
                "decision": "cancelled",
                "reasons": [],
                "reviewed_at": datetime.now(UTC).isoformat(),
                "reviewed_by": cancelled_by,
                "metadata": {},
            },
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._write(updated)
        self._emit("tool_intent.cancelled", updated)
        return updated

    def can_execute_intent(self, intent_id: str) -> bool:
        return self.get_intent(intent_id).status == "approved"

    def execute_intent(self, intent_id: str, executor: str = "user") -> ToolIntent:
        intent = self.get_intent(intent_id)
        if intent.status != "approved":
            raise ValidationError(f"Tool intent cannot execute from status: {intent.status}")
        executed_at = datetime.now(UTC).isoformat()
        try:
            if self.execution_router is None:
                raise ValidationError("Execution Router Runtime is unavailable")
            plan = self.execution_router.route_intent(intent.intent_id)
            caller_type = "system" if executor == "system" else "user"
            caller = self.default_actor_id if executor == "user" else executor
            result = self.tools.execute(
                ToolExecutionRequest(
                    tool_id=intent.tool_id,
                    arguments=intent.proposed_arguments,
                    caller=caller,
                    caller_type=caller_type,
                    agent_id=intent.source_agent_id,
                    conversation_id=intent.conversation_id,
                    mission_id=intent.mission_id,
                    correlation_id=intent.correlation_id,
                    causation_id=intent.causation_id,
                    metadata={
                        "source": "tool_intent_execution",
                        "intent_id": intent.intent_id,
                        "execution_plan": asdict(plan),
                    },
                )
            )
            updated = replace(
                intent,
                status="executed" if result.success else "failed",
                execution_result=asdict(result),
                execution_plan=asdict(plan),
                executed_at=executed_at,
                executor=executor,
                updated_at=executed_at,
            )
            self._write(updated)
            self._emit(
                "tool_intent.executed" if result.success else "tool_intent.failed",
                updated,
            )
            return updated
        except Exception as exc:
            failed = replace(
                intent,
                status="failed",
                execution_result={
                    "success": False,
                    "tool_id": intent.tool_id,
                    "output": {},
                    "duration_ms": 0,
                    "error": str(exc) or type(exc).__name__,
                    "metadata": {"error_type": type(exc).__name__},
                },
                executed_at=executed_at,
                executor=executor,
                updated_at=executed_at,
            )
            self._write(failed)
            self._emit("tool_intent.failed", failed)
            return failed

    def execution_summary(self, intent_id: str) -> dict[str, Any]:
        intent = self.get_intent(intent_id)
        return {
            "intent_id": intent.intent_id,
            "tool_id": intent.tool_id,
            "status": intent.status,
            "can_execute": intent.status == "approved",
            "executed_at": intent.executed_at,
            "executor": intent.executor,
            "execution_plan": intent.execution_plan,
            "execution_result": intent.execution_result,
        }

    def _decision(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        source: str,
        source_agent_id: str | None,
        conversation_id: str | None,
        mission_id: str | None,
        correlation_id: str | None,
        causation_id: str | None,
    ) -> dict[str, Any]:
        definition = self.tools.get_tool(tool_id)
        if self.tools.permission_bridge is None:
            return {
                "allowed": False,
                "blocked": True,
                "requires_approval": False,
                "reasons": [],
                "blocked_reasons": ["Tool permission bridge is unavailable"],
                "approval_id": None,
                "policy_metadata": {},
            }
        caller = source_agent_id or self.default_actor_id
        caller_type = "agent" if source_agent_id else (source if source != "model" else "system")
        decision = self.tools.permission_bridge.evaluate(
            definition,
            ToolExecutionRequest(
                tool_id=tool_id,
                arguments=arguments,
                caller=caller,
                caller_type=caller_type,
                agent_id=source_agent_id,
                conversation_id=conversation_id,
                mission_id=mission_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
                dry_run=True,
                metadata={"source": "tool_intent", "intent_source": source},
            ),
        )
        return asdict(decision)

    @staticmethod
    def _assert_reviewable(intent: ToolIntent) -> None:
        if intent.status not in {"proposed", "reviewed"}:
            raise ValidationError(f"Tool intent cannot be reviewed from status: {intent.status}")

    def _path(self, intent_id: str) -> Path:
        safe_id = intent_id.strip()
        if not safe_id or any(character in safe_id for character in ("/", "\\", "..")):
            raise ValidationError("Invalid tool intent id")
        return self.root / f"{safe_id}.yaml"

    def _write(self, intent: ToolIntent) -> None:
        dump_structured_file(self._path(intent.intent_id), asdict(intent))

    @staticmethod
    def _read(path: Path) -> ToolIntent:
        return ToolIntent(**load_structured_file(path))

    def _emit(self, event_type: str, intent: ToolIntent) -> None:
        self.events.emit(
            event_type,
            intent.source_agent_id or self.default_actor_id,
            {
                "intent_id": intent.intent_id,
                "tool_id": intent.tool_id,
                "status": intent.status,
                "correlation_id": intent.correlation_id,
            },
        )
