from dataclasses import replace

from tests.test_repository_runtime_change_sets import (
    compare,
    explicit_fact,
    snapshot,
    with_entries,
)

from synapse.repository_runtime import (
    RepositoryChangeType,
    RepositoryCollisionBehavior,
    RepositoryFingerprint,
    RepositoryMutationDiagnosticCode,
    RepositoryMutationOperationKind,
    RepositoryMutationPlanRequest,
    RepositoryMutationPlanService,
    RepositoryMutationPolicy,
    RepositoryMutationPreconditionKind,
    RepositoryMutationRule,
    RepositoryMutationScope,
    RepositoryObservationCompleteness,
    RepositoryRecoveryRequirement,
    RepositoryTopology,
)


def change_set(base, target, facts=()):
    result = compare(base, target, facts)
    assert result.change_set is not None
    return result.change_set


def request(base, target, changes, *, overwrite=(), occurrence=()):
    return RepositoryMutationPlanRequest(
        base.repository_id,
        base.checkout_id,
        base.worktree_id,
        base.platform_profile,
        base.fingerprint,
        target.fingerprint,
        changes.fingerprint,
        overwrite,
        occurrence,
    )


def rule(
    change_type,
    operation,
    scope,
    collision,
    recovery=RepositoryRecoveryRequirement.NOT_REQUIRED,
):
    return RepositoryMutationRule(change_type, operation, scope, collision, recovery)


def policy(*rules, require_complete_inputs=True, require_recovery_for=()):
    return RepositoryMutationPolicy(
        "mutation-policy",
        "v1",
        rules,
        require_complete_inputs,
        require_recovery_for,
    )


def plan(base, target, changes, selected_policy, *, supplied_request=None):
    return RepositoryMutationPlanService().plan(
        supplied_request or request(base, target, changes),
        selected_policy,
        base,
        target,
        changes,
    )


def codes(result):
    return {item.code for item in result.diagnostics}


CREATE = rule(
    RepositoryChangeType.ADDED,
    RepositoryMutationOperationKind.CREATE,
    RepositoryMutationScope.RESOURCE,
    RepositoryCollisionBehavior.CREATE_ONLY,
)
DELETE = rule(
    RepositoryChangeType.DELETED,
    RepositoryMutationOperationKind.DELETE,
    RepositoryMutationScope.RESOURCE,
    RepositoryCollisionBehavior.FAIL_IF_MISSING,
    RepositoryRecoveryRequirement.REQUIRED,
)
REPLACE = rule(
    RepositoryChangeType.MODIFIED,
    RepositoryMutationOperationKind.REPLACE,
    RepositoryMutationScope.CONTENT,
    RepositoryCollisionBehavior.REPLACE_IF_MATCHES,
    RepositoryRecoveryRequirement.REQUIRED,
)
MOVE = rule(
    RepositoryChangeType.RENAMED,
    RepositoryMutationOperationKind.MOVE,
    RepositoryMutationScope.RESOURCE,
    RepositoryCollisionBehavior.FAIL_IF_EXISTS,
    RepositoryRecoveryRequirement.REQUIRED,
)
COPY = rule(
    RepositoryChangeType.COPIED,
    RepositoryMutationOperationKind.COPY,
    RepositoryMutationScope.RESOURCE,
    RepositoryCollisionBehavior.FAIL_IF_EXISTS,
)


def test_empty_policy_does_not_translate_factual_changes() -> None:
    base = snapshot("old.txt")
    target = snapshot("new.txt")
    changes = change_set(base, target)
    result = plan(base, target, changes, policy())
    assert result.plan is not None
    assert result.plan.operations == ()
    assert codes(result) == {
        RepositoryMutationDiagnosticCode.DELETE_POLICY_REQUIRED,
        RepositoryMutationDiagnosticCode.TRANSLATION_RULE_MISSING,
    }


def test_explicit_rules_create_and_delete_without_authority_or_application() -> None:
    base = snapshot("old.txt")
    target = snapshot("new.txt")
    changes = change_set(base, target)
    result = plan(base, target, changes, policy(CREATE, DELETE))
    assert result.plan is not None
    assert {item.kind for item in result.plan.operations} == {
        RepositoryMutationOperationKind.CREATE,
        RepositoryMutationOperationKind.DELETE,
    }
    assert not hasattr(result.plan, "authorize")
    assert not hasattr(result.plan, "apply")
    assert not hasattr(result.plan.operations[0], "payload")


def test_delete_requires_an_explicit_policy_rule() -> None:
    base = snapshot("old.txt")
    target = snapshot("new.txt")
    changes = change_set(base, target)
    result = plan(base, target, changes, policy(CREATE))
    assert RepositoryMutationDiagnosticCode.DELETE_POLICY_REQUIRED in codes(result)
    assert result.plan is not None
    assert all(item.kind is not RepositoryMutationOperationKind.DELETE for item in result.plan.operations)


