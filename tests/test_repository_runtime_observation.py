from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.repository_runtime import (
    InvalidRepositoryObservationFacts,
    RepositoryCaseSensitivity,
    RepositoryCheckout,
    RepositoryCheckoutIdentity,
    RepositoryDimensionCompleteness,
    RepositoryEntryStatus,
    RepositoryGitTracking,
    RepositoryHeadKind,
    RepositoryHeadState,
    RepositoryIdentity,
    RepositoryIndexPresence,
    RepositoryIndexState,
    RepositoryMaterialRole,
    RepositoryObservationCompleteness,
    RepositoryObservationDiagnosticCode,
    RepositoryObservationDimension,
    RepositoryObservationFacts,
    RepositoryObservationOutcome,
    RepositoryObservationRequest,
    RepositoryObservationService,
    RepositoryObservationSource,
    RepositoryObservedEntry,
    RepositoryPath,
    RepositoryPathClassification,
    RepositoryPlatformKind,
    RepositoryPlatformProfile,
    RepositoryPresence,
    RepositorySensitivity,
    RepositoryTopology,
    RepositoryUnicodeNormalization,
    RepositoryWorkspaceStatus,
    RepositoryWorktree,
    RepositoryWorktreeIdentity,
    canonical_bytes,
)


def profile() -> RepositoryPlatformProfile:
    return RepositoryPlatformProfile(
        RepositoryPlatformKind.WINDOWS,
        RepositoryCaseSensitivity.INSENSITIVE,
        RepositoryUnicodeNormalization.NFC,
    )


def identities() -> tuple[
    RepositoryIdentity, RepositoryCheckoutIdentity, RepositoryWorktreeIdentity
]:
    repository = RepositoryIdentity.from_stable_key("repository-1")
    checkout = RepositoryCheckoutIdentity.derive(repository, "checkout-1")
    worktree = RepositoryWorktreeIdentity.derive(checkout, "worktree-1")
    return repository, checkout, worktree


def request(*, with_worktree: bool = True) -> RepositoryObservationRequest:
    repository, checkout, worktree = identities()
    return RepositoryObservationRequest(
        repository, checkout, worktree if with_worktree else None, profile()
    )


def complete_dimensions(
    *, with_worktree: bool = True
) -> tuple[RepositoryDimensionCompleteness, ...]:
    return tuple(
        RepositoryDimensionCompleteness(
            dimension,
            RepositoryObservationCompleteness.COMPLETE
            if dimension is not RepositoryObservationDimension.WORKTREE or with_worktree
            else RepositoryObservationCompleteness.NOT_REQUIRED,
        )
        for dimension in RepositoryObservationDimension
    )


def classification(
    tracking: RepositoryGitTracking = RepositoryGitTracking.TRACKED,
    role: RepositoryMaterialRole = RepositoryMaterialRole.SOURCE,
    topology: RepositoryTopology = RepositoryTopology.REGULAR,
) -> RepositoryPathClassification:
    return RepositoryPathClassification(
        tracking, role, RepositorySensitivity.NORMAL, topology
    )


def entry(
    name: str,
    *,
    tracking: RepositoryGitTracking = RepositoryGitTracking.TRACKED,
    role: RepositoryMaterialRole = RepositoryMaterialRole.SOURCE,
    topology: RepositoryTopology = RepositoryTopology.REGULAR,
    status: RepositoryEntryStatus = RepositoryEntryStatus.UNCHANGED,
    content_observed: bool = True,
    descendants_observed: bool = False,
) -> RepositoryObservedEntry:
    _, checkout, worktree = identities()
    return RepositoryObservedEntry(
        RepositoryPath(name, profile(), checkout, worktree),
        classification(tracking, role, topology),
        status,
        content_observed,
        descendants_observed,
    )


