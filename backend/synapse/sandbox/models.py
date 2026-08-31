"""Pure immutable models for the Sandbox Execution Boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import InvalidSandboxModel, SandboxInvariantViolation
from .identities import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxAttemptId,
    SandboxIsolationProfileId,
    SandboxPolicyVersion,
    SandboxWorkloadId,
)
from .states import (
    SandboxCleanupState,
    SandboxRollbackState,
)

_NAME = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_SECRET_WORDS = ("secret=", "token=", "password=", "credential=")


def _bounded_text(value: str, name: str, *, maximum: int = 512) -> None:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise InvalidSandboxModel(f"{name} must be non-empty and bounded")
    lowered = value.lower()
    if any(marker in lowered for marker in _SECRET_WORDS):
        raise InvalidSandboxModel(f"{name} cannot contain secret values")
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", value):
        raise InvalidSandboxModel(f"{name} cannot contain an absolute path")
    if ".." in value.replace("\\", "/").split("/"):
        raise InvalidSandboxModel(f"{name} cannot contain path traversal")


def _name(value: str, name: str) -> None:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise InvalidSandboxModel(f"{name} must be a bounded semantic name")


def _positive(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InvalidSandboxModel(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class CapabilityDeclaration:
    name: str

    def __post_init__(self) -> None:
        _name(self.name, "capability declaration")


@dataclass(frozen=True, slots=True)
class RequestedCapability:
    name: str
    required: bool = True

    def __post_init__(self) -> None:
        _name(self.name, "requested capability")


@dataclass(frozen=True, slots=True)
class ResourceRequest:
    resource: str
    amount: int
    unit: str

    def __post_init__(self) -> None:
        _name(self.resource, "resource")
        _positive(self.amount, "resource amount")
        _name(self.unit, "resource unit")


@dataclass(frozen=True, slots=True)
class ResourceLimit:
    resource: str
    maximum: int
    unit: str

    def __post_init__(self) -> None:
        _name(self.resource, "resource")
        _positive(self.maximum, "resource maximum")
        _name(self.unit, "resource unit")


@dataclass(frozen=True, slots=True)
class SandboxAdmissionRequest:
    workload_id: SandboxWorkloadId
    subject: OpaqueReference
    handoff_fingerprint: SandboxArtifactFingerprint
    actor_ref: OpaqueReference
    purpose: str
    correlation_ref: OpaqueReference
    policy_refs: tuple[OpaqueReference, ...]
    approval_ref: OpaqueReference | None
    declared_capabilities: tuple[CapabilityDeclaration, ...]
    requested_capabilities: tuple[RequestedCapability, ...]
    requested_resources: tuple[ResourceRequest, ...]
    execution_profile: OpaqueReference
    isolation_policy_version: SandboxPolicyVersion
    isolation_profile_id: SandboxIsolationProfileId
    secret_refs: tuple[OpaqueReference, ...] = ()
    structurally_complete: bool = False

    def __post_init__(self) -> None:
        _bounded_text(self.purpose, "purpose", maximum=256)
        if len({item.name for item in self.declared_capabilities}) != len(
            self.declared_capabilities
        ):
            raise SandboxInvariantViolation("capability declarations must be unique")
        if len({item.name for item in self.requested_capabilities}) != len(
            self.requested_capabilities
        ):
            raise SandboxInvariantViolation("requested capabilities must be unique")


@dataclass(frozen=True, slots=True)
class SandboxCleanupResult:
    attempt_id: SandboxAttemptId
    state: SandboxCleanupState
    verification_ref: OpaqueReference | None = None

    def __post_init__(self) -> None:
        if self.state is SandboxCleanupState.VERIFIED and self.verification_ref is None:
            raise SandboxInvariantViolation("verified cleanup requires verification reference")


@dataclass(frozen=True, slots=True)
class SandboxRollbackResult:
    attempt_id: SandboxAttemptId
    state: SandboxRollbackState
    evidence_ref: OpaqueReference | None = None

    def __post_init__(self) -> None:
        if self.state is SandboxRollbackState.COMPLETED and self.evidence_ref is None:
            raise SandboxInvariantViolation("completed rollback requires evidence reference")
