from dataclasses import replace

from tests.test_coding_sessions_intents import _contract, _intent

from synapse.coding_sessions import (
    CodingSessionFingerprint,
    CodingSessionIntentCategory,
    CodingSessionLifecycleState,
    CodingSessionRequestedCapability,
    CodingSessionStateProjection,
    CodingSessionTargetAuthority,
)
from synapse.coding_sessions_integrations import (
    CodingSessionEvalDiagnosticCode,
    CodingSessionEvalReceipt,
    CodingSessionEvalReceiptKind,
    CodingSessionEvalReceiptState,
    CodingSessionEvaluationProjectionState,
    CodingSessionPrivateEvalContext,
    CodingSessionPrivateEvalsCompatibilityAdapter,
)
from synapse.private_evals import (
    BaselineId,
    EvalResultId,
    EvalRunId,
    ResultStatus,
    RunStatus,
    Verdict,
)


def _context(state=CodingSessionLifecycleState.ACTIVE, *, baseline=True, evidence=True):
    contract = _contract(capability=CodingSessionRequestedCapability.PRIVATE_EVAL)
    intent = _intent(
        contract,
        category=CodingSessionIntentCategory.PRIVATE_EVAL_REQUEST,
        authority=CodingSessionTargetAuthority.PRIVATE_EVALS,
        capability=CodingSessionRequestedCapability.PRIVATE_EVAL,
        write=False,
    )
    return CodingSessionPrivateEvalContext(
        contract,
        CodingSessionStateProjection(contract.session_identity, lifecycle=state),
        intent,
        "subject:one",
        CodingSessionFingerprint.from_content("subject"),
        "candidate:one",
        CodingSessionFingerprint.from_content("candidate"),
        "quality-evaluation",
        EvalRunId("run:one"),
        CodingSessionFingerprint.from_content("run"),
        BaselineId("baseline:one") if baseline else None,
        CodingSessionFingerprint.from_content("baseline") if baseline else None,
        (),
        (),
        evidence,
        "eval-policy",
        "v1",
    )


def _receipt(context, **changes):
    binding = context.contract.binding
    base = CodingSessionEvalReceipt(
        "private-evals", "v1", "receipt:one",
        CodingSessionFingerprint.from_content("receipt"),
        context.contract.session_identity.value, context.intent.intent_identity.value,
        context.contract.actor.value, context.contract.purpose.purpose.value,
        context.contract.correlation.value, context.subject_identity,
        context.subject_fingerprint, context.candidate_identity,
        context.candidate_fingerprint, context.run_id,
        context.run_fingerprint, EvalResultId("result:one"),
        CodingSessionFingerprint.from_content("result"), "evidence:one",
        CodingSessionFingerprint.from_content("evidence"), EvalResultId("result:one"),
        context.baseline_id, context.baseline_fingerprint, None, None,
        CodingSessionEvalReceiptKind.SCORING_RESULT,
        CodingSessionEvalReceiptState.RESULT_AVAILABLE, RunStatus.COMPLETED,
        ResultStatus.VALID, Verdict.PASSED, None, "scoring-v1",
        (
            binding.repository.identity if binding.repository else None,
            binding.checkout.identity if binding.checkout else None,
            binding.worktree.identity if binding.worktree else None,
        ),
        False, 1, None,
    )
    return replace(base, **changes)


def test_requests_never_score_select_baseline_promote_or_execute() -> None:
    context = _context()
    adapter = CodingSessionPrivateEvalsCompatibilityAdapter()
    results = (
        adapter.run_request(context),
        adapter.subject_evaluation(context),
        adapter.baseline_comparison(context),
        adapter.evidence_retrieval(
            context,
            result_id=EvalResultId("result:one"),
            result_fingerprint=CodingSessionFingerprint.from_content("result"),
        ),
    )
    assert all(item.request is not None for item in results)
    assert all(not item.score_calculated for item in results)
    assert all(not item.baseline_selected for item in results)
    assert all(not item.regression_decided for item in results)
    assert all(not item.candidate_promoted for item in results)
    assert all(not item.operation_executed for item in results)
    assert results[2].request.reference.baseline_selector is None


