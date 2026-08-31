from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from tests.test_repository_runtime_change_sets import snapshot
from tests.test_repository_runtime_mutation_plans import CREATE, change_set, plan, policy
from tests.test_repository_runtime_restore_points import replace_context
from tests.test_repository_runtime_snapshots import identities, profile

from synapse.repository_runtime import (
    RepositoryAdapterBoundaryViolation,
    RepositoryAdapterCapabilityState,
    RepositoryAdapterFeature,
    RepositoryFingerprint,
    RepositoryLocalAdapter,
    RepositoryLocalAdapterConfig,
    RepositoryMutationApplicationOutcome,
    RepositoryMutationAttempt,
    RepositoryMutationMaterial,
    RepositoryMutationPreconditionOutcome,
    RepositoryMutationSideEffect,
    RepositoryMutationStepRequest,
    RepositoryObservationRequest,
    RepositoryPath,
    RepositoryRecoveryAction,
    RepositoryRecoveryAttempt,
    RepositoryRecoveryMaterial,
    RepositoryRecoveryPlan,
    RepositoryRecoveryState,
    RepositoryRecoveryStep,
    RepositoryRecoveryStepState,
)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Repository Test")
    git(root, "config", "user.email", "repository@example.invalid")
    (root / "existing.txt").write_bytes(b"base")
    git(root, "add", "existing.txt")
    git(root, "commit", "-m", "base")
    return root


def config(repository: Path, **changes) -> RepositoryLocalAdapterConfig:
    repository_id, checkout_id, worktree_id = identities()
    values = {
        "repository_root": str(repository),
        "restore_root": str(repository.parent / "restore"),
        "repository_id": repository_id,
        "checkout_id": checkout_id,
        "worktree_id": worktree_id,
        "platform_profile": profile(),
    }
    values.update(changes)
    return RepositoryLocalAdapterConfig(**values)


def create_adapter(repository: Path):
    base = snapshot("existing.txt")
    target = snapshot("existing.txt", "new.txt")
    planned = plan(base, target, change_set(base, target), policy(CREATE))
    assert planned.plan is not None
    mutation_plan = planned.plan
    operation = mutation_plan.operations[0]
    adapter = RepositoryLocalAdapter(
        config(
            repository,
            mutation_plan=mutation_plan,
            mutation_materials=(
                RepositoryMutationMaterial(
                    operation.operation_id,
                    operation.expected_target_fingerprint,
                    b"created",
                ),
            ),
        )
    )
    attempt = RepositoryMutationAttempt(
        RepositoryFingerprint.from_content("adapter-attempt"),
        RepositoryFingerprint.from_content("adapter-request"),
        mutation_plan.fingerprint,
        (operation.operation_id,),
    )
    step = RepositoryMutationStepRequest(
        attempt.attempt_id, mutation_plan.fingerprint, 0, operation
    )
    return adapter, attempt, step


def test_real_repository_observation_preserves_dirty_and_untracked(repository: Path) -> None:
    (repository / "existing.txt").write_bytes(b"dirty")
    (repository / "untracked.txt").write_bytes(b"untracked")
    selected = config(repository)
    adapter = RepositoryLocalAdapter(selected)
    facts = adapter.facts_for(
        RepositoryObservationRequest(
            selected.repository_id,
            selected.checkout_id,
            selected.worktree_id,
            selected.platform_profile,
        )
    )
    assert facts.head is not None and facts.head.branch_name == "main"
    assert facts.workspace_status.value == "dirty"
    assert {item.path.value for item in facts.entries} >= {
        "existing.txt",
        "untracked.txt",
    }
    assert (repository / "untracked.txt").read_bytes() == b"untracked"


