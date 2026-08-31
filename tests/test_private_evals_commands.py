from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from synapse.private_evals.case_evaluation import CaseEvaluationResponse
from synapse.private_evals.command_errors import (
    PrivateEvalBoundaryError,
    PublicErrorCategory,
    ReferencedInputMismatch,
    ReferencedInputNotFound,
)
from synapse.private_evals.command_handlers import PrivateEvalsCommandHandlers
from synapse.private_evals.command_models import (
    CreateEvalResultCommand,
    CreateRunCommand,
    CreateScoringDecisionCommand,
    FinalizeRunCommand,
    PrivateEvalCommandContext,
    PublicWriteOutcome,
    RecordMaterializedOutputCommand,
    RecoverFinalizationCommand,
    StartRunCommand,
    SubmitEvidenceCommand,
)
from synapse.private_evals.evidence_submission_errors import (
    EvidenceReconciliationRequired,
)
from synapse.private_evals.evidence_submission_models import EvidenceSubmissionOutcome
from synapse.private_evals.query_handler import PrivateEvalsRunSummaryQuery
from synapse.private_evals.query_models import (
    EvidenceLocalState,
    EvidenceLocalStateProjection,
    PrivateEvalQueryContext,
    RunSummaryRequest,
)
from synapse.private_evals.run_finalization_errors import RunFinalizationError
from synapse.private_evals.run_finalization_service import FinalizationWriteDisposition
from synapse.private_evals.store_models import WriteDisposition
from synapse.private_evals.values import EvalRunId

HEX = "a" * 64


def _value(value: object) -> SimpleNamespace:
    return SimpleNamespace(value=value)


def _context() -> PrivateEvalCommandContext:
    return PrivateEvalCommandContext(
        "actor-1",
        "authz-1",
        HEX,
        "binding-1",
        "correlation-1",
        "request-1",
        "idem-1",
        "2026-07-19T12:00:00Z",
    )


def _query_context() -> PrivateEvalQueryContext:
    return PrivateEvalQueryContext(
        "actor-1", "authz-1", HEX, "binding-1", "correlation-1", "request-1"
    )


def _dependencies() -> SimpleNamespace:
    return SimpleNamespace(
        run_runtime=Mock(),
        materialization_service=Mock(),
        result_service=Mock(),
        scoring_service=Mock(),
        finalization_service=Mock(),
        evidence_submission_service=Mock(),
        manifest_resolver=Mock(),
        materialization_resolver=Mock(),
        evaluation_resolver=Mock(),
        scoring_resolver=Mock(),
        finalization_resolver=Mock(),
        evidence_submission_resolver=Mock(),
    )


def _principal_call_count(dependencies: SimpleNamespace) -> int:
    return sum(
        item.call_count
        for item in (
            dependencies.run_runtime.prepare_run,
            dependencies.run_runtime.start_run,
            dependencies.materialization_service.materialize,
            dependencies.result_service.create_result,
            dependencies.scoring_service.score_run,
            dependencies.finalization_service.finalize,
            dependencies.evidence_submission_service.submit,
        )
    )


def _materialization_command() -> RecordMaterializedOutputCommand:
    return RecordMaterializedOutputCommand(
        _context(),
        "run-1",
        "execution-request-1",
        "execution-attempt-1",
        "logical-projection-1",
        "manifest-1",
        "case-1",
        "output-1",
        "private-evals",
        "15.0.0",
    )


def _evaluation_command() -> CreateEvalResultCommand:
    response = object.__new__(CaseEvaluationResponse)
    return CreateEvalResultCommand(
        _context(),
        "run-1",
        "output-1",
        "evaluation-request-1",
        response,
        "manifest-1",
        "case-1",
        "scoring-protocol-1",
        "result-1",
        "private-evals",
        "15.0.0",
    )


def _scoring_command() -> CreateScoringDecisionCommand:
    return CreateScoringDecisionCommand(
        _context(),
        "run-1",
        "manifest-1",
        HEX,
        "scoring-protocol-1",
        HEX,
        "expected-matrix-1",
        ("result-1", "result-2"),
        "decision-1",
        "private-evals",
        "15.0.0",
    )


