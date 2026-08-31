from dataclasses import replace

from tests.test_repository_runtime_change_sets import snapshot, with_entries
from tests.test_repository_runtime_mutation_plans import (
    CREATE,
    DELETE,
    REPLACE,
    change_set,
)
from tests.test_repository_runtime_mutation_plans import (
    plan as build_plan,
)
from tests.test_repository_runtime_mutation_plans import (
    policy as mutation_policy,
)
from tests.test_repository_runtime_mutation_plans import (
    request as mutation_request,
)

from synapse.repository_runtime import (
    RepositoryAuthorizationAssessmentService,
    RepositoryAuthorizationDiagnosticCode,
    RepositoryAuthorizationFact,
    RepositoryAuthorizationFactEffect,
    RepositoryAuthorizationFactsSnapshot,
    RepositoryAuthorizationFreshness,
    RepositoryAuthorizationOutcome,
    RepositoryAuthorizationPathScope,
    RepositoryAuthorizationRequirement,
    RepositoryFingerprint,
    RepositoryMutationOperationKind,
    RepositoryObservationCompleteness,
    RepositoryPath,
)

NOW = 1_000


def create_plan(*paths: str):
    base = snapshot("existing.txt")
    target = snapshot("existing.txt", *paths)
    changes = change_set(base, target)
    result = build_plan(base, target, changes, mutation_policy(CREATE))
    assert result.plan is not None
    return result.plan


def replace_plan(*, overwrite: bool = False):
    base = snapshot("file.txt")
    target = with_entries(
        base,
        (
            replace(
                base.entries[0],
                content_fingerprint=RepositoryFingerprint.from_content("changed"),
            ),
        ),
    )
    changes = change_set(base, target)
    selected_rule = REPLACE
    request = None
    if overwrite:
        from synapse.repository_runtime import RepositoryCollisionBehavior

        selected_rule = replace(
            REPLACE,
            collision_behavior=RepositoryCollisionBehavior.EXPLICIT_OVERWRITE,
        )
        request = mutation_request(
            base,
            target,
            changes,
            overwrite=(changes.entries[0].fingerprint,),
        )
    result = build_plan(
        base,
        target,
        changes,
        mutation_policy(selected_rule),
        supplied_request=request,
    )
    assert result.plan is not None
    return result.plan


def delete_plan():
    base = snapshot("old.txt")
    target = snapshot("new.txt")
    changes = change_set(base, target)
    result = build_plan(base, target, changes, mutation_policy(DELETE))
    assert result.plan is not None
    return replace(
        result.plan,
        operations=tuple(
            item
            for item in result.plan.operations
            if item.kind is RepositoryMutationOperationKind.DELETE
        ),
    )


def requirement(plan, **changes):
    base = RepositoryAuthorizationRequirement.from_plan(
        plan,
        actor="agent:atlas",
        purpose="repository:update",
        assessment_time=NOW,
        maximum_fact_age=200,
        accepted_sources=(("governance", "authorization-policy", "v1"),),
    )
    return replace(base, **changes)


def fact(plan, **changes):
    operations = plan.operations
    base = RepositoryAuthorizationFact(
        plan.repository_id,
        plan.checkout_id,
        plan.worktree_id,
        plan.fingerprint,
        "agent:atlas",
        "repository:update",
        tuple(item.kind for item in operations),
        tuple(item.scope for item in operations),
        tuple(item.collision_behavior for item in operations),
        tuple(item.recovery_requirement for item in operations),
        tuple(item.path for item in operations),
        (),
        RepositoryAuthorizationPathScope.EXACT,
        any(item.kind is RepositoryMutationOperationKind.DELETE for item in operations),
        any(item.overwrite_intent for item in operations),
        "governance",
        "approval:reference",
        "authorization-policy",
        "v1",
        900,
        900,
        1_100,
        RepositoryObservationCompleteness.COMPLETE,
    )
    return replace(base, **changes)


def assess(plan, facts, *, selected_requirement=None, completeness=RepositoryObservationCompleteness.COMPLETE):
    snapshot = RepositoryAuthorizationFactsSnapshot(tuple(facts), completeness)
    return RepositoryAuthorizationAssessmentService().assess(
        selected_requirement or requirement(plan), plan, snapshot
    )


def codes(result):
    return {item.code for item in result.diagnostics}


