"""Pure pause, resume, and cancellation assessments without external effects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from .causal import CodingSessionCausalMetadata
from .contracts import CodingSessionContract, CodingSessionPurpose
from .identities import (
    CodingSessionExternalReceiptIdentity,
    CodingSessionFactIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionIntentIdentity,
)
from .intents import CodingSessionProducerReference
from .journal import (
    CodingSessionCheckpointAssessment,
    CodingSessionCheckpointDurabilityState,
    CodingSessionJournalAssessment,
)
from .leases import CodingSessionOwnershipProjection
from .lifecycle import (
    CodingSessionCancellationState,
    CodingSessionCoordinationState,
    CodingSessionLifecycleFact,
    CodingSessionLifecycleState,
    CodingSessionRecoveryState,
    CodingSessionRepositoryCorrespondenceState,
    CodingSessionStateDimension,
    CodingSessionStateProjection,
    CodingSessionTransitionAssessment,
    CodingSessionTransitionReason,
    CodingSessionTransitionRequest,
)
from .references import (
    CodingSessionActorReference,
    CodingSessionCorrelationReference,
)

CODING_SESSION_CONTROL_POLICY_VERSION = "coding-session-control-policy-v1"


class CodingSessionControlDiagnosticCode(str, Enum):
    SESSION_MISMATCH = "session-mismatch"
    ACTOR_PURPOSE_MISMATCH = "actor-purpose-mismatch"
    CORRELATION_MISMATCH = "correlation-mismatch"
    CAUSAL_REVISION_MISMATCH = "causal-revision-mismatch"
    LIFECYCLE_INCOMPATIBLE = "lifecycle-incompatible"
    MANUAL_INTERVENTION_REQUIRED = "manual-intervention-required"
    BINDING_UNKNOWN = "binding-unknown"
    CHECKPOINT_INELIGIBLE = "checkpoint-ineligible"
    CHECKPOINT_MISMATCH = "checkpoint-mismatch"
    JOURNAL_INCOMPLETE = "journal-incomplete"
    PERSISTENCE_EVIDENCE_MISSING = "persistence-evidence-missing"
    LEASE_INELIGIBLE = "lease-ineligible"
    REPOSITORY_INELIGIBLE = "repository-ineligible"
    CANCELLATION_PENDING = "cancellation-pending"
    RECOVERY_REQUIRED = "recovery-required"
    PREREQUISITE_MISSING = "prerequisite-missing"
    DUPLICATE_RESUME = "duplicate-resume"
    DUPLICATE_CANCELLATION_REQUEST = "duplicate-cancellation-request"
    ACKNOWLEDGEMENT_MISMATCH = "acknowledgement-mismatch"
    EVIDENCE_MISMATCH = "evidence-mismatch"
    DUPLICATE_CAUSAL_REVISION = "duplicate-causal-revision"
    LINEAGE_GAP = "lineage-gap"
    TERMINATION_INCOMPLETE = "termination-incomplete"
    LATE_FACT = "late-fact"
    UNSUPPORTED_POLICY_VERSION = "unsupported-policy-version"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionControlDiagnostic:
    code: CodingSessionControlDiagnosticCode
    subject: str = "session-control"


@dataclass(frozen=True, slots=True)
class CodingSessionPauseRequest:
    session_identity: CodingSessionIdentity
    expected_causal_revision: int
    reason_reference: CodingSessionFingerprint
    occurrence_metadata: tuple[tuple[str, str], ...] = ()
    policy_version: str = CODING_SESSION_CONTROL_POLICY_VERSION

    def semantic_content(self) -> object:
        return (
            self.session_identity,
            self.expected_causal_revision,
            self.reason_reference,
            self.policy_version,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionPauseAssessment:
    eligible: bool
    diagnostics: tuple[CodingSessionControlDiagnostic, ...]
    lifecycle_fact: CodingSessionLifecycleFact | None

    @classmethod
    def assess(
        cls,
        request: CodingSessionPauseRequest,
        lifecycle: CodingSessionStateProjection,
        contract: CodingSessionContract,
    ) -> CodingSessionPauseAssessment:
        findings: set[CodingSessionControlDiagnostic] = set()
        if request.policy_version != CODING_SESSION_CONTROL_POLICY_VERSION:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.UNSUPPORTED_POLICY_VERSION))
        if request.session_identity != lifecycle.session_identity or request.session_identity != contract.session_identity:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.SESSION_MISMATCH))
        if request.expected_causal_revision != lifecycle.causal_revision:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.CAUSAL_REVISION_MISMATCH))
        if lifecycle.lifecycle is not CodingSessionLifecycleState.ACTIVE:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.LIFECYCLE_INCOMPATIBLE))
        if lifecycle.coordination is CodingSessionCoordinationState.CONFLICTED or lifecycle.recovery is CodingSessionRecoveryState.MANUAL_INTERVENTION:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.MANUAL_INTERVENTION_REQUIRED))
        if contract.binding.scope.value != "none" and contract.binding.repository is None:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.BINDING_UNKNOWN))
        if findings:
            return cls(False, tuple(sorted(findings)), None)
        transition = CodingSessionTransitionAssessment.assess(
            CodingSessionTransitionRequest(
                session_identity=request.session_identity,
                dimension=CodingSessionStateDimension.LIFECYCLE,
                expected_previous_state=CodingSessionLifecycleState.ACTIVE,
                next_state=CodingSessionLifecycleState.SUSPENDED,
                reason=CodingSessionTransitionReason.SUSPENSION_CONFIRMED,
                expected_causal_revision=request.expected_causal_revision,
                evidence=(request.reason_reference,),
                occurrence_metadata=request.occurrence_metadata,
            ),
            lifecycle,
        )
        return cls(transition.accepted, (), transition.fact)


@dataclass(frozen=True, slots=True)
class CodingSessionResumeRequest:
    session_identity: CodingSessionIdentity
    expected_causal_revision: int
    checkpoint_identity: str
    checkpoint_fingerprint: CodingSessionFingerprint
    checkpoint_revision: int
    persistence_evidence: CodingSessionFingerprint | None
    required_prerequisites: frozenset[CodingSessionFingerprint] = frozenset()
    satisfied_prerequisites: frozenset[CodingSessionFingerprint] = frozenset()
    occurrence_metadata: tuple[tuple[str, str], ...] = ()
    policy_version: str = CODING_SESSION_CONTROL_POLICY_VERSION

    def semantic_content(self) -> object:
        return (
            self.session_identity,
            self.expected_causal_revision,
            self.checkpoint_identity,
            self.checkpoint_fingerprint,
            self.checkpoint_revision,
            self.persistence_evidence,
            self.required_prerequisites,
            self.satisfied_prerequisites,
            self.policy_version,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionResumeAssessment:
    eligible: bool
    diagnostics: tuple[CodingSessionControlDiagnostic, ...]
    lifecycle_fact: CodingSessionLifecycleFact | None

    @classmethod
    def assess(
        cls,
        request: CodingSessionResumeRequest,
        lifecycle: CodingSessionStateProjection,
        checkpoint: CodingSessionCheckpointAssessment,
        journal: CodingSessionJournalAssessment,
        ownership: CodingSessionOwnershipProjection | None,
        prior_resume_fingerprints: frozenset[CodingSessionFingerprint] = frozenset(),
    ) -> CodingSessionResumeAssessment:
        findings: set[CodingSessionControlDiagnostic] = set()
        if request.fingerprint in prior_resume_fingerprints:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.DUPLICATE_RESUME))
        if request.policy_version != CODING_SESSION_CONTROL_POLICY_VERSION:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.UNSUPPORTED_POLICY_VERSION))
        if request.session_identity != lifecycle.session_identity or request.session_identity != checkpoint.fact.session_identity:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.SESSION_MISMATCH))
        if request.expected_causal_revision != lifecycle.causal_revision:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.CAUSAL_REVISION_MISMATCH))
        if lifecycle.lifecycle is not CodingSessionLifecycleState.SUSPENDED:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.LIFECYCLE_INCOMPATIBLE))
        if checkpoint.state is not CodingSessionCheckpointDurabilityState.DURABLE_READY or not checkpoint.structurally_complete:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.CHECKPOINT_INELIGIBLE))
        if request.checkpoint_identity != checkpoint.fact.checkpoint_identity.value or request.checkpoint_fingerprint != checkpoint.fact.fingerprint or request.checkpoint_revision != checkpoint.fact.manifest.through_revision:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.CHECKPOINT_MISMATCH))
        if not journal.accepted:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.JOURNAL_INCOMPLETE))
        if request.persistence_evidence is None:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.PERSISTENCE_EVIDENCE_MISSING))
        if ownership is not None and ownership.state not in {CodingSessionCoordinationState.READ_OWNED, CodingSessionCoordinationState.WRITE_OWNED}:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.LEASE_INELIGIBLE))
        if lifecycle.repository_correspondence not in {CodingSessionRepositoryCorrespondenceState.UNBOUND, CodingSessionRepositoryCorrespondenceState.CORRESPONDING}:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.REPOSITORY_INELIGIBLE))
        if lifecycle.cancellation is not CodingSessionCancellationState.NOT_REQUESTED:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.CANCELLATION_PENDING))
        if lifecycle.recovery in {CodingSessionRecoveryState.REQUIRED, CodingSessionRecoveryState.PLANNED, CodingSessionRecoveryState.IN_PROGRESS, CodingSessionRecoveryState.PARTIALLY_RECOVERED, CodingSessionRecoveryState.FAILED, CodingSessionRecoveryState.MANUAL_INTERVENTION}:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.RECOVERY_REQUIRED))
        if not request.required_prerequisites <= request.satisfied_prerequisites:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.PREREQUISITE_MISSING))
        if findings:
            return cls(False, tuple(sorted(findings)), None)
        evidence = {request.checkpoint_fingerprint, request.persistence_evidence}
        evidence.update(request.satisfied_prerequisites)
        transition = CodingSessionTransitionAssessment.assess(
            CodingSessionTransitionRequest(
                session_identity=request.session_identity,
                dimension=CodingSessionStateDimension.LIFECYCLE,
                expected_previous_state=CodingSessionLifecycleState.SUSPENDED,
                next_state=CodingSessionLifecycleState.ACTIVE,
                reason=CodingSessionTransitionReason.ACTIVATION_CONFIRMED,
                expected_causal_revision=request.expected_causal_revision,
                evidence=tuple(item for item in evidence if item is not None),
                occurrence_metadata=request.occurrence_metadata,
            ),
            lifecycle,
        )
        return cls(transition.accepted, (), transition.fact)


class CodingSessionCancellationEvidenceKind(str, Enum):
    PROCESS_EXIT = "process-exit"
    WORKER_TERMINATION = "worker-termination"
    SANDBOX_CLEANUP = "sandbox-cleanup"


class CodingSessionCancellationAssessmentState(str, Enum):
    REQUESTED = "requested"
    ACKNOWLEDGED = "acknowledged"
    TERMINATION_UNVERIFIED = "termination-unverified"
    TERMINATED = "terminated"
    FAILED = "failed"


class CodingSessionCancellationRace(str, Enum):
    WORKER_COMPLETED_AFTER_REQUEST = "worker-completed-after-request"
    PROCESS_EXIT_BEFORE_ACKNOWLEDGEMENT = "process-exit-before-acknowledgement"
    ACKNOWLEDGEMENT_AFTER_TERMINATION = "acknowledgement-after-termination"
    PAUSE_CANCELLATION_CONCURRENT = "pause-cancellation-concurrent"
    LATE_FACT = "late-fact"


@dataclass(frozen=True, slots=True)
class CodingSessionCancellationRequest:
    request_identity: CodingSessionFactIdentity
    session_identity: CodingSessionIdentity
    actor: CodingSessionActorReference
    purpose: CodingSessionPurpose
    correlation: CodingSessionCorrelationReference
    cancellation_intent: CodingSessionIntentIdentity | None
    worker_execution_references: tuple[CodingSessionProducerReference, ...]
    policy_version: str
    causal_metadata: CodingSessionCausalMetadata

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class CodingSessionCancellationAcknowledgement:
    acknowledgement_identity: CodingSessionExternalReceiptIdentity
    request_identity: CodingSessionFactIdentity
    request_fingerprint: CodingSessionFingerprint
    session_identity: CodingSessionIdentity
    actor: CodingSessionActorReference
    purpose: CodingSessionPurpose
    correlation: CodingSessionCorrelationReference
    cancellation_intent: CodingSessionIntentIdentity | None
    producer_reference: CodingSessionProducerReference
    accepted: bool
    causal_metadata: CodingSessionCausalMetadata

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class CodingSessionCancellationEvidence:
    evidence_identity: CodingSessionExternalReceiptIdentity
    request_identity: CodingSessionFactIdentity
    request_fingerprint: CodingSessionFingerprint
    session_identity: CodingSessionIdentity
    actor: CodingSessionActorReference
    purpose: CodingSessionPurpose
    correlation: CodingSessionCorrelationReference
    kind: CodingSessionCancellationEvidenceKind
    producer_reference: CodingSessionProducerReference
    verified: bool
    causal_metadata: CodingSessionCausalMetadata

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


CodingSessionCancellationExternalFact: TypeAlias = (
    CodingSessionCancellationAcknowledgement | CodingSessionCancellationEvidence
)


@dataclass(frozen=True, slots=True)
class CodingSessionCancellationPolicy:
    required_evidence: frozenset[CodingSessionCancellationEvidenceKind]
    version: str = CODING_SESSION_CONTROL_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class CodingSessionCancellationAssessment:
    state: CodingSessionCancellationAssessmentState
    cancelled_outcome_eligible: bool
    diagnostics: tuple[CodingSessionControlDiagnostic, ...]
    races: frozenset[CodingSessionCancellationRace]

    @classmethod
    def assess(
        cls,
        requests: tuple[CodingSessionCancellationRequest, ...],
        acknowledgements: tuple[CodingSessionCancellationAcknowledgement, ...],
        evidence: tuple[CodingSessionCancellationEvidence, ...],
        lifecycle: CodingSessionStateProjection,
        policy: CodingSessionCancellationPolicy,
    ) -> CodingSessionCancellationAssessment:
        findings: set[CodingSessionControlDiagnostic] = set()
        races: set[CodingSessionCancellationRace] = set()
        if len(requests) != 1:
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.DUPLICATE_CANCELLATION_REQUEST))
        if not requests:
            return cls(CodingSessionCancellationAssessmentState.FAILED, False, tuple(sorted(findings)), frozenset())
        request = sorted(requests, key=lambda item: item.causal_metadata.revision.value)[0]
        all_facts: tuple[CodingSessionCancellationExternalFact, ...] = (
            *acknowledgements,
            *evidence,
        )
        revisions = [item.causal_metadata.revision.value for item in all_facts]
        if len(revisions) != len(set(revisions)):
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.DUPLICATE_CAUSAL_REVISION))
        for fact in all_facts:
            if fact.session_identity != request.session_identity or fact.request_identity != request.request_identity or fact.request_fingerprint != request.fingerprint:
                findings.add(_diagnostic(CodingSessionControlDiagnosticCode.EVIDENCE_MISMATCH))
            if fact.actor != request.actor or fact.purpose != request.purpose:
                findings.add(_diagnostic(CodingSessionControlDiagnosticCode.ACTOR_PURPOSE_MISMATCH))
            if fact.correlation != request.correlation:
                findings.add(_diagnostic(CodingSessionControlDiagnosticCode.CORRELATION_MISMATCH))
            if request.fingerprint not in {*fact.causal_metadata.lineage.parents, *fact.causal_metadata.lineage.references}:
                findings.add(_diagnostic(CodingSessionControlDiagnosticCode.LINEAGE_GAP))
        accepted_ack = any(item.accepted for item in acknowledgements)
        verified = {item.kind for item in evidence if item.verified}
        if any(not item.accepted for item in acknowledgements):
            state = CodingSessionCancellationAssessmentState.FAILED
        elif not acknowledgements and not evidence:
            state = CodingSessionCancellationAssessmentState.REQUESTED
        elif accepted_ack and policy.required_evidence <= verified:
            state = CodingSessionCancellationAssessmentState.TERMINATED
        elif accepted_ack and not evidence:
            state = CodingSessionCancellationAssessmentState.ACKNOWLEDGED
        else:
            state = CodingSessionCancellationAssessmentState.TERMINATION_UNVERIFIED
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.TERMINATION_INCOMPLETE))
        ack_revision = min((item.causal_metadata.revision.value for item in acknowledgements), default=10**9)
        process_revisions = [item.causal_metadata.revision.value for item in evidence if item.kind is CodingSessionCancellationEvidenceKind.PROCESS_EXIT]
        if process_revisions and min(process_revisions) < ack_revision:
            races.add(CodingSessionCancellationRace.PROCESS_EXIT_BEFORE_ACKNOWLEDGEMENT)
        if acknowledgements and evidence and ack_revision > min(item.causal_metadata.revision.value for item in evidence):
            races.add(CodingSessionCancellationRace.ACKNOWLEDGEMENT_AFTER_TERMINATION)
        if any(item.kind is CodingSessionCancellationEvidenceKind.WORKER_TERMINATION for item in evidence):
            races.add(CodingSessionCancellationRace.WORKER_COMPLETED_AFTER_REQUEST)
        if lifecycle.lifecycle is CodingSessionLifecycleState.SUSPENDED:
            races.add(CodingSessionCancellationRace.PAUSE_CANCELLATION_CONCURRENT)
        if lifecycle.lifecycle is CodingSessionLifecycleState.TERMINAL:
            races.add(CodingSessionCancellationRace.LATE_FACT)
            findings.add(_diagnostic(CodingSessionControlDiagnosticCode.LATE_FACT))
        eligible = state is CodingSessionCancellationAssessmentState.TERMINATED and not findings - {_diagnostic(CodingSessionControlDiagnosticCode.LATE_FACT)}
        return cls(state, eligible, tuple(sorted(findings)), frozenset(races))


def _diagnostic(code: CodingSessionControlDiagnosticCode) -> CodingSessionControlDiagnostic:
    return CodingSessionControlDiagnostic(code)
