"""Pure outbound intents, external receipts, and factual correspondence projection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from .causal import CodingSessionCausalMetadata
from .contracts import (
    CodingSessionBinding,
    CodingSessionContract,
    CodingSessionContractAssessment,
    CodingSessionPurpose,
    CodingSessionRequestedCapability,
)
from .identities import (
    CodingSessionExternalReceiptIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionIntentIdentity,
    CodingSessionLeaseFactIdentity,
)
from .leases import CodingSessionLeaseFact, CodingSessionOwnershipProjection
from .lifecycle import CodingSessionLifecycleState, CodingSessionStateProjection
from .references import (
    CodingSessionActorReference,
    CodingSessionApprovalReference,
    CodingSessionArtifactReference,
    CodingSessionAuthorizationReference,
    CodingSessionCheckoutReference,
    CodingSessionCorrelationReference,
    CodingSessionDeploymentCandidateReference,
    CodingSessionPrivateEvalEvidenceReference,
    CodingSessionPrivateEvalResultReference,
    CodingSessionPrivateEvalRunReference,
    CodingSessionRepositoryReference,
    CodingSessionSandboxAttemptReference,
    CodingSessionSandboxPlanReference,
    CodingSessionSandboxResultReference,
    CodingSessionWorkerAssignmentReference,
    CodingSessionWorkerAttemptReference,
    CodingSessionWorktreeReference,
)

CODING_SESSION_INTENT_POLICY_VERSION = "coding-session-intent-policy-v1"

CodingSessionProducerReference: TypeAlias = (
    CodingSessionRepositoryReference
    | CodingSessionCheckoutReference
    | CodingSessionWorktreeReference
    | CodingSessionWorkerAssignmentReference
    | CodingSessionWorkerAttemptReference
    | CodingSessionSandboxPlanReference
    | CodingSessionSandboxAttemptReference
    | CodingSessionSandboxResultReference
    | CodingSessionAuthorizationReference
    | CodingSessionApprovalReference
    | CodingSessionPrivateEvalRunReference
    | CodingSessionPrivateEvalResultReference
    | CodingSessionPrivateEvalEvidenceReference
    | CodingSessionArtifactReference
    | CodingSessionDeploymentCandidateReference
)


class CodingSessionIntentCategory(str, Enum):
    REPOSITORY_OBSERVATION = "repository-observation"
    REPOSITORY_MUTATION_PLANNING = "repository-mutation-planning"
    REPOSITORY_APPLICATION = "repository-application"
    REPOSITORY_VERIFICATION = "repository-verification"
    REPOSITORY_RECOVERY = "repository-recovery"
    AUTHORIZATION_REQUEST = "authorization-request"
    WORKER_ASSISTANCE_REQUEST = "worker-assistance-request"
    SANDBOX_EXECUTION_REQUEST = "sandbox-execution-request"
    SANDBOX_CANCELLATION_REQUEST = "sandbox-cancellation-request"
    PRIVATE_EVAL_REQUEST = "private-eval-request"
    ARTIFACT_REQUEST = "artifact-request"
    DEPLOYMENT_CANDIDATE_HANDOFF = "deployment-candidate-handoff"


class CodingSessionTargetAuthority(str, Enum):
    REPOSITORY_RUNTIME = "repository-runtime"
    GOVERNANCE_APPROVALS = "governance-approvals"
    WORKERS = "workers"
    SANDBOX = "sandbox"
    PRIVATE_EVALS = "private-evals"
    ARTIFACT_AUTHORITY = "artifact-authority"
    DEPLOYMENT_RUNTIME = "deployment-runtime"


class CodingSessionReceiptOutcome(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class CodingSessionReceiptCompleteness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class CodingSessionIntentReceiptStatus(str, Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    RESPONDED = "responded"
    STALE = "stale"
    LATE = "late"
    MISMATCHED = "mismatched"
    UNRESOLVED = "unresolved"


class CodingSessionIntentDiagnosticCode(str, Enum):
    CONTRACT_INVALID = "contract-invalid"
    CAPABILITY_NOT_DECLARED = "capability-not-declared"
    SESSION_MISMATCH = "session-mismatch"
    ACTOR_MISMATCH = "actor-mismatch"
    PURPOSE_MISMATCH = "purpose-mismatch"
    CORRELATION_MISMATCH = "correlation-mismatch"
    BINDING_MISMATCH = "binding-mismatch"
    TARGET_AUTHORITY_MISMATCH = "target-authority-mismatch"
    LIFECYCLE_INCOMPATIBLE = "lifecycle-incompatible"
    WRITE_LEASE_REQUIRED = "write-lease-required"
    SCOPE_ESCALATION = "scope-escalation"
    RECEIPT_INTENT_NOT_FOUND = "receipt-intent-not-found"
    PRODUCER_MISMATCH = "producer-mismatch"
    ARTIFACT_MISMATCH = "artifact-mismatch"
    UNEXPECTED_OUTCOME = "unexpected-outcome"
    DUPLICATE_RECEIPT_IDENTITY = "duplicate-receipt-identity"
    DUPLICATE_CAUSAL_REVISION = "duplicate-causal-revision"
    LINEAGE_GAP = "lineage-gap"
    STALE_RECEIPT = "stale-receipt"
    LATE_RECEIPT = "late-receipt"
    UNSUPPORTED_POLICY_VERSION = "unsupported-policy-version"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionIntentDiagnostic:
    code: CodingSessionIntentDiagnosticCode
    subject: str = "intent-receipt"


@dataclass(frozen=True, slots=True)
class CodingSessionIntentRequirement:
    requested_capability: CodingSessionRequestedCapability
    accepted_outcomes: frozenset[CodingSessionReceiptOutcome]
    write_coordination_required: bool = False


@dataclass(frozen=True, slots=True)
class CodingSessionIntent:
    intent_identity: CodingSessionIntentIdentity
    session_identity: CodingSessionIdentity
    actor: CodingSessionActorReference
    purpose: CodingSessionPurpose
    correlation: CodingSessionCorrelationReference
    category: CodingSessionIntentCategory
    target_authority: CodingSessionTargetAuthority
    target_type: str
    requirement: CodingSessionIntentRequirement
    binding: CodingSessionBinding
    external_references: tuple[CodingSessionProducerReference, ...]
    lease_reference: CodingSessionLeaseFactIdentity | None
    policy_version: str
    causal_metadata: CodingSessionCausalMetadata

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "external_references",
            tuple(
                sorted(
                    set(self.external_references),
                    key=lambda item: (item.producer, item.artifact_type, item.identity),
                )
            ),
        )

    def semantic_content(self) -> object:
        return (
            self.intent_identity,
            self.session_identity,
            self.actor,
            self.purpose,
            self.correlation,
            self.category,
            self.target_authority,
            self.target_type,
            self.requirement,
            self.binding,
            self.external_references,
            self.lease_reference,
            self.policy_version,
            self.causal_metadata,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionIntentAssessment:
    accepted: bool
    intent_fingerprint: CodingSessionFingerprint
    diagnostics: tuple[CodingSessionIntentDiagnostic, ...]

    @classmethod
    def assess(
        cls,
        intent: CodingSessionIntent,
        contract: CodingSessionContract,
        lifecycle: CodingSessionStateProjection,
        ownership: CodingSessionOwnershipProjection | None = None,
        lease_facts: tuple[CodingSessionLeaseFact, ...] = (),
    ) -> CodingSessionIntentAssessment:
        findings: set[CodingSessionIntentDiagnostic] = set()
        contract_assessment = CodingSessionContractAssessment.assess(contract)
        if not contract_assessment.complete or not contract_assessment.valid:
            findings.add(_diagnostic(CodingSessionIntentDiagnosticCode.CONTRACT_INVALID))
        if intent.policy_version != CODING_SESSION_INTENT_POLICY_VERSION:
            findings.add(
                _diagnostic(CodingSessionIntentDiagnosticCode.UNSUPPORTED_POLICY_VERSION)
            )
        if intent.causal_metadata.semantic_identity != intent.intent_identity:
            findings.add(_diagnostic(CodingSessionIntentDiagnosticCode.LINEAGE_GAP))
        if (
            intent.session_identity != contract.session_identity
            or lifecycle.session_identity != intent.session_identity
            or intent.binding.session_identity != intent.session_identity
        ):
            findings.add(_diagnostic(CodingSessionIntentDiagnosticCode.SESSION_MISMATCH))
        if intent.actor != contract.actor:
            findings.add(_diagnostic(CodingSessionIntentDiagnosticCode.ACTOR_MISMATCH))
        if intent.purpose != contract.purpose:
            findings.add(_diagnostic(CodingSessionIntentDiagnosticCode.PURPOSE_MISMATCH))
        if intent.correlation != contract.correlation:
            findings.add(_diagnostic(CodingSessionIntentDiagnosticCode.CORRELATION_MISMATCH))
        if intent.binding != contract.binding:
            findings.add(_diagnostic(CodingSessionIntentDiagnosticCode.BINDING_MISMATCH))
        declared = {item.code for item in contract.requested_capabilities}
        if intent.requirement.requested_capability not in declared:
            findings.add(
                _diagnostic(CodingSessionIntentDiagnosticCode.CAPABILITY_NOT_DECLARED)
            )
        expected_authority = _CATEGORY_AUTHORITY[intent.category]
        if intent.target_authority is not expected_authority:
            findings.add(
                _diagnostic(CodingSessionIntentDiagnosticCode.TARGET_AUTHORITY_MISMATCH)
            )
        if lifecycle.lifecycle not in {
            CodingSessionLifecycleState.PREPARED,
            CodingSessionLifecycleState.ACTIVE,
        }:
            findings.add(
                _diagnostic(CodingSessionIntentDiagnosticCode.LIFECYCLE_INCOMPATIBLE)
            )
        if intent.requirement.write_coordination_required and not _has_write_lease(
            intent, ownership, lease_facts
        ):
            findings.add(_diagnostic(CodingSessionIntentDiagnosticCode.WRITE_LEASE_REQUIRED))
        return cls(
            accepted=not findings,
            intent_fingerprint=intent.fingerprint,
            diagnostics=tuple(sorted(findings)),
        )


@dataclass(frozen=True, slots=True)
class CodingSessionExternalReceipt:
    receipt_identity: CodingSessionExternalReceiptIdentity
    session_identity: CodingSessionIdentity
    intent_identity: CodingSessionIntentIdentity
    intent_fingerprint: CodingSessionFingerprint
    producer_authority: CodingSessionTargetAuthority
    producer_artifact: CodingSessionProducerReference
    producer_version: str
    producer_fingerprint: CodingSessionFingerprint | None
    correlated_references: tuple[CodingSessionProducerReference, ...]
    actor: CodingSessionActorReference
    purpose: CodingSessionPurpose
    correlation: CodingSessionCorrelationReference
    binding: CodingSessionBinding
    outcome: CodingSessionReceiptOutcome
    completeness: CodingSessionReceiptCompleteness
    policy_version: str
    causal_metadata: CodingSessionCausalMetadata

    def semantic_content(self) -> object:
        return (
            self.receipt_identity,
            self.session_identity,
            self.intent_identity,
            self.intent_fingerprint,
            self.producer_authority,
            self.producer_artifact,
            self.producer_version,
            self.producer_fingerprint,
            self.correlated_references,
            self.actor,
            self.purpose,
            self.correlation,
            self.binding,
            self.outcome,
            self.completeness,
            self.policy_version,
            self.causal_metadata,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionIntentReceiptBinding:
    session_identity: CodingSessionIdentity
    intent_identity: CodingSessionIntentIdentity
    intent_fingerprint: CodingSessionFingerprint
    receipt_identity: CodingSessionExternalReceiptIdentity | None
    receipt_fingerprint: CodingSessionFingerprint
    status: CodingSessionIntentReceiptStatus
    diagnostics: tuple[CodingSessionIntentDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CodingSessionReceiptAssessment:
    corresponding: bool
    late: bool
    stale: bool
    binding: CodingSessionIntentReceiptBinding

    @classmethod
    def assess(
        cls,
        receipt: CodingSessionExternalReceipt,
        intent: CodingSessionIntent | None,
        lifecycle: CodingSessionStateProjection,
    ) -> CodingSessionReceiptAssessment:
        findings = _receipt_diagnostics(receipt, intent, lifecycle)
        codes = {item.code for item in findings}
        late = CodingSessionIntentDiagnosticCode.LATE_RECEIPT in codes
        stale = CodingSessionIntentDiagnosticCode.STALE_RECEIPT in codes
        mismatch_codes = codes - {
            CodingSessionIntentDiagnosticCode.LATE_RECEIPT,
            CodingSessionIntentDiagnosticCode.STALE_RECEIPT,
        }
        if mismatch_codes:
            status = CodingSessionIntentReceiptStatus.MISMATCHED
        elif late:
            status = CodingSessionIntentReceiptStatus.LATE
        elif stale:
            status = CodingSessionIntentReceiptStatus.STALE
        elif receipt.completeness is not CodingSessionReceiptCompleteness.COMPLETE:
            status = CodingSessionIntentReceiptStatus.UNRESOLVED
        elif receipt.outcome is CodingSessionReceiptOutcome.ACKNOWLEDGED:
            status = CodingSessionIntentReceiptStatus.ACKNOWLEDGED
        else:
            status = CodingSessionIntentReceiptStatus.RESPONDED
        binding = CodingSessionIntentReceiptBinding(
            session_identity=receipt.session_identity,
            intent_identity=receipt.intent_identity,
            intent_fingerprint=receipt.intent_fingerprint,
            receipt_identity=receipt.receipt_identity,
            receipt_fingerprint=receipt.fingerprint,
            status=status,
            diagnostics=findings,
        )
        return cls(not mismatch_codes and not stale, late, stale, binding)


@dataclass(frozen=True, slots=True)
class CodingSessionIntentReceiptProjection:
    session_identity: CodingSessionIdentity
    bindings: tuple[CodingSessionIntentReceiptBinding, ...]
    diagnostics: tuple[CodingSessionIntentDiagnostic, ...]
    valid: bool

    @classmethod
    def project(
        cls,
        session_identity: CodingSessionIdentity,
        intents: tuple[CodingSessionIntent, ...],
        receipts: tuple[CodingSessionExternalReceipt, ...],
        lifecycle: CodingSessionStateProjection,
    ) -> CodingSessionIntentReceiptProjection:
        diagnostics: set[CodingSessionIntentDiagnostic] = set()
        if len({item.receipt_identity for item in receipts}) != len(receipts):
            diagnostics.add(
                _diagnostic(CodingSessionIntentDiagnosticCode.DUPLICATE_RECEIPT_IDENTITY)
            )
        for intent_identity in {item.intent_identity for item in receipts}:
            revisions = [
                item.causal_metadata.revision.value
                for item in receipts
                if item.intent_identity == intent_identity
            ]
            if len(revisions) != len(set(revisions)):
                diagnostics.add(
                    _diagnostic(CodingSessionIntentDiagnosticCode.DUPLICATE_CAUSAL_REVISION)
                )
        if lifecycle.session_identity != session_identity or any(
            item.session_identity != session_identity for item in intents
        ):
            diagnostics.add(_diagnostic(CodingSessionIntentDiagnosticCode.SESSION_MISMATCH))
        bindings: list[CodingSessionIntentReceiptBinding] = []
        for intent in sorted(intents, key=lambda item: item.intent_identity.value):
            matching = sorted(
                (item for item in receipts if item.intent_identity == intent.intent_identity),
                key=lambda item: item.causal_metadata.revision.value,
            )
            if not matching:
                bindings.append(
                    CodingSessionIntentReceiptBinding(
                        session_identity=intent.session_identity,
                        intent_identity=intent.intent_identity,
                        intent_fingerprint=intent.fingerprint,
                        receipt_identity=None,
                        receipt_fingerprint=CodingSessionFingerprint.from_content(
                            (intent.fingerprint, "pending")
                        ),
                        status=CodingSessionIntentReceiptStatus.PENDING,
                        diagnostics=(),
                    )
                )
                continue
            previous_fingerprint = intent.fingerprint
            expected_revision = intent.causal_metadata.revision.value + 1
            for receipt in matching:
                if (
                    receipt.causal_metadata.revision.value != expected_revision
                    or receipt.causal_metadata.lineage.parents != (previous_fingerprint,)
                ):
                    diagnostics.add(_diagnostic(CodingSessionIntentDiagnosticCode.LINEAGE_GAP))
                assessment = CodingSessionReceiptAssessment.assess(
                    receipt, intent, lifecycle
                )
                diagnostics.update(assessment.binding.diagnostics)
                bindings.append(assessment.binding)
                previous_fingerprint = receipt.fingerprint
                expected_revision += 1
        unmatched = tuple(
            receipt
            for receipt in receipts
            if not any(intent.intent_identity == receipt.intent_identity for intent in intents)
        )
        for receipt in unmatched:
            assessment = CodingSessionReceiptAssessment.assess(receipt, None, lifecycle)
            diagnostics.update(assessment.binding.diagnostics)
            bindings.append(assessment.binding)
        return cls(
            session_identity=session_identity,
            bindings=tuple(
                sorted(
                    bindings,
                    key=lambda item: (
                        item.intent_identity.value,
                        item.receipt_identity.value if item.receipt_identity else "",
                    ),
                )
            ),
            diagnostics=tuple(sorted(diagnostics)),
            valid=not any(
                item.code
                in {
                    CodingSessionIntentDiagnosticCode.DUPLICATE_RECEIPT_IDENTITY,
                    CodingSessionIntentDiagnosticCode.DUPLICATE_CAUSAL_REVISION,
                    CodingSessionIntentDiagnosticCode.LINEAGE_GAP,
                    CodingSessionIntentDiagnosticCode.SESSION_MISMATCH,
                }
                for item in diagnostics
            ),
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(
            (self.session_identity, self.bindings, self.diagnostics, self.valid)
        )


_CATEGORY_AUTHORITY = {
    CodingSessionIntentCategory.REPOSITORY_OBSERVATION: (
        CodingSessionTargetAuthority.REPOSITORY_RUNTIME
    ),
    CodingSessionIntentCategory.REPOSITORY_MUTATION_PLANNING: (
        CodingSessionTargetAuthority.REPOSITORY_RUNTIME
    ),
    CodingSessionIntentCategory.REPOSITORY_APPLICATION: (
        CodingSessionTargetAuthority.REPOSITORY_RUNTIME
    ),
    CodingSessionIntentCategory.REPOSITORY_VERIFICATION: (
        CodingSessionTargetAuthority.REPOSITORY_RUNTIME
    ),
    CodingSessionIntentCategory.REPOSITORY_RECOVERY: (
        CodingSessionTargetAuthority.REPOSITORY_RUNTIME
    ),
    CodingSessionIntentCategory.AUTHORIZATION_REQUEST: (
        CodingSessionTargetAuthority.GOVERNANCE_APPROVALS
    ),
    CodingSessionIntentCategory.WORKER_ASSISTANCE_REQUEST: (
        CodingSessionTargetAuthority.WORKERS
    ),
    CodingSessionIntentCategory.SANDBOX_EXECUTION_REQUEST: (
        CodingSessionTargetAuthority.SANDBOX
    ),
    CodingSessionIntentCategory.SANDBOX_CANCELLATION_REQUEST: (
        CodingSessionTargetAuthority.SANDBOX
    ),
    CodingSessionIntentCategory.PRIVATE_EVAL_REQUEST: (
        CodingSessionTargetAuthority.PRIVATE_EVALS
    ),
    CodingSessionIntentCategory.ARTIFACT_REQUEST: (
        CodingSessionTargetAuthority.ARTIFACT_AUTHORITY
    ),
    CodingSessionIntentCategory.DEPLOYMENT_CANDIDATE_HANDOFF: (
        CodingSessionTargetAuthority.DEPLOYMENT_RUNTIME
    ),
}


def _has_write_lease(
    intent: CodingSessionIntent,
    ownership: CodingSessionOwnershipProjection | None,
    lease_facts: tuple[CodingSessionLeaseFact, ...],
) -> bool:
    if ownership is None or intent.lease_reference is None:
        return False
    if intent.lease_reference not in ownership.active_leases:
        return False
    return any(
        fact.lease_identity == intent.lease_reference
        and fact.session_identity == intent.session_identity
        and fact.binding == intent.binding
        and fact.capability.value == "write"
        for fact in lease_facts
    )


def _receipt_diagnostics(
    receipt: CodingSessionExternalReceipt,
    intent: CodingSessionIntent | None,
    lifecycle: CodingSessionStateProjection,
) -> tuple[CodingSessionIntentDiagnostic, ...]:
    findings: set[CodingSessionIntentDiagnostic] = set()
    add = findings.add
    if receipt.policy_version != CODING_SESSION_INTENT_POLICY_VERSION:
        add(_diagnostic(CodingSessionIntentDiagnosticCode.UNSUPPORTED_POLICY_VERSION))
    if intent is None:
        add(_diagnostic(CodingSessionIntentDiagnosticCode.RECEIPT_INTENT_NOT_FOUND))
    else:
        if receipt.session_identity != intent.session_identity:
            add(_diagnostic(CodingSessionIntentDiagnosticCode.SESSION_MISMATCH))
        if receipt.intent_fingerprint != intent.fingerprint:
            add(_diagnostic(CodingSessionIntentDiagnosticCode.STALE_RECEIPT))
        if receipt.producer_authority is not intent.target_authority:
            add(_diagnostic(CodingSessionIntentDiagnosticCode.PRODUCER_MISMATCH))
        if receipt.correlated_references != intent.external_references:
            add(_diagnostic(CodingSessionIntentDiagnosticCode.ARTIFACT_MISMATCH))
        if receipt.actor != intent.actor:
            add(_diagnostic(CodingSessionIntentDiagnosticCode.ACTOR_MISMATCH))
        if receipt.purpose != intent.purpose:
            add(_diagnostic(CodingSessionIntentDiagnosticCode.PURPOSE_MISMATCH))
        if receipt.correlation != intent.correlation:
            add(_diagnostic(CodingSessionIntentDiagnosticCode.CORRELATION_MISMATCH))
        if receipt.binding != intent.binding:
            add(_diagnostic(CodingSessionIntentDiagnosticCode.BINDING_MISMATCH))
        if receipt.outcome not in intent.requirement.accepted_outcomes:
            add(_diagnostic(CodingSessionIntentDiagnosticCode.UNEXPECTED_OUTCOME))
        if intent.fingerprint not in {
            *receipt.causal_metadata.lineage.parents,
            *receipt.causal_metadata.lineage.references,
        }:
            add(_diagnostic(CodingSessionIntentDiagnosticCode.LINEAGE_GAP))
    if (
        receipt.causal_metadata.semantic_identity != receipt.receipt_identity
        or receipt.producer_version != receipt.producer_artifact.version
        or (intent is not None and receipt.producer_artifact.artifact_type != intent.target_type)
        or (
        receipt.producer_fingerprint != receipt.producer_artifact.fingerprint
        )
    ):
        add(_diagnostic(CodingSessionIntentDiagnosticCode.ARTIFACT_MISMATCH))
    if lifecycle.lifecycle is CodingSessionLifecycleState.TERMINAL:
        add(_diagnostic(CodingSessionIntentDiagnosticCode.LATE_RECEIPT))
    return tuple(sorted(findings))


def _diagnostic(code: CodingSessionIntentDiagnosticCode) -> CodingSessionIntentDiagnostic:
    return CodingSessionIntentDiagnostic(code=code)
