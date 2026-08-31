from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from synapse.intelligence_boundary.models import DataClassification
from synapse.private_evals.evidence import (
    EvalEvidenceSource,
    EvidenceMetric,
    EvidenceMetricAllowlist,
    EvidenceProjectionKind,
    GovernanceEvidenceBinding,
    ProjectionReadinessStatus,
    ProjectionReasonCode,
)
from synapse.private_evals.evidence_submission import (
    EvalEvidencePlanningInput,
    EvalEvidenceSubmissionPlanner,
    EvidenceProjectionCandidate,
)
from synapse.private_evals.evidence_submission_errors import (
    EvidencePersistenceUnavailable,
    EvidencePlanIncomplete,
    EvidencePlanInvalid,
    EvidenceReconciliationRequired,
    EvidenceSubmissionContentConflict,
    GovernanceReferenceMismatch,
    GovernanceSubmissionUnavailable,
    PartialEvidenceRecoveryConflict,
)
from synapse.private_evals.evidence_submission_models import (
    EvidenceSubmissionOutcome,
    GovernanceEvidenceIdentity,
)
from synapse.private_evals.evidence_submission_service import (
    EvalEvidenceSubmissionService,
)
from synapse.private_evals.run_finalization import EvalRunFinalizationFactory
from synapse.private_evals.run_finalization_models import (
    RetryTerminalityKind,
    TerminalFailureStage,
    TerminalFailureStatus,
)
from synapse.private_evals.states import Verdict
from synapse.private_evals.store_errors import EvalDuplicateRecord, EvalStoreUnavailable
from synapse.private_evals.store_models import IdempotencyKey
from synapse.private_evals.values import ContentChecksum, UtcTimestamp
from synapse.project_governance.models import (
    EvalReference,
    EvidenceRecord,
    RFCImplementationBinding,
)
from test_private_evals_run_finalization import finalization_input, terminal_input

NOW = UtcTimestamp("2026-07-19T12:00:00Z")


def implementation() -> RFCImplementationBinding:
    return RFCImplementationBinding("project-1", "rfc-1", 3, "a" * 64, "plan-1", 2, "b" * 64)


def allowlist() -> EvidenceMetricAllowlist:
    return EvidenceMetricAllowlist(
        "evidence-allowlist-1",
        "1.0.0",
        ("quality.score",),
        "classification-policy-1",
        DataClassification.INTERNAL,
    )


def eval_reference() -> EvalReference:
    return EvalReference("suite-1", "1.0.0", True, "dataset-reference-1", "quality.score", "0.8")


def scorable_planning_input(**changes: object) -> EvalEvidencePlanningInput:
    finalization_source = finalization_input()
    finalization = EvalRunFinalizationFactory().create(finalization_source)
    decision = finalization_source.scoring_decision
    assert decision is not None and finalization.fingerprint is not None
    binding = GovernanceEvidenceBinding(
        implementation(),
        "implementation-binding-1",
        "eval-requirement-1",
        finalization.suite_id.value,
        finalization.suite_version.value,
        EvidenceProjectionKind.EVAL_RESULT,
        "private-evals",
        "14.0.0",
        "correlation-1",
    )
    source = EvalEvidenceSource(
        applicable=True,
        run_id=finalization.run_id,
        suite_id=finalization.suite_id,
        suite_version=finalization.suite_version,
        run_manifest_reference="run-manifest-1",
        run_manifest_fingerprint=finalization.manifest_fingerprint,
        finalization_reference="finalization-1",
        finalization_fingerprint=finalization.fingerprint,
        scoring_decision_reference=decision.decision_id.value,
        scoring_decision_fingerprint=decision.decision_fingerprint,
        verdict=decision.verdict,
        security_snapshot_reference=finalization.security_snapshot_reference,
        security_snapshot_fingerprint=finalization.security_snapshot_fingerprint,
        provenance_references=("provenance-1",),
        reason_codes=(ProjectionReasonCode.EVAL_COMPLETED,),
    )
    candidate = EvidenceProjectionCandidate(
        binding,
        replace(
            eval_reference(),
            eval_id=finalization.suite_id.value,
            version=finalization.suite_version.value,
        ),
        f"private-evals-scoring:{decision.decision_id.value}",
        source,
        allowlist(),
        (EvidenceMetric("quality.score", Decimal("0.9")),),
    )
    planning = EvalEvidencePlanningInput(
        finalization,
        implementation(),
        "implementation-binding-1",
        (candidate,),
        decision,
        IdempotencyKey("evidence-submission-1"),
        "correlation-1",
        "private-evals",
        "14.0.0",
        NOW,
    )
    return replace(planning, **changes)


