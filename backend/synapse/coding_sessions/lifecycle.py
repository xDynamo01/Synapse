"""Pure multidimensional lifecycle facts, transitions, and deterministic replay."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import TypeAlias

from .causal import CodingSessionCausalMetadata, CodingSessionCausalRevision, CodingSessionLineage
from .contracts import CodingSessionContract, CodingSessionContractAssessment
from .identities import CodingSessionFactIdentity, CodingSessionFingerprint, CodingSessionIdentity

CODING_SESSION_LIFECYCLE_POLICY_VERSION = "coding-session-lifecycle-policy-v1"


class CodingSessionStateDimension(str, Enum):
    LIFECYCLE = "lifecycle"
    TERMINAL_OUTCOME = "terminal-outcome"
    COORDINATION = "coordination"
    REPOSITORY_CORRESPONDENCE = "repository-correspondence"
    WORKER_BINDING = "worker-binding"
    EXECUTION_BINDING = "execution-binding"
    CHECKPOINT = "checkpoint"
    CANCELLATION = "cancellation"
    RECOVERY = "recovery"
    EVALUATION = "evaluation"
    DEPLOYMENT_CANDIDATE = "deployment-candidate"


class CodingSessionLifecycleState(str, Enum):
    UNKNOWN = "unknown"
    PLANNED = "planned"
    PREPARED = "prepared"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINAL = "terminal"


class CodingSessionTerminalOutcome(str, Enum):
    UNKNOWN = "unknown"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"
    MANUAL_INTERVENTION = "manual-intervention"


class CodingSessionCoordinationState(str, Enum):
    UNKNOWN = "unknown"
    UNOWNED = "unowned"
    READ_OWNED = "read-owned"
    WRITE_OWNED = "write-owned"
    CONFLICTED = "conflicted"
    STALE = "stale"
    REVOKED = "revoked"


class CodingSessionRepositoryCorrespondenceState(str, Enum):
    UNBOUND = "unbound"
    CORRESPONDING = "corresponding"
    STALE = "stale"
    MISMATCHED = "mismatched"
    UNVERIFIABLE = "unverifiable"


class CodingSessionWorkerBindingState(str, Enum):
    UNBOUND = "unbound"
    ASSIGNED = "assigned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    LOST = "lost"
    UNKNOWN = "unknown"


class CodingSessionExecutionBindingState(str, Enum):
    UNBOUND = "unbound"
    PLANNED = "planned"
    ADMITTED = "admitted"
    RUNNING = "running"
    EXITED = "exited"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


class CodingSessionCheckpointState(str, Enum):
    ABSENT = "absent"
    REQUESTED = "requested"
    AVAILABLE = "available"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class CodingSessionCancellationState(str, Enum):
    NOT_REQUESTED = "not-requested"
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CodingSessionRecoveryState(str, Enum):
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not-required"
    REQUIRED = "required"
    PLANNED = "planned"
    IN_PROGRESS = "in-progress"
    PARTIALLY_RECOVERED = "partially-recovered"
    RECOVERED = "recovered"
    FAILED = "failed"
    MANUAL_INTERVENTION = "manual-intervention"


class CodingSessionEvaluationState(str, Enum):
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not-required"
    REQUIRED = "required"
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class CodingSessionDeploymentCandidateState(str, Enum):
    ABSENT = "absent"
    REQUIRED = "required"
    PRODUCED = "produced"
    HANDED_OFF = "handed-off"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


CodingSessionSemanticState: TypeAlias = (
    CodingSessionLifecycleState
    | CodingSessionTerminalOutcome
    | CodingSessionCoordinationState
    | CodingSessionRepositoryCorrespondenceState
    | CodingSessionWorkerBindingState
    | CodingSessionExecutionBindingState
    | CodingSessionCheckpointState
    | CodingSessionCancellationState
    | CodingSessionRecoveryState
    | CodingSessionEvaluationState
    | CodingSessionDeploymentCandidateState
)


class CodingSessionTransitionReason(str, Enum):
    SESSION_PLANNED = "session-planned"
    CONTRACT_ACCEPTED = "contract-accepted"
    ACTIVATION_CONFIRMED = "activation-confirmed"
    SUSPENSION_CONFIRMED = "suspension-confirmed"
    TERMINATION_CONFIRMED = "termination-confirmed"
    COORDINATION_OBSERVED = "coordination-observed"
    REPOSITORY_OBSERVED = "repository-observed"
    MUTATION_APPLIED = "mutation-applied"
    WORKER_ASSIGNED = "worker-assigned"
    WORKER_SUCCEEDED = "worker-succeeded"
    PROCESS_EXITED = "process-exited"
    EXECUTION_OBSERVED = "execution-observed"
    CHECKPOINT_OBSERVED = "checkpoint-observed"
    CANCELLATION_REQUESTED = "cancellation-requested"
    CANCELLATION_CONFIRMED = "cancellation-confirmed"
    RECOVERY_REQUIRED = "recovery-required"
    RECOVERY_STARTED = "recovery-started"
    RECOVERY_OBSERVED = "recovery-observed"
    EVALUATION_OBSERVED = "evaluation-observed"
    EVALUATION_ACCEPTED = "evaluation-accepted"
    DEPLOYMENT_CANDIDATE_PRODUCED = "deployment-candidate-produced"
    DEPLOYMENT_HANDOFF_OBSERVED = "deployment-handoff-observed"
    EXTERNAL_FACT_OBSERVED = "external-fact-observed"
    RESTART_REPLAYED = "restart-replayed"


class CodingSessionTransitionDiagnosticCode(str, Enum):
    SESSION_IDENTITY_MISMATCH = "session-identity-mismatch"
    DIMENSION_STATE_MISMATCH = "dimension-state-mismatch"
    PREVIOUS_STATE_MISMATCH = "previous-state-mismatch"
    INVALID_TRANSITION = "invalid-transition"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"
    CONTRACT_NOT_COMPLETE = "contract-not-complete"
    TERMINAL_SESSION_REOPEN = "terminal-session-reopen"
    COMPLETION_ASSESSMENT_UNAVAILABLE = "completion-assessment-unavailable"
    UNSUPPORTED_POLICY_VERSION = "unsupported-policy-version"
    CAUSAL_REVISION_GAP = "causal-revision-gap"
    DUPLICATE_CAUSAL_REVISION = "duplicate-causal-revision"
    LINEAGE_GAP = "lineage-gap"
    RESTART_CANNOT_TRANSITION = "restart-cannot-transition"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionTransitionDiagnostic:
    code: CodingSessionTransitionDiagnosticCode
    subject: str


@dataclass(frozen=True, slots=True)
class CodingSessionLifecycleFact:
    fact_identity: CodingSessionFactIdentity
    session_identity: CodingSessionIdentity
    dimension: CodingSessionStateDimension
    previous_state: CodingSessionSemanticState
    next_state: CodingSessionSemanticState
    reason: CodingSessionTransitionReason
    policy_version: str
    causal_metadata: CodingSessionCausalMetadata

    def semantic_content(self) -> object:
        return (
            self.fact_identity,
            self.session_identity,
            self.dimension,
            self.previous_state,
            self.next_state,
            self.reason,
            self.policy_version,
            self.causal_metadata,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionTransitionRequest:
    session_identity: CodingSessionIdentity
    dimension: CodingSessionStateDimension
    expected_previous_state: CodingSessionSemanticState
    next_state: CodingSessionSemanticState
    reason: CodingSessionTransitionReason
    expected_causal_revision: int
    evidence: tuple[CodingSessionFingerprint, ...] = ()
    occurrence_metadata: tuple[tuple[str, str], ...] = ()
    policy_version: str = CODING_SESSION_LIFECYCLE_POLICY_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence",
            tuple(sorted(set(self.evidence), key=lambda item: item.value)),
        )
        object.__setattr__(
            self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata)))
        )

    def semantic_content(self) -> object:
        return (
            self.session_identity,
            self.dimension,
            self.expected_previous_state,
            self.next_state,
            self.reason,
            self.expected_causal_revision,
            self.evidence,
            self.policy_version,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionStateProjection:
    session_identity: CodingSessionIdentity
    lifecycle: CodingSessionLifecycleState = CodingSessionLifecycleState.UNKNOWN
    terminal_outcome: CodingSessionTerminalOutcome = CodingSessionTerminalOutcome.UNKNOWN
    coordination: CodingSessionCoordinationState = CodingSessionCoordinationState.UNKNOWN
    repository_correspondence: CodingSessionRepositoryCorrespondenceState = (
        CodingSessionRepositoryCorrespondenceState.UNBOUND
    )
    worker_binding: CodingSessionWorkerBindingState = CodingSessionWorkerBindingState.UNBOUND
    execution_binding: CodingSessionExecutionBindingState = (
        CodingSessionExecutionBindingState.UNBOUND
    )
    checkpoint: CodingSessionCheckpointState = CodingSessionCheckpointState.ABSENT
    cancellation: CodingSessionCancellationState = (
        CodingSessionCancellationState.NOT_REQUESTED
    )
    recovery: CodingSessionRecoveryState = CodingSessionRecoveryState.UNKNOWN
    evaluation: CodingSessionEvaluationState = CodingSessionEvaluationState.UNKNOWN
    deployment_candidate: CodingSessionDeploymentCandidateState = (
        CodingSessionDeploymentCandidateState.ABSENT
    )
    causal_revision: int = 0
    last_fact_fingerprint: CodingSessionFingerprint | None = None
    valid: bool = True
    diagnostics: tuple[CodingSessionTransitionDiagnostic, ...] = ()

    @classmethod
    def replay(
        cls,
        session_identity: CodingSessionIdentity,
        facts: tuple[CodingSessionLifecycleFact, ...],
    ) -> CodingSessionStateProjection:
        projection = cls(session_identity=session_identity)
        revisions = [fact.causal_metadata.revision.value for fact in facts]
        duplicate_revisions = {revision for revision in revisions if revisions.count(revision) > 1}
        if duplicate_revisions:
            return replace(
                projection,
                valid=False,
                diagnostics=(
                    _diagnostic(
                        CodingSessionTransitionDiagnosticCode.DUPLICATE_CAUSAL_REVISION
                    ),
                ),
            )
        for fact in sorted(facts, key=lambda item: item.causal_metadata.revision.value):
            diagnostics = _fact_diagnostics(projection, fact)
            if diagnostics:
                return replace(projection, valid=False, diagnostics=diagnostics)
            projection = _apply_fact(projection, fact)
        return projection

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(
            (
                self.session_identity,
                self.lifecycle,
                self.terminal_outcome,
                self.coordination,
                self.repository_correspondence,
                self.worker_binding,
                self.execution_binding,
                self.checkpoint,
                self.cancellation,
                self.recovery,
                self.evaluation,
                self.deployment_candidate,
                self.causal_revision,
                self.last_fact_fingerprint,
                self.valid,
                self.diagnostics,
            )
        )


@dataclass(frozen=True, slots=True)
class CodingSessionTransitionAssessment:
    accepted: bool
    request_fingerprint: CodingSessionFingerprint
    diagnostics: tuple[CodingSessionTransitionDiagnostic, ...]
    fact: CodingSessionLifecycleFact | None = None

    @classmethod
    def assess(
        cls,
        request: CodingSessionTransitionRequest,
        projection: CodingSessionStateProjection,
        *,
        contract: CodingSessionContract | None = None,
        contract_assessment: CodingSessionContractAssessment | None = None,
    ) -> CodingSessionTransitionAssessment:
        diagnostics = _request_diagnostics(
            request, projection, contract, contract_assessment
        )
        if diagnostics:
            return cls(False, request.fingerprint, diagnostics)
        revision = request.expected_causal_revision + 1
        contract_reference = (
            contract.fingerprint
            if request.next_state is CodingSessionLifecycleState.PREPARED and contract is not None
            else None
        )
        fact_key = CodingSessionFingerprint.from_content(
            (request.fingerprint, contract_reference)
        )
        fact_identity = CodingSessionFactIdentity.from_stable_key(fact_key.value)
        parents = (
            (projection.last_fact_fingerprint,) if projection.last_fact_fingerprint else ()
        )
        references = set(request.evidence)
        if contract_reference is not None:
            references.add(contract_reference)
        fact = CodingSessionLifecycleFact(
            fact_identity=fact_identity,
            session_identity=request.session_identity,
            dimension=request.dimension,
            previous_state=request.expected_previous_state,
            next_state=request.next_state,
            reason=request.reason,
            policy_version=request.policy_version,
            causal_metadata=CodingSessionCausalMetadata(
                semantic_identity=fact_identity,
                revision=CodingSessionCausalRevision(revision),
                lineage=CodingSessionLineage(
                    parents=parents,
                    references=tuple(sorted(references, key=lambda item: item.value)),
                ),
                occurrence_metadata=request.occurrence_metadata,
            ),
        )
        return cls(True, request.fingerprint, (), fact)


_STATE_TYPES: dict[CodingSessionStateDimension, type[Enum]] = {
    CodingSessionStateDimension.LIFECYCLE: CodingSessionLifecycleState,
    CodingSessionStateDimension.TERMINAL_OUTCOME: CodingSessionTerminalOutcome,
    CodingSessionStateDimension.COORDINATION: CodingSessionCoordinationState,
    CodingSessionStateDimension.REPOSITORY_CORRESPONDENCE: (
        CodingSessionRepositoryCorrespondenceState
    ),
    CodingSessionStateDimension.WORKER_BINDING: CodingSessionWorkerBindingState,
    CodingSessionStateDimension.EXECUTION_BINDING: CodingSessionExecutionBindingState,
    CodingSessionStateDimension.CHECKPOINT: CodingSessionCheckpointState,
    CodingSessionStateDimension.CANCELLATION: CodingSessionCancellationState,
    CodingSessionStateDimension.RECOVERY: CodingSessionRecoveryState,
    CodingSessionStateDimension.EVALUATION: CodingSessionEvaluationState,
    CodingSessionStateDimension.DEPLOYMENT_CANDIDATE: CodingSessionDeploymentCandidateState,
}

_FIELD_NAMES = {
    CodingSessionStateDimension.LIFECYCLE: "lifecycle",
    CodingSessionStateDimension.TERMINAL_OUTCOME: "terminal_outcome",
    CodingSessionStateDimension.COORDINATION: "coordination",
    CodingSessionStateDimension.REPOSITORY_CORRESPONDENCE: "repository_correspondence",
    CodingSessionStateDimension.WORKER_BINDING: "worker_binding",
    CodingSessionStateDimension.EXECUTION_BINDING: "execution_binding",
    CodingSessionStateDimension.CHECKPOINT: "checkpoint",
    CodingSessionStateDimension.CANCELLATION: "cancellation",
    CodingSessionStateDimension.RECOVERY: "recovery",
    CodingSessionStateDimension.EVALUATION: "evaluation",
    CodingSessionStateDimension.DEPLOYMENT_CANDIDATE: "deployment_candidate",
}

_ALLOWED: dict[CodingSessionStateDimension, set[tuple[Enum, Enum]]] = {
    CodingSessionStateDimension.LIFECYCLE: {
        (CodingSessionLifecycleState.UNKNOWN, CodingSessionLifecycleState.PLANNED),
        (CodingSessionLifecycleState.PLANNED, CodingSessionLifecycleState.PREPARED),
        (CodingSessionLifecycleState.PREPARED, CodingSessionLifecycleState.ACTIVE),
        (CodingSessionLifecycleState.ACTIVE, CodingSessionLifecycleState.SUSPENDED),
        (CodingSessionLifecycleState.SUSPENDED, CodingSessionLifecycleState.ACTIVE),
        (CodingSessionLifecycleState.PLANNED, CodingSessionLifecycleState.TERMINAL),
        (CodingSessionLifecycleState.PREPARED, CodingSessionLifecycleState.TERMINAL),
        (CodingSessionLifecycleState.ACTIVE, CodingSessionLifecycleState.TERMINAL),
        (CodingSessionLifecycleState.SUSPENDED, CodingSessionLifecycleState.TERMINAL),
    },
    CodingSessionStateDimension.TERMINAL_OUTCOME: {
        (CodingSessionTerminalOutcome.UNKNOWN, CodingSessionTerminalOutcome.FAILED),
        (CodingSessionTerminalOutcome.UNKNOWN, CodingSessionTerminalOutcome.CANCELLED),
        (CodingSessionTerminalOutcome.UNKNOWN, CodingSessionTerminalOutcome.ABANDONED),
        (
            CodingSessionTerminalOutcome.UNKNOWN,
            CodingSessionTerminalOutcome.MANUAL_INTERVENTION,
        ),
    },
    CodingSessionStateDimension.COORDINATION: {
        (source, target)
        for source in CodingSessionCoordinationState
        for target in CodingSessionCoordinationState
        if source != target
    },
    CodingSessionStateDimension.REPOSITORY_CORRESPONDENCE: {
        (source, target)
        for source in CodingSessionRepositoryCorrespondenceState
        for target in CodingSessionRepositoryCorrespondenceState
        if source != target
    },
    CodingSessionStateDimension.WORKER_BINDING: {
        (CodingSessionWorkerBindingState.UNBOUND, CodingSessionWorkerBindingState.ASSIGNED),
        (CodingSessionWorkerBindingState.ASSIGNED, CodingSessionWorkerBindingState.RUNNING),
        (CodingSessionWorkerBindingState.RUNNING, CodingSessionWorkerBindingState.SUCCEEDED),
        (CodingSessionWorkerBindingState.RUNNING, CodingSessionWorkerBindingState.FAILED),
        (CodingSessionWorkerBindingState.RUNNING, CodingSessionWorkerBindingState.LOST),
    },
    CodingSessionStateDimension.EXECUTION_BINDING: {
        (CodingSessionExecutionBindingState.UNBOUND, CodingSessionExecutionBindingState.PLANNED),
        (CodingSessionExecutionBindingState.PLANNED, CodingSessionExecutionBindingState.ADMITTED),
        (CodingSessionExecutionBindingState.ADMITTED, CodingSessionExecutionBindingState.RUNNING),
        (CodingSessionExecutionBindingState.RUNNING, CodingSessionExecutionBindingState.EXITED),
        (CodingSessionExecutionBindingState.RUNNING, CodingSessionExecutionBindingState.SUCCEEDED),
        (CodingSessionExecutionBindingState.RUNNING, CodingSessionExecutionBindingState.FAILED),
        (
            CodingSessionExecutionBindingState.RUNNING,
            CodingSessionExecutionBindingState.INTERRUPTED,
        ),
    },
    CodingSessionStateDimension.CHECKPOINT: {
        (CodingSessionCheckpointState.ABSENT, CodingSessionCheckpointState.REQUESTED),
        (CodingSessionCheckpointState.REQUESTED, CodingSessionCheckpointState.AVAILABLE),
        (CodingSessionCheckpointState.REQUESTED, CodingSessionCheckpointState.INVALID),
        (CodingSessionCheckpointState.AVAILABLE, CodingSessionCheckpointState.INVALID),
    },
    CodingSessionStateDimension.CANCELLATION: {
        (CodingSessionCancellationState.NOT_REQUESTED, CodingSessionCancellationState.REQUESTED),
        (CodingSessionCancellationState.REQUESTED, CodingSessionCancellationState.CONFIRMED),
        (CodingSessionCancellationState.REQUESTED, CodingSessionCancellationState.FAILED),
    },
    CodingSessionStateDimension.RECOVERY: {
        (CodingSessionRecoveryState.UNKNOWN, CodingSessionRecoveryState.NOT_REQUIRED),
        (CodingSessionRecoveryState.UNKNOWN, CodingSessionRecoveryState.REQUIRED),
        (CodingSessionRecoveryState.NOT_REQUIRED, CodingSessionRecoveryState.REQUIRED),
        (CodingSessionRecoveryState.REQUIRED, CodingSessionRecoveryState.PLANNED),
        (CodingSessionRecoveryState.PLANNED, CodingSessionRecoveryState.IN_PROGRESS),
        (
            CodingSessionRecoveryState.IN_PROGRESS,
            CodingSessionRecoveryState.PARTIALLY_RECOVERED,
        ),
        (CodingSessionRecoveryState.IN_PROGRESS, CodingSessionRecoveryState.RECOVERED),
        (CodingSessionRecoveryState.IN_PROGRESS, CodingSessionRecoveryState.FAILED),
        (
            CodingSessionRecoveryState.PARTIALLY_RECOVERED,
            CodingSessionRecoveryState.RECOVERED,
        ),
        (
            CodingSessionRecoveryState.PARTIALLY_RECOVERED,
            CodingSessionRecoveryState.MANUAL_INTERVENTION,
        ),
        (CodingSessionRecoveryState.FAILED, CodingSessionRecoveryState.MANUAL_INTERVENTION),
    },
    CodingSessionStateDimension.EVALUATION: {
        (CodingSessionEvaluationState.UNKNOWN, CodingSessionEvaluationState.NOT_REQUIRED),
        (CodingSessionEvaluationState.UNKNOWN, CodingSessionEvaluationState.REQUIRED),
        (CodingSessionEvaluationState.REQUIRED, CodingSessionEvaluationState.PENDING),
        (CodingSessionEvaluationState.PENDING, CodingSessionEvaluationState.ACCEPTED),
        (CodingSessionEvaluationState.PENDING, CodingSessionEvaluationState.REJECTED),
        (CodingSessionEvaluationState.PENDING, CodingSessionEvaluationState.INCONCLUSIVE),
    },
    CodingSessionStateDimension.DEPLOYMENT_CANDIDATE: {
        (
            CodingSessionDeploymentCandidateState.ABSENT,
            CodingSessionDeploymentCandidateState.REQUIRED,
        ),
        (
            CodingSessionDeploymentCandidateState.REQUIRED,
            CodingSessionDeploymentCandidateState.PRODUCED,
        ),
        (
            CodingSessionDeploymentCandidateState.PRODUCED,
            CodingSessionDeploymentCandidateState.HANDED_OFF,
        ),
        (
            CodingSessionDeploymentCandidateState.PRODUCED,
            CodingSessionDeploymentCandidateState.REJECTED,
        ),
    },
}


def _request_diagnostics(
    request: CodingSessionTransitionRequest,
    projection: CodingSessionStateProjection,
    contract: CodingSessionContract | None,
    contract_assessment: CodingSessionContractAssessment | None,
) -> tuple[CodingSessionTransitionDiagnostic, ...]:
    findings: set[CodingSessionTransitionDiagnostic] = set()
    if request.session_identity != projection.session_identity:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.SESSION_IDENTITY_MISMATCH))
    if request.policy_version != CODING_SESSION_LIFECYCLE_POLICY_VERSION:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.UNSUPPORTED_POLICY_VERSION))
    if request.expected_causal_revision != projection.causal_revision:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.CAUSAL_REVISION_GAP))
    current = _current_state(projection, request.dimension)
    if request.expected_previous_state != current:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.PREVIOUS_STATE_MISMATCH))
    if not _states_match_dimension(request.dimension, request.expected_previous_state, request.next_state):
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.DIMENSION_STATE_MISMATCH))
    elif (request.expected_previous_state, request.next_state) not in _ALLOWED[request.dimension]:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.INVALID_TRANSITION))
    if (
        projection.lifecycle is CodingSessionLifecycleState.TERMINAL
        and request.dimension is CodingSessionStateDimension.LIFECYCLE
        and request.next_state is not CodingSessionLifecycleState.TERMINAL
    ):
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.TERMINAL_SESSION_REOPEN))
    if request.next_state is CodingSessionTerminalOutcome.COMPLETED:
        findings.add(
            _diagnostic(CodingSessionTransitionDiagnosticCode.COMPLETION_ASSESSMENT_UNAVAILABLE)
        )
    if request.reason is CodingSessionTransitionReason.RESTART_REPLAYED:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.RESTART_CANNOT_TRANSITION))
    if not _reason_corresponds(request):
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.INSUFFICIENT_EVIDENCE))
    if request.next_state is CodingSessionLifecycleState.PREPARED:
        if (
            contract is None
            or contract_assessment is None
            or contract.session_identity != request.session_identity
            or contract.fingerprint != contract_assessment.contract_fingerprint
            or not contract_assessment.complete
            or not contract_assessment.valid
        ):
            findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.CONTRACT_NOT_COMPLETE))
    if (
        request.next_state is CodingSessionTerminalOutcome.CANCELLED
        and projection.cancellation is not CodingSessionCancellationState.CONFIRMED
    ):
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.INSUFFICIENT_EVIDENCE))
    return tuple(sorted(findings, key=lambda item: (item.code.value, item.subject)))


def _reason_corresponds(request: CodingSessionTransitionRequest) -> bool:
    exact = {
        CodingSessionTransitionReason.SESSION_PLANNED: (
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.PLANNED,
            False,
        ),
        CodingSessionTransitionReason.CONTRACT_ACCEPTED: (
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.PREPARED,
            False,
        ),
        CodingSessionTransitionReason.ACTIVATION_CONFIRMED: (
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.ACTIVE,
            True,
        ),
        CodingSessionTransitionReason.SUSPENSION_CONFIRMED: (
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.SUSPENDED,
            True,
        ),
        CodingSessionTransitionReason.TERMINATION_CONFIRMED: (
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.TERMINAL,
            True,
        ),
        CodingSessionTransitionReason.CANCELLATION_REQUESTED: (
            CodingSessionStateDimension.CANCELLATION,
            CodingSessionCancellationState.REQUESTED,
            False,
        ),
        CodingSessionTransitionReason.CANCELLATION_CONFIRMED: (
            CodingSessionStateDimension.CANCELLATION,
            CodingSessionCancellationState.CONFIRMED,
            True,
        ),
        CodingSessionTransitionReason.WORKER_SUCCEEDED: (
            CodingSessionStateDimension.WORKER_BINDING,
            CodingSessionWorkerBindingState.SUCCEEDED,
            True,
        ),
        CodingSessionTransitionReason.PROCESS_EXITED: (
            CodingSessionStateDimension.EXECUTION_BINDING,
            CodingSessionExecutionBindingState.EXITED,
            True,
        ),
        CodingSessionTransitionReason.EVALUATION_ACCEPTED: (
            CodingSessionStateDimension.EVALUATION,
            CodingSessionEvaluationState.ACCEPTED,
            True,
        ),
        CodingSessionTransitionReason.MUTATION_APPLIED: (
            CodingSessionStateDimension.REPOSITORY_CORRESPONDENCE,
            CodingSessionRepositoryCorrespondenceState.STALE,
            True,
        ),
        CodingSessionTransitionReason.RECOVERY_REQUIRED: (
            CodingSessionStateDimension.RECOVERY,
            CodingSessionRecoveryState.REQUIRED,
            True,
        ),
        CodingSessionTransitionReason.RECOVERY_STARTED: (
            CodingSessionStateDimension.RECOVERY,
            CodingSessionRecoveryState.IN_PROGRESS,
            True,
        ),
        CodingSessionTransitionReason.DEPLOYMENT_CANDIDATE_PRODUCED: (
            CodingSessionStateDimension.DEPLOYMENT_CANDIDATE,
            CodingSessionDeploymentCandidateState.PRODUCED,
            True,
        ),
    }
    if request.reason in exact:
        dimension, state, evidence_required = exact[request.reason]
        return (
            request.dimension is dimension
            and request.next_state is state
            and (not evidence_required or bool(request.evidence))
        )
    generic_dimensions = {
        CodingSessionTransitionReason.COORDINATION_OBSERVED: CodingSessionStateDimension.COORDINATION,
        CodingSessionTransitionReason.REPOSITORY_OBSERVED: (
            CodingSessionStateDimension.REPOSITORY_CORRESPONDENCE
        ),
        CodingSessionTransitionReason.WORKER_ASSIGNED: CodingSessionStateDimension.WORKER_BINDING,
        CodingSessionTransitionReason.EXECUTION_OBSERVED: (
            CodingSessionStateDimension.EXECUTION_BINDING
        ),
        CodingSessionTransitionReason.CHECKPOINT_OBSERVED: CodingSessionStateDimension.CHECKPOINT,
        CodingSessionTransitionReason.RECOVERY_OBSERVED: CodingSessionStateDimension.RECOVERY,
        CodingSessionTransitionReason.EVALUATION_OBSERVED: CodingSessionStateDimension.EVALUATION,
        CodingSessionTransitionReason.DEPLOYMENT_HANDOFF_OBSERVED: (
            CodingSessionStateDimension.DEPLOYMENT_CANDIDATE
        ),
    }
    if request.reason in generic_dimensions:
        return request.dimension is generic_dimensions[request.reason] and bool(request.evidence)
    return request.reason is CodingSessionTransitionReason.EXTERNAL_FACT_OBSERVED and bool(
        request.evidence
    )


def _fact_diagnostics(
    projection: CodingSessionStateProjection,
    fact: CodingSessionLifecycleFact,
) -> tuple[CodingSessionTransitionDiagnostic, ...]:
    findings: set[CodingSessionTransitionDiagnostic] = set()
    revision = fact.causal_metadata.revision.value
    if fact.session_identity != projection.session_identity:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.SESSION_IDENTITY_MISMATCH))
    if fact.policy_version != CODING_SESSION_LIFECYCLE_POLICY_VERSION:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.UNSUPPORTED_POLICY_VERSION))
    if fact.causal_metadata.semantic_identity != fact.fact_identity:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.LINEAGE_GAP))
    if revision != projection.causal_revision + 1:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.CAUSAL_REVISION_GAP))
    expected_parents = (
        (projection.last_fact_fingerprint,) if projection.last_fact_fingerprint else ()
    )
    if fact.causal_metadata.lineage.parents != expected_parents:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.LINEAGE_GAP))
    current = _current_state(projection, fact.dimension)
    if fact.previous_state != current:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.PREVIOUS_STATE_MISMATCH))
    if not _states_match_dimension(fact.dimension, fact.previous_state, fact.next_state):
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.DIMENSION_STATE_MISMATCH))
    elif (fact.previous_state, fact.next_state) not in _ALLOWED[fact.dimension]:
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.INVALID_TRANSITION))
    replay_request = CodingSessionTransitionRequest(
        session_identity=fact.session_identity,
        dimension=fact.dimension,
        expected_previous_state=fact.previous_state,
        next_state=fact.next_state,
        reason=fact.reason,
        expected_causal_revision=revision - 1,
        evidence=fact.causal_metadata.lineage.references,
        policy_version=fact.policy_version,
    )
    if not _reason_corresponds(replay_request):
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.INSUFFICIENT_EVIDENCE))
    if (
        fact.next_state is CodingSessionTerminalOutcome.CANCELLED
        and projection.cancellation is not CodingSessionCancellationState.CONFIRMED
    ):
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.INSUFFICIENT_EVIDENCE))
    if (
        projection.lifecycle is CodingSessionLifecycleState.TERMINAL
        and fact.dimension is CodingSessionStateDimension.LIFECYCLE
        and fact.next_state is not CodingSessionLifecycleState.TERMINAL
    ):
        findings.add(_diagnostic(CodingSessionTransitionDiagnosticCode.TERMINAL_SESSION_REOPEN))
    if fact.next_state is CodingSessionTerminalOutcome.COMPLETED:
        findings.add(
            _diagnostic(CodingSessionTransitionDiagnosticCode.COMPLETION_ASSESSMENT_UNAVAILABLE)
        )
    return tuple(sorted(findings, key=lambda item: (item.code.value, item.subject)))


def _states_match_dimension(
    dimension: CodingSessionStateDimension,
    previous: CodingSessionSemanticState,
    next_state: CodingSessionSemanticState,
) -> bool:
    expected_type = _STATE_TYPES[dimension]
    return isinstance(previous, expected_type) and isinstance(next_state, expected_type)


def _current_state(
    projection: CodingSessionStateProjection, dimension: CodingSessionStateDimension
) -> CodingSessionSemanticState:
    return getattr(projection, _FIELD_NAMES[dimension])


def _apply_fact(
    projection: CodingSessionStateProjection, fact: CodingSessionLifecycleFact
) -> CodingSessionStateProjection:
    updated = _replace_dimension(projection, fact.dimension, fact.next_state)
    return replace(
        updated,
        causal_revision=fact.causal_metadata.revision.value,
        last_fact_fingerprint=fact.fingerprint,
    )


def _replace_dimension(
    projection: CodingSessionStateProjection,
    dimension: CodingSessionStateDimension,
    state: CodingSessionSemanticState,
) -> CodingSessionStateProjection:
    if dimension is CodingSessionStateDimension.LIFECYCLE and isinstance(
        state, CodingSessionLifecycleState
    ):
        return replace(projection, lifecycle=state)
    if dimension is CodingSessionStateDimension.TERMINAL_OUTCOME and isinstance(
        state, CodingSessionTerminalOutcome
    ):
        return replace(projection, terminal_outcome=state)
    if dimension is CodingSessionStateDimension.COORDINATION and isinstance(
        state, CodingSessionCoordinationState
    ):
        return replace(projection, coordination=state)
    if dimension is CodingSessionStateDimension.REPOSITORY_CORRESPONDENCE and isinstance(
        state, CodingSessionRepositoryCorrespondenceState
    ):
        return replace(projection, repository_correspondence=state)
    if dimension is CodingSessionStateDimension.WORKER_BINDING and isinstance(
        state, CodingSessionWorkerBindingState
    ):
        return replace(projection, worker_binding=state)
    if dimension is CodingSessionStateDimension.EXECUTION_BINDING and isinstance(
        state, CodingSessionExecutionBindingState
    ):
        return replace(projection, execution_binding=state)
    if dimension is CodingSessionStateDimension.CHECKPOINT and isinstance(
        state, CodingSessionCheckpointState
    ):
        return replace(projection, checkpoint=state)
    if dimension is CodingSessionStateDimension.CANCELLATION and isinstance(
        state, CodingSessionCancellationState
    ):
        return replace(projection, cancellation=state)
    if dimension is CodingSessionStateDimension.RECOVERY and isinstance(
        state, CodingSessionRecoveryState
    ):
        return replace(projection, recovery=state)
    if dimension is CodingSessionStateDimension.EVALUATION and isinstance(
        state, CodingSessionEvaluationState
    ):
        return replace(projection, evaluation=state)
    if dimension is CodingSessionStateDimension.DEPLOYMENT_CANDIDATE and isinstance(
        state, CodingSessionDeploymentCandidateState
    ):
        return replace(projection, deployment_candidate=state)
    return projection


def _diagnostic(
    code: CodingSessionTransitionDiagnosticCode,
) -> CodingSessionTransitionDiagnostic:
    return CodingSessionTransitionDiagnostic(code=code, subject="transition")
