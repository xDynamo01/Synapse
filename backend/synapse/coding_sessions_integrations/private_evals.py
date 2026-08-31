"""Reference-only compatibility with the frozen Private Evals authority."""

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
    CodingSessionPrivateEvalEvidenceReference,
    CodingSessionPrivateEvalResultReference,
    CodingSessionPrivateEvalRunReference,
    CodingSessionRequestedCapability,
    CodingSessionStateProjection,
    CodingSessionTargetAuthority,
)
from synapse.private_evals import (
    BaselineId,
    ComparisonResult,
    EvalResultId,
    EvalRunId,
    RegressionReportId,
    ResultStatus,
    RunStatus,
    Verdict,
)

CODING_SESSION_PRIVATE_EVALS_COMPATIBILITY_VERSION = (
    "coding-session-private-evals-compatibility-v1"
)


class CodingSessionEvalRequestKind(str, Enum):
    RUN = "run"
    SUBJECT_EVALUATION = "subject-evaluation"
    BASELINE_COMPARISON = "baseline-comparison"
    EVIDENCE_RETRIEVAL = "evidence-retrieval"


class CodingSessionEvalReceiptKind(str, Enum):
    RUN = "run"
    SCORING_RESULT = "scoring-result"
    REGRESSION_RESULT = "regression-result"
    BASELINE_RESULT = "baseline-result"
    EVIDENCE = "evidence"