def facts(
    *,
    entries: tuple[RepositoryObservedEntry, ...] = (),
    dimensions: tuple[RepositoryDimensionCompleteness, ...] | None = None,
    workspace: RepositoryWorkspaceStatus = RepositoryWorkspaceStatus.CLEAN,
    head: RepositoryHeadState | None = None,
    branch_reference: str | None = "main",
    object_reference: str | None = "abcd1234",
    index: RepositoryIndexState | None = None,
    staged_paths: tuple[RepositoryPath, ...] = (),
    occurred_at: datetime | None = None,
) -> RepositoryObservationFacts:
    repository, checkout, worktree = identities()
    return RepositoryObservationFacts(
        RepositoryObservationSource(
            "neutral-observer",
            "v1",
            occurred_at or datetime(2026, 8, 3, tzinfo=UTC),
        ),
        RepositoryPresence.PRESENT,
        repository,
        RepositoryCheckout(checkout, repository),
        RepositoryWorktree(worktree, checkout, repository),
        profile(),
        head or RepositoryHeadState(RepositoryHeadKind.NAMED_BRANCH, "main", "abcd1234"),
        branch_reference,
        object_reference,
        index or RepositoryIndexState(RepositoryIndexPresence.PRESENT),
        workspace,
        entries,
        staged_paths,
        dimensions or complete_dimensions(),
    )


def assess(
    supplied: RepositoryObservationFacts, *, requested: RepositoryObservationRequest | None = None
):
    return RepositoryObservationService().assess(requested or request(), supplied)


def codes(result: object) -> set[RepositoryObservationDiagnosticCode]:
    assert hasattr(result, "assessment")
    return {item.code for item in result.assessment.diagnostics}


def test_complete_corresponding_facts_materialize_canonical_observation() -> None:
    untracked = entry(
        "scratch.txt",
        tracking=RepositoryGitTracking.UNTRACKED,
        role=RepositoryMaterialRole.UNKNOWN,
        status=RepositoryEntryStatus.ADDED,
    )
    result = assess(facts(entries=(untracked,), workspace=RepositoryWorkspaceStatus.DIRTY))
    assert result.assessment.outcome is RepositoryObservationOutcome.SATISFIED
    assert result.observation is not None
    assert result.observation.paths[0].classification.tracking is RepositoryGitTracking.UNTRACKED


def test_observation_is_factual_and_has_no_mutation_authority_surface() -> None:
    result = assess(facts())
    assert result.observation is not None
    assert not hasattr(result, "authorize")
    assert not hasattr(result.observation, "apply")


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("repository", RepositoryObservationDiagnosticCode.REPOSITORY_IDENTITY_MISMATCH),
        ("checkout", RepositoryObservationDiagnosticCode.CHECKOUT_BINDING_MISMATCH),
        ("worktree", RepositoryObservationDiagnosticCode.WORKTREE_BINDING_MISMATCH),
        ("platform", RepositoryObservationDiagnosticCode.PLATFORM_PROFILE_MISMATCH),
    ],
)
def test_identity_and_platform_correspondence_is_exact(
    field: str, code: RepositoryObservationDiagnosticCode
) -> None:
    supplied = facts()
    other_repository = RepositoryIdentity.from_stable_key("other-repository")
    if field == "repository":
        supplied = replace(supplied, repository_id=other_repository)
    elif field == "checkout":
        other_checkout = RepositoryCheckoutIdentity.derive(other_repository, "other-checkout")
        supplied = replace(supplied, checkout=RepositoryCheckout(other_checkout, other_repository))
    elif field == "worktree":
        other_checkout = RepositoryCheckoutIdentity.derive(other_repository, "other-checkout")
        other_worktree = RepositoryWorktreeIdentity.derive(other_checkout, "other-worktree")
        supplied = replace(
            supplied,
            worktree=RepositoryWorktree(other_worktree, other_checkout, other_repository),
        )
    else:
        supplied = replace(
            supplied,
            platform_profile=RepositoryPlatformProfile(
                RepositoryPlatformKind.POSIX,
                RepositoryCaseSensitivity.SENSITIVE,
                RepositoryUnicodeNormalization.PRESERVE,
            ),
        )
    result = assess(supplied)
    assert result.assessment.outcome is RepositoryObservationOutcome.MISMATCH
    assert code in codes(result)
    assert result.observation is None


