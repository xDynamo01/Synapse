from __future__ import annotations

from synapse.attention.models import AttentionEvent

from .world_attention_support import DomainFixture


def test_attention_deduplicates_scores_suppresses_and_escalates() -> None:
    fixture = DomainFixture()
    try:
        low = AttentionEvent(
            id="low-1", type="provider.offline", source="providers", title="Provider offline",
            summary="Transient provider state", severity="informational", confidence=0.1,
            metadata={"deduplication_key": "provider:x"},
        )
        item = fixture.attention.ingest_event(low, fixture.world_state.snapshot())
        assert item.status == "suppressed"
        critical = AttentionEvent(
            id="critical-1", type="provider.offline", source="providers", title="Provider offline",
            summary="Provider still offline", severity="critical", urgency=1.0,
            metadata={"deduplication_key": "provider:x"},
        )
        escalated = fixture.attention.ingest_event(critical, fixture.world_state.snapshot())
        assert escalated.id == item.id
        assert escalated.status == "pending"
        assert escalated.severity == "critical"
        assert escalated.occurrence_count == 2
        assert fixture.attention.score_event(critical).factors["severity"] > 0
    finally:
        fixture.close()
