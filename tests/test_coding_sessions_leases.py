from __future__ import annotations

from dataclasses import replace

from synapse.coding_sessions import (
    CodingSessionActorReference,
    CodingSessionBinding,
    CodingSessionBindingScope,
    CodingSessionCausalMetadata,
    CodingSessionCausalRevision,
    CodingSessionCheckoutReference,
    CodingSessionContract,
    CodingSessionCoordinationState,
    CodingSessionCorrelationReference,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionLeaseAction,
    CodingSessionLeaseAssessment,
    CodingSessionLeaseCapability,
    CodingSessionLeaseDiagnosticCode,
    CodingSessionLeaseInterval,
    CodingSessionLeaseMode,
    CodingSessionLeasePolicy,
    CodingSessionLeaseRequest,
    CodingSessionLeaseScope,
    CodingSessionLeaseValidity,
    CodingSessionLineage,
    CodingSessionOwnershipProjection,
    CodingSessionProjectReference,
    CodingSessionPurpose,
    CodingSessionPurposeReference,
    CodingSessionRepositoryReference,
    CodingSessionRequestedCapability,
    CodingSessionRequirement,
    CodingSessionTaskReference,
    CodingSessionWorktreeReference,
)


def _external(reference_type, artifact_type: str, identity: str):
    return reference_type("repository-runtime", artifact_type, "v1", identity)


def _contract(
    session_key: str = "session:one",
    *,
    worktree: str = "worktree:one",
    scope: CodingSessionBindingScope = CodingSessionBindingScope.WORKTREE,
    write: bool = True,
) -> CodingSessionContract:
    identity = CodingSessionIdentity.from_stable_key(session_key)
    actor = CodingSessionActorReference(f"actor:{session_key}")
    project = CodingSessionProjectReference("project:one")
    purpose = CodingSessionPurpose(
        CodingSessionTaskReference("task:one"),
        CodingSessionPurposeReference("purpose:implement"),
    )
    binding = CodingSessionBinding(
        session_identity=identity,
        project=project,
        scope=scope,
        repository=_external(
            CodingSessionRepositoryReference, "repository", "repository:one"
        ),
        checkout=(
            _external(CodingSessionCheckoutReference, "checkout", "checkout:one")
            if scope in {CodingSessionBindingScope.CHECKOUT, CodingSessionBindingScope.WORKTREE}
            else None
        ),
        worktree=(
            _external(CodingSessionWorktreeReference, "worktree", worktree)
            if scope is CodingSessionBindingScope.WORKTREE
            else None
        ),
    )
    capability = (
        CodingSessionRequestedCapability.REPOSITORY_MUTATION
        if write
        else CodingSessionRequestedCapability.REPOSITORY_ACCESS
    )
    return CodingSessionContract(
        session_identity=identity,
        actor=actor,
        project=project,
        purpose=purpose,
        correlation=CodingSessionCorrelationReference(f"correlation:{session_key}"),
        binding=binding,
        requested_capabilities=(CodingSessionRequirement(capability),),
        completion_requirements=(),
        policy_version="policy-v1",
        causal_metadata=CodingSessionCausalMetadata(
            identity,
            CodingSessionCausalRevision(1),
            CodingSessionLineage(),
        ),
    )


def _request(
    contract: CodingSessionContract,
    *,
    action: CodingSessionLeaseAction = CodingSessionLeaseAction.ISSUE,
    capability: CodingSessionLeaseCapability = CodingSessionLeaseCapability.WRITE,
    mode: CodingSessionLeaseMode = CodingSessionLeaseMode.EXCLUSIVE,
    scope: CodingSessionBindingScope | None = None,
    interval: CodingSessionLeaseInterval = CodingSessionLeaseInterval(10, 10, 20),
    previous=None,
    occurrence: tuple[tuple[str, str], ...] = (),
) -> CodingSessionLeaseRequest:
    return CodingSessionLeaseRequest(
        action=action,
        session_identity=contract.session_identity,
        actor=contract.actor,
        purpose=contract.purpose,
        binding=contract.binding,
        scope=CodingSessionLeaseScope(scope or contract.binding.scope),
        capability=capability,
        mode=mode,
        interval=interval,
        expected_causal_revision=(
            previous.causal_metadata.revision.value if previous is not None else 0
        ),
        previous_fact_identity=(previous.fact_identity if previous is not None else None),
        occurrence_metadata=occurrence,
    )


