from dataclasses import replace
from datetime import UTC, datetime

from synapse.repository_runtime import (
    RepositoryCaseSensitivity,
    RepositoryCheckout,
    RepositoryCheckoutIdentity,
    RepositoryContentKind,
    RepositoryDimensionCompleteness,
    RepositoryFingerprint,
    RepositoryGitTracking,
    RepositoryHeadKind,
    RepositoryHeadState,
    RepositoryIdentity,
    RepositoryIndexPresence,
    RepositoryIndexState,
    RepositoryObservationCompleteness,
    RepositoryObservationDimension,
    RepositoryObservationFacts,
    RepositoryObservationRequest,
    RepositoryObservationService,
    RepositoryObservationSource,
    RepositoryPath,
    RepositoryPathClassificationPolicy,
    RepositoryPathClassificationService,
    RepositoryPathDiagnostic,
    RepositoryPathDiagnosticCode,
    RepositoryPathFacts,
    RepositoryPathFingerprintFact,
    RepositoryPlatformKind,
    RepositoryPlatformProfile,
    RepositoryPresence,
    RepositoryResourceKind,
    RepositorySizeClass,
    RepositorySnapshotDiagnosticCode,
    RepositorySnapshotDimension,
    RepositorySnapshotDimensionState,
    RepositorySnapshotPolicy,
    RepositorySnapshotRequest,
    RepositorySnapshotService,
    RepositorySparseCheckoutState,
    RepositoryTopology,
    RepositoryUnicodeNormalization,
    RepositoryWorkspaceState,
    RepositoryWorkspaceStatus,
    RepositoryWorktree,
    RepositoryWorktreeIdentity,
)


def identities():
    repository = RepositoryIdentity.from_stable_key("repository-1")
    checkout = RepositoryCheckoutIdentity.derive(repository, "checkout-1")
    worktree = RepositoryWorktreeIdentity.derive(checkout, "worktree-1")
    return repository, checkout, worktree


def profile():
    return RepositoryPlatformProfile(
        RepositoryPlatformKind.POSIX,
        RepositoryCaseSensitivity.SENSITIVE,
        RepositoryUnicodeNormalization.PRESERVE,
    )


def observation_result(
    *,
    head: RepositoryHeadState | None = None,
    index: RepositoryIndexState | None = None,
    workspace: RepositoryWorkspaceStatus = RepositoryWorkspaceStatus.CLEAN,
):
    repository, checkout, worktree = identities()
    platform = profile()
    request = RepositoryObservationRequest(repository, checkout, worktree, platform)
    dimensions = tuple(
        RepositoryDimensionCompleteness(
            dimension, RepositoryObservationCompleteness.COMPLETE
        )
        for dimension in RepositoryObservationDimension
    )
    facts = RepositoryObservationFacts(
        RepositoryObservationSource("snapshot-observer", "v1", datetime(2026, 8, 3, tzinfo=UTC)),
        RepositoryPresence.PRESENT,
        repository,
        RepositoryCheckout(checkout, repository),
        RepositoryWorktree(worktree, checkout, repository),
        platform,
        head or RepositoryHeadState(RepositoryHeadKind.NAMED_BRANCH, "main", "abcd1234"),
        (head.branch_name if head is not None else "main"),
        (head.commit_id if head is not None else "abcd1234"),
        index or RepositoryIndexState(RepositoryIndexPresence.PRESENT),
        workspace,
        (),
        (),
        dimensions,
    )
    return RepositoryObservationService().assess(request, facts)


def path_facts(
    value: str,
    *,
    resource: RepositoryResourceKind = RepositoryResourceKind.FILE,
    topology: RepositoryTopology = RepositoryTopology.REGULAR,
):
    _, checkout, worktree = identities()
    return RepositoryPathFacts(
        RepositoryPath(value, profile(), checkout, worktree),
        RepositoryGitTracking.TRACKED,
        topology,
        resource,
        False if resource is RepositoryResourceKind.FILE else None,
        RepositoryContentKind.TEXT
        if resource is RepositoryResourceKind.FILE
        else RepositoryContentKind.UNKNOWN,
        RepositorySizeClass.SMALL
        if resource is RepositoryResourceKind.FILE
        else RepositorySizeClass.UNKNOWN,
        topology is not RepositoryTopology.SPARSE_EXCLUDED,
        False,
        RepositoryObservationCompleteness.COMPLETE,
    )


