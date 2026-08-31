from __future__ import annotations

from dataclasses import replace

from synapse.coding_sessions import (
    CODING_SESSION_CONTRACT_VERSION,
    CodingSessionActorReference,
    CodingSessionBinding,
    CodingSessionBindingScope,
    CodingSessionCausalMetadata,
    CodingSessionCausalRevision,
    CodingSessionCheckoutReference,
    CodingSessionCompletionRequirement,
    CodingSessionContract,
    CodingSessionContractAssessment,
    CodingSessionContractDiagnosticCode,
    CodingSessionCorrelationReference,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionLineage,
    CodingSessionPlatformContextReference,
    CodingSessionProjectReference,
    CodingSessionPurpose,
    CodingSessionPurposeReference,
    CodingSessionRepositoryReference,
    CodingSessionRequestedCapability,
    CodingSessionRequirement,
    CodingSessionRuntimeConclusion,
    CodingSessionTaskReference,
    CodingSessionWorktreeReference,
)


def _reference(reference_type, artifact_type: str, identity: str):
    return reference_type("producer", artifact_type, "v1", identity)


def _contract(
    *,
    scope: CodingSessionBindingScope = CodingSessionBindingScope.WORKTREE,
    repository: bool = True,
    checkout: bool = True,
    worktree: bool = True,
    requested: tuple[CodingSessionRequirement, ...] = (),
    completion: tuple[CodingSessionRequirement, ...] = (),
    occurrence: tuple[tuple[str, str], ...] = (),
) -> CodingSessionContract:
    identity = CodingSessionIdentity.from_stable_key("project:task:session")
    project = CodingSessionProjectReference("project:one")
    return CodingSessionContract(
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
            scope=scope,
            repository=(
                _reference(CodingSessionRepositoryReference, "repository", "repository:one")
                if repository
                else None
            ),
            checkout=(
                _reference(CodingSessionCheckoutReference, "checkout", "checkout:one")
                if checkout
                else None
            ),
            worktree=(
                _reference(CodingSessionWorktreeReference, "worktree", "worktree:one")
                if worktree
                else None
            ),
            platform_context=_reference(
                CodingSessionPlatformContextReference,
                "platform-context",
                "platform:windows",
            ),
        ),
        requested_capabilities=requested,
        completion_requirements=completion,
        policy_version="policy-v1",
        causal_metadata=CodingSessionCausalMetadata(
            identity,
            CodingSessionCausalRevision(1),
            CodingSessionLineage(),
            occurrence,
        ),
    )


def _codes(assessment: CodingSessionContractAssessment) -> set[CodingSessionContractDiagnosticCode]:
    return {item.code for item in assessment.diagnostics}


def test_complete_valid_contract_does_not_claim_prepared_or_active() -> None:
    assessment = CodingSessionContractAssessment.assess(_contract())
    assert assessment.complete is True
    assert assessment.valid is True
    assert assessment.prepared is CodingSessionRuntimeConclusion.NOT_EVALUATED
    assert assessment.active is CodingSessionRuntimeConclusion.NOT_EVALUATED


def test_non_repository_session_requires_no_implicit_repository_binding() -> None:
    contract = _contract(
        scope=CodingSessionBindingScope.NONE,
        repository=False,
        checkout=False,
        worktree=False,
    )
    assessment = CodingSessionContractAssessment.assess(contract)
    assert assessment.complete is True
    assert assessment.valid is True
    assert contract.binding.repository is None
    assert contract.binding.checkout is None
    assert contract.binding.worktree is None


def test_repository_binding_does_not_select_checkout_or_worktree() -> None:
    contract = _contract(
        scope=CodingSessionBindingScope.REPOSITORY,
        checkout=False,
        worktree=False,
    )
    assert CodingSessionContractAssessment.assess(contract).valid is True
    assert contract.binding.checkout is None
    assert contract.binding.worktree is None


def test_binding_scope_reports_missing_and_incompatible_combinations() -> None:
    missing = _contract(scope=CodingSessionBindingScope.WORKTREE, checkout=False)
    incompatible = _contract(scope=CodingSessionBindingScope.REPOSITORY)
    assert CodingSessionContractDiagnosticCode.MISSING_REQUIRED_BINDING in _codes(
        CodingSessionContractAssessment.assess(missing)
    )
    assert CodingSessionContractDiagnosticCode.INCOMPATIBLE_BINDING_COMBINATION in _codes(
        CodingSessionContractAssessment.assess(incompatible)
    )


def test_requested_capability_neither_grants_authority_nor_executes() -> None:
    capability = CodingSessionRequirement(
        CodingSessionRequestedCapability.REPOSITORY_MUTATION
    )
    contract = _contract(requested=(capability,))
    assessment = CodingSessionContractAssessment.assess(contract)
    assert assessment.valid is True
    assert not hasattr(contract, "authorization")
    assert not hasattr(assessment, "executed")
    assert assessment.prepared is CodingSessionRuntimeConclusion.NOT_EVALUATED


def test_completion_requirement_does_not_conclude_completion() -> None:
    requirement = CodingSessionRequirement(
        CodingSessionCompletionRequirement.REPOSITORY_VERIFICATION
    )
    assessment = CodingSessionContractAssessment.assess(
        _contract(completion=(requirement,))
    )
    assert assessment.valid is True
    assert not hasattr(assessment, "completed")


