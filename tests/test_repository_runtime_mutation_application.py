from dataclasses import replace

import pytest
from tests.test_repository_runtime_authorization_facts import (
    assess,
    fact,
)
from tests.test_repository_runtime_authorization_facts import (
    requirement as authorization_requirement,
)
from tests.test_repository_runtime_change_sets import snapshot
from tests.test_repository_runtime_mutation_plans import (
    CREATE,
    change_set,
)
from tests.test_repository_runtime_mutation_plans import (
    plan as build_mutation_plan,
)
from tests.test_repository_runtime_mutation_plans import (
    policy as mutation_policy,
)
from tests.test_repository_runtime_restore_points import (
    evaluate as evaluate_restore,
)
from tests.test_repository_runtime_restore_points import (
    manifest_for,
    replace_context,
    verification_facts,
)
from tests.test_repository_runtime_restore_points import (
    planned as plan_restore,
)

from synapse.repository_runtime import (
    InvalidRepositoryMutationApplicationModel,
    RepositoryAuthorizationOutcome,
    RepositoryFingerprint,
    RepositoryMutationApplicationOutcome,
    RepositoryMutationApplicationRequest,
    RepositoryMutationApplicationService,
    RepositoryMutationCleanupRequirement,
    RepositoryMutationCleanupResult,
    RepositoryMutationDiagnosticCode,
    RepositoryMutationInterruptionResult,
    RepositoryMutationObservationResult,
    RepositoryMutationPreconditionOutcome,
    RepositoryMutationPreconditionReport,
    RepositoryMutationPreconditionResult,
    RepositoryMutationSideEffect,
    RepositoryMutationStepResult,
)


def context(*, two_operations=False):
    if two_operations:
        base = snapshot("existing.txt")
        target = snapshot("existing.txt", "a.txt", "b.txt")
        changes = change_set(base, target)
        planned_mutation = build_mutation_plan(
            base, target, changes, mutation_policy(CREATE)
        )
        assert planned_mutation.plan is not None
        mutation_plan = planned_mutation.plan
        authorization = assess(
            mutation_plan,
            (fact(mutation_plan),),
            selected_requirement=authorization_requirement(mutation_plan),
        ).assessment
    else:
        base, mutation_plan, authorization = replace_context()
    restore_requirement = plan_restore(base, mutation_plan, authorization).requirement
    assert restore_requirement is not None
    manifest = manifest_for(restore_requirement)
    restore = evaluate_restore(
        base,
        mutation_plan,
        authorization,
        manifest,
        verification_facts(manifest),
    )
    assert restore.verification is not None and restore.verification.recoverable
    return base, mutation_plan, authorization, restore


def request(base, mutation_plan, authorization, restore, occurrence=()):
    return RepositoryMutationApplicationRequest(
        base.repository_id,
        base.checkout_id,
        base.worktree_id,
        base.platform_profile,
        base.fingerprint,
        mutation_plan.fingerprint,
        authorization.fingerprint,
        restore.fingerprint,
        "attempt:one",
        occurrence,
    )


class Preconditions:
    def __init__(
        self,
        outcome=RepositoryMutationPreconditionOutcome.SATISFIED,
        *,
        observed_matches=True,
    ):
        self.outcome = outcome
        self.observed_matches = observed_matches
        self.calls = 0

    def revalidate_preconditions(self, attempt, preconditions):
        self.calls += 1
        return RepositoryMutationPreconditionReport(
            attempt.attempt_id,
            attempt.mutation_plan_fingerprint,
            tuple(
                RepositoryMutationPreconditionResult(
                    RepositoryFingerprint.from_content(item),
                    self.outcome,
                    item.expected_fingerprint
                    if self.observed_matches
                    else RepositoryFingerprint.from_content("stale"),
                )
                for item in preconditions
            ),
        )


class Operations:
    def __init__(self, outcomes=(), *, wrong_operation=False):
        self.outcomes = tuple(outcomes)
        self.wrong_operation = wrong_operation
        self.calls = []

    def apply_operation(self, step):
        self.calls.append(step.operation.operation_id)
        outcome = (
            self.outcomes[step.sequence_index]
            if step.sequence_index < len(self.outcomes)
            else RepositoryMutationApplicationOutcome.APPLIED
        )
        partial = outcome is RepositoryMutationApplicationOutcome.PARTIALLY_APPLIED
        operation_id = (
            RepositoryFingerprint.from_content("not-in-plan")
            if self.wrong_operation
            else step.operation.operation_id
        )
        return RepositoryMutationStepResult(
            step.attempt_id,
            operation_id,
            outcome,
            RepositoryMutationSideEffect.PARTIAL
            if partial
            else RepositoryMutationSideEffect.DECLARED,
            RepositoryMutationCleanupRequirement.REQUIRED
            if partial
            else RepositoryMutationCleanupRequirement.NOT_REQUIRED,
            (step.operation.expected_target_fingerprint,)
            if step.operation.expected_target_fingerprint
            else (),
        )


