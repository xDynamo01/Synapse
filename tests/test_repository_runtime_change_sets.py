from dataclasses import replace

from tests.test_repository_runtime_snapshots import (
    build,
    catalog,
    fingerprint_fact,
    identities,
    path_facts,
    profile,
)

from synapse.repository_runtime import (
    RepositoryChangeAxisState,
    RepositoryChangeDiagnosticCode,
    RepositoryChangeFact,
    RepositoryChangeSetPolicy,
    RepositoryChangeSetRequest,
    RepositoryChangeSetService,
    RepositoryChangeType,
    RepositoryFingerprint,
    RepositoryGitTracking,
    RepositoryMaterialRole,
    RepositoryObservationCompleteness,
    RepositoryPathClassification,
    RepositoryResourceKind,
    RepositorySensitivity,
    RepositoryTopology,
)


def snapshot(*paths: str):
    path_catalog = catalog(*(path_facts(value) for value in paths))
    facts = tuple(
        fingerprint_fact(
            entry,
            content=RepositoryFingerprint.from_content(f"content:{entry.path.value}"),
        )
        for entry in path_catalog.entries
    )
    result = build(path_catalog, facts)
    assert result.snapshot is not None
    return result.snapshot


def with_entries(base, entries):
    ordered = tuple(entries)
    return replace(
        base,
        entries=ordered,
        source_tree_fingerprint=RepositoryFingerprint.from_content(ordered),
        path_catalog_fingerprint=RepositoryFingerprint.from_content(
            (base.path_catalog_fingerprint, tuple(entry.path for entry in ordered))
        ),
    )


def request(base, target, *, base_order: int = 1, target_order: int = 2, occurrence=()):
    repository, checkout, worktree = identities()
    return RepositoryChangeSetRequest(
        repository,
        checkout,
        worktree,
        profile(),
        base.fingerprint,
        target.fingerprint,
        base_order,
        target_order,
        occurrence,
    )


def policy(**changes):
    return replace(
        RepositoryChangeSetPolicy("change-policy", "v1"),
        **changes,
    )


def compare(base, target, facts=(), *, selected_policy=None, supplied_request=None):
    return RepositoryChangeSetService().compare(
        supplied_request or request(base, target),
        selected_policy or policy(),
        base,
        target,
        facts,
    )


def codes(result):
    return {item.code for item in result.diagnostics}


def explicit_fact(change_type, before, after, *, evidence="observer:evidence:v1", occurrence=()):
    return RepositoryChangeFact(
        change_type,
        before.path if before else None,
        after.path if after else None,
        RepositoryFingerprint.from_content(before) if before else None,
        RepositoryFingerprint.from_content(after) if after else None,
        before.content_fingerprint if before else None,
        after.content_fingerprint if after else None,
        before.content_length if before else None,
        after.content_length if after else None,
        before.classification if before else None,
        after.classification if after else None,
        RepositoryObservationCompleteness.COMPLETE,
        evidence,
        occurrence,
    )


def test_added_and_deleted_are_facts_without_mutation_authority() -> None:
    base = snapshot("old.txt")
    target = snapshot("new.txt")
    result = compare(base, target)
    assert result.change_set is not None
    assert {entry.change_type for entry in result.change_set.entries} == {
        RepositoryChangeType.ADDED,
        RepositoryChangeType.DELETED,
    }
    assert not hasattr(result.change_set, "plan")
    assert not hasattr(result.change_set, "authorize")
    assert not hasattr(result.change_set.entries[0], "apply")
    assert not hasattr(result.change_set.entries[0], "delete")


def test_content_identity_alone_does_not_prove_rename_or_copy() -> None:
    base = snapshot("old.txt")
    target = snapshot("new.txt")
    target_entry = replace(
        target.entries[0],
        content_fingerprint=base.entries[0].content_fingerprint,
    )
    target = with_entries(target, (target_entry,))
    result = compare(base, target)
    assert result.change_set is not None
    assert {entry.change_type for entry in result.change_set.entries} == {
        RepositoryChangeType.ADDED,
        RepositoryChangeType.DELETED,
    }


def test_explicit_rename_evidence_produces_rename() -> None:
    base = snapshot("old.txt")
    target = snapshot("new.txt")
    target = with_entries(
        target,
        (replace(target.entries[0], content_fingerprint=base.entries[0].content_fingerprint),),
    )
    fact = explicit_fact(RepositoryChangeType.RENAMED, base.entries[0], target.entries[0])
    result = compare(base, target, (fact,))
    assert result.change_set is not None
    assert [entry.change_type for entry in result.change_set.entries] == [
        RepositoryChangeType.RENAMED
    ]
    assert result.change_set.entries[0].evidence_reference == "observer:evidence:v1"


