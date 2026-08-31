from __future__ import annotations

from dataclasses import replace

import pytest

from synapse.coding_sessions import (
    CodingSessionActorReference,
    CodingSessionArtifactReference,
    CodingSessionBinding,
    CodingSessionBindingScope,
    CodingSessionCausalMetadata,
    CodingSessionCausalRevision,
    CodingSessionCheckoutReference,
    CodingSessionContract,
    CodingSessionCorrelationReference,
    CodingSessionExternalReceipt,
    CodingSessionExternalReceiptIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionIntent,
    CodingSessionIntentAssessment,
    CodingSessionIntentCategory,
    CodingSessionIntentDiagnosticCode,
    CodingSessionIntentIdentity,
    CodingSessionIntentReceiptProjection,
    CodingSessionIntentReceiptStatus,
    CodingSessionIntentRequirement,
    CodingSessionLeaseAction,
    CodingSessionLeaseAssessment,
    CodingSessionLeaseCapability,
    CodingSessionLeaseInterval,
    CodingSessionLeaseMode,
    CodingSessionLeasePolicy,
    CodingSessionLeaseRequest,
    CodingSessionLeaseScope,
    CodingSessionLifecycleState,
    CodingSessionLineage,
    CodingSessionOwnershipProjection,
    CodingSessionProjectReference,
    CodingSessionPurpose,
    CodingSessionPurposeReference,
    CodingSessionReceiptAssessment,
    CodingSessionReceiptCompleteness,
    CodingSessionReceiptOutcome,
    CodingSessionRepositoryCorrespondenceState,
    CodingSessionRepositoryReference,
    CodingSessionRequestedCapability,
    CodingSessionRequirement,
    CodingSessionStateProjection,
    CodingSessionTargetAuthority,
    CodingSessionTaskReference,
    CodingSessionWorktreeReference,
)


def _contract(
    key: str = "session:one",
    capability: CodingSessionRequestedCapability = (
        CodingSessionRequestedCapability.REPOSITORY_MUTATION
    ),
) -> CodingSessionContract:
    identity = CodingSessionIdentity.from_stable_key(key)
    project = CodingSessionProjectReference("project:one")
    purpose = CodingSessionPurpose(
        CodingSessionTaskReference("task:one"),
        CodingSessionPurposeReference("purpose:implement"),
    )
    repository = CodingSessionRepositoryReference.create(
        "repository-runtime", "v1", "repository:one"
    )
    checkout = CodingSessionCheckoutReference.create(
        "repository-runtime", "v1", "checkout:one"
    )
    worktree = CodingSessionWorktreeReference.create(
        "repository-runtime", "v1", "worktree:one"
    )
    binding = CodingSessionBinding(
        identity,
        project,
        CodingSessionBindingScope.WORKTREE,
        repository=repository,
        checkout=checkout,
        worktree=worktree,
    )
    return CodingSessionContract(
        session_identity=identity,
        actor=CodingSessionActorReference(f"actor:{key}"),
        project=project,
        purpose=purpose,
        correlation=CodingSessionCorrelationReference(f"correlation:{key}"),
        binding=binding,
        requested_capabilities=(CodingSessionRequirement(capability),),
        completion_requirements=(),
        policy_version="policy-v1",
        causal_metadata=CodingSessionCausalMetadata(
            identity, CodingSessionCausalRevision(1), CodingSessionLineage()
        ),
    )


def _lifecycle(
    contract: CodingSessionContract,
    state: CodingSessionLifecycleState = CodingSessionLifecycleState.PREPARED,
) -> CodingSessionStateProjection:
    return CodingSessionStateProjection(contract.session_identity, lifecycle=state)


def _intent(
    contract: CodingSessionContract,
    *,
    category: CodingSessionIntentCategory = CodingSessionIntentCategory.REPOSITORY_APPLICATION,
    authority: CodingSessionTargetAuthority = CodingSessionTargetAuthority.REPOSITORY_RUNTIME,
    capability: CodingSessionRequestedCapability = (
        CodingSessionRequestedCapability.REPOSITORY_MUTATION
    ),
    write: bool = True,
    lease_reference=None,
    key: str = "intent:one",
    occurrence: tuple[tuple[str, str], ...] = (),
) -> CodingSessionIntent:
    identity = CodingSessionIntentIdentity.from_stable_key(key)
    reference = contract.binding.repository
    assert reference is not None
    return CodingSessionIntent(
        intent_identity=identity,
        session_identity=contract.session_identity,
        actor=contract.actor,
        purpose=contract.purpose,
        correlation=contract.correlation,
        category=category,
        target_authority=authority,
        target_type="artifact",
        requirement=CodingSessionIntentRequirement(
            capability,
            frozenset(
                {
                    CodingSessionReceiptOutcome.ACKNOWLEDGED,
                    CodingSessionReceiptOutcome.SUCCEEDED,
                    CodingSessionReceiptOutcome.FAILED,
                }
            ),
            write_coordination_required=write,
        ),
        binding=contract.binding,
        external_references=(reference,),
        lease_reference=lease_reference,
        policy_version="coding-session-intent-policy-v1",
        causal_metadata=CodingSessionCausalMetadata(
            identity,
            CodingSessionCausalRevision(1),
            CodingSessionLineage(),
            occurrence,
        ),
    )


