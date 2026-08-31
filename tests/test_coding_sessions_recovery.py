from dataclasses import replace

from synapse.coding_sessions import (
    CODING_SESSION_RECOVERY_POLICY_VERSION,
    CodingSessionArtifactReference,
    CodingSessionCausalMetadata,
    CodingSessionCausalRevision,
    CodingSessionFactIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionLifecycleState,
    CodingSessionLineage,
    CodingSessionReconciliationAssessment,
    CodingSessionReconciliationOutcome,
    CodingSessionRecoveryArtifactIdentity,
    CodingSessionRecoveryAssessment,
    CodingSessionRecoveryDiagnosticCode,
    CodingSessionRecoveryFact,
    CodingSessionRecoveryFactState,
    CodingSessionRecoveryLifecycleState,
    CodingSessionRecoveryOutcome,
    CodingSessionRecoveryPlan,
    CodingSessionRecoveryReason,
    CodingSessionRecoveryRequest,
    CodingSessionRecoveryStepKind,
    CodingSessionResumeEligibilityResult,
)


def _fingerprint(key: str) -> CodingSessionFingerprint:
    return CodingSessionFingerprint.from_content(key)


def _session() -> CodingSessionIdentity:
    return CodingSessionIdentity.from_stable_key("session-recovery")


def _reconciliation(
    outcome: CodingSessionReconciliationOutcome = CodingSessionReconciliationOutcome.RECOVERY_REQUIRED,
) -> CodingSessionReconciliationAssessment:
    eligibility = CodingSessionResumeEligibilityResult(
        eligible=outcome is CodingSessionReconciliationOutcome.SAFE_TO_RESUME,
        outcome=outcome,
        unknown_dimensions=frozenset(),
        diagnostics=(),
    )
    fingerprint = CodingSessionFingerprint.from_content(((), eligibility))
    return CodingSessionReconciliationAssessment((), eligibility, fingerprint)


def _request(
    *reasons: CodingSessionRecoveryReason,
    outcome: CodingSessionReconciliationOutcome = CodingSessionReconciliationOutcome.RECOVERY_REQUIRED,
    occurrence_metadata: tuple[tuple[str, str], ...] = (),
) -> CodingSessionRecoveryRequest:
    return CodingSessionRecoveryRequest(
        recovery_identity=CodingSessionRecoveryArtifactIdentity.from_stable_key(
            "recovery-one"
        ),
        session_identity=_session(),
        reconciliation=_reconciliation(outcome),
        reasons=reasons,
        expected_lifecycle=CodingSessionLifecycleState.SUSPENDED,
        occurrence_metadata=occurrence_metadata,
    )


def _fact(
    plan: CodingSessionRecoveryPlan,
    index: int,
    *,
    state: CodingSessionRecoveryFactState = CodingSessionRecoveryFactState.SATISFIED,
    previous: CodingSessionRecoveryFact | None = None,
    evidence: bool = True,
    attempt_key: str | None = None,
    external_receipt: CodingSessionArtifactReference | None = None,
) -> CodingSessionRecoveryFact:
    step = plan.steps[index]
    fact_identity = CodingSessionFactIdentity.from_stable_key(f"recovery-fact-{index}")
    causal = CodingSessionCausalMetadata(
        semantic_identity=fact_identity,
        revision=CodingSessionCausalRevision(index + 1),
        lineage=CodingSessionLineage(
            parents=((previous.fingerprint,) if previous is not None else ())
        ),
        occurrence_metadata=(("observed", str(index)),),
    )
    return CodingSessionRecoveryFact(
        fact_identity=fact_identity,
        attempt_identity=CodingSessionFactIdentity.from_stable_key(
            attempt_key or f"recovery-attempt-{index}"
        ),
        session_identity=plan.session_identity,
        recovery_identity=plan.recovery_identity,
        plan_fingerprint=plan.fingerprint,
        step_identity=step.step_identity,
        state=state,
        evidence_fingerprint=(_fingerprint(f"evidence-{index}") if evidence else None),
        external_receipt=external_receipt,
        causal_metadata=causal,
    )


def _project(
    plan: CodingSessionRecoveryPlan,
    facts: tuple[CodingSessionRecoveryFact, ...],
    *,
    prior_attempts: frozenset[CodingSessionFactIdentity] = frozenset(),
) -> CodingSessionRecoveryAssessment:
    return CodingSessionRecoveryAssessment.project(
        plan,
        facts,
        current_reconciliation_fingerprint=plan.reconciliation_fingerprint,
        lifecycle=CodingSessionLifecycleState.SUSPENDED,
        prior_attempts=prior_attempts,
    )


