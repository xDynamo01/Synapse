from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from synapse.core.execution_policy import ResourcePolicy
from synapse.core.permissions import PermissionContext


class Operation(StrEnum):
    CONVERSATION = "conversation"
    CODING = "coding"
    REASONING = "reasoning"
    REVIEW = "review"
    SUMMARY = "summary"


class Route(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    operation: Operation
    provider: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    model: str = Field(min_length=1, max_length=256, pattern=r"^[^\r\n]+$")


class Configuration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    workspace_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    primary_agent_id: str
    enabled: StrictBool = False
    revision: int = Field(default=0, ge=0, strict=True)
    routes: tuple[Route, ...] = ()
    resource_policy: ResourcePolicy = ResourcePolicy.RESPONSIVE

    @model_validator(mode="after")
    def unique_operations(self) -> Configuration:
        if len({route.operation for route in self.routes}) != len(self.routes):
            raise ValueError("Each MoM operation must have exactly one route.")
        return self


class Output(BaseModel):
    model_config = ConfigDict(frozen=True)
    content: str
    provider: str
    model: str


class Result(Output):
    operation_id: str
    operation: Operation
    primary_agent_id: str
    configuration_revision: int


class ConfigurationPort(Protocol):
    def read(self, workspace_id: str) -> Configuration | None: ...
    def write(self, configuration: Configuration, expected_revision: int) -> None: ...


class PrimaryPort(Protocol):
    def current_agent(self, workspace_id: str) -> str: ...


class InferencePort(Protocol):
    def validate_route(self, route: Route) -> None: ...
    def generate(self, context: PermissionContext, primary_agent_id: str,
                 route: Route, message: str, operation_id: str) -> Output: ...


class ResourcePolicyPort(Protocol):
    def apply(self, policy: ResourcePolicy) -> None: ...
    def status(self) -> dict[str, object]: ...
