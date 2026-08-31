from dataclasses import replace

import pytest

from synapse.repository_runtime import (
    RepositoryCaseSensitivity,
    RepositoryCheckoutIdentity,
    RepositoryContentKind,
    RepositoryFingerprint,
    RepositoryGitTracking,
    RepositoryIdentity,
    RepositoryLinkPolicy,
    RepositoryMaterialRole,
    RepositoryMaterialRule,
    RepositoryObservationCompleteness,
    RepositoryPath,
    RepositoryPathClassificationPolicy,
    RepositoryPathClassificationService,
    RepositoryPathDiagnosticCode,
    RepositoryPathFacts,
    RepositoryPlatformKind,
    RepositoryPlatformProfile,
    RepositoryResourceKind,
    RepositorySensitivity,
    RepositorySensitivityRule,
    RepositorySizeClass,
    RepositoryTopology,
    RepositoryUnicodeNormalization,
    RepositoryWorktreeIdentity,
    canonical_bytes,
)


def identities() -> tuple[
    RepositoryIdentity, RepositoryCheckoutIdentity, RepositoryWorktreeIdentity
]:
    repository = RepositoryIdentity.from_stable_key("repository-1")
    checkout = RepositoryCheckoutIdentity.derive(repository, "checkout-1")
    return repository, checkout, RepositoryWorktreeIdentity.derive(checkout, "worktree-1")


def profile(
    *,
    case: RepositoryCaseSensitivity = RepositoryCaseSensitivity.SENSITIVE,
    unicode: RepositoryUnicodeNormalization = RepositoryUnicodeNormalization.PRESERVE,
) -> RepositoryPlatformProfile:
    return RepositoryPlatformProfile(RepositoryPlatformKind.POSIX, case, unicode)


def policy(*, links: RepositoryLinkPolicy | None = RepositoryLinkPolicy.PRESERVE):
    return RepositoryPathClassificationPolicy(
        "classification-policy",
        "v1",
        (
            RepositoryMaterialRule("role.source.v1", RepositoryMaterialRole.SOURCE),
            RepositoryMaterialRule("role.generated.v1", RepositoryMaterialRole.GENERATED),
            RepositoryMaterialRule("role.artifact.v1", RepositoryMaterialRole.ARTIFACT),
        ),
        (
            RepositorySensitivityRule("sensitivity.normal.v1", RepositorySensitivity.NORMAL),
            RepositorySensitivityRule(
                "sensitivity.secret.v1", RepositorySensitivity.SECRET_RISK
            ),
        ),
        links,
    )


def path(value: str, platform: RepositoryPlatformProfile | None = None) -> RepositoryPath:
    _, checkout, worktree = identities()
    return RepositoryPath(value, platform or profile(), checkout, worktree)


def facts(
    value: str = "src/main.py",
    *,
    platform: RepositoryPlatformProfile | None = None,
    tracking: RepositoryGitTracking = RepositoryGitTracking.TRACKED,
    topology: RepositoryTopology = RepositoryTopology.REGULAR,
    resource: RepositoryResourceKind = RepositoryResourceKind.FILE,
    content_observed: bool = True,
    descendants_observed: bool = False,
    completeness: RepositoryObservationCompleteness = RepositoryObservationCompleteness.COMPLETE,
    material_rules: tuple[str, ...] = (),
    generated_rule: str | None = None,
    sensitivity_rule: str | None = None,
    occurrence: tuple[tuple[str, str], ...] = (),
) -> RepositoryPathFacts:
    return RepositoryPathFacts(
        path(value, platform),
        tracking,
        topology,
        resource,
        False if resource is RepositoryResourceKind.FILE else None,
        RepositoryContentKind.TEXT if resource is RepositoryResourceKind.FILE else RepositoryContentKind.UNKNOWN,
        RepositorySizeClass.SMALL if resource is RepositoryResourceKind.FILE else RepositorySizeClass.UNKNOWN,
        content_observed,
        descendants_observed,
        completeness,
        material_rules,
        generated_rule,
        sensitivity_rule,
        "owner.scope.v1",
        occurrence,
    )


