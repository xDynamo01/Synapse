from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from synapse.coding_sessions import (
    FENCING_AUTHORITY_VERSION,
    CodingSessionIdentity,
    CodingSessionLeaseFactIdentity,
    CodingSessionRepositoryReference,
    FencingAuthority,
    FencingConflictError,
    FencingOperationClass,
    FencingScope,
    FencingTokenV1,
    FencingTransitionRequest,
    FencingValidationState,
)
from synapse.coding_sessions.fencing_sqlite import (
    FencingSQLiteConfig,
    SQLiteFencingGenerationStore,
)


def _scope(name: str = "one") -> FencingScope:
    return FencingScope(
        CodingSessionIdentity.from_stable_key("session:" + name),
        CodingSessionRepositoryReference(
            "repository-runtime", "repository", "v1", "repository:" + name
        ),
        workspace_reference="workspace:" + name,
    )


def _request(scope: FencingScope, owner: str, key: str, expected: int = 0) -> FencingTransitionRequest:
    return FencingTransitionRequest(
        scope=scope,
        ownership_identity=CodingSessionLeaseFactIdentity.from_stable_key("lease:" + owner),
        authority_identity="coding-sessions:fencing",
        authority_version=FENCING_AUTHORITY_VERSION,
        occurrence_reference="occurrence:" + key,
        idempotency_key="transition:" + key,
        expected_generation=expected,
    )


@pytest.fixture
def store(tmp_path):
    value = SQLiteFencingGenerationStore(FencingSQLiteConfig(str(tmp_path / "fencing.sqlite3")))
    value.migrate()
    return value


def test_scope_requires_mutable_resource_and_typed_hierarchy() -> None:
    with pytest.raises(ValueError):
        FencingScope(CodingSessionIdentity.from_stable_key("session:invalid"))


def test_first_transfer_reacquisition_and_replay_do_not_use_time(store) -> None:
    scope = _scope()
    first = store.transition(_request(scope, "a", "1"))
    second = store.transition(_request(scope, "b", "2", 1))
    third = store.transition(_request(scope, "a", "3", 2))
    assert [first.generation.value, second.generation.value, third.generation.value] == [1, 2, 3]
    assert [fact.generation.value for fact in store.replay(scope)] == [1, 2, 3]
    assert store.latest(scope) == third


def test_idempotency_is_factual_and_contradiction_rejected(store) -> None:
    scope = _scope()
    request = _request(scope, "a", "same")
    assert store.transition(request) == store.transition(request)
    with pytest.raises(FencingConflictError):
        store.transition(replace(request, ownership_identity=CodingSessionLeaseFactIdentity.from_stable_key("lease:b")))


def test_current_stale_future_scope_owner_and_authority_validation(store) -> None:
    scope = _scope()
    authority = FencingAuthority(store)
    old = authority.transition(_request(scope, "a", "1"))
    current = authority.transition(_request(scope, "b", "2", 1))
    args = dict(scope=scope, ownership_identity=current.ownership_identity, authority_identity=current.authority_identity, operation=FencingOperationClass.WORKSPACE_WRITE)
    assert authority.validate(current, **args).state is FencingValidationState.VALID
    assert authority.validate(old, **{**args, "ownership_identity": old.ownership_identity}).state is FencingValidationState.STALE
    future = replace(current, generation=replace(current.generation, value=current.generation.value + 1))
    assert authority.validate(future, **args).state is FencingValidationState.INVALID
    assert authority.validate(current, **{**args, "scope": _scope("other")}).state is FencingValidationState.MISMATCHED
    assert authority.validate(current, **{**args, "ownership_identity": old.ownership_identity}).state is FencingValidationState.MISMATCHED
    assert authority.validate(current, **{**args, "authority_identity": "other:authority"}).state is FencingValidationState.MISMATCHED


def test_read_only_needs_no_token_but_mutation_does(store) -> None:
    authority = FencingAuthority(store)
    scope = _scope()
    common = dict(scope=scope, ownership_identity=None, authority_identity="coding-sessions:fencing")
    assert authority.validate(None, operation=FencingOperationClass.READ_ONLY, **common).accepted
    assert authority.validate(None, operation=FencingOperationClass.WORKER_WRITEBACK, **common).state is FencingValidationState.UNAVAILABLE


def test_restart_history_append_only_and_health(store) -> None:
    scope = _scope()
    first = store.transition(_request(scope, "a", "1"))
    restarted = SQLiteFencingGenerationStore(store._config)
    second = restarted.transition(_request(scope, "b", "2", 1))
    assert (first.generation.value, second.generation.value) == (1, 2)
    assert restarted.health(scope).token_validation_available
    with sqlite3.connect(store._config.database_path) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE fencing_history SET generation=9")
    with sqlite3.connect(store._config.database_path) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM fencing_history")


def test_concurrent_next_generation_is_unique(store) -> None:
    scope = _scope()
    store.transition(_request(scope, "seed", "0"))
    def acquire(index: int):
        try:
            return store.transition(_request(scope, str(index), str(index), 1))
        except FencingConflictError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        facts = list(pool.map(acquire, (1, 2)))
    winners = [fact for fact in facts if fact is not None]
    assert [f.generation.value for f in winners] == [2]
    assert [f.generation.value for f in store.replay(scope)] == [1, 2]


def test_historical_token_remains_immutable_and_becomes_stale(store) -> None:
    authority = FencingAuthority(store)
    scope = _scope()
    historical = authority.transition(_request(scope, "a", "1"))
    authority.transition(_request(scope, "b", "2", 1))
    result = authority.validate(historical, scope=scope, ownership_identity=historical.ownership_identity, authority_identity=historical.authority_identity, operation=FencingOperationClass.ARTIFACT_PUBLICATION)
    assert isinstance(historical, FencingTokenV1)
    assert result.state is FencingValidationState.STALE
