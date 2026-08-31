from dataclasses import replace

from tests.test_repository_runtime_change_sets import snapshot, with_entries
from tests.test_repository_runtime_mutation_application import apply_with, context

from synapse.repository_runtime import (
    RepositoryFingerprint,
    RepositoryObservationCompleteness,
    RepositoryReconciliationState,
    RepositoryVerificationDiagnosticCode,
    RepositoryVerificationDimension,
    RepositoryVerificationOutcome,
    RepositoryVerificationPolicy,
    RepositoryVerificationRequest,
    RepositoryVerificationService,
)

REQUIRED = tuple(
    dimension
    for dimension in RepositoryVerificationDimension
    if dimension
    not in {RepositoryVerificationDimension.PATH, RepositoryVerificationDimension.COLLISION}
)


def setup():
    base, plan, authorization, restore = context()
    target = with_entries(
        base,
        (
            replace(
                base.entries[0],
                content_fingerprint=RepositoryFingerprint.from_content("changed"),
            ),
        ),
    )
    assert target.fingerprint == plan.target_snapshot_fingerprint
    applied, _ = apply_with(base, plan, authorization, restore)
    policy = RepositoryVerificationPolicy("verification-policy", "v1", REQUIRED)
    return base, target, plan, applied.journal, restore, policy


def request(
    base, target, plan, journal, restore, observation, policy, *, stale=False, occurrence=()
):
    assert restore.manifest is not None and restore.verification is not None
    return RepositoryVerificationRequest(
        base.repository_id,
        base.checkout_id,
        base.worktree_id,
        base.platform_profile,
        base.fingerprint,
        target.fingerprint,
        plan.fingerprint,
        journal.attempt.attempt_id,
        journal.fingerprint,
        restore.manifest.fingerprint,
        restore.verification.fingerprint,
        observation.fingerprint,
        policy.policy_id,
        policy.policy_version,
        stale,
        occurrence,
    )


def verify(observation, *, stale=False, occurrence=()):
    base, target, plan, journal, restore, policy = setup()
    result = RepositoryVerificationService().verify(
        request(
            base,
            target,
            plan,
            journal,
            restore,
            observation,
            policy,
            stale=stale,
            occurrence=occurrence,
        ),
        policy,
        base,
        target,
        plan,
        journal,
        restore,
        observation,
    )
    return result


def test_applied_journal_is_not_proof_when_observation_matches_base() -> None:
    base, *_ = setup()
    result = verify(base)
    assert result.outcome is RepositoryVerificationOutcome.NOT_APPLIED
    assert result.reconciliation.state is RepositoryReconciliationState.ROLLBACK_CANDIDATE
    assert RepositoryVerificationDiagnosticCode.APPLICATION_NOT_PROOF in {
        item.code for item in result.diagnostics
    }


def test_complete_target_match_is_conforming_and_deterministic() -> None:
    _, target, *_ = setup()
    first = verify(target, occurrence=(("trace", "one"),))
    second = verify(target, occurrence=(("trace", "two"),))
    assert first.outcome is RepositoryVerificationOutcome.CONFORMING
    assert first.reconciliation.state is RepositoryReconciliationState.STATE_MATCHES_TARGET
    assert first.fingerprint == second.fingerprint


def test_partial_observation_never_verifies() -> None:
    _, target, *_ = setup()
    partial = replace(target, completeness=RepositoryObservationCompleteness.PARTIAL)
    result = verify(partial)
    assert result.outcome is RepositoryVerificationOutcome.UNVERIFIABLE
    assert RepositoryVerificationDiagnosticCode.OBSERVATION_INCOMPLETE in {
        item.code for item in result.diagnostics
    }


def test_stale_observation_is_not_final_state() -> None:
    _, target, *_ = setup()
    result = verify(target, stale=True)
    assert result.outcome is RepositoryVerificationOutcome.STALE_OBSERVATION


def test_head_branch_index_and_workspace_diverge_independently() -> None:
    _, target, *_ = setup()
    observed = replace(
        target,
        head_fingerprint=RepositoryFingerprint.from_content("other-head"),
        branch_reference="other-branch",
        index_fingerprint=RepositoryFingerprint.from_content("other-index"),
        workspace_fingerprint=RepositoryFingerprint.from_content("other-workspace"),
    )
    codes = {item.code for item in verify(observed).diagnostics}
    assert {
        RepositoryVerificationDiagnosticCode.HEAD_DIVERGENCE,
        RepositoryVerificationDiagnosticCode.BRANCH_DIVERGENCE,
        RepositoryVerificationDiagnosticCode.INDEX_DIVERGENCE,
        RepositoryVerificationDiagnosticCode.WORKSPACE_DIVERGENCE,
    } <= codes


def test_path_outside_plan_remains_visible() -> None:
    _, target, *_ = setup()
    extra = snapshot("outside.txt").entries[0]
    observed = with_entries(target, target.entries + (extra,))
    result = verify(observed)
    assert RepositoryVerificationDiagnosticCode.UNEXPECTED_MUTATION in {
        item.code for item in result.diagnostics
    }
    assert result.reconciliation.state is RepositoryReconciliationState.MANUAL_INTERVENTION_REQUIRED


def test_models_are_immutable_and_diagnostics_are_redacted() -> None:
    _, target, *_ = setup()
    result = verify(target)
    assert all(not hasattr(item, "path") for item in result.diagnostics)
    assert all(not hasattr(item, "content") for item in result.diagnostics)
