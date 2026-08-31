from dataclasses import replace

import pytest

from synapse.operational_projection import (
    ContradictoryOperationalFact,
    CrossProjectFact,
    OperationalEntity,
    OperationalEntityKind,
    OperationalFact,
    OperationalFactKind,
    OperationalProjectionReducer,
    OperationalRelation,
    OperationalRelationKind,
    OperationalRevisionGap,
    OperationalStatus,
    StaleOperationalFact,
)
from synapse.bootstrap.adapters.operational_projection import OperationalProjectionRuntime
from synapse.core.events import EventBus

NOW = "2026-08-20T12:00:00+00:00"


def entity(entity_id: str = "agent:primary") -> OperationalEntity:
    return OperationalEntity(
        entity_id=entity_id,
        kind=OperationalEntityKind.AGENT,
        role="orchestration",
        status=OperationalStatus.RUNNING,
        label="Primary Agent",
        metadata={"task_count": 2},
    )


def fact(revision: int, *, event_id: str | None = None) -> OperationalFact:
    return OperationalFact(
        event_id=event_id or f"event:{revision}",
        project_id="synapse",
        revision=revision,
        occurred_at=NOW,
        kind=OperationalFactKind.UPSERT_ENTITY,
        source_reference=f"source:{revision}",
        entity=entity(),
    )


def test_snapshot_is_project_scoped_and_deterministic() -> None:
    first = OperationalProjectionReducer("synapse")
    second = OperationalProjectionReducer("synapse")
    facts = (fact(1), replace(fact(2), entity=entity("agent:worker")))
    assert first.replay(facts) == second.replay(facts)
    assert first.snapshot(NOW).project_id == "synapse"


def test_duplicate_delivery_is_idempotent_but_contradiction_is_rejected() -> None:
    reducer = OperationalProjectionReducer("synapse")
    original = fact(1)
    assert reducer.apply(original)
    assert not reducer.apply(original)
    with pytest.raises(ContradictoryOperationalFact):
        reducer.apply(replace(original, source_reference="source:other"))


def test_stale_gap_and_cross_project_facts_are_explicit() -> None:
    reducer = OperationalProjectionReducer("synapse")
    reducer.apply(fact(1))
    with pytest.raises(StaleOperationalFact):
        reducer.apply(replace(fact(1), event_id="event:stale"))
    with pytest.raises(OperationalRevisionGap):
        reducer.apply(fact(3))
    with pytest.raises(CrossProjectFact):
        reducer.apply(replace(fact(2), project_id="other"))


def test_relation_requires_observed_entities_and_entity_removal_cleans_edges() -> None:
    reducer = OperationalProjectionReducer("synapse")
    reducer.apply(fact(1))
    reducer.apply(replace(fact(2), entity=entity("tool:test")))
    relation = OperationalRelation(
        "relation:tool",
        "agent:primary",
        "tool:test",
        OperationalRelationKind.TOOL_USE,
    )
    reducer.apply(
        replace(
            fact(3),
            kind=OperationalFactKind.UPSERT_RELATION,
            entity=None,
            relation=relation,
        )
    )
    reducer.apply(
        replace(
            fact(4),
            kind=OperationalFactKind.REMOVE_ENTITY,
            entity=None,
            entity_id="tool:test",
        )
    )
    assert reducer.snapshot(NOW).relations == ()


def test_degraded_state_is_factual_and_recoverable() -> None:
    reducer = OperationalProjectionReducer("synapse")
    reducer.apply(
        replace(
            fact(1),
            kind=OperationalFactKind.MARK_DEGRADED,
            entity=None,
            degradation_reason="source-unavailable",
        )
    )
    assert reducer.snapshot(NOW).degraded
    reducer.apply(
        replace(
            fact(2),
            kind=OperationalFactKind.CLEAR_DEGRADED,
            entity=None,
            degradation_reason="source-unavailable",
        )
    )
    assert not reducer.snapshot(NOW).degraded


@pytest.mark.parametrize("key", ["prompt", "chain_of_thought", "access_token", "secret"])
def test_sensitive_metadata_is_rejected(key: str) -> None:
    with pytest.raises(ValueError, match="sensitive"):
        replace(entity(), metadata={key: "not allowed"})


def test_conversation_scoped_event_is_projected_without_project_id(tmp_path) -> None:
    bus = EventBus(tmp_path)
    bus.emit(
        "agent.started",
        "primary",
        {"conversation_id": "conv-1", "agent_id": "primary", "label": "Primary Agent", "status": "processing"},
    )
    projection = OperationalProjectionRuntime(bus)
    snapshot = projection.snapshot("conversation:conv-1", NOW)
    assert [item.entity_id for item in snapshot.entities] == ["agent:primary"]
    assert snapshot.entities[0].status is OperationalStatus.PROCESSING