def terminal_planning_input(
    status: TerminalFailureStatus,
    kind: EvidenceProjectionKind | None,
) -> EvalEvidencePlanningInput:
    finalization_source = terminal_input(
        ((TerminalFailureStage.EXECUTION, status, RetryTerminalityKind.NON_RETRYABLE),)
    )
    finalization = EvalRunFinalizationFactory().create(finalization_source)
    candidates: tuple[EvidenceProjectionCandidate, ...] = ()
    if kind is not None:
        binding = GovernanceEvidenceBinding(
            implementation(),
            "implementation-binding-1",
            "eval-requirement-1",
            finalization.suite_id.value,
            finalization.suite_version.value,
            kind,
            "private-evals",
            "14.0.0",
            "correlation-1",
        )
        common = dict(
            applicable=True,
            run_id=finalization.run_id,
            suite_id=finalization.suite_id,
            suite_version=finalization.suite_version,
            finalization_reference="finalization-1",
            finalization_fingerprint=finalization.fingerprint,
            security_snapshot_reference=finalization.security_snapshot_reference,
            security_snapshot_fingerprint=finalization.security_snapshot_fingerprint,
            provenance_references=("provenance-1",),
        )
        evidence_source = (
            EvalEvidenceSource(
                **common,
                verdict=Verdict.POLICY_DENIED,
                security_decision_reference="security-decision-1",
                security_decision_fingerprint=finalization.reproducibility_fingerprint,
                reason_codes=(ProjectionReasonCode.POLICY_DENIED,),
            )
            if kind is EvidenceProjectionKind.POLICY_BLOCK
            else EvalEvidenceSource(
                **common,
                run_manifest_reference="run-manifest-1",
                run_manifest_fingerprint=finalization.manifest_fingerprint,
                verdict=Verdict.INVALID,
                reason_codes=(ProjectionReasonCode.REPRODUCIBILITY_INVALID,),
            )
        )
        candidates = (
            EvidenceProjectionCandidate(
                binding,
                replace(
                    eval_reference(),
                    eval_id=finalization.suite_id.value,
                    version=finalization.suite_version.value,
                ),
                "security-decision-1"
                if kind is EvidenceProjectionKind.POLICY_BLOCK
                else "run-manifest-1",
                evidence_source,
                allowlist(),
            ),
        )
    return EvalEvidencePlanningInput(
        finalization,
        implementation(),
        "implementation-binding-1",
        candidates,
        None,
        IdempotencyKey("evidence-submission-1"),
        "correlation-1",
        "private-evals",
        "14.0.0",
        NOW,
    )


class EvidenceStoreFake:
    def __init__(self) -> None:
        self.submission = None
        self.attempts = []
        self.receipts = []
        self.unavailable = False

    def evidence_submission_exists(self, run_id):  # noqa: ANN001, ANN201
        if self.unavailable:
            raise EvalStoreUnavailable()
        return self.submission is not None

    def get_evidence_submission_for_run(self, run_id):  # noqa: ANN001, ANN201
        return self.submission

    def get_evidence_submission(self, submission_id):  # noqa: ANN001, ANN201
        return self.submission

    def save_evidence_submission(self, record, *, idempotency_key):  # noqa: ANN001, ANN201
        if self.unavailable:
            raise EvalStoreUnavailable()
        if self.submission is not None:
            raise EvalDuplicateRecord()
        self.submission = record

    def list_evidence_submission_attempts(self, logical_submission_fingerprint):  # noqa: ANN001, ANN201
        if self.unavailable:
            raise EvalStoreUnavailable()
        return tuple(self.attempts)

    def save_evidence_submission_attempt(self, record, *, idempotency_key):  # noqa: ANN001, ANN201
        if self.unavailable:
            raise EvalStoreUnavailable()
        if any(
            item.projection_fingerprint == record.projection_fingerprint for item in self.attempts
        ):
            raise EvalDuplicateRecord()
        self.attempts.append(record)

    def list_evidence_submission_receipts(self, logical_submission_fingerprint):  # noqa: ANN001, ANN201
        if self.unavailable:
            raise EvalStoreUnavailable()
        return tuple(self.receipts)

    def save_evidence_submission_receipt(self, record, *, idempotency_key):  # noqa: ANN001, ANN201
        if self.unavailable:
            raise EvalStoreUnavailable()
        if any(
            item.projection_fingerprint == record.projection_fingerprint for item in self.receipts
        ):
            raise EvalDuplicateRecord()
        self.receipts.append(record)