def _write_ownership(contract: CodingSessionContract):
    request = CodingSessionLeaseRequest(
        action=CodingSessionLeaseAction.ISSUE,
        session_identity=contract.session_identity,
        actor=contract.actor,
        purpose=contract.purpose,
        binding=contract.binding,
        scope=CodingSessionLeaseScope(CodingSessionBindingScope.REPOSITORY),
        capability=CodingSessionLeaseCapability.WRITE,
        mode=CodingSessionLeaseMode.EXCLUSIVE,
        interval=CodingSessionLeaseInterval(10, 10, 20),
        expected_causal_revision=0,
    )
    fact = CodingSessionLeaseAssessment.assess(
        request, contract, (), CodingSessionLeasePolicy()
    ).fact
    assert fact is not None
    projection = CodingSessionOwnershipProjection.project(
        (fact,), observation_time=15, policy=CodingSessionLeasePolicy()
    )
    return fact, projection


def _receipt(
    intent: CodingSessionIntent,
    *,
    key: str = "receipt:one",
    outcome: CodingSessionReceiptOutcome = CodingSessionReceiptOutcome.SUCCEEDED,
    completeness: CodingSessionReceiptCompleteness = CodingSessionReceiptCompleteness.COMPLETE,
    lifecycle_parent: CodingSessionFingerprint | None = None,
    occurrence: tuple[tuple[str, str], ...] = (),
) -> CodingSessionExternalReceipt:
    identity = CodingSessionExternalReceiptIdentity.from_stable_key(key)
    producer_fingerprint = CodingSessionFingerprint.from_content((key, outcome))
    artifact = CodingSessionArtifactReference.create(
        intent.target_authority.value,
        "v1",
        f"artifact:{key}",
        producer_fingerprint,
    )
    parent = lifecycle_parent or intent.fingerprint
    references = () if parent == intent.fingerprint else (intent.fingerprint,)
    return CodingSessionExternalReceipt(
        receipt_identity=identity,
        session_identity=intent.session_identity,
        intent_identity=intent.intent_identity,
        intent_fingerprint=intent.fingerprint,
        producer_authority=intent.target_authority,
        producer_artifact=artifact,
        producer_version="v1",
        producer_fingerprint=producer_fingerprint,
        correlated_references=intent.external_references,
        actor=intent.actor,
        purpose=intent.purpose,
        correlation=intent.correlation,
        binding=intent.binding,
        outcome=outcome,
        completeness=completeness,
        policy_version="coding-session-intent-policy-v1",
        causal_metadata=CodingSessionCausalMetadata(
            identity,
            CodingSessionCausalRevision(2 if parent == intent.fingerprint else 3),
            CodingSessionLineage(parents=(parent,), references=references),
            occurrence,
        ),
    )


def _codes(assessment: CodingSessionReceiptAssessment) -> set[CodingSessionIntentDiagnosticCode]:
    return {item.code for item in assessment.binding.diagnostics}


def test_intent_and_valid_lease_do_not_imply_execution_or_authorization() -> None:
    contract = _contract()
    lease, ownership = _write_ownership(contract)
    intent = _intent(contract, lease_reference=lease.lease_identity)
    assessment = CodingSessionIntentAssessment.assess(
        intent, contract, _lifecycle(contract), ownership, (lease,)
    )
    assert assessment.accepted
    assert not hasattr(intent, "authorized")
    assert not hasattr(intent, "executed")
    assert not hasattr(assessment, "authorization")


def test_write_intent_requires_coordination_but_lease_never_grants_authority() -> None:
    contract = _contract()
    intent = _intent(contract)
    missing = CodingSessionIntentAssessment.assess(
        intent, contract, _lifecycle(contract)
    )
    assert CodingSessionIntentDiagnosticCode.WRITE_LEASE_REQUIRED in {
        item.code for item in missing.diagnostics
    }
    lease, ownership = _write_ownership(contract)
    coordinated = CodingSessionIntentAssessment.assess(
        replace(intent, lease_reference=lease.lease_identity),
        contract,
        _lifecycle(contract),
        ownership,
        (lease,),
    )
    assert coordinated.accepted
    assert not hasattr(coordinated, "authorized")


