from dataclasses import replace

from tests.test_repository_runtime_authorization_facts import (
    assess,
    fact,
)
from tests.test_repository_runtime_authorization_facts import (
    requirement as authorization_requirement,
)
from tests.test_repository_runtime_change_sets import explicit_fact, snapshot, with_entries
from tests.test_repository_runtime_mutation_plans import (
    CREATE,
    DELETE,
    MOVE,
    REPLACE,
    change_set,
)
from tests.test_repository_runtime_mutation_plans import (
    plan as build_mutation_plan,
)
from tests.test_repository_runtime_mutation_plans import (
    policy as mutation_policy,
)

from synapse.repository_runtime import (
    RepositoryAuthorizationOutcome,
    RepositoryChangeType,
    RepositoryFingerprint,
    RepositoryGitTracking,
    RepositoryMaterialRole,
    RepositoryMutationOperationKind,
    RepositoryObservationCompleteness,
    RepositoryRestorePointDiagnosticCode,
    RepositoryRestorePointDimension,
    RepositoryRestorePointEntry,
    RepositoryRestorePointManifest,
    RepositoryRestorePointMaterialHandling,
    RepositoryRestorePointPolicy,
    RepositoryRestorePointRequest,
    RepositoryRestorePointService,
    RepositoryRestorePointVerificationFact,
    RepositoryRestorePointVerificationState,
    RepositorySensitivity,
    RepositoryTopology,
)


def policy(**changes):
    base = RepositoryRestorePointPolicy(
        "restore-policy",
        "v1",
        (
            RepositoryMutationOperationKind.CREATE,
            RepositoryMutationOperationKind.REPLACE,
            RepositoryMutationOperationKind.DELETE,
            RepositoryMutationOperationKind.MOVE,
        ),
        (
            RepositoryRestorePointDimension.CONTENT,
            RepositoryRestorePointDimension.METADATA,
            RepositoryRestorePointDimension.HEAD,
            RepositoryRestorePointDimension.BRANCH,
            RepositoryRestorePointDimension.INDEX,
            RepositoryRestorePointDimension.UNTRACKED,
            RepositoryRestorePointDimension.TOPOLOGY,
        ),
        True,
        RepositoryRestorePointMaterialHandling.INCLUDE,
        RepositoryRestorePointMaterialHandling.INCLUDE,
        RepositoryRestorePointMaterialHandling.INCLUDE,
        RepositoryRestorePointMaterialHandling.BLOCK,
        10_000,
        100_000,
        100,
        True,
        (("sha256", "v1"),),
    )
    return replace(base, **changes)


def authorized(base, target, *rules):
    changes = change_set(base, target)
    planned = build_mutation_plan(
        base, target, changes, mutation_policy(*rules)
    )
    assert planned.plan is not None
    plan = planned.plan
    assessed = assess(
        plan,
        (fact(plan),),
        selected_requirement=authorization_requirement(plan),
    ).assessment
    assert assessed.outcome is RepositoryAuthorizationOutcome.SATISFIED
    return plan, assessed


def replace_context(*, classification=None):
    base = snapshot("file.txt")
    if classification is not None:
        base = with_entries(
            base, (replace(base.entries[0], classification=classification),)
        )
    target = with_entries(
        base,
        (
            replace(
                base.entries[0],
                content_fingerprint=RepositoryFingerprint.from_content("changed"),
            ),
        ),
    )
    plan, assessment = authorized(base, target, REPLACE)
    return base, plan, assessment


def create_context():
    base = snapshot("existing.txt")
    target = snapshot("existing.txt", "new.txt")
    plan, assessment = authorized(base, target, CREATE)
    return base, plan, assessment


def delete_context():
    base = snapshot("old.txt")
    target = snapshot("new.txt")
    changes = change_set(base, target)
    planned = build_mutation_plan(base, target, changes, mutation_policy(DELETE))
    assert planned.plan is not None
    plan = replace(
        planned.plan,
        operations=tuple(
            item
            for item in planned.plan.operations
            if item.kind is RepositoryMutationOperationKind.DELETE
        ),
    )
    assessment = assess(
        plan,
        (fact(plan),),
        selected_requirement=authorization_requirement(plan),
    ).assessment
    return base, plan, assessment


