from __future__ import annotations

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Event
from typing import Callable

import pytest
from tests.test_skills_phase6_lifecycle import _fields as _lifecycle_fields
from tests.test_skills_phase7_installation import (
    _activate_request,
    _deactivate_request,
    _install_request,
    _terminate_request,
)
from tests.test_skills_phase10_bindings import (
    _governance_request,
    _intelligence_request,
)
from tests.test_skills_phase11_bindings import _request as _private_eval_request
from tests.test_skills_phase17_recovery import (
    NOW,
    coordinator,
    insert_full_state,
    publication_request,
    runtime_configuration,
)

import synapse.skills.recovery as recovery_api
from synapse.skills.application.commands import (
    ActivateSkillVersionCommand,
    ApplySkillLifecycleTransitionCommand,
    BindSkillGovernanceDecisionCommand,
    BindSkillIntelligenceFactCommand,
    BindSkillPrivateEvalResultCommand,
    DeactivateSkillVersionCommand,
    InstallSkillVersionCommand,
    PublishSkillVersionCommand,
    TerminateSkillInstallationCommand,
)
from synapse.skills.application.queries import (
    GetPublishedSkillVersionQuery,
    GetSkillGovernanceBindingsQuery,
    GetSkillInstallationProjectionQuery,
    GetSkillIntelligenceBindingsQuery,
    GetSkillLifecycleProjectionQuery,
    GetSkillPrivateEvalBindingsQuery,
)
from synapse.skills.composition import (
    SkillsCompatibilityMode,
    SkillsRuntimeComposition,
    build_skills_runtime,
)
from synapse.skills.persistence import (
    SkillSQLiteConfig,
    SkillSQLiteConnectionFactory,
    SQLiteSkillAssignmentStore,
    SQLiteSkillBindingStore,
    SQLiteSkillLeaseStore,
)
from synapse.skills.phase2_models import SkillPublicationScope, SkillSemanticReference
from synapse.skills.phase3_records import (
    SkillAssignmentRecord,
    SkillAssignmentTerminationReason,
    SkillAssignmentTerminationRecord,
    SkillEvaluationBindingRecord,
    SkillGovernanceBindingRecord,
    SkillLeaseRecord,
    SkillLeaseTerminationReason,
    SkillLeaseTerminationRecord,
)
from synapse.skills.phase3_values import (
    SkillStoreQueryLimit,
    SkillStoreRecordFingerprint,
    SkillStoreRecordId,
)
from synapse.skills.phase6_models import DeprecateSkillVersionRequest
from synapse.skills.phase7_models import SkillInstallationTerminationReason
from synapse.skills.recovery import (
    SkillsRecoveryArtifactInvalid,
    SkillsRecoveryAtomicReplaceFailed,
    SkillsRecoveryCompositionRebuildFailed,
    SkillsRecoveryConflict,
    SkillsRecoveryManualInterventionRequired,
    SkillsRecoveryPostRestoreFailed,
    SkillsRecoverySourceUnavailable,
    SkillsRecoverySourceUnhealthy,
    SkillsRecoveryStagingFailed,
    SkillsRestoreRequest,
)


