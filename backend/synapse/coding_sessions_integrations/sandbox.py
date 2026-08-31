"""Reference-only compatibility with the frozen Sandbox execution boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from synapse.coding_sessions import (
    CODING_SESSION_INTENT_POLICY_VERSION,
    CodingSessionArtifactReference,
    CodingSessionContract,
    CodingSessionFingerprint,
    CodingSessionIntent,
    CodingSessionIntentCategory,
    CodingSessionLifecycleState,
    CodingSessionSandboxAttemptReference,
    CodingSessionSandboxPlanReference,
    CodingSessionStateProjection,
    CodingSessionTargetAuthority,
    FencingTokenV1,
)
from synapse.sandbox import (
    CapabilityDeclaration,
    OpaqueReference,
    RequestedCapability,
    SandboxAdmissionRequest,
    SandboxArtifactFingerprint,
    SandboxAttemptId,
    SandboxIsolationProfileId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxPolicyVersion,
    SandboxWorkloadId,
)

CODING_SESSION_SANDBOX_COMPATIBILITY_VERSION = (
    "coding-session-sandbox-compatibility-v1"
)


class CodingSessionSandboxRequestKind(str, Enum):
    ADMISSION = "admission"
    EXECUTION = "execution"
    OBSERVATION = "observation"
    CANCELLATION_TERMINATION = "cancellation-termination"
    RECONCILIATION_RECOVERY = "reconciliation-recovery"


class CodingSessionSandboxReceiptState(str, Enum):
    ADMISSION_PENDING = "admission-pending"
    ADMITTED = "admitted"
    DENIED = "denied"
    MATERIALIZED = "materialized"
    RUNNING = "running"
    WAITING = "waiting"
    EXITED = "exited"
    TERMINATION_REQUESTED = "termination-requested"
    TERMINATION_OBSERVED = "termination-observed"
    TERMINATION_PROVED = "termination-proved"
    CLEANUP_INCOMPLETE = "cleanup-incomplete"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class CodingSessionExecutionBindingProjectionState(str, Enum):
    NONE = "none"
    REQUESTED = "requested"
    ADMITTED = "admitted"
    RUNNING = "running"
    WAITING = "waiting"
    EXITED_UNVERIFIED = "exited-unverified"
    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CodingSessionSandboxDiagnosticCode(str, Enum):
    SESSION_MISMATCH = "session-mismatch"
    INTENT_MISMATCH = "intent-mismatch"
    PLAN_ATTEMPT_MISMATCH = "plan-attempt-mismatch"
    ACTOR_PURPOSE_CORRELATION_MISMATCH = "actor-purpose-correlation-mismatch"
    STALE_EXECUTION_BINDING = "stale-execution-binding"
    CAPABILITY_MISMATCH = "capability-mismatch"
    AUTHORIZATION_MISMATCH = "authorization-mismatch"
    BINDING_MISMATCH = "binding-mismatch"
    EXTERNAL_REFERENCE_MISMATCH = "external-reference-mismatch"
    DUPLICATE_RECEIPT = "duplicate-receipt"
    CONTRADICTORY_OUTCOME = "contradictory-outcome"
    LATE_RESULT = "late-result"
    TERMINATION_EVIDENCE_INCOMPATIBLE = "termination-evidence-incompatible"
    VERIFICATION_EVIDENCE_INCOMPATIBLE = "verification-evidence-incompatible"
    CLEANUP_INCOMPLETE = "cleanup-incomplete"
    PRODUCER_VERSION_MISMATCH = "producer-version-mismatch"
    CAUSAL_REVISION_MISMATCH = "causal-revision-mismatch"
    LINEAGE_GAP = "lineage-gap"
    LIFECYCLE_INCOMPATIBLE = "lifecycle-incompatible"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionSandboxDiagnostic:
    code: CodingSessionSandboxDiagnosticCode
    subject: str = "sandbox-compatibility"


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxContext:
    contract: CodingSessionContract
    lifecycle: CodingSessionStateProjection
    intent: CodingSessionIntent
    workload_id: SandboxWorkloadId
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    attempt_id: SandboxAttemptId | None
    attempt_fingerprint: SandboxArtifactFingerprint | None
    requested_capabilities: tuple[str, ...]
    artifact_references: tuple[CodingSessionArtifactReference, ...]
    authorization_references: tuple[CodingSessionArtifactReference, ...]
    lease_reference: str | None
    policy_id: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxReferenceRequest:
    session_identity: str
    intent_identity: str
    actor: str
    project: str
    task: str
    purpose: str
    correlation: str
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    attempt_id: SandboxAttemptId | None
    attempt_fingerprint: SandboxArtifactFingerprint | None
    requested_capabilities: tuple[str, ...]
    repository_binding: tuple[str | None, str | None, str | None]
    artifact_references: tuple[CodingSessionArtifactReference, ...]
    authorization_references: tuple[CodingSessionArtifactReference, ...]
    lease_reference: str | None
    causal_revision: int
    policy_id: str
    policy_version: str
    fencing_token: FencingTokenV1 | None = None
    isolation_driver: None = None
    process_command: None = None


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxExecutionRequest:
    reference: CodingSessionSandboxReferenceRequest
    admission_granted_locally: bool = False
    process_started_locally: bool = False


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxObservationRequest:
    reference: CodingSessionSandboxReferenceRequest


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxCancellationRequest:
    reference: CodingSessionSandboxReferenceRequest
    termination_inferred: bool = False
    termination_proof_inferred: bool = False


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxReconciliationRequest:
    reference: CodingSessionSandboxReferenceRequest
    recovery_completed_locally: bool = False
    cleanup_completed_locally: bool = False


CodingSessionNeutralSandboxRequest: TypeAlias = (
    SandboxAdmissionRequest
    | CodingSessionSandboxExecutionRequest
    | CodingSessionSandboxObservationRequest
    | CodingSessionSandboxCancellationRequest
    | CodingSessionSandboxReconciliationRequest
)


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxTranslation:
    kind: CodingSessionSandboxRequestKind
    request: CodingSessionNeutralSandboxRequest | None
    admission_decided: bool
    driver_selected: bool
    process_started: bool
    process_terminated: bool
    capability_grant_changed: bool
    cleanup_completed: bool
    diagnostics: tuple[CodingSessionSandboxDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxReceipt:
    producer: str
    producer_version: str
    receipt_identity: str
    receipt_fingerprint: CodingSessionFingerprint
    session_identity: str
    intent_identity: str
    actor: str
    purpose: str
    correlation: str
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    attempt_id: SandboxAttemptId | None
    attempt_fingerprint: SandboxArtifactFingerprint | None
    requested_capabilities: tuple[str, ...]
    repository_binding: tuple[str | None, str | None, str | None]
    authorization_fingerprints: tuple[CodingSessionFingerprint, ...]
    external_reference_fingerprints: tuple[CodingSessionFingerprint, ...]
    state: CodingSessionSandboxReceiptState
    execution_verified: bool
    verification_evidence_identity: str | None
    verification_evidence_fingerprint: CodingSessionFingerprint | None
    termination_observed: bool
    termination_proof_identity: str | None
    termination_proof_fingerprint: CodingSessionFingerprint | None
    cleanup_complete: bool
    exit_code: int | None
    stale: bool
    causal_revision: int
    parent_receipt_identity: str | None


@dataclass(frozen=True, slots=True)
class CodingSessionSandboxProjection:
    state: CodingSessionExecutionBindingProjectionState
    plan_reference: CodingSessionSandboxPlanReference | None
    attempt_reference: CodingSessionSandboxAttemptReference | None
    admission_as_authorization: bool
    capability_as_lease: bool
    session_lifecycle_changed: bool
    session_completed: bool
    session_failed: bool
    session_cancelled: bool
    recovery_completed: bool
    reopens_terminal_session: bool
    diagnostics: tuple[CodingSessionSandboxDiagnostic, ...]


class CodingSessionSandboxCompatibilityAdapter:
    """Translate references and reconcile evidence without executing Sandbox authority."""

    @staticmethod
    def admission_request(
        context: CodingSessionSandboxContext,
        *,
        isolation_profile_id: SandboxIsolationProfileId,
        isolation_policy_version: SandboxPolicyVersion,
        execution_profile: OpaqueReference,
    ) -> CodingSessionSandboxTranslation:
        diagnostics = _context_diagnostics(context)
        request = None
        if not diagnostics:
            request = SandboxAdmissionRequest(
                workload_id=context.workload_id,
                subject=OpaqueReference(context.contract.session_identity.value),
                handoff_fingerprint=SandboxArtifactFingerprint.from_content(
                    context.intent.fingerprint.value
                ),
                actor_ref=OpaqueReference(context.contract.actor.value),
                purpose=context.contract.purpose.purpose.value,
                correlation_ref=OpaqueReference(context.contract.correlation.value),
                policy_refs=(OpaqueReference(context.policy_id),),
                approval_ref=(
                    OpaqueReference(context.authorization_references[0].identity)
                    if context.authorization_references
                    else None
                ),
                declared_capabilities=tuple(
                    CapabilityDeclaration(item) for item in context.requested_capabilities
                ),
                requested_capabilities=tuple(
                    RequestedCapability(item) for item in context.requested_capabilities
                ),
                requested_resources=(),
                execution_profile=execution_profile,
                isolation_policy_version=isolation_policy_version,
                isolation_profile_id=isolation_profile_id,
                structurally_complete=True,
            )
        return _translation(CodingSessionSandboxRequestKind.ADMISSION, request, diagnostics)

    @staticmethod
    def execution_request(context: CodingSessionSandboxContext) -> CodingSessionSandboxTranslation:
        diagnostics = _context_diagnostics(context)
        request = None if diagnostics else CodingSessionSandboxExecutionRequest(_reference(context))
        return _translation(CodingSessionSandboxRequestKind.EXECUTION, request, diagnostics)

    @staticmethod
    def observation_request(context: CodingSessionSandboxContext) -> CodingSessionSandboxTranslation:
        diagnostics = _context_diagnostics(context, require_attempt=True)
        request = None if diagnostics else CodingSessionSandboxObservationRequest(_reference(context))
        return _translation(CodingSessionSandboxRequestKind.OBSERVATION, request, diagnostics)

    @staticmethod
    def cancellation_request(context: CodingSessionSandboxContext) -> CodingSessionSandboxTranslation:
        diagnostics = _context_diagnostics(context, require_attempt=True, allow_terminal=True)
        request = None if diagnostics else CodingSessionSandboxCancellationRequest(_reference(context))
        return _translation(CodingSessionSandboxRequestKind.CANCELLATION_TERMINATION, request, diagnostics)

    @staticmethod
    def reconciliation_request(context: CodingSessionSandboxContext) -> CodingSessionSandboxTranslation:
        diagnostics = _context_diagnostics(context, require_attempt=True, allow_terminal=True)
        request = None if diagnostics else CodingSessionSandboxReconciliationRequest(_reference(context))
        return _translation(CodingSessionSandboxRequestKind.RECONCILIATION_RECOVERY, request, diagnostics)

    @staticmethod
    def project_receipt(
        context: CodingSessionSandboxContext,
        receipt: CodingSessionSandboxReceipt,
        *,
        known_receipts: tuple[CodingSessionSandboxReceipt, ...] = (),
    ) -> CodingSessionSandboxProjection:
        findings = set(_context_diagnostics(context, allow_terminal=True))
        comparisons = (
            (receipt.session_identity, context.contract.session_identity.value, CodingSessionSandboxDiagnosticCode.SESSION_MISMATCH),
            (receipt.intent_identity, context.intent.intent_identity.value, CodingSessionSandboxDiagnosticCode.INTENT_MISMATCH),
            ((receipt.actor, receipt.purpose, receipt.correlation), (context.contract.actor.value, context.contract.purpose.purpose.value, context.contract.correlation.value), CodingSessionSandboxDiagnosticCode.ACTOR_PURPOSE_CORRELATION_MISMATCH),
            ((receipt.plan_id, receipt.plan_fingerprint), (context.plan_id, context.plan_fingerprint), CodingSessionSandboxDiagnosticCode.PLAN_ATTEMPT_MISMATCH),
            ((receipt.attempt_id, receipt.attempt_fingerprint), (context.attempt_id, context.attempt_fingerprint), CodingSessionSandboxDiagnosticCode.PLAN_ATTEMPT_MISMATCH),
            (receipt.requested_capabilities, context.requested_capabilities, CodingSessionSandboxDiagnosticCode.CAPABILITY_MISMATCH),
            (receipt.repository_binding, _binding(context), CodingSessionSandboxDiagnosticCode.BINDING_MISMATCH),
            (receipt.authorization_fingerprints, _fingerprints(context.authorization_references), CodingSessionSandboxDiagnosticCode.AUTHORIZATION_MISMATCH),
            (receipt.external_reference_fingerprints, _fingerprints(context.artifact_references), CodingSessionSandboxDiagnosticCode.EXTERNAL_REFERENCE_MISMATCH),
        )
        for actual, expected, code in comparisons:
            if actual != expected:
                findings.add(CodingSessionSandboxDiagnostic(code))
        if receipt.producer != "sandbox" or receipt.producer_version != "v1":
            findings.add(CodingSessionSandboxDiagnostic(CodingSessionSandboxDiagnosticCode.PRODUCER_VERSION_MISMATCH))
        if receipt.stale:
            findings.add(CodingSessionSandboxDiagnostic(CodingSessionSandboxDiagnosticCode.STALE_EXECUTION_BINDING))
        if receipt.causal_revision < context.intent.causal_metadata.revision.value:
            findings.add(CodingSessionSandboxDiagnostic(CodingSessionSandboxDiagnosticCode.CAUSAL_REVISION_MISMATCH))
        if receipt.causal_revision > 1 and receipt.parent_receipt_identity is None:
            findings.add(CodingSessionSandboxDiagnostic(CodingSessionSandboxDiagnosticCode.LINEAGE_GAP))
        if receipt.state is CodingSessionSandboxReceiptState.CLEANUP_INCOMPLETE or not receipt.cleanup_complete:
            findings.add(CodingSessionSandboxDiagnostic(CodingSessionSandboxDiagnosticCode.CLEANUP_INCOMPLETE))
        if receipt.termination_proof_identity is not None and (
            not receipt.termination_observed or receipt.termination_proof_fingerprint is None
        ):
            findings.add(CodingSessionSandboxDiagnostic(CodingSessionSandboxDiagnosticCode.TERMINATION_EVIDENCE_INCOMPATIBLE))
        if receipt.execution_verified and (
            receipt.verification_evidence_identity is None
            or receipt.verification_evidence_fingerprint is None
        ):
            findings.add(CodingSessionSandboxDiagnostic(CodingSessionSandboxDiagnosticCode.VERIFICATION_EVIDENCE_INCOMPATIBLE))
        terminal_states = {
            CodingSessionSandboxReceiptState.EXITED,
            CodingSessionSandboxReceiptState.TERMINATION_PROVED,
            CodingSessionSandboxReceiptState.FAILED,
            CodingSessionSandboxReceiptState.DENIED,
        }
        for known in known_receipts:
            if known.receipt_identity == receipt.receipt_identity:
                code = CodingSessionSandboxDiagnosticCode.DUPLICATE_RECEIPT if known == receipt else CodingSessionSandboxDiagnosticCode.CONTRADICTORY_OUTCOME
                findings.add(CodingSessionSandboxDiagnostic(code))
            if known.attempt_id == receipt.attempt_id and known.state in terminal_states and receipt.state in terminal_states and known.state is not receipt.state:
                findings.add(CodingSessionSandboxDiagnostic(CodingSessionSandboxDiagnosticCode.CONTRADICTORY_OUTCOME))
            if known.causal_revision == receipt.causal_revision and known.receipt_identity != receipt.receipt_identity:
                findings.add(CodingSessionSandboxDiagnostic(CodingSessionSandboxDiagnosticCode.CAUSAL_REVISION_MISMATCH))
        if context.lifecycle.lifecycle is CodingSessionLifecycleState.TERMINAL:
            findings.add(CodingSessionSandboxDiagnostic(CodingSessionSandboxDiagnosticCode.LATE_RESULT))
        diagnostics = _ordered(findings)
        correspondence_failed = any(item.code in _CORRESPONDENCE_FAILURES for item in diagnostics)
        plan_reference = None
        attempt_reference = None
        if not correspondence_failed:
            plan_reference = CodingSessionSandboxPlanReference.create(
                receipt.producer, receipt.producer_version, receipt.plan_id.value,
                CodingSessionFingerprint.from_content(receipt.plan_fingerprint.value),
            )
            if receipt.attempt_id and receipt.attempt_fingerprint:
                attempt_reference = CodingSessionSandboxAttemptReference.create(
                    receipt.producer, receipt.producer_version, receipt.attempt_id.value,
                    CodingSessionFingerprint.from_content(receipt.attempt_fingerprint.value),
                )
        return CodingSessionSandboxProjection(
            _projection_state(receipt), plan_reference, attempt_reference,
            False, False, False, False, False, False, False, False, diagnostics,
        )


def _context_diagnostics(context: CodingSessionSandboxContext, *, require_attempt: bool = False, allow_terminal: bool = False) -> tuple[CodingSessionSandboxDiagnostic, ...]:
    contract, intent = context.contract, context.intent
    checks = (
        (intent.session_identity != contract.session_identity, CodingSessionSandboxDiagnosticCode.SESSION_MISMATCH),
        (intent.actor != contract.actor or intent.purpose != contract.purpose or intent.correlation != contract.correlation, CodingSessionSandboxDiagnosticCode.ACTOR_PURPOSE_CORRELATION_MISMATCH),
        (intent.binding != contract.binding, CodingSessionSandboxDiagnosticCode.BINDING_MISMATCH),
        (intent.target_authority is not CodingSessionTargetAuthority.SANDBOX, CodingSessionSandboxDiagnosticCode.CAPABILITY_MISMATCH),
        (intent.category not in {CodingSessionIntentCategory.SANDBOX_EXECUTION_REQUEST, CodingSessionIntentCategory.SANDBOX_CANCELLATION_REQUEST}, CodingSessionSandboxDiagnosticCode.CAPABILITY_MISMATCH),
        (intent.policy_version != CODING_SESSION_INTENT_POLICY_VERSION, CodingSessionSandboxDiagnosticCode.PRODUCER_VERSION_MISMATCH),
        (require_attempt and (context.attempt_id is None or context.attempt_fingerprint is None), CodingSessionSandboxDiagnosticCode.PLAN_ATTEMPT_MISMATCH),
        (not allow_terminal and context.lifecycle.lifecycle not in {CodingSessionLifecycleState.PREPARED, CodingSessionLifecycleState.ACTIVE}, CodingSessionSandboxDiagnosticCode.LIFECYCLE_INCOMPATIBLE),
    )
    return _ordered({CodingSessionSandboxDiagnostic(code) for failed, code in checks if failed})


def _reference(context: CodingSessionSandboxContext) -> CodingSessionSandboxReferenceRequest:
    contract = context.contract
    return CodingSessionSandboxReferenceRequest(
        contract.session_identity.value, context.intent.intent_identity.value,
        contract.actor.value, contract.project.value, contract.purpose.task.value,
        contract.purpose.purpose.value, contract.correlation.value,
        context.plan_id, context.plan_fingerprint, context.attempt_id,
        context.attempt_fingerprint, context.requested_capabilities, _binding(context),
        tuple(sorted(set(context.artifact_references), key=lambda item: item.identity)),
        tuple(sorted(set(context.authorization_references), key=lambda item: item.identity)),
        context.lease_reference, context.intent.causal_metadata.revision.value,
        context.policy_id, context.policy_version,
    )


def _binding(context: CodingSessionSandboxContext) -> tuple[str | None, str | None, str | None]:
    binding = context.contract.binding
    return (
        binding.repository.identity if binding.repository else None,
        binding.checkout.identity if binding.checkout else None,
        binding.worktree.identity if binding.worktree else None,
    )


def _fingerprints(references: tuple[CodingSessionArtifactReference, ...]) -> tuple[CodingSessionFingerprint, ...]:
    return tuple(sorted((item.fingerprint for item in references if item.fingerprint), key=lambda item: item.value))


def _translation(kind, request, diagnostics):
    return CodingSessionSandboxTranslation(
        kind, request, False, False, False, False, False, False, diagnostics
    )


def _ordered(findings: set[CodingSessionSandboxDiagnostic]) -> tuple[CodingSessionSandboxDiagnostic, ...]:
    return tuple(sorted(findings, key=lambda item: (item.code.value, item.subject)))


def _projection_state(receipt: CodingSessionSandboxReceipt) -> CodingSessionExecutionBindingProjectionState:
    if (
        receipt.execution_verified
        and receipt.verification_evidence_identity is not None
        and receipt.verification_evidence_fingerprint is not None
    ):
        return CodingSessionExecutionBindingProjectionState.VERIFIED
    return {
        CodingSessionSandboxReceiptState.ADMISSION_PENDING: CodingSessionExecutionBindingProjectionState.REQUESTED,
        CodingSessionSandboxReceiptState.ADMITTED: CodingSessionExecutionBindingProjectionState.ADMITTED,
        CodingSessionSandboxReceiptState.DENIED: CodingSessionExecutionBindingProjectionState.FAILED,
        CodingSessionSandboxReceiptState.MATERIALIZED: CodingSessionExecutionBindingProjectionState.ADMITTED,
        CodingSessionSandboxReceiptState.RUNNING: CodingSessionExecutionBindingProjectionState.RUNNING,
        CodingSessionSandboxReceiptState.WAITING: CodingSessionExecutionBindingProjectionState.WAITING,
        CodingSessionSandboxReceiptState.EXITED: CodingSessionExecutionBindingProjectionState.EXITED_UNVERIFIED,
        CodingSessionSandboxReceiptState.TERMINATION_REQUESTED: CodingSessionExecutionBindingProjectionState.RUNNING,
        CodingSessionSandboxReceiptState.TERMINATION_OBSERVED: CodingSessionExecutionBindingProjectionState.EXITED_UNVERIFIED,
        CodingSessionSandboxReceiptState.TERMINATION_PROVED: CodingSessionExecutionBindingProjectionState.EXITED_UNVERIFIED,
        CodingSessionSandboxReceiptState.CLEANUP_INCOMPLETE: CodingSessionExecutionBindingProjectionState.UNKNOWN,
        CodingSessionSandboxReceiptState.FAILED: CodingSessionExecutionBindingProjectionState.FAILED,
        CodingSessionSandboxReceiptState.UNAVAILABLE: CodingSessionExecutionBindingProjectionState.UNKNOWN,
        CodingSessionSandboxReceiptState.UNKNOWN: CodingSessionExecutionBindingProjectionState.UNKNOWN,
    }[receipt.state]


_CORRESPONDENCE_FAILURES = {
    CodingSessionSandboxDiagnosticCode.SESSION_MISMATCH,
    CodingSessionSandboxDiagnosticCode.INTENT_MISMATCH,
    CodingSessionSandboxDiagnosticCode.PLAN_ATTEMPT_MISMATCH,
    CodingSessionSandboxDiagnosticCode.ACTOR_PURPOSE_CORRELATION_MISMATCH,
    CodingSessionSandboxDiagnosticCode.CAPABILITY_MISMATCH,
    CodingSessionSandboxDiagnosticCode.AUTHORIZATION_MISMATCH,
    CodingSessionSandboxDiagnosticCode.BINDING_MISMATCH,
    CodingSessionSandboxDiagnosticCode.EXTERNAL_REFERENCE_MISMATCH,
    CodingSessionSandboxDiagnosticCode.CONTRADICTORY_OUTCOME,
    CodingSessionSandboxDiagnosticCode.TERMINATION_EVIDENCE_INCOMPATIBLE,
    CodingSessionSandboxDiagnosticCode.VERIFICATION_EVIDENCE_INCOMPATIBLE,
    CodingSessionSandboxDiagnosticCode.PRODUCER_VERSION_MISMATCH,
    CodingSessionSandboxDiagnosticCode.CAUSAL_REVISION_MISMATCH,
    CodingSessionSandboxDiagnosticCode.LINEAGE_GAP,
}