def test_overwrite_requires_entry_specific_intent() -> None:
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
    overwrite_rule = replace(
        REPLACE,
        collision_behavior=RepositoryCollisionBehavior.EXPLICIT_OVERWRITE,
    )
    missing = plan(base, target, changes, policy(overwrite_rule))
    assert RepositoryMutationDiagnosticCode.OVERWRITE_INTENT_REQUIRED in codes(missing)

    intent = request(base, target, changes, overwrite=(changes.entries[0].fingerprint,))
    accepted = plan(
        base,
        target,
        changes,
        policy(overwrite_rule),
        supplied_request=intent,
    )
    assert accepted.plan is not None
    assert accepted.plan.operations[0].overwrite_intent


def test_plan_binds_exact_inputs_and_complete_preconditions() -> None:
    base = snapshot("file.txt")
    target = with_entries(
        base,
        (replace(base.entries[0], content_fingerprint=RepositoryFingerprint.from_content("v2")),),
    )
    changes = change_set(base, target)
    result = plan(base, target, changes, policy(REPLACE))
    assert result.plan is not None
    assert result.plan.base_snapshot_fingerprint == base.fingerprint
    assert result.plan.target_snapshot_fingerprint == target.fingerprint
    assert result.plan.change_set_fingerprint == changes.fingerprint
    assert {item.kind for item in result.plan.preconditions} >= {
        RepositoryMutationPreconditionKind.REPOSITORY_IDENTITY,
        RepositoryMutationPreconditionKind.CHECKOUT_IDENTITY,
        RepositoryMutationPreconditionKind.WORKTREE_IDENTITY,
        RepositoryMutationPreconditionKind.HEAD_STATE,
        RepositoryMutationPreconditionKind.BRANCH_STATE,
        RepositoryMutationPreconditionKind.INDEX_STATE,
        RepositoryMutationPreconditionKind.WORKSPACE_STATE,
        RepositoryMutationPreconditionKind.PATH_STATE,
        RepositoryMutationPreconditionKind.COMPLETENESS,
        RepositoryMutationPreconditionKind.TOPOLOGY_BOUNDARY,
        RepositoryMutationPreconditionKind.COLLISION_STATE,
    }


def test_stale_base_or_change_set_fails_closed() -> None:
    base = snapshot("file.txt")
    target = snapshot("file.txt", "new.txt")
    changes = change_set(base, target)
    stale = replace(
        request(base, target, changes),
        base_snapshot_fingerprint=RepositoryFingerprint.from_content("stale"),
    )
    result = plan(base, target, changes, policy(CREATE), supplied_request=stale)
    assert result.plan is None
    assert RepositoryMutationDiagnosticCode.BASE_SNAPSHOT_MISMATCH in codes(result)

    stale_entry = replace(
        changes.entries[0],
        target_entry_fingerprint=RepositoryFingerprint.from_content("stale-entry"),
    )
    stale_changes = replace(changes, entries=(stale_entry, *changes.entries[1:]))
    stale_result = plan(
        base,
        target,
        stale_changes,
        policy(CREATE),
        supplied_request=request(base, target, stale_changes),
    )
    assert stale_result.plan is None
    assert RepositoryMutationDiagnosticCode.PATH_EXPECTATION_STALE in codes(stale_result)


def test_incomplete_inputs_never_produce_complete_plan() -> None:
    base = replace(snapshot("file.txt"), completeness=RepositoryObservationCompleteness.PARTIAL)
    target = snapshot("file.txt", "new.txt")
    changes = change_set(base, target)
    result = plan(base, target, changes, policy(CREATE))
    assert result.plan is not None
    assert result.plan.completeness is RepositoryObservationCompleteness.PARTIAL
    assert codes(result) >= {
        RepositoryMutationDiagnosticCode.SNAPSHOT_INCOMPLETE,
        RepositoryMutationDiagnosticCode.CHANGE_SET_INCOMPLETE,
    }


def test_invalid_translation_scope_fails_explicitly() -> None:
    base = snapshot("file.txt")
    target = snapshot("file.txt", "new.txt")
    changes = change_set(base, target)
    invalid = replace(CREATE, scope=RepositoryMutationScope.CONTENT)
    result = plan(base, target, changes, policy(invalid))
    assert RepositoryMutationDiagnosticCode.TRANSLATION_RULE_INVALID in codes(result)


def test_required_recovery_cannot_be_omitted() -> None:
    base = snapshot("file.txt")
    target = with_entries(
        base,
        (replace(base.entries[0], content_fingerprint=RepositoryFingerprint.from_content("v2")),),
    )
    changes = change_set(base, target)
    unsafe = replace(REPLACE, recovery_requirement=RepositoryRecoveryRequirement.NOT_REQUIRED)
    result = plan(
        base,
        target,
        changes,
        policy(unsafe, require_recovery_for=(RepositoryMutationOperationKind.REPLACE,)),
    )
    assert RepositoryMutationDiagnosticCode.RECOVERY_REQUIREMENT_MISSING in codes(result)


