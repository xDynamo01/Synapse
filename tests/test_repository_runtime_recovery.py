from tests.test_repository_runtime_verification import request as verification_request
from tests.test_repository_runtime_verification import setup as verification_setup

from synapse.repository_runtime import (
    RepositoryMutationSideEffect,
    RepositoryObservationCompleteness,
    RepositoryRecoveryAction,
    RepositoryRecoveryInterruption,
    RepositoryRecoveryObservation,
    RepositoryRecoveryPolicy,
    RepositoryRecoveryPreconditionReport,
    RepositoryRecoveryPreconditionState,
    RepositoryRecoveryRequest,
    RepositoryRecoveryService,
    RepositoryRecoveryState,
    RepositoryRecoveryStepResult,
    RepositoryRecoveryStepState,
    RepositoryRecoveryVerification,
    RepositoryVerificationService,
)

ALL_ACTIONS = tuple(RepositoryRecoveryAction)


def context(*, occurrence=()):
    base, target, mutation_plan, journal, restore, verification_policy = verification_setup()
    verification = RepositoryVerificationService().verify(
        verification_request(
            base,
            target,
            mutation_plan,
            journal,
            restore,
            base,
            verification_policy,
        ),
        verification_policy,
        base,
        target,
        mutation_plan,
        journal,
        restore,
        base,
    )
    assert verification.reconciliation.recovery_required
    assert restore.manifest is not None and restore.verification is not None
    policy = RepositoryRecoveryPolicy("recovery-policy", "v1", ALL_ACTIONS)
    request = RepositoryRecoveryRequest(
        base.repository_id,
        base.checkout_id,
        base.worktree_id,
        base.platform_profile,
        base.fingerprint,
        mutation_plan.fingerprint,
        journal.attempt.attempt_id,
        journal.fingerprint,
        verification.fingerprint,
        verification.reconciliation.fingerprint,
        restore.manifest.fingerprint,
        restore.verification.fingerprint,
        policy.policy_id,
        policy.policy_version,
        "recovery:one",
        occurrence,
    )
    planned = RepositoryRecoveryService().plan(
        request, policy, base, mutation_plan, journal, verification, restore
    )
    return base, request, policy, planned


class Preconditions:
    def __init__(self, state=RepositoryRecoveryPreconditionState.SATISFIED):
        self.state = state
        self.calls = 0

    def revalidate_recovery_preconditions(self, attempt, plan):
        self.calls += 1
        return RepositoryRecoveryPreconditionReport(
            attempt.attempt_id,
            plan.fingerprint,
            self.state,
            tuple(
                step.expected_current_fingerprint
                for step in plan.steps
                if step.expected_current_fingerprint is not None
            ),
        )


class Steps:
    def __init__(self, state=RepositoryRecoveryStepState.APPLIED):
        self.state = state
        self.calls = []

    def apply_recovery_step(self, attempt, step):
        self.calls.append(step.fingerprint)
        return RepositoryRecoveryStepResult(
            attempt.attempt_id,
            step.fingerprint,
            self.state,
            RepositoryMutationSideEffect.DECLARED
            if self.state is RepositoryRecoveryStepState.APPLIED
            else RepositoryMutationSideEffect.PARTIAL,
            (step.expected_restored_fingerprint,),
        )


class Observations:
    def __init__(self, *, corresponds=True, interference=False):
        self.corresponds = corresponds
        self.interference = interference

    def observe_recovery_step(self, attempt, step, result):
        return RepositoryRecoveryObservation(
            attempt.attempt_id,
            step.fingerprint,
            self.corresponds,
            self.interference,
            result.observed_fingerprints,
        )


class Interruption:
    def __init__(self, interrupted=True):
        self.interrupted = interrupted
        self.calls = 0

    def interrupt_recovery(self, attempt, step_fingerprint):
        self.calls += 1
        return RepositoryRecoveryInterruption(attempt.attempt_id, self.interrupted)


class Verification:
    def __init__(self, *, restored=True, interference=False):
        self.restored = restored
        self.interference = interference
        self.calls = 0

    def verify_recovered_state(self, attempt, base):
        self.calls += 1
        return RepositoryRecoveryVerification(
            attempt.attempt_id,
            base.fingerprint,
            base.fingerprint if self.restored else None,
            RepositoryObservationCompleteness.COMPLETE,
            self.restored,
            self.interference,
        )


def recover(
    *, preconditions=None, steps=None, observations=None, interruption=None, verification=None
):
    base, request, _, planned = context()
    assert planned.plan is not None
    return RepositoryRecoveryService().recover(
        request,
        planned.plan,
        base,
        preconditions or Preconditions(),
        steps or Steps(),
        observations or Observations(),
        interruption or Interruption(),
        verification or Verification(),
    )


def test_divergence_and_request_do_not_start_rollback() -> None:
    _, _, _, planned = context()
    assert planned.state is RepositoryRecoveryState.PLANNED
    assert planned.journal is None


def test_plan_uses_only_verified_restore_point_coverage() -> None:
    _, _, _, planned = context()
    assert planned.plan is not None
    assert planned.plan.steps
    assert all(
        step.coverage_entry_fingerprint is not None
        for step in planned.plan.steps
        if step.action is not RepositoryRecoveryAction.VERIFY_RESTORED_STATE
    )


def test_recovered_requires_post_recovery_verification() -> None:
    failed = recover(verification=Verification(restored=False))
    assert failed.state is RepositoryRecoveryState.VERIFICATION_FAILED
    recovered = recover()
    assert recovered.state is RepositoryRecoveryState.RECOVERED


def test_step_success_is_not_restored_state() -> None:
    verifier = Verification(restored=False)
    result = recover(verification=verifier)
    assert verifier.calls == 1
    assert result.state is RepositoryRecoveryState.VERIFICATION_FAILED


def test_partial_recovery_never_becomes_recovered() -> None:
    result = recover(steps=Steps(RepositoryRecoveryStepState.PARTIAL))
    assert result.state is RepositoryRecoveryState.PARTIALLY_RECOVERED


def test_external_interference_blocks_clean_recovery() -> None:
    result = recover(observations=Observations(interference=True))
    assert result.state is RepositoryRecoveryState.MANUAL_INTERVENTION


def test_precondition_interference_stops_before_first_side_effect() -> None:
    steps = Steps()
    result = recover(
        preconditions=Preconditions(RepositoryRecoveryPreconditionState.EXTERNAL_INTERFERENCE),
        steps=steps,
    )
    assert result.state is RepositoryRecoveryState.MANUAL_INTERVENTION
    assert steps.calls == []


def test_same_facts_and_different_occurrence_metadata_have_same_identity() -> None:
    _, request_one, _, planned_one = context(occurrence=(("trace", "one"),))
    _, request_two, _, planned_two = context(occurrence=(("trace", "two"),))
    assert request_one.fingerprint == request_two.fingerprint
    assert planned_one.fingerprint == planned_two.fingerprint


def test_rollback_failed_is_distinct_from_verification_failed() -> None:
    rollback_failed = recover(
        preconditions=Preconditions(RepositoryRecoveryPreconditionState.MISMATCH)
    )
    verification_failed = recover(verification=Verification(restored=False))
    assert rollback_failed.state is RepositoryRecoveryState.ROLLBACK_FAILED
    assert verification_failed.state is RepositoryRecoveryState.VERIFICATION_FAILED


def test_result_replay_is_canonical() -> None:
    first = recover()
    second = recover()
    assert first.fingerprint == second.fingerprint
    assert first.journal is not None and second.journal is not None
    assert first.journal.fingerprint == second.journal.fingerprint
