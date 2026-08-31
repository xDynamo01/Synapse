from __future__ import annotations

from dataclasses import replace

from synapse.coding_sessions import (
    CodingSessionActorReference,
    CodingSessionBinding,
    CodingSessionBindingScope,
    CodingSessionCancellationState,
    CodingSessionCausalMetadata,
    CodingSessionCausalRevision,
    CodingSessionContract,
    CodingSessionContractAssessment,
    CodingSessionCoordinationState,
    CodingSessionCorrelationReference,
    CodingSessionDeploymentCandidateState,
    CodingSessionEvaluationState,
    CodingSessionExecutionBindingState,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionLifecycleState,
    CodingSessionLineage,
    CodingSessionProjectReference,
    CodingSessionPurpose,
    CodingSessionPurposeReference,
    CodingSessionRecoveryState,
    CodingSessionRepositoryCorrespondenceState,
    CodingSessionStateDimension,
    CodingSessionStateProjection,
    CodingSessionTaskReference,
    CodingSessionTerminalOutcome,
    CodingSessionTransitionAssessment,
    CodingSessionTransitionDiagnosticCode,
    CodingSessionTransitionReason,
    CodingSessionTransitionRequest,
    CodingSessionWorkerBindingState,
)


def _session(key: str = "session:one") -> CodingSessionIdentity:
    return CodingSessionIdentity.from_stable_key(key)


def _evidence(label: str = "external:fact") -> tuple[CodingSessionFingerprint, ...]:
    return (CodingSessionFingerprint.from_content(label),)


def _contract() -> tuple[CodingSessionContract, CodingSessionContractAssessment]:
    identity = _session()
    project = CodingSessionProjectReference("project:one")
    contract = CodingSessionContract(
        session_identity=identity,
        actor=CodingSessionActorReference("actor:one"),
        project=project,
        purpose=CodingSessionPurpose(
            CodingSessionTaskReference("task:one"),
            CodingSessionPurposeReference("purpose:implement"),
        ),
        correlation=CodingSessionCorrelationReference("correlation:one"),
        binding=CodingSessionBinding(
            session_identity=identity,
            project=project,
            scope=CodingSessionBindingScope.NONE,
        ),
        requested_capabilities=(),
        completion_requirements=(),
        policy_version="policy-v1",
        causal_metadata=CodingSessionCausalMetadata(
            identity,
            CodingSessionCausalRevision(1),
            CodingSessionLineage(),
        ),
    )
    return contract, CodingSessionContractAssessment.assess(contract)


def _request(
    projection: CodingSessionStateProjection,
    dimension: CodingSessionStateDimension,
    next_state,
    reason: CodingSessionTransitionReason,
    *,
    evidence: tuple[CodingSessionFingerprint, ...] = (),
    occurrence: tuple[tuple[str, str], ...] = (),
) -> CodingSessionTransitionRequest:
    field = {
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
    }[dimension]
    return CodingSessionTransitionRequest(
        session_identity=projection.session_identity,
        dimension=dimension,
        expected_previous_state=getattr(projection, field),
        next_state=next_state,
        reason=reason,
        expected_causal_revision=projection.causal_revision,
        evidence=evidence,
        occurrence_metadata=occurrence,
    )


def _advance(
    projection: CodingSessionStateProjection,
    dimension: CodingSessionStateDimension,
    next_state,
    reason: CodingSessionTransitionReason,
    *,
    evidence: tuple[CodingSessionFingerprint, ...] = (),
    contract: CodingSessionContract | None = None,
    contract_assessment: CodingSessionContractAssessment | None = None,
):
    assessment = CodingSessionTransitionAssessment.assess(
        _request(projection, dimension, next_state, reason, evidence=evidence),
        projection,
        contract=contract,
        contract_assessment=contract_assessment,
    )
    assert assessment.accepted
    assert assessment.fact is not None
    updated = CodingSessionStateProjection.replay(
        projection.session_identity,
        (assessment.fact,),
    ) if projection.causal_revision == 0 else None
    return assessment.fact, updated


def _replay(facts) -> CodingSessionStateProjection:
    return CodingSessionStateProjection.replay(_session(), tuple(facts))


def _assess(
    projection: CodingSessionStateProjection,
    dimension: CodingSessionStateDimension,
    next_state,
    reason: CodingSessionTransitionReason,
    *,
    evidence: tuple[CodingSessionFingerprint, ...] = (),
) -> CodingSessionTransitionAssessment:
    return CodingSessionTransitionAssessment.assess(
        _request(projection, dimension, next_state, reason, evidence=evidence), projection
    )


