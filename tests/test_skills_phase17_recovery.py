from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from synapse.skills.application.commands import PublishSkillVersionCommand
from synapse.skills.application.queries import GetPublishedSkillVersionQuery
from synapse.skills.composition import (
    SkillsCompatibilityMode,
    SkillsIntegrityPolicy,
    SkillsMigrationPolicy,
    SkillsRuntimeConfiguration,
    SkillsRuntimeState,
    build_skills_runtime,
)
from synapse.skills.persistence import SkillSQLiteConfig
from synapse.skills.phase2_models import SkillSemanticReference
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase4_verification import SkillPackageVerifier
from synapse.skills.phase5_models import PublishVerifiedSkillVersionRequest
from synapse.skills.recovery import (
    SkillsLogicalFingerprint,
    SkillsRecoveryArtifactInvalid,
    SkillsRecoveryArtifactMissing,
    SkillsRecoveryCompositionRebuildFailed,
    SkillsRecoveryConfiguration,
    SkillsRecoveryConflict,
    SkillsRecoveryCoordinator,
    SkillsRecoveryInvalidConfiguration,
    SkillsRecoveryManualInterventionRequired,
    SkillsRecoveryPostRestoreFailed,
    SkillsRecoverySourceOpen,
    SkillsRestorePointFormatVersion,
    SkillsRestoreRequest,
)

NOW = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)


def runtime_configuration(path: Path) -> SkillsRuntimeConfiguration:
    return SkillsRuntimeConfiguration(
        SkillSQLiteConfig(path),
        SkillsMigrationPolicy.MIGRATE_IF_NEEDED,
        SkillsIntegrityPolicy.FULL,
        SkillsCompatibilityMode.DISABLED,
        SkillStoreQueryLimit(100),
    )


def coordinator(path: Path, recovery: Path) -> SkillsRecoveryCoordinator:
    return SkillsRecoveryCoordinator(
        SkillsRecoveryConfiguration(
            SkillSQLiteConfig(path),
            recovery,
            10_000_000,
        ),
        lambda: NOW,
    )


def publication_request(root: Path) -> PublishVerifiedSkillVersionRequest:
    content = b"# Recovery"
    digest = hashlib.sha256(content).hexdigest()
    root.mkdir()
    (root / "SKILL.md").write_bytes(content)
    (root / "manifest.yaml").write_text(
        f"""format_version: 1
skill_id: recovery-skill
version: 1.0.0
display_name: Recovery skill
summary: Recovery integration.
description: Verified recovery integration fixture.
provenance:
  publisher_ref: publisher:test
scopes:
  - project
content:
  - logical_path: SKILL.md
    fingerprint: {digest}
    kind: instructions
    media_type: text/markdown
    size_bytes: {len(content)}
""",
        encoding="utf-8",
    )
    return PublishVerifiedSkillVersionRequest(
        snapshot=SkillPackageVerifier().verify(root),
        actor_ref=SkillSemanticReference("actor:test"),
        publication_ref=SkillSemanticReference("publication:test"),
        idempotency_ref=SkillSemanticReference("idempotency:test"),
        published_at=NOW,
    )


FAMILIES = (
    "publications",
    "lifecycle_records",
    "installation_records",
    "installation_terminations",
    "assignments",
    "assignment_terminations",
    "leases",
    "lease_terminations",
    "legacy_governance_bindings",
    "legacy_evaluation_bindings",
    "governance_bindings",
    "intelligence_bindings",
    "private_eval_bindings",
)


