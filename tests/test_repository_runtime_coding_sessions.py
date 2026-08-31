from __future__ import annotations

from dataclasses import replace

import pytest
from tests.test_repository_runtime_change_sets import snapshot
from tests.test_repository_runtime_mutation_plans import CREATE, change_set, plan, policy
from tests.test_repository_runtime_snapshots import identities, profile

from synapse.repository_runtime import (
    RepositoryAuthorizationRequirement,
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryMutationApplicationRequest,
    RepositoryMutationPlanRequest,
    RepositoryObservationRequest,
    RepositoryRecoveryRequest,
    RepositoryWorktreeIdentity,
)
from synapse.repository_runtime_integrations import (
    CodingSessionActor,
    CodingSessionBinding,
    CodingSessionCapability,
    CodingSessionContract,
    CodingSessionCorrelation,
    CodingSessionDiagnosticCode,
    CodingSessionIdentity,
    CodingSessionLeaseMode,
    CodingSessionLeaseScope,
    CodingSessionLifecycle,
    CodingSessionLifecycleFact,
    CodingSessionOwnershipLease,
    CodingSessionProjectReference,
    CodingSessionRepositoryIntentAdapter,
    CodingSessionTask,
    CodingSessionTranslationStatus,
    RepositoryApplicationIntent,
    RepositoryAuthorizationIntent,
    RepositoryMutationPlanningIntent,
    RepositoryObservationIntent,
    RepositoryRecoveryIntent,
)

NOW = 1_800_000_000


def fingerprint(value: str) -> RepositoryFingerprint:
    return RepositoryFingerprint.from_content(value)


def other_identities(key: str):
    repository = RepositoryIdentity.from_stable_key(f"repository-{key}")
    checkout = RepositoryCheckoutIdentity.derive(repository, f"checkout-{key}")
    worktree = RepositoryWorktreeIdentity.derive(checkout, f"worktree-{key}")
    return repository, checkout, worktree


def contract(*, capabilities: tuple[CodingSessionCapability, ...] | None = None):
    repository_id, checkout_id, worktree_id = identities()
    session_id = CodingSessionIdentity.from_stable_key("session-one")
    actor = CodingSessionActor("actor:developer")
    binding = CodingSessionBinding(
        CodingSessionProjectReference("project:synapse"),
        repository_id,
        checkout_id,
        worktree_id,
        profile(),
    )
    session = CodingSessionContract(
        session_id,
        actor,
        binding,
        CodingSessionTask("task:slice-15", "purpose:slice-15"),
        CodingSessionCorrelation("correlation:slice-15"),
        capabilities
        or (
            CodingSessionCapability.OBSERVE,
            CodingSessionCapability.PLAN_MUTATION,
            CodingSessionCapability.REQUEST_AUTHORIZATION,
            CodingSessionCapability.APPLY_MUTATION,
            CodingSessionCapability.REQUEST_RECOVERY,
        ),
        CodingSessionLifecycleFact(session_id, CodingSessionLifecycle.ACTIVE, NOW - 10),
    )
    lease = CodingSessionOwnershipLease(
        "lease:session-one",
        session_id,
        actor,
        session.task.purpose,
        binding,
        CodingSessionLeaseScope.WRITE,
        CodingSessionLeaseMode.EXCLUSIVE,
        NOW - 5,
        NOW + 100,
    )
    return session, lease


def mutation_plan():
    base = snapshot("existing.txt")
    target = snapshot("existing.txt", "new.txt")
    result = plan(base, target, change_set(base, target), policy(CREATE))
    assert result.plan is not None
    return result.plan


def codes(result) -> set[CodingSessionDiagnosticCode]:
    return {item.code for item in result.diagnostics}


def test_observation_translation_is_deterministic_and_reference_only() -> None:
    session, lease = contract()
    intent = RepositoryObservationIntent(session=session, lease=lease, observed_at=NOW)
    adapter = CodingSessionRepositoryIntentAdapter()
    left = adapter.translate(intent)
    right = adapter.translate(intent)
    assert left == right
    assert left.status is CodingSessionTranslationStatus.TRANSLATED
    assert isinstance(left.translated_request, RepositoryObservationRequest)
    assert left.translated_request.repository_id == session.binding.repository_id
    assert not left.authorization_granted
    assert not left.operation_executed