class CodingSessionEvalReceiptState(str, Enum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    RESULT_AVAILABLE = "result-available"
    EVIDENCE_AVAILABLE = "evidence-available"
    STALE = "stale"
    LATE = "late"
    UNKNOWN = "unknown"


class CodingSessionEvaluationProjectionState(str, Enum):
    NOT_REQUESTED = "not-requested"
    REQUESTED = "requested"
    PENDING = "pending"
    RECEIVED = "received"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    STALE = "stale"
    UNKNOWN = "unknown"


class CodingSessionEvalDiagnosticCode(str, Enum):
    SESSION_MISMATCH = "session-mismatch"
    INTENT_MISMATCH = "intent-mismatch"
    RUN_RESULT_MISMATCH = "run-result-mismatch"
    EVIDENCE_RESULT_MISMATCH = "evidence-result-mismatch"
    SUBJECT_MISMATCH = "subject-mismatch"
    ACTOR_PURPOSE_CORRELATION_MISMATCH = "actor-purpose-correlation-mismatch"
    BINDING_MISMATCH = "binding-mismatch"
    BASELINE_MISMATCH = "baseline-mismatch"
    STALE_RESULT = "stale-result"
    LATE_RESULT = "late-result"
    DUPLICATE_RECEIPT = "duplicate-receipt"
    CONTRADICTORY_RESULT = "contradictory-result"
    PRODUCER_VERSION_MISMATCH = "producer-version-mismatch"
    CAUSAL_REVISION_MISMATCH = "causal-revision-mismatch"
    LINEAGE_GAP = "lineage-gap"
    MISSING_REQUIRED_EVIDENCE = "missing-required-evidence"
    CAPABILITY_MISMATCH = "capability-mismatch"
    LIFECYCLE_INCOMPATIBLE = "lifecycle-incompatible"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionEvalDiagnostic:
    code: CodingSessionEvalDiagnosticCode
    subject: str = "private-evals-compatibility"


@dataclass(frozen=True, slots=True)
class CodingSessionPrivateEvalContext:
    contract: CodingSessionContract
    lifecycle: CodingSessionStateProjection
    intent: CodingSessionIntent
    subject_identity: str
    subject_fingerprint: CodingSessionFingerprint
    candidate_identity: str
    candidate_fingerprint: CodingSessionFingerprint
    requested_evaluation_capability: str
    run_id: EvalRunId | None
    run_fingerprint: CodingSessionFingerprint | None
    baseline_id: BaselineId | None
    baseline_fingerprint: CodingSessionFingerprint | None
    artifact_references: tuple[CodingSessionArtifactReference, ...]
    authorization_references: tuple[CodingSessionArtifactReference, ...]
    evidence_required: bool
    policy_id: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class CodingSessionEvalReferenceRequest:
    session_identity: str
    intent_identity: str
    actor: str
    project: str
    task: str
    purpose: str
    correlation: str
    subject_identity: str
    subject_fingerprint: CodingSessionFingerprint
    candidate_identity: str
    candidate_fingerprint: CodingSessionFingerprint
    requested_evaluation_capability: str
    run_id: EvalRunId | None
    run_fingerprint: CodingSessionFingerprint | None
    baseline_id: BaselineId | None
    baseline_fingerprint: CodingSessionFingerprint | None
    repository_binding: tuple[str | None, str | None, str | None]
    artifact_references: tuple[CodingSessionArtifactReference, ...]
    authorization_references: tuple[CodingSessionArtifactReference, ...]
    causal_revision: int
    policy_id: str
    policy_version: str
    baseline_selector: None = None


@dataclass(frozen=True, slots=True)
class CodingSessionEvalRunRequest:
    reference: CodingSessionEvalReferenceRequest
    score_calculated_locally: bool = False


@dataclass(frozen=True, slots=True)
class CodingSessionSubjectEvaluationRequest:
    reference: CodingSessionEvalReferenceRequest


@dataclass(frozen=True, slots=True)
class CodingSessionBaselineComparisonRequest:
    reference: CodingSessionEvalReferenceRequest
    regression_decided_locally: bool = False


@dataclass(frozen=True, slots=True)
class CodingSessionEvalEvidenceRetrievalRequest:
    reference: CodingSessionEvalReferenceRequest
    result_id: EvalResultId
    result_fingerprint: CodingSessionFingerprint


CodingSessionNeutralEvalRequest: TypeAlias = (
    CodingSessionEvalRunRequest
    | CodingSessionSubjectEvaluationRequest
    | CodingSessionBaselineComparisonRequest
    | CodingSessionEvalEvidenceRetrievalRequest
)


@dataclass(frozen=True, slots=True)
class CodingSessionEvalTranslation:
    kind: CodingSessionEvalRequestKind
    request: CodingSessionNeutralEvalRequest | None
    score_calculated: bool
    baseline_selected: bool
    regression_decided: bool
    candidate_promoted: bool
    operation_executed: bool
    diagnostics: tuple[CodingSessionEvalDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CodingSessionEvalReceipt:
    producer: str
    producer_version: str
    receipt_identity: str
    producer_fingerprint: CodingSessionFingerprint
    session_identity: str
    intent_identity: str
    actor: str
    purpose: str
    correlation: str
    subject_identity: str
    subject_fingerprint: CodingSessionFingerprint
    candidate_identity: str
    candidate_fingerprint: CodingSessionFingerprint
    run_id: EvalRunId
    run_fingerprint: CodingSessionFingerprint
    result_id: EvalResultId | None
    result_fingerprint: CodingSessionFingerprint | None
    evidence_identity: str | None
    evidence_fingerprint: CodingSessionFingerprint | None
    evidence_for_result_id: EvalResultId | None
    baseline_id: BaselineId | None
    baseline_fingerprint: CodingSessionFingerprint | None
    regression_report_id: RegressionReportId | None
    regression_report_fingerprint: CodingSessionFingerprint | None
    kind: CodingSessionEvalReceiptKind
    state: CodingSessionEvalReceiptState
    run_status: RunStatus | None
    result_status: ResultStatus | None
    verdict: Verdict | None
    comparison_result: ComparisonResult | None
    scoring_version: str | None
    repository_binding: tuple[str | None, str | None, str | None]
    stale: bool
    causal_revision: int
    parent_receipt_identity: str | None


@dataclass(frozen=True, slots=True)
class CodingSessionEvaluationProjection:
    state: CodingSessionEvaluationProjectionState
    run_reference: CodingSessionPrivateEvalRunReference | None
    result_reference: CodingSessionPrivateEvalResultReference | None
    evidence_reference: CodingSessionPrivateEvalEvidenceReference | None
    verdict: Verdict | None
    comparison_result: ComparisonResult | None
    scoring_authority_transferred: bool
    session_lifecycle_changed: bool
    session_completed: bool
    session_failed: bool
    recovery_started: bool
    deployment_candidate_created: bool
    candidate_promoted: bool
    reopens_terminal_session: bool
    diagnostics: tuple[CodingSessionEvalDiagnostic, ...]


class CodingSessionPrivateEvalsCompatibilityAdapter:
    @staticmethod
    def run_request(context: CodingSessionPrivateEvalContext) -> CodingSessionEvalTranslation:
        diagnostics = _context_diagnostics(context)
        request = None if diagnostics else CodingSessionEvalRunRequest(_reference(context))
        return _translation(CodingSessionEvalRequestKind.RUN, request, diagnostics)

    @staticmethod
    def subject_evaluation(context: CodingSessionPrivateEvalContext) -> CodingSessionEvalTranslation:
        diagnostics = _context_diagnostics(context, require_run=True)
        request = None if diagnostics else CodingSessionSubjectEvaluationRequest(_reference(context))
        return _translation(CodingSessionEvalRequestKind.SUBJECT_EVALUATION, request, diagnostics)

    @staticmethod
    def baseline_comparison(context: CodingSessionPrivateEvalContext) -> CodingSessionEvalTranslation:
        diagnostics = _context_diagnostics(context, require_run=True, require_baseline=True)
        request = None if diagnostics else CodingSessionBaselineComparisonRequest(_reference(context))
        return _translation(CodingSessionEvalRequestKind.BASELINE_COMPARISON, request, diagnostics)

    @staticmethod
    def evidence_retrieval(
        context: CodingSessionPrivateEvalContext,
        *,
        result_id: EvalResultId,
        result_fingerprint: CodingSessionFingerprint,
    ) -> CodingSessionEvalTranslation:
        diagnostics = _context_diagnostics(context, require_run=True)
        request = None if diagnostics else CodingSessionEvalEvidenceRetrievalRequest(
            _reference(context), result_id, result_fingerprint
        )
        return _translation(CodingSessionEvalRequestKind.EVIDENCE_RETRIEVAL, request, diagnostics)

    @staticmethod
    def project_receipt(
        context: CodingSessionPrivateEvalContext,
        receipt: CodingSessionEvalReceipt,
        *,
        known_receipts: tuple[CodingSessionEvalReceipt, ...] = (),
    ) -> CodingSessionEvaluationProjection:
        findings = set(_context_diagnostics(context, allow_terminal=True))
        comparisons = (
            (receipt.session_identity, context.contract.session_identity.value, CodingSessionEvalDiagnosticCode.SESSION_MISMATCH),
            (receipt.intent_identity, context.intent.intent_identity.value, CodingSessionEvalDiagnosticCode.INTENT_MISMATCH),
            ((receipt.actor, receipt.purpose, receipt.correlation), (context.contract.actor.value, context.contract.purpose.purpose.value, context.contract.correlation.value), CodingSessionEvalDiagnosticCode.ACTOR_PURPOSE_CORRELATION_MISMATCH),
            ((receipt.subject_identity, receipt.subject_fingerprint), (context.subject_identity, context.subject_fingerprint), CodingSessionEvalDiagnosticCode.SUBJECT_MISMATCH),
            ((receipt.candidate_identity, receipt.candidate_fingerprint), (context.candidate_identity, context.candidate_fingerprint), CodingSessionEvalDiagnosticCode.SUBJECT_MISMATCH),
            ((receipt.run_id, receipt.run_fingerprint), (context.run_id, context.run_fingerprint), CodingSessionEvalDiagnosticCode.RUN_RESULT_MISMATCH),
            ((receipt.baseline_id, receipt.baseline_fingerprint), (context.baseline_id, context.baseline_fingerprint), CodingSessionEvalDiagnosticCode.BASELINE_MISMATCH),
            (receipt.repository_binding, _binding(context), CodingSessionEvalDiagnosticCode.BINDING_MISMATCH),
        )
        for actual, expected, code in comparisons:
            if actual != expected:
                findings.add(CodingSessionEvalDiagnostic(code))
        if receipt.producer != "private-evals" or receipt.producer_version != "v1":
            findings.add(CodingSessionEvalDiagnostic(CodingSessionEvalDiagnosticCode.PRODUCER_VERSION_MISMATCH))
        if receipt.result_id is not None and receipt.result_fingerprint is None:
            findings.add(CodingSessionEvalDiagnostic(CodingSessionEvalDiagnosticCode.RUN_RESULT_MISMATCH))
        if receipt.evidence_identity is not None and (
            receipt.evidence_fingerprint is None
            or receipt.evidence_for_result_id != receipt.result_id
        ):
            findings.add(CodingSessionEvalDiagnostic(CodingSessionEvalDiagnosticCode.EVIDENCE_RESULT_MISMATCH))
        if context.evidence_required and (
            receipt.evidence_identity is None or receipt.evidence_fingerprint is None
        ):
            findings.add(CodingSessionEvalDiagnostic(CodingSessionEvalDiagnosticCode.MISSING_REQUIRED_EVIDENCE))
        if receipt.stale or receipt.state is CodingSessionEvalReceiptState.STALE:
            findings.add(CodingSessionEvalDiagnostic(CodingSessionEvalDiagnosticCode.STALE_RESULT))
        if receipt.causal_revision < context.intent.causal_metadata.revision.value:
            findings.add(CodingSessionEvalDiagnostic(CodingSessionEvalDiagnosticCode.CAUSAL_REVISION_MISMATCH))
        if receipt.causal_revision > 1 and receipt.parent_receipt_identity is None:
            findings.add(CodingSessionEvalDiagnostic(CodingSessionEvalDiagnosticCode.LINEAGE_GAP))
        terminal_states = {CodingSessionEvalReceiptState.COMPLETED, CodingSessionEvalReceiptState.FAILED, CodingSessionEvalReceiptState.RESULT_AVAILABLE}
        for known in known_receipts:
            if known.receipt_identity == receipt.receipt_identity:
                code = CodingSessionEvalDiagnosticCode.DUPLICATE_RECEIPT if known == receipt else CodingSessionEvalDiagnosticCode.CONTRADICTORY_RESULT
                findings.add(CodingSessionEvalDiagnostic(code))
            if known.run_id == receipt.run_id and known.state in terminal_states and receipt.state in terminal_states and (known.verdict, known.comparison_result) != (receipt.verdict, receipt.comparison_result):
                findings.add(CodingSessionEvalDiagnostic(CodingSessionEvalDiagnosticCode.CONTRADICTORY_RESULT))
            if known.causal_revision == receipt.causal_revision and known.receipt_identity != receipt.receipt_identity:
                findings.add(CodingSessionEvalDiagnostic(CodingSessionEvalDiagnosticCode.CAUSAL_REVISION_MISMATCH))
        if context.lifecycle.lifecycle is CodingSessionLifecycleState.TERMINAL or receipt.state is CodingSessionEvalReceiptState.LATE:
            findings.add(CodingSessionEvalDiagnostic(CodingSessionEvalDiagnosticCode.LATE_RESULT))
        diagnostics = _ordered(findings)
        failed = any(item.code in _CORRESPONDENCE_FAILURES for item in diagnostics)
        run_ref = result_ref = evidence_ref = None
        if not failed:
            run_ref = CodingSessionPrivateEvalRunReference.create(
                receipt.producer, receipt.producer_version, receipt.run_id.value,
                receipt.run_fingerprint,
            )
            if receipt.result_id and receipt.result_fingerprint:
                result_ref = CodingSessionPrivateEvalResultReference.create(
                    receipt.producer, receipt.producer_version, receipt.result_id.value,
                    receipt.result_fingerprint,
                )
            if receipt.evidence_identity and receipt.evidence_fingerprint:
                evidence_ref = CodingSessionPrivateEvalEvidenceReference.create(
                    receipt.producer, receipt.producer_version, receipt.evidence_identity,
                    receipt.evidence_fingerprint,
                )
        return CodingSessionEvaluationProjection(
            _projection_state(receipt, diagnostics), run_ref, result_ref, evidence_ref,
            receipt.verdict, receipt.comparison_result, False, False, False, False,
            False, False, False, False, diagnostics,
        )


def _context_diagnostics(context: CodingSessionPrivateEvalContext, *, require_run: bool = False, require_baseline: bool = False, allow_terminal: bool = False) -> tuple[CodingSessionEvalDiagnostic, ...]:
    contract, intent = context.contract, context.intent
    checks = (
        (intent.session_identity != contract.session_identity, CodingSessionEvalDiagnosticCode.SESSION_MISMATCH),
        (intent.actor != contract.actor or intent.purpose != contract.purpose or intent.correlation != contract.correlation, CodingSessionEvalDiagnosticCode.ACTOR_PURPOSE_CORRELATION_MISMATCH),
        (intent.binding != contract.binding, CodingSessionEvalDiagnosticCode.BINDING_MISMATCH),
        (intent.category is not CodingSessionIntentCategory.PRIVATE_EVAL_REQUEST or intent.target_authority is not CodingSessionTargetAuthority.PRIVATE_EVALS or intent.requirement.requested_capability is not CodingSessionRequestedCapability.PRIVATE_EVAL, CodingSessionEvalDiagnosticCode.CAPABILITY_MISMATCH),
        (intent.policy_version != CODING_SESSION_INTENT_POLICY_VERSION, CodingSessionEvalDiagnosticCode.PRODUCER_VERSION_MISMATCH),
        (require_run and (context.run_id is None or context.run_fingerprint is None), CodingSessionEvalDiagnosticCode.RUN_RESULT_MISMATCH),
        (require_baseline and (context.baseline_id is None or context.baseline_fingerprint is None), CodingSessionEvalDiagnosticCode.BASELINE_MISMATCH),
        (not allow_terminal and context.lifecycle.lifecycle not in {CodingSessionLifecycleState.PREPARED, CodingSessionLifecycleState.ACTIVE}, CodingSessionEvalDiagnosticCode.LIFECYCLE_INCOMPATIBLE),
    )
    return _ordered({CodingSessionEvalDiagnostic(code) for failed, code in checks if failed})


def _reference(context: CodingSessionPrivateEvalContext) -> CodingSessionEvalReferenceRequest:
    contract = context.contract
    return CodingSessionEvalReferenceRequest(
        contract.session_identity.value, context.intent.intent_identity.value,
        contract.actor.value, contract.project.value, contract.purpose.task.value,
        contract.purpose.purpose.value, contract.correlation.value,
        context.subject_identity, context.subject_fingerprint, context.candidate_identity,
        context.candidate_fingerprint, context.requested_evaluation_capability,
        context.run_id, context.run_fingerprint, context.baseline_id,
        context.baseline_fingerprint, _binding(context),
        tuple(sorted(set(context.artifact_references), key=lambda item: item.identity)),
        tuple(sorted(set(context.authorization_references), key=lambda item: item.identity)),
        context.intent.causal_metadata.revision.value, context.policy_id,
        context.policy_version,
    )


def _binding(context: CodingSessionPrivateEvalContext) -> tuple[str | None, str | None, str | None]:
    binding = context.contract.binding
    return (
        binding.repository.identity if binding.repository else None,
        binding.checkout.identity if binding.checkout else None,
        binding.worktree.identity if binding.worktree else None,
    )


def _translation(kind, request, diagnostics):
    return CodingSessionEvalTranslation(kind, request, False, False, False, False, False, diagnostics)


def _ordered(findings: set[CodingSessionEvalDiagnostic]) -> tuple[CodingSessionEvalDiagnostic, ...]:
    return tuple(sorted(findings, key=lambda item: (item.code.value, item.subject)))


def _projection_state(receipt: CodingSessionEvalReceipt, diagnostics: tuple[CodingSessionEvalDiagnostic, ...]) -> CodingSessionEvaluationProjectionState:
    if CodingSessionEvalDiagnostic(CodingSessionEvalDiagnosticCode.STALE_RESULT) in diagnostics:
        return CodingSessionEvaluationProjectionState.STALE
    if receipt.verdict is Verdict.PASSED:
        return CodingSessionEvaluationProjectionState.ACCEPTED
    if receipt.verdict in {Verdict.FAILED, Verdict.INVALID, Verdict.BLOCKED, Verdict.POLICY_DENIED}:
        return CodingSessionEvaluationProjectionState.REJECTED
    return {
        CodingSessionEvalReceiptState.REQUESTED: CodingSessionEvaluationProjectionState.REQUESTED,
        CodingSessionEvalReceiptState.ACCEPTED: CodingSessionEvaluationProjectionState.PENDING,
        CodingSessionEvalReceiptState.RUNNING: CodingSessionEvaluationProjectionState.PENDING,
        CodingSessionEvalReceiptState.COMPLETED: CodingSessionEvaluationProjectionState.RECEIVED,
        CodingSessionEvalReceiptState.FAILED: CodingSessionEvaluationProjectionState.REJECTED,
        CodingSessionEvalReceiptState.UNAVAILABLE: CodingSessionEvaluationProjectionState.UNKNOWN,
        CodingSessionEvalReceiptState.RESULT_AVAILABLE: CodingSessionEvaluationProjectionState.RECEIVED,
        CodingSessionEvalReceiptState.EVIDENCE_AVAILABLE: CodingSessionEvaluationProjectionState.RECEIVED,
        CodingSessionEvalReceiptState.STALE: CodingSessionEvaluationProjectionState.STALE,
        CodingSessionEvalReceiptState.LATE: CodingSessionEvaluationProjectionState.RECEIVED,
        CodingSessionEvalReceiptState.UNKNOWN: CodingSessionEvaluationProjectionState.UNKNOWN,
    }[receipt.state]


_CORRESPONDENCE_FAILURES = {
    CodingSessionEvalDiagnosticCode.SESSION_MISMATCH,
    CodingSessionEvalDiagnosticCode.INTENT_MISMATCH,
    CodingSessionEvalDiagnosticCode.RUN_RESULT_MISMATCH,
    CodingSessionEvalDiagnosticCode.EVIDENCE_RESULT_MISMATCH,
    CodingSessionEvalDiagnosticCode.SUBJECT_MISMATCH,
    CodingSessionEvalDiagnosticCode.ACTOR_PURPOSE_CORRELATION_MISMATCH,
    CodingSessionEvalDiagnosticCode.BINDING_MISMATCH,
    CodingSessionEvalDiagnosticCode.BASELINE_MISMATCH,
    CodingSessionEvalDiagnosticCode.STALE_RESULT,
    CodingSessionEvalDiagnosticCode.CONTRADICTORY_RESULT,
    CodingSessionEvalDiagnosticCode.PRODUCER_VERSION_MISMATCH,
    CodingSessionEvalDiagnosticCode.CAUSAL_REVISION_MISMATCH,
    CodingSessionEvalDiagnosticCode.LINEAGE_GAP,
    CodingSessionEvalDiagnosticCode.MISSING_REQUIRED_EVIDENCE,
    CodingSessionEvalDiagnosticCode.CAPABILITY_MISMATCH,
}
