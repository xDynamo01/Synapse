from __future__ import annotations

from dataclasses import replace

from synapse.coding_sessions import (
    CodingSessionActorReference,
    CodingSessionArtifactReference,
    CodingSessionBinding,
    CodingSessionBindingScope,
    CodingSessionCancellationAcknowledgement,
    CodingSessionCancellationAssessment,
    CodingSessionCancellationAssessmentState,
    CodingSessionCancellationEvidence,
    CodingSessionCancellationEvidenceKind,
    CodingSessionCancellationPolicy,
    CodingSessionCancellationRace,
    CodingSessionCancellationRequest,
    CodingSessionCancellationState,
    CodingSessionCausalMetadata,
    CodingSessionCausalRevision,
    CodingSessionCheckpointAssessment,
    CodingSessionCheckpointComponent,
    CodingSessionCheckpointIdentity,
    CodingSessionCheckpointManifest,
    CodingSessionCheckpointPolicy,
    CodingSessionCheckpointRequest,
    CodingSessionContract,
    CodingSessionControlDiagnosticCode,
    CodingSessionCoordinationState,
    CodingSessionCorrelationReference,
    CodingSessionExternalReceiptIdentity,
    CodingSessionFactIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionJournalAssessment,
    CodingSessionJournalEntry,
    CodingSessionJournalEntryCategory,
    CodingSessionLifecycleState,
    CodingSessionLineage,
    CodingSessionPauseAssessment,
    CodingSessionPauseRequest,
    CodingSessionProjectReference,
    CodingSessionPurpose,
    CodingSessionPurposeReference,
    CodingSessionRecoveryState,
    CodingSessionRepositoryCorrespondenceState,
    CodingSessionRepositoryReference,
    CodingSessionResumeAssessment,
    CodingSessionResumeRequest,
    CodingSessionStateProjection,
    CodingSessionTaskReference,
)


def _contract() -> CodingSessionContract:
    session = CodingSessionIdentity.from_stable_key("session:one")
    project = CodingSessionProjectReference("project:one")
    purpose = CodingSessionPurpose(
        CodingSessionTaskReference("task:one"),
        CodingSessionPurposeReference("purpose:one"),
    )
    repository = CodingSessionRepositoryReference.create(
        "repository-runtime", "v1", "repository:one"
    )
    return CodingSessionContract(
        session,
        CodingSessionActorReference("actor:one"),
        project,
        purpose,
        CodingSessionCorrelationReference("correlation:one"),
        CodingSessionBinding(
            session,
            project,
            CodingSessionBindingScope.REPOSITORY,
            repository=repository,
        ),
        (),
        (),
        "policy-v1",
        CodingSessionCausalMetadata(
            session, CodingSessionCausalRevision(1), CodingSessionLineage()
        ),
    )


def _lifecycle(state: CodingSessionLifecycleState) -> CodingSessionStateProjection:
    return CodingSessionStateProjection(
        _contract().session_identity,
        lifecycle=state,
        repository_correspondence=CodingSessionRepositoryCorrespondenceState.CORRESPONDING,
        causal_revision=4,
    )


def _journal_checkpoint():
    session = _contract().session_identity
    semantic = CodingSessionFingerprint.from_content("contract")
    entry = CodingSessionJournalEntry.create(
        session_identity=session,
        category=CodingSessionJournalEntryCategory.CONTRACT_BINDING,
        semantic_identity="contract:one",
        semantic_fingerprint=semantic,
        causal_revision=1,
    )
    journal = CodingSessionJournalAssessment.assess_stream(session, (entry,))
    manifest = CodingSessionCheckpointManifest(
        session,
        journal.stream.fingerprint,
        1,
        contract_fingerprint=semantic,
        lifecycle_fingerprint=CodingSessionFingerprint.from_content("lifecycle"),
    )
    request = CodingSessionCheckpointRequest(
        CodingSessionCheckpointIdentity.from_stable_key("checkpoint:one"),
        session,
        manifest,
        1,
    )
    checkpoint = CodingSessionCheckpointAssessment.assess(
        request,
        journal,
        CodingSessionCheckpointPolicy(
            frozenset(
                {
                    CodingSessionCheckpointComponent.CONTRACT,
                    CodingSessionCheckpointComponent.LIFECYCLE,
                }
            )
        ),
    )
    return journal, checkpoint


def _resume_request(checkpoint: CodingSessionCheckpointAssessment) -> CodingSessionResumeRequest:
    return CodingSessionResumeRequest(
        session_identity=_contract().session_identity,
        expected_causal_revision=4,
        checkpoint_identity=checkpoint.fact.checkpoint_identity.value,
        checkpoint_fingerprint=checkpoint.fact.fingerprint,
        checkpoint_revision=checkpoint.fact.manifest.through_revision,
        persistence_evidence=CodingSessionFingerprint.from_content("persisted"),
    )