def test_detached_head_rejects_branch_reference() -> None:
    result = assess(
        facts(
            head=RepositoryHeadState(RepositoryHeadKind.DETACHED, None, "abcd1234"),
            branch_reference="main",
        )
    )
    assert result.assessment.outcome is RepositoryObservationOutcome.CONTRADICTORY
    assert RepositoryObservationDiagnosticCode.HEAD_BRANCH_CONTRADICTION in codes(result)


def test_unborn_branch_remains_distinct_from_absent_head() -> None:
    unborn = assess(
        facts(
            head=RepositoryHeadState(RepositoryHeadKind.UNBORN_BRANCH, "main", None),
            branch_reference="main",
            object_reference=None,
        )
    )
    absent = assess(
        facts(
            head=RepositoryHeadState(RepositoryHeadKind.ABSENT, None, None),
            branch_reference=None,
            object_reference=None,
        )
    )
    assert unborn.observation is not None and absent.observation is not None
    assert unborn.observation.head.kind is RepositoryHeadKind.UNBORN_BRANCH
    assert absent.observation.head.kind is RepositoryHeadKind.ABSENT


@pytest.mark.parametrize(
    ("state", "outcome"),
    [
        (RepositoryObservationCompleteness.PARTIAL, RepositoryObservationOutcome.INCOMPLETE),
        (RepositoryObservationCompleteness.UNKNOWN, RepositoryObservationOutcome.INCOMPLETE),
        (RepositoryObservationCompleteness.UNAVAILABLE, RepositoryObservationOutcome.UNAVAILABLE),
        (RepositoryObservationCompleteness.UNSUPPORTED, RepositoryObservationOutcome.UNSUPPORTED),
    ],
)
def test_non_complete_dimension_never_materializes_clean(
    state: RepositoryObservationCompleteness, outcome: RepositoryObservationOutcome
) -> None:
    dimensions = tuple(
        replace(item, state=state)
        if item.dimension is RepositoryObservationDimension.PATHS
        else item
        for item in complete_dimensions()
    )
    result = assess(facts(dimensions=dimensions))
    assert result.assessment.outcome is outcome
    assert result.observation is None
    assert RepositoryObservationDiagnosticCode.CLEAN_WITH_INCOMPLETE_OBSERVATION in codes(result)


def test_not_required_is_valid_only_for_absent_requested_worktree() -> None:
    dimensions = complete_dimensions(with_worktree=False)
    supplied = replace(facts(dimensions=dimensions), worktree=None)
    result = assess(supplied, requested=request(with_worktree=False))
    assert result.assessment.outcome is RepositoryObservationOutcome.SATISFIED
    invalid = assess(facts(dimensions=dimensions))
    assert invalid.assessment.outcome is RepositoryObservationOutcome.MISMATCH
    assert RepositoryObservationDiagnosticCode.NOT_REQUIRED_INVALID in codes(invalid)


def test_clean_with_changed_or_conflicted_entries_fails_closed() -> None:
    modified = entry("modified.py", status=RepositoryEntryStatus.MODIFIED)
    conflicted = entry("conflicted.py", status=RepositoryEntryStatus.CONFLICTED)
    result = assess(facts(entries=(modified, conflicted)))
    assert result.assessment.outcome is RepositoryObservationOutcome.CONTRADICTORY
    assert RepositoryObservationDiagnosticCode.CLEAN_WITH_CHANGES in codes(result)
    assert RepositoryObservationDiagnosticCode.CLEAN_WITH_CONFLICTS in codes(result)


def test_index_absent_rejects_staging_facts() -> None:
    staged = entry("staged.py").path
    result = assess(
        facts(
            index=RepositoryIndexState(RepositoryIndexPresence.ABSENT),
            staged_paths=(staged,),
        )
    )
    assert RepositoryObservationDiagnosticCode.INDEX_ABSENT_WITH_STAGING in codes(result)