def request(base, plan, assessment, occurrence=()):
    return RepositoryRestorePointRequest(
        base.repository_id,
        base.checkout_id,
        base.worktree_id,
        base.platform_profile,
        base.fingerprint,
        plan.fingerprint,
        assessment.fingerprint,
        occurrence,
    )


def planned(base, plan, assessment, selected_policy=None):
    return RepositoryRestorePointService().plan(
        request(base, plan, assessment),
        selected_policy or policy(),
        base,
        plan,
        assessment,
    )


def manifest_for(requirement, *, entries=None, completeness=RepositoryObservationCompleteness.COMPLETE, occurrence=()):
    produced = tuple(
        RepositoryRestorePointEntry(
            item.path_fingerprint,
            item.expected_content_fingerprint,
            item.expected_metadata_fingerprint,
            f"restore:{index}",
            item.expected_size,
            item.coverage_kind,
            item.completeness,
            "sha256",
            "v1",
        )
        for index, item in enumerate(requirement.coverage)
    )
    return RepositoryRestorePointManifest(
        requirement.repository_id,
        requirement.checkout_id,
        requirement.worktree_id,
        requirement.platform_profile,
        requirement.base_snapshot_fingerprint,
        requirement.mutation_plan_fingerprint,
        requirement.authorization_assessment_fingerprint,
        requirement.fingerprint,
        requirement.policy_id,
        requirement.policy_version,
        produced if entries is None else tuple(entries),
        completeness,
        occurrence,
    )


def verification_facts(manifest):
    return tuple(
        RepositoryRestorePointVerificationFact(
            item.fingerprint,
            item.expected_content_fingerprint,
            item.expected_metadata_fingerprint,
            RepositoryRestorePointVerificationState.VERIFIED,
        )
        for item in manifest.entries
    )


def evaluate(base, plan, assessment, manifest, facts, selected_policy=None):
    return RepositoryRestorePointService().evaluate(
        request(base, plan, assessment),
        selected_policy or policy(),
        base,
        plan,
        assessment,
        manifest,
        tuple(facts),
    )


def codes(result):
    return {item.code for item in result.diagnostics}


def test_snapshot_does_not_imply_restore_point() -> None:
    base = snapshot("file.txt")
    assert not hasattr(base, "restore_point")
    assert not hasattr(base, "recoverable")


def test_planned_requirement_does_not_imply_manifest_or_verification() -> None:
    base, plan, assessment = replace_context()
    result = planned(base, plan, assessment)
    assert result.requirement is not None
    assert result.manifest is None
    assert result.verification is None
    assert not hasattr(result.requirement, "rollback")


def test_complete_verified_manifest_is_recoverable_without_rollback() -> None:
    base, plan, assessment = replace_context()
    requirement = planned(base, plan, assessment).requirement
    assert requirement is not None
    manifest = manifest_for(requirement)
    result = evaluate(base, plan, assessment, manifest, verification_facts(manifest))
    assert result.verification is not None
    assert result.verification.state is RepositoryRestorePointVerificationState.VERIFIED
    assert result.verification.recoverable
    assert not hasattr(result.verification, "rollback")
    assert not hasattr(result.verification, "restore")


def test_delete_and_replace_have_explicit_content_coverage() -> None:
    replace_base, replace_plan, replace_assessment = replace_context()
    replace_requirement = planned(
        replace_base, replace_plan, replace_assessment
    ).requirement
    assert replace_requirement is not None
    assert any(item.expected_content_fingerprint for item in replace_requirement.coverage)

    delete_base, delete_plan, delete_assessment = delete_context()
    delete_requirement = planned(delete_base, delete_plan, delete_assessment).requirement
    assert delete_requirement is not None
    assert any(item.expected_content_fingerprint for item in delete_requirement.coverage)


def test_move_covers_source_and_destination() -> None:
    base = snapshot("old.txt")
    target = snapshot("new.txt")
    rename = explicit_fact(
        RepositoryChangeType.RENAMED, base.entries[0], target.entries[0]
    )
    changes = change_set(base, target, (rename,))
    planned_move = build_mutation_plan(
        base, target, changes, mutation_policy(MOVE)
    )
    assert planned_move.plan is not None
    mutation_plan = planned_move.plan
    assessment = assess(
        mutation_plan,
        (fact(mutation_plan),),
        selected_requirement=authorization_requirement(mutation_plan),
    ).assessment
    restore_requirement = planned(base, mutation_plan, assessment).requirement
    assert restore_requirement is not None
    kinds = {item.coverage_kind.value for item in restore_requirement.coverage}
    assert {"move_source", "move_destination"} <= kinds