def test_matching_external_fact_satisfies_correspondence_without_decision() -> None:
    plan = create_plan("new.txt")
    result = assess(plan, (fact(plan),))
    assert result.assessment.outcome is RepositoryAuthorizationOutcome.SATISFIED
    assert result.assessment.freshness is RepositoryAuthorizationFreshness.FRESH
    assert not hasattr(result.assessment, "authorized")
    assert not hasattr(result.assessment, "approve")
    assert not hasattr(result.assessment, "apply")
    assert not hasattr(plan, "authorization")


def test_plan_repository_actor_and_purpose_must_correspond_exactly() -> None:
    plan = create_plan("new.txt")
    other_plan = create_plan("other.txt")
    wrong = replace(
        fact(plan),
        mutation_plan_fingerprint=other_plan.fingerprint,
        repository_id=plan.repository_id.from_stable_key("other"),
        actor="agent:other",
        purpose="repository:other",
    )
    result = assess(plan, (wrong,))
    assert result.assessment.outcome is RepositoryAuthorizationOutcome.MISMATCH
    assert codes(result) >= {
        RepositoryAuthorizationDiagnosticCode.PLAN_FINGERPRINT_MISMATCH,
        RepositoryAuthorizationDiagnosticCode.REPOSITORY_MISMATCH,
        RepositoryAuthorizationDiagnosticCode.ACTOR_MISMATCH,
        RepositoryAuthorizationDiagnosticCode.PURPOSE_MISMATCH,
    }


def test_create_fact_does_not_cover_replace() -> None:
    plan = replace_plan()
    wrong = replace(
        fact(plan),
        operation_kinds=(RepositoryMutationOperationKind.CREATE,),
    )
    result = assess(plan, (wrong,))
    assert result.assessment.outcome is RepositoryAuthorizationOutcome.MISMATCH
    assert RepositoryAuthorizationDiagnosticCode.OPERATION_NOT_COVERED in codes(result)


def test_exact_path_does_not_cover_descendants() -> None:
    plan = create_plan("dir/file.txt")
    operation = plan.operations[0]
    parent = RepositoryPath(
        "dir", operation.path.profile, operation.path.checkout_id, operation.path.worktree_id
    )
    exact = replace(fact(plan), paths=(parent,))
    result = assess(plan, (exact,))
    assert result.assessment.outcome is RepositoryAuthorizationOutcome.MISMATCH
    assert RepositoryAuthorizationDiagnosticCode.PATH_NOT_COVERED in codes(result)


def test_prefix_recursive_and_wildcard_are_only_used_when_explicit() -> None:
    plan = create_plan("dir/file.txt")
    operation = plan.operations[0]
    parent = RepositoryPath(
        "dir", operation.path.profile, operation.path.checkout_id, operation.path.worktree_id
    )
    recursive = replace(
        fact(plan),
        paths=(parent,),
        path_scope=RepositoryAuthorizationPathScope.RECURSIVE,
    )
    recursive_result = assess(
        plan,
        (recursive,),
        selected_requirement=requirement(plan, allow_broader_facts=True),
    )
    assert recursive_result.assessment.outcome is RepositoryAuthorizationOutcome.SATISFIED

    wildcard = replace(
        fact(plan), paths=(), path_scope=RepositoryAuthorizationPathScope.WILDCARD
    )
    rejected = assess(plan, (wildcard,))
    assert RepositoryAuthorizationDiagnosticCode.BROADER_FACT_REQUIRES_RULE in codes(rejected)
    accepted = assess(
        plan,
        (wildcard,),
        selected_requirement=requirement(plan, allow_broader_facts=True),
    )
    assert accepted.assessment.outcome is RepositoryAuthorizationOutcome.SATISFIED


def test_delete_requires_specific_correspondence() -> None:
    plan = delete_plan()
    denied = assess(plan, (replace(fact(plan), allows_delete=False),))
    assert RepositoryAuthorizationDiagnosticCode.DELETE_CORRESPONDENCE_REQUIRED in codes(denied)
    accepted = assess(plan, (fact(plan),))
    assert accepted.assessment.outcome is RepositoryAuthorizationOutcome.SATISFIED


