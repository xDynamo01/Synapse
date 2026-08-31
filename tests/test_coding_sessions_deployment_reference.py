from dataclasses import replace

from tests.test_coding_sessions_intents import _contract

from synapse.coding_sessions import (
    CodingSessionApprovalReference,
    CodingSessionArtifactReference,
    CodingSessionCausalMetadata,
    CodingSessionCausalRevision,
    CodingSessionFingerprint,
    CodingSessionLifecycleState,
    CodingSessionLineage,
    CodingSessionPrivateEvalResultReference,
    CodingSessionStateProjection,
)
from synapse.coding_sessions_integrations import (
    CodingSessionCandidateArtifactReference,
    CodingSessionCandidateInvalidation,
    CodingSessionCandidateInvalidationReason,
    CodingSessionCandidateProvenance,
    CodingSessionDeploymentCandidate,
    CodingSessionDeploymentDiagnosticCode,
    CodingSessionDeploymentHandoffReceipt,
    CodingSessionDeploymentHandoffRequest,
    CodingSessionDeploymentProjectionState,
    CodingSessionDeploymentReferenceService,
)


def _facts(*, evals=True, approvals=True):
    contract = _contract()
    artifact = CodingSessionArtifactReference.create(
        "artifact-authority", "v1", "artifact:release",
        CodingSessionFingerprint.from_content("artifact"),
    )
    snapshot = CodingSessionArtifactReference.create(
        "repository-runtime", "v1", "snapshot:source",
        CodingSessionFingerprint.from_content("snapshot"),
    )
    verification = CodingSessionArtifactReference.create(
        "repository-runtime", "v1", "verification:source",
        CodingSessionFingerprint.from_content("verification"),
    )
    eval_refs = (
        CodingSessionPrivateEvalResultReference.create(
            "private-evals", "v1", "result:one",
            CodingSessionFingerprint.from_content("eval"),
        ),
    ) if evals else ()
    approval_refs = (
        CodingSessionApprovalReference.create(
            "approvals", "v1", "approval:one",
            CodingSessionFingerprint.from_content("approval"),
        ),
    ) if approvals else ()
    provenance = CodingSessionCandidateProvenance(
        contract.binding.repository,
        contract.binding.checkout,
        contract.binding.worktree,
        snapshot,
        verification,
        eval_results=eval_refs,
        approvals=approval_refs,
    )
    candidate = CodingSessionDeploymentCandidate(
        contract.session_identity,
        contract.actor,
        contract.project,
        contract.purpose,
        contract.correlation,
        "candidate:one",
        (CodingSessionCandidateArtifactReference(artifact, "application"),),
        provenance,
        1,
        1,
        "deployment-handoff-policy",
        "v1",
        CodingSessionCausalMetadata(
            contract.session_identity,
            CodingSessionCausalRevision(1),
            CodingSessionLineage(),
        ),
    )
    assessment = CodingSessionDeploymentReferenceService.assess_candidate(
        candidate,
        observed_session=contract.session_identity,
        observed_artifacts=(artifact,),
        observed_repository_binding=(
            contract.binding.repository,
            contract.binding.checkout,
            contract.binding.worktree,
        ),
        source_verification_fresh=True,
    )
    request = CodingSessionDeploymentHandoffRequest(
        contract.session_identity,
        candidate.candidate_identity,
        candidate.fingerprint,
        (artifact,),
        "candidate-handoff",
        "deployment-runtime",
        approval_refs,
        eval_refs,
        "deployment-handoff-receipt",
        candidate.policy_id,
        candidate.policy_version,
        CodingSessionCausalMetadata(
            contract.session_identity,
            CodingSessionCausalRevision(2),
            CodingSessionLineage(parents=(candidate.fingerprint,)),
        ),
    )
    return contract, artifact, candidate, assessment, request


def _receipt(contract, candidate, request, **changes):
    base = CodingSessionDeploymentHandoffReceipt(
        "future-deployment-authority",
        "v1",
        "receipt:one",
        CodingSessionFingerprint.from_content("receipt"),
        contract.session_identity,
        candidate.candidate_identity,
        candidate.fingerprint,
        request.fingerprint,
        tuple(item.artifact for item in candidate.artifacts),
        CodingSessionDeploymentProjectionState.HANDED_OFF,
        3,
        "handoff-request:one",
    )
    return replace(base, **changes)


def test_candidate_and_handoff_have_no_deployment_authority_or_effects() -> None:
    contract, _, candidate, assessment, request = _facts()
    result = CodingSessionDeploymentReferenceService.assess_handoff(
        candidate,
        request,
        candidate_assessment=assessment,
        lifecycle=CodingSessionStateProjection(
            contract.session_identity, lifecycle=CodingSessionLifecycleState.ACTIVE
        ),
    )
    assert assessment.eligible
    assert result.state is CodingSessionDeploymentProjectionState.HANDOFF_REQUESTED
    assert not result.release_created
    assert not result.deployment_authorized
    assert not result.environment_selected
    assert not result.artifact_published
    assert not result.version_promoted
    assert not result.rollout_executed
    assert not result.rollback_executed
    assert not result.session_completed