def test_intent_validates_contract_lifecycle_actor_purpose_and_binding() -> None:
    contract = _contract(
        capability=CodingSessionRequestedCapability.REPOSITORY_ACCESS
    )
    intent = _intent(
        contract,
        category=CodingSessionIntentCategory.REPOSITORY_OBSERVATION,
        capability=CodingSessionRequestedCapability.REPOSITORY_ACCESS,
        write=False,
    )
    assert CodingSessionIntentAssessment.assess(
        intent, contract, _lifecycle(contract)
    ).accepted
    planned = CodingSessionIntentAssessment.assess(
        intent, contract, _lifecycle(contract, CodingSessionLifecycleState.PLANNED)
    )
    mismatched = CodingSessionIntentAssessment.assess(
        replace(intent, actor=CodingSessionActorReference("actor:other")),
        contract,
        _lifecycle(contract),
    )
    assert CodingSessionIntentDiagnosticCode.LIFECYCLE_INCOMPATIBLE in {
        item.code for item in planned.diagnostics
    }
    assert CodingSessionIntentDiagnosticCode.ACTOR_MISMATCH in {
        item.code for item in mismatched.diagnostics
    }


def test_receipt_is_factual_and_does_not_update_internal_dimensions() -> None:
    contract = _contract()
    intent = _intent(contract)
    lifecycle = _lifecycle(contract, CodingSessionLifecycleState.ACTIVE)
    receipt = _receipt(intent)
    assessment = CodingSessionReceiptAssessment.assess(receipt, intent, lifecycle)
    assert assessment.corresponding
    assert assessment.binding.status is CodingSessionIntentReceiptStatus.RESPONDED
    assert lifecycle.lifecycle is CodingSessionLifecycleState.ACTIVE
    assert lifecycle.repository_correspondence is CodingSessionRepositoryCorrespondenceState.UNBOUND
    assert not hasattr(receipt, "session_completed")
    assert not hasattr(receipt, "execution_verified")
    assert not hasattr(receipt, "published")


@pytest.mark.parametrize(
    "category,authority,outcome",
    (
        (
            CodingSessionIntentCategory.WORKER_ASSISTANCE_REQUEST,
            CodingSessionTargetAuthority.WORKERS,
            CodingSessionReceiptOutcome.SUCCEEDED,
        ),
        (
            CodingSessionIntentCategory.SANDBOX_EXECUTION_REQUEST,
            CodingSessionTargetAuthority.SANDBOX,
            CodingSessionReceiptOutcome.SUCCEEDED,
        ),
        (
            CodingSessionIntentCategory.PRIVATE_EVAL_REQUEST,
            CodingSessionTargetAuthority.PRIVATE_EVALS,
            CodingSessionReceiptOutcome.SUCCEEDED,
        ),
        (
            CodingSessionIntentCategory.DEPLOYMENT_CANDIDATE_HANDOFF,
            CodingSessionTargetAuthority.DEPLOYMENT_RUNTIME,
            CodingSessionReceiptOutcome.SUCCEEDED,
        ),
    ),
)
def test_external_success_never_implies_session_completion(
    category: CodingSessionIntentCategory,
    authority: CodingSessionTargetAuthority,
    outcome: CodingSessionReceiptOutcome,
) -> None:
    contract = _contract()
    intent = _intent(contract, category=category, authority=authority)
    lifecycle = _lifecycle(contract, CodingSessionLifecycleState.ACTIVE)
    assessment = CodingSessionReceiptAssessment.assess(
        _receipt(intent, outcome=outcome), intent, lifecycle
    )
    assert assessment.binding.status is CodingSessionIntentReceiptStatus.RESPONDED
    assert lifecycle.lifecycle is CodingSessionLifecycleState.ACTIVE


def test_receipt_correspondence_rejects_session_producer_binding_and_correlation_mismatch() -> None:
    contract = _contract()
    intent = _intent(contract)
    receipt = _receipt(intent)
    other_contract = _contract("session:other")
    cases = (
        replace(receipt, session_identity=other_contract.session_identity),
        replace(receipt, producer_authority=CodingSessionTargetAuthority.SANDBOX),
        replace(receipt, binding=other_contract.binding),
        replace(receipt, correlation=other_contract.correlation),
    )
    expected = (
        CodingSessionIntentDiagnosticCode.SESSION_MISMATCH,
        CodingSessionIntentDiagnosticCode.PRODUCER_MISMATCH,
        CodingSessionIntentDiagnosticCode.BINDING_MISMATCH,
        CodingSessionIntentDiagnosticCode.CORRELATION_MISMATCH,
    )
    for candidate, code in zip(cases, expected):
        assert code in _codes(
            CodingSessionReceiptAssessment.assess(
                candidate, intent, _lifecycle(contract)
            )
        )