def test_recovery_required_does_not_start_or_execute_recovery() -> None:
    plan = CodingSessionRecoveryPlan.derive(
        _request(CodingSessionRecoveryReason.REPOSITORY_DIVERGENCE)
    )

    assessment = _project(plan, ())

    assert assessment.state is CodingSessionRecoveryLifecycleState.PLANNED
    assert assessment.outcome is CodingSessionRecoveryOutcome.REMAIN_SUSPENDED
    assert plan.steps[0].kind is CodingSessionRecoveryStepKind.REQUEST_REPOSITORY_RECOVERY
    assert plan.steps[-1].kind is CodingSessionRecoveryStepKind.VERIFY_SESSION_RECOVERY


def test_safe_reconciliation_rejects_recovery_plan() -> None:
    plan = CodingSessionRecoveryPlan.derive(
        _request(
            CodingSessionRecoveryReason.CRASH_RESTART_INCOMPLETE,
            outcome=CodingSessionReconciliationOutcome.SAFE_TO_RESUME,
        )
    )

    assert CodingSessionRecoveryDiagnosticCode.RECOVERY_NOT_REQUIRED in {
        item.code for item in plan.diagnostics
    }
    assert not plan.steps


def test_external_step_success_does_not_imply_recovered() -> None:
    plan = CodingSessionRecoveryPlan.derive(
        _request(CodingSessionRecoveryReason.EXECUTION_UNKNOWN)
    )
    external = _fact(plan, 0)

    assessment = _project(plan, (external,))

    assert assessment.state is CodingSessionRecoveryLifecycleState.RECOVERABLE
    assert assessment.outcome is CodingSessionRecoveryOutcome.REMAIN_SUSPENDED
    assert plan.steps[0].kind is CodingSessionRecoveryStepKind.RECONCILE_SANDBOX_EXECUTION


def test_recovered_requires_all_steps_and_factual_verification() -> None:
    plan = CodingSessionRecoveryPlan.derive(
        _request(CodingSessionRecoveryReason.ORPHAN_WORKER)
    )
    first = _fact(plan, 0)
    verification = _fact(plan, 1, previous=first)

    assessment = _project(plan, (verification, first))

    assert assessment.state is CodingSessionRecoveryLifecycleState.RECOVERED
    assert assessment.outcome is CodingSessionRecoveryOutcome.CONTINUATION_ELIGIBLE
    assert assessment.outcome.value != CodingSessionLifecycleState.ACTIVE.value


def test_missing_evidence_preserves_partial_recovery() -> None:
    plan = CodingSessionRecoveryPlan.derive(
        _request(CodingSessionRecoveryReason.CANCELLATION_INCOMPLETE)
    )
    fact = _fact(plan, 0, evidence=False)

    first = _project(plan, (fact,))
    replay = _project(plan, (fact,))

    assert first.state is CodingSessionRecoveryLifecycleState.RECONCILING
    assert replay.fingerprint == first.fingerprint
    assert CodingSessionRecoveryDiagnosticCode.MISSING_RECOVERY_EVIDENCE in {
        item.code for item in first.diagnostics
    }
    assert [item.kind for item in plan.steps[:2]] == [
        CodingSessionRecoveryStepKind.REQUEST_WORKER_CANCELLATION,
        CodingSessionRecoveryStepKind.REQUEST_SANDBOX_CLEANUP,
    ]


def test_stale_plan_and_external_interference_fail_closed() -> None:
    plan = CodingSessionRecoveryPlan.derive(
        _request(CodingSessionRecoveryReason.MUTATION_OUTCOME_UNKNOWN)
    )
    interference = _fact(
        plan, 0, state=CodingSessionRecoveryFactState.EXTERNAL_INTERFERENCE
    )

    assessment = CodingSessionRecoveryAssessment.project(
        plan,
        (interference,),
        current_reconciliation_fingerprint=_fingerprint("new-reconciliation"),
        lifecycle=CodingSessionLifecycleState.SUSPENDED,
    )

    assert assessment.state is CodingSessionRecoveryLifecycleState.MANUAL_INTERVENTION
    assert {
        CodingSessionRecoveryDiagnosticCode.STALE_RECOVERY_PLAN,
        CodingSessionRecoveryDiagnosticCode.EXTERNAL_INTERFERENCE,
    } <= {item.code for item in assessment.diagnostics}


