from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from synapse.api.common import runtime_from
from synapse.api.operational_activity_stream import activity_event_stream
from synapse.operational_projection import (
    OperationalCursorError,
    OperationalResyncRequired,
    fact_dict,
    snapshot_dict,
)
from synapse.project_governance.errors import ProjectNotFound

router = APIRouter(tags=["operational-activity"])


def _scope_allowed(scope_id: str, request: Request) -> bool:
    if scope_id.startswith("conversation:") and len(scope_id) > len("conversation:"):
        return True
    runtime = runtime_from(request)
    try:
        runtime.project_governance.projects.get(scope_id)
    except ProjectNotFound:
        return False
    return True


@router.get("/activity/scopes/{scope_id}")
def scoped_activity(scope_id: str, request: Request) -> dict[str, object]:
    if not _scope_allowed(scope_id, request):
        raise HTTPException(status_code=404, detail="activity_scope_not_found")
    runtime = runtime_from(request)
    return snapshot_dict(runtime.operational_projection.snapshot(scope_id, datetime.now(UTC).isoformat()))


@router.get("/activity/scopes/{scope_id}/events")
def scoped_activity_events(scope_id: str, request: Request, cursor: str | None = Query(default=None)) -> dict[str, object]:
    if not _scope_allowed(scope_id, request):
        raise HTTPException(status_code=404, detail="activity_scope_not_found")
    runtime = runtime_from(request)
    try:
        resumed = runtime.operational_projection.resume(scope_id, cursor, datetime.now(UTC).isoformat())
    except OperationalResyncRequired as exc:
        raise HTTPException(status_code=409, detail="activity_resync_required") from exc
    except OperationalCursorError as exc:
        raise HTTPException(status_code=422, detail="invalid_activity_cursor") from exc
    return {"snapshot": snapshot_dict(resumed.snapshot), "events": [fact_dict(event) for event in resumed.events], "cursor": resumed.cursor.encode() if resumed.cursor else None, "resynchronized": resumed.resynchronized}


@router.get("/activity/scopes/{scope_id}/stream")
def scoped_activity_stream(scope_id: str, request: Request, cursor: str | None = Query(default=None)) -> StreamingResponse:
    if not _scope_allowed(scope_id, request):
        raise HTTPException(status_code=404, detail="activity_scope_not_found")
    runtime = runtime_from(request)
    return StreamingResponse(activity_event_stream(request, runtime.operational_projection, scope_id, cursor), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/projects/{project_id}/activity")
def project_activity(project_id: str, request: Request) -> dict[str, object]:
    runtime = runtime_from(request)
    try:
        runtime.project_governance.projects.get(project_id)
    except ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    return snapshot_dict(
        runtime.operational_projection.snapshot(project_id, datetime.now(UTC).isoformat())
    )


@router.get("/projects/{project_id}/activity/events")
def project_activity_events(
    project_id: str,
    request: Request,
    cursor: str | None = Query(default=None),
) -> dict[str, object]:
    runtime = runtime_from(request)
    try:
        runtime.project_governance.projects.get(project_id)
    except ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    try:
        resumed = runtime.operational_projection.resume(
            project_id, cursor, datetime.now(UTC).isoformat()
        )
    except OperationalResyncRequired as exc:
        raise HTTPException(status_code=409, detail="activity_resync_required") from exc
    except OperationalCursorError as exc:
        raise HTTPException(status_code=422, detail="invalid_activity_cursor") from exc
    return {
        "snapshot": snapshot_dict(resumed.snapshot),
        "events": [fact_dict(event) for event in resumed.events],
        "cursor": resumed.cursor.encode() if resumed.cursor else None,
        "resynchronized": resumed.resynchronized,
    }


@router.get("/projects/{project_id}/activity/stream")
def project_activity_stream(
    project_id: str,
    request: Request,
    cursor: str | None = Query(default=None),
) -> StreamingResponse:
    runtime = runtime_from(request)
    try:
        runtime.project_governance.projects.get(project_id)
    except ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    return StreamingResponse(
        activity_event_stream(request, runtime.operational_projection, project_id, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
