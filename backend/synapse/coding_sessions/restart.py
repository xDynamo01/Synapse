"""Pure restart reconstruction and multidimensional reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .causal import CodingSessionCausalMetadata, CodingSessionCausalRevision, CodingSessionLineage
from .contracts import CodingSessionContract, CodingSessionRequestedCapability
from .identities import CodingSessionFactIdentity, CodingSessionFingerprint, CodingSessionIdentity
from .intents import (
    CodingSessionExternalReceipt,
    CodingSessionIntent,
    CodingSessionIntentDiagnosticCode,
    CodingSessionIntentReceiptProjection,
)
from .journal import CodingSessionCheckpointAssessment, CodingSessionJournalAssessment
from .leases import (
    CodingSessionLeaseFact,
    CodingSessionLeasePolicy,
    CodingSessionOwnershipProjection,
)
from .lifecycle import (
    CodingSessionCancellationState,
    CodingSessionLifecycleFact,
    CodingSessionLifecycleState,
    CodingSessionRecoveryState,
    CodingSessionStateProjection,
)

CODING_SESSION_RESTART_POLICY_VERSION = "coding-session-restart-policy-v1"


class CodingSessionReconciliationDimension(str, Enum):
    CONTRACT = "contract"
    JOURNAL = "journal"
    CHECKPOINT = "checkpoint"
    LIFECYCLE = "lifecycle"
    OWNERSHIP = "ownership"
    REPOSITORY = "repository"
    WORKER = "worker"
    EXECUTION = "execution"
    AUTHORIZATION = "authorization"
    CANCELLATION = "cancellation"
    RECOVERY = "recovery"
    EVALUATION = "evaluation"
    ARTIFACT = "artifact"
    DEPLOYMENT = "deployment"


class CodingSessionReconciliationEvidenceState(str, Enum):
    RECONSTRUCTED = "reconstructed"
    REVALIDATED = "revalidated"
    UNKNOWN = "unknown"
    STALE = "stale"
    CONTRADICTORY = "contradictory"
    MISSING = "missing"
    ORPHANED = "orphaned"


class CodingSessionReconciliationOutcome(str, Enum):
    SAFE_TO_RESUME = "safe-to-resume"
    RECONCILIATION_INCOMPLETE = "reconciliation-incomplete"
    RECOVERY_REQUIRED = "recovery-required"
    MANUAL_INTERVENTION = "manual-intervention"


class CodingSessionRestartDiagnosticCode(str, Enum):
    SESSION_IDENTITY_MISMATCH = "session-identity-mismatch"
    CAUSAL_REVISION_MISMATCH = "causal-revision-mismatch"
    DUPLICATE_RESTART = "duplicate-restart"
    DUPLICATE_RESUME = "duplicate-resume"
    JOURNAL_INCOMPLETE = "journal-incomplete"
    CHECKPOINT_MISSING = "checkpoint-missing"
    CHECKPOINT_LINEAGE_GAP = "checkpoint-lineage-gap"
    CHECKPOINT_NOT_PERSISTED = "checkpoint-not-persisted"
    CONTRADICTORY_RECEIPTS = "contradictory-receipts"
    LATE_RESULT = "late-result"
    STALE_LEASE = "stale-lease"
    REPOSITORY_UNKNOWN_OR_STALE = "repository-unknown-or-stale"
    ORPHAN_WORKER = "orphan-worker"
    EXECUTION_UNKNOWN = "execution-unknown"
    CANCELLATION_PENDING = "cancellation-pending"
    RECOVERY_REQUIRED = "recovery-required"
    MISSING_ARTIFACT_REFERENCE = "missing-artifact-reference"
    EXTERNAL_REVALIDATION_REQUIRED = "external-revalidation-required"
    TERMINAL_SESSION = "terminal-session"
    MANUAL_INTERVENTION_REQUIRED = "manual-intervention-required"
    UNSUPPORTED_POLICY_VERSION = "unsupported-policy-version"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionRestartDiagnostic:
    code: CodingSessionRestartDiagnosticCode
    subject: str = "restart-reconciliation"


@dataclass(frozen=True, slots=True)
class CodingSessionRestartFact:
    fact_identity: CodingSessionFactIdentity
    session_identity: CodingSessionIdentity
    dimension: CodingSessionReconciliationDimension
    state: CodingSessionReconciliationEvidenceState
    evidence_fingerprint: CodingSessionFingerprint | None
    causal_metadata: CodingSessionCausalMetadata

    def semantic_content(self) -> object:
        return (
            self.fact_identity,
            self.session_identity,
            self.dimension,
            self.state,
            self.evidence_fingerprint,
            self.causal_metadata,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionRestartRequest:
    restart_identity: CodingSessionFactIdentity
    session_identity: CodingSessionIdentity
    expected_causal_revision: int
    contract: CodingSessionContract
    journal: CodingSessionJournalAssessment
    checkpoint: CodingSessionCheckpointAssessment | None
    checkpoint_persistence_evidence: CodingSessionFingerprint | None
    lifecycle_facts: tuple[CodingSessionLifecycleFact, ...]
    lease_facts: tuple[CodingSessionLeaseFact, ...]
    intents: tuple[CodingSessionIntent, ...]
    receipts: tuple[CodingSessionExternalReceipt, ...]
    observation_time: int
    occurrence_metadata: tuple[tuple[str, str], ...] = ()
    policy_version: str = CODING_SESSION_RESTART_POLICY_VERSION

    def semantic_content(self) -> object:
        return (
            self.restart_identity,
            self.session_identity,
            self.expected_causal_revision,
            self.contract.fingerprint,
            self.journal.stream.fingerprint,
            self.checkpoint.fact.fingerprint if self.checkpoint else None,
            self.checkpoint_persistence_evidence,
            tuple(item.fingerprint for item in self.lifecycle_facts),
            tuple(item.fingerprint for item in self.lease_facts),
            tuple(item.fingerprint for item in self.intents),
            tuple(item.fingerprint for item in self.receipts),
            self.observation_time,
            self.policy_version,
        )

    @property
    def idempotency_fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionRestartAssessment:
    reconstructed: bool
    lifecycle: CodingSessionStateProjection
    ownership: CodingSessionOwnershipProjection
    intent_receipts: CodingSessionIntentReceiptProjection
    repository_bound: bool
    declared_capabilities: frozenset[CodingSessionRequestedCapability]
    facts: tuple[CodingSessionRestartFact, ...]
    diagnostics: tuple[CodingSessionRestartDiagnostic, ...]
    idempotency_fingerprint: CodingSessionFingerprint

    @classmethod
    def assess(
        cls,
        request: CodingSessionRestartRequest,
        *,
        prior_restart_fingerprints: frozenset[CodingSessionFingerprint] = frozenset(),
    ) -> CodingSessionRestartAssessment:
        diagnostics: set[CodingSessionRestartDiagnostic] = set()
        if request.idempotency_fingerprint in prior_restart_fingerprints:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.DUPLICATE_RESTART))
        if request.policy_version != CODING_SESSION_RESTART_POLICY_VERSION:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.UNSUPPORTED_POLICY_VERSION))
        if (
            request.session_identity != request.contract.session_identity
            or request.session_identity != request.journal.stream.session_identity
        ):
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.SESSION_IDENTITY_MISMATCH))
        if request.expected_causal_revision != len(request.journal.stream.entries):
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.CAUSAL_REVISION_MISMATCH))
        if not request.journal.accepted:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.JOURNAL_INCOMPLETE))
        if request.checkpoint is None:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.CHECKPOINT_MISSING))
        elif not request.checkpoint.structurally_complete:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.CHECKPOINT_LINEAGE_GAP))
        if request.checkpoint_persistence_evidence is None:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.CHECKPOINT_NOT_PERSISTED))
        lifecycle = CodingSessionStateProjection.replay(
            request.session_identity, request.lifecycle_facts
        )
        ownership = CodingSessionOwnershipProjection.project(
            request.lease_facts,
            observation_time=request.observation_time,
            policy=CodingSessionLeasePolicy(),
        )
        intent_receipts = CodingSessionIntentReceiptProjection.project(
            request.session_identity,
            request.intents,
            request.receipts,
            lifecycle,
        )
        if not lifecycle.valid:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.JOURNAL_INCOMPLETE))
        if any(
            item.code is CodingSessionIntentDiagnosticCode.LATE_RECEIPT
            for item in intent_receipts.diagnostics
        ):
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.LATE_RESULT))
        if _receipts_contradict(request.receipts):
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.CONTRADICTORY_RECEIPTS))
        facts = _restart_facts(request, lifecycle, ownership, intent_receipts)
        return cls(
            reconstructed=not diagnostics,
            lifecycle=lifecycle,
            ownership=ownership,
            intent_receipts=intent_receipts,
            repository_bound=request.contract.binding.repository is not None,
            declared_capabilities=frozenset(
                item.code
                for item in request.contract.requested_capabilities
                if isinstance(item.code, CodingSessionRequestedCapability)
            ),
            facts=facts,
            diagnostics=tuple(sorted(diagnostics)),
            idempotency_fingerprint=request.idempotency_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class CodingSessionReconciliationRequest:
    session_identity: CodingSessionIdentity
    expected_causal_revision: int
    restart: CodingSessionRestartAssessment
    revalidation_facts: tuple[CodingSessionRestartFact, ...]
    prior_resume_fingerprints: frozenset[CodingSessionFingerprint] = frozenset()
    resume_fingerprint: CodingSessionFingerprint | None = None
    policy_version: str = CODING_SESSION_RESTART_POLICY_VERSION

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class CodingSessionReconciliationFact:
    session_identity: CodingSessionIdentity
    dimension: CodingSessionReconciliationDimension
    state: CodingSessionReconciliationEvidenceState
    source_fingerprint: CodingSessionFingerprint | None


@dataclass(frozen=True, slots=True)
class CodingSessionResumeEligibilityResult:
    eligible: bool
    outcome: CodingSessionReconciliationOutcome
    unknown_dimensions: frozenset[CodingSessionReconciliationDimension]
    diagnostics: tuple[CodingSessionRestartDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CodingSessionReconciliationAssessment:
    facts: tuple[CodingSessionReconciliationFact, ...]
    resume_eligibility: CodingSessionResumeEligibilityResult
    fingerprint: CodingSessionFingerprint

    @classmethod
    def assess(
        cls, request: CodingSessionReconciliationRequest
    ) -> CodingSessionReconciliationAssessment:
        diagnostics: set[CodingSessionRestartDiagnostic] = set(request.restart.diagnostics)
        if request.policy_version != CODING_SESSION_RESTART_POLICY_VERSION:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.UNSUPPORTED_POLICY_VERSION))
        if request.session_identity != request.restart.lifecycle.session_identity:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.SESSION_IDENTITY_MISMATCH))
        if request.expected_causal_revision != request.restart.lifecycle.causal_revision:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.CAUSAL_REVISION_MISMATCH))
        if request.resume_fingerprint is not None and request.resume_fingerprint in request.prior_resume_fingerprints:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.DUPLICATE_RESUME))
        revisions = [fact.causal_metadata.revision.value for fact in request.revalidation_facts]
        if len(revisions) != len(set(revisions)):
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.CAUSAL_REVISION_MISMATCH))
        if any(
            fact.session_identity != request.session_identity
            or fact.causal_metadata.semantic_identity != fact.fact_identity
            for fact in request.revalidation_facts
        ):
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.SESSION_IDENTITY_MISMATCH))
        states = {fact.dimension: fact.state for fact in request.revalidation_facts}
        required_external = {
            CodingSessionReconciliationDimension.WORKER,
            CodingSessionReconciliationDimension.EXECUTION,
        }
        if request.restart.repository_bound:
            required_external.add(CodingSessionReconciliationDimension.REPOSITORY)
            required_external.add(CodingSessionReconciliationDimension.OWNERSHIP)
        if CodingSessionRequestedCapability.APPROVAL in request.restart.declared_capabilities:
            required_external.add(CodingSessionReconciliationDimension.AUTHORIZATION)
        unknown = frozenset(
            dimension
            for dimension in required_external
            if states.get(dimension) is not CodingSessionReconciliationEvidenceState.REVALIDATED
        )
        if unknown:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.EXTERNAL_REVALIDATION_REQUIRED))
        lifecycle = request.restart.lifecycle
        if lifecycle.lifecycle is not CodingSessionLifecycleState.SUSPENDED:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.EXTERNAL_REVALIDATION_REQUIRED))
        if lifecycle.lifecycle is CodingSessionLifecycleState.TERMINAL:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.TERMINAL_SESSION))
        if lifecycle.cancellation is not CodingSessionCancellationState.NOT_REQUESTED:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.CANCELLATION_PENDING))
        if lifecycle.recovery in {
            CodingSessionRecoveryState.REQUIRED,
            CodingSessionRecoveryState.PLANNED,
            CodingSessionRecoveryState.IN_PROGRESS,
            CodingSessionRecoveryState.PARTIALLY_RECOVERED,
            CodingSessionRecoveryState.FAILED,
        }:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.RECOVERY_REQUIRED))
        if lifecycle.recovery is CodingSessionRecoveryState.MANUAL_INTERVENTION or any(
            state in {
                CodingSessionReconciliationEvidenceState.CONTRADICTORY,
                CodingSessionReconciliationEvidenceState.ORPHANED,
            }
            for state in states.values()
        ):
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.MANUAL_INTERVENTION_REQUIRED))
        if states.get(CodingSessionReconciliationDimension.OWNERSHIP) is CodingSessionReconciliationEvidenceState.STALE:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.STALE_LEASE))
        if states.get(CodingSessionReconciliationDimension.REPOSITORY) in {
            CodingSessionReconciliationEvidenceState.UNKNOWN,
            CodingSessionReconciliationEvidenceState.STALE,
            CodingSessionReconciliationEvidenceState.MISSING,
        }:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.REPOSITORY_UNKNOWN_OR_STALE))
        if states.get(CodingSessionReconciliationDimension.WORKER) is CodingSessionReconciliationEvidenceState.ORPHANED:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.ORPHAN_WORKER))
        if states.get(CodingSessionReconciliationDimension.EXECUTION) is CodingSessionReconciliationEvidenceState.UNKNOWN:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.EXECUTION_UNKNOWN))
        if states.get(CodingSessionReconciliationDimension.ARTIFACT) is CodingSessionReconciliationEvidenceState.MISSING:
            diagnostics.add(_diagnostic(CodingSessionRestartDiagnosticCode.MISSING_ARTIFACT_REFERENCE))
        codes = {item.code for item in diagnostics}
        if CodingSessionRestartDiagnosticCode.MANUAL_INTERVENTION_REQUIRED in codes:
            outcome = CodingSessionReconciliationOutcome.MANUAL_INTERVENTION
        elif CodingSessionRestartDiagnosticCode.RECOVERY_REQUIRED in codes:
            outcome = CodingSessionReconciliationOutcome.RECOVERY_REQUIRED
        elif diagnostics:
            outcome = CodingSessionReconciliationOutcome.RECONCILIATION_INCOMPLETE
        else:
            outcome = CodingSessionReconciliationOutcome.SAFE_TO_RESUME
        facts = tuple(
            sorted(
                (
                    CodingSessionReconciliationFact(
                        request.session_identity,
                        dimension,
                        state,
                        next(
                            (
                                fact.evidence_fingerprint
                                for fact in request.revalidation_facts
                                if fact.dimension is dimension
                            ),
                            None,
                        ),
                    )
                    for dimension, state in states.items()
                ),
                key=lambda item: item.dimension.value,
            )
        )
        eligibility = CodingSessionResumeEligibilityResult(
            eligible=outcome is CodingSessionReconciliationOutcome.SAFE_TO_RESUME,
            outcome=outcome,
            unknown_dimensions=unknown,
            diagnostics=tuple(sorted(diagnostics)),
        )
        fingerprint = CodingSessionFingerprint.from_content((facts, eligibility))
        return cls(facts, eligibility, fingerprint)


def _restart_facts(
    request: CodingSessionRestartRequest,
    lifecycle: CodingSessionStateProjection,
    ownership: CodingSessionOwnershipProjection,
    intents: CodingSessionIntentReceiptProjection,
) -> tuple[CodingSessionRestartFact, ...]:
    known = {
        CodingSessionReconciliationDimension.CONTRACT: request.contract.fingerprint,
        CodingSessionReconciliationDimension.JOURNAL: request.journal.stream.fingerprint,
        CodingSessionReconciliationDimension.LIFECYCLE: lifecycle.fingerprint,
        CodingSessionReconciliationDimension.OWNERSHIP: ownership.evidence_fingerprint,
    }
    if request.checkpoint is not None:
        known[CodingSessionReconciliationDimension.CHECKPOINT] = request.checkpoint.fact.fingerprint
    known[CodingSessionReconciliationDimension.ARTIFACT] = intents.fingerprint
    external_unknown = {
        CodingSessionReconciliationDimension.REPOSITORY,
        CodingSessionReconciliationDimension.WORKER,
        CodingSessionReconciliationDimension.EXECUTION,
        CodingSessionReconciliationDimension.AUTHORIZATION,
        CodingSessionReconciliationDimension.EVALUATION,
        CodingSessionReconciliationDimension.DEPLOYMENT,
    }
    results: list[CodingSessionRestartFact] = []
    for offset, dimension in enumerate(
        sorted((*known.keys(), *external_unknown), key=lambda item: item.value), start=1
    ):
        state = (
            CodingSessionReconciliationEvidenceState.RECONSTRUCTED
            if dimension in known
            else CodingSessionReconciliationEvidenceState.UNKNOWN
        )
        identity = CodingSessionFactIdentity.from_stable_key(
            f"{request.restart_identity.value}:{dimension.value}"
        )
        results.append(
            CodingSessionRestartFact(
                identity,
                request.session_identity,
                dimension,
                state,
                known.get(dimension),
                CodingSessionCausalMetadata(
                    identity,
                    CodingSessionCausalRevision(offset),
                    CodingSessionLineage(references=((known[dimension],) if dimension in known else ())),
                    request.occurrence_metadata,
                ),
            )
        )
    return tuple(results)


def _receipts_contradict(receipts: tuple[CodingSessionExternalReceipt, ...]) -> bool:
    return any(
        len({item.outcome for item in receipts if item.intent_identity == intent_identity}) > 1
        for intent_identity in {item.intent_identity for item in receipts}
    )


def _diagnostic(code: CodingSessionRestartDiagnosticCode) -> CodingSessionRestartDiagnostic:
    return CodingSessionRestartDiagnostic(code)