class GovernanceFake:
    def __init__(self) -> None:
        self.records: dict[str, EvidenceRecord] = {}
        self.calls = 0
        self.unavailable = False
        self.ambiguous = False
        self.fail_on_call: int | None = None

    def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        self.calls += 1
        if self.unavailable:
            raise GovernanceSubmissionUnavailable()
        if self.ambiguous or self.calls == self.fail_on_call:
            raise RuntimeError("provider payload must not escape")
        existing = self.records.get(evidence.evidence_id)
        if existing is not None:
            raise RuntimeError("conflict")
        self.records[evidence.evidence_id] = evidence
        return evidence


def identities(source: EvalEvidencePlanningInput, evidence_prefix: str = "governance-evidence"):
    plan = EvalEvidenceSubmissionPlanner().create(source)
    return tuple(
        GovernanceEvidenceIdentity(
            specification.projection_kind,
            specification.expected_projection_fingerprint,
            f"{evidence_prefix}-{index}",
        )
        for index, specification in enumerate(plan.specifications, start=1)
    )


def multiple_projection_input() -> EvalEvidencePlanningInput:
    combined = EvalRunFinalizationFactory().create(
        terminal_input(
            (
                (
                    TerminalFailureStage.EXECUTION,
                    TerminalFailureStatus.POLICY_DENIED,
                    RetryTerminalityKind.NON_RETRYABLE,
                ),
                (
                    TerminalFailureStage.EXECUTION,
                    TerminalFailureStatus.INVALID,
                    RetryTerminalityKind.NON_RETRYABLE,
                ),
            )
        )
    )
    policy = terminal_planning_input(
        TerminalFailureStatus.POLICY_DENIED, EvidenceProjectionKind.POLICY_BLOCK
    ).candidates[0]
    reproducibility = terminal_planning_input(
        TerminalFailureStatus.INVALID, EvidenceProjectionKind.REPRODUCIBILITY_FAILURE
    ).candidates[0]
    policy = replace(
        policy,
        source=replace(
            policy.source,
            finalization_fingerprint=combined.fingerprint,
            fingerprint=None,
        ),
    )
    reproducibility = replace(
        reproducibility,
        source=replace(
            reproducibility.source,
            finalization_fingerprint=combined.fingerprint,
            fingerprint=None,
        ),
    )
    return replace(
        terminal_planning_input(TerminalFailureStatus.CANCELLED, None),
        finalization=combined,
        candidates=(reproducibility, policy),
    )


def test_planning_selects_scorable_policy_reproducibility_and_not_applicable() -> None:
    planner = EvalEvidenceSubmissionPlanner()
    scorable = planner.assess(scorable_planning_input())
    policy = planner.assess(
        terminal_planning_input(
            TerminalFailureStatus.POLICY_DENIED, EvidenceProjectionKind.POLICY_BLOCK
        )
    )
    reproducibility = planner.assess(
        terminal_planning_input(
            TerminalFailureStatus.INVALID, EvidenceProjectionKind.REPRODUCIBILITY_FAILURE
        )
    )
    not_applicable = planner.assess(terminal_planning_input(TerminalFailureStatus.CANCELLED, None))
    assert scorable.plan and scorable.plan.projection_kinds == (EvidenceProjectionKind.EVAL_RESULT,)
    assert policy.plan and policy.plan.projection_kinds == (EvidenceProjectionKind.POLICY_BLOCK,)
    assert reproducibility.plan and reproducibility.plan.projection_kinds == (
        EvidenceProjectionKind.REPRODUCIBILITY_FAILURE,
    )
    assert not_applicable.status is ProjectionReadinessStatus.NOT_APPLICABLE