def classify(
    supplied: tuple[RepositoryPathFacts, ...],
    *,
    platform: RepositoryPlatformProfile | None = None,
    selected_policy: RepositoryPathClassificationPolicy | None = None,
):
    repository, checkout, worktree = identities()
    return RepositoryPathClassificationService().classify(
        repository_id=repository,
        checkout_id=checkout,
        worktree_id=worktree,
        observation_fingerprint=RepositoryFingerprint.from_content("observation-1"),
        platform_profile=platform or profile(),
        policy=selected_policy or policy(),
        facts=supplied,
    )


def codes(result) -> set[RepositoryPathDiagnosticCode]:
    return {item.code for item in result.diagnostics}


def test_explicit_rules_classify_independent_axes() -> None:
    result = classify(
        (
            facts(
                tracking=RepositoryGitTracking.IGNORED,
                material_rules=("role.source.v1",),
                sensitivity_rule="sensitivity.secret.v1",
            ),
        )
    )
    classification = result.catalog.entries[0].classification
    assert classification.tracking is RepositoryGitTracking.IGNORED
    assert classification.material_role is RepositoryMaterialRole.SOURCE
    assert classification.sensitivity is RepositorySensitivity.SECRET_RISK
    assert classification.topology is RepositoryTopology.REGULAR


@pytest.mark.parametrize(
    "tracking",
    [
        RepositoryGitTracking.TRACKED,
        RepositoryGitTracking.UNTRACKED,
        RepositoryGitTracking.IGNORED,
    ],
)
def test_tracking_does_not_infer_material_role(tracking: RepositoryGitTracking) -> None:
    entry = classify((facts(tracking=tracking),)).catalog.entries[0]
    assert entry.classification.material_role is RepositoryMaterialRole.UNKNOWN


def test_name_and_extension_do_not_infer_sensitivity() -> None:
    entry = classify((facts("secrets/private-key.pem"),)).catalog.entries[0]
    assert entry.classification.sensitivity is RepositorySensitivity.UNKNOWN


def test_source_and_generated_rules_fail_closed() -> None:
    result = classify(
        (
            facts(
                material_rules=("role.source.v1",),
                generated_rule="role.generated.v1",
            ),
        )
    )
    assert RepositoryPathDiagnosticCode.MATERIAL_ROLE_CONFLICT in codes(result)
    assert result.catalog.entries[0].classification.material_role is RepositoryMaterialRole.UNKNOWN
    assert result.catalog.completeness is RepositoryObservationCompleteness.PARTIAL


def test_sparse_excluded_rejects_observed_content() -> None:
    result = classify((facts(topology=RepositoryTopology.SPARSE_EXCLUDED),))
    assert RepositoryPathDiagnosticCode.SPARSE_EXCLUDED_CONTENT in codes(result)


@pytest.mark.parametrize(
    "topology",
    [RepositoryTopology.SUBMODULE, RepositoryTopology.NESTED_REPOSITORY],
)
def test_repository_boundaries_reject_descendant_traversal(
    topology: RepositoryTopology,
) -> None:
    result = classify((facts(topology=topology, descendants_observed=True),))
    assert RepositoryPathDiagnosticCode.TOPOLOGY_CONTENT_TRAVERSAL in codes(result)
    assert result.catalog.entries[0].classification.topology is topology


def test_link_requires_explicit_policy() -> None:
    result = classify(
        (facts(resource=RepositoryResourceKind.LINK, content_observed=False),),
        selected_policy=policy(links=None),
    )
    assert RepositoryPathDiagnosticCode.LINK_POLICY_REQUIRED in codes(result)


def test_unknown_rules_fail_closed_without_exposing_reference() -> None:
    result = classify(
        (
            facts(
                generated_rule="unknown.material.rule",
                sensitivity_rule="unknown.sensitivity.rule",
            ),
        )
    )
    assert codes(result) >= {
        RepositoryPathDiagnosticCode.UNKNOWN_MATERIAL_RULE,
        RepositoryPathDiagnosticCode.UNKNOWN_SENSITIVITY_RULE,
    }
    assert all(not hasattr(item, "message") for item in result.diagnostics)