def test_incompatible_duplicate_path_facts_fail_closed() -> None:
    first = entry("same.py")
    second = replace(first, classification=classification(RepositoryGitTracking.IGNORED))
    result = assess(facts(entries=(first, second), workspace=RepositoryWorkspaceStatus.DIRTY))
    assert result.assessment.outcome is RepositoryObservationOutcome.CONTRADICTORY
    assert RepositoryObservationDiagnosticCode.PATH_FACT_CONFLICT in codes(result)


def test_ignored_and_generated_remain_independent() -> None:
    ignored_source = entry(
        "ignored-source.py",
        tracking=RepositoryGitTracking.IGNORED,
        role=RepositoryMaterialRole.SOURCE,
    )
    tracked_generated = entry(
        "generated.py",
        tracking=RepositoryGitTracking.TRACKED,
        role=RepositoryMaterialRole.GENERATED,
    )
    result = assess(facts(entries=(ignored_source, tracked_generated)))
    assert result.observation is not None
    pairs = {
        (item.classification.tracking, item.classification.material_role)
        for item in result.observation.paths
    }
    assert (RepositoryGitTracking.IGNORED, RepositoryMaterialRole.SOURCE) in pairs
    assert (RepositoryGitTracking.TRACKED, RepositoryMaterialRole.GENERATED) in pairs


def test_sparse_excluded_cannot_be_reported_as_content_observed() -> None:
    sparse = entry("sparse.py", topology=RepositoryTopology.SPARSE_EXCLUDED)
    result = assess(facts(entries=(sparse,)))
    assert RepositoryObservationDiagnosticCode.SPARSE_EXCLUDED_OBSERVED in codes(result)


@pytest.mark.parametrize(
    "topology",
    [RepositoryTopology.SUBMODULE, RepositoryTopology.NESTED_REPOSITORY],
)
def test_repository_boundaries_are_not_traversed(topology: RepositoryTopology) -> None:
    boundary = entry("boundary", topology=topology, descendants_observed=True)
    result = assess(facts(entries=(boundary,)))
    assert RepositoryObservationDiagnosticCode.TOPOLOGY_IMPLICIT_TRAVERSAL in codes(result)


def test_fact_order_does_not_change_result_or_fingerprint() -> None:
    a = entry("a.py")
    b = entry("b.py", tracking=RepositoryGitTracking.UNTRACKED)
    first = assess(facts(entries=(a, b)))
    second = assess(
        facts(entries=(b, a), dimensions=tuple(reversed(complete_dimensions())))
    )
    assert canonical_bytes(first) == canonical_bytes(second)
    assert first.fingerprint == second.fingerprint


def test_occurrence_metadata_does_not_change_semantic_fingerprint() -> None:
    first = assess(facts(occurred_at=datetime(2026, 8, 3, tzinfo=UTC)))
    second = assess(facts(occurred_at=datetime(2026, 8, 3, tzinfo=UTC) + timedelta(hours=1)))
    assert first.occurred_at != second.occurred_at
    assert first.fingerprint == second.fingerprint


def test_diagnostics_are_closed_and_carry_no_paths_payloads_or_secrets() -> None:
    result = assess(
        facts(entries=(entry("private/credential.txt", status=RepositoryEntryStatus.MODIFIED),))
    )
    serialized = " ".join(
        f"{item.dimension.value}:{item.code.value}" for item in result.assessment.diagnostics
    )
    assert "private/credential.txt" not in serialized
    assert "credential" not in serialized
    assert all(isinstance(item.code, RepositoryObservationDiagnosticCode) for item in result.assessment.diagnostics)


def test_source_occurrence_requires_timezone_and_safe_bounded_identity() -> None:
    with pytest.raises(InvalidRepositoryObservationFacts):
        RepositoryObservationSource("observer", "v1", datetime(2026, 8, 3))
