from dataclasses import dataclass, replace

import pytest

from synapse.repository_runtime import (
    InvalidRepositoryModel,
    InvalidRepositoryPath,
    RepositoryCaseSensitivity,
    RepositoryCheckout,
    RepositoryCheckoutIdentity,
    RepositoryGitTracking,
    RepositoryHeadKind,
    RepositoryHeadState,
    RepositoryIdentity,
    RepositoryIndexPresence,
    RepositoryIndexState,
    RepositoryMaterialRole,
    RepositoryObservation,
    RepositoryObservationCompleteness,
    RepositoryPath,
    RepositoryPathClassification,
    RepositoryPathObservation,
    RepositoryPlatformKind,
    RepositoryPlatformProfile,
    RepositorySensitivity,
    RepositoryTopology,
    RepositoryUnicodeNormalization,
    RepositoryWorkspaceState,
    RepositoryWorkspaceStatus,
    RepositoryWorktree,
    RepositoryWorktreeIdentity,
    canonical_bytes,
)


def profile(
    *,
    case: RepositoryCaseSensitivity = RepositoryCaseSensitivity.SENSITIVE,
    unicode: RepositoryUnicodeNormalization = RepositoryUnicodeNormalization.NFC,
) -> RepositoryPlatformProfile:
    return RepositoryPlatformProfile(RepositoryPlatformKind.WINDOWS, case, unicode)


def identities() -> tuple[
    RepositoryIdentity, RepositoryCheckoutIdentity, RepositoryWorktreeIdentity
]:
    repository = RepositoryIdentity.from_stable_key("repository-key-1")
    checkout = RepositoryCheckoutIdentity.derive(repository, "checkout-key-1")
    worktree = RepositoryWorktreeIdentity.derive(checkout, "worktree-key-1")
    return repository, checkout, worktree


def classification(
    tracking: RepositoryGitTracking = RepositoryGitTracking.TRACKED,
    role: RepositoryMaterialRole = RepositoryMaterialRole.SOURCE,
    topology: RepositoryTopology = RepositoryTopology.REGULAR,
) -> RepositoryPathClassification:
    return RepositoryPathClassification(
        tracking, role, RepositorySensitivity.NORMAL, topology
    )


def observation(paths: tuple[RepositoryPathObservation, ...] = ()) -> RepositoryObservation:
    repository, checkout, worktree = identities()
    return RepositoryObservation(
        repository,
        checkout,
        worktree,
        RepositoryHeadState(RepositoryHeadKind.NAMED_BRANCH, "main", "abcd1234"),
        RepositoryIndexState(RepositoryIndexPresence.PRESENT),
        RepositoryWorkspaceState(
            RepositoryWorkspaceStatus.DIRTY, RepositoryObservationCompleteness.COMPLETE
        ),
        RepositoryObservationCompleteness.COMPLETE,
        paths,
    )


def test_repository_checkout_and_worktree_are_distinct_typed_identities() -> None:
    repository, checkout, worktree = identities()
    assert repository != checkout
    assert checkout != worktree
    assert RepositoryCheckout(checkout, repository).repository_id == repository
    assert RepositoryWorktree(worktree, checkout, repository).checkout_id == checkout


def test_identity_subtypes_reject_another_identity_kind() -> None:
    _, checkout, _ = identities()
    with pytest.raises(ValueError):
        RepositoryIdentity(checkout.value)


def test_repository_identity_excludes_branch_head_remote_path_and_occurrence() -> None:
    repository = RepositoryIdentity.from_stable_key("stable-admitted-key")

    @dataclass(frozen=True)
    class Occurrence:
        repository_id: RepositoryIdentity
        branch: str
        head: str
        remote: str
        developer_path: str
        observed_at: str

    first = Occurrence(repository, "main", "a", "remote-a", "path-a", "time-a")
    second = Occurrence(repository, "topic", "b", "remote-b", "path-b", "time-b")
    assert first.repository_id == second.repository_id


def test_checkout_and_worktree_keys_change_only_their_own_identity() -> None:
    repository, checkout, _ = identities()
    other_checkout = RepositoryCheckoutIdentity.derive(repository, "checkout-key-2")
    assert other_checkout != checkout
    assert RepositoryWorktreeIdentity.derive(checkout, "one") != RepositoryWorktreeIdentity.derive(
        checkout, "two"
    )


