from __future__ import annotations

from synapse.attention.decision import DecisionRuntime
from synapse.core.serialization import dump_structured_file
from synapse.world_state.models import WorldStateUpdate

from .world_attention_support import DomainFixture, loop


def test_dnd_defers_low_notification_and_preserves_critical() -> None:
    fixture = DomainFixture()
    try:
        dump_structured_file(fixture.data_dir.resolve("config/proactive_behavior.yaml"), {
            "proactive_behavior": {"mode": "suggest", "allowed_dispositions": ["notify"]}
        })
        fixture.world_state.apply_state_update(WorldStateUpdate(
            source="user", entity_type="user_state", operation="merge",
            values={"do_not_disturb": True},
        ))
        item = fixture.high_item("notify")
        decisions = DecisionRuntime(fixture.data_dir, fixture.events)
        decision = decisions.decide(item, fixture.world_state.snapshot())
        assert decision.disposition == "defer"
        result = loop(fixture, decisions).run_cycle("acceptance.dnd")
        assert result.disposition == "defer"
        assert fixture.attention.get_item(item.id).status == "deferred"
    finally:
        fixture.close()