def _issue(
    contract: CodingSessionContract,
    *,
    capability: CodingSessionLeaseCapability = CodingSessionLeaseCapability.WRITE,
    mode: CodingSessionLeaseMode = CodingSessionLeaseMode.EXCLUSIVE,
    policy: CodingSessionLeasePolicy = CodingSessionLeasePolicy(),
):
    assessment = CodingSessionLeaseAssessment.assess(
        _request(contract, capability=capability, mode=mode), contract, (), policy
    )
    assert assessment.accepted and assessment.fact is not None
    return assessment.fact


def _codes(assessment: CodingSessionLeaseAssessment) -> set[CodingSessionLeaseDiagnosticCode]:
    return {diagnostic.code for diagnostic in assessment.diagnostics}


def test_lease_is_coordination_not_authorization_or_mutation() -> None:
    fact = _issue(_contract())
    assert not hasattr(fact, "authorization")
    assert not hasattr(fact, "approval")
    assert not hasattr(fact, "mutation")
    assert not hasattr(fact, "filesystem_security")


def test_read_shared_is_not_write_or_exclusive() -> None:
    contract = _contract(write=False)
    fact = _issue(
        contract,
        capability=CodingSessionLeaseCapability.READ,
        mode=CodingSessionLeaseMode.SHARED,
    )
    projection = CodingSessionOwnershipProjection.project(
        (fact,), observation_time=15, policy=CodingSessionLeasePolicy()
    )
    assert projection.state is CodingSessionCoordinationState.READ_OWNED
    assert fact.capability is CodingSessionLeaseCapability.READ
    assert fact.mode is CodingSessionLeaseMode.SHARED


def test_shared_write_requires_explicit_policy() -> None:
    contract = _contract()
    request = _request(contract, mode=CodingSessionLeaseMode.SHARED)
    denied = CodingSessionLeaseAssessment.assess(
        request, contract, (), CodingSessionLeasePolicy()
    )
    allowed = CodingSessionLeaseAssessment.assess(
        request, contract, (), CodingSessionLeasePolicy(allow_shared_write=True)
    )
    assert CodingSessionLeaseDiagnosticCode.SHARED_WRITE_NOT_ALLOWED in _codes(denied)
    assert allowed.accepted


def test_contract_capability_and_scope_cannot_be_escalated() -> None:
    read_contract = _contract(write=False)
    capability = CodingSessionLeaseAssessment.assess(
        _request(read_contract), read_contract, (), CodingSessionLeasePolicy()
    )
    checkout_contract = _contract(scope=CodingSessionBindingScope.CHECKOUT)
    scope = CodingSessionLeaseAssessment.assess(
        _request(checkout_contract, scope=CodingSessionBindingScope.WORKTREE),
        checkout_contract,
        (),
        CodingSessionLeasePolicy(),
    )
    assert CodingSessionLeaseDiagnosticCode.CONTRACT_CAPABILITY_MISSING in _codes(capability)
    assert CodingSessionLeaseDiagnosticCode.SCOPE_ESCALATION in _codes(scope)


def test_actor_purpose_session_and_binding_mismatches_fail_closed() -> None:
    contract = _contract()
    request = _request(contract)
    cases = (
        replace(request, actor=CodingSessionActorReference("actor:other")),
        replace(
            request,
            purpose=replace(
                request.purpose,
                purpose=CodingSessionPurposeReference("purpose:other"),
            ),
        ),
        replace(request, session_identity=CodingSessionIdentity.from_stable_key("other")),
        replace(request, binding=_contract(worktree="worktree:other").binding),
    )
    expected = (
        CodingSessionLeaseDiagnosticCode.ACTOR_MISMATCH,
        CodingSessionLeaseDiagnosticCode.PURPOSE_MISMATCH,
        CodingSessionLeaseDiagnosticCode.SESSION_MISMATCH,
        CodingSessionLeaseDiagnosticCode.BINDING_MISMATCH,
    )
    for candidate, code in zip(cases, expected):
        assessment = CodingSessionLeaseAssessment.assess(
            candidate, contract, (), CodingSessionLeasePolicy()
        )
        assert code in _codes(assessment)