def catalog(*paths: RepositoryPathFacts, observation=None):
    repository, checkout, worktree = identities()
    observation = observation or observation_result()
    return RepositoryPathClassificationService().classify(
        repository_id=repository,
        checkout_id=checkout,
        worktree_id=worktree,
        observation_fingerprint=observation.fingerprint,
        platform_profile=profile(),
        policy=RepositoryPathClassificationPolicy("path-policy", "v1"),
        facts=paths,
    ).catalog


def snapshot_policy(*required: RepositorySnapshotDimension):
    return RepositorySnapshotPolicy(
        "snapshot-policy",
        "v1",
        required or tuple(RepositorySnapshotDimension),
    )


def fingerprint_fact(
    entry,
    *,
    content: RepositoryFingerprint | None = None,
    metadata: RepositoryFingerprint | None = None,
    algorithm: str = "sha256",
    version: str = "v1",
    completeness: RepositoryObservationCompleteness = RepositoryObservationCompleteness.COMPLETE,
    occurrence: tuple[tuple[str, str], ...] = (),
):
    return RepositoryPathFingerprintFact(
        RepositoryFingerprint.from_content(entry.path),
        content,
        metadata,
        128 if content is not None else None,
        algorithm,
        version,
        completeness,
        occurrence,
    )


def request(observation, paths, *, sparse=RepositorySparseCheckoutState.DISABLED, occurrence=()):
    assert observation.observation is not None
    observed = observation.observation
    completeness = tuple(
        RepositorySnapshotDimensionState(
            dimension,
            RepositoryObservationCompleteness.COMPLETE,
        )
        for dimension in RepositorySnapshotDimension
    )
    return RepositorySnapshotRequest(
        observed.repository_id,
        observed.checkout_id,
        observed.worktree_id,
        profile(),
        observation.fingerprint,
        paths.fingerprint,
        observed.head,
        observed.head.commit_id,
        observed.head.branch_name,
        observed.index,
        observed.workspace,
        sparse,
        completeness,
        occurrence,
    )


def build(paths, facts, *, supplied_observation=None, supplied_request=None, policy=None):
    observation = supplied_observation or observation_result()
    snapshot_request = supplied_request or request(observation, paths)
    return RepositorySnapshotService().build(
        snapshot_request,
        policy or snapshot_policy(),
        observation,
        paths,
        facts,
    )


def codes(result):
    return {item.code for item in result.diagnostics}


def test_complete_snapshot_binds_all_authoritative_facts_and_fingerprints() -> None:
    paths = catalog(path_facts("src/main.py"))
    fact = fingerprint_fact(paths.entries[0], content=RepositoryFingerprint.from_content("bytes"))
    result = build(paths, (fact,))
    assert result.snapshot is not None
    snapshot = result.snapshot
    assert snapshot.completeness is RepositoryObservationCompleteness.COMPLETE
    assert snapshot.observation_fingerprint == observation_result().fingerprint
    assert snapshot.path_catalog_fingerprint == paths.fingerprint
    assert len(
        {
            snapshot.repository_metadata_fingerprint,
            snapshot.head_fingerprint,
            snapshot.index_fingerprint,
            snapshot.source_tree_fingerprint,
            snapshot.workspace_fingerprint,
            snapshot.path_catalog_fingerprint,
            snapshot.fingerprint,
        }
    ) == 7


def test_snapshot_has_no_restore_or_mutation_authority() -> None:
    paths = catalog()
    result = build(paths, ())
    assert result.snapshot is not None
    assert not hasattr(result.snapshot, "restore")
    assert not hasattr(result.snapshot, "rollback")
    assert not hasattr(result.snapshot, "apply")
    assert not hasattr(result, "authorize")


