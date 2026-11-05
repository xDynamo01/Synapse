from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from synapse.api.common import api_error, context_from, runtime_from
from synapse.core.execution_policy import ResourcePolicy
from synapse.mom.contracts import Configuration, Operation, Result, Route

router = APIRouter()


class MoMSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool
    resource_policy: ResourcePolicy | None = None
    routes: tuple[Route, ...] = Field(max_length=5)
    expected_revision: int = Field(ge=0, strict=True)
    workspace_id: str = Field(default="default", pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class MoMOperationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Operation
    message: str = Field(min_length=1, max_length=32000)
    workspace_id: str = Field(default="default", pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@router.get("/primary/mom/configuration")
def mom_configuration(request: Request, workspace_id: str = "default",
                      x_actor_id: str | None = Header(default=None),
                      x_actor_type: str | None = Header(default=None)) -> Configuration:
    runtime = runtime_from(request)
    try:
        return runtime.mom.get_configuration(context_from(runtime, x_actor_id, x_actor_type), workspace_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.put("/primary/mom/configuration")
def configure_mom(payload: MoMSettingsPayload, request: Request,
                  x_actor_id: str | None = Header(default=None),
                  x_actor_type: str | None = Header(default=None)) -> Configuration:
    runtime = runtime_from(request)
    try:
        return runtime.mom.configure(context_from(runtime, x_actor_id, x_actor_type),
                                     payload.workspace_id, payload.enabled, payload.routes,
                                     payload.expected_revision, payload.resource_policy)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/primary/mom/operations")
def execute_mom(payload: MoMOperationPayload, request: Request,
                x_actor_id: str | None = Header(default=None),
                x_actor_type: str | None = Header(default=None)) -> Result:
    runtime = runtime_from(request)
    try:
        return runtime.mom.execute(context_from(runtime, x_actor_id, x_actor_type),
                                   payload.operation, payload.message, payload.workspace_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/primary/mom/resources")
def mom_resources(request: Request, workspace_id: str = "default",
                  x_actor_id: str | None = Header(default=None),
                  x_actor_type: str | None = Header(default=None)) -> dict[str, object]:
    runtime = runtime_from(request)
    try:
        return runtime.mom.resource_status(context_from(runtime, x_actor_id, x_actor_type), workspace_id)
    except Exception as exc:
        raise api_error(exc) from exc