def test_planning_detects_incomplete_duplicate_binding_and_source_mismatch() -> None:
    planner = EvalEvidenceSubmissionPlanner()
    source = scorable_planning_input()
    assert (
        planner.assess(replace(source, candidates=())).status
        is ProjectionReadinessStatus.INCOMPLETE
    )
    with pytest.raises(EvidencePlanIncomplete):
        planner.create(replace(source, candidates=()))
    assert (
        planner.assess(replace(source, candidates=source.candidates * 2)).status
        is ProjectionReadinessStatus.INVALID
    )
    changed_binding = replace(
        source.candidates[0].binding, implementation=replace(implementation(), rfc_revision=4)
    )
    assert (
        planner.assess(
            replace(source, candidates=(replace(source.candidates[0], binding=changed_binding),))
        ).status
        is ProjectionReadinessStatus.INVALID
    )
    changed_source = replace(
        source.candidates[0].source,
        security_snapshot_fingerprint=source.finalization.reproducibility_fingerprint,
        fingerprint=None,
    )
    assert (
        planner.assess(
            replace(source, candidates=(replace(source.candidates[0], source=changed_source),))
        ).status
        is ProjectionReadinessStatus.INVALID
    )


def test_projection_construction_is_factory_bound_deterministic_and_fingerprint_checked() -> None:
    source = scorable_planning_input()
    planner = EvalEvidenceSubmissionPlanner()
    plan = planner.create(source)
    projections = planner.construct_projections(source, plan)
    assert projections[0].fingerprint == plan.expected_projection_fingerprints[0]
    object.__setattr__(
        source.finalization,
        "fingerprint",
        source.finalization.reproducibility_fingerprint,
    )
    with pytest.raises(EvidencePlanInvalid):
        planner.create(source)


def test_service_creates_and_equivalent_replay_does_not_resubmit() -> None:
    source = scorable_planning_input()
    store, governance = EvidenceStoreFake(), GovernanceFake()
    service = EvalEvidenceSubmissionService(store, governance)
    first = service.submit(
        source, submission_id="submission-1", governance_identities=identities(source)
    )
    replay = service.submit(
        source, submission_id="submission-1", governance_identities=identities(source)
    )
    assert first.outcome is EvidenceSubmissionOutcome.CREATED
    assert replay.outcome is EvidenceSubmissionOutcome.IDEMPOTENT_REPLAY
    assert governance.calls == 1
    assert store.submission.governance_receipts[0].evidence_id == "governance-evidence-1"


def test_multiple_projections_are_ordered_and_second_projection_recovers() -> None:
    source = multiple_projection_input()
    plan = EvalEvidenceSubmissionPlanner().create(source)
    assert plan.projection_kinds == (
        EvidenceProjectionKind.POLICY_BLOCK,
        EvidenceProjectionKind.REPRODUCIBILITY_FAILURE,
    )
    store, governance = EvidenceStoreFake(), GovernanceFake()
    service = EvalEvidenceSubmissionService(store, governance)
    complete = service.submit(
        source,
        submission_id="submission-1",
        governance_identities=identities(source),
    )
    assert complete.record is not None
    store.submission = None
    store.attempts = store.attempts[:1]
    store.receipts = store.receipts[:1]
    governance.records.pop("governance-evidence-2")
    governance.calls = 0
    result = service.submit(
        source,
        submission_id="submission-1",
        governance_identities=identities(source),
    )
    assert result.outcome is EvidenceSubmissionOutcome.PARTIAL_RECOVERY
    assert len(store.attempts) == 2 and governance.calls == 1
    assert (
        tuple(item.projection_kind for item in result.record.governance_receipts)
        == plan.projection_kinds
    )


def test_partial_attempt_is_recovered_without_duplicate_institutional_evidence() -> None:
    source = scorable_planning_input()
    store, governance = EvidenceStoreFake(), GovernanceFake()
    service = EvalEvidenceSubmissionService(store, governance)
    original_save = store.save_evidence_submission
    store.save_evidence_submission = lambda *args, **kwargs: (_ for _ in ()).throw(
        EvalStoreUnavailable()
    )
    with pytest.raises(EvidencePersistenceUnavailable):
        service.submit(
            source, submission_id="submission-1", governance_identities=identities(source)
        )
    store.save_evidence_submission = original_save
    result = service.submit(
        source, submission_id="submission-1", governance_identities=identities(source)
    )
    assert result.outcome is EvidenceSubmissionOutcome.PARTIAL_RECOVERY
    assert governance.calls == 1