def test_missing_stale_and_late_receipts_remain_explicit_without_reopening() -> None:
    contract = _contract()
    intent = _intent(contract)
    lifecycle = _lifecycle(contract)
    missing = CodingSessionReceiptAssessment.assess(_receipt(intent), None, lifecycle)
    stale_receipt = replace(
        _receipt(intent),
        intent_fingerprint=CodingSessionFingerprint.from_content("older-intent"),
    )
    stale = CodingSessionReceiptAssessment.assess(stale_receipt, intent, lifecycle)
    terminal = _lifecycle(contract, CodingSessionLifecycleState.TERMINAL)
    late = CodingSessionReceiptAssessment.assess(_receipt(intent), intent, terminal)
    assert CodingSessionIntentDiagnosticCode.RECEIPT_INTENT_NOT_FOUND in _codes(missing)
    assert stale.binding.status is CodingSessionIntentReceiptStatus.STALE
    assert late.binding.status is CodingSessionIntentReceiptStatus.LATE
    assert terminal.lifecycle is CodingSessionLifecycleState.TERMINAL


def test_projection_has_pending_unresolved_and_responded_states() -> None:
    contract = _contract()
    first = _intent(contract, key="intent:first")
    second = _intent(contract, key="intent:second")
    partial = _receipt(
        first, completeness=CodingSessionReceiptCompleteness.PARTIAL
    )
    projection = CodingSessionIntentReceiptProjection.project(
        contract.session_identity,
        (second, first),
        (partial,),
        _lifecycle(contract),
    )
    assert {item.status for item in projection.bindings} == {
        CodingSessionIntentReceiptStatus.PENDING,
        CodingSessionIntentReceiptStatus.UNRESOLVED,
    }


def test_projection_detects_duplicate_identity_revision_and_lineage_gap() -> None:
    contract = _contract()
    intent = _intent(contract)
    receipt = _receipt(intent)
    duplicate = replace(
        receipt,
        receipt_identity=CodingSessionExternalReceiptIdentity.from_stable_key(
            "receipt:duplicate"
        ),
    )
    duplicated = CodingSessionIntentReceiptProjection.project(
        contract.session_identity,
        (intent,),
        (receipt, receipt, duplicate),
        _lifecycle(contract),
    )
    codes = {item.code for item in duplicated.diagnostics}
    assert CodingSessionIntentDiagnosticCode.DUPLICATE_RECEIPT_IDENTITY in codes
    assert CodingSessionIntentDiagnosticCode.DUPLICATE_CAUSAL_REVISION in codes
    broken = replace(
        receipt,
        causal_metadata=replace(
            receipt.causal_metadata,
            lineage=CodingSessionLineage(),
        ),
    )
    gap = CodingSessionIntentReceiptProjection.project(
        contract.session_identity,
        (intent,),
        (broken,),
        _lifecycle(contract),
    )
    assert CodingSessionIntentDiagnosticCode.LINEAGE_GAP in {
        item.code for item in gap.diagnostics
    }


def test_projection_is_deterministic_for_same_causal_set() -> None:
    contract = _contract()
    first = _intent(contract, key="intent:first")
    second = _intent(contract, key="intent:second")
    first_receipt = _receipt(first, key="receipt:first")
    second_receipt = _receipt(second, key="receipt:second")
    left = CodingSessionIntentReceiptProjection.project(
        contract.session_identity,
        (first, second),
        (first_receipt, second_receipt),
        _lifecycle(contract),
    )
    right = CodingSessionIntentReceiptProjection.project(
        contract.session_identity,
        (second, first),
        (second_receipt, first_receipt),
        _lifecycle(contract),
    )
    assert left.fingerprint == right.fingerprint


def test_occurrence_metadata_does_not_change_intent_or_receipt_identity() -> None:
    contract = _contract()
    first_intent = _intent(contract, occurrence=(("observed-at", "100"),))
    second_intent = replace(
        first_intent,
        causal_metadata=replace(
            first_intent.causal_metadata,
            occurrence_metadata=(("observed-at", "200"),),
        ),
    )
    first_receipt = _receipt(
        first_intent, occurrence=(("observed-at", "100"),)
    )
    second_receipt = replace(
        first_receipt,
        causal_metadata=replace(
            first_receipt.causal_metadata,
            occurrence_metadata=(("observed-at", "200"),),
        ),
    )
    assert first_intent.fingerprint == second_intent.fingerprint
    assert first_receipt.fingerprint == second_receipt.fingerprint