def test_observation_and_catalog_fingerprints_must_correspond_exactly() -> None:
    paths = catalog()
    bad_request = replace(
        request(observation_result(), paths),
        observation_fingerprint=RepositoryFingerprint.from_content("other"),
    )
    result = build(paths, (), supplied_request=bad_request)
    assert result.snapshot is None
    assert RepositorySnapshotDiagnosticCode.OBSERVATION_FINGERPRINT_MISMATCH in codes(result)


def test_repository_checkout_and_worktree_mismatch_fail_closed() -> None:
    paths = catalog()
    base = request(observation_result(), paths)
    other_repository = RepositoryIdentity.from_stable_key("other")
    other_checkout = RepositoryCheckoutIdentity.derive(other_repository, "other")
    other_worktree = RepositoryWorktreeIdentity.derive(other_checkout, "other")
    for changed, expected in (
        (replace(base, repository_id=other_repository), RepositorySnapshotDiagnosticCode.REPOSITORY_IDENTITY_MISMATCH),
        (replace(base, checkout_id=other_checkout), RepositorySnapshotDiagnosticCode.CHECKOUT_IDENTITY_MISMATCH),
        (replace(base, worktree_id=other_worktree), RepositorySnapshotDiagnosticCode.WORKTREE_IDENTITY_MISMATCH),
    ):
        result = build(paths, (), supplied_request=changed)
        assert result.snapshot is None
        assert expected in codes(result)


def test_required_file_without_content_fingerprint_is_partial() -> None:
    paths = catalog(path_facts("large.bin"))
    result = build(paths, (fingerprint_fact(paths.entries[0]),))
    assert result.snapshot is not None
    assert result.snapshot.completeness is RepositoryObservationCompleteness.PARTIAL
    assert RepositorySnapshotDiagnosticCode.CONTENT_FINGERPRINT_REQUIRED in codes(result)


def test_sparse_directory_link_and_repository_boundaries_do_not_require_content() -> None:
    supplied = (
        path_facts("excluded", topology=RepositoryTopology.SPARSE_EXCLUDED),
        path_facts("directory", resource=RepositoryResourceKind.DIRECTORY),
        path_facts("link", resource=RepositoryResourceKind.LINK),
        path_facts("submodule", topology=RepositoryTopology.SUBMODULE),
        path_facts("nested", topology=RepositoryTopology.NESTED_REPOSITORY),
    )
    paths = catalog(*supplied)
    facts = tuple(fingerprint_fact(entry) for entry in paths.entries)
    result = build(
        paths,
        facts,
        supplied_request=request(
            observation_result(), paths, sparse=RepositorySparseCheckoutState.ENABLED
        ),
    )
    assert result.snapshot is not None
    assert RepositorySnapshotDiagnosticCode.CONTENT_FINGERPRINT_REQUIRED not in codes(result)
    assert all(entry.content_fingerprint is None for entry in result.snapshot.entries)


def test_unknown_algorithm_is_explicit_and_partial() -> None:
    paths = catalog(path_facts("src/main.py"))
    fact = fingerprint_fact(
        paths.entries[0],
        content=RepositoryFingerprint.from_content("bytes"),
        algorithm="future-hash",
    )
    result = build(paths, (fact,))
    assert RepositorySnapshotDiagnosticCode.FINGERPRINT_ALGORITHM_UNSUPPORTED in codes(result)
    assert result.snapshot is not None
    assert result.snapshot.completeness is RepositoryObservationCompleteness.PARTIAL


def test_duplicate_divergent_content_fingerprint_fails_explicitly() -> None:
    paths = catalog(path_facts("src/main.py"))
    first = fingerprint_fact(paths.entries[0], content=RepositoryFingerprint.from_content("one"))
    second = replace(first, content_fingerprint=RepositoryFingerprint.from_content("two"))
    result = build(paths, (first, second))
    assert codes(result) >= {
        RepositorySnapshotDiagnosticCode.PATH_FACT_DUPLICATE,
        RepositorySnapshotDiagnosticCode.CONTENT_FINGERPRINT_CONFLICT,
    }
    assert result.snapshot is not None
    assert result.snapshot.completeness is RepositoryObservationCompleteness.PARTIAL


