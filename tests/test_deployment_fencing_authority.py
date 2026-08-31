from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from synapse.deployment import (
    DEPLOYMENT_FENCING_AUTHORITY_VERSION,
    CapabilityReference,
    DeploymentFencingAuthority,
    DeploymentFencingConflict,
    DeploymentFencingScopeKind,
    DeploymentFencingScopeV1,
    DeploymentFencingTransitionRequestV1,
    DeploymentFencingValidationState,
    DeploymentFingerprint,
    DeploymentGeneration,
    DeploymentIdempotencyContradiction,
    DeploymentIdempotencyDisposition,
    DeploymentIdempotencyKey,
    DeploymentIdempotencyRequestV1,
    DeploymentMutationClass,
    DeploymentTargetId,
    OccurrenceReference,
    ReleaseId,
    RequesterReference,
    RevisionId,
    RollbackAttemptId,
    RolloutId,
    SlotId,
    replay_generation_history,
)
from synapse.deployment_adapters import (
    DeploymentSQLiteConfig,
    SQLiteDeploymentAuthorityStore,
    SQLiteDeploymentJournalStore,
)


def _store(tmp_path) -> SQLiteDeploymentAuthorityStore:
    store = SQLiteDeploymentAuthorityStore(
        DeploymentSQLiteConfig((tmp_path / "deployment.sqlite3").resolve())
    )
    store.initialize()
    return store


def _latest(
    store: SQLiteDeploymentAuthorityStore, scope: DeploymentFencingScopeV1
):
    fact = store.latest(scope)
    assert fact is not None
    return fact


def _scope(kind: DeploymentFencingScopeKind = DeploymentFencingScopeKind.TARGET) -> DeploymentFencingScopeV1:
    if kind is DeploymentFencingScopeKind.RELEASE:
        return DeploymentFencingScopeV1(kind, release_id=ReleaseId("deployment-release:fence"))
    if kind is DeploymentFencingScopeKind.TARGET:
        return DeploymentFencingScopeV1(kind, target_id=DeploymentTargetId("deployment-target:fence"))
    if kind is DeploymentFencingScopeKind.TARGET_SLOT:
        return DeploymentFencingScopeV1(
            kind, target_id=DeploymentTargetId("deployment-target:fence"),
            slot_id=SlotId("deployment-slot:primary"),
        )
    if kind is DeploymentFencingScopeKind.ROLLOUT:
        return DeploymentFencingScopeV1(
            kind, release_id=ReleaseId("deployment-release:fence"),
            rollout_id=RolloutId("deployment-rollout:fence"),
        )
    return DeploymentFencingScopeV1(
        kind,
        release_id=ReleaseId("deployment-release:fence"),
        target_id=DeploymentTargetId("deployment-target:fence"),
        rollback_attempt_id=RollbackAttemptId("deployment-rollback-attempt:fence"),
        source_revision=RevisionId("deployment-revision:new"),
        intended_revision=RevisionId("deployment-revision:old"),
    )


def _transition(
    scope: DeploymentFencingScopeV1,
    expected: int,
    occurrence: str,
    owner: str = "owner:one",
    binding: DeploymentFingerprint | None = None,
) -> DeploymentFencingTransitionRequestV1:
    return DeploymentFencingTransitionRequestV1(
        scope,
        RequesterReference(owner),
        CapabilityReference("authority:deployment-fencing"),
        expected,
        OccurrenceReference(occurrence),
        binding,
    )


def test_first_next_transfer_and_reacquisition_are_monotonic(tmp_path) -> None:
    store = _store(tmp_path)
    scope = _scope()
    first = store.transition(_transition(scope, 0, "occurrence:first"))
    transfer = store.transition(_transition(scope, 1, "occurrence:transfer", "owner:two"))
    reacquired = store.transition(_transition(scope, 2, "occurrence:reacquire"))
    assert [fact.generation.value for fact in store.history(scope)] == [1, 2, 3]
    assert first.generation == DeploymentGeneration(1)
    assert transfer.owner == RequesterReference("owner:two")
    assert reacquired.owner == RequesterReference("owner:one")


@pytest.mark.parametrize("kind", tuple(DeploymentFencingScopeKind))
def test_all_scopes_are_typed_and_isolated(tmp_path, kind: DeploymentFencingScopeKind) -> None:
    store = _store(tmp_path)
    fact = store.transition(_transition(_scope(kind), 0, f"occurrence:{kind.value}"))
    assert fact.scope.kind is kind
    assert fact.generation.value == 1


def test_scope_isolation_does_not_use_one_global_generation(tmp_path) -> None:
    store = _store(tmp_path)
    target = store.transition(_transition(_scope(), 0, "occurrence:target"))
    release = store.transition(
        _transition(_scope(DeploymentFencingScopeKind.RELEASE), 0, "occurrence:release")
    )
    assert target.generation.value == release.generation.value == 1


def test_generation_validation_rejects_zero_bool_negative_and_overflow() -> None:
    for value in (0, -1, True, 2**64):
        with pytest.raises(ValueError):
            DeploymentGeneration(value)


