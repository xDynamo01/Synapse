from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from synapse.skills.composition import (
    SkillsHealthStatus,
    SkillsRuntimeComposition,
    SkillsRuntimeState,
    build_skills_runtime,
)
from synapse.skills.persistence import (
    SkillPersistenceIntegrityChecker,
    SkillPersistenceMigrator,
    SkillSQLiteConfig,
    SkillSQLiteConnectionFactory,
)

from .errors import (
    SkillsRecoveryArtifactInvalid,
    SkillsRecoveryArtifactMissing,
    SkillsRecoveryAtomicReplaceFailed,
    SkillsRecoveryCompositionRebuildFailed,
    SkillsRecoveryConflict,
    SkillsRecoveryError,
    SkillsRecoveryInvalidConfiguration,
    SkillsRecoveryManualInterventionRequired,
    SkillsRecoveryPostRestoreFailed,
    SkillsRecoverySourceOpen,
    SkillsRecoverySourceUnavailable,
    SkillsRecoverySourceUnhealthy,
    SkillsRecoveryStagingFailed,
)
from .models import (
    SkillsBackupReference,
    SkillsCreateOutcome,
    SkillsCreateRestorePointResult,
    SkillsLogicalFingerprint,
    SkillsPhysicalFingerprint,
    SkillsRecoveryClock,
    SkillsRecoveryConfiguration,
    SkillsRestorePoint,
    SkillsRestorePointFormatVersion,
    SkillsRestorePointVerification,
    SkillsRestoreRequest,
    SkillsRestoreResult,
)