class Observations:
    def __init__(self):
        self.calls = []

    def observe_result(self, step, result):
        self.calls.append(step.operation.operation_id)
        return RepositoryMutationObservationResult(
            step.attempt_id,
            step.operation.operation_id,
            result.observed_fingerprints,
            result.operation_id == step.operation.operation_id,
        )


class Interruption:
    def __init__(self, interrupted=True):
        self.interrupted = interrupted
        self.calls = []

    def interrupt_sequence(self, attempt, operation_id):
        self.calls.append(operation_id)
        return RepositoryMutationInterruptionResult(
            attempt.attempt_id, operation_id, self.interrupted
        )


class Cleanup:
    def __init__(self, outcome=RepositoryMutationApplicationOutcome.APPLIED):
        self.outcome = outcome
        self.calls = 0
        self.completed_step_counts = []

    def request_cleanup(self, attempt, completed_steps):
        self.calls += 1
        self.completed_step_counts.append(len(completed_steps))
        return RepositoryMutationCleanupResult(attempt.attempt_id, self.outcome)


def apply_with(
    base,
    mutation_plan,
    authorization,
    restore,
    *,
    preconditions=None,
    operations=None,
    observations=None,
    interruption=None,
    cleanup=None,
    supplied_request=None,
):
    ports = (
        preconditions or Preconditions(),
        operations or Operations(),
        observations or Observations(),
        interruption or Interruption(),
        cleanup or Cleanup(),
    )
    result = RepositoryMutationApplicationService().apply(
        supplied_request or request(base, mutation_plan, authorization, restore),
        base,
        mutation_plan,
        authorization,
        restore,
        *ports,
    )
    return result, ports


def codes(result):
    return {item.code for item in result.diagnostics}


def test_unsatisfied_assessment_does_not_call_any_port() -> None:
    base, mutation_plan, authorization, restore = context()
    authorization = replace(
        authorization, outcome=RepositoryAuthorizationOutcome.PARTIAL
    )
    supplied = request(base, mutation_plan, authorization, restore)
    result, ports = apply_with(
        base,
        mutation_plan,
        authorization,
        restore,
        supplied_request=supplied,
    )
    assert result.journal.outcome is RepositoryMutationApplicationOutcome.NOT_STARTED
    assert RepositoryMutationDiagnosticCode.AUTHORIZATION_NOT_SATISFIED in codes(result)
    assert ports[0].calls == 0
    assert ports[1].calls == []


def test_nonrecoverable_restore_point_blocks_before_first_port() -> None:
    base, mutation_plan, authorization, restore = context()
    blocked = replace(restore, verification=None)
    result, ports = apply_with(
        base,
        mutation_plan,
        authorization,
        blocked,
        supplied_request=request(base, mutation_plan, authorization, blocked),
    )
    assert RepositoryMutationDiagnosticCode.RESTORE_POINT_NOT_RECOVERABLE in codes(result)
    assert ports[0].calls == 0
    assert ports[1].calls == []


def test_stale_precondition_fails_before_first_side_effect() -> None:
    base, mutation_plan, authorization, restore = context()
    stale = Preconditions(RepositoryMutationPreconditionOutcome.STALE)
    operations = Operations()
    result, _ = apply_with(
        base,
        mutation_plan,
        authorization,
        restore,
        preconditions=stale,
        operations=operations,
    )
    assert result.journal.outcome is RepositoryMutationApplicationOutcome.PRECONDITION_FAILED
    assert RepositoryMutationDiagnosticCode.PRECONDITION_STALE in codes(result)
    assert stale.calls == 1
    assert operations.calls == []


def test_mismatched_observed_precondition_fails_before_side_effect() -> None:
    base, mutation_plan, authorization, restore = context()
    mismatched = Preconditions(observed_matches=False)
    operations = Operations()
    result, _ = apply_with(
        base,
        mutation_plan,
        authorization,
        restore,
        preconditions=mismatched,
        operations=operations,
    )
    assert result.journal.outcome is RepositoryMutationApplicationOutcome.PRECONDITION_FAILED
    assert RepositoryMutationDiagnosticCode.PRECONDITION_MISMATCH in codes(result)
    assert operations.calls == []


def test_steps_follow_canonical_plan_order() -> None:
    base, mutation_plan, authorization, restore = context(two_operations=True)
    operations = Operations()
    result, _ = apply_with(
        base,
        mutation_plan,
        authorization,
        restore,
        operations=operations,
    )
    expected = [item.operation_id for item in mutation_plan.operations]
    assert operations.calls == expected
    assert [item.operation_id for item in result.journal.steps] == expected
    assert result.journal.outcome is RepositoryMutationApplicationOutcome.APPLIED