def test_missing_and_outside_catalog_path_facts_are_diagnostic() -> None:
    paths = catalog(path_facts("src/main.py"))
    outside = RepositoryPathFingerprintFact(
        RepositoryFingerprint.from_content("outside-path"),
        None,
        None,
        None,
        "sha256",
        "v1",
        RepositoryObservationCompleteness.COMPLETE,
    )
    result = build(paths, (outside,))
    assert codes(result) >= {
        RepositorySnapshotDiagnosticCode.PATH_FACT_MISSING,
        RepositorySnapshotDiagnosticCode.PATH_FACT_OUTSIDE_CATALOG,
    }


def test_catalog_collision_remains_visible_to_snapshot() -> None:
    _, checkout, worktree = identities()
    insensitive = RepositoryPlatformProfile(
        RepositoryPlatformKind.WINDOWS,
        RepositoryCaseSensitivity.INSENSITIVE,
        RepositoryUnicodeNormalization.NFC,
    )
    original = RepositoryPath("Docs/Readme.md", insensitive, checkout, worktree)
    collision = RepositoryPath("docs/readme.md", insensitive, checkout, worktree)
    base = catalog()
    path_fingerprint = RepositoryFingerprint.from_content(original)
    collision_diagnostic = RepositoryPathDiagnostic(
        path_fingerprint, RepositoryPathDiagnosticCode.PATH_COLLISION
    )
    collided = replace(
        base,
        platform_profile=insensitive,
        completeness=RepositoryObservationCompleteness.PARTIAL,
        diagnostics=(collision_diagnostic,),
    )
    snapshot_request = replace(
        request(observation_result(), collided),
        platform_profile=insensitive,
        path_catalog_fingerprint=collided.fingerprint,
    )
    assert original == collision
    result = build(collided, (), supplied_request=snapshot_request)
    assert RepositorySnapshotDiagnosticCode.PATH_COLLISION in codes(result)


def test_head_index_workspace_and_sparse_contradictions_fail_closed() -> None:
    paths = catalog(path_facts("excluded", topology=RepositoryTopology.SPARSE_EXCLUDED))
    base = request(observation_result(), paths)
    changed = replace(
        base,
        object_reference="ffff",
        index=RepositoryIndexState(RepositoryIndexPresence.ABSENT),
        workspace=RepositoryWorkspaceState(
            RepositoryWorkspaceStatus.DIRTY, RepositoryObservationCompleteness.COMPLETE
        ),
    )
    result = build(paths, (), supplied_request=changed)
    assert result.snapshot is None
    assert codes(result) >= {
        RepositorySnapshotDiagnosticCode.OBJECT_REFERENCE_MISMATCH,
        RepositorySnapshotDiagnosticCode.INDEX_STATE_MISMATCH,
        RepositorySnapshotDiagnosticCode.WORKSPACE_STATE_MISMATCH,
        RepositorySnapshotDiagnosticCode.SPARSE_STATE_CONTRADICTION,
    }


def test_entry_order_does_not_change_source_tree_or_snapshot_fingerprint() -> None:
    paths = catalog(path_facts("z.txt"), path_facts("a.txt"))
    first = fingerprint_fact(paths.entries[0], content=RepositoryFingerprint.from_content("a"))
    second = fingerprint_fact(paths.entries[1], content=RepositoryFingerprint.from_content("z"))
    forward = build(paths, (first, second))
    reverse = build(paths, (second, first))
    assert forward == reverse
    assert forward.fingerprint == reverse.fingerprint
    assert forward.snapshot is not None and reverse.snapshot is not None
    assert forward.snapshot.source_tree_fingerprint == reverse.snapshot.source_tree_fingerprint


def test_occurrence_metadata_does_not_change_semantic_identity() -> None:
    paths = catalog(path_facts("src/main.py"))
    base_fact = fingerprint_fact(
        paths.entries[0], content=RepositoryFingerprint.from_content("bytes")
    )
    first = build(
        paths,
        (replace(base_fact, occurrence_metadata=(("sample", "one"),)),),
        supplied_request=request(observation_result(), paths, occurrence=(("run", "one"),)),
    )
    second = build(
        paths,
        (replace(base_fact, occurrence_metadata=(("sample", "two"),)),),
        supplied_request=request(observation_result(), paths, occurrence=(("run", "two"),)),
    )
    assert first.snapshot == second.snapshot
    assert first.snapshot is not None and second.snapshot is not None
    assert first.snapshot.fingerprint == second.snapshot.fingerprint