@pytest.mark.parametrize(
    ("state", "branch", "commit"),
    [
        (RepositoryHeadKind.NAMED_BRANCH, "main", "abcd"),
        (RepositoryHeadKind.DETACHED, None, "abcd"),
        (RepositoryHeadKind.UNBORN_BRANCH, "main", None),
        (RepositoryHeadKind.ABSENT, None, None),
    ],
)
def test_head_states_are_explicit(
    state: RepositoryHeadKind, branch: str | None, commit: str | None
) -> None:
    head = RepositoryHeadState(state, branch, commit)
    assert head.branch_name == branch


def test_detached_head_cannot_claim_an_implicit_branch() -> None:
    with pytest.raises(InvalidRepositoryModel):
        RepositoryHeadState(RepositoryHeadKind.DETACHED, "main", "abcd")


@pytest.mark.parametrize(
    "presence",
    list(RepositoryIndexPresence),
)
def test_index_presence_is_closed_and_explicit(presence: RepositoryIndexPresence) -> None:
    assert RepositoryIndexState(presence).presence is presence


@pytest.mark.parametrize(
    "completeness",
    [
        RepositoryObservationCompleteness.PARTIAL,
        RepositoryObservationCompleteness.UNAVAILABLE,
        RepositoryObservationCompleteness.UNSUPPORTED,
        RepositoryObservationCompleteness.UNKNOWN,
        RepositoryObservationCompleteness.NOT_REQUIRED,
    ],
)
def test_incomplete_observation_never_produces_clean(
    completeness: RepositoryObservationCompleteness,
) -> None:
    with pytest.raises(InvalidRepositoryModel):
        RepositoryWorkspaceState(RepositoryWorkspaceStatus.CLEAN, completeness)


def test_tracking_and_material_role_are_independent_axes() -> None:
    ignored_source = classification(
        RepositoryGitTracking.IGNORED, RepositoryMaterialRole.SOURCE
    )
    tracked_generated = classification(
        RepositoryGitTracking.TRACKED, RepositoryMaterialRole.GENERATED
    )
    assert ignored_source.material_role is RepositoryMaterialRole.SOURCE
    assert tracked_generated.material_role is RepositoryMaterialRole.GENERATED


@pytest.mark.parametrize(
    "topology",
    [RepositoryTopology.SUBMODULE, RepositoryTopology.NESTED_REPOSITORY],
)
def test_repository_topologies_never_grant_implicit_traversal(
    topology: RepositoryTopology,
) -> None:
    assert not classification(topology=topology).allows_implicit_traversal


@pytest.mark.parametrize(
    "value",
    ["", "/absolute", "C:/absolute", "../escape", "a/../escape", "a\\b", "a//b", "a/"],
)
def test_invalid_paths_fail_closed(value: str) -> None:
    _, checkout, worktree = identities()
    with pytest.raises(InvalidRepositoryPath):
        RepositoryPath(value, profile(), checkout, worktree)


def test_case_and_unicode_semantics_require_and_follow_explicit_profile() -> None:
    _, checkout, worktree = identities()
    sensitive = RepositoryPath("Src/Caf\N{LATIN SMALL LETTER E WITH ACUTE}.py", profile(), checkout, worktree)
    insensitive = RepositoryPath(
        "Src/Cafe\N{COMBINING ACUTE ACCENT}.py",
        profile(case=RepositoryCaseSensitivity.INSENSITIVE),
        checkout,
        worktree,
    )
    assert sensitive.value == "Src/Caf\N{LATIN SMALL LETTER E WITH ACUTE}.py"
    assert insensitive.value == "src/caf\N{LATIN SMALL LETTER E WITH ACUTE}.py"


def test_collection_order_does_not_change_canonical_form_or_fingerprint() -> None:
    _, checkout, worktree = identities()
    a = RepositoryPathObservation(
        RepositoryPath("a.py", profile(), checkout, worktree), classification()
    )
    b = RepositoryPathObservation(
        RepositoryPath("b.py", profile(), checkout, worktree), classification()
    )
    first = observation((a, b))
    second = observation((b, a))
    assert canonical_bytes(first) == canonical_bytes(second)
    assert first.fingerprint == second.fingerprint


def test_occurrence_metadata_is_not_part_of_semantic_observation_identity() -> None:
    base = observation()

    @dataclass(frozen=True)
    class RecordedObservation:
        semantic: RepositoryObservation
        observed_at: str

    early = RecordedObservation(base, "2026-01-01T00:00:00Z")
    late = replace(early, observed_at="2026-02-01T00:00:00Z")
    assert early.semantic.fingerprint == late.semantic.fingerprint