def test_overwrite_requires_specific_correspondence() -> None:
    plan = replace_plan(overwrite=True)
    denied = assess(plan, (replace(fact(plan), allows_overwrite=False),))
    assert RepositoryAuthorizationDiagnosticCode.OVERWRITE_CORRESPONDENCE_REQUIRED in codes(denied)
    accepted = assess(plan, (fact(plan),))
    assert accepted.assessment.outcome is RepositoryAuthorizationOutcome.SATISFIED


def test_stale_expired_incomplete_and_unavailable_do_not_satisfy() -> None:
    plan = create_plan("new.txt")
    stale = assess(plan, (replace(fact(plan), issued_at=700),))
    assert stale.assessment.outcome is RepositoryAuthorizationOutcome.STALE

    expired = assess(plan, (replace(fact(plan), valid_until=950),))
    assert expired.assessment.outcome is RepositoryAuthorizationOutcome.EXPIRED

    incomplete = assess(
        plan,
        (replace(fact(plan), completeness=RepositoryObservationCompleteness.PARTIAL),),
    )
    assert incomplete.assessment.outcome is RepositoryAuthorizationOutcome.INCOMPLETE

    unavailable = assess(
        plan, (), completeness=RepositoryObservationCompleteness.UNAVAILABLE
    )
    assert unavailable.assessment.outcome is RepositoryAuthorizationOutcome.UNAVAILABLE


def test_conflicting_asserted_and_revoked_facts_fail_closed() -> None:
    plan = create_plan("new.txt")
    asserted = fact(plan)
    revoked = replace(asserted, effect=RepositoryAuthorizationFactEffect.REVOKED)
    result = assess(plan, (asserted, revoked))
    assert result.assessment.outcome is RepositoryAuthorizationOutcome.CONFLICT
    assert RepositoryAuthorizationDiagnosticCode.FACTS_CONFLICT in codes(result)


def test_partial_authorization_remains_partial() -> None:
    plan = create_plan("one.txt", "two.txt")
    first_operation = plan.operations[0]
    subset = replace(
        fact(plan),
        paths=(first_operation.path,),
    )
    result = assess(
        plan,
        (subset,),
        selected_requirement=requirement(plan, allow_combined_subset_facts=True),
    )
    assert result.assessment.outcome is RepositoryAuthorizationOutcome.PARTIAL
    assert RepositoryAuthorizationDiagnosticCode.AUTHORIZATION_PARTIAL in codes(result)


def test_unknown_source_or_version_does_not_correspond() -> None:
    plan = create_plan("new.txt")
    unknown = assess(plan, (replace(fact(plan), authorization_source="unknown"),))
    assert RepositoryAuthorizationDiagnosticCode.SOURCE_UNKNOWN in codes(unknown)
    version = assess(plan, (replace(fact(plan), policy_version="v2"),))
    assert RepositoryAuthorizationDiagnosticCode.SOURCE_VERSION_UNKNOWN in codes(version)


def test_fact_order_and_occurrence_metadata_do_not_change_identity() -> None:
    plan = create_plan("one.txt", "two.txt")
    base_fact = fact(plan)
    second_fact = replace(base_fact, authorization_reference="approval:second")
    first = assess(
        plan,
        (base_fact, second_fact),
        selected_requirement=requirement(plan, occurrence_metadata=(("run", "one"),)),
    )
    changed = (
        replace(second_fact, occurrence_metadata=(("sample", "two"),)),
        replace(base_fact, occurrence_metadata=(("sample", "one"),)),
    )
    snapshot = RepositoryAuthorizationFactsSnapshot(
        changed,
        RepositoryObservationCompleteness.COMPLETE,
        (("capture", "two"),),
    )
    second = RepositoryAuthorizationAssessmentService().assess(
        requirement(plan, occurrence_metadata=(("run", "two"),)), plan, snapshot
    )
    assert first.assessment == second.assessment
    assert first.fingerprint == second.fingerprint


def test_diagnostics_are_redacted_and_assessment_has_no_payload() -> None:
    plan = create_plan("secret/path.txt")
    result = assess(plan, (replace(fact(plan), actor="agent:other"),))
    diagnostic = result.diagnostics[0]
    assert not hasattr(diagnostic, "path")
    assert not hasattr(diagnostic, "content")
    assert not hasattr(diagnostic, "secret")
    assert not hasattr(result.assessment, "payload")
    assert not hasattr(result.assessment, "decision")