def insert_full_state(path: Path, suffix: str) -> None:
    identity = f"skill:fixture@1.0.{suffix}"
    values = {
        "exact_identity": identity,
        "skill_id": f"fixture-{suffix}",
        "version": f"1.0.{suffix}",
        "occurred_at": NOW.isoformat(),
        "record_kind": "fixture",
        "parent_installation_id": None,
        "installation_id": f"installation-{suffix}",
        "assignment_id": f"assignment-{suffix}",
        "lease_id": f"lease-{suffix}",
        "subject_ref": f"subject:{suffix}",
        "agent_ref": f"agent:{suffix}",
        "task_ref": f"task:{suffix}",
        "binding_ref": f"binding:{suffix}",
    }
    record_ids = {
        "lifecycle_records": f"lifecycle-{suffix}",
        "installation_records": f"installation-{suffix}",
        "installation_terminations": f"installation-termination-{suffix}",
        "assignments": f"assignment-{suffix}",
        "assignment_terminations": f"assignment-termination-{suffix}",
        "leases": f"lease-{suffix}",
        "lease_terminations": f"lease-termination-{suffix}",
        "legacy_governance_bindings": f"legacy-governance-{suffix}",
        "legacy_evaluation_bindings": f"legacy-evaluation-{suffix}",
    }
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for table in FAMILIES:
            columns = [
                str(row[1])
                for row in connection.execute(f"PRAGMA table_info({table})")
            ]
            row_values: list[object] = []
            for column in columns:
                if column == "payload":
                    row_values.append(
                        json.dumps(
                            {"family": table, "suffix": suffix},
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
                elif column in values:
                    row_values.append(values[column])
                elif column == "record_id":
                    row_values.append(record_ids[table])
                elif column == "occurrence_ref":
                    row_values.append(f"occurrence:{table}:{suffix}")
                else:
                    raise AssertionError(column)
            placeholders = ",".join("?" for _ in columns)
            connection.execute(
                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                row_values,
            )
        connection.commit()


def test_restore_point_is_verified_immutable_and_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    runtime = build_skills_runtime(runtime_configuration(path))
    runtime.close()
    service = coordinator(path, recovery)
    first_result = service.create_restore_point(runtime)
    first = first_result.restore_point
    second_result = service.create_restore_point(runtime)
    second = second_result.restore_point
    assert first.restore_point_id == second.restore_point_id
    assert first.backup_reference == second.backup_reference
    assert service.verify_restore_point(first).logical_fingerprint == first.backup_fingerprint
    with pytest.raises((AttributeError, TypeError)):
        first.database_size = 0  # type: ignore[misc]


def test_backup_and_restore_revert_entire_database_without_record_repair(
    tmp_path: Path,
) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(path)
    request = publication_request(tmp_path / "package")
    state_a = build_skills_runtime(config)
    state_a.close()
    service = coordinator(path, recovery)
    restore_point = service.create_restore_point(state_a).restore_point

    state_b = build_skills_runtime(config)
    created = state_b.gateway.publish(PublishSkillVersionCommand(request))
    state_b.close()
    result = service.restore(SkillsRestoreRequest(restore_point, config, state_b))
    with pytest.raises(Exception):
        result.composition.gateway.get(GetPublishedSkillVersionQuery(created.identity))
    replay_after_rollback = result.composition.gateway.publish(
        PublishSkillVersionCommand(request)
    )
    assert replay_after_rollback.outcome.value == "created"


def test_corruption_is_detected_then_explicit_restore_recovers(tmp_path: Path) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(path)
    runtime = build_skills_runtime(config)
    runtime.close()
    service = coordinator(path, recovery)
    restore_point = service.create_restore_point(runtime).restore_point
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("DROP TRIGGER publications_no_update")
    result = service.restore(SkillsRestoreRequest(restore_point, config, runtime))
    assert result.composition.state is SkillsRuntimeState.READY
    assert result.composition.verify_integrity().database_reachable


def test_restore_rejects_open_composition_without_closing_it(tmp_path: Path) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    runtime = build_skills_runtime(runtime_configuration(path))
    service = coordinator(path, recovery)
    with pytest.raises(SkillsRecoverySourceOpen):
        service.create_restore_point(runtime)
    assert runtime.state is SkillsRuntimeState.READY


def test_manifest_fingerprint_tampering_does_not_mutate_target(tmp_path: Path) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(path)
    runtime = build_skills_runtime(config)
    runtime.close()
    service = coordinator(path, recovery)
    valid = service.create_restore_point(runtime).restore_point
    tampered = replace(
        valid,
        backup_fingerprint=SkillsLogicalFingerprint("f" * 64),
    )
    with pytest.raises(SkillsRecoveryArtifactInvalid):
        service.restore(SkillsRestoreRequest(tampered, config, runtime))
    assert build_skills_runtime(config).state is SkillsRuntimeState.READY


def test_backup_substitution_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    runtime = build_skills_runtime(runtime_configuration(path))
    runtime.close()
    service = coordinator(path, recovery)
    point = service.create_restore_point(runtime).restore_point
    backup = recovery / f"{point.backup_reference.value.removeprefix('backup:')}.sqlite3"
    backup.write_bytes(b"not sqlite")
    with pytest.raises(SkillsRecoveryArtifactInvalid):
        service.verify_restore_point(point)


def test_failure_after_replace_rolls_back_original_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(path)
    base = build_skills_runtime(config)
    base.close()
    service = coordinator(path, recovery)
    point = service.create_restore_point(base).restore_point
    changed = build_skills_runtime(config)
    request = publication_request(tmp_path / "changed-package")
    created = changed.gateway.publish(PublishSkillVersionCommand(request))
    changed.close()

    def fail(_request: object) -> object:
        raise SkillsRecoveryCompositionRebuildFailed()

    monkeypatch.setattr(service, "_rebuild", fail)
    with pytest.raises(SkillsRecoveryCompositionRebuildFailed):
        service.restore(SkillsRestoreRequest(point, config, changed))
    rebuilt = build_skills_runtime(config)
    assert rebuilt.gateway.get(GetPublishedSkillVersionQuery(created.identity))


def test_invalid_recovery_directory_and_bool_limit_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "skills.sqlite3"
    with pytest.raises(SkillsRecoveryInvalidConfiguration):
        SkillsRecoveryConfiguration(SkillSQLiteConfig(path), Path("relative"), 1)
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    with pytest.raises(SkillsRecoveryInvalidConfiguration):
        SkillsRecoveryConfiguration(SkillSQLiteConfig(path), recovery, True)
    valid = SkillsRecoveryConfiguration(SkillSQLiteConfig(path), recovery, 10)
    assert str(tmp_path) not in repr(valid)


def test_lost_publication_response_reopens_and_replays_once(tmp_path: Path) -> None:
    path = tmp_path / "skills.sqlite3"
    config = runtime_configuration(path)
    request = publication_request(tmp_path / "lost-package")
    first = build_skills_runtime(config)
    created = first.gateway.publish(PublishSkillVersionCommand(request))
    first.close()
    reopened = build_skills_runtime(config)
    replayed = reopened.gateway.publish(PublishSkillVersionCommand(request))
    assert replayed.identity == created.identity
    assert replayed.outcome.value == "replayed"


def test_restore_point_format_is_independent_from_schema_version() -> None:
    assert SkillsRestorePointFormatVersion.V1.value == 1


def test_full_state_fingerprint_and_restore_cover_all_thirteen_families(
    tmp_path: Path,
) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(path)
    runtime = build_skills_runtime(config)
    runtime.close()
    insert_full_state(path, "1")
    service = coordinator(path, recovery)
    point = service.create_restore_point(runtime).restore_point
    assert tuple(name for name, count in point.record_counts if count) == FAMILIES
    insert_full_state(path, "2")
    result = service.restore(SkillsRestoreRequest(point, config, runtime))
    with closing(sqlite3.connect(path)) as connection:
        assert tuple(
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in FAMILIES
        ) == (1,) * 13
    result.close()


def test_logical_fingerprint_ignores_vacuum_and_physical_layout(
    tmp_path: Path,
) -> None:
    path = tmp_path / "skills.sqlite3"
    other = tmp_path / "other.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    runtime = build_skills_runtime(runtime_configuration(path))
    runtime.close()
    insert_full_state(path, "1")
    service = coordinator(path, recovery)
    service._backup(path, other)
    before = service._inspect(other)
    with closing(sqlite3.connect(other)) as connection:
        connection.execute("VACUUM")
    assert service._inspect(other) == before


@pytest.mark.parametrize("mutation", ["truncate", "append"])
def test_physical_artifact_tampering_is_detected(
    tmp_path: Path, mutation: str
) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    runtime = build_skills_runtime(runtime_configuration(path))
    runtime.close()
    service = coordinator(path, recovery)
    point = service.create_restore_point(runtime).restore_point
    backup = service._backup_path(point.backup_reference)
    content = backup.read_bytes()
    backup.write_bytes(content[:-1] if mutation == "truncate" else content + b"x")
    with pytest.raises(SkillsRecoveryArtifactInvalid):
        service.verify_restore_point(point)


def test_manifest_and_artifact_are_both_required(tmp_path: Path) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    runtime = build_skills_runtime(runtime_configuration(path))
    runtime.close()
    service = coordinator(path, recovery)
    point = service.create_restore_point(runtime).restore_point
    service._manifest_path(point.restore_point_id).unlink()
    with pytest.raises(SkillsRecoveryArtifactMissing):
        service.verify_restore_point(point)


def test_repeated_verification_is_read_only_and_detects_later_tamper(
    tmp_path: Path,
) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    runtime = build_skills_runtime(runtime_configuration(path))
    runtime.close()
    service = coordinator(path, recovery)
    point = service.create_restore_point(runtime).restore_point
    manifest = service._manifest_path(point.restore_point_id)
    backup = service._backup_path(point.backup_reference)
    stamps = (manifest.stat().st_mtime_ns, backup.stat().st_mtime_ns)
    first = service.verify_restore_point(point)
    second = service.verify_restore_point(point)
    assert first.restore_point_id == second.restore_point_id
    assert stamps == (manifest.stat().st_mtime_ns, backup.stat().st_mtime_ns)
    manifest.write_text("{}", encoding="utf-8")
    with pytest.raises(SkillsRecoveryArtifactInvalid):
        service.verify_restore_point(point)


def test_existing_valid_restore_point_is_reused_not_overwritten(
    tmp_path: Path,
) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    runtime = build_skills_runtime(runtime_configuration(path))
    runtime.close()
    service = coordinator(path, recovery)
    first = service.create_restore_point(runtime)
    backup = service._backup_path(first.restore_point.backup_reference)
    stamp = backup.stat().st_mtime_ns
    second = service.create_restore_point(runtime)
    assert second.outcome.value == "reused_verified"
    assert second.restore_point == first.restore_point
    assert backup.stat().st_mtime_ns == stamp


def test_existing_invalid_restore_point_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    runtime = build_skills_runtime(runtime_configuration(path))
    runtime.close()
    service = coordinator(path, recovery)
    first = service.create_restore_point(runtime).restore_point
    backup = service._backup_path(first.backup_reference)
    backup.write_bytes(b"invalid")
    with pytest.raises(SkillsRecoveryArtifactInvalid):
        service.create_restore_point(runtime)
    assert backup.read_bytes() == b"invalid"


def test_internal_lock_and_staging_collisions_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    runtime = build_skills_runtime(runtime_configuration(path))
    runtime.close()
    service = coordinator(path, recovery)
    lock = recovery / ".skills-recovery.lock"
    lock.write_text("", encoding="utf-8")
    with pytest.raises(SkillsRecoveryConflict):
        service.create_restore_point(runtime)
    lock.unlink()
    staging = recovery / ".skills-backup-staging.sqlite3"
    staging.write_bytes(b"owned elsewhere")
    with pytest.raises(SkillsRecoveryConflict):
        service.create_restore_point(runtime)
    assert staging.read_bytes() == b"owned elsewhere"


def test_restore_result_explicitly_owns_and_closes_composition(tmp_path: Path) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(path)
    runtime = build_skills_runtime(config)
    runtime.close()
    service = coordinator(path, recovery)
    point = service.create_restore_point(runtime).restore_point
    result = service.restore(SkillsRestoreRequest(point, config, runtime))
    assert result.composition.state is SkillsRuntimeState.READY
    result.close()
    assert result.composition.state.value == "closed"


def test_rollback_failure_requires_manual_intervention_and_preserves_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(path)
    runtime = build_skills_runtime(config)
    runtime.close()
    service = coordinator(path, recovery)
    point = service.create_restore_point(runtime).restore_point

    def fail_rebuild(_request: object) -> object:
        raise SkillsRecoveryCompositionRebuildFailed()

    original_replace = os.replace

    def fail_rollback(source: Path, target: Path) -> None:
        if Path(source).name == ".skills-restore-return.sqlite3":
            raise OSError("injected")
        original_replace(source, target)

    monkeypatch.setattr(service, "_rebuild", fail_rebuild)
    monkeypatch.setattr(os, "replace", fail_rollback)
    with pytest.raises(SkillsRecoveryManualInterventionRequired) as caught:
        service.restore(SkillsRestoreRequest(point, config, runtime))
    assert str(path) not in str(caught.value)
    assert (path.parent / ".skills-restore-rollback.sqlite3").exists()


def test_substitution_between_verify_and_copy_is_detected_before_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(path)
    runtime = build_skills_runtime(config)
    runtime.close()
    insert_full_state(path, "1")
    service = coordinator(path, recovery)
    point = service.create_restore_point(runtime).restore_point
    insert_full_state(path, "2")
    original = service._copy_file

    def substitute(source: Path, target: Path) -> None:
        source.write_bytes(b"substituted")
        original(source, target)

    monkeypatch.setattr(service, "_copy_file", substitute)
    with pytest.raises(SkillsRecoveryArtifactInvalid):
        service.restore(SkillsRestoreRequest(point, config, runtime))
    with closing(sqlite3.connect(path)) as connection:
        assert int(connection.execute("SELECT COUNT(*) FROM publications").fetchone()[0]) == 2


@pytest.mark.parametrize(
    "failure",
    [
        SkillsRecoveryArtifactInvalid,
        SkillsRecoveryCompositionRebuildFailed,
    ],
)
def test_post_replace_failures_restore_exact_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[Exception],
) -> None:
    path = tmp_path / "skills.sqlite3"
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    config = runtime_configuration(path)
    runtime = build_skills_runtime(config)
    runtime.close()
    service = coordinator(path, recovery)
    point = service.create_restore_point(runtime).restore_point
    insert_full_state(path, "1")
    original_state = service._inspect(path)
    if failure is SkillsRecoveryCompositionRebuildFailed:
        monkeypatch.setattr(
            service,
            "_rebuild",
            lambda _request: (_ for _ in ()).throw(failure()),
        )
    else:
        monkeypatch.setattr(
            service,
            "_verify_target_logical",
            lambda *_args: (_ for _ in ()).throw(failure()),
        )
    with pytest.raises(SkillsRecoveryPostRestoreFailed):
        service.restore(SkillsRestoreRequest(point, config, runtime))
    assert service._inspect(path) == original_state
