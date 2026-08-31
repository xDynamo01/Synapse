"""Driver-local coordination of execution grants, fencing and preconditions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable, Protocol

from synapse.sandbox import OpaqueReference, SandboxArtifactFingerprint, SandboxWorkspaceId


class WindowsExecutionGrantStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class WindowsAuthorityDecision(StrEnum):
    ALLOWED = "allowed"
    GRANT_MISSING = "grant_missing"
    GRANT_INVALID = "grant_invalid"
    GRANT_STALE = "grant_stale"
    CAPABILITY_MISMATCH = "capability_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    FENCING_MISSING = "fencing_missing"
    FENCING_STALE = "fencing_stale"
    FENCING_UNAVAILABLE = "fencing_unavailable"
    FENCING_MISMATCHED = "fencing_mismatched"
    PRECONDITION_STALE = "precondition_stale"
    AUTHORITY_UNAVAILABLE = "authority_unavailable"


@dataclass(frozen=True, slots=True)
class WindowsExecutionGrantV1:
    grant_reference: OpaqueReference
    subject_reference: OpaqueReference
    requester_reference: OpaqueReference
    workload_reference: OpaqueReference
    plan_reference: OpaqueReference
    attempt_reference: OpaqueReference
    workspace_id: SandboxWorkspaceId
    capabilities: tuple[OpaqueReference, ...]
    resource_grants: tuple[OpaqueReference, ...]
    operations: tuple[str, ...]
    policy_reference: OpaqueReference
    revision: int
    status: WindowsExecutionGrantStatus
    expires_at: datetime
    grant_fingerprint: SandboxArtifactFingerprint

    def __post_init__(self) -> None:
        if self.revision < 1 or self.expires_at.tzinfo is None:
            raise ValueError("grant_invalid")
        if self.operations != tuple(sorted(set(self.operations))):
            raise ValueError("grant_invalid")


@dataclass(frozen=True, slots=True)
class WindowsAuthorityContextV1:
    session_reference: OpaqueReference
    subject_reference: OpaqueReference
    requester_reference: OpaqueReference
    workload_reference: OpaqueReference
    plan_reference: OpaqueReference
    attempt_reference: OpaqueReference
    workspace_id: SandboxWorkspaceId
    grant: WindowsExecutionGrantV1 | None
    required_capabilities: tuple[OpaqueReference, ...] = ()
    required_resource_grants: tuple[OpaqueReference, ...] = ()
    policy_reference: OpaqueReference | None = None
    expected_precondition: SandboxArtifactFingerprint | None = None
    idempotency_reference: OpaqueReference | None = None


class WindowsGrantValidationPort(Protocol):
    def validate(self, grant: WindowsExecutionGrantV1) -> bool: ...


class WindowsPreconditionValidationPort(Protocol):
    def validate(
        self,
        context: WindowsAuthorityContextV1,
        operation: str,
        expected: SandboxArtifactFingerprint,
    ) -> bool: ...


class WindowsAuthorityFencingPort(Protocol):
    def validate(self, workspace_id: SandboxWorkspaceId, operation: str) -> object: ...


@dataclass(frozen=True, slots=True)
class WindowsAuthorityAuditFact:
    operation: str
    authorization_validated: bool
    fencing_validated: bool
    precondition_validated: bool | None
    effect_attempted: bool
    effect_applied: bool
    effect_blocked: bool
    decision: WindowsAuthorityDecision


@dataclass(frozen=True, slots=True)
class WindowsAuthorityCheck:
    allowed: bool
    decision: WindowsAuthorityDecision
    audit: WindowsAuthorityAuditFact


class WindowsExecutionAuthorityGuard:
    def __init__(
        self,
        grants: WindowsGrantValidationPort | None,
        fencing: WindowsAuthorityFencingPort | None,
        *,
        preconditions: WindowsPreconditionValidationPort | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._grants = grants
        self._fencing = fencing
        self._preconditions = preconditions
        self._now = now

    def authorize(
        self,
        context: WindowsAuthorityContextV1 | None,
        workspace_id: SandboxWorkspaceId,
        operation: str,
    ) -> WindowsAuthorityCheck:
        decision = self._grant_decision(context, workspace_id, operation)
        if decision is not WindowsAuthorityDecision.ALLOWED:
            return self._blocked(operation, decision, False, False, None)
        assert context is not None and context.grant is not None
        if self._fencing is None:
            return self._blocked(
                operation, WindowsAuthorityDecision.FENCING_MISSING, True, False, None
            )
        fence = self._fencing.validate(workspace_id, operation)
        fence_value = str(getattr(fence, "value", fence))
        fence_decision = {
            "stale": WindowsAuthorityDecision.FENCING_STALE,
            "unavailable": WindowsAuthorityDecision.FENCING_UNAVAILABLE,
            "invalid": WindowsAuthorityDecision.FENCING_MISMATCHED,
        }.get(fence_value)
        if fence_value not in {"valid", "stale", "unavailable", "invalid"}:
            fence_decision = WindowsAuthorityDecision.AUTHORITY_UNAVAILABLE
        if fence_decision is not None:
            return self._blocked(operation, fence_decision, True, False, None)
        precondition_validated: bool | None = None
        if context.expected_precondition is not None:
            if self._preconditions is None:
                return self._blocked(
                    operation, WindowsAuthorityDecision.AUTHORITY_UNAVAILABLE, True, True, False
                )
            precondition_validated = self._preconditions.validate(
                context, operation, context.expected_precondition
            )
            if not precondition_validated:
                return self._blocked(
                    operation, WindowsAuthorityDecision.PRECONDITION_STALE, True, True, False
                )
        audit = WindowsAuthorityAuditFact(
            operation, True, True, precondition_validated, True, False, False,
            WindowsAuthorityDecision.ALLOWED,
        )
        return WindowsAuthorityCheck(True, WindowsAuthorityDecision.ALLOWED, audit)

    @staticmethod
    def applied(check: WindowsAuthorityCheck) -> WindowsAuthorityAuditFact:
        if not check.allowed:
            return check.audit
        audit = check.audit
        return WindowsAuthorityAuditFact(
            audit.operation, True, True, audit.precondition_validated, True, True, False,
            WindowsAuthorityDecision.ALLOWED,
        )

    def _grant_decision(
        self,
        context: WindowsAuthorityContextV1 | None,
        workspace_id: SandboxWorkspaceId,
        operation: str,
    ) -> WindowsAuthorityDecision:
        if context is None or context.grant is None:
            return WindowsAuthorityDecision.GRANT_MISSING
        grant = context.grant
        if self._grants is None:
            return WindowsAuthorityDecision.AUTHORITY_UNAVAILABLE
        if not self._grants.validate(grant):
            return WindowsAuthorityDecision.GRANT_INVALID
        if grant.status is not WindowsExecutionGrantStatus.ACTIVE or self._now() >= grant.expires_at:
            return WindowsAuthorityDecision.GRANT_STALE
        if (
            context.workspace_id != workspace_id
            or grant.workspace_id != workspace_id
            or grant.subject_reference != context.subject_reference
            or grant.requester_reference != context.requester_reference
            or grant.workload_reference != context.workload_reference
            or grant.plan_reference != context.plan_reference
            or grant.attempt_reference != context.attempt_reference
            or context.policy_reference != grant.policy_reference
            or operation not in grant.operations
        ):
            return WindowsAuthorityDecision.SCOPE_MISMATCH
        if not set(context.required_capabilities) <= set(grant.capabilities) or not set(
            context.required_resource_grants
        ) <= set(grant.resource_grants):
            return WindowsAuthorityDecision.CAPABILITY_MISMATCH
        return WindowsAuthorityDecision.ALLOWED

    @staticmethod
    def _blocked(
        operation: str,
        decision: WindowsAuthorityDecision,
        authorized: bool,
        fenced: bool,
        precondition: bool | None,
    ) -> WindowsAuthorityCheck:
        return WindowsAuthorityCheck(
            False,
            decision,
            WindowsAuthorityAuditFact(
                operation, authorized, fenced, precondition, False, False, True, decision
            ),
        )

    def health(self) -> WindowsAuthorityHealth:
        grants = self._grants is not None
        fencing = self._fencing is not None
        enforced = grants and fencing
        return WindowsAuthorityHealth(grants, fencing, True, enforced, False)


@dataclass(frozen=True, slots=True)
class WindowsAuthorityHealth:
    grant_validation_available: bool
    fencing_validation_available: bool
    mutation_guard_available: bool
    sandbox_end_to_end_fencing_enforced: bool
    repository_end_to_end_fencing_enforced: bool