def test_rename_without_evidence_fails_explicitly() -> None:
    base = snapshot("old.txt")
    target = snapshot("new.txt")
    fact = explicit_fact(
        RepositoryChangeType.RENAMED,
        base.entries[0],
        target.entries[0],
        evidence=None,
    )
    result = compare(base, target, (fact,))
    assert RepositoryChangeDiagnosticCode.RENAME_EVIDENCE_REQUIRED in codes(result)


def test_explicit_copy_requires_valid_source_and_evidence() -> None:
    base = snapshot("source.txt")
    target = snapshot("source.txt", "copy.txt")
    source = base.entries[0]
    copied = next(entry for entry in target.entries if entry.path.value == "copy.txt")
    copied = replace(copied, content_fingerprint=source.content_fingerprint)
    target = with_entries(
        target,
        tuple(copied if entry.path.value == "copy.txt" else entry for entry in target.entries),
    )
    fact = explicit_fact(RepositoryChangeType.COPIED, source, copied)
    result = compare(base, target, (fact,))
    assert result.change_set is not None
    assert [entry.change_type for entry in result.change_set.entries] == [
        RepositoryChangeType.COPIED
    ]


def test_content_metadata_type_and_classification_axes_remain_independent() -> None:
    base = snapshot("file.txt")
    before = base.entries[0]

    content_target = with_entries(
        base,
        (replace(before, content_fingerprint=RepositoryFingerprint.from_content("changed")),),
    )
    content_result = compare(base, content_target)
    assert content_result.change_set is not None
    content_entry = content_result.change_set.entries[0]
    assert content_entry.change_type is RepositoryChangeType.MODIFIED
    assert content_entry.axes.content is RepositoryChangeAxisState.CHANGED
    assert content_entry.axes.material_role is RepositoryChangeAxisState.UNCHANGED

    metadata_target = with_entries(
        base,
        (replace(before, metadata_fingerprint=RepositoryFingerprint.from_content("metadata")),),
    )
    metadata_result = compare(base, metadata_target)
    assert metadata_result.change_set is not None
    assert metadata_result.change_set.entries[0].change_type is RepositoryChangeType.METADATA_CHANGED

    type_target = with_entries(
        base,
        (
                replace(
                    before,
                    resource_kind=RepositoryResourceKind.DIRECTORY,
                    content_length=None,
                ),
        ),
    )
    type_result = compare(base, type_target)
    assert type_result.change_set is not None
    assert type_result.change_set.entries[0].change_type is RepositoryChangeType.TYPE_CHANGED

    changed_classification = replace(
        before.classification,
        material_role=RepositoryMaterialRole.GENERATED,
    )
    classification_target = with_entries(
        base,
        (replace(before, classification=changed_classification),),
    )
    classification_result = compare(base, classification_target)
    assert classification_result.change_set is not None
    classification_entry = classification_result.change_set.entries[0]
    assert classification_entry.change_type is RepositoryChangeType.CLASSIFICATION_CHANGED
    assert classification_entry.axes.content is RepositoryChangeAxisState.UNCHANGED
    assert classification_entry.axes.material_role is RepositoryChangeAxisState.CHANGED


def test_incompatible_identity_and_platform_fail_closed() -> None:
    base = snapshot("file.txt")
    target = snapshot("file.txt", "new.txt")
    other_repository = identities()[0].from_stable_key("other")
    incompatible = replace(target, repository_id=other_repository)
    result = compare(
        base,
        incompatible,
        supplied_request=replace(request(base, incompatible), repository_id=other_repository),
    )
    assert result.change_set is None
    assert RepositoryChangeDiagnosticCode.REPOSITORY_MISMATCH in codes(result)


def test_identical_or_inverted_snapshots_fail_closed() -> None:
    base = snapshot("file.txt")
    identical = compare(base, base)
    assert identical.change_set is None
    assert RepositoryChangeDiagnosticCode.IDENTICAL_SNAPSHOTS in codes(identical)

    target = snapshot("file.txt", "new.txt")
    inverted = compare(
        base,
        target,
        supplied_request=request(base, target, base_order=2, target_order=1),
    )
    assert inverted.change_set is None
    assert RepositoryChangeDiagnosticCode.SNAPSHOT_ORDER_INVALID in codes(inverted)


def test_incomplete_snapshot_never_produces_complete_change_set() -> None:
    base = replace(snapshot("file.txt"), completeness=RepositoryObservationCompleteness.PARTIAL)
    target = snapshot("file.txt", "new.txt")
    result = compare(base, target)
    assert result.change_set is not None
    assert result.change_set.completeness is RepositoryObservationCompleteness.PARTIAL
    assert RepositoryChangeDiagnosticCode.SNAPSHOT_INCOMPLETE in codes(result)