def test_dimensions_are_independent_and_absent_evidence_stays_unknown_or_absent() -> None:
    projection = CodingSessionStateProjection(_session())
    assert projection.lifecycle is CodingSessionLifecycleState.UNKNOWN
    assert projection.terminal_outcome is CodingSessionTerminalOutcome.UNKNOWN
    assert projection.coordination is CodingSessionCoordinationState.UNKNOWN
    assert projection.repository_correspondence is CodingSessionRepositoryCorrespondenceState.UNBOUND
    assert projection.worker_binding is CodingSessionWorkerBindingState.UNBOUND
    assert projection.execution_binding is CodingSessionExecutionBindingState.UNBOUND
    assert projection.cancellation is CodingSessionCancellationState.NOT_REQUESTED
    assert projection.recovery is CodingSessionRecoveryState.UNKNOWN
    assert projection.evaluation is CodingSessionEvaluationState.UNKNOWN
    assert projection.deployment_candidate is CodingSessionDeploymentCandidateState.ABSENT


def test_valid_contract_does_not_make_session_active() -> None:
    contract, assessment = _contract()
    projection = CodingSessionStateProjection(contract.session_identity)
    assert assessment.valid and assessment.complete
    assert projection.lifecycle is CodingSessionLifecycleState.UNKNOWN


def test_planned_to_prepared_requires_contract_but_prepared_does_not_imply_active() -> None:
    contract, contract_assessment = _contract()
    initial = CodingSessionStateProjection(_session())
    planned = CodingSessionTransitionAssessment.assess(
        _request(
            initial,
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.PLANNED,
            CodingSessionTransitionReason.SESSION_PLANNED,
        ),
        initial,
    ).fact
    assert planned is not None
    planned_projection = _replay((planned,))
    prepared_assessment = CodingSessionTransitionAssessment.assess(
        _request(
            planned_projection,
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.PREPARED,
            CodingSessionTransitionReason.CONTRACT_ACCEPTED,
        ),
        planned_projection,
        contract=contract,
        contract_assessment=contract_assessment,
    )
    assert prepared_assessment.accepted
    assert prepared_assessment.fact is not None
    assert contract.fingerprint in prepared_assessment.fact.causal_metadata.lineage.references
    projection = _replay((planned, prepared_assessment.fact))
    assert projection.lifecycle is CodingSessionLifecycleState.PREPARED
    active = _assess(
        projection,
        CodingSessionStateDimension.LIFECYCLE,
        CodingSessionLifecycleState.ACTIVE,
        CodingSessionTransitionReason.ACTIVATION_CONFIRMED,
    )
    assert not active.accepted
    assert CodingSessionTransitionDiagnosticCode.INSUFFICIENT_EVIDENCE in {
        item.code for item in active.diagnostics
    }


def test_process_worker_and_eval_success_do_not_complete_session() -> None:
    projection = CodingSessionStateProjection(_session())
    requests = (
        (
            CodingSessionStateDimension.EXECUTION_BINDING,
            CodingSessionTerminalOutcome.COMPLETED,
            CodingSessionTransitionReason.PROCESS_EXITED,
        ),
        (
            CodingSessionStateDimension.WORKER_BINDING,
            CodingSessionTerminalOutcome.COMPLETED,
            CodingSessionTransitionReason.WORKER_SUCCEEDED,
        ),
        (
            CodingSessionStateDimension.EVALUATION,
            CodingSessionTerminalOutcome.COMPLETED,
            CodingSessionTransitionReason.EVALUATION_ACCEPTED,
        ),
    )
    for dimension, next_state, reason in requests:
        assessment = _assess(projection, dimension, next_state, reason, evidence=_evidence())
        assert not assessment.accepted
        assert CodingSessionTransitionDiagnosticCode.DIMENSION_STATE_MISMATCH in {
            item.code for item in assessment.diagnostics
        }
    assert projection.terminal_outcome is CodingSessionTerminalOutcome.UNKNOWN


