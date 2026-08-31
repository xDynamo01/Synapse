from __future__ import annotations

import os
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from synapse.api.common import runtime_from
from synapse.desktop_commands import DesktopCommandAuthority
from synapse.desktop_commands.authority import DesktopAuthorityError

router = APIRouter(prefix="/desktop", tags=["desktop-command-authority"])


class SessionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class TaskCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=8000)
    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")


class CommandEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
    command_type: Literal["task.create"]
    project_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    session_id: str = Field(min_length=16, max_length=128)
    issued_at: datetime
    payload: TaskCreatePayload


@router.post("/sessions")
def create_desktop_session(
    payload: SessionPayload,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    runtime = runtime_from(request)
    authority = getattr(request.app.state, "desktop_command_authority", None)
    if authority is None:
        authority = DesktopCommandAuthority(runtime, os.environ.get("SYNAPSE_LAUNCH_TOKEN", ""))
        request.app.state.desktop_command_authority = authority
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "missing_credential"})
    try:
        session = authority.create_session(authorization.removeprefix("Bearer "), payload.project_id)
    except DesktopAuthorityError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code}) from exc
    return {
        "session_id": session.session_id,
        "session_token": session.token,
        "project_id": session.project_id,
        "capabilities": list(session.capabilities),
        "expires_at": session.expires_at.isoformat(),
    }


@router.post("/commands")
def execute_desktop_command(
    payload: CommandEnvelope,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    runtime = runtime_from(request)
    authority = getattr(request.app.state, "desktop_command_authority", None)
    if authority is None:
        authority = DesktopCommandAuthority(runtime, os.environ.get("SYNAPSE_LAUNCH_TOKEN", ""))
        request.app.state.desktop_command_authority = authority
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "missing_credential"})
    try:
        return authority.execute(
            authorization.removeprefix("Bearer "), payload.model_dump(mode="json")
        )
    except DesktopAuthorityError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code}) from exc