def test_rename_and_copy_require_validated_change_evidence() -> None:
    base = snapshot("old.txt")
    target = snapshot("new.txt")
    fact = explicit_fact(RepositoryChangeType.RENAMED, base.entries[0], target.entries[0])
    changes = change_set(base, target, (fact,))
    renamed = plan(base, target, changes, policy(MOVE))
    assert renamed.plan is not None
    assert renamed.plan.operations[0].kind is RepositoryMutationOperationKind.MOVE

    stripped = replace(changes.entries[0], evidence_reference=None)
    invalid_changes = replace(changes, entries=(stripped,))
    invalid = plan(
        base,
        target,
        invalid_changes,
        policy(MOVE),
        supplied_request=request(base, target, invalid_changes),
    )
    assert RepositoryMutationDiagnosticCode.EVIDENCE_REQUIRED in codes(invalid)


def test_move_cycles_are_rejected() -> None:
    base = snapshot("a.txt", "b.txt")
    target = with_entries(
        base,
        tuple(
            replace(
                entry,
                content_fingerprint=RepositoryFingerprint.from_content(f"target:{entry.path.value}"),
            )
            for entry in base.entries
        ),
    )
    before = {entry.path.value: entry for entry in base.entries}
    after = {entry.path.value: entry for entry in target.entries}
    facts = (
        explicit_fact(RepositoryChangeType.RENAMED, before["a.txt"], after["b.txt"]),
        explicit_fact(RepositoryChangeType.RENAMED, before["b.txt"], after["a.txt"]),
    )
    changes = change_set(base, target, facts)
    result = plan(base, target, changes, policy(MOVE))
    assert result.plan is None
    assert RepositoryMutationDiagnosticCode.MOVE_CYCLE in codes(result)


def test_repository_boundaries_fail_closed() -> None:
    base = snapshot("vendor")
    boundary = replace(
        base.entries[0],
        topology=RepositoryTopology.SUBMODULE,
        classification=replace(
            base.entries[0].classification,
            topology=RepositoryTopology.SUBMODULE,
        ),
    )
    base = with_entries(base, (boundary,))
    target = snapshot("vendor", "vendor/new.txt")
    changes = change_set(base, target)
    result = plan(base, target, changes, policy(CREATE))
    assert result.plan is None
    assert RepositoryMutationDiagnosticCode.REPOSITORY_BOUNDARY_TRAVERSAL in codes(result)


def test_operation_order_and_occurrence_do_not_change_fingerprint() -> None:
    base = snapshot("a.txt", "b.txt")
    target = snapshot("a.txt", "b.txt", "c.txt", "d.txt")
    changes = change_set(base, target)
    first = plan(
        base,
        target,
        changes,
        policy(CREATE),
        supplied_request=request(base, target, changes, occurrence=(("run", "one"),)),
    )
    second_changes = replace(changes, entries=tuple(reversed(changes.entries)))
    second = plan(
        base,
        target,
        second_changes,
        policy(CREATE),
        supplied_request=request(base, target, second_changes, occurrence=(("run", "two"),)),
    )
    assert first.plan == second.plan
    assert first.fingerprint == second.fingerprint


def test_semantic_operation_change_changes_plan_fingerprint() -> None:
    base = snapshot("file.txt")
    target = snapshot("file.txt", "new.txt")
    changes = change_set(base, target)
    create_only = plan(base, target, changes, policy(CREATE))
    fail_exists = plan(
        base,
        target,
        changes,
        policy(replace(CREATE, collision_behavior=RepositoryCollisionBehavior.FAIL_IF_EXISTS)),
    )
    assert create_only.plan is not None and fail_exists.plan is not None
    assert create_only.plan.fingerprint != fail_exists.plan.fingerprint


def test_diagnostics_are_safe_and_operations_have_no_payload() -> None:
    base = snapshot("safe/path.txt")
    target = snapshot("other.txt")
    changes = change_set(base, target)
    result = plan(base, target, changes, policy())
    diagnostic = result.diagnostics[0]
    assert not hasattr(diagnostic, "path")
    assert not hasattr(diagnostic, "content")
    assert not hasattr(diagnostic, "secret")
    assert not hasattr(diagnostic, "patch")


def test_plan_is_immutable_and_contains_no_authorization_fact() -> None:
    base = snapshot("file.txt")
    target = snapshot("file.txt", "new.txt")
    changes = change_set(base, target)
    result = plan(base, target, changes, policy(CREATE))
    assert result.plan is not None
    assert not hasattr(result.plan, "authorization")
    assert not hasattr(result.plan, "authorized")
    assert not hasattr(result.plan, "executed")
    assert isinstance(result.plan.operations, tuple)