def test_incomplete_facts_never_produce_complete_entry() -> None:
    result = classify(
        (facts(completeness=RepositoryObservationCompleteness.PARTIAL),)
    )
    assert RepositoryPathDiagnosticCode.FACTS_INCOMPLETE in codes(result)
    assert result.catalog.entries[0].completeness is RepositoryObservationCompleteness.PARTIAL


def test_divergent_tracking_for_same_path_fails_closed() -> None:
    result = classify(
        (
            facts(tracking=RepositoryGitTracking.TRACKED),
            facts(tracking=RepositoryGitTracking.UNTRACKED),
        )
    )
    assert codes(result) >= {
        RepositoryPathDiagnosticCode.PATH_COLLISION,
        RepositoryPathDiagnosticCode.TRACKING_CONFLICT,
    }
    assert result.catalog.entries[0].classification.tracking is RepositoryGitTracking.UNKNOWN


def test_case_and_unicode_collisions_follow_platform_profile() -> None:
    insensitive = profile(
        case=RepositoryCaseSensitivity.INSENSITIVE,
        unicode=RepositoryUnicodeNormalization.NFC,
    )
    collided = classify(
        (
            facts("Docs/Café.txt", platform=insensitive),
            facts("docs/Café.txt", platform=insensitive),
        ),
        platform=insensitive,
    )
    assert RepositoryPathDiagnosticCode.PATH_COLLISION in codes(collided)
    assert len(collided.catalog.entries) == 1

    sensitive = profile()
    distinct = classify(
        (facts("Docs/Café.txt", platform=sensitive), facts("docs/Café.txt", platform=sensitive)),
        platform=sensitive,
    )
    assert RepositoryPathDiagnosticCode.PATH_COLLISION not in codes(distinct)
    assert len(distinct.catalog.entries) == 2


def test_fact_order_does_not_change_catalog_or_fingerprint() -> None:
    first = facts("z.txt", material_rules=("role.artifact.v1",))
    second = facts("a.txt", material_rules=("role.source.v1",))
    forward = classify((first, second))
    reverse = classify((second, first))
    assert forward == reverse
    assert forward.fingerprint == reverse.fingerprint
    assert [entry.path.value for entry in forward.catalog.entries] == ["a.txt", "z.txt"]


def test_occurrence_metadata_does_not_change_semantic_result() -> None:
    first = classify((facts(occurrence=(("sample", "one"),)),))
    second = classify((facts(occurrence=(("sample", "two"),)),))
    assert first == second
    assert canonical_bytes(first.catalog) == canonical_bytes(second.catalog)
    assert first.fingerprint == second.fingerprint


def test_catalog_is_bound_and_has_no_mutation_authority() -> None:
    repository, checkout, worktree = identities()
    result = classify((facts(),))
    assert result.catalog.repository_id == repository
    assert result.catalog.checkout_id == checkout
    assert result.catalog.worktree_id == worktree
    assert not hasattr(result, "authorize")
    assert not hasattr(result.catalog, "apply")


def test_diagnostics_contain_only_safe_closed_identifiers() -> None:
    result = classify((facts("safe/relative.txt"), facts("safe/relative.txt")))
    diagnostic = result.diagnostics[0]
    assert isinstance(diagnostic.path_fingerprint, RepositoryFingerprint)
    assert not hasattr(diagnostic, "path")
    assert not hasattr(diagnostic, "content")
    assert not hasattr(diagnostic, "secret")


def test_platform_or_identity_binding_mismatch_is_diagnostic() -> None:
    other_profile = profile(case=RepositoryCaseSensitivity.INSENSITIVE)
    supplied = replace(facts(), path=path("src/main.py", other_profile))
    result = classify((supplied,))
    assert RepositoryPathDiagnosticCode.PATH_BINDING_MISMATCH in codes(result)
