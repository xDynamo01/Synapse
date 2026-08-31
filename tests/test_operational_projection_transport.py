import asyncio
import json

from synapse.api.operational_activity_stream import activity_event_stream
from synapse.bootstrap.adapters.operational_projection import OperationalProjectionRuntime
from synapse.core.events import EventBus

NOW = "2026-08-20T12:00:00+00:00"


def test_event_bus_bridge_rebuilds_project_feed_after_restart(tmp_path) -> None:
    events = EventBus(tmp_path)
    emitted = events.emit(
        "agent.started",
        "backend",
        {"project_id": "synapse", "agent_id": "backend", "status": "running"},
    )
    first = OperationalProjectionRuntime(events)
    snapshot = first.snapshot("synapse", NOW)
    assert snapshot.revision == 1
    assert snapshot.entities[0].entity_id == "agent:backend"

    rebuilt = OperationalProjectionRuntime(EventBus(tmp_path))
    restored = rebuilt.snapshot("synapse", NOW)
    assert restored == snapshot
    assert restored.last_event_id == emitted.id


def test_projectless_events_are_not_attached_to_requested_project(tmp_path) -> None:
    events = EventBus(tmp_path)
    events.emit("agent.started", "backend", {"agent_id": "backend"})
    projection = OperationalProjectionRuntime(events)
    assert projection.snapshot("synapse", NOW).revision == 0
    assert projection.diagnostics()["unscoped_events"] == 1


def test_corrupt_event_record_preserves_valid_facts_and_marks_projection_degraded(tmp_path) -> None:
    events = EventBus(tmp_path)
    events.emit(
        "agent.started",
        "backend",
        {"project_id": "synapse", "agent_id": "backend", "status": "running"},
    )
    with events.path.open("a", encoding="utf-8") as handle:
        handle.write('truncated durable record\n')
    events.emit(
        "agent.completed",
        "backend",
        {"project_id": "synapse", "agent_id": "backend", "status": "completed"},
    )

    projection = OperationalProjectionRuntime(events)
    snapshot = projection.snapshot("synapse", NOW)

    assert snapshot.revision == 2
    assert snapshot.entities[0].status.value == "completed"
    assert snapshot.degraded is True
    assert snapshot.degradation_reasons == ("operational-event-log-corrupt",)
    assert projection.diagnostics()["corrupt_event_records"] == 1


def test_sse_starts_with_factual_snapshot_and_opaque_cursor(tmp_path) -> None:
    events = EventBus(tmp_path)
    events.emit(
        "agent.started",
        "backend",
        {"project_id": "synapse", "agent_id": "backend", "status": "running"},
    )
    projection = OperationalProjectionRuntime(events)

    class ConnectedRequest:
        async def is_disconnected(self) -> bool:
            return False

    async def first_message() -> str:
        stream = activity_event_stream(ConnectedRequest(), projection, "synapse", None)
        try:
            return await anext(stream)
        finally:
            await stream.aclose()

    message = asyncio.run(first_message())
    lines = message.strip().splitlines()
    assert lines[0] == "event: snapshot"
    assert lines[1].startswith("id: ") and len(lines[1]) > 4
    payload = json.loads(lines[2].removeprefix("data: "))
    assert payload["projectId"] == "synapse"
    assert payload["entities"][0]["status"] == "running"
