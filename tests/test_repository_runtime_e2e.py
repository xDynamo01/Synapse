from __future__ import annotations

import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from tests.test_repository_runtime_authorization_facts import (
    fact as authorization_fact,
)
from tests.test_repository_runtime_authorization_facts import (
    requirement as authorization_requirement,
)
from tests.test_repository_runtime_change_sets import policy as change_policy
from tests.test_repository_runtime_change_sets import request as change_request
from tests.test_repository_runtime_change_sets import snapshot, with_entries
from tests.test_repository_runtime_coding_sessions import NOW as LEASE_NOW
from tests.test_repository_runtime_coding_sessions import contract as session_contract
from tests.test_repository_runtime_composition import config, git
from tests.test_repository_runtime_mutation_application import request as application_request
from tests.test_repository_runtime_mutation_plans import CREATE
from tests.test_repository_runtime_mutation_plans import policy as mutation_policy
from tests.test_repository_runtime_mutation_plans import request as mutation_request
from tests.test_repository_runtime_persistence import draft
from tests.test_repository_runtime_recovery import (
    Interruption as RecoveryInterruption,
)
from tests.test_repository_runtime_recovery import (
    Observations as RecoveryObservations,
)
from tests.test_repository_runtime_recovery import Preconditions as RecoveryPreconditions
from tests.test_repository_runtime_recovery import Steps as RecoverySteps
from tests.test_repository_runtime_recovery import Verification as RecoveryVerification
from tests.test_repository_runtime_recovery import context as recovery_context
from tests.test_repository_runtime_restore_points import (
    manifest_for,
    verification_facts,
)
from tests.test_repository_runtime_restore_points import (
    policy as restore_policy,
)
from tests.test_repository_runtime_restore_points import (
    request as restore_request,
)
from tests.test_repository_runtime_snapshots import (
    path_facts,
    snapshot_policy,
)
from tests.test_repository_runtime_snapshots import (
    request as snapshot_request,
)
from tests.test_repository_runtime_verification import (
    request as verification_request,
)
from tests.test_repository_runtime_verification import setup as verification_setup

from synapse.repository_runtime import (
    RepositoryAdapterBoundaryViolation,
    RepositoryAdapterFeature,
    RepositoryArtifactKind,
    RepositoryAuthorizationFactsSnapshot,
    RepositoryFingerprint,
    RepositoryMutationApplicationOutcome,
    RepositoryMutationMaterial,
    RepositoryObservationCompleteness,
    RepositoryObservationRequest,
    RepositoryPath,
    RepositoryPathClassificationPolicy,
    RepositoryPersistedLifecycleState,
    RepositoryReconciliationState,
    RepositoryRecordCompleteness,
    RepositoryRecoveryPreconditionState,
    RepositoryRecoveryState,
    RepositoryRecoveryStepState,
    RepositoryStoreResponsibility,
    RepositoryTopology,
    RepositoryVerificationOutcome,
)
from synapse.repository_runtime_composition import RepositoryRuntimeBuilder
from synapse.repository_runtime_integrations import (
    CodingSessionDiagnosticCode,
    CodingSessionIdentity,
    CodingSessionRepositoryIntentAdapter,
    RepositoryObservationIntent,
)


@pytest.fixture
def real_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Repository E2E")
    git(root, "config", "user.email", "repository-e2e@example.invalid")
    (root / "existing.txt").write_bytes(b"existing")
    git(root, "add", "existing.txt")
    git(root, "commit", "-m", "base")
    return root


def _bytes_fingerprint(value: bytes) -> RepositoryFingerprint:
    return RepositoryFingerprint("sha256:" + hashlib.sha256(value).hexdigest())


