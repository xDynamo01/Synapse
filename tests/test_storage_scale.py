from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from synapse.storage.collection import FileCollection
from synapse.storage.contracts import CollectionQuery


@pytest.mark.parametrize("agent_count", [100, 500])
def test_agent_scale_is_complete_and_paginated(
    tmp_path: Path, agent_count: int
) -> None:
    collection = FileCollection(
        collection_id=f"agent_scale_{agent_count}",
        root=(tmp_path / str(agent_count)).resolve(),
        current_schema_version=1,
        suffix=".json",
        backup_on_write=False,
    )
    timestamp = datetime.now(UTC).isoformat()
    for index in range(agent_count):
        record_id = f"agent-{index:04d}"
        collection.put(
            record_id,
            {
                "id": record_id,
                "schema_version": 1,
                "revision": 1,
                "created_at": timestamp,
                "updated_at": timestamp,
                "operational_counts": {
                    "conversations": 20,
                    "missions": 10,
                    "attempts": 30,
                    "events": 200,
                },
            },
        )

    cursor = None
    listed = []
    while True:
        page = collection.list(CollectionQuery(cursor=cursor, limit=100))
        listed.extend(item.record_id for item in page.items)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor

    assert len(listed) == agent_count
    assert listed == sorted(listed)