def test_operation_not_in_plan_is_rejected_and_sequence_stops() -> None:
    base, mutation_plan, authorization, restore = context(two_operations=True)
    operations = Operations(wrong_operation=True)
    result, _ = apply_with(
        base,
        mutation_plan,
        authorization,
        restore,
        operations=operations,
    )
    assert RepositoryMutationDiagnosticCode.OPERATION_NOT_IN_PLAN in codes(result)
    assert len(operations.calls) == 1
    assert result.journal.steps[1].application_outcome is RepositoryMutationApplicationOutcome.NOT_STARTED


def test_port_success_does_not_imply_final_verification() -> None:
    base, mutation_plan, authorization, restore = context()
    result, _ = apply_with(base, mutation_plan, authorization, restore)
    assert result.journal.outcome is RepositoryMutationApplicationOutcome.APPLIED
    assert not result.journal.final_state_verified
    assert not hasattr(result.journal, "committed")
    assert not hasattr(result.journal, "pushed")


def test_partial_application_remains_visible_and_interrupts_following_steps() -> None:
    base, mutation_plan, authorization, restore = context(two_operations=True)
    operations = Operations(
        (RepositoryMutationApplicationOutcome.PARTIALLY_APPLIED,)
    )
    interruption = Interruption()
    cleanup = Cleanup()
    result, _ = apply_with(
        base,
        mutation_plan,
        authorization,
        restore,
        operations=operations,
        interruption=interruption,
        cleanup=cleanup,
    )
    assert result.journal.outcome is RepositoryMutationApplicationOutcome.PARTIALLY_APPLIED
    assert result.journal.steps[0].application_outcome is RepositoryMutationApplicationOutcome.PARTIALLY_APPLIED
    assert result.journal.steps[1].application_outcome is RepositoryMutationApplicationOutcome.NOT_STARTED
    assert len(interruption.calls) == 1
    assert cleanup.calls == 1
    assert cleanup.completed_step_counts == [1]


def test_cleanup_required_does_not_imply_cleanup_completed() -> None:
    base, mutation_plan, authorization, restore = context()
    operations = Operations(
        (RepositoryMutationApplicationOutcome.PARTIALLY_APPLIED,)
    )
    cleanup = Cleanup(RepositoryMutationApplicationOutcome.CLEANUP_FAILED)
    result, _ = apply_with(
        base,
        mutation_plan,
        authorization,
        restore,
        operations=operations,
        cleanup=cleanup,
    )
    assert result.journal.outcome is RepositoryMutationApplicationOutcome.CLEANUP_FAILED
    assert result.journal.cleanup_outcome is RepositoryMutationApplicationOutcome.CLEANUP_FAILED
    assert RepositoryMutationDiagnosticCode.CLEANUP_FAILED in codes(result)


def test_failed_interruption_requires_manual_intervention() -> None:
    base, mutation_plan, authorization, restore = context()
    operations = Operations((RepositoryMutationApplicationOutcome.FAILED,))
    interruption = Interruption(interrupted=False)
    result, _ = apply_with(
        base,
        mutation_plan,
        authorization,
        restore,
        operations=operations,
        interruption=interruption,
    )
    assert result.journal.outcome is RepositoryMutationApplicationOutcome.MANUAL_INTERVENTION
    assert RepositoryMutationDiagnosticCode.MANUAL_INTERVENTION_REQUIRED in codes(result)


def test_journal_contains_no_path_payload_or_secret() -> None:
    base, mutation_plan, authorization, restore = context()
    result, _ = apply_with(base, mutation_plan, authorization, restore)
    assert not hasattr(result.journal, "path")
    assert not hasattr(result.journal, "payload")
    assert not hasattr(result.journal, "secret")
    assert all(not hasattr(step, "path") for step in result.journal.steps)


def test_invalid_result_order_fails_closed() -> None:
    base, mutation_plan, authorization, restore = context(two_operations=True)
    result, _ = apply_with(base, mutation_plan, authorization, restore)
    with pytest.raises(InvalidRepositoryMutationApplicationModel):
        replace(result.journal, steps=tuple(reversed(result.journal.steps)))


def test_same_factual_sequence_has_equivalent_journal() -> None:
    base, mutation_plan, authorization, restore = context(two_operations=True)
    first, _ = apply_with(
        base,
        mutation_plan,
        authorization,
        restore,
        supplied_request=request(
            base, mutation_plan, authorization, restore, (("run", "one"),)
        ),
    )
    second, _ = apply_with(
        base,
        mutation_plan,
        authorization,
        restore,
        supplied_request=request(
            base, mutation_plan, authorization, restore, (("run", "two"),)
        ),
    )
    assert first.journal.fingerprint == second.journal.fingerprint
    assert first.fingerprint == second.fingerprint