def _finalization_command(*, recover: bool = False):
    values = (
        _context(),
        "run-1",
        "finalization-1",
        "run-1",
        "manifest-1",
        "expected-matrix-1",
        ("result-1",),
        "decision-1",
        (),
        "execution-accounting-1",
        ("execution-projection-1",),
        (),
        "security-snapshot-1",
        HEX,
        "private-evals",
        "15.0.0",
    )
    return RecoverFinalizationCommand(*values) if recover else FinalizeRunCommand(*values)


def _evidence_command() -> SubmitEvidenceCommand:
    return SubmitEvidenceCommand(
        _context(),
        "run-1",
        "submission-1",
        "finalization-1",
        "implementation-1",
        (),
        None,
        (),
        "private-evals",
        "15.0.0",
    )


def test_context_is_immutable_reference_only_and_safe_repr() -> None:
    context = _context()
    with pytest.raises(FrozenInstanceError):
        context.actor_reference = "other"  # type: ignore[misc]
    rendered = repr(context)
    assert "idem-1" not in rendered
    assert HEX not in rendered
    assert not hasattr(context, "roles")
    assert not hasattr(context, "token")


@pytest.mark.parametrize(
    ("field", "value", "category"),
    [
        ("authorization_decision_reference", "", PublicErrorCategory.UNAUTHORIZED_REFERENCE),
        ("authorization_policy_fingerprint", "bad", PublicErrorCategory.UNAUTHORIZED_REFERENCE),
        ("implementation_binding_reference", "C:\\private", PublicErrorCategory.UNAUTHORIZED_REFERENCE),
        ("idempotency_key", "secret-token", PublicErrorCategory.INVALID_REQUEST),
    ],
)
def test_context_rejects_invalid_references(field: str, value: str, category) -> None:
    values = vars(_context()).copy()
    values[field] = value
    with pytest.raises(PrivateEvalBoundaryError) as caught:
        PrivateEvalCommandContext(**values)
    assert caught.value.envelope.code is category


def test_commands_reject_implicit_or_duplicate_record_sets() -> None:
    with pytest.raises(PrivateEvalBoundaryError):
        CreateScoringDecisionCommand(
            _context(), "run-1", "manifest-1", HEX, "protocol-1", HEX,
            "matrix-1", (), "decision-1", "producer-1", "15.0.0"
        )
    with pytest.raises(PrivateEvalBoundaryError):
        CreateScoringDecisionCommand(
            _context(), "run-1", "manifest-1", HEX, "protocol-1", HEX,
            "matrix-1", ("result-1", "result-1"), "decision-1", "producer-1", "15.0.0"
        )


def test_create_run_resolves_existing_manifest_and_calls_only_prepare() -> None:
    deps = _dependencies()
    deps.manifest_resolver.resolve_manifest.return_value = object()
    deps.run_runtime.prepare_run.return_value = SimpleNamespace(
        run_id=_value("run-1"), status=_value("created"), revision=_value(1),
        manifest_id=_value("manifest-1")
    )
    response = PrivateEvalsCommandHandlers(deps).create_run(
        CreateRunCommand(_context(), "run-1", "manifest-1")
    )
    assert response.outcome is PublicWriteOutcome.CREATED
    assert _principal_call_count(deps) == 1
    assert deps.manifest_resolver.resolve_manifest.call_args.args == ("manifest-1",)


def test_start_run_only_performs_cas_transition() -> None:
    deps = _dependencies()
    deps.run_runtime.start_run.return_value = SimpleNamespace(
        run_id=_value("run-1"), status=_value("running"), revision=_value(3),
        manifest_id=_value("manifest-1")
    )
    response = PrivateEvalsCommandHandlers(deps).start_run(
        StartRunCommand(_context(), "run-1", 2)
    )
    assert response.run_status == "running"
    assert deps.run_runtime.start_run.call_args.kwargs["expected_revision"].value == 2
    assert _principal_call_count(deps) == 1


