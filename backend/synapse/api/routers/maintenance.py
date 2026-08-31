from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from synapse.api.common import api_error, context_from, require_admin, runtime_from
from synapse.core.exceptions import ValidationError
from synapse.maintenance.models import (
    MaintenanceExecutionRequest,
    MaintenanceInspectionRequest,
    MaintenancePlanRequest,
    MaintenanceScope,
    MaintenanceScopeKind,
)
from synapse.observability.correlation import current_correlation

router = APIRouter()


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaintenanceScopePayload(StrictPayload):
    kind: Literal["all", "contributor", "capability", "domain", "category"] = "all"
    value: str | None = Field(default=None, max_length=100)


class MaintenanceInspectionPayload(StrictPayload):
    scope: MaintenanceScopePayload = Field(default_factory=MaintenanceScopePayload)
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)


class MaintenancePlanPayload(StrictPayload):
    scope: MaintenanceScopePayload = Field(default_factory=MaintenanceScopePayload)
    older_than_hours: int = Field(default=24, ge=1, le=8760)
    expires_in_seconds: int = Field(default=1800, ge=30, le=86400)
    dry_run: bool = True
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)


class MaintenanceExecutionPayload(StrictPayload):
    checksum: str = Field(min_length=64, max_length=64)
    expected_revision: int = Field(ge=1)
    confirmed: bool = False
    approval_id: str | None = None
    timeout_seconds: float = Field(default=10.0, gt=0, le=60)


class MaintenanceCancelPayload(StrictPayload):
    expected_revision: int = Field(ge=1)


def _scope(payload: MaintenanceScopePayload) -> MaintenanceScope:
    value = payload.value.strip() if payload.value else None
    if payload.kind == "all" and value is not None:
        raise ValidationError("The all scope cannot include a value")
    if payload.kind != "all" and not value:
        raise ValidationError(f"The {payload.kind} scope requires a registered value")
    if value and any(token in value for token in ("/", "\\", "..")):
        raise ValidationError("Scope values cannot contain filesystem path syntax")
    return MaintenanceScope(MaintenanceScopeKind(payload.kind), value)


def _correlation_id() -> str | None:
    correlation = current_correlation()
    return correlation.correlation_id if correlation else None


@router.get("/maintenance/status")
def maintenance_status(
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
):
    require_admin(x_actor_type)
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    runtime.permissions.require(context, "maintenance.admin")
    return asdict(runtime.maintenance.status())


@router.post("/maintenance/inspect")
def maintenance_inspect(
    payload: MaintenanceInspectionPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
):
    require_admin(x_actor_type)
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        correlation_id = _correlation_id()
        request_model = MaintenanceInspectionRequest(
            scope=_scope(payload.scope),
            timeout_seconds=payload.timeout_seconds,
            **({"correlation_id": correlation_id} if correlation_id else {}),
        )
        return asdict(runtime.maintenance.inspect(context, request_model))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/maintenance/plan")
def maintenance_plan(
    payload: MaintenancePlanPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
):
    require_admin(x_actor_type)
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        correlation_id = _correlation_id()
        plan_request = MaintenancePlanRequest(
            scope=_scope(payload.scope),
            older_than_hours=payload.older_than_hours,
            expires_in_seconds=payload.expires_in_seconds,
            dry_run=payload.dry_run,
            timeout_seconds=payload.timeout_seconds,
            **({"correlation_id": correlation_id} if correlation_id else {}),
        )
        return asdict(runtime.maintenance.create_plan(context, plan_request))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/maintenance/plans/{plan_id}")
def maintenance_plan_show(
    plan_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
):
    require_admin(x_actor_type)
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    runtime.permissions.require(context, "maintenance.admin")
    try:
        return asdict(runtime.maintenance.get_plan(plan_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/maintenance/plans/{plan_id}/execute")
def maintenance_execute(
    plan_id: str,
    payload: MaintenanceExecutionPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
):
    require_admin(x_actor_type)
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        correlation_id = _correlation_id()
        execution = MaintenanceExecutionRequest(
            plan_id=plan_id,
            checksum=payload.checksum,
            expected_revision=payload.expected_revision,
            confirmed=payload.confirmed,
            approval_id=payload.approval_id,
            timeout_seconds=payload.timeout_seconds,
            **({"correlation_id": correlation_id} if correlation_id else {}),
        )
        return asdict(runtime.maintenance.execute(context, execution))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/maintenance/plans/{plan_id}/cancel")
def maintenance_cancel(
    plan_id: str,
    payload: MaintenanceCancelPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
):
    require_admin(x_actor_type)
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.maintenance.cancel(context, plan_id, payload.expected_revision))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/maintenance/history")
def maintenance_history(
    request: Request,
    limit: int = 100,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
):
    require_admin(x_actor_type)
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    runtime.permissions.require(context, "maintenance.admin")
    return [asdict(item) for item in runtime.maintenance.history(limit)]


@router.get("/maintenance/contributors")
def maintenance_contributors(
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
):
    require_admin(x_actor_type)
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    runtime.permissions.require(context, "maintenance.admin")
    return [asdict(item) for item in runtime.maintenance.list_contributors()]