def test_missing_entry_or_verification_is_not_recoverable() -> None:
    base, plan, assessment = replace_context()
    requirement = planned(base, plan, assessment).requirement
    assert requirement is not None
    complete = manifest_for(requirement)
    manifest = manifest_for(requirement, entries=complete.entries[1:])
    result = evaluate(base, plan, assessment, manifest, verification_facts(manifest))
    assert RepositoryRestorePointDiagnosticCode.REQUIRED_ENTRY_MISSING in codes(result)
    assert result.verification is not None and not result.verification.recoverable

    unavailable = evaluate(base, plan, assessment, complete, ())
    assert unavailable.verification is not None
    assert unavailable.verification.state is RepositoryRestorePointVerificationState.UNAVAILABLE
    assert not unavailable.verification.recoverable


def test_manifest_for_other_plan_or_snapshot_fails_closed() -> None:
    base, plan, assessment = replace_context()
    requirement = planned(base, plan, assessment).requirement
    assert requirement is not None
    manifest = manifest_for(requirement)
    other = create_context()[1]
    mismatched = replace(manifest, mutation_plan_fingerprint=other.fingerprint)
    result = evaluate(base, plan, assessment, mismatched, verification_facts(mismatched))
    assert RepositoryRestorePointDiagnosticCode.MUTATION_PLAN_MISMATCH in codes(result)
    assert result.verification is not None and not result.verification.recoverable


def test_non_corresponding_authorization_assessment_fails_closed() -> None:
    base, plan, assessment = replace_context()
    partial = replace(assessment, outcome=RepositoryAuthorizationOutcome.PARTIAL)
    result = planned(base, plan, partial)
    assert result.requirement is None
    assert RepositoryRestorePointDiagnosticCode.AUTHORIZATION_CORRESPONDENCE_REQUIRED in codes(result)


def test_untracked_collision_remains_visible() -> None:
    base = snapshot("file.txt")
    classification = replace(
        base.entries[0].classification,
        tracking=RepositoryGitTracking.UNTRACKED,
    )
    base, plan, assessment = replace_context(classification=classification)
    requirement = planned(base, plan, assessment).requirement
    assert requirement is not None
    assert any(item.coverage_kind.value == "untracked_collision" for item in requirement.coverage)


def test_generated_and_ignored_are_not_excluded_by_inference() -> None:
    base = snapshot("file.txt")
    classification = replace(
        base.entries[0].classification,
        tracking=RepositoryGitTracking.IGNORED,
        material_role=RepositoryMaterialRole.GENERATED,
    )
    base, plan, assessment = replace_context(classification=classification)
    requirement = planned(base, plan, assessment).requirement
    assert requirement is not None
    assert any(item.classification == classification for item in requirement.coverage)


def test_secret_risk_requires_explicit_policy() -> None:
    base = snapshot("file.txt")
    secret = replace(
        base.entries[0].classification,
        sensitivity=RepositorySensitivity.SECRET_RISK,
    )
    base, plan, assessment = replace_context(classification=secret)
    blocked = planned(base, plan, assessment)
    assert blocked.requirement is None
    assert RepositoryRestorePointDiagnosticCode.SENSITIVE_CONTENT_BLOCKED in codes(blocked)

    allowed = planned(
        base,
        plan,
        assessment,
        policy(secret_risk_handling=RepositoryRestorePointMaterialHandling.INCLUDE),
    )
    assert allowed.requirement is not None


def test_topology_boundaries_are_not_traversed() -> None:
    base, mutation_plan, _ = replace_context()
    boundary_entry = replace(
        base.entries[0],
        topology=RepositoryTopology.SUBMODULE,
        classification=replace(
            base.entries[0].classification,
            topology=RepositoryTopology.SUBMODULE,
        ),
    )
    boundary_base = with_entries(base, (boundary_entry,))
    boundary_plan = replace(
        mutation_plan,
        base_snapshot_fingerprint=boundary_base.fingerprint,
    )
    boundary_assessment = assess(
        boundary_plan,
        (fact(boundary_plan),),
        selected_requirement=authorization_requirement(boundary_plan),
    ).assessment
    result = planned(boundary_base, boundary_plan, boundary_assessment)
    assert result.requirement is None
    assert RepositoryRestorePointDiagnosticCode.TOPOLOGY_BOUNDARY_TRAVERSAL in codes(result)