def test_materialization_resolves_only_explicit_records_and_stops() -> None:
    deps = _dependencies()
    resolver = deps.materialization_resolver
    resolver.resolve_execution_request.return_value = SimpleNamespace(
        logical_execution=SimpleNamespace(run_id=_value("run-1"))
    )
    deps.materialization_service.materialize.return_value = SimpleNamespace(
        record=SimpleNamespace(
            output_id=_value("output-1"), materialization_fingerprint=_value(HEX),
            checksum=_value("b" * 64)
        ),
        disposition=WriteDisposition.CREATED,
    )
    with patch(
        "synapse.private_evals.command_handlers.MaterializationInput",
        side_effect=lambda **values: SimpleNamespace(**values),
    ):
        response = PrivateEvalsCommandHandlers(deps).record_materialized_output(
            _materialization_command()
        )
    assert response.record_reference == "output-1"
    assert resolver.resolve_execution_request.call_count == 1
    assert deps.result_service.create_result.call_count == 0
    assert _principal_call_count(deps) == 1


def test_eval_result_uses_typed_external_response_and_stops_before_scoring() -> None:
    deps = _dependencies()
    deps.evaluation_resolver.resolve_evaluation_request.return_value = SimpleNamespace(
        run_id=_value("run-1")
    )
    deps.result_service.create_result.return_value = SimpleNamespace(
        result=SimpleNamespace(
            result_id=_value("result-1"), result_fingerprint=_value(HEX),
            checksum=_value("b" * 64)
        ),
        disposition=WriteDisposition.IDEMPOTENT_REPLAY,
    )
    with patch(
        "synapse.private_evals.command_handlers.EvalResultCreationInput",
        side_effect=lambda **values: SimpleNamespace(**values),
    ):
        response = PrivateEvalsCommandHandlers(deps).create_eval_result(
            _evaluation_command()
        )
    assert response.outcome is PublicWriteOutcome.IDEMPOTENT_REPLAY
    assert deps.scoring_service.score_run.call_count == 0
    assert _principal_call_count(deps) == 1


def test_scoring_resolves_each_explicit_result_and_does_not_finalize() -> None:
    deps = _dependencies()
    resolver = deps.scoring_resolver
    resolver.resolve_manifest.return_value = SimpleNamespace(
        manifest_id=_value("manifest-1"), suite_id=_value("suite-1"), suite_version="1.0.0"
    )
    resolver.resolve_result.side_effect = [object(), object()]
    deps.scoring_service.score_run.return_value = SimpleNamespace(
        decision=SimpleNamespace(
            decision_id=_value("decision-1"), run_id=_value("run-1"),
            aggregate=SimpleNamespace(verdict=_value("passed")),
            decision_fingerprint=_value(HEX), checksum=_value("b" * 64)
        ),
        disposition=WriteDisposition.CREATED,
    )
    with patch(
        "synapse.private_evals.command_handlers.RunScoringInput",
        side_effect=lambda **values: SimpleNamespace(**values),
    ):
        response = PrivateEvalsCommandHandlers(deps).create_scoring_decision(
            _scoring_command()
        )
    assert response.scoring_verdict == "passed"
    assert [call.args[0] for call in resolver.resolve_result.call_args_list] == [
        "result-1", "result-2"
    ]
    assert deps.finalization_service.finalize.call_count == 0
    assert _principal_call_count(deps) == 1


@pytest.mark.parametrize("recover", [False, True])
def test_finalize_and_recover_are_explicit_isolated_paths(recover: bool) -> None:
    deps = _dependencies()
    resolver = deps.finalization_resolver
    resolver.resolve_run.return_value = SimpleNamespace(run_id=_value("run-1"))
    resolver.resolve_scoring_decision.return_value = SimpleNamespace(verdict=_value("passed"))
    resolver.resolve_finalization.return_value = SimpleNamespace(
        record_reference="finalization-1"
    )
    deps.finalization_service.finalize.return_value = SimpleNamespace(
        finalization=SimpleNamespace(
            record_reference="finalization-1", run_id=_value("run-1"),
            lifecycle_status=_value("completed"), disposition=_value("completed"),
            coverage=_value("complete"), path=_value("scorable")
        ),
        disposition=(
            FinalizationWriteDisposition.RECOVERED
            if recover else FinalizationWriteDisposition.CREATED
        ),
    )
    with patch(
        "synapse.private_evals.command_handlers.RunFinalizationInput",
        side_effect=lambda **values: SimpleNamespace(**values),
    ):
        response = (
            PrivateEvalsCommandHandlers(deps).recover_finalization(
                _finalization_command(recover=True)
            )
            if recover
            else PrivateEvalsCommandHandlers(deps).finalize_run(
                _finalization_command()
            )
        )
    assert response.outcome is (
        PublicWriteOutcome.RECOVERED if recover else PublicWriteOutcome.CREATED
    )
    assert resolver.resolve_finalization.call_count == (1 if recover else 0)
    assert deps.evidence_submission_service.submit.call_count == 0
    assert _principal_call_count(deps) == 1