def test_compare_and_advance_conflict_and_no_regression(tmp_path) -> None:
    store = _store(tmp_path)
    scope = _scope()
    store.transition(_transition(scope, 0, "occurrence:first"))
    with pytest.raises(DeploymentFencingConflict):
        store.transition(_transition(scope, 0, "occurrence:stale-writer"))
    assert _latest(store, scope).generation.value == 1


def test_concurrent_transition_allows_exactly_one_next_generation(tmp_path) -> None:
    store = _store(tmp_path)
    scope = _scope()
    store.transition(_transition(scope, 0, "occurrence:first"))

    def acquire(index: int) -> str:
        try:
            store.transition(_transition(scope, 1, f"occurrence:race-{index}", f"owner:{index}"))
            return "won"
        except DeploymentFencingConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(acquire, (1, 2)))
    assert sorted(outcomes) == ["conflict", "won"]
    assert [fact.generation.value for fact in store.history(scope)] == [1, 2]


def test_current_stale_future_and_historical_tokens_are_factual(tmp_path) -> None:
    store = _store(tmp_path)
    authority = DeploymentFencingAuthority(store)
    scope = _scope()
    binding = DeploymentFingerprint("sha256:" + "a" * 64)
    first = authority.transition(_transition(scope, 0, "occurrence:first", binding=binding))
    current = authority.validate(
        first, scope=scope, owner=first.owner,
        authority_identity=first.authority_identity,
        operation=DeploymentMutationClass.APPLY_REQUEST,
        semantic_binding_fingerprint=binding,
    )
    assert current.state is DeploymentFencingValidationState.VALID
    authority.transition(_transition(scope, 1, "occurrence:transfer", "owner:two", binding))
    stale = authority.validate(
        first, scope=scope, owner=first.owner,
        authority_identity=first.authority_identity,
        operation=DeploymentMutationClass.APPLY_REQUEST,
        semantic_binding_fingerprint=binding,
    )
    assert stale.state is DeploymentFencingValidationState.STALE
    future = replace(first, generation=DeploymentGeneration(3))
    assert authority.validate(
        future, scope=scope, owner=future.owner,
        authority_identity=future.authority_identity,
        operation=DeploymentMutationClass.APPLY_REQUEST,
        semantic_binding_fingerprint=binding,
    ).state is DeploymentFencingValidationState.INVALID


@pytest.mark.parametrize("mismatch", ["scope", "owner", "authority", "binding"])
def test_wrong_scope_owner_authority_or_binding_is_mismatched(tmp_path, mismatch: str) -> None:
    store = _store(tmp_path)
    authority = DeploymentFencingAuthority(store)
    scope = _scope()
    binding = DeploymentFingerprint("sha256:" + "b" * 64)
    token = authority.transition(_transition(scope, 0, "occurrence:first", binding=binding))
    candidate_scope = scope
    candidate_owner = token.owner
    candidate_authority = token.authority_identity
    candidate_binding = binding
    if mismatch == "scope":
        candidate_scope = _scope(DeploymentFencingScopeKind.RELEASE)
    elif mismatch == "owner":
        candidate_owner = RequesterReference("owner:other")
    elif mismatch == "authority":
        candidate_authority = CapabilityReference("authority:other")
    else:
        candidate_binding = DeploymentFingerprint("sha256:" + "c" * 64)
    result = authority.validate(
        token,
        scope=candidate_scope,
        owner=candidate_owner,
        authority_identity=candidate_authority,
        operation=DeploymentMutationClass.APPLY_REQUEST,
        semantic_binding_fingerprint=candidate_binding,
    )
    assert result.state is DeploymentFencingValidationState.MISMATCHED


def test_missing_generation_is_unavailable_and_read_only_needs_no_token(tmp_path) -> None:
    authority = DeploymentFencingAuthority(_store(tmp_path))
    scope = _scope()
    missing = authority.validate(
        None, scope=scope, owner=None,
        authority_identity=CapabilityReference("authority:deployment-fencing"),
        operation=DeploymentMutationClass.APPLY_REQUEST,
    )
    readonly = authority.validate(
        None, scope=scope, owner=None,
        authority_identity=CapabilityReference("authority:deployment-fencing"),
        operation=DeploymentMutationClass.READ_ONLY_OBSERVATION,
    )
    assert missing.state is DeploymentFencingValidationState.UNAVAILABLE
    assert readonly.accepted


def test_token_does_not_authorize_and_external_revisions_are_not_generation(tmp_path) -> None:
    authority = DeploymentFencingAuthority(_store(tmp_path))
    token = authority.transition(_transition(_scope(), 0, "occurrence:first"))
    assert not token.authorized
    assert token.generation != "approvals-schema:1"
    assert token.authority_version == DEPLOYMENT_FENCING_AUTHORITY_VERSION
    assert "coding-session" not in token.authority_version


def _idempotency(scope: DeploymentFencingScopeV1, suffix: str = "one") -> DeploymentIdempotencyRequestV1:
    return DeploymentIdempotencyRequestV1(
        DeploymentMutationClass.APPLY_REQUEST,
        scope,
        DeploymentIdempotencyKey(f"deployment-idempotency:{suffix}"),
        DeploymentFingerprint("sha256:" + "d" * 64),
        OccurrenceReference(f"occurrence:idempotency-{suffix}"),
    )