def test_duplicate_path_is_diagnostic() -> None:
    base = snapshot("file.txt")
    duplicate = with_entries(base, (base.entries[0], base.entries[0]))
    target = snapshot("file.txt", "new.txt")
    result = compare(duplicate, target)
    assert codes(result) >= {
        RepositoryChangeDiagnosticCode.PATH_DUPLICATE,
        RepositoryChangeDiagnosticCode.PATH_COLLISION,
    }


def test_repository_boundary_is_not_traversed() -> None:
    base = snapshot("vendor")
    boundary_classification = replace(
        base.entries[0].classification,
        topology=RepositoryTopology.SUBMODULE,
    )
    base = with_entries(base, (replace(base.entries[0], classification=boundary_classification),))
    target = snapshot("vendor", "vendor/internal.txt")
    result = compare(base, target)
    assert RepositoryChangeDiagnosticCode.REPOSITORY_BOUNDARY_TRAVERSAL in codes(result)


def test_sensitivity_is_not_reduced_silently() -> None:
    base = snapshot("secret.txt")
    secret = RepositoryPathClassification(
        RepositoryGitTracking.TRACKED,
        RepositoryMaterialRole.SOURCE,
        RepositorySensitivity.SECRET_RISK,
        RepositoryTopology.REGULAR,
    )
    normal = replace(secret, sensitivity=RepositorySensitivity.NORMAL)
    base = with_entries(base, (replace(base.entries[0], classification=secret),))
    target = with_entries(base, (replace(base.entries[0], classification=normal),))
    result = compare(base, target)
    assert RepositoryChangeDiagnosticCode.SENSITIVITY_REDUCTION in codes(result)
    assert result.change_set is not None
    assert result.change_set.completeness is RepositoryObservationCompleteness.PARTIAL


def test_fact_order_and_occurrence_metadata_do_not_change_identity() -> None:
    base = snapshot("old-a.txt", "old-b.txt")
    target = snapshot("new-a.txt", "new-b.txt")
    facts = tuple(
        explicit_fact(
            RepositoryChangeType.RENAMED,
            before,
            after,
            occurrence=(("sample", str(index)),),
        )
        for index, (before, after) in enumerate(zip(base.entries, target.entries, strict=True))
    )
    first = compare(
        base,
        target,
        facts,
        supplied_request=request(base, target, occurrence=(("run", "one"),)),
    )
    changed_occurrence = tuple(
        replace(fact, occurrence_metadata=(("sample", "changed"),)) for fact in facts
    )
    second = compare(
        base,
        target,
        tuple(reversed(changed_occurrence)),
        supplied_request=request(base, target, occurrence=(("run", "two"),)),
    )
    assert first.change_set == second.change_set
    assert first.fingerprint == second.fingerprint


def test_semantic_entry_change_changes_change_set_fingerprint() -> None:
    base = snapshot("file.txt")
    before = base.entries[0]
    first_target = with_entries(
        base,
        (replace(before, content_fingerprint=RepositoryFingerprint.from_content("one")),),
    )
    second_target = with_entries(
        base,
        (replace(before, content_fingerprint=RepositoryFingerprint.from_content("two")),),
    )
    first = compare(base, first_target)
    second = compare(base, second_target)
    assert first.change_set is not None and second.change_set is not None
    assert first.change_set.fingerprint != second.change_set.fingerprint


def test_conflict_fact_is_closed_and_contains_no_payload() -> None:
    base = snapshot("file.txt")
    target = with_entries(
        base,
        (
            replace(
                base.entries[0],
                content_fingerprint=RepositoryFingerprint.from_content("conflict"),
            ),
        ),
    )
    fact = explicit_fact(
        RepositoryChangeType.CONFLICT,
        base.entries[0],
        target.entries[0],
        evidence=None,
    )
    result = compare(base, target, (fact,))
    assert result.change_set is not None
    entry = result.change_set.entries[0]
    assert entry.change_type is RepositoryChangeType.CONFLICT
    assert entry.axes.content is RepositoryChangeAxisState.CONFLICT
    assert not hasattr(entry, "payload")
    assert not hasattr(entry, "patch")


def test_diagnostics_do_not_expose_paths_content_or_secrets() -> None:
    base = snapshot("safe/relative.txt")
    target = snapshot("other.txt")
    fact = explicit_fact(
        RepositoryChangeType.RENAMED,
        base.entries[0],
        target.entries[0],
        evidence=None,
    )
    result = compare(base, target, (fact,))
    diagnostic = result.diagnostics[0]
    assert not hasattr(diagnostic, "path")
    assert not hasattr(diagnostic, "content")
    assert not hasattr(diagnostic, "secret")
