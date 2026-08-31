from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Protocol

from synapse.skills.composition import SkillsRuntimeComposition, SkillsRuntimeConfiguration
from synapse.skills.persistence import SkillSQLiteConfig

from .errors import SkillsRecoveryInvalidConfiguration

_REFERENCE = re.compile(r"^backup:[0-9a-f]{64}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class SkillsRecoveryClock(Protocol):
    def __call__(self) -> datetime: ...


class SkillsRestorePointFormatVersion(IntEnum):
    V1 = 1


class SkillsCreateOutcome(StrEnum):
    CREATED = "created"
    REUSED_VERIFIED = "reused_verified"


@dataclass(frozen=True, order=True)
class SkillsBackupReference:
    """Identity of published backup bytes, never of logical database state."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _REFERENCE.fullmatch(self.value):
            raise SkillsRecoveryInvalidConfiguration()


@dataclass(frozen=True, order=True)
class SkillsLogicalFingerprint:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _DIGEST.fullmatch(self.value):
            raise SkillsRecoveryInvalidConfiguration()


@dataclass(frozen=True, order=True)
class SkillsPhysicalFingerprint:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _DIGEST.fullmatch(self.value):
            raise SkillsRecoveryInvalidConfiguration()


@dataclass(frozen=True)
class SkillsRestorePoint:
    """Content identity plus the inseparable published artifact binding."""

    restore_point_id: SkillsLogicalFingerprint
    format_version: SkillsRestorePointFormatVersion
    backup_reference: SkillsBackupReference
    source_fingerprint: SkillsLogicalFingerprint
    backup_fingerprint: SkillsLogicalFingerprint
    physical_fingerprint: SkillsPhysicalFingerprint
    schema_version: int
    migration_checksum: str
    created_at: datetime
    database_size: int
    record_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        valid_counts = (
            isinstance(self.record_counts, tuple)
            and len(self.record_counts) == 13
            and all(
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and item[0]
                and isinstance(item[1], int)
                and not isinstance(item[1], bool)
                and item[1] >= 0
                for item in self.record_counts
            )
        )
        if (
            not isinstance(self.restore_point_id, SkillsLogicalFingerprint)
            or not isinstance(self.format_version, SkillsRestorePointFormatVersion)
            or not isinstance(self.backup_reference, SkillsBackupReference)
            or not isinstance(self.source_fingerprint, SkillsLogicalFingerprint)
            or not isinstance(self.backup_fingerprint, SkillsLogicalFingerprint)
            or not isinstance(self.physical_fingerprint, SkillsPhysicalFingerprint)
            or isinstance(self.schema_version, bool)
            or self.schema_version < 1
            or not isinstance(self.migration_checksum, str)
            or not _DIGEST.fullmatch(self.migration_checksum)
            or not isinstance(self.created_at, datetime)
            or self.created_at.tzinfo is None
            or self.created_at.utcoffset() != UTC.utcoffset(self.created_at)
            or isinstance(self.database_size, bool)
            or self.database_size < 1
            or not valid_counts
        ):
            raise SkillsRecoveryInvalidConfiguration()


@dataclass(frozen=True)
class SkillsRestorePointVerification:
    restore_point_id: SkillsLogicalFingerprint
    logical_fingerprint: SkillsLogicalFingerprint
    physical_fingerprint: SkillsPhysicalFingerprint
    record_counts: tuple[tuple[str, int], ...]
    verified_at: datetime


@dataclass(frozen=True)
class SkillsCreateRestorePointResult:
    restore_point: SkillsRestorePoint
    outcome: SkillsCreateOutcome
    completed_at: datetime


@dataclass(frozen=True, repr=False)
class SkillsRecoveryConfiguration:
    source: SkillSQLiteConfig
    recovery_directory: Path
    maximum_backup_bytes: int

    def __post_init__(self) -> None:
        directory = self.recovery_directory
        source = self.source.database if isinstance(self.source, SkillSQLiteConfig) else None
        try:
            overlap = source is not None and source.resolve(strict=False).is_relative_to(
                directory.resolve(strict=True)
            )
            symlink_parent = any(parent.is_symlink() for parent in directory.parents)
        except (OSError, RuntimeError):
            overlap = True
            symlink_parent = True
        if (
            not isinstance(self.source, SkillSQLiteConfig)
            or not isinstance(directory, Path)
            or not directory.is_absolute()
            or not directory.exists()
            or not directory.is_dir()
            or directory.is_symlink()
            or symlink_parent
            or str(directory).startswith(("\\\\", "//"))
            or overlap
            or isinstance(self.maximum_backup_bytes, bool)
            or not isinstance(self.maximum_backup_bytes, int)
            or not 1 <= self.maximum_backup_bytes <= 1_000_000_000_000
        ):
            raise SkillsRecoveryInvalidConfiguration()

    def __repr__(self) -> str:
        return (
            "SkillsRecoveryConfiguration(source=<redacted>, "
            "recovery_directory=<redacted>, "
            f"maximum_backup_bytes={self.maximum_backup_bytes})"
        )


@dataclass(frozen=True)
class SkillsRestoreRequest:
    restore_point: SkillsRestorePoint
    runtime_configuration: SkillsRuntimeConfiguration
    composition: SkillsRuntimeComposition

    def __post_init__(self) -> None:
        if (
            not isinstance(self.restore_point, SkillsRestorePoint)
            or not isinstance(self.runtime_configuration, SkillsRuntimeConfiguration)
            or not isinstance(self.composition, SkillsRuntimeComposition)
        ):
            raise SkillsRecoveryInvalidConfiguration()


@dataclass(frozen=True)
class SkillsRestoreResult:
    """Transfers ownership of the READY composition to the caller."""

    restore_point_id: SkillsLogicalFingerprint
    target_fingerprint: SkillsLogicalFingerprint
    completed_at: datetime
    composition: SkillsRuntimeComposition

    def close(self) -> None:
        self.composition.close()

    def __enter__(self) -> SkillsRuntimeComposition:
        return self.composition

    def __exit__(self, *_exc: object) -> None:
        self.close()