def test_missing_eval_and_approval_block_handoff_eligibility() -> None:
    contract, artifact, candidate, _, _ = _facts(evals=False, approvals=False)
    result = CodingSessionDeploymentReferenceService.assess_candidate(
        candidate,
        observed_session=contract.session_identity,
        observed_artifacts=(artifact,),
        observed_repository_binding=(
            contract.binding.repository,
            contract.binding.checkout,
            contract.binding.worktree,
        ),
        source_verification_fresh=True,
    )
    assert not result.eligible
    assert {item.code for item in result.diagnostics} >= {
        CodingSessionDeploymentDiagnosticCode.MISSING_REQUIRED_EVAL,
        CodingSessionDeploymentDiagnosticCode.MISSING_REQUIRED_APPROVAL,
    }


def test_stale_verification_and_binding_or_artifact_mismatch_fail_closed() -> None:
    contract, _, candidate, _, _ = _facts()
    result = CodingSessionDeploymentReferenceService.assess_candidate(
        candidate,
        observed_session=contract.session_identity,
        observed_artifacts=(),
        observed_repository_binding=(None, None, None),
        source_verification_fresh=False,
    )
    assert {item.code for item in result.diagnostics} >= {
        CodingSessionDeploymentDiagnosticCode.ARTIFACT_MISMATCH,
        CodingSessionDeploymentDiagnosticCode.REPOSITORY_BINDING_MISMATCH,
        CodingSessionDeploymentDiagnosticCode.STALE_SOURCE_VERIFICATION,
    }


def test_invalidation_is_append_only_and_preserves_candidate() -> None:
    contract, artifact, candidate, _, _ = _facts()
    invalidation = CodingSessionCandidateInvalidation(
        candidate.candidate_identity,
        candidate.fingerprint,
        CodingSessionCandidateInvalidationReason.REPOSITORY_CHANGED,
        candidate.provenance.source_verification,
        2,
        candidate.fingerprint,
    )
    result = CodingSessionDeploymentReferenceService.assess_candidate(
        candidate,
        observed_session=contract.session_identity,
        observed_artifacts=(artifact,),
        observed_repository_binding=(
            contract.binding.repository,
            contract.binding.checkout,
            contract.binding.worktree,
        ),
        source_verification_fresh=True,
        invalidations=(invalidation,),
    )
    assert result.state is CodingSessionDeploymentProjectionState.INVALIDATED
    assert not result.candidate_history_deleted
    assert candidate.candidate_identity == invalidation.candidate_identity


def test_handed_off_is_only_reference_delivery() -> None:
    contract, _, candidate, assessment, request = _facts()
    receipt = _receipt(contract, candidate, request)
    result = CodingSessionDeploymentReferenceService.assess_handoff(
        candidate, request, candidate_assessment=assessment,
        lifecycle=CodingSessionStateProjection(contract.session_identity),
        receipt=receipt,
    )
    assert result.state is CodingSessionDeploymentProjectionState.HANDED_OFF
    assert result.candidate_reference is not None
    assert not result.deployment_authorized
    assert not result.rollout_executed
    assert not result.version_promoted
    assert not result.session_completed


def test_duplicate_conflicting_and_late_receipts_are_explicit() -> None:
    contract, _, candidate, assessment, request = _facts()
    receipt = _receipt(contract, candidate, request)
    conflict = replace(receipt, candidate_fingerprint=CodingSessionFingerprint.from_content("other"))
    lifecycle = CodingSessionStateProjection(
        contract.session_identity, lifecycle=CodingSessionLifecycleState.TERMINAL
    )
    duplicate = CodingSessionDeploymentReferenceService.assess_handoff(
        candidate, request, candidate_assessment=assessment, lifecycle=lifecycle,
        receipt=receipt, known_receipts=(receipt,),
    )
    conflicting = CodingSessionDeploymentReferenceService.assess_handoff(
        candidate, request, candidate_assessment=assessment, lifecycle=lifecycle,
        receipt=conflict, known_receipts=(receipt,),
    )
    assert {item.code for item in duplicate.diagnostics} >= {
        CodingSessionDeploymentDiagnosticCode.DUPLICATE_HANDOFF,
        CodingSessionDeploymentDiagnosticCode.LATE_RECEIPT,
    }
    assert CodingSessionDeploymentDiagnosticCode.CONFLICTING_HANDOFF_RECEIPT in {
        item.code for item in conflicting.diagnostics
    }
    assert not duplicate.reopens_terminal_session


def test_candidate_fingerprint_is_deterministic_and_semantic() -> None:
    _, _, candidate, _, _ = _facts()
    assert candidate.fingerprint == candidate.fingerprint
    changed = replace(candidate, required_eval_count=2)
    assert changed.fingerprint != candidate.fingerprint


def test_no_deployment_runtime_contract_is_imported() -> None:
    import synapse.coding_sessions_integrations.deployment as module

    assert "deployment_runtime" not in module.__dict__