def test_renewal_creates_new_fact_and_preserves_correspondence() -> None:
    contract = _contract()
    issued = _issue(contract)
    renewal_request = _request(
        contract,
        action=CodingSessionLeaseAction.RENEW,
        interval=CodingSessionLeaseInterval(10, 10, 30),
        previous=issued,
    )
    assessment = CodingSessionLeaseAssessment.assess(
        renewal_request, contract, (issued,), CodingSessionLeasePolicy()
    )
    assert assessment.accepted and assessment.fact is not None
    renewed = assessment.fact
    assert renewed.fact_identity != issued.fact_identity
    assert renewed.lease_identity == issued.lease_identity
    assert renewed.causal_metadata.lineage.parents == (issued.fingerprint,)
    assert issued.interval.expires_at == 20
    assert renewed.interval.expires_at == 30


def test_invalid_renewal_and_unknown_revocation_are_explicit() -> None:
    contract = _contract()
    issued = _issue(contract)
    escalated = replace(
        _request(
            contract,
            action=CodingSessionLeaseAction.RENEW,
            interval=CodingSessionLeaseInterval(10, 10, 30),
            previous=issued,
        ),
        scope=CodingSessionLeaseScope(CodingSessionBindingScope.REPOSITORY),
    )
    invalid = CodingSessionLeaseAssessment.assess(
        escalated, contract, (issued,), CodingSessionLeasePolicy()
    )
    unknown = CodingSessionLeaseAssessment.assess(
        replace(
            _request(contract, action=CodingSessionLeaseAction.REVOKE),
            previous_fact_identity=issued.fact_identity,
            expected_causal_revision=1,
        ),
        contract,
        (),
        CodingSessionLeasePolicy(),
    )
    assert CodingSessionLeaseDiagnosticCode.INVALID_RENEWAL in _codes(invalid)
    assert CodingSessionLeaseDiagnosticCode.UNKNOWN_REVOCATION in _codes(unknown)


def test_revocation_is_append_only_and_removes_active_ownership() -> None:
    contract = _contract()
    issued = _issue(contract)
    request = _request(
        contract,
        action=CodingSessionLeaseAction.REVOKE,
        previous=issued,
    )
    assessment = CodingSessionLeaseAssessment.assess(
        request, contract, (issued,), CodingSessionLeasePolicy()
    )
    assert assessment.accepted and assessment.fact is not None
    revoked = assessment.fact
    projection = CodingSessionOwnershipProjection.project(
        (issued, revoked), observation_time=15, policy=CodingSessionLeasePolicy()
    )
    assert revoked.fact_identity != issued.fact_identity
    assert issued.action is CodingSessionLeaseAction.ISSUE
    assert projection.state is CodingSessionCoordinationState.REVOKED
    assert projection.active_leases == ()


def test_expiry_depends_only_on_explicit_observation_time() -> None:
    fact = _issue(_contract())
    active = CodingSessionOwnershipProjection.project(
        (fact,), observation_time=15, policy=CodingSessionLeasePolicy()
    )
    expired = CodingSessionOwnershipProjection.project(
        (fact,), observation_time=20, policy=CodingSessionLeasePolicy()
    )
    assert active.state is CodingSessionCoordinationState.WRITE_OWNED
    assert expired.state is CodingSessionCoordinationState.UNOWNED
    assert expired.validities[0][1] is CodingSessionLeaseValidity.EXPIRED
    assert fact.interval == CodingSessionLeaseInterval(10, 10, 20)


def test_stale_lease_does_not_satisfy_ownership() -> None:
    contract = _contract()
    issued = _issue(contract)
    request = _request(
        contract,
        action=CodingSessionLeaseAction.MARK_STALE,
        previous=issued,
    )
    assessment = CodingSessionLeaseAssessment.assess(
        request, contract, (issued,), CodingSessionLeasePolicy()
    )
    assert assessment.accepted and assessment.fact is not None
    projection = CodingSessionOwnershipProjection.project(
        (issued, assessment.fact), observation_time=15, policy=CodingSessionLeasePolicy()
    )
    assert projection.state is CodingSessionCoordinationState.STALE
    assert projection.active_leases == ()


