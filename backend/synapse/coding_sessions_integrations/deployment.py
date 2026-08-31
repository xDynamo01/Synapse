"""Forward-compatible deployment handoff references without deployment authority."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from synapse.coding_sessions import (
    CodingSessionActorReference,
    CodingSessionApprovalReference,
    CodingSessionArtifactReference,
    CodingSessionCausalMetadata,
    CodingSessionCheckoutReference,
    CodingSessionCorrelationReference,
    CodingSessionDeploymentCandidateReference,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionPrivateEvalEvidenceReference,
    CodingSessionPrivateEvalResultReference,
    CodingSessionProjectReference,
    CodingSessionPurpose,
    CodingSessionRepositoryReference,
    CodingSessionStateProjection,
    CodingSessionWorktreeReference,
)

CODING_SESSION_DEPLOYMENT_REFERENCE_VERSION = "coding-session-deployment-reference-v1"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")


class CodingSessionDeploymentProjectionState(str, Enum):
    ABSENT = "absent"
    CANDIDATE_PRODUCED = "candidate-produced"
    HANDOFF_REQUESTED = "handoff-requested"
    HANDED_OFF = "handed-off"
    REJECTED = "rejected"
    STALE = "stale"
    INVALIDATED = "invalidated"
    UNKNOWN = "unknown"


class CodingSessionCandidateInvalidationReason(str, Enum):
    REPOSITORY_CHANGED = "repository-changed"
    EVAL_STALE = "eval-stale"
    APPROVAL_EXPIRED = "approval-expired"
    APPROVAL_REVOKED = "approval-revoked"
    ARTIFACT_DISAPPEARED = "artifact-disappeared"
    SOURCE_VERIFICATION_MISMATCH = "source-verification-mismatch"


class CodingSessionDeploymentDiagnosticCode(str, Enum):
    SESSION_MISMATCH = "session-mismatch"
    ARTIFACT_MISMATCH = "artifact-mismatch"
    REPOSITORY_BINDING_MISMATCH = "repository-binding-mismatch"
    STALE_SOURCE_VERIFICATION = "stale-source-verification"
    MISSING_REQUIRED_EVAL = "missing-required-eval"
    MISSING_REQUIRED_APPROVAL = "missing-required-approval"
    CANDIDATE_FINGERPRINT_MISMATCH = "candidate-fingerprint-mismatch"
    DUPLICATE_HANDOFF = "duplicate-handoff"
    CONFLICTING_HANDOFF_RECEIPT = "conflicting-handoff-receipt"
    LATE_RECEIPT = "late-receipt"
    LINEAGE_GAP = "lineage-gap"
    CAUSAL_REVISION_MISMATCH = "causal-revision-mismatch"
    CANDIDATE_INVALIDATED = "candidate-invalidated"
    TARGET_AUTHORITY_MISMATCH = "target-authority-mismatch"
    POLICY_VERSION_MISMATCH = "policy-version-mismatch"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionDeploymentDiagnostic:
    code: CodingSessionDeploymentDiagnosticCode
    subject: str = "deployment-reference"


@dataclass(frozen=True, slots=True)
class CodingSessionCandidateArtifactReference:
    artifact: CodingSessionArtifactReference
    role: str
    required: bool = True

    def __post_init__(self) -> None:
        if not _TOKEN.fullmatch(self.role):
            raise ValueError("invalid candidate artifact role")


@dataclass(frozen=True, slots=True)
class CodingSessionCandidateProvenance:
    repository: CodingSessionRepositoryReference | None
    checkout: CodingSessionCheckoutReference | None
    worktree: CodingSessionWorktreeReference | None
    source_snapshot: CodingSessionArtifactReference
    source_verification: CodingSessionArtifactReference
    eval_results: tuple[CodingSessionPrivateEvalResultReference, ...] = ()
    eval_evidence: tuple[CodingSessionPrivateEvalEvidenceReference, ...] = ()
    approvals: tuple[CodingSessionApprovalReference, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("eval_results", "eval_evidence", "approvals"):
            values = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                tuple(sorted(set(values), key=lambda item: (item.producer, item.identity))),
            )


@dataclass(frozen=True, slots=True)
class CodingSessionDeploymentCandidate:
    session_identity: CodingSessionIdentity
    actor: CodingSessionActorReference
    project: CodingSessionProjectReference
    purpose: CodingSessionPurpose
    correlation: CodingSessionCorrelationReference
    candidate_identity: str
    artifacts: tuple[CodingSessionCandidateArtifactReference, ...]
    provenance: CodingSessionCandidateProvenance
    required_eval_count: int
    required_approval_count: int
    policy_id: str
    policy_version: str
    causal_metadata: CodingSessionCausalMetadata

    def __post_init__(self) -> None:
        if not _TOKEN.fullmatch(self.candidate_identity):
            raise ValueError("invalid deployment candidate identity")
        if self.required_eval_count < 0 or self.required_approval_count < 0:
            raise ValueError("invalid deployment candidate requirements")
        object.__setattr__(
            self,
            "artifacts",
            tuple(sorted(set(self.artifacts), key=lambda item: (item.role, item.artifact.identity))),
        )

    def semantic_content(self) -> object:
        return (
            CODING_SESSION_DEPLOYMENT_REFERENCE_VERSION,
            self.session_identity,
            self.actor,
            self.project,
            self.purpose,
            self.correlation,
            self.candidate_identity,
            self.artifacts,
            self.provenance,
            self.required_eval_count,
            self.required_approval_count,
            self.policy_id,
            self.policy_version,
            self.causal_metadata.semantic_content(),
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionCandidateInvalidation:
    candidate_identity: str
    candidate_fingerprint: CodingSessionFingerprint
    reason: CodingSessionCandidateInvalidationReason
    evidence_reference: CodingSessionArtifactReference
    causal_revision: int
    parent_fingerprint: CodingSessionFingerprint


@dataclass(frozen=True, slots=True)
class CodingSessionDeploymentHandoffRequest:
    session_identity: CodingSessionIdentity
    candidate_identity: str
    candidate_fingerprint: CodingSessionFingerprint
    artifact_references: tuple[CodingSessionArtifactReference, ...]
    requested_deployment_capability: str
    target_deployment_authority: str
    authorization_references: tuple[CodingSessionApprovalReference, ...]
    eval_references: tuple[CodingSessionPrivateEvalResultReference, ...]
    expected_receipt_type: str
    policy_id: str
    policy_version: str
    causal_metadata: CodingSessionCausalMetadata

    def __post_init__(self) -> None:
        for value in (
            self.candidate_identity,
            self.requested_deployment_capability,
            self.target_deployment_authority,
            self.expected_receipt_type,
        ):
            if not _TOKEN.fullmatch(value):
                raise ValueError("invalid deployment handoff reference")
        object.__setattr__(
            self,
            "artifact_references",
            tuple(sorted(set(self.artifact_references), key=lambda item: item.identity)),
        )
        object.__setattr__(
            self,
            "authorization_references",
            tuple(sorted(set(self.authorization_references), key=lambda item: item.identity)),
        )
        object.__setattr__(
            self,
            "eval_references",
            tuple(sorted(set(self.eval_references), key=lambda item: item.identity)),
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class CodingSessionDeploymentHandoffReceipt:
    producer: str
    producer_version: str
    receipt_identity: str
    receipt_fingerprint: CodingSessionFingerprint
    session_identity: CodingSessionIdentity
    candidate_identity: str
    candidate_fingerprint: CodingSessionFingerprint
    handoff_request_fingerprint: CodingSessionFingerprint
    artifact_references: tuple[CodingSessionArtifactReference, ...]
    state: CodingSessionDeploymentProjectionState
    causal_revision: int
    parent_receipt_identity: str | None


@dataclass(frozen=True, slots=True)
class CodingSessionDeploymentHandoffAssessment:
    eligible: bool
    state: CodingSessionDeploymentProjectionState
    candidate_reference: CodingSessionDeploymentCandidateReference | None
    release_created: bool
    deployment_authorized: bool
    environment_selected: bool
    artifact_published: bool
    version_promoted: bool
    rollout_executed: bool
    rollback_executed: bool
    session_lifecycle_changed: bool
    session_completed: bool
    reopens_terminal_session: bool
    candidate_history_deleted: bool
    diagnostics: tuple[CodingSessionDeploymentDiagnostic, ...]


class CodingSessionDeploymentReferenceService:
    @staticmethod
    def assess_candidate(
        candidate: CodingSessionDeploymentCandidate,
        *,
        observed_session: CodingSessionIdentity,
        observed_artifacts: tuple[CodingSessionArtifactReference, ...],
        observed_repository_binding: tuple[
            CodingSessionRepositoryReference | None,
            CodingSessionCheckoutReference | None,
            CodingSessionWorktreeReference | None,
        ],
        source_verification_fresh: bool,
        invalidations: tuple[CodingSessionCandidateInvalidation, ...] = (),
    ) -> CodingSessionDeploymentHandoffAssessment:
        findings: set[CodingSessionDeploymentDiagnostic] = set()
        if candidate.session_identity != observed_session:
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.SESSION_MISMATCH))
        expected_artifacts = tuple(item.artifact for item in candidate.artifacts)
        if set(expected_artifacts) != set(observed_artifacts):
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.ARTIFACT_MISMATCH))
        provenance = candidate.provenance
        if observed_repository_binding != (
            provenance.repository,
            provenance.checkout,
            provenance.worktree,
        ):
            findings.add(
                _diag(CodingSessionDeploymentDiagnosticCode.REPOSITORY_BINDING_MISMATCH)
            )
        if not source_verification_fresh:
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.STALE_SOURCE_VERIFICATION))
        if len(provenance.eval_results) < candidate.required_eval_count:
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.MISSING_REQUIRED_EVAL))
        if len(provenance.approvals) < candidate.required_approval_count:
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.MISSING_REQUIRED_APPROVAL))
        if any(
            item.candidate_identity == candidate.candidate_identity
            and item.candidate_fingerprint == candidate.fingerprint
            for item in invalidations
        ):
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.CANDIDATE_INVALIDATED))
        if candidate.causal_metadata.semantic_identity != candidate.session_identity:
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.LINEAGE_GAP))
        return _assessment(
            not findings,
            (
                CodingSessionDeploymentProjectionState.INVALIDATED
                if CodingSessionDeploymentDiagnosticCode.CANDIDATE_INVALIDATED
                in {item.code for item in findings}
                else CodingSessionDeploymentProjectionState.CANDIDATE_PRODUCED
            ),
            None,
            findings,
        )

    @staticmethod
    def assess_handoff(
        candidate: CodingSessionDeploymentCandidate,
        request: CodingSessionDeploymentHandoffRequest,
        *,
        candidate_assessment: CodingSessionDeploymentHandoffAssessment,
        lifecycle: CodingSessionStateProjection,
        receipt: CodingSessionDeploymentHandoffReceipt | None = None,
        known_receipts: tuple[CodingSessionDeploymentHandoffReceipt, ...] = (),
    ) -> CodingSessionDeploymentHandoffAssessment:
        findings = set(candidate_assessment.diagnostics)
        if request.session_identity != candidate.session_identity:
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.SESSION_MISMATCH))
        if request.candidate_identity != candidate.candidate_identity or request.candidate_fingerprint != candidate.fingerprint:
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.CANDIDATE_FINGERPRINT_MISMATCH))
        if set(request.artifact_references) != {item.artifact for item in candidate.artifacts}:
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.ARTIFACT_MISMATCH))
        if request.target_deployment_authority != "deployment-runtime":
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.TARGET_AUTHORITY_MISMATCH))
        if request.policy_id != candidate.policy_id or request.policy_version != candidate.policy_version:
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.POLICY_VERSION_MISMATCH))
        if request.causal_metadata.revision.value <= candidate.causal_metadata.revision.value:
            findings.add(_diag(CodingSessionDeploymentDiagnosticCode.CAUSAL_REVISION_MISMATCH))
        state = CodingSessionDeploymentProjectionState.HANDOFF_REQUESTED
        reference = None
        if receipt is not None:
            if (
                receipt.session_identity != candidate.session_identity
                or receipt.candidate_identity != candidate.candidate_identity
                or receipt.candidate_fingerprint != candidate.fingerprint
                or receipt.handoff_request_fingerprint != request.fingerprint
            ):
                findings.add(_diag(CodingSessionDeploymentDiagnosticCode.CONFLICTING_HANDOFF_RECEIPT))
            for known in known_receipts:
                if known.receipt_identity == receipt.receipt_identity:
                    code = (
                        CodingSessionDeploymentDiagnosticCode.DUPLICATE_HANDOFF
                        if known == receipt
                        else CodingSessionDeploymentDiagnosticCode.CONFLICTING_HANDOFF_RECEIPT
                    )
                    findings.add(_diag(code))
            if receipt.causal_revision > 1 and receipt.parent_receipt_identity is None:
                findings.add(_diag(CodingSessionDeploymentDiagnosticCode.LINEAGE_GAP))
            if lifecycle.lifecycle.value == "terminal":
                findings.add(_diag(CodingSessionDeploymentDiagnosticCode.LATE_RECEIPT))
            state = receipt.state
            if not any(item.code in _CORRESPONDENCE_FAILURES for item in findings):
                reference = CodingSessionDeploymentCandidateReference.create(
                    receipt.producer,
                    receipt.producer_version,
                    receipt.candidate_identity,
                    receipt.candidate_fingerprint,
                )
        return _assessment(not findings, state, reference, findings)


def _diag(code: CodingSessionDeploymentDiagnosticCode) -> CodingSessionDeploymentDiagnostic:
    return CodingSessionDeploymentDiagnostic(code)


def _assessment(eligible, state, reference, findings):
    return CodingSessionDeploymentHandoffAssessment(
        eligible,
        state,
        reference,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        tuple(sorted(findings, key=lambda item: (item.code.value, item.subject))),
    )


_CORRESPONDENCE_FAILURES = {
    CodingSessionDeploymentDiagnosticCode.SESSION_MISMATCH,
    CodingSessionDeploymentDiagnosticCode.ARTIFACT_MISMATCH,
    CodingSessionDeploymentDiagnosticCode.REPOSITORY_BINDING_MISMATCH,
    CodingSessionDeploymentDiagnosticCode.STALE_SOURCE_VERIFICATION,
    CodingSessionDeploymentDiagnosticCode.MISSING_REQUIRED_EVAL,
    CodingSessionDeploymentDiagnosticCode.MISSING_REQUIRED_APPROVAL,
    CodingSessionDeploymentDiagnosticCode.CANDIDATE_FINGERPRINT_MISMATCH,
    CodingSessionDeploymentDiagnosticCode.CONFLICTING_HANDOFF_RECEIPT,
    CodingSessionDeploymentDiagnosticCode.LINEAGE_GAP,
    CodingSessionDeploymentDiagnosticCode.CAUSAL_REVISION_MISMATCH,
    CodingSessionDeploymentDiagnosticCode.CANDIDATE_INVALIDATED,
    CodingSessionDeploymentDiagnosticCode.TARGET_AUTHORITY_MISMATCH,
    CodingSessionDeploymentDiagnosticCode.POLICY_VERSION_MISMATCH,
}