def test_duplicate_attempt_revision_and_lineage_gap_remain_explicit() -> None:
    plan = CodingSessionRecoveryPlan.derive(
        _request(
            CodingSessionRecoveryReason.ORPHAN_WORKER,
            CodingSessionRecoveryReason.EXECUTION_UNKNOWN,
        )
    )
    first = _fact(plan, 0, attempt_key="same-attempt")
    second = _fact(plan, 1, attempt_key="same-attempt")
    second = replace(
        second,
        causal_metadata=replace(
            second.causal_metadata,
            revision=CodingSessionCausalRevision(1),
        ),
    )

    assessment = _project(plan, (first, second))

    assert {
        CodingSessionRecoveryDiagnosticCode.DUPLICATE_RECOVERY_ATTEMPT,
        CodingSessionRecoveryDiagnosticCode.DUPLICATE_CAUSAL_REVISION,
        CodingSessionRecoveryDiagnosticCode.LINEAGE_GAP,
    } <= {item.code for item in assessment.diagnostics}


def test_step_outside_plan_and_missing_prerequisite_are_rejected() -> None:
    plan = CodingSessionRecoveryPlan.derive(
        _request(
            CodingSessionRecoveryReason.ORPHAN_WORKER,
            CodingSessionRecoveryReason.EXECUTION_UNKNOWN,
        )
    )
    second = _fact(plan, 1)
    foreign = replace(
        second,
        step_identity=CodingSessionFactIdentity.from_stable_key("foreign-step"),
    )

    missing = _project(plan, (second,))
    outside = _project(plan, (foreign,))

    assert CodingSessionRecoveryDiagnosticCode.MISSING_PREREQUISITE in {
        item.code for item in missing.diagnostics
    }
    assert CodingSessionRecoveryDiagnosticCode.STEP_OUT_OF_SCOPE in {
        item.code for item in outside.diagnostics
    }


def test_external_receipt_must_match_exact_reference() -> None:
    plan = CodingSessionRecoveryPlan.derive(
        _request(CodingSessionRecoveryReason.REPOSITORY_DIVERGENCE)
    )
    expected = CodingSessionArtifactReference.create(
        producer="repository-runtime",
        version="v1",
        identity="expected",
        fingerprint=_fingerprint("expected"),
    )
    wrong = replace(expected, identity="wrong")
    first_step = replace(plan.steps[0], expected_external_receipt=expected)
    plan = replace(plan, steps=(first_step, *plan.steps[1:]))
    fact = _fact(plan, 0, external_receipt=wrong)

    assessment = _project(plan, (fact,))

    assert CodingSessionRecoveryDiagnosticCode.EXTERNAL_RECEIPT_MISMATCH in {
        item.code for item in assessment.diagnostics
    }


def test_manual_reason_and_terminal_session_remain_manual() -> None:
    plan = CodingSessionRecoveryPlan.derive(
        _request(
            CodingSessionRecoveryReason.CONTRADICTORY_RECEIPT,
            outcome=CodingSessionReconciliationOutcome.MANUAL_INTERVENTION,
        )
    )
    assessment = CodingSessionRecoveryAssessment.project(
        plan,
        (),
        current_reconciliation_fingerprint=plan.reconciliation_fingerprint,
        lifecycle=CodingSessionLifecycleState.TERMINAL,
    )

    assert assessment.state is CodingSessionRecoveryLifecycleState.MANUAL_INTERVENTION
    assert assessment.outcome is CodingSessionRecoveryOutcome.MANUAL_INTERVENTION_REQUIRED


def test_occurrence_metadata_does_not_change_semantic_identity() -> None:
    first = _request(
        CodingSessionRecoveryReason.JOURNAL_CHECKPOINT_LINEAGE_GAP,
        occurrence_metadata=(("observed-at", "100"),),
    )
    second = _request(
        CodingSessionRecoveryReason.JOURNAL_CHECKPOINT_LINEAGE_GAP,
        occurrence_metadata=(("observed-at", "200"),),
    )

    assert first.fingerprint == second.fingerprint
    assert CodingSessionRecoveryPlan.derive(first).fingerprint == CodingSessionRecoveryPlan.derive(
        second
    ).fingerprint
    assert first.policy_version == CODING_SESSION_RECOVERY_POLICY_VERSION