def test_runtime_observation_classification_snapshot_pipeline(
    real_repository: Path, tmp_path: Path
) -> None:
    runtime = RepositoryRuntimeBuilder().build(config(real_repository, tmp_path))
    binding = config(real_repository, tmp_path)
    request = RepositoryObservationRequest(
        binding.repository_id,
        binding.checkout_id,
        binding.worktree_id,
        binding.platform_profile,
    )
    observation = runtime.observation.assess(request, runtime.adapters.local.facts_for(request))
    assert observation.observation is not None

    classified = runtime.classification.classify(
        repository_id=binding.repository_id,
        checkout_id=binding.checkout_id,
        worktree_id=binding.worktree_id,
        observation_fingerprint=observation.fingerprint,
        platform_profile=binding.platform_profile,
        policy=RepositoryPathClassificationPolicy("e2e-path-policy", "v1"),
        facts=(path_facts("existing.txt"),),
    )
    assert classified.catalog is not None
    catalog = classified.catalog
    fingerprint_facts = runtime.adapters.local.fingerprint_facts_for(
        tuple(entry.path for entry in catalog.entries)
    )
    built = runtime.snapshots.build(
        snapshot_request(observation, catalog),
        snapshot_policy(),
        observation,
        catalog,
        fingerprint_facts,
    )

    assert built.snapshot is not None
    assert built.snapshot.observation_fingerprint == observation.fingerprint
    assert built.snapshot.path_catalog_fingerprint == catalog.fingerprint
    runtime.close()


def _journey(real_repository: Path, tmp_path: Path):
    initial = RepositoryRuntimeBuilder().build(config(real_repository, tmp_path))
    binding = config(real_repository, tmp_path)
    observation_request = RepositoryObservationRequest(
        binding.repository_id,
        binding.checkout_id,
        binding.worktree_id,
        binding.platform_profile,
    )
    facts = initial.adapters.local.facts_for(observation_request)
    observation = initial.observation.assess(observation_request, facts)
    assert observation.observation is not None

    base = snapshot("existing.txt")
    raw_target = snapshot("existing.txt", "new.txt")
    content = b"created-through-runtime"
    target = with_entries(
        raw_target,
        tuple(
            replace(entry, content_fingerprint=_bytes_fingerprint(content))
            if entry.path.value == "new.txt"
            else entry
            for entry in raw_target.entries
        ),
    )
    changes = initial.change_sets.compare(
        change_request(base, target),
        change_policy(),
        base,
        target,
        (),
    )
    assert changes.change_set is not None
    planned = initial.mutation_planning.plan(
        mutation_request(base, target, changes.change_set),
        mutation_policy(CREATE),
        base,
        target,
        changes.change_set,
    )
    assert planned.plan is not None
    plan = planned.plan
    authorization = initial.authorization.assess(
        authorization_requirement(plan),
        plan,
        RepositoryAuthorizationFactsSnapshot(
            (authorization_fact(plan),), RepositoryObservationCompleteness.COMPLETE
        ),
    ).assessment
    restore_planned = initial.restore_points.plan(
        restore_request(base, plan, authorization),
        restore_policy(),
        base,
        plan,
        authorization,
    )
    assert restore_planned.requirement is not None
    manifest = manifest_for(restore_planned.requirement)
    restore = initial.restore_points.evaluate(
        restore_request(base, plan, authorization),
        restore_policy(),
        base,
        plan,
        authorization,
        manifest,
        verification_facts(manifest),
    )
    operation = plan.operations[0]
    initial.close()

    configured = config(
        real_repository,
        tmp_path,
        mutation_plan=plan,
        mutation_materials=(
            RepositoryMutationMaterial(
                operation.operation_id, operation.expected_target_fingerprint, content
            ),
        ),
        restore_manifest=manifest,
    )
    runtime = RepositoryRuntimeBuilder().build(configured)
    return runtime, base, target, plan, authorization, restore, observation, content


