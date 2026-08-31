"""Concrete local persistence for the Skills Runtime Phase 2 contracts."""

from .connection import SkillSQLiteConfig, SkillSQLiteConnectionFactory
from .errors import (
    SkillPersistenceDatabaseCorrupt,
    SkillPersistenceDivergentDuplicate,
    SkillPersistenceError,
    SkillPersistenceMigrationChecksumMismatch,
    SkillPersistenceMigrationFailed,
    SkillPersistenceMigrationRequired,
    SkillPersistenceQueryFailed,
    SkillPersistenceRecordDecodeFailed,
    SkillPersistenceSchemaUnsupported,
    SkillPersistenceTransactionFailed,
    SkillPersistenceUnavailable,
    SkillPersistenceUniquenessConflict,
)
from .integrity import SkillPersistenceIntegrityChecker
from .migrations import (
    SkillPersistenceMigrator,
    SkillPersistenceSchemaVersion,
)
from .stores import (
    SQLiteSkillAssignmentStore,
    SQLiteSkillBindingStore,
    SQLiteSkillCatalogStore,
    SQLiteSkillExternalBindingStore,
    SQLiteSkillInstallationStore,
    SQLiteSkillLeaseStore,
    SQLiteSkillLifecycleStore,
    SQLiteSkillPrivateEvalBindingStore,
)

__all__ = [
    "SQLiteSkillAssignmentStore",
    "SQLiteSkillBindingStore",
    "SQLiteSkillCatalogStore",
    "SQLiteSkillExternalBindingStore",
    "SQLiteSkillInstallationStore",
    "SQLiteSkillLeaseStore",
    "SQLiteSkillLifecycleStore",
    "SQLiteSkillPrivateEvalBindingStore",
    "SkillPersistenceDatabaseCorrupt",
    "SkillPersistenceDivergentDuplicate",
    "SkillPersistenceError",
    "SkillPersistenceIntegrityChecker",
    "SkillPersistenceMigrationChecksumMismatch",
    "SkillPersistenceMigrationFailed",
    "SkillPersistenceMigrationRequired",
    "SkillPersistenceMigrator",
    "SkillPersistenceQueryFailed",
    "SkillPersistenceRecordDecodeFailed",
    "SkillPersistenceSchemaUnsupported",
    "SkillPersistenceSchemaVersion",
    "SkillPersistenceTransactionFailed",
    "SkillPersistenceUnavailable",
    "SkillPersistenceUniquenessConflict",
    "SkillSQLiteConfig",
    "SkillSQLiteConnectionFactory",
]