def test_unknown_algorithm_and_corrupt_verification_fail() -> None:
    base, plan, assessment = replace_context()
    requirement = planned(base, plan, assessment).requirement
    assert requirement is not None
    manifest = manifest_for(requirement)
    unsupported = replace(manifest.entries[0], integrity_algorithm="unknown")
    bad_manifest = manifest_for(
        requirement, entries=(unsupported, *manifest.entries[1:])
    )
    unsupported_result = evaluate(
        base, plan, assessment, bad_manifest, verification_facts(bad_manifest)
    )
    assert unsupported_result.verification is not None
    assert unsupported_result.verification.state is RepositoryRestorePointVerificationState.UNSUPPORTED

    corrupt_facts = list(verification_facts(manifest))
    corrupt_facts[0] = replace(
        corrupt_facts[0], state=RepositoryRestorePointVerificationState.CORRUPT
    )
    corrupt = evaluate(base, plan, assessment, manifest, corrupt_facts)
    assert corrupt.verification is not None
    assert corrupt.verification.state is RepositoryRestorePointVerificationState.CORRUPT
    assert not corrupt.verification.recoverable


def test_fingerprint_mismatch_and_duplicate_logical_reference_fail() -> None:
    base, plan, assessment = replace_context()
    requirement = planned(base, plan, assessment).requirement
    assert requirement is not None
    manifest = manifest_for(requirement)
    changed = replace(
        manifest.entries[0],
        expected_content_fingerprint=RepositoryFingerprint.from_content("wrong"),
    )
    duplicated = tuple(
        replace(item, logical_storage_reference="restore:duplicate")
        for item in (changed, *manifest.entries[1:])
    )
    bad_manifest = manifest_for(requirement, entries=duplicated)
    result = evaluate(
        base, plan, assessment, bad_manifest, verification_facts(bad_manifest)
    )
    assert codes(result) >= {
        RepositoryRestorePointDiagnosticCode.ENTRY_FINGERPRINT_MISMATCH,
        RepositoryRestorePointDiagnosticCode.LOGICAL_REFERENCE_DUPLICATE,
    }
    assert result.verification is not None
    assert result.verification.state is RepositoryRestorePointVerificationState.MISMATCH
    assert not result.verification.recoverable


def test_entry_and_manifest_limits_are_enforced() -> None:
    base, plan, assessment = replace_context()
    requirement = planned(base, plan, assessment).requirement
    assert requirement is not None
    manifest = manifest_for(requirement)
    result = evaluate(
        base,
        plan,
        assessment,
        manifest,
        verification_facts(manifest),
        policy(maximum_entry_size=0, maximum_total_size=0, maximum_entries=1),
    )
    assert result.verification is not None
    assert result.verification.state is RepositoryRestorePointVerificationState.OVERSIZED
    assert not result.verification.recoverable


def test_entry_order_and_occurrence_do_not_change_identity() -> None:
    base, plan, assessment = replace_context()
    requirement = planned(base, plan, assessment).requirement
    assert requirement is not None
    first = manifest_for(requirement, occurrence=(("capture", "one"),))
    changed_entries = tuple(
        replace(item, occurrence_metadata=(("sample", "changed"),))
        for item in reversed(first.entries)
    )
    second = manifest_for(
        requirement,
        entries=changed_entries,
        occurrence=(("capture", "two"),),
    )
    assert first.fingerprint == second.fingerprint


def test_diagnostics_are_redacted_and_entries_have_no_payload() -> None:
    base, plan, assessment = replace_context()
    requirement = planned(base, plan, assessment).requirement
    assert requirement is not None
    manifest = manifest_for(requirement, entries=())
    result = evaluate(base, plan, assessment, manifest, ())
    diagnostic = result.diagnostics[0]
    assert not hasattr(diagnostic, "path")
    assert not hasattr(diagnostic, "content")
    assert not hasattr(diagnostic, "secret")
    assert not hasattr(manifest, "archive")
    assert all(not hasattr(item, "payload") for item in manifest.entries)