def test_pause_is_lifecycle_decision_without_external_effects() -> None:
    lifecycle = _lifecycle(CodingSessionLifecycleState.ACTIVE)
    assessment = CodingSessionPauseAssessment.assess(
        CodingSessionPauseRequest(
            _contract().session_identity,
            4,
            CodingSessionFingerprint.from_content("pause-reason"),
        ),
        lifecycle,
        _contract(),
    )
    assert assessment.eligible and assessment.lifecycle_fact is not None
    assert lifecycle.lifecycle is CodingSessionLifecycleState.ACTIVE
    assert not hasattr(assessment, "process_paused")
    assert not hasattr(assessment, "worker_paused")
    assert not hasattr(assessment, "recovery_executed")


def test_pause_rejects_terminal_conflicted_or_wrong_revision() -> None:
    request = CodingSessionPauseRequest(
        _contract().session_identity,
        3,
        CodingSessionFingerprint.from_content("reason"),
    )
    lifecycle = replace(
        _lifecycle(CodingSessionLifecycleState.TERMINAL),
        coordination=CodingSessionCoordinationState.CONFLICTED,
    )
    assessment = CodingSessionPauseAssessment.assess(request, lifecycle, _contract())
    codes = {item.code for item in assessment.diagnostics}
    assert CodingSessionControlDiagnosticCode.LIFECYCLE_INCOMPATIBLE in codes
    assert CodingSessionControlDiagnosticCode.CAUSAL_REVISION_MISMATCH in codes
    assert CodingSessionControlDiagnosticCode.MANUAL_INTERVENTION_REQUIRED in codes


def test_resume_requires_exact_checkpoint_persistence_and_revalidation() -> None:
    journal, checkpoint = _journal_checkpoint()
    lifecycle = _lifecycle(CodingSessionLifecycleState.SUSPENDED)
    assessment = CodingSessionResumeAssessment.assess(
        _resume_request(checkpoint), lifecycle, checkpoint, journal, None
    )
    assert assessment.eligible and assessment.lifecycle_fact is not None
    assert lifecycle.lifecycle is CodingSessionLifecycleState.SUSPENDED
    missing_persistence = CodingSessionResumeAssessment.assess(
        replace(_resume_request(checkpoint), persistence_evidence=None),
        lifecycle,
        checkpoint,
        journal,
        None,
    )
    assert CodingSessionControlDiagnosticCode.PERSISTENCE_EVIDENCE_MISSING in {
        item.code for item in missing_persistence.diagnostics
    }


def test_resume_is_blocked_by_stale_repository_recovery_cancellation_and_duplicate() -> None:
    journal, checkpoint = _journal_checkpoint()
    request = _resume_request(checkpoint)
    lifecycle = replace(
        _lifecycle(CodingSessionLifecycleState.SUSPENDED),
        repository_correspondence=CodingSessionRepositoryCorrespondenceState.STALE,
        recovery=CodingSessionRecoveryState.REQUIRED,
        cancellation=CodingSessionCancellationState.REQUESTED,
    )
    assessment = CodingSessionResumeAssessment.assess(
        request,
        lifecycle,
        checkpoint,
        journal,
        None,
        frozenset({request.fingerprint}),
    )
    codes = {item.code for item in assessment.diagnostics}
    assert CodingSessionControlDiagnosticCode.REPOSITORY_INELIGIBLE in codes
    assert CodingSessionControlDiagnosticCode.RECOVERY_REQUIRED in codes
    assert CodingSessionControlDiagnosticCode.CANCELLATION_PENDING in codes
    assert CodingSessionControlDiagnosticCode.DUPLICATE_RESUME in codes


def test_checkpoint_complete_alone_never_implies_resume() -> None:
    journal, checkpoint = _journal_checkpoint()
    assessment = CodingSessionResumeAssessment.assess(
        _resume_request(checkpoint),
        _lifecycle(CodingSessionLifecycleState.ACTIVE),
        checkpoint,
        journal,
        None,
    )
    assert not assessment.eligible
    assert CodingSessionControlDiagnosticCode.LIFECYCLE_INCOMPATIBLE in {
        item.code for item in assessment.diagnostics
    }


def _cancellation_request(occurrence=()) -> CodingSessionCancellationRequest:
    contract = _contract()
    identity = CodingSessionFactIdentity.from_stable_key("cancel:one")
    return CodingSessionCancellationRequest(
        identity,
        contract.session_identity,
        contract.actor,
        contract.purpose,
        contract.correlation,
        None,
        (),
        "coding-session-control-policy-v1",
        CodingSessionCausalMetadata(
            identity,
            CodingSessionCausalRevision(1),
            CodingSessionLineage(),
            occurrence,
        ),
    )


