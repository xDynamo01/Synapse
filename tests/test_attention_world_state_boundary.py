from __future__ import annotations

from datetime import UTC, datetime

from acceptance.world_attention_support import DomainFixture
from synapse.attention.models import AttentionEvent
from synapse.attention.runtime import AttentionRuntime
from synapse.bootstrap.adapters.world_state import (
    RuntimeEventStateAdapter,
    WorldStateReadAdapter,
)
from synapse.core.events import Event


def _job_failed_event(event_id: str = "job-failed-1") -> Event:
    return Event(
        id=event_id,
        type="job.failed",
        actor_id="scheduler",
        source_module="scheduler",
        payload={"error": "failure", "deduplication_key": "job:x"},
        correlation_id="corr-1",
        timestamp=datetime.now(UTC).isoformat(),
    )


def test_attention_reads_current_snapshot_through_port() -> None:
    fixture = DomainFixture()
    try:
        reader = WorldStateReadAdapter(fixture.world_state)
        attention = AttentionRuntime(fixture.data_dir, fixture.events, reader)
        item = attention.ingest_event(
            AttentionEvent(
                id="port-read",
                type="attention.port_read",
                source="test",
                title="Read current state",
                summary="Read current state",
                severity="medium",
            )
        )
        assert item.policy_context["score"]["factors"]["user_availability"] == 0.04
        assert reader.snapshot() == fixture.world_state.snapshot()
    finally:
        fixture.close()


def test_runtime_event_projection_preserves_update_attention_and_deduplication() -> None:
    fixture = DomainFixture()
    try:
        attention = AttentionRuntime(
            fixture.data_dir,
            fixture.events,
            WorldStateReadAdapter(fixture.world_state),
        )
        adapter = RuntimeEventStateAdapter(fixture.world_state, attention)
        event = _job_failed_event()

        adapter.handle_event(event)
        first_snapshot = fixture.world_state.snapshot()
        first_item = attention.list_items()[0]
        adapter.handle_event(event)
        repeated_snapshot = fixture.world_state.snapshot()
        repeated_item = attention.list_items()[0]

        assert first_snapshot.revision == 1
        assert first_snapshot.system_state["scheduler_status"] == "degraded"
        assert repeated_snapshot.revision == first_snapshot.revision
        assert repeated_item.id == first_item.id
        assert repeated_item.occurrence_count == 1
        assert repeated_item.correlation_id == "corr-1"
        assert repeated_item.provenance == {
            "event_id": event.id,
            "event_type": "job.failed",
        }
    finally:
        fixture.close()


def test_read_adapter_exception_remains_isolated_by_event_projection() -> None:
    class FailingWorldStateReadPort:
        def snapshot(self):
            raise RuntimeError("world state unavailable")

    fixture = DomainFixture()
    try:
        attention = AttentionRuntime(
            fixture.data_dir,
            fixture.events,
            FailingWorldStateReadPort(),
        )
        adapter = RuntimeEventStateAdapter(fixture.world_state, attention)

        adapter.handle_event(_job_failed_event("job-failed-unavailable"))

        assert fixture.world_state.snapshot().revision == 1
        assert attention.list_items() == []
    finally:
        fixture.close()


def test_explicit_snapshot_and_no_port_preserve_legacy_fallbacks() -> None:
    fixture = DomainFixture()
    try:
        event = AttentionEvent(
            id="legacy-fallback",
            type="attention.legacy",
            source="test",
            title="Legacy fallback",
            summary="Legacy fallback",
            severity="low",
        )
        explicit = fixture.attention.ingest_event(event, fixture.world_state.snapshot())
        assert explicit.relevance == 0.302

        no_port = AttentionRuntime(fixture.data_dir, fixture.events)
        repeated = no_port.ingest_event(event)
        assert repeated.id == explicit.id
        assert repeated.relevance == explicit.relevance
    finally:
        fixture.close()