def test_repository_requirements_fail_complete_without_repository_or_worktree() -> None:
    mutation = CodingSessionRequirement(CodingSessionRequestedCapability.REPOSITORY_MUTATION)
    contract = _contract(
        scope=CodingSessionBindingScope.NONE,
        repository=False,
        checkout=False,
        worktree=False,
        requested=(mutation,),
    )
    assessment = CodingSessionContractAssessment.assess(contract)
    assert assessment.complete is False
    assert assessment.valid is False
    assert CodingSessionContractDiagnosticCode.MISSING_REQUIRED_BINDING in _codes(assessment)


def test_duplicate_and_conflicting_requirements_remain_explicit() -> None:
    first_target = CodingSessionFingerprint.from_content("target:first")
    second_target = CodingSessionFingerprint.from_content("target:second")
    duplicate = CodingSessionRequirement(
        CodingSessionRequestedCapability.PRIVATE_EVAL, first_target
    )
    conflicting = CodingSessionRequirement(
        CodingSessionRequestedCapability.PRIVATE_EVAL, second_target
    )
    assessment = CodingSessionContractAssessment.assess(
        _contract(requested=(duplicate, duplicate, conflicting))
    )
    assert CodingSessionContractDiagnosticCode.DUPLICATE_SEMANTIC_REQUIREMENT in _codes(
        assessment
    )
    assert CodingSessionContractDiagnosticCode.CONFLICTING_REQUIREMENT in _codes(assessment)


def test_requirement_in_wrong_category_is_conflicting() -> None:
    misplaced = CodingSessionRequirement(
        CodingSessionCompletionRequirement.DURABLE_CHECKPOINT
    )
    assessment = CodingSessionContractAssessment.assess(
        _contract(requested=(misplaced,))
    )
    assert CodingSessionContractDiagnosticCode.CONFLICTING_REQUIREMENT in _codes(assessment)


def test_session_project_and_causal_correspondence_are_assessed() -> None:
    contract = _contract()
    other_identity = CodingSessionIdentity.from_stable_key("other:session")
    other_project = CodingSessionProjectReference("project:other")
    mismatched = replace(
        contract,
        binding=replace(
            contract.binding,
            session_identity=other_identity,
            project=other_project,
        ),
        causal_metadata=replace(contract.causal_metadata, semantic_identity=other_identity),
    )
    codes = _codes(CodingSessionContractAssessment.assess(mismatched))
    assert CodingSessionContractDiagnosticCode.MISMATCHED_SESSION_IDENTITY in codes
    assert (
        CodingSessionContractDiagnosticCode.MISMATCHED_PROJECT_REPOSITORY_RELATIONSHIP
        in codes
    )


def test_repository_chain_requires_exact_producer_and_version_correspondence() -> None:
    contract = _contract()
    mismatched_checkout = CodingSessionCheckoutReference(
        "other-producer", "checkout", "v2", "checkout:one"
    )
    assessment = CodingSessionContractAssessment.assess(
        replace(contract, binding=replace(contract.binding, checkout=mismatched_checkout))
    )
    assert CodingSessionContractDiagnosticCode.INVALID_EXTERNAL_REFERENCE in _codes(assessment)


def test_unknown_contract_or_policy_version_fails_explicitly() -> None:
    contract = replace(_contract(), contract_version="coding-session-contract-v2")
    policy = replace(_contract(), policy_version="invalid policy")
    assert contract.contract_version != CODING_SESSION_CONTRACT_VERSION
    assert CodingSessionContractDiagnosticCode.UNSUPPORTED_CONTRACT_VERSION in _codes(
        CodingSessionContractAssessment.assess(contract)
    )
    assert CodingSessionContractDiagnosticCode.UNSUPPORTED_CONTRACT_VERSION in _codes(
        CodingSessionContractAssessment.assess(policy)
    )


def test_semantic_order_is_canonical_and_purpose_changes_fingerprint() -> None:
    access = CodingSessionRequirement(CodingSessionRequestedCapability.REPOSITORY_ACCESS)
    sandbox = CodingSessionRequirement(CodingSessionRequestedCapability.SANDBOX_EXECUTION)
    left = _contract(requested=(access, sandbox))
    right = _contract(requested=(sandbox, access))
    changed = replace(
        left,
        purpose=CodingSessionPurpose(
            left.purpose.task,
            CodingSessionPurposeReference("purpose:review"),
        ),
    )
    assert left.fingerprint == right.fingerprint
    assert left.fingerprint != changed.fingerprint


def test_occurrence_metadata_does_not_change_contract_fingerprint() -> None:
    first = _contract(occurrence=(("observed-at", "100"),))
    second = _contract(occurrence=(("observed-at", "200"),))
    assert first.session_identity == second.session_identity
    assert first.fingerprint == second.fingerprint


def test_diagnostics_are_closed_ordered_and_redacted() -> None:
    secret = "absolute-secret-path"
    contract = replace(
        _contract(scope=CodingSessionBindingScope.REPOSITORY),
        contract_version=f"unsupported-{secret}",
    )
    assessment = CodingSessionContractAssessment.assess(contract)
    assert assessment.diagnostics == tuple(
        sorted(assessment.diagnostics, key=lambda item: (item.code.value, item.subject))
    )
    assert all(secret not in diagnostic.subject for diagnostic in assessment.diagnostics)
