from dataclasses import replace

import pytest

from synapse.operational_projection import (
    CrossProjectCursor,
    InvalidOperationalCursor,
    OperationalCursor,
    OperationalEntity,
    OperationalEntityKind,
    OperationalFact,
    OperationalFactKind,
    OperationalResyncRequired,
    OperationalStatus,
    ProjectActivityFeed,
)

NOW = "2026-08-20T12:00:00+00:00"


def fact(revision: int) -> OperationalFact:
    return OperationalFact(
        event_id=f"event:{revision}",
        project_id="synapse",
        revision=revision,
        occurred_at=NOW,
        kind=OperationalFactKind.UPSERT_ENTITY,
        source_reference=f"source:{revision}",
        entity=OperationalEntity(
            entity_id="agent:primary",
            kind=OperationalEntityKind.AGENT,
            role="orchestration",
            status=OperationalStatus.RUNNING,
            label="Primary Agent",
        ),
    )


def test_cursor_round_trip_is_stable() -> None:
    cursor = OperationalCursor("synapse", 2, "event:2")
    assert OperationalCursor.decode(cursor.encode()) == cursor


def test_resume_delivers_only_events_after_cursor() -> None:
    feed = ProjectActivityFeed("synapse")
    first = feed.append(fact(1))
    feed.append(replace(fact(2), entity=replace(fact(1).entity, label="Updated")))
    resumed = feed.resume(first.encode(), NOW)
    assert [event.revision for event in resumed.events] == [2]
    assert not resumed.resynchronized


def test_initial_connect_returns_authoritative_snapshot() -> None:
    feed = ProjectActivityFeed("synapse")
    feed.append(fact(1))
    resumed = feed.resume(None, NOW)
    assert resumed.snapshot.revision == 1
    assert resumed.events == ()
    assert resumed.resynchronized


def test_evicted_cursor_requires_snapshot_resync() -> None:
    feed = ProjectActivityFeed("synapse", max_retained_events=1)
    first = feed.append(fact(1))
    feed.append(fact(2))
    with pytest.raises(OperationalResyncRequired):
        feed.resume(first.encode(), NOW)


def test_cursor_cannot_cross_projects_or_run_ahead() -> None:
    feed = ProjectActivityFeed("synapse")
    feed.append(fact(1))
    with pytest.raises(CrossProjectCursor):
        feed.resume(OperationalCursor("other", 1, "event:1").encode(), NOW)
    with pytest.raises(InvalidOperationalCursor):
        feed.resume(OperationalCursor("synapse", 2, "event:2").encode(), NOW)


def test_replay_reconstructs_the_same_snapshot() -> None:
    original = ProjectActivityFeed("synapse")
    original.append(fact(1))
    original.append(fact(2))
    rebuilt = ProjectActivityFeed("synapse")
    for event in original.retained_events():
        rebuilt.append(event)
    assert rebuilt.snapshot(NOW) == original.snapshot(NOW)
