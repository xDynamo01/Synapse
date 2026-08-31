"""Local opt-in Composition Root for Repository Runtime."""

from .runtime import (
    RepositoryRuntime,
    RepositoryRuntimeAdapters,
    RepositoryRuntimeBuilder,
    RepositoryRuntimeBuildError,
    RepositoryRuntimeClosedError,
    RepositoryRuntimeCloseError,
    RepositoryRuntimeConfig,
    RepositoryRuntimeFeatureDeclaration,
    RepositoryRuntimeHealth,
    RepositoryRuntimeManagedResource,
    RepositoryRuntimePersistence,
)

__all__ = [
    "RepositoryRuntime",
    "RepositoryRuntimeAdapters",
    "RepositoryRuntimeBuildError",
    "RepositoryRuntimeBuilder",
    "RepositoryRuntimeClosedError",
    "RepositoryRuntimeCloseError",
    "RepositoryRuntimeConfig",
    "RepositoryRuntimeFeatureDeclaration",
    "RepositoryRuntimeHealth",
    "RepositoryRuntimeManagedResource",
    "RepositoryRuntimePersistence",
]
