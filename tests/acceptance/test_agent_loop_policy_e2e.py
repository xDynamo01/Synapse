from __future__ import annotations

from synapse.attention.decision import DecisionRuntime

from .world_attention_support import DomainFixture


def test_observe_policy_denies_execution_without_explicit_allow() -> None:
    fixture = DomainFixture()
    try:
        item = fixture.high_item("execute_reversible_action", {"tool_id": "test"})
        decision = DecisionRuntime(fixture.data_dir, fixture.events).decide(item, fixture.world_state.snapshot())
        assert decision.disposition == "record_only"
        assert not decision.approval_required
        assert decision.autonomy_level == "observe"
    finally:
        fixture.close()
