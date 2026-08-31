"""Pure reference-only Coding Sessions translation into Repository Runtime requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from synapse.repository_runtime import (
    RepositoryAuthorizationRequirement,
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryMutationApplicationRequest,
    RepositoryMutationPlan,
    RepositoryMutationPlanRequest,
    RepositoryObservationRequest,
    RepositoryPlatformProfile,
    RepositoryRecoveryRequest,
    RepositoryWorktreeIdentity,
)

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")
_SESSION = re.compile(r"^coding-session:[0-9a-f]{64}$")


def _reference(value: str) -> None:
    if not isinstance(value, str) or not _REFERENCE.fullmatch(value):
        raise ValueError("coding session reference is invalid")


@dataclass(frozen=True, slots=True)
class CodingSessionIdentity:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _SESSION.fullmatch(self.value):
            raise ValueError("coding session identity is invalid")

    @classmethod
    def from_stable_key(cls, stable_key: str) -> CodingSessionIdentity:
        _reference(stable_key)
        digest = RepositoryFingerprint.from_content(
            ("coding-session-identity-v1", stable_key)
        ).value.removeprefix("sha256:")
        return cls(f"coding-session:{digest}")


@dataclass(frozen=True, slots=True)
class CodingSessionActor:
    reference: str

    def __post_init__(self) -> None:
        _reference(self.reference)


@dataclass(frozen=True, slots=True)
class CodingSessionProjectReference:
    reference: str

    def __post_init__(self) -> None:
        _reference(self.reference)


@dataclass(frozen=True, slots=True)
class CodingSessionTask:
    reference: str
    purpose: str

    def __post_init__(self) -> None:
        _reference(self.reference)
        _reference(self.purpose)


@dataclass(frozen=True, slots=True)
class CodingSessionCorrelation:
    reference: str

    def __post_init__(self) -> None:
        _reference(self.reference)


@dataclass(frozen=True, slots=True)
class CodingSessionBinding:
    project: CodingSessionProjectReference
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity
    platform_profile: RepositoryPlatformProfile


class CodingSessionCapability(StrEnum):
    OBSERVE = "observe"
    PLAN_MUTATION = "plan-mutation"
    REQUEST_AUTHORIZATION = "request-authorization"
    APPLY_MUTATION = "apply-mutation"
    REQUEST_RECOVERY = "request-recovery"


class CodingSessionLifecycle(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class CodingSessionLifecycleFact:
    session_id: CodingSessionIdentity
    state: CodingSessionLifecycle
    occurred_at: int

    def __post_init__(self) -> None:
        if self.occurred_at < 0:
            raise ValueError("session lifecycle time is invalid")


@dataclass(frozen=True, slots=True)
class CodingSessionContract:
    identity: CodingSessionIdentity
    actor: CodingSessionActor
    binding: CodingSessionBinding
    task: CodingSessionTask
    correlation: CodingSessionCorrelation
    requested_capabilities: tuple[CodingSessionCapability, ...]
    lifecycle: CodingSessionLifecycleFact

    def __post_init__(self) -> None:
        capabilities = tuple(sorted(set(self.requested_capabilities), key=lambda item: item.value))
        if not capabilities or self.lifecycle.session_id != self.identity:
            raise ValueError("coding session contract is invalid")
        object.__setattr__(self, "requested_capabilities", capabilities)

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


class CodingSessionLeaseScope(StrEnum):
    READ = "read"
    WRITE = "write"


class CodingSessionLeaseMode(StrEnum):
    SHARED = "shared"
    EXCLUSIVE = "exclusive"


@dataclass(frozen=True, slots=True)
class CodingSessionOwnershipLease:
    lease_reference: str
    session_id: CodingSessionIdentity
    actor: CodingSessionActor
    purpose: str
    binding: CodingSessionBinding
    scope: CodingSessionLeaseScope
    mode: CodingSessionLeaseMode
    issued_at: int
    expires_at: int
    revoked: bool = False

    def __post_init__(self) -> None:
        _reference(self.lease_reference)
        _reference(self.purpose)
        if self.issued_at < 0 or self.expires_at <= self.issued_at:
            raise ValueError("coding session lease interval is invalid")
        if (
            self.scope is CodingSessionLeaseScope.WRITE
            and self.mode is not CodingSessionLeaseMode.EXCLUSIVE
        ):
            raise ValueError("write lease must be exclusive")

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


class CodingSessionDiagnosticCode(StrEnum):
    CAPABILITY_NOT_REQUESTED = "capability_not_requested"
    BINDING_REQUIRED = "binding_required"
    BINDING_MISMATCH = "binding_mismatch"
    ACTOR_MISMATCH = "actor_mismatch"
    PURPOSE_MISMATCH = "purpose_mismatch"
    LIFECYCLE_INCOMPATIBLE = "lifecycle_incompatible"
    LEASE_STALE = "lease_stale"
    LEASE_EXPIRED = "lease_expired"
    LEASE_REVOKED = "lease_revoked"
    LEASE_SCOPE_INSUFFICIENT = "lease_scope_insufficient"
    WRITE_LEASE_CONFLICT = "write_lease_conflict"
    PLAN_MISMATCH = "plan_mismatch"


@dataclass(frozen=True, slots=True)
class CodingSessionDiagnostic:
    code: CodingSessionDiagnosticCode
    reference_fingerprint: RepositoryFingerprint | None = None


@dataclass(frozen=True, slots=True)
class CodingSessionLeaseAssessment:
    accepted: bool
    lease_fingerprint: RepositoryFingerprint
    diagnostics: tuple[CodingSessionDiagnostic, ...]


class CodingSessionTranslationStatus(StrEnum):
    TRANSLATED = "translated"
    REJECTED = "rejected"


RepositoryNeutralRequest = (
    RepositoryObservationRequest
    | RepositoryMutationPlanRequest
    | RepositoryAuthorizationRequirement
    | RepositoryMutationApplicationRequest
    | RepositoryRecoveryRequest
)


@dataclass(frozen=True, slots=True)
class CodingSessionTranslationResult:
    status: CodingSessionTranslationStatus
    session_fingerprint: RepositoryFingerprint
    intent_fingerprint: RepositoryFingerprint
    translated_request: RepositoryNeutralRequest | None
    authorization_granted: bool
    operation_executed: bool
    diagnostics: tuple[CodingSessionDiagnostic, ...]


@dataclass(frozen=True, kw_only=True, slots=True)
class _Intent:
    session: CodingSessionContract
    lease: CodingSessionOwnershipLease
    observed_at: int
    conflicting_leases: tuple[CodingSessionOwnershipLease, ...] = ()

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, kw_only=True, slots=True)
class RepositoryObservationIntent(_Intent):
    pass


@dataclass(frozen=True, kw_only=True, slots=True)
class RepositoryMutationPlanningIntent(_Intent):
    base_snapshot_fingerprint: RepositoryFingerprint
    target_snapshot_fingerprint: RepositoryFingerprint
    change_set_fingerprint: RepositoryFingerprint
    overwrite_intents: tuple[RepositoryFingerprint, ...] = ()


@dataclass(frozen=True, kw_only=True, slots=True)
class RepositoryAuthorizationIntent(_Intent):
    mutation_plan: RepositoryMutationPlan
    assessment_time: int
    maximum_fact_age: int
    accepted_sources: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, kw_only=True, slots=True)
class RepositoryApplicationIntent(_Intent):
    base_snapshot_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    authorization_assessment_fingerprint: RepositoryFingerprint
    restore_point_result_fingerprint: RepositoryFingerprint
    attempt_reference: str

    def __post_init__(self) -> None:
        _reference(self.attempt_reference)


@dataclass(frozen=True, kw_only=True, slots=True)
class RepositoryRecoveryIntent(_Intent):
    base_snapshot_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    mutation_attempt_fingerprint: RepositoryFingerprint
    mutation_journal_fingerprint: RepositoryFingerprint
    verification_result_fingerprint: RepositoryFingerprint
    reconciliation_fingerprint: RepositoryFingerprint
    restore_point_manifest_fingerprint: RepositoryFingerprint
    restore_point_verification_fingerprint: RepositoryFingerprint
    policy_id: str
    policy_version: str
    recovery_reference: str

    def __post_init__(self) -> None:
        for value in (self.policy_id, self.policy_version, self.recovery_reference):
            _reference(value)


class CodingSessionRepositoryIntentAdapter:
    """Validates coordination facts and creates DTOs; never authorizes or executes."""

    def assess_lease(
        self,
        session: CodingSessionContract,
        lease: CodingSessionOwnershipLease,
        observed_at: int,
        conflicting_leases: tuple[CodingSessionOwnershipLease, ...] = (),
        *,
        write_required: bool,
    ) -> CodingSessionLeaseAssessment:
        diagnostics: list[CodingSessionDiagnostic] = []
        if lease.session_id != session.identity:
            diagnostics.append(self._diagnostic(CodingSessionDiagnosticCode.LEASE_STALE, lease))
        if lease.binding != session.binding:
            diagnostics.append(
                self._diagnostic(CodingSessionDiagnosticCode.BINDING_MISMATCH, lease)
            )
        if lease.actor != session.actor:
            diagnostics.append(self._diagnostic(CodingSessionDiagnosticCode.ACTOR_MISMATCH, lease))
        if lease.purpose != session.task.purpose:
            diagnostics.append(
                self._diagnostic(CodingSessionDiagnosticCode.PURPOSE_MISMATCH, lease)
            )
        if lease.revoked:
            diagnostics.append(self._diagnostic(CodingSessionDiagnosticCode.LEASE_REVOKED, lease))
        if observed_at < lease.issued_at:
            diagnostics.append(self._diagnostic(CodingSessionDiagnosticCode.LEASE_STALE, lease))
        if observed_at >= lease.expires_at:
            diagnostics.append(self._diagnostic(CodingSessionDiagnosticCode.LEASE_EXPIRED, lease))
        if write_required and lease.scope is not CodingSessionLeaseScope.WRITE:
            diagnostics.append(
                self._diagnostic(CodingSessionDiagnosticCode.LEASE_SCOPE_INSUFFICIENT, lease)
            )
        if session.lifecycle.state is not CodingSessionLifecycle.ACTIVE:
            diagnostics.append(
                CodingSessionDiagnostic(CodingSessionDiagnosticCode.LIFECYCLE_INCOMPATIBLE)
            )
        if lease.scope is CodingSessionLeaseScope.WRITE:
            for other in conflicting_leases:
                if (
                    other.fingerprint != lease.fingerprint
                    and not other.revoked
                    and other.issued_at <= observed_at < other.expires_at
                    and other.scope is CodingSessionLeaseScope.WRITE
                    and other.binding == lease.binding
                ):
                    diagnostics.append(
                        self._diagnostic(CodingSessionDiagnosticCode.WRITE_LEASE_CONFLICT, other)
                    )
        ordered = _ordered_diagnostics(diagnostics)
        return CodingSessionLeaseAssessment(not ordered, lease.fingerprint, ordered)

    def translate(
        self,
        intent: RepositoryObservationIntent
        | RepositoryMutationPlanningIntent
        | RepositoryAuthorizationIntent
        | RepositoryApplicationIntent
        | RepositoryRecoveryIntent,
    ) -> CodingSessionTranslationResult:
        capability, write_required = self._required_capability(intent)
        diagnostics: list[CodingSessionDiagnostic] = []
        if capability not in intent.session.requested_capabilities:
            diagnostics.append(
                CodingSessionDiagnostic(CodingSessionDiagnosticCode.CAPABILITY_NOT_REQUESTED)
            )
        assessment = self.assess_lease(
            intent.session,
            intent.lease,
            intent.observed_at,
            intent.conflicting_leases,
            write_required=write_required,
        )
        diagnostics.extend(assessment.diagnostics)
        if isinstance(intent, RepositoryAuthorizationIntent) and not self._plan_matches(
            intent.session.binding, intent.mutation_plan
        ):
            diagnostics.append(
                self._diagnostic(CodingSessionDiagnosticCode.PLAN_MISMATCH, intent.mutation_plan)
            )
        ordered = _ordered_diagnostics(diagnostics)
        if ordered:
            return CodingSessionTranslationResult(
                CodingSessionTranslationStatus.REJECTED,
                intent.session.fingerprint,
                intent.fingerprint,
                None,
                False,
                False,
                ordered,
            )
        translated = self._translate_request(intent)
        return CodingSessionTranslationResult(
            CodingSessionTranslationStatus.TRANSLATED,
            intent.session.fingerprint,
            intent.fingerprint,
            translated,
            False,
            False,
            (),
        )

    @staticmethod
    def _required_capability(intent: _Intent) -> tuple[CodingSessionCapability, bool]:
        if isinstance(intent, RepositoryObservationIntent):
            return CodingSessionCapability.OBSERVE, False
        if isinstance(intent, RepositoryMutationPlanningIntent):
            return CodingSessionCapability.PLAN_MUTATION, False
        if isinstance(intent, RepositoryAuthorizationIntent):
            return CodingSessionCapability.REQUEST_AUTHORIZATION, False
        if isinstance(intent, RepositoryApplicationIntent):
            return CodingSessionCapability.APPLY_MUTATION, True
        return CodingSessionCapability.REQUEST_RECOVERY, True

    @staticmethod
    def _plan_matches(binding: CodingSessionBinding, plan: RepositoryMutationPlan) -> bool:
        return (
            plan.repository_id == binding.repository_id
            and plan.checkout_id == binding.checkout_id
            and plan.worktree_id == binding.worktree_id
            and plan.platform_profile == binding.platform_profile
        )

    @staticmethod
    def _translate_request(intent: _Intent) -> RepositoryNeutralRequest:
        binding = intent.session.binding
        metadata = (
            ("correlation", intent.session.correlation.reference),
            ("lease", intent.lease.fingerprint.value),
            ("lease-scope", intent.lease.scope.value),
            ("purpose", intent.session.task.purpose),
            ("session", intent.session.identity.value),
            ("task", intent.session.task.reference),
        )
        if isinstance(intent, RepositoryObservationIntent):
            return RepositoryObservationRequest(
                binding.repository_id,
                binding.checkout_id,
                binding.worktree_id,
                binding.platform_profile,
            )
        if isinstance(intent, RepositoryMutationPlanningIntent):
            return RepositoryMutationPlanRequest(
                binding.repository_id,
                binding.checkout_id,
                binding.worktree_id,
                binding.platform_profile,
                intent.base_snapshot_fingerprint,
                intent.target_snapshot_fingerprint,
                intent.change_set_fingerprint,
                intent.overwrite_intents,
                metadata,
            )
        if isinstance(intent, RepositoryAuthorizationIntent):
            return RepositoryAuthorizationRequirement.from_plan(
                intent.mutation_plan,
                actor=intent.session.actor.reference,
                purpose=intent.session.task.purpose,
                assessment_time=intent.assessment_time,
                maximum_fact_age=intent.maximum_fact_age,
                accepted_sources=intent.accepted_sources,
                occurrence_metadata=metadata,
            )
        if isinstance(intent, RepositoryApplicationIntent):
            return RepositoryMutationApplicationRequest(
                binding.repository_id,
                binding.checkout_id,
                binding.worktree_id,
                binding.platform_profile,
                intent.base_snapshot_fingerprint,
                intent.mutation_plan_fingerprint,
                intent.authorization_assessment_fingerprint,
                intent.restore_point_result_fingerprint,
                intent.attempt_reference,
                metadata,
            )
        assert isinstance(intent, RepositoryRecoveryIntent)
        return RepositoryRecoveryRequest(
            binding.repository_id,
            binding.checkout_id,
            binding.worktree_id,
            binding.platform_profile,
            intent.base_snapshot_fingerprint,
            intent.mutation_plan_fingerprint,
            intent.mutation_attempt_fingerprint,
            intent.mutation_journal_fingerprint,
            intent.verification_result_fingerprint,
            intent.reconciliation_fingerprint,
            intent.restore_point_manifest_fingerprint,
            intent.restore_point_verification_fingerprint,
            intent.policy_id,
            intent.policy_version,
            intent.recovery_reference,
            metadata,
        )

    @staticmethod
    def _diagnostic(code: CodingSessionDiagnosticCode, value: object) -> CodingSessionDiagnostic:
        return CodingSessionDiagnostic(code, RepositoryFingerprint.from_content(value))


def _ordered_diagnostics(
    diagnostics: list[CodingSessionDiagnostic],
) -> tuple[CodingSessionDiagnostic, ...]:
    return tuple(
        sorted(
            set(diagnostics),
            key=lambda item: (
                item.code.value,
                item.reference_fingerprint.value if item.reference_fingerprint else "",
            ),
        )
    )