def _prepare(
    family: str, runtime: SkillsRuntimeComposition, package_root: Path
) -> tuple[Callable[[], object], Callable[[], object], str]:
    request = publication_request(package_root)
    publication = runtime.gateway.publish(PublishSkillVersionCommand(request))
    identity = publication.identity
    record = runtime.gateway.get(GetPublishedSkillVersionQuery(identity)).record

    if family == "publication":
        return (
            lambda: runtime.gateway.publish(PublishSkillVersionCommand(request)),
            lambda: runtime.gateway.get(GetPublishedSkillVersionQuery(identity)),
            "publications",
        )
    if family == "lifecycle":
        lifecycle = replace(
            DeprecateSkillVersionRequest(**_lifecycle_fields(identity, 1, "recovery")),
            occurred_at=NOW + timedelta(minutes=1),
        )
        return (
            lambda: runtime.gateway.apply_lifecycle(
                ApplySkillLifecycleTransitionCommand(lifecycle)
            ),
            lambda: runtime.gateway.lifecycle(
                GetSkillLifecycleProjectionQuery(identity)
            ),
            "lifecycle_records",
        )

    install = replace(
        _install_request(record, request.snapshot),
        installed_at=NOW + timedelta(minutes=1),
    )
    runtime.gateway.install(InstallSkillVersionCommand(install))
    installation = runtime.gateway.installation(
        GetSkillInstallationProjectionQuery(identity)
    ).projection.installations[0]
    if family == "installation":
        return (
            lambda: runtime.gateway.install(InstallSkillVersionCommand(install)),
            lambda: runtime.gateway.installation(
                GetSkillInstallationProjectionQuery(identity)
            ),
            "installation_records",
        )
    if family == "activation":
        activation = replace(
            _activate_request(identity, installation.record_id),
            occurred_at=NOW + timedelta(minutes=2),
        )
        return (
            lambda: runtime.gateway.activate(ActivateSkillVersionCommand(activation)),
            lambda: runtime.gateway.lifecycle(
                GetSkillLifecycleProjectionQuery(identity)
            ),
            "lifecycle_records",
        )
    if family == "installation_termination":
        termination = replace(
            _terminate_request(
                identity,
                installation.record_id,
                SkillInstallationTerminationReason.DETACHED,
            ),
            occurred_at=NOW + timedelta(minutes=2),
        )
        return (
            lambda: runtime.gateway.terminate(
                TerminateSkillInstallationCommand(termination)
            ),
            lambda: runtime.gateway.installation(
                GetSkillInstallationProjectionQuery(identity)
            ),
            "installation_terminations",
        )
    if family == "governance":
        binding = replace(
            _governance_request(identity), bound_at=NOW + timedelta(minutes=2)
        )
        return (
            lambda: runtime.gateway.bind_governance(
                BindSkillGovernanceDecisionCommand(binding)
            ),
            lambda: runtime.gateway.governance(
                GetSkillGovernanceBindingsQuery(identity)
            ),
            "governance_bindings",
        )
    if family == "intelligence":
        binding = replace(
            _intelligence_request(identity),
            observed_at=NOW + timedelta(minutes=1),
            bound_at=NOW + timedelta(minutes=2),
        )
        return (
            lambda: runtime.gateway.bind_intelligence(
                BindSkillIntelligenceFactCommand(binding)
            ),
            lambda: runtime.gateway.intelligence(
                GetSkillIntelligenceBindingsQuery(identity)
            ),
            "intelligence_bindings",
        )
    binding = replace(
        _private_eval_request(identity),
        evaluated_at=NOW + timedelta(minutes=1),
        bound_at=NOW + timedelta(minutes=2),
    )
    return (
        lambda: runtime.gateway.bind_private_eval(
            BindSkillPrivateEvalResultCommand(binding)
        ),
        lambda: runtime.gateway.private_evals(
            GetSkillPrivateEvalBindingsQuery(identity)
        ),
        "private_eval_bindings",
    )