def test_idempotency_same_key_same_semantics_and_contradiction(tmp_path) -> None:
    store = _store(tmp_path)
    authority = DeploymentFencingAuthority(store)
    scope = _scope()
    request = _idempotency(scope)
    token = authority.transition(
        _transition(scope, 0, "occurrence:first", binding=request.semantic_fingerprint)
    )
    first = authority.accept_operation(
        request, token, owner=token.owner, authority_identity=token.authority_identity
    )
    duplicate = authority.accept_operation(
        request, token, owner=token.owner, authority_identity=token.authority_identity
    )
    assert first.disposition is DeploymentIdempotencyDisposition.RECORDED
    assert duplicate.disposition is DeploymentIdempotencyDisposition.IDEMPOTENT
    with pytest.raises(DeploymentIdempotencyContradiction):
        store.record_idempotency(
            replace(request, semantic_fingerprint=DeploymentFingerprint("sha256:" + "e" * 64)),
            token.generation,
        )


def test_same_idempotency_key_with_stale_fencing_remains_stale(tmp_path) -> None:
    store = _store(tmp_path)
    authority = DeploymentFencingAuthority(store)
    scope = _scope()
    request = _idempotency(scope)
    first = authority.transition(
        _transition(scope, 0, "occurrence:first", binding=request.semantic_fingerprint)
    )
    authority.accept_operation(
        request, first, owner=first.owner, authority_identity=first.authority_identity
    )
    authority.transition(
        _transition(scope, 1, "occurrence:transfer", "owner:two", request.semantic_fingerprint)
    )
    rejected = authority.accept_operation(
        request, first, owner=first.owner, authority_identity=first.authority_identity
    )
    assert rejected.disposition is DeploymentIdempotencyDisposition.FENCING_REJECTED
    assert rejected.fencing.state is DeploymentFencingValidationState.STALE


def test_idempotency_identity_is_operation_scope_and_key(tmp_path) -> None:
    store = _store(tmp_path)
    authority = DeploymentFencingAuthority(store)
    target_request = _idempotency(_scope())
    release_request = replace(
        target_request, scope=_scope(DeploymentFencingScopeKind.RELEASE)
    )
    for request, occurrence in (
        (target_request, "occurrence:target"),
        (release_request, "occurrence:release"),
    ):
        token = authority.transition(
            _transition(
                request.scope,
                0,
                occurrence,
                binding=request.semantic_fingerprint,
            )
        )
        accepted = authority.accept_operation(
            request,
            token,
            owner=token.owner,
            authority_identity=token.authority_identity,
        )
        assert accepted.disposition is DeploymentIdempotencyDisposition.RECORDED


def test_restart_preserves_generation_and_idempotency_without_external_apply(tmp_path) -> None:
    store = _store(tmp_path)
    scope = _scope()
    request = _idempotency(scope)
    authority = DeploymentFencingAuthority(store)
    token = authority.transition(
        _transition(scope, 0, "occurrence:first", binding=request.semantic_fingerprint)
    )
    authority.accept_operation(
        request, token, owner=token.owner, authority_identity=token.authority_identity
    )
    reopened = _store(tmp_path)
    assert _latest(reopened, scope).generation.value == 1
    assert reopened.idempotency_record(request) is not None
    next_fact = reopened.transition(_transition(scope, 1, "occurrence:after-restart"))
    assert next_fact.generation.value == 2
    assert not hasattr(reopened, "apply")


def test_replay_is_read_only_and_does_not_advance_generation(tmp_path) -> None:
    store = _store(tmp_path)
    scope = _scope()
    store.transition(_transition(scope, 0, "occurrence:first"))
    facts = store.history(scope)
    assert replay_generation_history(facts) == facts[-1]
    assert _latest(store, scope).generation.value == 1


def test_append_only_triggers_block_update_delete_and_health_fails_closed(tmp_path) -> None:
    store = _store(tmp_path)
    scope = _scope()
    authority = DeploymentFencingAuthority(store)
    request = _idempotency(scope)
    token = authority.transition(
        _transition(scope, 0, "occurrence:first", binding=request.semantic_fingerprint)
    )
    authority.accept_operation(
        request, token, owner=token.owner, authority_identity=token.authority_identity
    )
    path = store.database_path
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE deployment_fencing_history SET generation=2")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM deployment_fencing_history")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM deployment_idempotency_facts")
        connection.execute("DROP TRIGGER deployment_fencing_no_update")
    health = store.health()
    assert health.corruption_detected
    assert not health.monotonicity_integrity
    assert not health.end_to_end_enforced


def test_journal_and_authority_share_database_without_mixing_histories(tmp_path) -> None:
    store = _store(tmp_path)
    journal = SQLiteDeploymentJournalStore(
        DeploymentSQLiteConfig(store.database_path)
    )
    assert journal.health().store_available
    assert store.history(_scope()) == ()