def test_all_neutral_request_types_preserve_exact_binding_and_references() -> None:
    session, lease = contract()
    selected_plan = mutation_plan()
    adapter = CodingSessionRepositoryIntentAdapter()
    planning = adapter.translate(
        RepositoryMutationPlanningIntent(
            session=session,
            lease=lease,
            observed_at=NOW,
            base_snapshot_fingerprint=fingerprint("base"),
            target_snapshot_fingerprint=fingerprint("target"),
            change_set_fingerprint=fingerprint("changes"),
        )
    ).translated_request
    authorization = adapter.translate(
        RepositoryAuthorizationIntent(
            session=session,
            lease=lease,
            observed_at=NOW,
            mutation_plan=selected_plan,
            assessment_time=NOW,
            maximum_fact_age=60,
            accepted_sources=(("source", "issuer", "v1"),),
        )
    ).translated_request
    application = adapter.translate(
        RepositoryApplicationIntent(
            session=session,
            lease=lease,
            observed_at=NOW,
            base_snapshot_fingerprint=fingerprint("base"),
            mutation_plan_fingerprint=fingerprint("plan"),
            authorization_assessment_fingerprint=fingerprint("authorization"),
            restore_point_result_fingerprint=fingerprint("restore"),
            attempt_reference="attempt:slice-15",
        )
    ).translated_request
    recovery = adapter.translate(
        RepositoryRecoveryIntent(
            session=session,
            lease=lease,
            observed_at=NOW,
            base_snapshot_fingerprint=fingerprint("base"),
            mutation_plan_fingerprint=fingerprint("plan"),
            mutation_attempt_fingerprint=fingerprint("attempt"),
            mutation_journal_fingerprint=fingerprint("journal"),
            verification_result_fingerprint=fingerprint("verification"),
            reconciliation_fingerprint=fingerprint("reconciliation"),
            restore_point_manifest_fingerprint=fingerprint("manifest"),
            restore_point_verification_fingerprint=fingerprint("restore-verification"),
            policy_id="recovery-policy",
            policy_version="v1",
            recovery_reference="recovery:slice-15",
        )
    ).translated_request
    assert isinstance(planning, RepositoryMutationPlanRequest)
    assert isinstance(authorization, RepositoryAuthorizationRequirement)
    assert isinstance(application, RepositoryMutationApplicationRequest)
    assert isinstance(recovery, RepositoryRecoveryRequest)
    for request in (planning, application, recovery):
        assert request.repository_id == session.binding.repository_id
        assert request.checkout_id == session.binding.checkout_id
        assert request.worktree_id == session.binding.worktree_id
    assert authorization.actor == session.actor.reference
    assert authorization.mutation_plan_fingerprint == selected_plan.fingerprint


def test_lease_never_becomes_authorization_or_execution() -> None:
    session, lease = contract()
    result = CodingSessionRepositoryIntentAdapter().translate(
        RepositoryApplicationIntent(
            session=session,
            lease=lease,
            observed_at=NOW,
            base_snapshot_fingerprint=fingerprint("base"),
            mutation_plan_fingerprint=fingerprint("plan"),
            authorization_assessment_fingerprint=fingerprint("authorization"),
            restore_point_result_fingerprint=fingerprint("restore"),
            attempt_reference="attempt:explicit",
        )
    )
    assert isinstance(result.translated_request, RepositoryMutationApplicationRequest)
    assert not result.authorization_granted
    assert not result.operation_executed


def test_shared_read_lease_does_not_grant_write() -> None:
    session, lease = contract()
    read_lease = replace(
        lease,
        scope=CodingSessionLeaseScope.READ,
        mode=CodingSessionLeaseMode.SHARED,
    )
    intent = RepositoryApplicationIntent(
        session=session,
        lease=read_lease,
        observed_at=NOW,
        base_snapshot_fingerprint=fingerprint("base"),
        mutation_plan_fingerprint=fingerprint("plan"),
        authorization_assessment_fingerprint=fingerprint("authorization"),
        restore_point_result_fingerprint=fingerprint("restore"),
        attempt_reference="attempt:read-only",
    )
    result = CodingSessionRepositoryIntentAdapter().translate(intent)
    assert result.translated_request is None
    assert CodingSessionDiagnosticCode.LEASE_SCOPE_INSUFFICIENT in codes(result)