def test_evidence_submission_reports_only_local_facts() -> None:
    deps = _dependencies()
    deps.evidence_submission_resolver.resolve_finalization.return_value = SimpleNamespace(
        run_id=_value("run-1")
    )
    deps.evidence_submission_service.submit.return_value = SimpleNamespace(
        outcome=EvidenceSubmissionOutcome.NOT_APPLICABLE,
        plan=SimpleNamespace(run_id=_value("run-1"), projection_kinds=()),
        record=None,
    )
    with patch(
        "synapse.private_evals.command_handlers.EvalEvidencePlanningInput",
        side_effect=lambda **values: SimpleNamespace(**values),
    ):
        response = PrivateEvalsCommandHandlers(deps).submit_evidence(_evidence_command())
    assert response.local_outcome is PublicWriteOutcome.NOT_APPLICABLE
    assert "approved" not in repr(response).lower()
    assert "accepted" not in repr(response).lower()
    assert _principal_call_count(deps) == 1


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (ReferencedInputNotFound(), PublicErrorCategory.NOT_FOUND),
        (ReferencedInputMismatch(), PublicErrorCategory.CONFLICT),
        (EvidenceReconciliationRequired("unsafe path"), PublicErrorCategory.RECONCILIATION_REQUIRED),
    ],
)
def test_public_error_translation_is_fixed_and_safe(error: Exception, category) -> None:
    deps = _dependencies()
    deps.manifest_resolver.resolve_manifest.side_effect = error
    with pytest.raises(PrivateEvalBoundaryError) as caught:
        PrivateEvalsCommandHandlers(deps).create_run(
            CreateRunCommand(_context(), "run-1", "manifest-1")
        )
    assert caught.value.envelope.code is category
    assert "path" not in str(caught.value).lower()
    assert not hasattr(caught.value.envelope, "retryable")
    assert _principal_call_count(deps) == 0


def test_unknown_programming_error_is_not_masked() -> None:
    deps = _dependencies()
    deps.run_runtime.start_run.side_effect = RuntimeError("programming defect")
    with pytest.raises(RuntimeError, match="programming defect"):
        PrivateEvalsCommandHandlers(deps).start_run(
            StartRunCommand(_context(), "run-1", 2)
        )


def _summary_dependencies(
    *,
    status: str = "running",
    finalization=None,
    decision=None,
    evidence: EvidenceLocalStateProjection | None = None,
):
    runtime, run_store, analysis_store, evidence_reader = Mock(), Mock(), Mock(), Mock()
    runtime.get_run.return_value = SimpleNamespace(
        run_id=_value("run-1"), suite_id=_value("suite-1"), suite_version="1.0.0",
        status=_value(status), revision=_value(3), manifest_id=_value("manifest-1"),
        finalization_reference=(
            finalization.record_reference if finalization is not None else None
        ),
        accepted_result_count=1, failed_execution_count=0,
    )
    run_store.finalization_exists.return_value = finalization is not None
    run_store.get_finalization_for_run.return_value = finalization
    analysis_store.scoring_decision_exists.return_value = decision is not None
    analysis_store.get_scoring_decision_for_run.return_value = decision
    evidence_reader.get_local_evidence_state.return_value = evidence or EvidenceLocalStateProjection(
        "run-1", None, None, 0, EvidenceLocalState.ABSENT, True, True
    )
    return runtime, run_store, analysis_store, evidence_reader