def test_governance_existing_with_all_local_state_lost_requires_reconciliation() -> None:
    source = scorable_planning_input()
    store, governance = EvidenceStoreFake(), GovernanceFake()
    first_store = EvidenceStoreFake()
    EvalEvidenceSubmissionService(first_store, governance).submit(
        source, submission_id="submission-1", governance_identities=identities(source)
    )
    governance.calls = 0
    with pytest.raises(EvidenceReconciliationRequired):
        EvalEvidenceSubmissionService(store, governance).submit(
            source, submission_id="submission-1", governance_identities=identities(source)
        )
    with pytest.raises(EvidenceReconciliationRequired):
        EvalEvidenceSubmissionService(store, governance).submit(
            source, submission_id="submission-1", governance_identities=identities(source)
        )


def test_divergent_identity_existing_record_and_recovery_receipt_conflict() -> None:
    source = scorable_planning_input()
    store, governance = EvidenceStoreFake(), GovernanceFake()
    service = EvalEvidenceSubmissionService(store, governance)
    service.submit(source, submission_id="submission-1", governance_identities=identities(source))
    with pytest.raises(EvidenceSubmissionContentConflict):
        service.submit(
            source,
            submission_id="submission-1",
            governance_identities=identities(source, "other-evidence"),
        )
    store.submission = None
    store.receipts[0] = replace(
        store.receipts[0],
        governance_receipt=replace(
            store.receipts[0].governance_receipt, evidence_id="other-evidence"
        ),
        checksum=None,
    )
    with pytest.raises(PartialEvidenceRecoveryConflict):
        service.submit(
            source, submission_id="submission-1", governance_identities=identities(source)
        )


def test_unavailable_governance_and_store_are_translated_to_fixed_safe_errors() -> None:
    source = scorable_planning_input()
    store, governance = EvidenceStoreFake(), GovernanceFake()
    governance.unavailable = True
    with pytest.raises(GovernanceSubmissionUnavailable) as governance_error:
        EvalEvidenceSubmissionService(store, governance).submit(
            source, submission_id="submission-1", governance_identities=identities(source)
        )
    assert str(governance_error.value) == "Governance Evidence submission is unavailable"
    store = EvidenceStoreFake()
    store.unavailable = True
    with pytest.raises(EvidencePersistenceUnavailable) as store_error:
        EvalEvidenceSubmissionService(store, GovernanceFake()).submit(
            source, submission_id="submission-1", governance_identities=identities(source)
        )
    assert str(store_error.value) == "Evidence submission persistence is unavailable"


def test_not_applicable_does_not_call_governance_or_create_local_record() -> None:
    source = terminal_planning_input(TerminalFailureStatus.CANCELLED, None)
    store, governance = EvidenceStoreFake(), GovernanceFake()
    result = EvalEvidenceSubmissionService(store, governance).submit(
        source, submission_id="submission-1", governance_identities=()
    )
    assert result.outcome is EvidenceSubmissionOutcome.NOT_APPLICABLE
    assert governance.calls == 0 and store.submission is None


def test_records_plans_errors_and_repr_contain_only_safe_references() -> None:
    source = scorable_planning_input()
    plan = EvalEvidenceSubmissionPlanner().create(source)
    rendered = repr(plan)
    assert not any(
        term in rendered.lower() for term in ("prompt", "payload", "output", "token", "provider")
    )
    with pytest.raises(GovernanceReferenceMismatch) as error:
        GovernanceEvidenceIdentity(
            plan.specifications[0].projection_kind,
            plan.specifications[0].expected_projection_fingerprint,
            "Bearer-secret-token",
        )
    assert "token" not in str(error.value).lower()


def test_ambiguous_governance_failure_is_never_automatically_retried() -> None:
    source = scorable_planning_input()
    store, governance = EvidenceStoreFake(), GovernanceFake()
    governance.ambiguous = True
    service = EvalEvidenceSubmissionService(store, governance)
    with pytest.raises(EvidenceReconciliationRequired):
        service.submit(
            source,
            submission_id="submission-1",
            governance_identities=identities(source),
        )
    assert len(store.attempts) == 1 and not store.receipts and governance.calls == 1
    with pytest.raises(EvidenceReconciliationRequired):
        service.submit(
            source,
            submission_id="submission-1",
            governance_identities=identities(source),
        )
    assert governance.calls == 1


