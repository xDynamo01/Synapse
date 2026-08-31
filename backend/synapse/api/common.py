from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel

from synapse.core.exceptions import NotFound, PermissionDenied, SynapseError, ValidationError


def runtime_from(request: Request):
    return request.app.state.runtime


def context_from(
    runtime: Any,
    actor_id: str | None,
    actor_type: str | None,
    device_id: str | None = None,
):
    """Translate transport actor headers into the canonical permission context."""

    return runtime.context(
        actor_id=actor_id,
        actor_type=actor_type or "user",
        device_id=device_id,
    )


def payload_dict(payload: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic transport DTO without domain-specific behavior."""

    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    return payload.dict()


def require_admin(actor_type: str | None) -> None:
    """Enforce the existing transport-level administrative header contract."""

    if actor_type not in {"admin", "system"}:
        raise HTTPException(
            status_code=403,
            detail="Administrative operation requires X-Actor-Type: admin",
        )


def api_error(exc: Exception) -> HTTPException:
    if hasattr(exc, "code") and hasattr(exc, "to_dict"):
        return HTTPException(
            status_code=int(getattr(exc, "status_code", 400)),
            detail=exc.to_dict(),
        )
    if isinstance(exc, PermissionDenied):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, SynapseError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=type(exc).__name__)
