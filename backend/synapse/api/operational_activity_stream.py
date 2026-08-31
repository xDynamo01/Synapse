from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import AsyncIterator

from fastapi import Request

from synapse.operational_projection import (
    OperationalCursor,
    OperationalCursorError,
    OperationalProjectionReadPort,
    fact_dict,
    snapshot_dict,
)


async def activity_event_stream(
    request: Request,
    projection: OperationalProjectionReadPort,
    project_id: str,
    cursor: str | None,
) -> AsyncIterator[str]:
    current = cursor
    while not await request.is_disconnected():
        try:
            resumed = projection.resume(project_id, current, _now())
        except OperationalCursorError:
            resumed = projection.resume(project_id, None, _now())
            yield _sse("resync", snapshot_dict(resumed.snapshot), resumed.cursor)
        else:
            if current is None:
                yield _sse("snapshot", snapshot_dict(resumed.snapshot), resumed.cursor)
            for event in resumed.events:
                yield _sse(
                    "activity",
                    fact_dict(event),
                    OperationalCursor(project_id, event.revision, event.event_id),
                )
        current = resumed.cursor.encode() if resumed.cursor else current
        await asyncio.sleep(0.25)


def _sse(
    name: str,
    payload: dict[str, object],
    cursor: OperationalCursor | None,
) -> str:
    event_id = cursor.encode() if cursor is not None else ""
    data = json.dumps(payload, separators=(",", ":"))
    return f"event: {name}\nid: {event_id}\ndata: {data}\n\n"


def _now() -> str:
    return datetime.now(UTC).isoformat()
