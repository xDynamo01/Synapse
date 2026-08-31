"""Safe errors for the pure Repository Runtime domain foundation."""


class RepositoryDomainError(ValueError):
    """Base error that never needs to expose rejected external input."""

    code = "repository_domain_error"


class InvalidRepositoryIdentity(RepositoryDomainError):
    code = "invalid_repository_identity"


class InvalidRepositoryPath(RepositoryDomainError):
    code = "invalid_repository_path"


class InvalidRepositoryModel(RepositoryDomainError):
    code = "invalid_repository_model"


class InvalidRepositoryObservationFacts(InvalidRepositoryModel):
    code = "invalid_repository_observation_facts"


class InvalidRepositoryPathFacts(InvalidRepositoryModel):
    code = "invalid_repository_path_facts"


class InvalidRepositoryPathClassificationPolicy(InvalidRepositoryModel):
    code = "invalid_repository_path_classification_policy"


class InvalidRepositorySnapshotModel(InvalidRepositoryModel):
    code = "invalid_repository_snapshot_model"


class InvalidRepositoryChangeSetModel(InvalidRepositoryModel):
    code = "invalid_repository_change_set_model"


class InvalidRepositoryMutationPlanModel(InvalidRepositoryModel):
    code = "invalid_repository_mutation_plan_model"


class InvalidRepositoryAuthorizationModel(InvalidRepositoryModel):
    code = "invalid_repository_authorization_model"


class InvalidRepositoryRestorePointModel(InvalidRepositoryModel):
    code = "invalid_repository_restore_point_model"


class InvalidRepositoryMutationApplicationModel(InvalidRepositoryModel):
    code = "invalid_repository_mutation_application_model"


class InvalidRepositoryVerificationModel(InvalidRepositoryModel):
    code = "invalid_repository_verification_model"


class InvalidRepositoryRecoveryModel(InvalidRepositoryModel):
    code = "invalid_repository_recovery_model"


class InvalidRepositoryPersistenceModel(InvalidRepositoryModel):
    code = "invalid_repository_persistence_model"


class RepositoryPersistenceError(RepositoryDomainError):
    code = "repository_persistence_error"


class RepositoryPersistenceConflict(RepositoryPersistenceError):
    code = "repository_persistence_conflict"


class RepositoryPersistenceCorrupt(RepositoryPersistenceError):
    code = "repository_persistence_corrupt"


class RepositoryPersistenceVersionUnsupported(RepositoryPersistenceError):
    code = "repository_persistence_version_unsupported"


class RepositoryPersistenceMigrationMismatch(RepositoryPersistenceError):
    code = "repository_persistence_migration_mismatch"


class RepositoryPersistenceRecordNotFound(RepositoryPersistenceError):
    code = "repository_persistence_record_not_found"


class RepositoryPersistenceUnavailable(RepositoryPersistenceError):
    code = "repository_persistence_unavailable"


class RepositoryAdapterError(RepositoryDomainError):
    code = "repository_adapter_error"


class RepositoryAdapterUnavailable(RepositoryAdapterError):
    code = "repository_adapter_unavailable"


class RepositoryAdapterBoundaryViolation(RepositoryAdapterError):
    code = "repository_adapter_boundary_violation"


class RepositoryCanonicalizationError(RepositoryDomainError):
    code = "repository_canonicalization_error"


class UnsupportedRepositoryFormat(RepositoryDomainError):
    code = "unsupported_repository_format"
