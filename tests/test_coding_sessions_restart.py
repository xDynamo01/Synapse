from __future__ import annotations

from dataclasses import replace

from synapse.coding_sessions import (
    CodingSessionActorReference,
    CodingSessionBinding,
    CodingSessionBindingScope,
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
    CodingSessionCorrelationReference,
    CodingSessionFactIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionJournalAssessment,
    CodingSessionJournalEntry,
    CodingSessionJournalEntryCategory,
    CodingSessionLifecycleState,
    CodingSessionLineage,
    CodingSessionProjectReference,
    CodingSessionPurpose,
    CodingSessionPurposeReference,
    CodingSessionReconciliationAssessment,
    CodingSessionReconciliationDimension,
    CodingSessionReconciliationEvidenceState,
    CodingSessionReconciliationOutcome,
    CodingSessionReconciliationRequest,
    CodingSessionRecoveryState,
    CodingSessionRepositoryReference,
    CodingSessionRestartAssessment,
    CodingSessionRestartDiagnosticCode,
    CodingSessionRestartFact,
    CodingSessionRestartRequest,
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


def _journal_checkpoint():
    contract = _contract()
    entry = CodingSessionJournalEntry.create(
        session_identity=contract.session_identity,
        category=CodingSessionJournalEntryCategory.CONTRACT_BINDING,
        semantic_identity="contract:one",
        semantic_fingerprint=contract.fingerprint,
        causal_revision=1,
    )
    journal = CodingSessionJournalAssessment.assess_stream(
        contract.session_identity, (entry,)
    )
    manifest = CodingSessionCheckpointManifest(
        contract.session_identity,
        journal.stream.fingerprint,
        1,
        contract_fingerprint=contract.fingerprint,
        lifecycle_fingerprint=CodingSessionFingerprint.from_content("lifecycle"),
    )
    checkpoint = CodingSessionCheckpointAssessment.assess(
        CodingSessionCheckpointRequest(
            CodingSessionCheckpointIdentity.from_stable_key("checkpoint:one"),
            contract.session_identity,
            manifest,
            1,
        ),
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


def _restart_request(occurrence=()) -> CodingSessionRestartRequest:
    journal, checkpoint = _journal_checkpoint()
    identity = CodingSessionFactIdentity.from_stable_key("restart:one")
    return CodingSessionRestartRequest(
        restart_identity=identity,
        session_identity=_contract().session_identity,
        expected_causal_revision=1,
        contract=_contract(),
        journal=journal,
        checkpoint=checkpoint,
        checkpoint_persistence_evidence=CodingSessionFingerprint.from_content(
            "persisted-checkpoint"
        ),
        lifecycle_facts=(),
        lease_facts=(),
        intents=(),
        receipts=(),
        observation_time=100,
        occurrence_metadata=occurrence,
    )


def _restart() -> CodingSessionRestartAssessment:
    return CodingSessionRestartAssessment.assess(_restart_request())


def _fact(
    dimension: CodingSessionReconciliationDimension,
    state: CodingSessionReconciliationEvidenceState,
    revision: int,
) -> CodingSessionRestartFact:
    identity = CodingSessionFactIdentity.from_stable_key(
        f"revalidation:{dimension.value}"
    )
    evidence = CodingSessionFingerprint.from_content((dimension, state))
    return CodingSessionRestartFact(
        identity,
        _contract().session_identity,
        dimension,
        state,
        evidence,
        CodingSessionCausalMetadata(
            identity,
            CodingSessionCausalRevision(revision),
            CodingSessionLineage(references=(evidence,)),
        ),
    )


def test_restart_reconstructs_only_supplied_facts_and_never_activates_or_resumes() -> None:
    restart = _restart()
    assert restart.lifecycle.lifecycle is CodingSessionLifecycleState.UNKNOWN
    states = {fact.dimension: fact.state for fact in restart.facts}
    assert states[CodingSessionReconciliationDimension.CONTRACT] is (
        CodingSessionReconciliationEvidenceState.RECONSTRUCTED
    )
    assert states[CodingSessionReconciliationDimension.REPOSITORY] is (
        CodingSessionReconciliationEvidenceState.UNKNOWN
    )
    assert states[CodingSessionReconciliationDimension.WORKER] is (
        CodingSessionReconciliationEvidenceState.UNKNOWN
    )
    assert states[CodingSessionReconciliationDimension.EXECUTION] is (
        CodingSessionReconciliationEvidenceState.UNKNOWN
    )
    assert not hasattr(restart, "resumed")


def test_duplicate_restart_is_idempotent_and_creates_no_second_progression() -> None:
    request = _restart_request()
    duplicate = CodingSessionRestartAssessment.assess(
        request,
        prior_restart_fingerprints=frozenset({request.idempotency_fingerprint}),
    )
    assert CodingSessionRestartDiagnosticCode.DUPLICATE_RESTART in {
        item.code for item in duplicate.diagnostics
    }
    assert duplicate.idempotency_fingerprint == request.idempotency_fingerprint


def test_journal_or_causal_mismatch_blocks_clean_restart() -> None:
    request = replace(_restart_request(), expected_causal_revision=2)
    assessment = CodingSessionRestartAssessment.assess(request)
    assert CodingSessionRestartDiagnosticCode.CAUSAL_REVISION_MISMATCH in {
        item.code for item in assessment.diagnostics
    }


def test_unknown_external_state_blocks_resume_without_becoming_failure() -> None:
    restart = _restart()
    assessment = CodingSessionReconciliationAssessment.assess(
        CodingSessionReconciliationRequest(
            _contract().session_identity,
            restart.lifecycle.causal_revision,
            restart,
            (),
        )
    )
    assert not assessment.resume_eligibility.eligible
    assert assessment.resume_eligibility.outcome is (
        CodingSessionReconciliationOutcome.RECONCILIATION_INCOMPLETE
    )
    assert CodingSessionReconciliationDimension.WORKER in (
        assessment.resume_eligibility.unknown_dimensions
    )
    assert CodingSessionReconciliationDimension.EXECUTION in (
        assessment.resume_eligibility.unknown_dimensions
    )


def test_safe_resume_requires_explicit_revalidation_of_every_required_dimension() -> None:
    restart = replace(
        _restart(),
        lifecycle=replace(
            _restart().lifecycle,
            lifecycle=CodingSessionLifecycleState.SUSPENDED,
            cancellation=CodingSessionCancellationState.NOT_REQUESTED,
            recovery=CodingSessionRecoveryState.NOT_REQUIRED,
        ),
    )
    facts = tuple(
        _fact(dimension, CodingSessionReconciliationEvidenceState.REVALIDATED, revision)
        for revision, dimension in enumerate(
            (
                CodingSessionReconciliationDimension.REPOSITORY,
                CodingSessionReconciliationDimension.OWNERSHIP,
                CodingSessionReconciliationDimension.WORKER,
                CodingSessionReconciliationDimension.EXECUTION,
            ),
            start=1,
        )
    )
    assessment = CodingSessionReconciliationAssessment.assess(
        CodingSessionReconciliationRequest(
            _contract().session_identity, 0, restart, facts
        )
    )
    assert assessment.resume_eligibility.eligible
    assert assessment.resume_eligibility.outcome is (
        CodingSessionReconciliationOutcome.SAFE_TO_RESUME
    )
    assert not hasattr(assessment, "transition")


def test_stale_lease_cancellation_and_recovery_block_resume() -> None:
    restart = replace(
        _restart(),
        lifecycle=replace(
            _restart().lifecycle,
            lifecycle=CodingSessionLifecycleState.SUSPENDED,
            cancellation=CodingSessionCancellationState.REQUESTED,
            recovery=CodingSessionRecoveryState.REQUIRED,
        ),
    )
    facts = (
        _fact(
            CodingSessionReconciliationDimension.OWNERSHIP,
            CodingSessionReconciliationEvidenceState.STALE,
            1,
        ),
    )
    assessment = CodingSessionReconciliationAssessment.assess(
        CodingSessionReconciliationRequest(
            _contract().session_identity, 0, restart, facts
        )
    )
    codes = {item.code for item in assessment.resume_eligibility.diagnostics}
    assert CodingSessionRestartDiagnosticCode.STALE_LEASE in codes
    assert CodingSessionRestartDiagnosticCode.CANCELLATION_PENDING in codes
    assert CodingSessionRestartDiagnosticCode.RECOVERY_REQUIRED in codes
    assert assessment.resume_eligibility.outcome is (
        CodingSessionReconciliationOutcome.RECOVERY_REQUIRED
    )


def test_contradiction_or_orphan_worker_requires_manual_intervention() -> None:
    restart = _restart()
    facts = (
        _fact(
            CodingSessionReconciliationDimension.WORKER,
            CodingSessionReconciliationEvidenceState.ORPHANED,
            1,
        ),
        _fact(
            CodingSessionReconciliationDimension.REPOSITORY,
            CodingSessionReconciliationEvidenceState.CONTRADICTORY,
            2,
        ),
    )
    assessment = CodingSessionReconciliationAssessment.assess(
        CodingSessionReconciliationRequest(
            _contract().session_identity, 0, restart, facts
        )
    )
    assert assessment.resume_eligibility.outcome is (
        CodingSessionReconciliationOutcome.MANUAL_INTERVENTION
    )
    assert CodingSessionRestartDiagnosticCode.MANUAL_INTERVENTION_REQUIRED in {
        item.code for item in assessment.resume_eligibility.diagnostics
    }


def test_duplicate_resume_and_terminal_late_state_do_not_reopen_session() -> None:
    restart = replace(
        _restart(),
        lifecycle=replace(
            _restart().lifecycle, lifecycle=CodingSessionLifecycleState.TERMINAL
        ),
    )
    resume = CodingSessionFingerprint.from_content("resume:one")
    assessment = CodingSessionReconciliationAssessment.assess(
        CodingSessionReconciliationRequest(
            _contract().session_identity,
            0,
            restart,
            (),
            prior_resume_fingerprints=frozenset({resume}),
            resume_fingerprint=resume,
        )
    )
    codes = {item.code for item in assessment.resume_eligibility.diagnostics}
    assert CodingSessionRestartDiagnosticCode.DUPLICATE_RESUME in codes
    assert CodingSessionRestartDiagnosticCode.TERMINAL_SESSION in codes
    assert restart.lifecycle.lifecycle is CodingSessionLifecycleState.TERMINAL


def test_same_evidence_is_deterministic_and_occurrence_is_not_semantic() -> None:
    first = _restart_request((("observed-at", "100"),))
    second = _restart_request((("observed-at", "200"),))
    assert first.idempotency_fingerprint == second.idempotency_fingerprint
    left = CodingSessionReconciliationAssessment.assess(
        CodingSessionReconciliationRequest(
            _contract().session_identity, 0, _restart(), ()
        )
    )
    right = CodingSessionReconciliationAssessment.assess(
        CodingSessionReconciliationRequest(
            _contract().session_identity, 0, _restart(), ()
        )
    )
    assert left.fingerprint == right.fingerprint
