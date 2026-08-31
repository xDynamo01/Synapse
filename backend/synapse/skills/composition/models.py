from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from synapse.skills.persistence import SkillSQLiteConfig
from synapse.skills.phase3_values import SkillStoreQueryLimit

from .errors import SkillsCompositionInvalidConfiguration


class SkillsMigrationPolicy(StrEnum):
    REQUIRE_CURRENT = "require_current"
    MIGRATE_IF_NEEDED = "migrate_if_needed"
    VERIFY_ONLY = "verify_only"


class SkillsIntegrityPolicy(StrEnum):
    FULL = "full"
    EXPLICIT_ONLY = "explicit_only"


class SkillsCompatibilityMode(StrEnum):
    DISABLED = "disabled"
    READ_ONLY = "read_only"


class SkillsRuntimeState(StrEnum):
    READY = "ready"
    CLOSED = "closed"


class SkillsMigrationStatus(StrEnum):
    APPLIED = "applied"
    CURRENT_VERIFIED = "current_verified"
    NOT_CHECKED = "not_checked"


class SkillsHealthStatus(StrEnum):
    HEALTHY = "healthy"
    UNAVAILABLE = "unavailable"
    NOT_CHECKED = "not_checked"
    CLOSED = "closed"


@dataclass(frozen=True, repr=False)
class SkillsRuntimeConfiguration:
    database: SkillSQLiteConfig
    migration: SkillsMigrationPolicy
    integrity: SkillsIntegrityPolicy
    compatibility: SkillsCompatibilityMode
    binding_history_limit: SkillStoreQueryLimit

    def __post_init__(self) -> None:
        if (
            not isinstance(self.database, SkillSQLiteConfig)
            or not isinstance(self.migration, SkillsMigrationPolicy)
            or not isinstance(self.integrity, SkillsIntegrityPolicy)
            or not isinstance(self.compatibility, SkillsCompatibilityMode)
            or not isinstance(self.binding_history_limit, SkillStoreQueryLimit)
        ):
            raise SkillsCompositionInvalidConfiguration()

    def __repr__(self) -> str:
        return (
            "SkillsRuntimeConfiguration(database=<redacted>, "
            f"migration={self.migration!r}, integrity={self.integrity!r}, "
            f"compatibility={self.compatibility!r}, "
            f"binding_history_limit={self.binding_history_limit!r})"
        )


@dataclass(frozen=True)
class SkillsRuntimeConfigurationView:
    migration: SkillsMigrationPolicy
    integrity: SkillsIntegrityPolicy
    compatibility: SkillsCompatibilityMode
    binding_history_limit: SkillStoreQueryLimit


@dataclass(frozen=True)
class SkillsHealthResult:
    status: SkillsHealthStatus
    configuration_valid: bool
    schema_current: bool
    migration: SkillsMigrationStatus
    database_reachable: bool
    integrity: SkillsHealthStatus
    foreign_keys: SkillsHealthStatus
    application_constructed: bool
    compatibility_enabled: bool
    runtime_state: SkillsRuntimeState