def test_real_e2e_observation_planning_authorization_restore_application_and_replay(
    real_repository: Path, tmp_path: Path
) -> None:
    runtime, base, target, plan, authorization, restore, observation, content = _journey(
        real_repository, tmp_path
    )
    result = runtime.mutation_application.apply(
        application_request(base, plan, authorization, restore),
        base,
        plan,
        authorization,
        restore,
        runtime.adapters.local,
        runtime.adapters.local,
        runtime.adapters.local,
        runtime.adapters.local,
        runtime.adapters.local,
    )
    assert result.journal.outcome is RepositoryMutationApplicationOutcome.APPLIED
    assert (real_repository / "new.txt").read_bytes() == content
    observed_fingerprint = runtime.adapters.local.fingerprint_facts_for((plan.operations[0].path,))[
        0
    ].content_fingerprint
    assert observed_fingerprint == target.entries[-1].content_fingerprint
    assert observation.observation is not None

    record = draft(
        RepositoryStoreResponsibility.MUTATION_LIFECYCLE,
        RepositoryArtifactKind.MUTATION_JOURNAL,
        "journal:e2e",
        payload={"journal_fingerprint": result.journal.fingerprint.value},
        state=RepositoryPersistedLifecycleState.APPLICATION_PARTIAL,
        completeness=RepositoryRecordCompleteness.PARTIAL,
    )
    first = runtime.persistence.mutation_lifecycle.append(record)
    replayed = runtime.persistence.mutation_lifecycle.append(record)
    assert first.record.semantic_fingerprint == replayed.record.semantic_fingerprint
    assert len(runtime.persistence.mutation_lifecycle.replay(record.stream_identity).records) == 1
    runtime.close()

    restarted = RepositoryRuntimeBuilder().build(config(real_repository, tmp_path))
    replay = restarted.persistence.mutation_lifecycle.restart_state(record.stream_identity)
    assert replay.records[0].semantic_fingerprint == first.record.semantic_fingerprint
    assert replay.lifecycle_states == (RepositoryPersistedLifecycleState.APPLICATION_PARTIAL,)
    assert restarted.health().schema_valid
    restarted.close()


@pytest.mark.parametrize("interference", ("head", "index", "workspace", "path"))
def test_real_stale_state_blocks_before_first_side_effect(
    real_repository: Path, tmp_path: Path, interference: str
) -> None:
    runtime, base, _, plan, authorization, restore, _, _ = _journey(real_repository, tmp_path)
    if interference == "head":
        git(real_repository, "commit", "--allow-empty", "-m", "external-head")
    elif interference == "index":
        (real_repository / "index.txt").write_bytes(b"index")
        git(real_repository, "add", "index.txt")
    elif interference == "workspace":
        (real_repository / "outside.txt").write_bytes(b"outside")
    else:
        (real_repository / "existing.txt").write_bytes(b"changed")
    result = runtime.mutation_application.apply(
        application_request(base, plan, authorization, restore),
        base,
        plan,
        authorization,
        restore,
        runtime.adapters.local,
        runtime.adapters.local,
        runtime.adapters.local,
        runtime.adapters.local,
        runtime.adapters.local,
    )
    assert result.journal.outcome is RepositoryMutationApplicationOutcome.PRECONDITION_FAILED
    assert not (real_repository / "new.txt").exists()
    runtime.close()


def test_two_sessions_and_conflicting_write_leases_fail_closed(
    real_repository: Path, tmp_path: Path
) -> None:
    integration = CodingSessionRepositoryIntentAdapter()
    runtime = RepositoryRuntimeBuilder().build(
        config(
            real_repository,
            tmp_path,
            coding_sessions_enabled=True,
            coding_sessions_adapter=integration,
        )
    )
    session, lease = session_contract()
    competing = replace(
        lease,
        lease_reference="lease:competing",
        session_id=CodingSessionIdentity.from_stable_key("competing-session"),
    )
    result = runtime.adapters.coding_sessions.translate(
        RepositoryObservationIntent(
            session=session,
            lease=lease,
            observed_at=LEASE_NOW,
            conflicting_leases=(competing,),
        )
    )
    assert result.translated_request is None
    assert CodingSessionDiagnosticCode.WRITE_LEASE_CONFLICT in {
        item.code for item in result.diagnostics
    }
    runtime.close()