_RECORD_TABLES = (
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
_BACKUP_STAGING = ".skills-backup-staging.sqlite3"
_MANIFEST_STAGING = ".skills-manifest-staging.json"
_RESTORE_STAGING = ".skills-restore-staging.sqlite3"
_ROLLBACK = ".skills-restore-rollback.sqlite3"
_ROLLBACK_RETURN = ".skills-restore-return.sqlite3"
_LOCK = ".skills-recovery.lock"


@dataclass(frozen=True)
class _RollbackArtifactBinding:
    source_identity: str
    physical: SkillsPhysicalFingerprint
    logical: SkillsLogicalFingerprint
    schema_version: int
    migration_checksum: str
    record_counts: tuple[tuple[str, int], ...]
    artifact_size: int


class SkillsRecoveryCoordinator:
    """Administrative whole-database recovery; it never edits domain records."""

    def __init__(
        self, configuration: SkillsRecoveryConfiguration, clock: SkillsRecoveryClock
    ) -> None:
        self._configuration = configuration
        self._clock = clock

    def create_restore_point(
        self, composition: SkillsRuntimeComposition
    ) -> SkillsCreateRestorePointResult:
        self._require_closed(composition)
        with self._exclusive():
            source = self._configuration.source.database
            staging = self._configuration.recovery_directory / _BACKUP_STAGING
            if staging.exists():
                raise SkillsRecoveryConflict()
            try:
                self._backup(source, staging)
                state = self._inspect(staging)
                physical = self._physical(staging)
                size = self._bounded_size(staging)
                restore_id = _restore_identity(state[0], state[1], state[2])
                manifest = self._manifest_path(restore_id)
                if manifest.exists():
                    existing = self._read_manifest(manifest)
                    self.verify_restore_point(existing)
                    staging.unlink()
                    return SkillsCreateRestorePointResult(
                        existing, SkillsCreateOutcome.REUSED_VERIFIED, self._time()
                    )
                reference = SkillsBackupReference(f"backup:{physical.value}")
                published = self._backup_path(reference)
                if published.exists():
                    raise SkillsRecoveryArtifactInvalid()
                point = SkillsRestorePoint(
                    restore_id,
                    SkillsRestorePointFormatVersion.V1,
                    reference,
                    state[0],
                    state[0],
                    physical,
                    1,
                    state[2],
                    self._time(),
                    size,
                    state[1],
                )
                os.replace(staging, published)
                self._sync_file(published)
                try:
                    self._publish_manifest(point, manifest)
                except Exception:
                    # An unpublished backup is an orphan, not a valid restore point.
                    published.unlink(missing_ok=True)
                    raise
                self._sync_directory(self._configuration.recovery_directory)
                return SkillsCreateRestorePointResult(
                    point, SkillsCreateOutcome.CREATED, self._time()
                )
            except SkillsRecoveryError:
                staging.unlink(missing_ok=True)
                raise
            except Exception as exc:
                staging.unlink(missing_ok=True)
                raise SkillsRecoveryStagingFailed() from exc

    def verify_restore_point(
        self, restore_point: SkillsRestorePoint
    ) -> SkillsRestorePointVerification:
        manifest_path = self._manifest_path(restore_point.restore_point_id)
        backup = self._backup_path(restore_point.backup_reference)
        if not manifest_path.exists() or not backup.exists():
            raise SkillsRecoveryArtifactMissing()
        persisted = self._read_manifest(manifest_path)
        if persisted != restore_point:
            raise SkillsRecoveryArtifactInvalid()
        self._verify_artifact(backup, restore_point)
        return SkillsRestorePointVerification(
            restore_point.restore_point_id,
            restore_point.backup_fingerprint,
            restore_point.physical_fingerprint,
            restore_point.record_counts,
            self._time(),
        )

    def restore(self, request: SkillsRestoreRequest) -> SkillsRestoreResult:
        self._require_closed(request.composition)
        with self._exclusive():
            self.verify_restore_point(request.restore_point)
            target = self._configuration.source.database
            if (
                not target.exists()
                or target.is_symlink()
                or target.stat().st_nlink != 1
            ):
                raise SkillsRecoverySourceUnavailable()
            staging = target.parent / _RESTORE_STAGING
            rollback = target.parent / _ROLLBACK
            rollback_return = target.parent / _ROLLBACK_RETURN
            if any(path.exists() for path in (staging, rollback, rollback_return)):
                raise SkillsRecoveryConflict()
            backup = self._backup_path(request.restore_point.backup_reference)
            replaced = False
            runtime: SkillsRuntimeComposition | None = None
            try:
                self._copy_file(backup, staging)
                self._verify_artifact(staging, request.restore_point)
                self._backup(target, rollback)
                rollback_binding = self._capture_rollback_binding(target, rollback)
                self._verify_rollback_binding(rollback, rollback_binding)
                current_state = self._logical_snapshot(target)
                if (
                    current_state[0] != rollback_binding.logical
                    or current_state[1] != rollback_binding.record_counts
                    or current_state[2] != rollback_binding.migration_checksum
                    or current_state[3] != rollback_binding.schema_version
                ):
                    raise SkillsRecoveryConflict()
                os.replace(staging, target)
                replaced = True
                self._verify_replaced_target(target, request.restore_point)
                runtime = self._rebuild(request)
                health = runtime.verify_integrity()
                if (
                    runtime.state is not SkillsRuntimeState.READY
                    or health.status is not SkillsHealthStatus.HEALTHY
                    or not health.schema_current
                    or not health.database_reachable
                    or not health.application_constructed
                    or health.integrity is not SkillsHealthStatus.HEALTHY
                    or health.foreign_keys is not SkillsHealthStatus.HEALTHY
                    or health.compatibility_enabled
                    is not (
                        request.runtime_configuration.compatibility.value
                        == "read_only"
                    )
                ):
                    raise SkillsRecoveryPostRestoreFailed()
                rollback.unlink()
                return SkillsRestoreResult(
                    request.restore_point.restore_point_id,
                    request.restore_point.backup_fingerprint,
                    self._time(),
                    runtime,
                )
            except Exception as exc:
                if not replaced:
                    staging.unlink(missing_ok=True)
                    rollback.unlink(missing_ok=True)
                    if isinstance(exc, SkillsRecoveryError):
                        raise
                    raise SkillsRecoveryAtomicReplaceFailed() from exc
                if runtime is not None:
                    runtime.close()
                try:
                    self._copy_file(rollback, rollback_return)
                    self._verify_rollback_binding(rollback_return, rollback_binding)
                    os.replace(rollback_return, target)
                    self._verify_rollback_binding(target, rollback_binding)
                    rollback_runtime = self._rebuild_rollback(request)
                    rollback_health = rollback_runtime.verify_integrity()
                    if (
                        rollback_runtime.state is not SkillsRuntimeState.READY
                        or rollback_health.status is not SkillsHealthStatus.HEALTHY
                        or not rollback_health.schema_current
                        or not rollback_health.database_reachable
                        or not rollback_health.application_constructed
                        or rollback_health.integrity is not SkillsHealthStatus.HEALTHY
                        or rollback_health.foreign_keys is not SkillsHealthStatus.HEALTHY
                    ):
                        rollback_runtime.close()
                        raise SkillsRecoveryArtifactInvalid()
                    rollback_runtime.close()
                    rollback.unlink()
                except Exception as rollback_exc:
                    # Keep every surviving private artifact for operator diagnosis.
                    raise SkillsRecoveryManualInterventionRequired() from rollback_exc
                if isinstance(exc, SkillsRecoveryCompositionRebuildFailed):
                    raise exc
                raise SkillsRecoveryPostRestoreFailed() from exc

    def _rebuild(self, request: SkillsRestoreRequest) -> SkillsRuntimeComposition:
        return self._build_runtime(request)

    def _rebuild_rollback(
        self, request: SkillsRestoreRequest
    ) -> SkillsRuntimeComposition:
        return self._build_runtime(request)

    def _build_runtime(
        self, request: SkillsRestoreRequest
    ) -> SkillsRuntimeComposition:
        if request.runtime_configuration.database != self._configuration.source:
            raise SkillsRecoveryCompositionRebuildFailed()
        try:
            return build_skills_runtime(request.runtime_configuration)
        except Exception as exc:
            raise SkillsRecoveryCompositionRebuildFailed() from exc

    def _inspect(
        self, path: Path
    ) -> tuple[SkillsLogicalFingerprint, tuple[tuple[str, int], ...], str]:
        if not path.exists() or not path.is_file() or path.is_symlink():
            raise SkillsRecoverySourceUnavailable()
        factory = SkillSQLiteConnectionFactory(
            SkillSQLiteConfig(path, self._configuration.source.busy_timeout_ms)
        )
        try:
            SkillPersistenceMigrator(factory, self._clock).verify()
            SkillPersistenceIntegrityChecker(factory).check()
            logical, counts, checksum, _schema = self._logical_snapshot(path)
        except SkillsRecoveryError:
            raise
        except Exception as exc:
            raise SkillsRecoverySourceUnhealthy() from exc
        return logical, counts, checksum

    def _logical_snapshot(
        self, path: Path
    ) -> tuple[
        SkillsLogicalFingerprint,
        tuple[tuple[str, int], ...],
        str,
        int,
    ]:
        try:
            with closing(
                sqlite3.connect(f"file:{path}?mode=ro", uri=True, isolation_level=None)
            ) as connection:
                connection.execute("BEGIN")
                schema_row = connection.execute(
                    "SELECT schema_version FROM skill_schema_metadata "
                    "WHERE singleton = 1"
                ).fetchone()
                checksum_row = connection.execute(
                    "SELECT checksum FROM skill_migration_history "
                    "WHERE migration_id = 'skills-schema-v1'"
                ).fetchone()
                if schema_row is None or checksum_row is None:
                    raise SkillsRecoverySourceUnhealthy()
                schema = int(schema_row[0])
                checksum = str(checksum_row[0])
                digest = hashlib.sha256()
                digest.update(
                    f"skills-logical-database-v1\0schema:{schema}\0".encode("ascii")
                )
                digest.update(checksum.encode("ascii"))
                counts: list[tuple[str, int]] = []
                for table in _RECORD_TABLES:
                    rows = connection.execute(
                        f"SELECT payload FROM {table} ORDER BY payload"
                    ).fetchall()
                    counts.append((table, len(rows)))
                    digest.update(b"\0family:" + table.encode("ascii") + b"\0")
                    for (payload,) in rows:
                        canonical = json.dumps(
                            json.loads(str(payload)),
                            ensure_ascii=True,
                            separators=(",", ":"),
                            sort_keys=True,
                        ).encode("ascii")
                        digest.update(len(canonical).to_bytes(8, "big"))
                        digest.update(canonical)
                connection.execute("COMMIT")
        except SkillsRecoveryError:
            raise
        except Exception as exc:
            raise SkillsRecoverySourceUnhealthy() from exc
        return (
            SkillsLogicalFingerprint(digest.hexdigest()),
            tuple(counts),
            checksum,
            schema,
        )

    def _capture_rollback_binding(
        self, source: Path, artifact: Path
    ) -> _RollbackArtifactBinding:
        logical, counts, checksum, schema = self._logical_snapshot(artifact)
        return _RollbackArtifactBinding(
            str(source.resolve(strict=True)),
            self._physical(artifact),
            logical,
            schema,
            checksum,
            counts,
            self._bounded_size(artifact),
        )

    def _verify_rollback_binding(
        self, artifact: Path, binding: _RollbackArtifactBinding
    ) -> None:
        self._verify_rollback_open(artifact)
        self._verify_rollback_schema(artifact, binding)
        self._verify_rollback_integrity(artifact)
        self._verify_rollback_foreign_keys(artifact)
        self._verify_rollback_logical(artifact, binding)
        self._verify_rollback_physical(artifact, binding)
        self._verify_rollback_source(binding)

    @staticmethod
    def _verify_rollback_open(artifact: Path) -> None:
        try:
            with closing(
                sqlite3.connect(f"file:{artifact}?mode=ro", uri=True)
            ) as connection:
                connection.execute("SELECT 1").fetchone()
        except sqlite3.Error as exc:
            raise SkillsRecoveryArtifactInvalid() from exc

    def _verify_rollback_schema(
        self, artifact: Path, binding: _RollbackArtifactBinding
    ) -> None:
        _logical, _counts, checksum, schema = self._logical_snapshot(artifact)
        if (
            schema != binding.schema_version
            or checksum != binding.migration_checksum
        ):
            raise SkillsRecoveryArtifactInvalid()

    @staticmethod
    def _verify_rollback_integrity(artifact: Path) -> None:
        try:
            with closing(
                sqlite3.connect(f"file:{artifact}?mode=ro", uri=True)
            ) as connection:
                rows = connection.execute("PRAGMA integrity_check").fetchall()
            if rows != [("ok",)]:
                raise SkillsRecoveryArtifactInvalid()
        except sqlite3.Error as exc:
            raise SkillsRecoveryArtifactInvalid() from exc

    @staticmethod
    def _verify_rollback_foreign_keys(artifact: Path) -> None:
        try:
            with closing(
                sqlite3.connect(f"file:{artifact}?mode=ro", uri=True)
            ) as connection:
                rows = connection.execute("PRAGMA foreign_key_check").fetchall()
            if rows:
                raise SkillsRecoveryArtifactInvalid()
        except sqlite3.Error as exc:
            raise SkillsRecoveryArtifactInvalid() from exc

    def _verify_rollback_logical(
        self, artifact: Path, binding: _RollbackArtifactBinding
    ) -> None:
        logical, counts, checksum, schema = self._logical_snapshot(artifact)
        if (
            logical != binding.logical
            or schema != binding.schema_version
            or checksum != binding.migration_checksum
            or counts != binding.record_counts
        ):
            raise SkillsRecoveryArtifactInvalid()

    def _verify_rollback_physical(
        self, artifact: Path, binding: _RollbackArtifactBinding
    ) -> None:
        if (
            self._bounded_size(artifact) != binding.artifact_size
            or self._physical(artifact) != binding.physical
        ):
            raise SkillsRecoveryArtifactInvalid()

    def _verify_rollback_source(self, binding: _RollbackArtifactBinding) -> None:
        if (
            str(self._configuration.source.database.resolve(strict=True))
            != binding.source_identity
        ):
            raise SkillsRecoveryArtifactInvalid()

    @staticmethod
    def _backup(source: Path, target: Path) -> None:
        try:
            with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as source_db:
                with closing(sqlite3.connect(target)) as target_db:
                    source_db.backup(target_db)
        except sqlite3.Error as exc:
            raise SkillsRecoveryStagingFailed() from exc

    @staticmethod
    def _copy_file(source: Path, target: Path) -> None:
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with source.open("rb") as input_stream, os.fdopen(
                descriptor, "wb"
            ) as output_stream:
                for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                    output_stream.write(chunk)
                output_stream.flush()
                os.fsync(output_stream.fileno())
        except (OSError, ValueError) as exc:
            target.unlink(missing_ok=True)
            raise SkillsRecoveryStagingFailed() from exc

    def _verify_artifact(self, path: Path, point: SkillsRestorePoint) -> None:
        try:
            if path.is_symlink() or path.stat().st_nlink != 1:
                raise SkillsRecoveryArtifactInvalid()
            size = self._bounded_size(path)
            physical = self._physical(path)
            if (
                size != point.database_size
                or physical != point.physical_fingerprint
                or point.backup_reference.value != f"backup:{physical.value}"
            ):
                raise SkillsRecoveryArtifactInvalid()
            logical, counts, checksum = self._inspect(path)
        except SkillsRecoveryError as exc:
            raise SkillsRecoveryArtifactInvalid() from exc
        if (
            logical != point.backup_fingerprint
            or counts != point.record_counts
            or checksum != point.migration_checksum
            or _restore_identity(logical, counts, checksum) != point.restore_point_id
        ):
            raise SkillsRecoveryArtifactInvalid()

    def _verify_replaced_target(
        self, path: Path, point: SkillsRestorePoint
    ) -> None:
        self._verify_target_open(path)
        self._verify_target_schema(path)
        self._verify_target_migration(path, point)
        self._verify_target_integrity(path)
        self._verify_target_foreign_keys(path)
        self._verify_target_logical(path, point)
        self._verify_target_physical(path, point)

    @staticmethod
    def _verify_target_open(path: Path) -> None:
        try:
            with closing(
                sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            ) as connection:
                connection.execute("SELECT 1").fetchone()
        except sqlite3.Error as exc:
            raise SkillsRecoveryPostRestoreFailed() from exc

    @staticmethod
    def _verify_target_schema(path: Path) -> None:
        try:
            with closing(
                sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            ) as connection:
                row = connection.execute(
                    "SELECT schema_version FROM skill_schema_metadata "
                    "WHERE singleton = 1"
                ).fetchone()
            if row is None or int(row[0]) != 1:
                raise SkillsRecoveryPostRestoreFailed()
        except sqlite3.Error as exc:
            raise SkillsRecoveryPostRestoreFailed() from exc

    @staticmethod
    def _verify_target_migration(path: Path, point: SkillsRestorePoint) -> None:
        try:
            with closing(
                sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            ) as connection:
                row = connection.execute(
                    "SELECT checksum FROM skill_migration_history "
                    "WHERE migration_id = 'skills-schema-v1'"
                ).fetchone()
            if row is None or str(row[0]) != point.migration_checksum:
                raise SkillsRecoveryPostRestoreFailed()
        except sqlite3.Error as exc:
            raise SkillsRecoveryPostRestoreFailed() from exc

    @staticmethod
    def _verify_target_integrity(path: Path) -> None:
        try:
            with closing(
                sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            ) as connection:
                rows = connection.execute("PRAGMA integrity_check").fetchall()
            if rows != [("ok",)]:
                raise SkillsRecoveryPostRestoreFailed()
        except sqlite3.Error as exc:
            raise SkillsRecoveryPostRestoreFailed() from exc

    @staticmethod
    def _verify_target_foreign_keys(path: Path) -> None:
        try:
            with closing(
                sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            ) as connection:
                rows = connection.execute("PRAGMA foreign_key_check").fetchall()
            if rows:
                raise SkillsRecoveryPostRestoreFailed()
        except sqlite3.Error as exc:
            raise SkillsRecoveryPostRestoreFailed() from exc

    def _verify_target_logical(
        self, path: Path, point: SkillsRestorePoint
    ) -> None:
        logical, counts, checksum, schema = self._logical_snapshot(path)
        if (
            logical != point.backup_fingerprint
            or counts != point.record_counts
            or checksum != point.migration_checksum
            or schema != point.schema_version
        ):
            raise SkillsRecoveryPostRestoreFailed()

    def _verify_target_physical(
        self, path: Path, point: SkillsRestorePoint
    ) -> None:
        if (
            self._bounded_size(path) != point.database_size
            or self._physical(path) != point.physical_fingerprint
        ):
            raise SkillsRecoveryPostRestoreFailed()

    def _bounded_size(self, path: Path) -> int:
        size = path.stat().st_size
        if size < 1 or size > self._configuration.maximum_backup_bytes:
            raise SkillsRecoveryArtifactInvalid()
        return size

    @staticmethod
    def _physical(path: Path) -> SkillsPhysicalFingerprint:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return SkillsPhysicalFingerprint(digest.hexdigest())

    def _backup_path(self, reference: SkillsBackupReference) -> Path:
        return self._configuration.recovery_directory / (
            reference.value.removeprefix("backup:") + ".sqlite3"
        )

    def _manifest_path(self, identity: SkillsLogicalFingerprint) -> Path:
        return self._configuration.recovery_directory / f"{identity.value}.json"

    def _publish_manifest(self, point: SkillsRestorePoint, destination: Path) -> None:
        staging = self._configuration.recovery_directory / _MANIFEST_STAGING
        if staging.exists() or destination.exists():
            raise SkillsRecoveryConflict()
        data = _manifest_data(point)
        descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staging, destination)
        finally:
            staging.unlink(missing_ok=True)

    def _read_manifest(self, path: Path) -> SkillsRestorePoint:
        if path.is_symlink():
            raise SkillsRecoveryArtifactInvalid()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return _point_from_manifest(data)
        except SkillsRecoveryError:
            raise
        except Exception as exc:
            raise SkillsRecoveryArtifactInvalid() from exc

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        lock = self._configuration.recovery_directory / _LOCK
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise SkillsRecoveryConflict() from exc
        try:
            os.close(descriptor)
            yield
        finally:
            lock.unlink(missing_ok=True)

    @staticmethod
    def _require_closed(composition: SkillsRuntimeComposition) -> None:
        if (
            not isinstance(composition, SkillsRuntimeComposition)
            or composition.state is not SkillsRuntimeState.CLOSED
        ):
            raise SkillsRecoverySourceOpen()

    def _time(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise SkillsRecoveryInvalidConfiguration()
        return value

    @staticmethod
    def _sync_file(path: Path) -> None:
        with path.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _sync_directory(path: Path) -> None:
        if os.name != "nt":
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)


