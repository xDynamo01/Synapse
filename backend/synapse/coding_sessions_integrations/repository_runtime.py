"""Compatibility projection from Coding Sessions into frozen Repository DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from synapse.coding_sessions import (
    CODING_SESSION_CONTRACT_VERSION,
    CODING_SESSION_INTENT_POLICY_VERSION,
    CODING_SESSION_LEASE_POLICY_VERSION,
    CodingSessionContract,
    CodingSessionFingerprint,
    CodingSessionIntent,
    CodingSessionIntentCategory,
    CodingSessionLeaseAction,
    CodingSessionLeaseCapability,
    CodingSessionLeaseFact,
    CodingSessionLifecycleState,
    CodingSessionProducerReference,
    CodingSessionReceiptCompleteness,
    CodingSessionReceiptOutcome,
    CodingSessionRequestedCapability,
    CodingSessionStateProjection,
    CodingSessionTargetAuthority,
    CodingSessionTerminalOutcome,
    FencingTokenV1,
)
from synapse.repository_runtime import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryMutationPlan,
    RepositoryPlatformProfile,
    RepositoryWorktreeIdentity,
)
from synapse.repository_runtime_integrations import (
    CodingSessionActor as CompatibilityActor,
)
from synapse.repository_runtime_integrations import (
    CodingSessionBinding as CompatibilityBinding,
)
from synapse.repository_runtime_integrations import (
    CodingSessionCapability as CompatibilityCapability,
)
from synapse.repository_runtime_integrations import (
    CodingSessionContract as CompatibilityContract,
)
from synapse.repository_runtime_integrations import (
    CodingSessionCorrelation as CompatibilityCorrelation,
)
from synapse.repository_runtime_integrations import (
    CodingSessionIdentity as CompatibilityIdentity,
)
from synapse.repository_runtime_integrations import (
    CodingSessionLeaseMode as CompatibilityLeaseMode,
)
from synapse.repository_runtime_integrations import (
    CodingSessionLeaseScope as CompatibilityLeaseScope,
)
from synapse.repository_runtime_integrations import (
    CodingSessionLifecycle as CompatibilityLifecycle,
)
from synapse.repository_runtime_integrations import (
    CodingSessionLifecycleFact as CompatibilityLifecycleFact,
)
from synapse.repository_runtime_integrations import (
    CodingSessionOwnershipLease,
    CodingSessionRepositoryIntentAdapter,
    CodingSessionTranslationResult,
    RepositoryApplicationIntent,
    RepositoryAuthorizationIntent,
    RepositoryMutationPlanningIntent,
    RepositoryNeutralRequest,
    RepositoryObservationIntent,
    RepositoryRecoveryIntent,
)
from synapse.repository_runtime_integrations import (
    CodingSessionProjectReference as CompatibilityProjectReference,
)
from synapse.repository_runtime_integrations import (
    CodingSessionTask as CompatibilityTask,
)

CODING_SESSION_REPOSITORY_COMPATIBILITY_VERSION = (
    "coding-session-repository-compatibility-v1"
)


class CodingSessionRepositoryCompatibilityStatus(str, Enum):
    EXACT = "exact"
    DEGRADED = "degraded"
    UNREPRESENTABLE = "unrepresentable"
    REJECTED = "rejected"


class CodingSessionRepositoryCompatibilityDiagnosticCode(str, Enum):
    SESSION_MISMATCH = "session-mismatch"
    ACTOR_PURPOSE_MISMATCH = "actor-purpose-mismatch"
    BINDING_MISMATCH = "binding-mismatch"
    CAPABILITY_MISMATCH = "capability-mismatch"
    SCOPE_ESCALATION = "scope-escalation"
    LEASE_STALE = "lease-stale"
    LEASE_EXPIRED = "lease-expired"
    LEASE_REVOKED = "lease-revoked"
    UNSUPPORTED_LIFECYCLE = "unsupported-lifecycle"
    REPRESENTATIONAL_LOSS = "representational-loss"
    CONTRACT_VERSION_MISMATCH = "contract-version-mismatch"
    PRODUCER_REFERENCE_MISMATCH = "producer-reference-mismatch"
    INTENT_REQUEST_MISMATCH = "intent-request-mismatch"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionRepositoryCompatibilityDiagnostic:
    code: CodingSessionRepositoryCompatibilityDiagnosticCode
    subject: str = "repository-compatibility"


@dataclass(frozen=True, slots=True)
class CodingSessionRepositoryBinding:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity
    platform_profile: RepositoryPlatformProfile

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class CodingSessionRepositoryLifecycleProjection:
    status: CodingSessionRepositoryCompatibilityStatus
    lifecycle: CompatibilityLifecycle | None
    diagnostics: tuple[CodingSessionRepositoryCompatibilityDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CodingSessionRepositoryContractProjection:
    status: CodingSessionRepositoryCompatibilityStatus
    contract: CompatibilityContract | None
    lease: CodingSessionOwnershipLease | None
    lifecycle: CodingSessionRepositoryLifecycleProjection
    losses: tuple[str, ...]
    diagnostics: tuple[CodingSessionRepositoryCompatibilityDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CodingSessionRepositoryObservationPayload:
    pass


@dataclass(frozen=True, slots=True)
class CodingSessionRepositoryMutationPlanningPayload:
    base_snapshot_fingerprint: RepositoryFingerprint
    target_snapshot_fingerprint: RepositoryFingerprint
    change_set_fingerprint: RepositoryFingerprint
    overwrite_intents: tuple[RepositoryFingerprint, ...] = ()


@dataclass(frozen=True, slots=True)
class CodingSessionRepositoryAuthorizationPayload:
    mutation_plan: RepositoryMutationPlan
    assessment_time: int
    maximum_fact_age: int
    accepted_sources: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, slots=True)
class CodingSessionRepositoryApplicationPayload:
    base_snapshot_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    authorization_assessment_fingerprint: RepositoryFingerprint
    restore_point_result_fingerprint: RepositoryFingerprint
    attempt_reference: str
    fencing_token: FencingTokenV1 | None = None


@dataclass(frozen=True, slots=True)
class CodingSessionRepositoryRecoveryPayload:
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


RepositoryCompatibilityPayload: TypeAlias = (
    CodingSessionRepositoryObservationPayload
    | CodingSessionRepositoryMutationPlanningPayload
    | CodingSessionRepositoryAuthorizationPayload
    | CodingSessionRepositoryApplicationPayload
    | CodingSessionRepositoryRecoveryPayload
)


@dataclass(frozen=True, slots=True)
class CodingSessionRepositoryTranslationResult:
    status: CodingSessionRepositoryCompatibilityStatus
    translated_request: RepositoryNeutralRequest | None
    intent_fingerprint: CodingSessionFingerprint
    authorization_granted: bool
    operation_executed: bool
    diagnostics: tuple[CodingSessionRepositoryCompatibilityDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CodingSessionRepositoryReceiptProjection:
    status: CodingSessionRepositoryCompatibilityStatus
    producer_reference: CodingSessionProducerReference | None
    outcome: CodingSessionReceiptOutcome
    completeness: CodingSessionReceiptCompleteness
    session_completed: bool = False
    repository_correspondence_inferred: bool = False
    recovery_completed: bool = False
    lifecycle_transitioned: bool = False
    diagnostics: tuple[CodingSessionRepositoryCompatibilityDiagnostic, ...] = ()


class CodingSessionRepositoryCompatibilityAdapter:
    """Projects facts and requests without owning lease, authority, or execution."""

    def project(
        self,
        contract: CodingSessionContract,
        lifecycle: CodingSessionStateProjection,
        lease: CodingSessionLeaseFact,
        binding: CodingSessionRepositoryBinding,
        *,
        observation_time: int,
    ) -> CodingSessionRepositoryContractProjection:
        diagnostics: set[CodingSessionRepositoryCompatibilityDiagnostic] = set()
        losses: set[str] = set()
        if contract.contract_version != CODING_SESSION_CONTRACT_VERSION:
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.CONTRACT_VERSION_MISMATCH))
        if contract.session_identity != lifecycle.session_identity or lease.session_identity != contract.session_identity:
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.SESSION_MISMATCH))
        if lease.actor != contract.actor or lease.purpose != contract.purpose:
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.ACTOR_PURPOSE_MISMATCH))
        if lease.binding != contract.binding or not _binding_matches(contract, binding):
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.BINDING_MISMATCH))
        lifecycle_projection = self.project_lifecycle(lifecycle)
        diagnostics.update(lifecycle_projection.diagnostics)
        validity_diagnostic = _lease_validity_diagnostic(lease, observation_time)
        if validity_diagnostic is not None:
            diagnostics.add(validity_diagnostic)
        if lease.policy_version != CODING_SESSION_LEASE_POLICY_VERSION:
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.CONTRACT_VERSION_MISMATCH))
        if lease.interval.valid_from != lease.interval.issued_at:
            losses.add("lease-valid-from")
        if lease.causal_metadata.lineage.parents:
            losses.add("lease-causal-lineage")
        if lease.scope.level.value != "worktree":
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.SCOPE_ESCALATION))
        capabilities = _compatibility_capabilities(contract)
        compatibility_contract: CompatibilityContract | None = None
        compatibility_lease: CodingSessionOwnershipLease | None = None
        unsafe_loss = bool(losses) and lease.capability is CodingSessionLeaseCapability.WRITE
        if unsafe_loss:
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.REPRESENTATIONAL_LOSS))
        if not diagnostics and lifecycle_projection.lifecycle is not None:
            identity = CompatibilityIdentity(contract.session_identity.value)
            compatibility_binding = CompatibilityBinding(
                CompatibilityProjectReference(contract.project.value),
                binding.repository_id,
                binding.checkout_id,
                binding.worktree_id,
                binding.platform_profile,
            )
            compatibility_contract = CompatibilityContract(
                identity,
                CompatibilityActor(contract.actor.value),
                compatibility_binding,
                CompatibilityTask(contract.purpose.task.value, contract.purpose.purpose.value),
                CompatibilityCorrelation(contract.correlation.value),
                capabilities,
                CompatibilityLifecycleFact(
                    identity,
                    lifecycle_projection.lifecycle,
                    lifecycle.causal_revision,
                ),
            )
            compatibility_lease = CodingSessionOwnershipLease(
                lease.lease_identity.value,
                identity,
                compatibility_contract.actor,
                compatibility_contract.task.purpose,
                compatibility_binding,
                CompatibilityLeaseScope(lease.capability.value),
                CompatibilityLeaseMode(lease.mode.value),
                lease.interval.issued_at,
                lease.interval.expires_at,
                lease.action is CodingSessionLeaseAction.REVOKE,
            )
        ordered = tuple(sorted(diagnostics))
        if ordered:
            status = CodingSessionRepositoryCompatibilityStatus.REJECTED
        elif losses or lifecycle_projection.status is CodingSessionRepositoryCompatibilityStatus.DEGRADED:
            status = CodingSessionRepositoryCompatibilityStatus.DEGRADED
        else:
            status = CodingSessionRepositoryCompatibilityStatus.EXACT
        return CodingSessionRepositoryContractProjection(
            status,
            compatibility_contract,
            compatibility_lease,
            lifecycle_projection,
            tuple(sorted(losses)),
            ordered,
        )

    def project_lifecycle(
        self, lifecycle: CodingSessionStateProjection
    ) -> CodingSessionRepositoryLifecycleProjection:
        state = lifecycle.lifecycle
        if state is CodingSessionLifecycleState.PLANNED:
            return _lifecycle(CodingSessionRepositoryCompatibilityStatus.EXACT, CompatibilityLifecycle.PLANNED)
        if state is CodingSessionLifecycleState.PREPARED:
            return _lifecycle(CodingSessionRepositoryCompatibilityStatus.DEGRADED, CompatibilityLifecycle.PLANNED)
        if state is CodingSessionLifecycleState.ACTIVE:
            return _lifecycle(CodingSessionRepositoryCompatibilityStatus.EXACT, CompatibilityLifecycle.ACTIVE)
        if state is CodingSessionLifecycleState.SUSPENDED:
            return _lifecycle(CodingSessionRepositoryCompatibilityStatus.EXACT, CompatibilityLifecycle.SUSPENDED)
        if state is CodingSessionLifecycleState.TERMINAL:
            if lifecycle.terminal_outcome is CodingSessionTerminalOutcome.COMPLETED:
                return _lifecycle(CodingSessionRepositoryCompatibilityStatus.EXACT, CompatibilityLifecycle.COMPLETED)
            if lifecycle.terminal_outcome is CodingSessionTerminalOutcome.CANCELLED:
                return _lifecycle(CodingSessionRepositoryCompatibilityStatus.EXACT, CompatibilityLifecycle.CANCELLED)
        diagnostic = _diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.UNSUPPORTED_LIFECYCLE)
        return CodingSessionRepositoryLifecycleProjection(
            CodingSessionRepositoryCompatibilityStatus.UNREPRESENTABLE,
            None,
            (diagnostic,),
        )

    def translate(
        self,
        intent: CodingSessionIntent,
        projection: CodingSessionRepositoryContractProjection,
        payload: RepositoryCompatibilityPayload,
        *,
        observation_time: int,
    ) -> CodingSessionRepositoryTranslationResult:
        diagnostics: set[CodingSessionRepositoryCompatibilityDiagnostic] = set(projection.diagnostics)
        if intent.policy_version != CODING_SESSION_INTENT_POLICY_VERSION:
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.CONTRACT_VERSION_MISMATCH))
        if projection.contract is None or projection.lease is None:
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.INTENT_REQUEST_MISMATCH))
        elif (
            intent.session_identity.value != projection.contract.identity.value
            or intent.actor.value != projection.contract.actor.reference
            or intent.purpose.purpose.value != projection.contract.task.purpose
            or intent.correlation.value != projection.contract.correlation.reference
        ):
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.INTENT_REQUEST_MISMATCH))
        if (
            projection.lease is not None
            and intent.requirement.write_coordination_required
            and (
                intent.lease_reference is None
                or intent.lease_reference.value != projection.lease.lease_reference
            )
        ):
            diagnostics.add(
                _diagnostic(
                    CodingSessionRepositoryCompatibilityDiagnosticCode.INTENT_REQUEST_MISMATCH
                )
            )
        if intent.target_authority is not CodingSessionTargetAuthority.REPOSITORY_RUNTIME:
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.PRODUCER_REFERENCE_MISMATCH))
        if intent.requirement.requested_capability not in {
            CodingSessionRequestedCapability.REPOSITORY_ACCESS,
            CodingSessionRequestedCapability.REPOSITORY_MUTATION,
            CodingSessionRequestedCapability.APPROVAL,
        }:
            diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.CAPABILITY_MISMATCH))
        old_intent = None
        if not diagnostics and projection.contract is not None and projection.lease is not None:
            old_intent = _compatibility_intent(
                intent, projection.contract, projection.lease, payload, observation_time
            )
            if old_intent is None:
                diagnostics.add(_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.INTENT_REQUEST_MISMATCH))
        if diagnostics or old_intent is None:
            return CodingSessionRepositoryTranslationResult(
                CodingSessionRepositoryCompatibilityStatus.REJECTED,
                None,
                intent.fingerprint,
                False,
                False,
                tuple(sorted(diagnostics)),
            )
        translated: CodingSessionTranslationResult = CodingSessionRepositoryIntentAdapter().translate(old_intent)
        if translated.translated_request is None:
            return CodingSessionRepositoryTranslationResult(
                CodingSessionRepositoryCompatibilityStatus.REJECTED,
                None,
                intent.fingerprint,
                False,
                False,
                (_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.INTENT_REQUEST_MISMATCH),),
            )
        return CodingSessionRepositoryTranslationResult(
            projection.status,
            translated.translated_request,
            intent.fingerprint,
            False,
            False,
            (),
        )

    def project_receipt(
        self,
        intent: CodingSessionIntent,
        producer_reference: CodingSessionProducerReference,
        *,
        outcome: CodingSessionReceiptOutcome,
        completeness: CodingSessionReceiptCompleteness,
    ) -> CodingSessionRepositoryReceiptProjection:
        diagnostics: tuple[CodingSessionRepositoryCompatibilityDiagnostic, ...] = ()
        if intent.target_authority is not CodingSessionTargetAuthority.REPOSITORY_RUNTIME or producer_reference.producer != "repository-runtime":
            diagnostics = (_diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.PRODUCER_REFERENCE_MISMATCH),)
        return CodingSessionRepositoryReceiptProjection(
            CodingSessionRepositoryCompatibilityStatus.REJECTED
            if diagnostics
            else CodingSessionRepositoryCompatibilityStatus.EXACT,
            None if diagnostics else producer_reference,
            outcome,
            completeness,
            diagnostics=diagnostics,
        )


def _binding_matches(
    contract: CodingSessionContract, binding: CodingSessionRepositoryBinding
) -> bool:
    source = contract.binding
    if source.repository is None or source.checkout is None or source.worktree is None or source.platform_context is None:
        return False
    return (
        source.repository.identity == binding.repository_id.value
        and source.checkout.identity == binding.checkout_id.value
        and source.worktree.identity == binding.worktree_id.value
        and source.platform_context.identity == binding.fingerprint.value
    )


def _compatibility_capabilities(
    contract: CodingSessionContract,
) -> tuple[CompatibilityCapability, ...]:
    declared = {item.code for item in contract.requested_capabilities}
    capabilities: set[CompatibilityCapability] = set()
    if CodingSessionRequestedCapability.REPOSITORY_ACCESS in declared:
        capabilities.add(CompatibilityCapability.OBSERVE)
    if CodingSessionRequestedCapability.REPOSITORY_MUTATION in declared:
        capabilities.update(
            {
                CompatibilityCapability.PLAN_MUTATION,
                CompatibilityCapability.APPLY_MUTATION,
                CompatibilityCapability.REQUEST_RECOVERY,
            }
        )
    if CodingSessionRequestedCapability.APPROVAL in declared:
        capabilities.add(CompatibilityCapability.REQUEST_AUTHORIZATION)
    return tuple(sorted(capabilities, key=lambda item: item.value))


def _lease_validity_diagnostic(
    lease: CodingSessionLeaseFact, observation_time: int
) -> CodingSessionRepositoryCompatibilityDiagnostic | None:
    if lease.action is CodingSessionLeaseAction.REVOKE:
        return _diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.LEASE_REVOKED)
    if lease.action is CodingSessionLeaseAction.MARK_STALE or observation_time < lease.interval.valid_from:
        return _diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.LEASE_STALE)
    if observation_time >= lease.interval.expires_at:
        return _diagnostic(CodingSessionRepositoryCompatibilityDiagnosticCode.LEASE_EXPIRED)
    return None


def _compatibility_intent(
    intent: CodingSessionIntent,
    contract: CompatibilityContract,
    lease: CodingSessionOwnershipLease,
    payload: RepositoryCompatibilityPayload,
    observation_time: int,
) -> (
    RepositoryObservationIntent
    | RepositoryMutationPlanningIntent
    | RepositoryAuthorizationIntent
    | RepositoryApplicationIntent
    | RepositoryRecoveryIntent
    | None
):
    if intent.category is CodingSessionIntentCategory.REPOSITORY_OBSERVATION and isinstance(payload, CodingSessionRepositoryObservationPayload):
        return RepositoryObservationIntent(
            session=contract, lease=lease, observed_at=observation_time
        )
    if intent.category is CodingSessionIntentCategory.REPOSITORY_MUTATION_PLANNING and isinstance(payload, CodingSessionRepositoryMutationPlanningPayload):
        return RepositoryMutationPlanningIntent(
            session=contract,
            lease=lease,
            observed_at=observation_time,
            base_snapshot_fingerprint=payload.base_snapshot_fingerprint,
            target_snapshot_fingerprint=payload.target_snapshot_fingerprint,
            change_set_fingerprint=payload.change_set_fingerprint,
            overwrite_intents=payload.overwrite_intents,
        )
    if intent.category is CodingSessionIntentCategory.AUTHORIZATION_REQUEST and isinstance(payload, CodingSessionRepositoryAuthorizationPayload):
        return RepositoryAuthorizationIntent(
            session=contract,
            lease=lease,
            observed_at=observation_time,
            mutation_plan=payload.mutation_plan,
            assessment_time=payload.assessment_time,
            maximum_fact_age=payload.maximum_fact_age,
            accepted_sources=payload.accepted_sources,
        )
    if intent.category is CodingSessionIntentCategory.REPOSITORY_APPLICATION and isinstance(payload, CodingSessionRepositoryApplicationPayload):
        return RepositoryApplicationIntent(
            session=contract,
            lease=lease,
            observed_at=observation_time,
            base_snapshot_fingerprint=payload.base_snapshot_fingerprint,
            mutation_plan_fingerprint=payload.mutation_plan_fingerprint,
            authorization_assessment_fingerprint=payload.authorization_assessment_fingerprint,
            restore_point_result_fingerprint=payload.restore_point_result_fingerprint,
            attempt_reference=payload.attempt_reference,
        )
    if intent.category is CodingSessionIntentCategory.REPOSITORY_RECOVERY and isinstance(payload, CodingSessionRepositoryRecoveryPayload):
        return RepositoryRecoveryIntent(
            session=contract,
            lease=lease,
            observed_at=observation_time,
            base_snapshot_fingerprint=payload.base_snapshot_fingerprint,
            mutation_plan_fingerprint=payload.mutation_plan_fingerprint,
            mutation_attempt_fingerprint=payload.mutation_attempt_fingerprint,
            mutation_journal_fingerprint=payload.mutation_journal_fingerprint,
            verification_result_fingerprint=payload.verification_result_fingerprint,
            reconciliation_fingerprint=payload.reconciliation_fingerprint,
            restore_point_manifest_fingerprint=payload.restore_point_manifest_fingerprint,
            restore_point_verification_fingerprint=payload.restore_point_verification_fingerprint,
            policy_id=payload.policy_id,
            policy_version=payload.policy_version,
            recovery_reference=payload.recovery_reference,
        )
    return None


def _lifecycle(
    status: CodingSessionRepositoryCompatibilityStatus,
    lifecycle: CompatibilityLifecycle,
) -> CodingSessionRepositoryLifecycleProjection:
    return CodingSessionRepositoryLifecycleProjection(status, lifecycle, ())


def _diagnostic(
    code: CodingSessionRepositoryCompatibilityDiagnosticCode,
) -> CodingSessionRepositoryCompatibilityDiagnostic:
    return CodingSessionRepositoryCompatibilityDiagnostic(code)