def test_incompatible_write_lease_conflict_fails_closed() -> None:
    session, lease = contract()
    other_session = CodingSessionIdentity.from_stable_key("session-two")
    conflicting = replace(
        lease,
        lease_reference="lease:session-two",
        session_id=other_session,
    )
    result = CodingSessionRepositoryIntentAdapter().translate(
        RepositoryObservationIntent(
            session=session,
            lease=lease,
            observed_at=NOW,
            conflicting_leases=(conflicting,),
        )
    )
    assert result.status is CodingSessionTranslationStatus.REJECTED
    assert CodingSessionDiagnosticCode.WRITE_LEASE_CONFLICT in codes(result)


@pytest.mark.parametrize(
    ("change", "expected"),
    (
        ("expired", CodingSessionDiagnosticCode.LEASE_EXPIRED),
        ("revoked", CodingSessionDiagnosticCode.LEASE_REVOKED),
        ("actor", CodingSessionDiagnosticCode.ACTOR_MISMATCH),
        ("purpose", CodingSessionDiagnosticCode.PURPOSE_MISMATCH),
        ("lifecycle", CodingSessionDiagnosticCode.LIFECYCLE_INCOMPATIBLE),
        ("binding", CodingSessionDiagnosticCode.BINDING_MISMATCH),
    ),
)
def test_invalid_ownership_or_lifecycle_is_explicit(change: str, expected) -> None:
    session, lease = contract()
    if change == "expired":
        lease = replace(lease, issued_at=NOW - 100, expires_at=NOW)
    elif change == "revoked":
        lease = replace(lease, revoked=True)
    elif change == "actor":
        lease = replace(lease, actor=CodingSessionActor("actor:other"))
    elif change == "purpose":
        lease = replace(lease, purpose="purpose:other")
    elif change == "lifecycle":
        session = replace(
            session,
            lifecycle=replace(session.lifecycle, state=CodingSessionLifecycle.COMPLETED),
        )
    else:
        other_repository, other_checkout, other_worktree = other_identities("other")
        lease = replace(
            lease,
            binding=replace(
                lease.binding,
                repository_id=other_repository,
                checkout_id=other_checkout,
                worktree_id=other_worktree,
            ),
        )
    result = CodingSessionRepositoryIntentAdapter().translate(
        RepositoryObservationIntent(session=session, lease=lease, observed_at=NOW)
    )
    assert result.translated_request is None
    assert expected in codes(result)


def test_capability_and_plan_correspondence_are_not_inferred() -> None:
    session, lease = contract(capabilities=(CodingSessionCapability.OBSERVE,))
    result = CodingSessionRepositoryIntentAdapter().translate(
        RepositoryMutationPlanningIntent(
            session=session,
            lease=lease,
            observed_at=NOW,
            base_snapshot_fingerprint=fingerprint("base"),
            target_snapshot_fingerprint=fingerprint("target"),
            change_set_fingerprint=fingerprint("changes"),
        )
    )
    assert CodingSessionDiagnosticCode.CAPABILITY_NOT_REQUESTED in codes(result)

    full_session, full_lease = contract()
    selected_plan = mutation_plan()
    other_repository, other_checkout, other_worktree = other_identities("other-plan")
    mismatched = replace(
        selected_plan,
        repository_id=other_repository,
        checkout_id=other_checkout,
        worktree_id=other_worktree,
    )
    authorization = CodingSessionRepositoryIntentAdapter().translate(
        RepositoryAuthorizationIntent(
            session=full_session,
            lease=full_lease,
            observed_at=NOW,
            mutation_plan=mismatched,
            assessment_time=NOW,
            maximum_fact_age=10,
            accepted_sources=(("source", "issuer", "v1"),),
        )
    )
    assert CodingSessionDiagnosticCode.PLAN_MISMATCH in codes(authorization)
    assert authorization.translated_request is None


def test_invalid_or_implicit_identity_and_write_shared_lease_are_impossible() -> None:
    with pytest.raises(ValueError):
        CodingSessionIdentity("current")
    session, lease = contract()
    with pytest.raises(ValueError):
        replace(lease, mode=CodingSessionLeaseMode.SHARED)