def _external(request, revision, kind=None, accepted=True, verified=True):
    identity = CodingSessionExternalReceiptIdentity.from_stable_key(
        f"cancel-external:{revision}"
    )
    fingerprint = CodingSessionFingerprint.from_content(f"external:{revision}")
    reference = CodingSessionArtifactReference.create(
        "external", "v1", f"artifact:{revision}", fingerprint
    )
    causal = CodingSessionCausalMetadata(
        identity,
        CodingSessionCausalRevision(revision),
        CodingSessionLineage(references=(request.fingerprint,)),
    )
    common = (
        request.request_identity,
        request.fingerprint,
        request.session_identity,
        request.actor,
        request.purpose,
        request.correlation,
    )
    if kind is None:
        return CodingSessionCancellationAcknowledgement(
            identity, *common, request.cancellation_intent, reference, accepted, causal
        )
    return CodingSessionCancellationEvidence(
        identity, *common, kind, reference, verified, causal
    )


def _cancel_policy() -> CodingSessionCancellationPolicy:
    return CodingSessionCancellationPolicy(
        frozenset(
            {
                CodingSessionCancellationEvidenceKind.PROCESS_EXIT,
                CodingSessionCancellationEvidenceKind.WORKER_TERMINATION,
                CodingSessionCancellationEvidenceKind.SANDBOX_CLEANUP,
            }
        )
    )


def test_cancellation_request_ack_and_process_exit_do_not_imply_cancelled() -> None:
    request = _cancellation_request()
    lifecycle = _lifecycle(CodingSessionLifecycleState.ACTIVE)
    requested = CodingSessionCancellationAssessment.assess(
        (request,), (), (), lifecycle, _cancel_policy()
    )
    acknowledged = CodingSessionCancellationAssessment.assess(
        (request,), (_external(request, 2),), (), lifecycle, _cancel_policy()
    )
    process_only = CodingSessionCancellationAssessment.assess(
        (request,), (), (_external(request, 2, CodingSessionCancellationEvidenceKind.PROCESS_EXIT),), lifecycle, _cancel_policy()
    )
    assert requested.state is CodingSessionCancellationAssessmentState.REQUESTED
    assert acknowledged.state is CodingSessionCancellationAssessmentState.ACKNOWLEDGED
    assert process_only.state is CodingSessionCancellationAssessmentState.TERMINATION_UNVERIFIED
    assert not requested.cancelled_outcome_eligible
    assert not acknowledged.cancelled_outcome_eligible
    assert not process_only.cancelled_outcome_eligible


def test_cancelled_outcome_requires_all_reconciled_effects() -> None:
    request = _cancellation_request()
    ack = _external(request, 2)
    evidence = tuple(
        _external(request, revision, kind)
        for revision, kind in enumerate(
            (
                CodingSessionCancellationEvidenceKind.PROCESS_EXIT,
                CodingSessionCancellationEvidenceKind.WORKER_TERMINATION,
                CodingSessionCancellationEvidenceKind.SANDBOX_CLEANUP,
            ),
            start=3,
        )
    )
    assessment = CodingSessionCancellationAssessment.assess(
        (request,), (ack,), evidence, _lifecycle(CodingSessionLifecycleState.ACTIVE), _cancel_policy()
    )
    assert assessment.state is CodingSessionCancellationAssessmentState.TERMINATED
    assert assessment.cancelled_outcome_eligible
    assert _lifecycle(CodingSessionLifecycleState.ACTIVE).lifecycle is CodingSessionLifecycleState.ACTIVE


def test_duplicate_cancel_pause_race_and_late_fact_remain_explicit() -> None:
    request = _cancellation_request()
    duplicate = replace(
        request,
        request_identity=CodingSessionFactIdentity.from_stable_key("cancel:duplicate"),
    )
    suspended = CodingSessionCancellationAssessment.assess(
        (request, duplicate), (), (), _lifecycle(CodingSessionLifecycleState.SUSPENDED), _cancel_policy()
    )
    late = CodingSessionCancellationAssessment.assess(
        (request,), (), (), _lifecycle(CodingSessionLifecycleState.TERMINAL), _cancel_policy()
    )
    assert CodingSessionControlDiagnosticCode.DUPLICATE_CANCELLATION_REQUEST in {
        item.code for item in suspended.diagnostics
    }
    assert CodingSessionCancellationRace.PAUSE_CANCELLATION_CONCURRENT in suspended.races
    assert CodingSessionCancellationRace.LATE_FACT in late.races
    assert _lifecycle(CodingSessionLifecycleState.TERMINAL).lifecycle is CodingSessionLifecycleState.TERMINAL


def test_occurrence_metadata_does_not_change_request_identity() -> None:
    first = _cancellation_request((("observed-at", "100"),))
    second = _cancellation_request((("observed-at", "200"),))
    assert first.request_identity == second.request_identity
    assert first.fingerprint == second.fingerprint