def test_capability_report_makes_hooks_filters_lfs_and_forbidden_git_explicit(
    repository: Path,
) -> None:
    git(repository, "config", "filter.example.clean", "example-clean")
    report = RepositoryLocalAdapter(config(repository)).capability_report()
    states = {item.feature: item.state for item in report.capabilities}
    assert states[RepositoryAdapterFeature.FILTERS] is RepositoryAdapterCapabilityState.DEGRADED
    assert states[RepositoryAdapterFeature.STAGING] is RepositoryAdapterCapabilityState.UNSUPPORTED
    assert states[RepositoryAdapterFeature.COMMIT] is RepositoryAdapterCapabilityState.UNSUPPORTED
    assert states[RepositoryAdapterFeature.PUSH] is RepositoryAdapterCapabilityState.UNSUPPORTED


@pytest.mark.parametrize("interference", ("workspace", "index", "head", "path"))
def test_stale_state_blocks_before_side_effect(repository: Path, interference: str) -> None:
    adapter, attempt, step = create_adapter(repository)
    if interference == "workspace":
        (repository / "external.txt").write_bytes(b"interference")
    elif interference == "index":
        (repository / "staged.txt").write_bytes(b"staged")
        git(repository, "add", "staged.txt")
    elif interference == "head":
        git(repository, "commit", "--allow-empty", "-m", "external-head")
    else:
        (repository / "existing.txt").write_bytes(b"external-path-change")
    report = adapter.revalidate_preconditions(attempt, (step.operation,))
    assert {item.outcome for item in report.results} == {
        RepositoryMutationPreconditionOutcome.STALE
    }
    result = adapter.apply_operation(step)
    assert result.outcome is RepositoryMutationApplicationOutcome.FAILED
    assert result.side_effect is RepositoryMutationSideEffect.NONE
    assert not (repository / "new.txt").exists()


def test_planned_mutation_touches_only_declared_path_and_never_stages(repository: Path) -> None:
    adapter, _, step = create_adapter(repository)
    head_before = git(repository, "rev-parse", "HEAD")
    staged_before = git(repository, "diff", "--cached", "--name-only")
    result = adapter.apply_operation(step)
    assert result.outcome is RepositoryMutationApplicationOutcome.APPLIED
    assert (repository / "new.txt").read_bytes() == b"created"
    assert git(repository, "rev-parse", "HEAD") == head_before
    assert git(repository, "diff", "--cached", "--name-only") == staged_before


def test_restore_point_required_blocks_replace_before_side_effect(repository: Path) -> None:
    _, mutation_plan, _ = replace_context()
    operation = mutation_plan.operations[0]
    adapter = RepositoryLocalAdapter(
        config(
            repository,
            mutation_plan=mutation_plan,
            mutation_materials=(
                RepositoryMutationMaterial(
                    operation.operation_id,
                    operation.expected_target_fingerprint,
                    b"target",
                ),
            ),
        )
    )
    attempt = RepositoryMutationAttempt(
        RepositoryFingerprint.from_content("replace-attempt"),
        RepositoryFingerprint.from_content("replace-request"),
        mutation_plan.fingerprint,
        (operation.operation_id,),
    )
    result = adapter.apply_operation(
        RepositoryMutationStepRequest(attempt.attempt_id, mutation_plan.fingerprint, 0, operation)
    )
    assert result.outcome is RepositoryMutationApplicationOutcome.FAILED
    assert (repository / "existing.txt").read_bytes() == b"base"


def test_partial_filesystem_failure_remains_explicit(repository: Path) -> None:
    (repository / "new.txt").mkdir()
    adapter, _, step = create_adapter(repository)
    result = adapter.apply_operation(step)
    assert result.outcome is RepositoryMutationApplicationOutcome.FAILED
    assert result.side_effect is RepositoryMutationSideEffect.PARTIAL


def test_reparse_or_symlink_escape_fails_closed(repository: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = repository / "escape"
    if os.name == "nt":
        created = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
            check=False,
            capture_output=True,
        )
        assert created.returncode == 0
    else:
        os.symlink(outside, link, target_is_directory=True)
    selected = config(repository)
    adapter = RepositoryLocalAdapter(selected)
    logical = selected.platform_profile
    with pytest.raises(RepositoryAdapterBoundaryViolation):
        adapter.fingerprint_facts_for(
            (
                RepositoryPath(
                    "escape/file.txt",
                    logical,
                    selected.checkout_id,
                    selected.worktree_id,
                ),
            )
        )