def test_baseline_is_explicit_and_missing_or_mismatch_fails_closed() -> None:
    missing = _context(baseline=False)
    rejected = CodingSessionPrivateEvalsCompatibilityAdapter.baseline_comparison(missing)
    context = _context()
    projection = CodingSessionPrivateEvalsCompatibilityAdapter.project_receipt(
        context, _receipt(context, baseline_id=BaselineId("baseline:other"))
    )
    assert rejected.request is None
    assert projection.result_reference is None
    assert CodingSessionEvalDiagnosticCode.BASELINE_MISMATCH in {
        item.code for item in projection.diagnostics
    }


def test_passed_and_rejected_results_never_change_session_outcome() -> None:
    context = _context()
    accepted = CodingSessionPrivateEvalsCompatibilityAdapter.project_receipt(
        context, _receipt(context)
    )
    rejected = CodingSessionPrivateEvalsCompatibilityAdapter.project_receipt(
        context, _receipt(context, verdict=Verdict.FAILED)
    )
    assert accepted.state is CodingSessionEvaluationProjectionState.ACCEPTED
    assert rejected.state is CodingSessionEvaluationProjectionState.REJECTED
    assert not accepted.session_completed and not rejected.session_failed
    assert not accepted.session_lifecycle_changed and not rejected.session_lifecycle_changed
    assert not accepted.scoring_authority_transferred
    assert not accepted.candidate_promoted


def test_run_result_and_evidence_result_mismatch_fail_closed() -> None:
    context = _context()
    run = CodingSessionPrivateEvalsCompatibilityAdapter.project_receipt(
        context, _receipt(context, run_id=EvalRunId("run:other"))
    )
    evidence = CodingSessionPrivateEvalsCompatibilityAdapter.project_receipt(
        context, _receipt(context, evidence_for_result_id=EvalResultId("result:other"))
    )
    assert run.run_reference is None
    assert evidence.evidence_reference is None
    assert CodingSessionEvalDiagnosticCode.RUN_RESULT_MISMATCH in {x.code for x in run.diagnostics}
    assert CodingSessionEvalDiagnosticCode.EVIDENCE_RESULT_MISMATCH in {x.code for x in evidence.diagnostics}


def test_stale_and_missing_required_evidence_do_not_satisfy_current_requirement() -> None:
    context = _context()
    result = CodingSessionPrivateEvalsCompatibilityAdapter.project_receipt(
        context,
        _receipt(
            context, stale=True, evidence_identity=None,
            evidence_fingerprint=None, evidence_for_result_id=None,
        ),
    )
    assert result.state is CodingSessionEvaluationProjectionState.STALE
    assert result.result_reference is None
    assert {x.code for x in result.diagnostics} >= {
        CodingSessionEvalDiagnosticCode.STALE_RESULT,
        CodingSessionEvalDiagnosticCode.MISSING_REQUIRED_EVIDENCE,
    }


def test_scoring_regression_baseline_and_evidence_remain_distinct() -> None:
    context = _context()
    kinds = tuple(
        CodingSessionPrivateEvalsCompatibilityAdapter.project_receipt(
            context, _receipt(context, kind=kind)
        )
        for kind in CodingSessionEvalReceiptKind
    )
    assert len(kinds) == 5
    assert all(item.comparison_result is None for item in kinds)


def test_contradiction_lineage_and_late_result_remain_explicit() -> None:
    context = _context(CodingSessionLifecycleState.TERMINAL)
    first = _receipt(context, verdict=Verdict.PASSED)
    second = _receipt(
        context, receipt_identity="receipt:two", verdict=Verdict.FAILED,
        causal_revision=2, parent_receipt_identity=None,
    )
    result = CodingSessionPrivateEvalsCompatibilityAdapter.project_receipt(
        context, second, known_receipts=(first,)
    )
    assert {x.code for x in result.diagnostics} >= {
        CodingSessionEvalDiagnosticCode.CONTRADICTORY_RESULT,
        CodingSessionEvalDiagnosticCode.LINEAGE_GAP,
        CodingSessionEvalDiagnosticCode.LATE_RESULT,
    }
    assert not result.reopens_terminal_session


def test_same_canonical_input_is_deterministic() -> None:
    context = _context()
    assert (
        CodingSessionPrivateEvalsCompatibilityAdapter.run_request(context)
        == CodingSessionPrivateEvalsCompatibilityAdapter.run_request(context)
    )