def _restore_identity(
    logical: SkillsLogicalFingerprint,
    counts: tuple[tuple[str, int], ...],
    checksum: str,
) -> SkillsLogicalFingerprint:
    digest = hashlib.sha256()
    projection = {
        "format_version": 1,
        "logical_fingerprint": logical.value,
        "schema_version": 1,
        "migration_checksum": checksum,
        "record_counts": counts,
    }
    digest.update(
        json.dumps(projection, sort_keys=True, separators=(",", ":")).encode("ascii")
    )
    return SkillsLogicalFingerprint(digest.hexdigest())


def _manifest_data(point: SkillsRestorePoint) -> dict[str, object]:
    return {
        "restore_point_id": point.restore_point_id.value,
        "format_version": point.format_version.value,
        "backup_reference": point.backup_reference.value,
        "source_fingerprint": point.source_fingerprint.value,
        "backup_fingerprint": point.backup_fingerprint.value,
        "physical_fingerprint": point.physical_fingerprint.value,
        "schema_version": point.schema_version,
        "migration_checksum": point.migration_checksum,
        "created_at": point.created_at.isoformat(),
        "database_size": point.database_size,
        "record_counts": point.record_counts,
    }


def _point_from_manifest(data: object) -> SkillsRestorePoint:
    if not isinstance(data, dict):
        raise SkillsRecoveryArtifactInvalid()
    return SkillsRestorePoint(
        SkillsLogicalFingerprint(str(data["restore_point_id"])),
        SkillsRestorePointFormatVersion(int(data["format_version"])),
        SkillsBackupReference(str(data["backup_reference"])),
        SkillsLogicalFingerprint(str(data["source_fingerprint"])),
        SkillsLogicalFingerprint(str(data["backup_fingerprint"])),
        SkillsPhysicalFingerprint(str(data["physical_fingerprint"])),
        int(data["schema_version"]),
        str(data["migration_checksum"]),
        datetime.fromisoformat(str(data["created_at"])),
        int(data["database_size"]),
        tuple((str(item[0]), int(item[1])) for item in data["record_counts"]),
    )
