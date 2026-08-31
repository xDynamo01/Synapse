from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from acceptance.world_attention_support import DomainFixture, FixedDecisionRuntime, loop
from synapse.agent_loop.errors import LoopInvalidState
from synapse.attention.decision import DecisionRuntime
from synapse.attention.models import AttentionEvent
from synapse.core.serialization import dump_structured_file
from synapse.world_state.errors import InvalidStateUpdate, WorldStateConflict
from synapse.world_state.models import WorldStateUpdate


def test_world_state_revision_conflict_and_temporal_order() -> None:
    fixture = DomainFixture()
    try:
        now = datetime.now(UTC)
        fixture.world_state.apply_state_update(WorldStateUpdate(
            id="new", source="test", entity_type="user_state", operation="merge",
            values={"activity": "typing"}, timestamp=now.isoformat(), expected_revision=0,
        ))
        with pytest.raises(WorldStateConflict):
            fixture.world_state.apply_state_update(WorldStateUpdate(
                id="revision-conflict", source="test", entity_type="user_state",
                operation="merge", values={"activity": "idle"}, expected_revision=0,
            ))
        with pytest.raises(WorldStateConflict):
            fixture.world_state.apply_state_update(WorldStateUpdate(
                id="old", source="test", entity_type="user_state", operation="merge",
                values={"activity": "old"}, timestamp=(now - timedelta(seconds=1)).isoformat(),
            ))
    finally:
        fixture.close()


def test_world_state_merge_is_deterministic_and_new_update_clears_old_ttl() -> None:
    fixture = DomainFixture()
    try:
        now = datetime.now(UTC)
        fixture.world_state.apply_state_update(WorldStateUpdate(
            source="test", entity_type="active_context", operation="set",
            values={"nested": {"left": 1}}, timestamp=now.isoformat(),
            expires_at=(now + timedelta(seconds=1)).isoformat(),
        ))
        fixture.world_state.apply_state_update(WorldStateUpdate(
            source="test", entity_type="active_context", operation="merge",
            values={"nested": {"right": 2}}, timestamp=(now + timedelta(milliseconds=1)).isoformat(),
        ))
        expired = fixture.world_state.expire_state(now + timedelta(seconds=2))
        assert expired.active_context["nested"] == {"left": 1, "right": 2}
    finally:
        fixture.close()


def test_world_state_validates_expiry_and_entity_type() -> None:
    fixture = DomainFixture()
    try:
        with pytest.raises(InvalidStateUpdate):
            fixture.world_state.apply_state_update(WorldStateUpdate(
                source="test", entity_type="unknown", operation="set", values={},
            ))
        now = datetime.now(UTC)
        with pytest.raises(InvalidStateUpdate):
            fixture.world_state.apply_state_update(WorldStateUpdate(
                source="test", entity_type="user_state", operation="set", values={},
                timestamp=now.isoformat(), expires_at=now.isoformat(),
            ))
    finally:
        fixture.close()


def test_attention_critical_cannot_be_suppressed() -> None:
    fixture = DomainFixture()
    try:
        item = fixture.attention.ingest_event(AttentionEvent(
            type="security.alert", source="security", title="Critical", summary="Critical",
            severity="critical", urgency=1.0,
        ))
        with pytest.raises(Exception, match="cannot be suppressed"):
            fixture.attention.suppress(item.id, "noise")
    finally:
        fixture.close()


def test_decision_rate_limit_and_tool_risk_ceiling_are_conservative() -> None:
    fixture = DomainFixture()
    try:
        dump_structured_file(fixture.data_dir.resolve("config/proactive_behavior.yaml"), {
            "proactive_behavior": {
                "mode": "autonomous_limited",
                "allowed_dispositions": ["execute_reversible_action"],
                "tool_risk_ceiling": "low",
                "max_proactive_actions_per_hour": 1,
            }
        })
        item = fixture.high_item("execute_reversible_action", {"tool_id": "x", "reversible": True})
        decision = DecisionRuntime(fixture.data_dir, fixture.events).decide(item, fixture.world_state.snapshot())
        assert decision.disposition == "require_approval"
        assert decision.approval_required
    finally:
        fixture.close()


def test_loop_rejects_invalid_pause_transition() -> None:
    fixture = DomainFixture()
    try:
        runtime = loop(fixture, FixedDecisionRuntime("record_only"))
        with pytest.raises(LoopInvalidState):
            runtime.pause()
    finally:
        fixture.close()