def test_incompatible_overlapping_write_leases_conflict_explicitly() -> None:
    first = _issue(_contract("session:one"))
    second = _issue(_contract("session:two"))
    projection = CodingSessionOwnershipProjection.project(
        (second, first), observation_time=15, policy=CodingSessionLeasePolicy()
    )
    assert projection.state is CodingSessionCoordinationState.CONFLICTED
    assert len(projection.conflicts) == 1


def test_compatible_shared_reads_coexist_and_different_bindings_do_not_conflict() -> None:
    first_contract = _contract("session:one", write=False)
    second_contract = _contract("session:two", write=False)
    reads = (
        _issue(
            first_contract,
            capability=CodingSessionLeaseCapability.READ,
            mode=CodingSessionLeaseMode.SHARED,
        ),
        _issue(
            second_contract,
            capability=CodingSessionLeaseCapability.READ,
            mode=CodingSessionLeaseMode.SHARED,
        ),
    )
    read_projection = CodingSessionOwnershipProjection.project(
        reads, observation_time=15, policy=CodingSessionLeasePolicy()
    )
    different = (
        _issue(_contract("session:three", worktree="worktree:one")),
        _issue(_contract("session:four", worktree="worktree:other")),
    )
    different_projection = CodingSessionOwnershipProjection.project(
        different, observation_time=15, policy=CodingSessionLeasePolicy()
    )
    assert read_projection.state is CodingSessionCoordinationState.READ_OWNED
    assert read_projection.conflicts == ()
    assert different_projection.state is CodingSessionCoordinationState.WRITE_OWNED
    assert different_projection.conflicts == ()


def test_projection_detects_duplicate_revision_and_lineage_gap() -> None:
    contract = _contract()
    issued = _issue(contract)
    duplicate = replace(
        issued,
        fact_identity=type(issued.fact_identity).from_stable_key("duplicate"),
    )
    duplicate_projection = CodingSessionOwnershipProjection.project(
        (issued, duplicate), observation_time=15, policy=CodingSessionLeasePolicy()
    )
    assert not duplicate_projection.valid
    assert CodingSessionLeaseDiagnosticCode.DUPLICATE_CAUSAL_REVISION in {
        item.code for item in duplicate_projection.diagnostics
    }
    broken = replace(
        issued,
        causal_metadata=replace(
            issued.causal_metadata,
            revision=CodingSessionCausalRevision(2),
        ),
    )
    lineage_projection = CodingSessionOwnershipProjection.project(
        (broken,), observation_time=15, policy=CodingSessionLeasePolicy()
    )
    assert CodingSessionLeaseDiagnosticCode.LINEAGE_GAP in {
        item.code for item in lineage_projection.diagnostics
    }


def test_projection_is_deterministic_and_occurrence_is_not_semantic() -> None:
    first = _issue(_contract("session:one"))
    second = _issue(_contract("session:two", worktree="worktree:other"))
    left = CodingSessionOwnershipProjection.project(
        (first, second), observation_time=15, policy=CodingSessionLeasePolicy()
    )
    right = CodingSessionOwnershipProjection.project(
        (second, first), observation_time=15, policy=CodingSessionLeasePolicy()
    )
    assert left.evidence_fingerprint == right.evidence_fingerprint

    contract = _contract("session:occurrence")
    first_request = _request(contract, occurrence=(("observed-at", "100"),))
    second_request = replace(
        first_request, occurrence_metadata=(("observed-at", "200"),)
    )
    first_fact = CodingSessionLeaseAssessment.assess(
        first_request, contract, (), CodingSessionLeasePolicy()
    ).fact
    second_fact = CodingSessionLeaseAssessment.assess(
        second_request, contract, (), CodingSessionLeasePolicy()
    ).fact
    assert first_fact is not None and second_fact is not None
    assert first_request.fingerprint == second_request.fingerprint
    assert first_fact.fact_identity == second_fact.fact_identity
    assert first_fact.fingerprint == second_fact.fingerprint


def test_ownership_projection_only_produces_lifecycle_evidence() -> None:
    fact = _issue(_contract())
    projection = CodingSessionOwnershipProjection.project(
        (fact,), observation_time=15, policy=CodingSessionLeasePolicy()
    )
    assert projection.state is CodingSessionCoordinationState.WRITE_OWNED
    assert isinstance(projection.evidence_fingerprint, CodingSessionFingerprint)
    assert not hasattr(projection, "transition")