@pytest.mark.parametrize(
    ("kind", "state", "completeness", "store_name"),
    (
        (
            RepositoryArtifactKind.OBSERVATION,
            RepositoryPersistedLifecycleState.OBSERVATION_PARTIAL,
            RepositoryRecordCompleteness.PARTIAL,
            "observation_snapshots",
        ),
        (
            RepositoryArtifactKind.SNAPSHOT,
            RepositoryPersistedLifecycleState.NONE,
            RepositoryRecordCompleteness.COMPLETE,
            "observation_snapshots",
        ),
        (
            RepositoryArtifactKind.MUTATION_PLAN,
            RepositoryPersistedLifecycleState.PLAN_AWAITING_AUTHORIZATION,
            RepositoryRecordCompleteness.PARTIAL,
            "planning_authorization",
        ),
        (
            RepositoryArtifactKind.AUTHORIZATION_ASSESSMENT,
            RepositoryPersistedLifecycleState.PLAN_AWAITING_AUTHORIZATION,
            RepositoryRecordCompleteness.COMPLETE,
            "planning_authorization",
        ),
        (
            RepositoryArtifactKind.RESTORE_POINT_VERIFICATION,
            RepositoryPersistedLifecycleState.NONE,
            RepositoryRecordCompleteness.COMPLETE,
            "planning_authorization",
        ),
        (
            RepositoryArtifactKind.MUTATION_JOURNAL,
            RepositoryPersistedLifecycleState.APPLICATION_PARTIAL,
            RepositoryRecordCompleteness.PARTIAL,
            "mutation_lifecycle",
        ),
        (
            RepositoryArtifactKind.REPOSITORY_VERIFICATION,
            RepositoryPersistedLifecycleState.VERIFICATION_DIVERGENT,
            RepositoryRecordCompleteness.PARTIAL,
            "recovery_evidence",
        ),
        (
            RepositoryArtifactKind.RECOVERY_JOURNAL,
            RepositoryPersistedLifecycleState.RECOVERY_PARTIAL,
            RepositoryRecordCompleteness.PARTIAL,
            "recovery_evidence",
        ),
        (
            RepositoryArtifactKind.RECOVERY_RESULT,
            RepositoryPersistedLifecycleState.ROLLBACK_FAILED,
            RepositoryRecordCompleteness.COMPLETE,
            "recovery_evidence",
        ),
    ),
)
def test_crash_restart_preserves_each_checkpoint_without_invented_transition(
    real_repository: Path,
    tmp_path: Path,
    kind,
    state,
    completeness,
    store_name: str,
) -> None:
    selected = config(real_repository, tmp_path)
    runtime = RepositoryRuntimeBuilder().build(selected)
    responsibility = {
        "observation_snapshots": RepositoryStoreResponsibility.OBSERVATION_SNAPSHOT,
        "planning_authorization": RepositoryStoreResponsibility.PLANNING_AUTHORIZATION,
        "mutation_lifecycle": RepositoryStoreResponsibility.MUTATION_LIFECYCLE,
        "recovery_evidence": RepositoryStoreResponsibility.RECOVERY_EVIDENCE,
    }[store_name]
    record = draft(
        responsibility,
        kind,
        f"checkpoint:{kind.value}",
        state=state,
        completeness=completeness,
    )
    store = getattr(runtime.persistence, store_name)
    persisted = store.append(record).record
    runtime.close()

    restarted = RepositoryRuntimeBuilder().build(selected)
    replay = getattr(restarted.persistence, store_name).restart_state(record.stream_identity)
    assert replay.records[0].semantic_fingerprint == persisted.semantic_fingerprint
    assert replay.lifecycle_states == (state,)
    assert replay.records[0].completeness is completeness
    restarted.close()


def test_verification_divergence_does_not_start_recovery_and_recovery_failures_stay_explicit(
    real_repository: Path, tmp_path: Path
) -> None:
    runtime = RepositoryRuntimeBuilder().build(config(real_repository, tmp_path))
    base, target, plan, journal, restore, policy = verification_setup()
    verification = runtime.verification.verify(
        verification_request(base, target, plan, journal, restore, base, policy),
        policy,
        base,
        target,
        plan,
        journal,
        restore,
        base,
    )
    assert verification.outcome is RepositoryVerificationOutcome.NOT_APPLIED
    assert verification.reconciliation.state is RepositoryReconciliationState.ROLLBACK_CANDIDATE

    recovery_base, request, _, planned = recovery_context()
    assert planned.plan is not None and planned.journal is None
    partial = runtime.recovery.recover(
        request,
        planned.plan,
        recovery_base,
        RecoveryPreconditions(),
        RecoverySteps(RepositoryRecoveryStepState.PARTIAL),
        RecoveryObservations(),
        RecoveryInterruption(),
        RecoveryVerification(),
    )
    assert partial.state is RepositoryRecoveryState.PARTIALLY_RECOVERED
    interference = runtime.recovery.recover(
        request,
        planned.plan,
        recovery_base,
        RecoveryPreconditions(),
        RecoverySteps(),
        RecoveryObservations(interference=True),
        RecoveryInterruption(),
        RecoveryVerification(),
    )
    assert interference.state is RepositoryRecoveryState.MANUAL_INTERVENTION
    rollback_failed = runtime.recovery.recover(
        request,
        planned.plan,
        recovery_base,
        RecoveryPreconditions(RepositoryRecoveryPreconditionState.MISMATCH),
        RecoverySteps(),
        RecoveryObservations(),
        RecoveryInterruption(),
        RecoveryVerification(),
    )
    assert rollback_failed.state is RepositoryRecoveryState.ROLLBACK_FAILED
    runtime.close()