def test_final_record_requires_complete_attempt_and_receipt_chain() -> None:
    source = scorable_planning_input()
    store, governance = EvidenceStoreFake(), GovernanceFake()
    service = EvalEvidenceSubmissionService(store, governance)
    service.submit(
        source,
        submission_id="submission-1",
        governance_identities=identities(source),
    )
    store.attempts.clear()
    store.receipts.clear()
    with pytest.raises(PartialEvidenceRecoveryConflict):
        service.submit(
            source,
            submission_id="submission-1",
            governance_identities=identities(source),
        )


@pytest.mark.parametrize("artifact", ["attempt", "receipt", "submission"])
def test_manually_tampered_coordination_records_are_rejected(artifact: str) -> None:
    source = scorable_planning_input()
    store, governance = EvidenceStoreFake(), GovernanceFake()
    service = EvalEvidenceSubmissionService(store, governance)
    service.submit(
        source,
        submission_id="submission-1",
        governance_identities=identities(source),
    )
    target = {
        "attempt": store.attempts[0],
        "receipt": store.receipts[0],
        "submission": store.submission,
    }[artifact]
    object.__setattr__(target, "checksum", ContentChecksum("f" * 64))
    expected = (
        EvidenceSubmissionContentConflict
        if artifact == "submission"
        else PartialEvidenceRecoveryConflict
    )
    with pytest.raises(expected):
        service.submit(
            source,
            submission_id="submission-1",
            governance_identities=identities(source),
        )


def test_plan_and_submission_identity_exclude_operational_fields() -> None:
    source = scorable_planning_input()
    planner = EvalEvidenceSubmissionPlanner()
    first = planner.create(source)
    changed = planner.create(
        replace(
            source,
            idempotency_key=IdempotencyKey("other-idempotency-key"),
            correlation_reference="other-correlation",
            created_at=UtcTimestamp("2026-07-19T13:00:00Z"),
        )
    )
    assert first.plan_fingerprint == changed.plan_fingerprint
    assert first.semantic_fingerprint == changed.semantic_fingerprint


def test_candidate_order_is_canonical_and_future_kinds_are_invalid() -> None:
    source = multiple_projection_input()
    planner = EvalEvidenceSubmissionPlanner()
    first = planner.create(source)
    reordered = planner.create(replace(source, candidates=tuple(reversed(source.candidates))))
    assert first.specifications == reordered.specifications
    assert first.plan_fingerprint == reordered.plan_fingerprint
    scorable = scorable_planning_input()
    future = replace(
        scorable.candidates[0],
        binding=replace(
            scorable.candidates[0].binding,
            projection_kind=EvidenceProjectionKind.REGRESSION_RESULT,
        ),
    )
    assert (
        planner.assess(replace(scorable, candidates=(future,))).status
        is ProjectionReadinessStatus.INVALID
    )


@pytest.mark.parametrize(
    ("stage", "status", "retry_kind"),
    [
        (
            TerminalFailureStage.EXECUTION,
            TerminalFailureStatus.INFRASTRUCTURE_FAILED,
            RetryTerminalityKind.RETRY_EXHAUSTED,
        ),
        (
            TerminalFailureStage.EVALUATION,
            TerminalFailureStatus.INFRASTRUCTURE_FAILED,
            RetryTerminalityKind.NON_RETRYABLE,
        ),
        (
            TerminalFailureStage.EXECUTION,
            TerminalFailureStatus.CANCELLED,
            RetryTerminalityKind.NON_RETRYABLE,
        ),
    ],
)
def test_operational_terminal_failures_are_not_applicable(
    stage: TerminalFailureStage,
    status: TerminalFailureStatus,
    retry_kind: RetryTerminalityKind,
) -> None:
    source = terminal_input(((stage, status, retry_kind),))
    finalization = EvalRunFinalizationFactory().create(source)
    planning = replace(
        terminal_planning_input(TerminalFailureStatus.CANCELLED, None),
        finalization=finalization,
    )
    readiness = EvalEvidenceSubmissionPlanner().assess(planning)
    assert readiness.status is ProjectionReadinessStatus.NOT_APPLICABLE


def test_equivalent_final_record_save_race_replays_without_second_governance_write() -> None:
    class FinalRaceStore(EvidenceStoreFake):
        def save_evidence_submission(self, record, *, idempotency_key):  # noqa: ANN001, ANN201
            self.submission = replace(record)
            raise EvalDuplicateRecord()

    source = scorable_planning_input()
    store, governance = FinalRaceStore(), GovernanceFake()
    result = EvalEvidenceSubmissionService(store, governance).submit(
        source,
        submission_id="submission-1",
        governance_identities=identities(source),
    )
    assert result.outcome is EvidenceSubmissionOutcome.IDEMPOTENT_REPLAY
    assert governance.calls == 1