def test_nested_repository_boundary_is_not_traversed(repository: Path) -> None:
    nested = repository / "nested"
    nested.mkdir()
    git(nested, "init", "-b", "nested-main")
    (nested / "inside.txt").write_bytes(b"nested")
    selected = config(repository)
    adapter = RepositoryLocalAdapter(selected)
    with pytest.raises(RepositoryAdapterBoundaryViolation):
        adapter.fingerprint_facts_for(
            (
                RepositoryPath(
                    "nested/inside.txt",
                    selected.platform_profile,
                    selected.checkout_id,
                    selected.worktree_id,
                ),
            )
        )


def test_detached_real_worktree_and_common_git_dir_are_observed(
    repository: Path, tmp_path: Path
) -> None:
    worktree = tmp_path / "detached-worktree"
    git(repository, "worktree", "add", "--detach", str(worktree), "HEAD")
    selected = config(worktree)
    adapter = RepositoryLocalAdapter(selected)
    facts = adapter.facts_for(
        RepositoryObservationRequest(
            selected.repository_id,
            selected.checkout_id,
            selected.worktree_id,
            selected.platform_profile,
        )
    )
    assert facts.head is not None and facts.head.kind.value == "detached"
    assert adapter.capability_report().git_version is not None


def test_recovery_step_is_coverage_bound_and_requires_factual_verification(
    repository: Path,
) -> None:
    _, checkout_id, worktree_id = identities()
    logical = RepositoryPath("existing.txt", profile(), checkout_id, worktree_id)
    step = RepositoryRecoveryStep(
        0,
        RepositoryRecoveryAction.RESTORE_CONTENT,
        RepositoryFingerprint.from_content(logical),
        RepositoryFingerprint.from_content("verified-coverage"),
        RepositoryFingerprint.from_content("divergent"),
        RepositoryFingerprint.from_content("restored"),
    )
    recovery_plan = RepositoryRecoveryPlan(
        RepositoryFingerprint.from_content("recovery-request"),
        identities()[0],
        checkout_id,
        worktree_id,
        profile(),
        RepositoryFingerprint.from_content("base"),
        RepositoryFingerprint.from_content("mutation-plan"),
        RepositoryFingerprint.from_content("mutation-journal"),
        RepositoryFingerprint.from_content("verification"),
        RepositoryFingerprint.from_content("manifest"),
        RepositoryFingerprint.from_content("restore-verification"),
        "recovery-policy",
        "v1",
        RepositoryRecoveryState.PLANNED,
        (step,),
        (),
    )
    (repository / "existing.txt").write_bytes(b"divergent")
    adapter = RepositoryLocalAdapter(
        config(
            repository,
            recovery_plan=recovery_plan,
            recovery_materials=(RepositoryRecoveryMaterial(step.fingerprint, logical, b"base"),),
        )
    )
    attempt = RepositoryRecoveryAttempt(
        RepositoryFingerprint.from_content("recovery-attempt"),
        recovery_plan.request_fingerprint,
        recovery_plan.fingerprint,
        (step.fingerprint,),
    )
    applied = adapter.apply_recovery_step(attempt, step)
    assert applied.state is RepositoryRecoveryStepState.APPLIED
    base = snapshot("existing.txt")
    verified = adapter.verify_recovered_state(attempt, base)
    assert verified.state_restored
    assert verified.observed_snapshot_fingerprint == base.fingerprint

    replace_step = RepositoryRecoveryStep(
        0,
        RepositoryRecoveryAction.RESTORE_CONTENT,
        RepositoryFingerprint.from_content("outside"),
        RepositoryFingerprint.from_content("outside-coverage"),
        None,
        RepositoryFingerprint.from_content("outside-target"),
    )
    rejected = adapter.apply_recovery_step(attempt, replace_step)
    assert rejected.state is RepositoryRecoveryStepState.FAILED