def test_semantic_changes_update_their_fingerprint_layer() -> None:
    paths = catalog(path_facts("src/main.py"))
    fact = fingerprint_fact(paths.entries[0], content=RepositoryFingerprint.from_content("one"))
    original = build(paths, (fact,))
    changed_fact = replace(fact, content_fingerprint=RepositoryFingerprint.from_content("two"))
    changed = build(paths, (changed_fact,))
    assert original.snapshot is not None and changed.snapshot is not None
    assert original.snapshot.source_tree_fingerprint != changed.snapshot.source_tree_fingerprint
    assert original.snapshot.fingerprint != changed.snapshot.fingerprint


def test_head_index_workspace_and_catalog_changes_update_independent_layers() -> None:
    path_state = path_facts("src/main.py")
    base_observation = observation_result()
    base_catalog = catalog(path_state, observation=base_observation)
    base_fact = fingerprint_fact(
        base_catalog.entries[0], content=RepositoryFingerprint.from_content("bytes")
    )
    base = build(
        base_catalog,
        (base_fact,),
        supplied_observation=base_observation,
        supplied_request=request(base_observation, base_catalog),
    )
    assert base.snapshot is not None

    detached_observation = observation_result(
        head=RepositoryHeadState(RepositoryHeadKind.DETACHED, None, "abcd1234")
    )
    detached_catalog = catalog(path_state, observation=detached_observation)
    detached = build(
        detached_catalog,
        (base_fact,),
        supplied_observation=detached_observation,
        supplied_request=request(detached_observation, detached_catalog),
    )
    assert detached.snapshot is not None
    assert base.snapshot.head_fingerprint != detached.snapshot.head_fingerprint

    absent_index_observation = observation_result(
        index=RepositoryIndexState(RepositoryIndexPresence.ABSENT)
    )
    absent_index_catalog = catalog(path_state, observation=absent_index_observation)
    absent_index = build(
        absent_index_catalog,
        (base_fact,),
        supplied_observation=absent_index_observation,
        supplied_request=request(absent_index_observation, absent_index_catalog),
    )
    assert absent_index.snapshot is not None
    assert base.snapshot.index_fingerprint != absent_index.snapshot.index_fingerprint

    dirty_observation = observation_result(workspace=RepositoryWorkspaceStatus.DIRTY)
    dirty_catalog = catalog(path_state, observation=dirty_observation)
    dirty = build(
        dirty_catalog,
        (base_fact,),
        supplied_observation=dirty_observation,
        supplied_request=request(dirty_observation, dirty_catalog),
    )
    assert dirty.snapshot is not None
    assert base.snapshot.workspace_fingerprint != dirty.snapshot.workspace_fingerprint

    expanded_catalog = catalog(path_state, path_facts("src/other.py"), observation=base_observation)
    expanded_facts = tuple(
        fingerprint_fact(entry, content=RepositoryFingerprint.from_content(entry.path.value))
        for entry in expanded_catalog.entries
    )
    expanded = build(
        expanded_catalog,
        expanded_facts,
        supplied_observation=base_observation,
        supplied_request=request(base_observation, expanded_catalog),
    )
    assert expanded.snapshot is not None
    assert base.snapshot.path_catalog_fingerprint != expanded.snapshot.path_catalog_fingerprint
    assert base.snapshot.fingerprint != expanded.snapshot.fingerprint


def test_diagnostics_do_not_expose_paths_content_or_secrets() -> None:
    paths = catalog(path_facts("safe/relative.txt"))
    result = build(paths, ())
    diagnostic = result.diagnostics[0]
    assert not hasattr(diagnostic, "path")
    assert not hasattr(diagnostic, "content")
    assert not hasattr(diagnostic, "secret")