def test_completed_outcome_is_reserved_for_future_completion_assessment() -> None:
    assessment = _assess(
        CodingSessionStateProjection(_session()),
        CodingSessionStateDimension.TERMINAL_OUTCOME,
        CodingSessionTerminalOutcome.COMPLETED,
        CodingSessionTransitionReason.EXTERNAL_FACT_OBSERVED,
        evidence=_evidence(),
    )
    assert not assessment.accepted
    assert CodingSessionTransitionDiagnosticCode.COMPLETION_ASSESSMENT_UNAVAILABLE in {
        item.code for item in assessment.diagnostics
    }


def test_cancellation_requested_does_not_imply_cancelled() -> None:
    initial = CodingSessionStateProjection(_session())
    request = _request(
        initial,
        CodingSessionStateDimension.CANCELLATION,
        CodingSessionCancellationState.REQUESTED,
        CodingSessionTransitionReason.CANCELLATION_REQUESTED,
    )
    fact = CodingSessionTransitionAssessment.assess(request, initial).fact
    assert fact is not None
    projection = _replay((fact,))
    assert projection.cancellation is CodingSessionCancellationState.REQUESTED
    assert projection.terminal_outcome is CodingSessionTerminalOutcome.UNKNOWN
    cancelled = _assess(
        projection,
        CodingSessionStateDimension.TERMINAL_OUTCOME,
        CodingSessionTerminalOutcome.CANCELLED,
        CodingSessionTransitionReason.EXTERNAL_FACT_OBSERVED,
        evidence=_evidence(),
    )
    assert not cancelled.accepted


def test_recovery_required_does_not_start_recovery() -> None:
    initial = CodingSessionStateProjection(_session())
    fact = CodingSessionTransitionAssessment.assess(
        _request(
            initial,
            CodingSessionStateDimension.RECOVERY,
            CodingSessionRecoveryState.REQUIRED,
            CodingSessionTransitionReason.RECOVERY_REQUIRED,
            evidence=_evidence(),
        ),
        initial,
    ).fact
    assert fact is not None
    projection = _replay((fact,))
    assert projection.recovery is CodingSessionRecoveryState.REQUIRED


def test_mutation_applied_cannot_claim_repository_corresponding() -> None:
    assessment = _assess(
        CodingSessionStateProjection(_session()),
        CodingSessionStateDimension.REPOSITORY_CORRESPONDENCE,
        CodingSessionRepositoryCorrespondenceState.CORRESPONDING,
        CodingSessionTransitionReason.MUTATION_APPLIED,
        evidence=_evidence(),
    )
    assert not assessment.accepted
    assert CodingSessionTransitionDiagnosticCode.INSUFFICIENT_EVIDENCE in {
        item.code for item in assessment.diagnostics
    }


def test_restart_never_creates_transition() -> None:
    assessment = _assess(
        CodingSessionStateProjection(_session()),
        CodingSessionStateDimension.LIFECYCLE,
        CodingSessionLifecycleState.PLANNED,
        CodingSessionTransitionReason.RESTART_REPLAYED,
    )
    assert not assessment.accepted
    assert CodingSessionTransitionDiagnosticCode.RESTART_CANNOT_TRANSITION in {
        item.code for item in assessment.diagnostics
    }


def test_terminal_lifecycle_cannot_reopen_on_late_fact() -> None:
    initial = CodingSessionStateProjection(_session())
    planned = CodingSessionTransitionAssessment.assess(
        _request(
            initial,
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.PLANNED,
            CodingSessionTransitionReason.SESSION_PLANNED,
        ),
        initial,
    ).fact
    assert planned is not None
    planned_projection = _replay((planned,))
    terminal = CodingSessionTransitionAssessment.assess(
        _request(
            planned_projection,
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.TERMINAL,
            CodingSessionTransitionReason.TERMINATION_CONFIRMED,
            evidence=_evidence(),
        ),
        planned_projection,
    ).fact
    assert terminal is not None
    terminal_projection = _replay((planned, terminal))
    late = _assess(
        terminal_projection,
        CodingSessionStateDimension.LIFECYCLE,
        CodingSessionLifecycleState.ACTIVE,
        CodingSessionTransitionReason.ACTIVATION_CONFIRMED,
        evidence=_evidence(),
    )
    assert not late.accepted
    assert CodingSessionTransitionDiagnosticCode.TERMINAL_SESSION_REOPEN in {
        item.code for item in late.diagnostics
    }


