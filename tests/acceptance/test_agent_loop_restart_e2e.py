from __future__ import annotations

from synapse.attention.models import Decision
from synapse.core.serialization import dump_json

from .world_attention_support import DomainFixture, FixedDecisionRuntime, ToolSpy, loop


def test_restart_does_not_repeat_started_action() -> None:
    fixture = DomainFixture()
    try:
        item = fixture.high_item("execute_reversible_action")
        tool = ToolSpy()
        runtime = loop(fixture, FixedDecisionRuntime("execute_reversible_action", {"tool_id": "test"}), tool_runtime=tool)
        decision = Decision(
            id="crashed-decision", attention_item_id=item.id, disposition="execute_reversible_action",
            reason="allowed", policy_result={"allowed": True}, autonomy_level="autonomous_limited",
            risk="low", selected_action={"tool_id": "test"},
        )
        dump_json(runtime.executions_root / f"{decision.id}.json", {
            "status": "started", "started_at": decision.created_at, "decision_id": decision.id,
        })
        result = runtime._execute_idempotent(item, decision)
        assert result.verification["reason"] == "outcome_unknown_after_restart"
        assert tool.calls == 0
    finally:
        fixture.close()