@pytest.mark.parametrize(
    ("state", "chain_complete", "expected"),
    [
        (EvidenceLocalState.ABSENT, True, "not_required"),
        (EvidenceLocalState.ATTEMPT_STARTED, False, "reconciliation_required"),
        (EvidenceLocalState.RECEIPTS_COMPLETE, False, "reconciliation_required"),
        (EvidenceLocalState.SUBMITTED, False, "reconciliation_required"),
    ],
)
def test_run_summary_projects_orphan_and_incomplete_evidence_facts(
    state: EvidenceLocalState, chain_complete: bool, expected: str
) -> None:
    evidence = EvidenceLocalStateProjection(
        "run-1", None, "submission-1" if state is EvidenceLocalState.SUBMITTED else None,
        1 if state is not EvidenceLocalState.ABSENT else 0,
        state, chain_complete, True,
    )
    dependencies = _summary_dependencies(evidence=evidence)
    response = PrivateEvalsRunSummaryQuery(*dependencies).execute(
        RunSummaryRequest(_query_context(), "run-1")
    )
    assert response.evidence_local_state == state.value
    assert response.reconciliation_state == expected


def test_run_summary_reports_running_with_finalization_without_recovery() -> None:
    finalization = SimpleNamespace(
        record_reference="finalization-1", run_id=_value("run-1"),
        disposition=_value("completed"), coverage=_value("complete"),
        path=_value("scorable"), lifecycle_status=_value("completed"), terminal_causes=(),
    )
    dependencies = _summary_dependencies(status="running", finalization=finalization)
    with patch("synapse.private_evals.query_handler.validate_finalization_record"):
        response = PrivateEvalsRunSummaryQuery(*dependencies).execute(
            RunSummaryRequest(_query_context(), "run-1")
        )
    assert response.run_status == "running"
    assert response.finalization_reference == "finalization-1"
    assert response.reconciliation_state == "reconciliation_required"
    assert dependencies[0].apply_finalization.call_count == 0


@pytest.mark.parametrize(
    "status",
    ["partially_failed", "completed", "failed", "cancelled", "invalid", "policy_denied"],
)
def test_terminal_run_without_finalization_reference_requires_reconciliation(
    status: str,
) -> None:
    dependencies = _summary_dependencies(status=status)
    response = PrivateEvalsRunSummaryQuery(*dependencies).execute(
        RunSummaryRequest(_query_context(), "run-1")
    )
    assert response.finalization_reference is None
    assert response.reconciliation_state == "reconciliation_required"


@pytest.mark.parametrize(
    "evidence",
    [
        EvidenceLocalStateProjection(
            "other-run", None, None, 0, EvidenceLocalState.ABSENT, True, True
        ),
        EvidenceLocalStateProjection(
            "run-1", None, None, 0, EvidenceLocalState.ABSENT, True, False
        ),
    ],
)
def test_query_rejects_cross_run_or_tampered_evidence_projection(evidence) -> None:
    dependencies = _summary_dependencies(evidence=evidence)
    response = PrivateEvalsRunSummaryQuery(*dependencies).execute(
        RunSummaryRequest(_query_context(), "run-1")
    )
    assert response.reconciliation_state == "reconciliation_required"


def test_tampered_finalization_is_reported_without_query_recovery() -> None:
    finalization = SimpleNamespace(
        record_reference="finalization-1", run_id=_value("run-1"),
        disposition=_value("completed"), coverage=_value("complete"),
        path=_value("scorable"), lifecycle_status=_value("completed"), terminal_causes=(),
    )
    dependencies = _summary_dependencies(status="completed", finalization=finalization)
    with patch(
        "synapse.private_evals.query_handler.validate_finalization_record",
        side_effect=RunFinalizationError("tampered checksum"),
    ):
        response = PrivateEvalsRunSummaryQuery(*dependencies).execute(
            RunSummaryRequest(_query_context(), "run-1")
        )
    assert response.finalization_reference == "finalization-1"
    assert response.reconciliation_state == "reconciliation_required"
    assert dependencies[0].apply_finalization.call_count == 0


def test_query_uses_typed_identity_and_unexpected_error_escapes() -> None:
    runtime = Mock()
    runtime.get_run.side_effect = RuntimeError("operational defect")
    with pytest.raises(RuntimeError, match="operational defect"):
        PrivateEvalsRunSummaryQuery(runtime, Mock(), Mock(), Mock()).execute(
            RunSummaryRequest(_query_context(), "run-1")
        )
    assert runtime.get_run.call_args.args == (EvalRunId("run-1"),)