def test_governance_success_followed_by_receipt_persistence_failure_is_ambiguous() -> None:
    class ReceiptUnavailableStore(EvidenceStoreFake):
        def save_evidence_submission_receipt(self, record, *, idempotency_key):  # noqa: ANN001, ANN201
            raise EvalStoreUnavailable()

    source = scorable_planning_input()
    store, governance = ReceiptUnavailableStore(), GovernanceFake()
    service = EvalEvidenceSubmissionService(store, governance)
    with pytest.raises(EvidencePersistenceUnavailable):
        service.submit(
            source,
            submission_id="submission-1",
            governance_identities=identities(source),
        )
    assert governance.calls == 1 and len(store.attempts) == 1
    with pytest.raises(EvidenceReconciliationRequired):
        service.submit(
            source,
            submission_id="submission-1",
            governance_identities=identities(source),
        )
    assert governance.calls == 1


def test_local_completed_receipt_replays_while_governance_is_unavailable() -> None:
    source = scorable_planning_input()
    store, governance = EvidenceStoreFake(), GovernanceFake()
    service = EvalEvidenceSubmissionService(store, governance)
    service.submit(
        source,
        submission_id="submission-1",
        governance_identities=identities(source),
    )
    governance.unavailable = True
    replay = service.submit(
        source,
        submission_id="submission-1",
        governance_identities=identities(source),
    )
    assert replay.outcome is EvidenceSubmissionOutcome.IDEMPOTENT_REPLAY
    assert governance.calls == 1


def test_governance_returning_a_different_reference_is_a_safe_conflict() -> None:
    class DivergentGovernance(GovernanceFake):
        def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
            return replace(evidence, evidence_id="different-governance-evidence")

    source = scorable_planning_input()
    with pytest.raises(GovernanceReferenceMismatch):
        EvalEvidenceSubmissionService(EvidenceStoreFake(), DivergentGovernance()).submit(
            source,
            submission_id="submission-1",
            governance_identities=identities(source),
        )


def test_divergent_binding_for_same_run_conflicts_before_governance_write() -> None:
    source = scorable_planning_input()
    store, governance = EvidenceStoreFake(), GovernanceFake()
    service = EvalEvidenceSubmissionService(store, governance)
    service.submit(
        source,
        submission_id="submission-1",
        governance_identities=identities(source),
    )
    other_implementation = replace(implementation(), plan_id="other-plan")
    other_candidate = replace(
        source.candidates[0],
        binding=replace(
            source.candidates[0].binding,
            implementation=other_implementation,
        ),
    )
    divergent = replace(
        source,
        implementation=other_implementation,
        candidates=(other_candidate,),
    )
    with pytest.raises(EvidenceSubmissionContentConflict):
        service.submit(
            divergent,
            submission_id="submission-2",
            governance_identities=identities(divergent),
        )
    assert governance.calls == 1


def test_attempt_claim_race_fails_closed_before_governance_write() -> None:
    class AttemptRaceStore(EvidenceStoreFake):
        def save_evidence_submission_attempt(self, record, *, idempotency_key):  # noqa: ANN001, ANN201
            self.attempts.append(record)
            raise EvalDuplicateRecord()

    source = scorable_planning_input()
    governance = GovernanceFake()
    with pytest.raises(EvidenceReconciliationRequired):
        EvalEvidenceSubmissionService(AttemptRaceStore(), governance).submit(
            source,
            submission_id="submission-1",
            governance_identities=identities(source),
        )
    assert governance.calls == 0


def test_plan_fingerprint_and_projection_fingerprint_tampering_are_rejected() -> None:
    source = scorable_planning_input()
    plan = EvalEvidenceSubmissionPlanner().create(source)
    assert plan.plan_fingerprint is not None
    with pytest.raises(EvidencePlanInvalid):
        replace(
            plan,
            plan_fingerprint=source.finalization.reproducibility_fingerprint,
        )
    specification = plan.specifications[0]
    with pytest.raises(EvidencePlanInvalid):
        replace(
            plan,
            specifications=(
                replace(
                    specification,
                    expected_projection_fingerprint=source.finalization.reproducibility_fingerprint,
                ),
            ),
        )