def test_real_boundaries_and_capabilities_remain_fail_closed(
    real_repository: Path, tmp_path: Path
) -> None:
    nested = real_repository / "nested"
    nested.mkdir()
    git(nested, "init", "-b", "nested-main")
    (nested / "inside.txt").write_bytes(b"nested")
    untracked = real_repository / "untracked.txt"
    untracked.write_bytes(b"preserve")
    runtime = RepositoryRuntimeBuilder().build(config(real_repository, tmp_path))
    health = runtime.health()
    assert RepositoryAdapterFeature.MUTATION in health.degraded_features
    assert RepositoryAdapterFeature.STAGING in health.unsupported_features
    assert RepositoryAdapterFeature.COMMIT in health.unsupported_features
    assert RepositoryAdapterFeature.PUSH in health.unsupported_features
    assert not hasattr(runtime, "stage") and not hasattr(runtime, "commit")
    assert not hasattr(runtime, "push") and not hasattr(runtime, "remote")
    assert untracked.read_bytes() == b"preserve"
    runtime.close()


def test_real_submodule_boundary_is_observed_and_not_traversed(
    real_repository: Path, tmp_path: Path
) -> None:
    child = tmp_path / "child"
    child.mkdir()
    git(child, "init", "-b", "main")
    git(child, "config", "user.name", "Submodule Test")
    git(child, "config", "user.email", "submodule@example.invalid")
    (child / "child.txt").write_bytes(b"child")
    git(child, "add", "child.txt")
    git(child, "commit", "-m", "child")
    subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "-C",
            str(real_repository),
            "submodule",
            "add",
            str(child),
            "modules/child",
        ],
        check=True,
        capture_output=True,
    )
    git(real_repository, "commit", "-am", "submodule")
    selected = config(real_repository, tmp_path)
    runtime = RepositoryRuntimeBuilder().build(selected)
    request = RepositoryObservationRequest(
        selected.repository_id,
        selected.checkout_id,
        selected.worktree_id,
        selected.platform_profile,
    )
    facts = runtime.adapters.local.facts_for(request)
    submodule = next(item for item in facts.entries if item.path.value == "modules/child")
    assert submodule.classification.topology is RepositoryTopology.SUBMODULE
    with pytest.raises(RepositoryAdapterBoundaryViolation):
        runtime.adapters.local.fingerprint_facts_for(
            (
                RepositoryPath(
                    "modules/child/child.txt",
                    selected.platform_profile,
                    selected.checkout_id,
                    selected.worktree_id,
                ),
            )
        )
    runtime.close()


def test_real_sparse_checkout_reports_excluded_content_without_inventing_presence(
    real_repository: Path, tmp_path: Path
) -> None:
    (real_repository / "keep").mkdir()
    (real_repository / "omit").mkdir()
    (real_repository / "keep" / "a.txt").write_bytes(b"keep")
    (real_repository / "omit" / "b.txt").write_bytes(b"omit")
    git(real_repository, "add", "keep/a.txt", "omit/b.txt")
    git(real_repository, "commit", "-m", "sparse-base")
    git(real_repository, "sparse-checkout", "init", "--cone")
    git(real_repository, "sparse-checkout", "set", "keep")
    selected = config(real_repository, tmp_path)
    runtime = RepositoryRuntimeBuilder().build(selected)
    request = RepositoryObservationRequest(
        selected.repository_id,
        selected.checkout_id,
        selected.worktree_id,
        selected.platform_profile,
    )
    facts = runtime.adapters.local.facts_for(request)
    excluded = next(item for item in facts.entries if item.path.value == "omit/b.txt")
    assert excluded.classification.topology is RepositoryTopology.SPARSE_EXCLUDED
    assert not excluded.content_observed
    assert RepositoryAdapterFeature.SPARSE_CHECKOUT in runtime.health().degraded_features
    runtime.close()