def test_projection_detects_duplicate_revision_lineage_gap_and_other_session() -> None:
    initial = CodingSessionStateProjection(_session())
    fact = CodingSessionTransitionAssessment.assess(
        _request(
            initial,
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.PLANNED,
            CodingSessionTransitionReason.SESSION_PLANNED,
        ),
        initial,
    ).fact
    assert fact is not None
    duplicate = _replay((fact, fact))
    assert CodingSessionTransitionDiagnosticCode.DUPLICATE_CAUSAL_REVISION in {
        item.code for item in duplicate.diagnostics
    }
    gap = replace(
        fact,
        causal_metadata=replace(
            fact.causal_metadata,
            revision=CodingSessionCausalRevision(2),
        ),
    )
    gap_projection = _replay((gap,))
    assert CodingSessionTransitionDiagnosticCode.CAUSAL_REVISION_GAP in {
        item.code for item in gap_projection.diagnostics
    }
    foreign = replace(fact, session_identity=_session("session:other"))
    foreign_projection = _replay((foreign,))
    assert CodingSessionTransitionDiagnosticCode.SESSION_IDENTITY_MISMATCH in {
        item.code for item in foreign_projection.diagnostics
    }


def test_projection_detects_parent_lineage_gap() -> None:
    initial = CodingSessionStateProjection(_session())
    fact = CodingSessionTransitionAssessment.assess(
        _request(
            initial,
            CodingSessionStateDimension.COORDINATION,
            CodingSessionCoordinationState.UNOWNED,
            CodingSessionTransitionReason.COORDINATION_OBSERVED,
            evidence=_evidence(),
        ),
        initial,
    ).fact
    assert fact is not None
    bad_parent = CodingSessionFingerprint.from_content("wrong-parent")
    broken = replace(
        fact,
        causal_metadata=replace(
            fact.causal_metadata,
            lineage=CodingSessionLineage(parents=(bad_parent,), references=()),
        ),
    )
    projection = _replay((broken,))
    assert CodingSessionTransitionDiagnosticCode.LINEAGE_GAP in {
        item.code for item in projection.diagnostics
    }


def test_projection_rejects_fact_whose_reason_does_not_match_dimension() -> None:
    initial = CodingSessionStateProjection(_session())
    fact = CodingSessionTransitionAssessment.assess(
        _request(
            initial,
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.PLANNED,
            CodingSessionTransitionReason.SESSION_PLANNED,
        ),
        initial,
    ).fact
    assert fact is not None
    forged = replace(fact, reason=CodingSessionTransitionReason.PROCESS_EXITED)
    projection = _replay((forged,))
    assert CodingSessionTransitionDiagnosticCode.INSUFFICIENT_EVIDENCE in {
        item.code for item in projection.diagnostics
    }


def test_same_causal_facts_in_any_input_order_produce_same_projection() -> None:
    initial = CodingSessionStateProjection(_session())
    first = CodingSessionTransitionAssessment.assess(
        _request(
            initial,
            CodingSessionStateDimension.LIFECYCLE,
            CodingSessionLifecycleState.PLANNED,
            CodingSessionTransitionReason.SESSION_PLANNED,
        ),
        initial,
    ).fact
    assert first is not None
    after_first = _replay((first,))
    second = CodingSessionTransitionAssessment.assess(
        _request(
            after_first,
            CodingSessionStateDimension.COORDINATION,
            CodingSessionCoordinationState.UNOWNED,
            CodingSessionTransitionReason.COORDINATION_OBSERVED,
            evidence=_evidence(),
        ),
        after_first,
    ).fact
    assert second is not None
    assert _replay((first, second)).fingerprint == _replay((second, first)).fingerprint


def test_occurrence_metadata_does_not_change_semantic_fact_identity() -> None:
    projection = CodingSessionStateProjection(_session())
    first_request = _request(
        projection,
        CodingSessionStateDimension.LIFECYCLE,
        CodingSessionLifecycleState.PLANNED,
        CodingSessionTransitionReason.SESSION_PLANNED,
        occurrence=(("observed-at", "100"),),
    )
    second_request = replace(first_request, occurrence_metadata=(("observed-at", "200"),))
    first = CodingSessionTransitionAssessment.assess(first_request, projection).fact
    second = CodingSessionTransitionAssessment.assess(second_request, projection).fact
    assert first is not None and second is not None
    assert first_request.fingerprint == second_request.fingerprint
    assert first.fact_identity == second.fact_identity
    assert first.fingerprint == second.fingerprint


def test_deployment_candidate_produced_does_not_claim_publication() -> None:
    assert "published" not in {state.value for state in CodingSessionDeploymentCandidateState}