@pytest.mark.parametrize(
    "family",
    (
        "publication",
        "lifecycle",
        "installation",
        "installation_termination",
        "activation",
        "governance",
        "intelligence",
        "private_eval",
    ),
)
def test_lost_response_replays_before_and_after_restore_through_public_api(
    tmp_path: Path, family: str
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    runtime = build_skills_runtime(config)
    command, query, table = _prepare(family, runtime, tmp_path / "package")
    created = command()
    assert created.outcome.value in {"created", "replayed"}
    before = query()
    runtime.close()

    reopened = build_skills_runtime(config)
    retry, reopened_query, _ = _prepare(
        family, reopened, tmp_path / "package-retry"
    )
    replayed = retry()
    assert replayed.outcome.value == "replayed"
    assert reopened_query() == before
    reopened.close()

    service = coordinator(database, recovery)
    point = service.create_restore_point(reopened).restore_point
    insert_full_state(database, "99")
    changed = build_skills_runtime(config)
    changed.close()
    result = service.restore(SkillsRestoreRequest(point, config, changed))
    final_command, final_query, _ = _prepare(
        family, result.composition, tmp_path / "package-final"
    )
    final_replay = final_command()
    assert final_replay.outcome.value == "replayed"
    assert final_query() == before
    assert service.verify_restore_point(point).logical_fingerprint == point.backup_fingerprint
    assert dict(point.record_counts)[table] == 1
    result.close()


@pytest.mark.parametrize("family", ("publication", "lifecycle", "governance"))
def test_commit_uncertain_reconciles_by_query_then_retry_before_and_after_restore(
    tmp_path: Path, family: str
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    runtime = build_skills_runtime(config)
    command, query, _table = _prepare(family, runtime, tmp_path / "package")
    command()  # caller receives no commit flag or response
    expected = query()
    runtime.close()

    reopened = build_skills_runtime(config)
    retry, semantic_query, _ = _prepare(
        family, reopened, tmp_path / "package-reopen"
    )
    assert semantic_query() == expected
    assert retry().outcome.value == "replayed"
    reopened.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(reopened).restore_point
    insert_full_state(database, "97")
    changed = build_skills_runtime(config)
    changed.close()
    result = service.restore(SkillsRestoreRequest(point, config, changed))
    final_retry, final_query, _ = _prepare(
        family, result.composition, tmp_path / "package-final"
    )
    assert final_query() == expected
    assert final_retry().outcome.value == "replayed"
    result.close()


@pytest.mark.parametrize(
    "injection",
    (
        "open",
        "schema",
        "migration",
        "integrity",
        "foreign_keys",
        "logical",
        "physical",
        "rebuild",
        "health",
        "compatibility",
    ),
)
def test_each_post_replace_failure_rolls_back_verified_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, injection: str
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    if injection == "compatibility":
        config = replace(config, compatibility=SkillsCompatibilityMode.READ_ONLY)
    runtime = build_skills_runtime(config)
    runtime.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(runtime).restore_point
    changed = build_skills_runtime(config)
    changed.gateway.publish(
        PublishSkillVersionCommand(publication_request(tmp_path / "changed"))
    )
    changed.close()
    original_state = service._logical_snapshot(database)

    if injection in {
        "open",
        "schema",
        "migration",
        "integrity",
        "foreign_keys",
        "logical",
        "physical",
    }:
        method = f"_verify_target_{injection}"
        monkeypatch.setattr(
            service,
            method,
            lambda *_args: (_ for _ in ()).throw(
                SkillsRecoveryPostRestoreFailed()
            ),
        )
    elif injection in {"rebuild", "compatibility"}:
        monkeypatch.setattr(
            service,
            "_rebuild",
            lambda _request: (_ for _ in ()).throw(
                SkillsRecoveryCompositionRebuildFailed()
            ),
        )
    else:
        original_verify = SkillsRuntimeComposition.verify_integrity
        calls = 0

        def fail_first(
            composition: SkillsRuntimeComposition,
        ) -> object:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise SkillsRecoveryPostRestoreFailed()
            return original_verify(composition)

        monkeypatch.setattr(
            SkillsRuntimeComposition, "verify_integrity", fail_first
        )

    with pytest.raises(SkillsRecoveryPostRestoreFailed):
        service.restore(SkillsRestoreRequest(point, config, changed))
    assert service._logical_snapshot(database) == original_state


@pytest.mark.parametrize(
    "injection",
    (
        "copy",
        "replace",
        "open",
        "schema",
        "integrity",
        "foreign_keys",
        "logical",
        "rebuild",
        "health",
    ),
)
def test_each_rollback_failure_preserves_artifacts_and_requires_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, injection: str
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    runtime = build_skills_runtime(config)
    runtime.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(runtime).restore_point
    changed = build_skills_runtime(config)
    changed.gateway.publish(
        PublishSkillVersionCommand(publication_request(tmp_path / "changed"))
    )
    changed.close()
    monkeypatch.setattr(
        service,
        "_verify_target_logical",
        lambda *_args: (_ for _ in ()).throw(
            SkillsRecoveryPostRestoreFailed()
        ),
    )

    if injection == "copy":
        original_copy = service._copy_file

        def fail_copy(source: Path, target: Path) -> None:
            if source.name == ".skills-restore-rollback.sqlite3":
                raise SkillsRecoveryStagingFailed()
            original_copy(source, target)

        monkeypatch.setattr(service, "_copy_file", fail_copy)
    elif injection == "replace":
        original_replace = os.replace

        def fail_replace(source: Path, target: Path) -> None:
            if Path(source).name == ".skills-restore-return.sqlite3":
                raise OSError("injected")
            original_replace(source, target)

        monkeypatch.setattr(os, "replace", fail_replace)
    elif injection in {
        "open",
        "schema",
        "integrity",
        "foreign_keys",
        "logical",
    }:
        method = f"_verify_rollback_{injection}"
        original_method = getattr(service, method)
        calls = 0

        def fail_after_capture(*args: object) -> object:
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise SkillsRecoveryPostRestoreFailed()
            return original_method(*args)

        monkeypatch.setattr(service, method, fail_after_capture)
    elif injection == "rebuild":
        monkeypatch.setattr(
            service,
            "_rebuild_rollback",
            lambda _request: (_ for _ in ()).throw(
                SkillsRecoveryCompositionRebuildFailed()
            ),
        )
    else:
        monkeypatch.setattr(
            SkillsRuntimeComposition,
            "verify_integrity",
            lambda _self: (_ for _ in ()).throw(
                SkillsRecoveryPostRestoreFailed()
            ),
        )

    with pytest.raises(SkillsRecoveryManualInterventionRequired):
        service.restore(SkillsRestoreRequest(point, config, changed))
    assert (database.parent / ".skills-restore-rollback.sqlite3").exists()


def test_restore_result_context_manager_exception_and_double_close(
    tmp_path: Path,
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    closed = build_skills_runtime(config)
    closed.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(closed).restore_point
    result = service.restore(SkillsRestoreRequest(point, config, closed))
    with pytest.raises(RuntimeError):
        with result as composition:
            assert composition.state.value == "ready"
            raise RuntimeError("caller failure")
    assert result.composition.state.value == "closed"
    result.close()


@pytest.mark.skipif(not hasattr(os, "link"), reason="hardlinks unsupported")
def test_hardlinked_backup_and_target_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    closed = build_skills_runtime(config)
    closed.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(closed).restore_point
    backup = service._backup_path(point.backup_reference)
    alias = recovery / "backup-alias.sqlite3"
    os.link(backup, alias)
    with pytest.raises(SkillsRecoveryArtifactInvalid):
        service.verify_restore_point(point)
    alias.unlink()
    target_alias = tmp_path / "target-alias.sqlite3"
    os.link(database, target_alias)
    with pytest.raises(SkillsRecoverySourceUnavailable):
        service.restore(SkillsRestoreRequest(point, config, closed))


def test_symlinked_published_backup_fails_closed_when_supported(
    tmp_path: Path,
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    closed = build_skills_runtime(config)
    closed.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(closed).restore_point
    backup = service._backup_path(point.backup_reference)
    original = recovery / "original.sqlite3"
    backup.replace(original)
    try:
        backup.symlink_to(original)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(SkillsRecoveryArtifactInvalid):
        service.verify_restore_point(point)


def test_restore_staging_is_constructed_beside_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "target" / "skills.sqlite3"
    database.parent.mkdir()
    recovery = tmp_path / "other-volume-candidate"
    recovery.mkdir()
    config = runtime_configuration(database)
    closed = build_skills_runtime(config)
    closed.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(closed).restore_point
    destinations: list[Path] = []
    original_copy = service._copy_file

    def observe(source: Path, target: Path) -> None:
        destinations.append(target)
        original_copy(source, target)

    monkeypatch.setattr(service, "_copy_file", observe)
    result = service.restore(SkillsRestoreRequest(point, config, closed))
    assert destinations[0].parent == database.parent
    result.close()


def test_two_creates_same_state_have_one_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    closed = build_skills_runtime(runtime_configuration(database))
    closed.close()
    service = coordinator(database, recovery)
    entered = Event()
    release = Event()
    original_backup = service._backup
    first = True

    def blocked_backup(source: Path, target: Path) -> None:
        nonlocal first
        if first:
            first = False
            entered.set()
            assert release.wait(5)
        original_backup(source, target)

    monkeypatch.setattr(service, "_backup", blocked_backup)
    with ThreadPoolExecutor(max_workers=2) as executor:
        winner = executor.submit(service.create_restore_point, closed)
        assert entered.wait(5)
        loser = executor.submit(service.create_restore_point, closed)
        with pytest.raises(SkillsRecoveryConflict):
            loser.result()
        release.set()
        assert winner.result().outcome.value == "created"


def test_two_restores_same_target_have_one_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    first_closed = build_skills_runtime(config)
    first_closed.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(first_closed).restore_point
    second_closed = build_skills_runtime(config)
    second_closed.close()
    entered = Event()
    release = Event()
    original_copy = service._copy_file
    first = True

    def blocked_copy(source: Path, target: Path) -> None:
        nonlocal first
        if first:
            first = False
            entered.set()
            assert release.wait(5)
        original_copy(source, target)

    monkeypatch.setattr(service, "_copy_file", blocked_copy)
    with ThreadPoolExecutor(max_workers=2) as executor:
        winner = executor.submit(
            service.restore,
            SkillsRestoreRequest(point, config, first_closed),
        )
        assert entered.wait(5)
        loser = executor.submit(
            service.restore,
            SkillsRestoreRequest(point, config, second_closed),
        )
        with pytest.raises(SkillsRecoveryConflict):
            loser.result()
        release.set()
        result = winner.result()
    result.close()
    assert service.verify_restore_point(point).logical_fingerprint == point.backup_fingerprint


def test_independent_targets_recover_independently(tmp_path: Path) -> None:
    def recover(name: str) -> str:
        root = tmp_path / name
        root.mkdir()
        database = root / "skills.sqlite3"
        recovery = root / "recovery"
        recovery.mkdir()
        config = runtime_configuration(database)
        closed = build_skills_runtime(config)
        closed.close()
        service = coordinator(database, recovery)
        point = service.create_restore_point(closed).restore_point
        result = service.restore(SkillsRestoreRequest(point, config, closed))
        result.close()
        return point.restore_point_id.value

    with ThreadPoolExecutor(max_workers=2) as executor:
        identities = tuple(executor.map(recover, ("one", "two")))
    assert identities[0] == identities[1]


def test_full_state_is_equal_after_restore_through_public_gateways_and_ports(
    tmp_path: Path,
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    runtime = build_skills_runtime(config)
    request = publication_request(tmp_path / "package")
    publication = runtime.gateway.publish(PublishSkillVersionCommand(request))
    identity = publication.identity
    published_record = runtime.gateway.get(
        GetPublishedSkillVersionQuery(identity)
    ).record
    install_request = replace(
        _install_request(published_record, request.snapshot),
        installed_at=NOW + timedelta(minutes=1),
    )
    runtime.gateway.install(InstallSkillVersionCommand(install_request))
    installation = runtime.gateway.installation(
        GetSkillInstallationProjectionQuery(identity)
    ).projection.installations[0]
    activation = replace(
        _activate_request(identity, installation.record_id),
        occurred_at=NOW + timedelta(minutes=2),
    )
    runtime.gateway.activate(ActivateSkillVersionCommand(activation))
    deactivation = replace(
        _deactivate_request(identity),
        occurred_at=NOW + timedelta(minutes=3),
    )
    runtime.gateway.deactivate(DeactivateSkillVersionCommand(deactivation))
    termination = replace(
        _terminate_request(
            identity,
            installation.record_id,
            SkillInstallationTerminationReason.DETACHED,
        ),
        occurred_at=NOW + timedelta(minutes=4),
    )
    runtime.gateway.terminate(TerminateSkillInstallationCommand(termination))
    governance = replace(
        _governance_request(identity), bound_at=NOW + timedelta(minutes=4)
    )
    intelligence = replace(
        _intelligence_request(identity),
        observed_at=NOW + timedelta(minutes=3),
        bound_at=NOW + timedelta(minutes=4),
    )
    private_eval = replace(
        _private_eval_request(identity),
        evaluated_at=NOW + timedelta(minutes=3),
        bound_at=NOW + timedelta(minutes=4),
    )
    runtime.gateway.bind_governance(
        BindSkillGovernanceDecisionCommand(governance)
    )
    runtime.gateway.bind_intelligence(
        BindSkillIntelligenceFactCommand(intelligence)
    )
    runtime.gateway.bind_private_eval(
        BindSkillPrivateEvalResultCommand(private_eval)
    )

    factory = SkillSQLiteConnectionFactory(SkillSQLiteConfig(database))
    subject = SkillSemanticReference("subject:recovery")
    assignment = SkillAssignmentRecord(
        SkillStoreRecordId("assignment:recovery"),
        identity,
        subject,
        SkillPublicationScope.PROJECT,
        NOW + timedelta(minutes=5),
        SkillSemanticReference("actor:operator"),
        SkillSemanticReference("reason:assigned"),
    )
    assignment_end = SkillAssignmentTerminationRecord(
        SkillStoreRecordId("assignment-end:recovery"),
        assignment.record_id,
        identity,
        NOW + timedelta(minutes=9),
        SkillSemanticReference("actor:operator"),
        SkillAssignmentTerminationReason.REVOKED,
    )
    assignments = SQLiteSkillAssignmentStore(factory)
    assignments.append_assignment(assignment)
    assignments.append_termination(assignment_end)
    lease = SkillLeaseRecord(
        SkillStoreRecordId("lease:recovery"),
        assignment.record_id,
        identity,
        SkillSemanticReference("agent:recovery"),
        SkillSemanticReference("task:recovery"),
        NOW + timedelta(minutes=6),
        NOW + timedelta(hours=1),
        SkillSemanticReference("actor:operator"),
    )
    lease_end = SkillLeaseTerminationRecord(
        SkillStoreRecordId("lease-end:recovery"),
        lease.record_id,
        identity,
        NOW + timedelta(minutes=8),
        SkillSemanticReference("actor:operator"),
        SkillLeaseTerminationReason.TERMINATED,
    )
    leases = SQLiteSkillLeaseStore(factory)
    leases.append_lease(lease)
    leases.append_termination(lease_end)
    legacy_governance = SkillGovernanceBindingRecord(
        SkillStoreRecordId("governance-binding:recovery"),
        identity,
        SkillSemanticReference("governance:recovery"),
        SkillStoreRecordFingerprint("a" * 64),
        NOW + timedelta(minutes=6),
        SkillSemanticReference("actor:operator"),
    )
    legacy_evaluation = SkillEvaluationBindingRecord(
        SkillStoreRecordId("evaluation-binding:recovery"),
        identity,
        SkillSemanticReference("evaluation:recovery"),
        SkillStoreRecordFingerprint("b" * 64),
        NOW + timedelta(minutes=7),
        SkillSemanticReference("actor:operator"),
    )
    legacy = SQLiteSkillBindingStore(factory)
    legacy.append_governance(legacy_governance)
    legacy.append_evaluation(legacy_evaluation)
    limit = SkillStoreQueryLimit(100)

    def public_state(composition: SkillsRuntimeComposition) -> tuple[object, ...]:
        reopened_factory = SkillSQLiteConnectionFactory(SkillSQLiteConfig(database))
        return (
            composition.gateway.get(GetPublishedSkillVersionQuery(identity)),
            composition.gateway.lifecycle(GetSkillLifecycleProjectionQuery(identity)),
            composition.gateway.installation(
                GetSkillInstallationProjectionQuery(identity)
            ),
            composition.gateway.governance(
                GetSkillGovernanceBindingsQuery(identity)
            ),
            composition.gateway.intelligence(
                GetSkillIntelligenceBindingsQuery(identity)
            ),
            composition.gateway.private_evals(
                GetSkillPrivateEvalBindingsQuery(identity)
            ),
            SQLiteSkillAssignmentStore(reopened_factory).history_for_subject(
                subject, limit
            ),
            SQLiteSkillLeaseStore(reopened_factory).history_for_task(
                lease.task_ref, limit
            ),
            SQLiteSkillBindingStore(reopened_factory).list_governance_for_version(
                identity, limit
            ),
            SQLiteSkillBindingStore(reopened_factory).list_evaluations_for_version(
                identity, limit
            ),
        )

    before = public_state(runtime)
    runtime.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(runtime).restore_point
    assert all(count == 1 or family == "lifecycle_records" for family, count in point.record_counts)
    insert_full_state(database, "98")
    changed = build_skills_runtime(config)
    changed.close()
    result = service.restore(SkillsRestoreRequest(point, config, changed))
    assert public_state(result.composition) == before
    assert result.target_fingerprint == point.backup_fingerprint
    result.close()


def test_public_surface_contains_only_final_operational_contracts() -> None:
    assert len(recovery_api.__all__) == 24
    assert "SkillsPhysicalFingerprint" not in recovery_api.__all__
    assert "SkillsRecoveryClock" not in recovery_api.__all__
    assert "SkillsRecoveryRestorePointUnsupported" not in recovery_api.__all__
    assert not {
        "SkillsRecordFamilyCount",
        "SkillsRecoveryAction",
        "SkillsRecoveryEvidence",
        "SkillsRecoveryVerificationStatus",
    } & set(recovery_api.__all__)


def test_manifest_publish_failure_removes_only_owned_unpublished_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    closed = build_skills_runtime(runtime_configuration(database))
    closed.close()
    service = coordinator(database, recovery)
    monkeypatch.setattr(
        service,
        "_publish_manifest",
        lambda *_args: (_ for _ in ()).throw(OSError("injected")),
    )
    with pytest.raises(SkillsRecoveryStagingFailed):
        service.create_restore_point(closed)
    assert not tuple(recovery.glob("*.sqlite3"))
    assert not (recovery / ".skills-manifest-staging.json").exists()


def test_logical_state_can_match_while_physical_layout_differs(
    tmp_path: Path,
) -> None:
    database = tmp_path / "skills.sqlite3"
    compacted = tmp_path / "compacted.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    closed = build_skills_runtime(runtime_configuration(database))
    closed.close()
    insert_full_state(database, "96")
    service = coordinator(database, recovery)
    service._backup(database, compacted)
    with sqlite3.connect(compacted) as connection:
        connection.execute("PRAGMA page_size = 8192")
        connection.execute("VACUUM")
    assert service._logical_snapshot(database) == service._logical_snapshot(compacted)
    assert service._physical(database) != service._physical(compacted)


def test_atomic_replace_failure_preserves_target_and_cleans_private_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    closed = build_skills_runtime(config)
    closed.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(closed).restore_point
    original = service._logical_snapshot(database)
    real_replace = os.replace

    def fail_target_replace(source: Path, target: Path) -> None:
        if (
            Path(source).name == ".skills-restore-staging.sqlite3"
            and Path(target) == database
        ):
            raise OSError("injected")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_target_replace)
    with pytest.raises(SkillsRecoveryAtomicReplaceFailed):
        service.restore(SkillsRestoreRequest(point, config, closed))
    assert service._logical_snapshot(database) == original
    assert not (database.parent / ".skills-restore-staging.sqlite3").exists()
    assert not (database.parent / ".skills-restore-rollback.sqlite3").exists()


def test_unhealthy_source_has_specific_safe_error(tmp_path: Path) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    closed = build_skills_runtime(runtime_configuration(database))
    closed.close()
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER publications_no_update")
    service = coordinator(database, recovery)
    with pytest.raises(SkillsRecoverySourceUnhealthy) as caught:
        service.create_restore_point(closed)
    assert str(tmp_path) not in str(caught.value)
    assert "SELECT " not in str(caught.value)


def test_verify_remains_read_only_while_restore_lock_is_held_and_create_loses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    closed = build_skills_runtime(config)
    closed.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(closed).restore_point
    entered = Event()
    release = Event()
    original_copy = service._copy_file

    def blocked_copy(source: Path, target: Path) -> None:
        entered.set()
        assert release.wait(5)
        original_copy(source, target)

    monkeypatch.setattr(service, "_copy_file", blocked_copy)
    with ThreadPoolExecutor(max_workers=2) as executor:
        restoring = executor.submit(
            service.restore, SkillsRestoreRequest(point, config, closed)
        )
        assert entered.wait(5)
        assert (
            service.verify_restore_point(point).logical_fingerprint
            == point.backup_fingerprint
        )
        with pytest.raises(SkillsRecoveryConflict):
            service.create_restore_point(closed)
        release.set()
        result = restoring.result()
    result.close()


def test_verify_remains_read_only_while_equivalent_create_is_in_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    closed = build_skills_runtime(runtime_configuration(database))
    closed.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(closed).restore_point
    entered = Event()
    release = Event()
    original_backup = service._backup

    def blocked_backup(source: Path, target: Path) -> None:
        entered.set()
        assert release.wait(5)
        original_backup(source, target)

    monkeypatch.setattr(service, "_backup", blocked_backup)
    with ThreadPoolExecutor(max_workers=2) as executor:
        creating = executor.submit(service.create_restore_point, closed)
        assert entered.wait(5)
        assert service.verify_restore_point(point).restore_point_id == point.restore_point_id
        release.set()
        assert creating.result().outcome.value == "reused_verified"


@pytest.mark.parametrize(
    "artifact",
    (".skills-restore-staging.sqlite3", ".skills-restore-rollback.sqlite3"),
)
def test_preexisting_restore_private_artifact_is_preserved(
    tmp_path: Path, artifact: str
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    closed = build_skills_runtime(config)
    closed.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(closed).restore_point
    collision = database.parent / artifact
    collision.write_bytes(b"operator evidence")
    with pytest.raises(SkillsRecoveryConflict):
        service.restore(SkillsRestoreRequest(point, config, closed))
    assert collision.read_bytes() == b"operator evidence"


def test_discarding_result_does_not_auto_close_transferred_composition(
    tmp_path: Path,
) -> None:
    database = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(database)
    closed = build_skills_runtime(config)
    closed.close()
    service = coordinator(database, recovery)
    point = service.create_restore_point(closed).restore_point
    result = service.restore(SkillsRestoreRequest(point, config, closed))
    transferred = result.composition
    del result
    assert transferred.state.value == "ready"
    transferred.close()
