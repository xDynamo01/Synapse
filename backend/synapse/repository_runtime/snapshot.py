"""Pure construction of immutable repository snapshots from supplied fingerprints."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .classification import RepositoryPathCatalog, RepositoryPathDiagnosticCode
from .errors import InvalidRepositorySnapshotModel
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .models import (
    RepositoryHeadState,
    RepositoryIndexState,
    RepositoryPath,
    RepositoryPathClassification,
    RepositoryPlatformProfile,
    RepositoryWorkspaceState,
)
from .observation import RepositoryObservationResult
from .states import (
    RepositoryObservationCompleteness,
    RepositoryResourceKind,
    RepositorySnapshotDimension,
    RepositorySparseCheckoutState,
    RepositoryTopology,
)

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


class RepositorySnapshotDiagnosticCode(StrEnum):
    OBSERVATION_UNAVAILABLE = "observation_unavailable"
    OBSERVATION_FINGERPRINT_MISMATCH = "observation_fingerprint_mismatch"
    CATALOG_FINGERPRINT_MISMATCH = "catalog_fingerprint_mismatch"
    CATALOG_OBSERVATION_MISMATCH = "catalog_observation_mismatch"
    REPOSITORY_IDENTITY_MISMATCH = "repository_identity_mismatch"
    CHECKOUT_IDENTITY_MISMATCH = "checkout_identity_mismatch"
    WORKTREE_IDENTITY_MISMATCH = "worktree_identity_mismatch"
    PLATFORM_PROFILE_MISMATCH = "platform_profile_mismatch"
    HEAD_STATE_MISMATCH = "head_state_mismatch"
    OBJECT_REFERENCE_MISMATCH = "object_reference_mismatch"
    BRANCH_REFERENCE_MISMATCH = "branch_reference_mismatch"
    INDEX_STATE_MISMATCH = "index_state_mismatch"
    WORKSPACE_STATE_MISMATCH = "workspace_state_mismatch"
    SPARSE_STATE_CONTRADICTION = "sparse_state_contradiction"
    PATH_FACT_MISSING = "path_fact_missing"
    PATH_FACT_DUPLICATE = "path_fact_duplicate"
    PATH_FACT_OUTSIDE_CATALOG = "path_fact_outside_catalog"
    CONTENT_FINGERPRINT_CONFLICT = "content_fingerprint_conflict"
    CONTENT_FINGERPRINT_REQUIRED = "content_fingerprint_required"
    FINGERPRINT_ALGORITHM_UNSUPPORTED = "fingerprint_algorithm_unsupported"
    PATH_COLLISION = "path_collision"
    CATALOG_INCOMPLETE = "catalog_incomplete"
    COMPLETENESS_INCONSISTENT = "completeness_inconsistent"
    REQUIRED_DIMENSION_INCOMPLETE = "required_dimension_incomplete"


@dataclass(frozen=True, slots=True, order=True)
class RepositorySnapshotDimensionState:
    dimension: RepositorySnapshotDimension
    completeness: RepositoryObservationCompleteness


@dataclass(frozen=True, slots=True)
class RepositorySnapshotPolicy:
    policy_id: str
    policy_version: str
    required_dimensions: tuple[RepositorySnapshotDimension, ...]
    accepted_fingerprint_schemes: tuple[tuple[str, str], ...] = (("sha256", "v1"),)
    require_regular_file_content: bool = True

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.policy_id) or not _REFERENCE.fullmatch(self.policy_version):
            raise InvalidRepositorySnapshotModel("snapshot policy identity is invalid")
        required = tuple(sorted(set(self.required_dimensions), key=str))
        schemes = tuple(sorted(set(self.accepted_fingerprint_schemes)))
        if not required or len(required) != len(self.required_dimensions):
            raise InvalidRepositorySnapshotModel("required dimensions must be unique and non-empty")
        if not schemes or any(
            not _REFERENCE.fullmatch(algorithm) or not _REFERENCE.fullmatch(version)
            for algorithm, version in schemes
        ):
            raise InvalidRepositorySnapshotModel("fingerprint schemes are invalid")
        object.__setattr__(self, "required_dimensions", required)
        object.__setattr__(self, "accepted_fingerprint_schemes", schemes)


@dataclass(frozen=True, slots=True)
class RepositoryPathFingerprintFact:
    path_fingerprint: RepositoryFingerprint
    content_fingerprint: RepositoryFingerprint | None
    metadata_fingerprint: RepositoryFingerprint | None
    content_length: int | None
    fingerprint_algorithm: str
    fingerprint_version: str
    completeness: RepositoryObservationCompleteness
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if (
            not _REFERENCE.fullmatch(self.fingerprint_algorithm)
            or not _REFERENCE.fullmatch(self.fingerprint_version)
        ):
            raise InvalidRepositorySnapshotModel("fingerprint scheme is invalid")
        if self.content_length is not None and self.content_length < 0:
            raise InvalidRepositorySnapshotModel("content length cannot be negative")
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositorySnapshotModel("occurrence metadata is invalid")
        object.__setattr__(self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata))))

    def semantic_content(self) -> object:
        return (
            self.path_fingerprint,
            self.content_fingerprint,
            self.metadata_fingerprint,
            self.content_length,
            self.fingerprint_algorithm,
            self.fingerprint_version,
            self.completeness,
        )


@dataclass(frozen=True, slots=True)
class RepositorySnapshotRequest:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    observation_fingerprint: RepositoryFingerprint
    path_catalog_fingerprint: RepositoryFingerprint
    head: RepositoryHeadState
    object_reference: str | None
    branch_reference: str | None
    index: RepositoryIndexState
    workspace: RepositoryWorkspaceState
    sparse_checkout: RepositorySparseCheckoutState
    completeness: tuple[RepositorySnapshotDimensionState, ...]
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        dimensions = tuple(sorted(self.completeness))
        if len({item.dimension for item in dimensions}) != len(dimensions):
            raise InvalidRepositorySnapshotModel("snapshot completeness dimensions must be unique")
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositorySnapshotModel("occurrence metadata is invalid")
        object.__setattr__(self, "completeness", dimensions)
        object.__setattr__(self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata))))

    def semantic_content(self) -> object:
        return (
            self.repository_id,
            self.checkout_id,
            self.worktree_id,
            self.platform_profile,
            self.observation_fingerprint,
            self.path_catalog_fingerprint,
            self.head,
            self.object_reference,
            self.branch_reference,
            self.index,
            self.workspace,
            self.sparse_checkout,
            self.completeness,
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class RepositorySnapshotEntry:
    path: RepositoryPath
    path_fingerprint: RepositoryFingerprint
    resource_kind: RepositoryResourceKind
    topology: RepositoryTopology
    classification: RepositoryPathClassification
    content_fingerprint: RepositoryFingerprint | None
    metadata_fingerprint: RepositoryFingerprint | None
    content_length: int | None
    fingerprint_algorithm: str
    fingerprint_version: str
    completeness: RepositoryObservationCompleteness


@dataclass(frozen=True, slots=True)
class RepositorySnapshotDiagnostic:
    dimension: RepositorySnapshotDimension
    code: RepositorySnapshotDiagnosticCode
    path_fingerprint: RepositoryFingerprint | None = None


def _diagnostic_key(item: RepositorySnapshotDiagnostic) -> tuple[str, str, str]:
    return (
        item.dimension.value,
        item.code.value,
        item.path_fingerprint.value if item.path_fingerprint is not None else "",
    )


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    observation_fingerprint: RepositoryFingerprint
    path_catalog_fingerprint: RepositoryFingerprint
    head: RepositoryHeadState
    object_reference: str | None
    branch_reference: str | None
    index: RepositoryIndexState
    workspace: RepositoryWorkspaceState
    sparse_checkout: RepositorySparseCheckoutState
    completeness: RepositoryObservationCompleteness
    dimensions: tuple[RepositorySnapshotDimensionState, ...]
    entries: tuple[RepositorySnapshotEntry, ...]
    repository_metadata_fingerprint: RepositoryFingerprint
    head_fingerprint: RepositoryFingerprint
    index_fingerprint: RepositoryFingerprint
    source_tree_fingerprint: RepositoryFingerprint
    workspace_fingerprint: RepositoryFingerprint

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimensions", tuple(sorted(self.dimensions)))
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda item: item.path.value)))

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositorySnapshotResult:
    request_fingerprint: RepositoryFingerprint
    snapshot: RepositorySnapshot | None
    diagnostics: tuple[RepositorySnapshotDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "diagnostics",
            tuple(sorted(set(self.diagnostics), key=_diagnostic_key)),
        )

    def canonical_value(self) -> object:
        return (self.request_fingerprint, self.snapshot, self.diagnostics)

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self.canonical_value())


class RepositorySnapshotService:
    """Validate and compose supplied facts; never read or hash repository resources."""

    _blocking = {
        RepositorySnapshotDiagnosticCode.OBSERVATION_UNAVAILABLE,
        RepositorySnapshotDiagnosticCode.OBSERVATION_FINGERPRINT_MISMATCH,
        RepositorySnapshotDiagnosticCode.CATALOG_FINGERPRINT_MISMATCH,
        RepositorySnapshotDiagnosticCode.CATALOG_OBSERVATION_MISMATCH,
        RepositorySnapshotDiagnosticCode.REPOSITORY_IDENTITY_MISMATCH,
        RepositorySnapshotDiagnosticCode.CHECKOUT_IDENTITY_MISMATCH,
        RepositorySnapshotDiagnosticCode.WORKTREE_IDENTITY_MISMATCH,
        RepositorySnapshotDiagnosticCode.PLATFORM_PROFILE_MISMATCH,
        RepositorySnapshotDiagnosticCode.HEAD_STATE_MISMATCH,
        RepositorySnapshotDiagnosticCode.OBJECT_REFERENCE_MISMATCH,
        RepositorySnapshotDiagnosticCode.BRANCH_REFERENCE_MISMATCH,
        RepositorySnapshotDiagnosticCode.INDEX_STATE_MISMATCH,
        RepositorySnapshotDiagnosticCode.WORKSPACE_STATE_MISMATCH,
        RepositorySnapshotDiagnosticCode.SPARSE_STATE_CONTRADICTION,
    }

    def build(
        self,
        request: RepositorySnapshotRequest,
        policy: RepositorySnapshotPolicy,
        observation_result: RepositoryObservationResult,
        path_catalog: RepositoryPathCatalog,
        path_facts: tuple[RepositoryPathFingerprintFact, ...],
    ) -> RepositorySnapshotResult:
        diagnostics: set[RepositorySnapshotDiagnostic] = set()

        def add(
            dimension: RepositorySnapshotDimension,
            code: RepositorySnapshotDiagnosticCode,
            path: RepositoryFingerprint | None = None,
        ) -> None:
            diagnostics.add(RepositorySnapshotDiagnostic(dimension, code, path))

        observation = observation_result.observation
        if observation is None:
            add(
                RepositorySnapshotDimension.REPOSITORY_METADATA,
                RepositorySnapshotDiagnosticCode.OBSERVATION_UNAVAILABLE,
            )
        if request.observation_fingerprint != observation_result.fingerprint:
            add(
                RepositorySnapshotDimension.REPOSITORY_METADATA,
                RepositorySnapshotDiagnosticCode.OBSERVATION_FINGERPRINT_MISMATCH,
            )
        if request.path_catalog_fingerprint != path_catalog.fingerprint:
            add(
                RepositorySnapshotDimension.PATH_CATALOG,
                RepositorySnapshotDiagnosticCode.CATALOG_FINGERPRINT_MISMATCH,
            )
        if path_catalog.observation_fingerprint != observation_result.fingerprint:
            add(
                RepositorySnapshotDimension.PATH_CATALOG,
                RepositorySnapshotDiagnosticCode.CATALOG_OBSERVATION_MISMATCH,
            )
        if path_catalog.completeness is not RepositoryObservationCompleteness.COMPLETE:
            add(
                RepositorySnapshotDimension.PATH_CATALOG,
                RepositorySnapshotDiagnosticCode.CATALOG_INCOMPLETE,
            )
        if any(
            item.code is RepositoryPathDiagnosticCode.PATH_COLLISION
            for item in path_catalog.diagnostics
        ):
            add(
                RepositorySnapshotDimension.PATH_CATALOG,
                RepositorySnapshotDiagnosticCode.PATH_COLLISION,
            )
        self._identity_diagnostics(request, path_catalog, observation, add)

        if observation is not None:
            if request.head != observation.head:
                add(RepositorySnapshotDimension.HEAD, RepositorySnapshotDiagnosticCode.HEAD_STATE_MISMATCH)
            if request.object_reference != observation.head.commit_id:
                add(
                    RepositorySnapshotDimension.HEAD,
                    RepositorySnapshotDiagnosticCode.OBJECT_REFERENCE_MISMATCH,
                )
            if request.branch_reference != observation.head.branch_name:
                add(
                    RepositorySnapshotDimension.HEAD,
                    RepositorySnapshotDiagnosticCode.BRANCH_REFERENCE_MISMATCH,
                )
            if request.index != observation.index:
                add(RepositorySnapshotDimension.INDEX, RepositorySnapshotDiagnosticCode.INDEX_STATE_MISMATCH)
            if request.workspace != observation.workspace:
                add(
                    RepositorySnapshotDimension.WORKSPACE,
                    RepositorySnapshotDiagnosticCode.WORKSPACE_STATE_MISMATCH,
                )

        has_sparse = any(
            entry.classification.topology is RepositoryTopology.SPARSE_EXCLUDED
            for entry in path_catalog.entries
        )
        if has_sparse and request.sparse_checkout is RepositorySparseCheckoutState.DISABLED:
            add(
                RepositorySnapshotDimension.SPARSE_CHECKOUT,
                RepositorySnapshotDiagnosticCode.SPARSE_STATE_CONTRADICTION,
            )

        entries = self._entries(policy, path_catalog, path_facts, add)
        dimensions = self._dimensions(request, path_catalog, entries, diagnostics)
        declared = {item.dimension: item.completeness for item in request.completeness}
        actual = {item.dimension: item.completeness for item in dimensions}
        for dimension in RepositorySnapshotDimension:
            if declared.get(dimension, RepositoryObservationCompleteness.UNKNOWN) != actual[dimension]:
                add(dimension, RepositorySnapshotDiagnosticCode.COMPLETENESS_INCONSISTENT)
        for dimension in policy.required_dimensions:
            if actual[dimension] is not RepositoryObservationCompleteness.COMPLETE:
                add(dimension, RepositorySnapshotDiagnosticCode.REQUIRED_DIMENSION_INCOMPLETE)

        if any(item.code in self._blocking for item in diagnostics):
            return RepositorySnapshotResult(request.fingerprint, None, tuple(diagnostics))

        complete = all(
            actual[dimension] is RepositoryObservationCompleteness.COMPLETE
            for dimension in policy.required_dimensions
        ) and not diagnostics
        snapshot = RepositorySnapshot(
            request.repository_id,
            request.checkout_id,
            request.worktree_id,
            request.platform_profile,
            request.observation_fingerprint,
            request.path_catalog_fingerprint,
            request.head,
            request.object_reference,
            request.branch_reference,
            request.index,
            request.workspace,
            request.sparse_checkout,
            RepositoryObservationCompleteness.COMPLETE
            if complete
            else RepositoryObservationCompleteness.PARTIAL,
            dimensions,
            entries,
            RepositoryFingerprint.from_content(
                (request.repository_id, request.checkout_id, request.worktree_id, request.platform_profile)
            ),
            RepositoryFingerprint.from_content(
                (request.head, request.object_reference, request.branch_reference)
            ),
            RepositoryFingerprint.from_content(request.index),
            RepositoryFingerprint.from_content(entries),
            RepositoryFingerprint.from_content((request.workspace, request.sparse_checkout)),
        )
        return RepositorySnapshotResult(request.fingerprint, snapshot, tuple(diagnostics))

    @staticmethod
    def _identity_diagnostics(request, catalog, observation, add) -> None:
        sources = (catalog, observation) if observation is not None else (catalog,)
        for source in sources:
            if source.repository_id != request.repository_id:
                add(
                    RepositorySnapshotDimension.REPOSITORY_METADATA,
                    RepositorySnapshotDiagnosticCode.REPOSITORY_IDENTITY_MISMATCH,
                )
            if source.checkout_id != request.checkout_id:
                add(
                    RepositorySnapshotDimension.REPOSITORY_METADATA,
                    RepositorySnapshotDiagnosticCode.CHECKOUT_IDENTITY_MISMATCH,
                )
            if source.worktree_id != request.worktree_id:
                add(
                    RepositorySnapshotDimension.REPOSITORY_METADATA,
                    RepositorySnapshotDiagnosticCode.WORKTREE_IDENTITY_MISMATCH,
                )
        if catalog.platform_profile != request.platform_profile:
            add(
                RepositorySnapshotDimension.REPOSITORY_METADATA,
                RepositorySnapshotDiagnosticCode.PLATFORM_PROFILE_MISMATCH,
            )

    @staticmethod
    def _entries(policy, catalog, facts, add) -> tuple[RepositorySnapshotEntry, ...]:
        catalog_by_fingerprint = {
            RepositoryFingerprint.from_content(entry.path): entry for entry in catalog.entries
        }
        facts_by_path: dict[RepositoryFingerprint, list[RepositoryPathFingerprintFact]] = {}
        for fact in facts:
            facts_by_path.setdefault(fact.path_fingerprint, []).append(fact)
            if fact.path_fingerprint not in catalog_by_fingerprint:
                add(
                    RepositorySnapshotDimension.SOURCE_TREE,
                    RepositorySnapshotDiagnosticCode.PATH_FACT_OUTSIDE_CATALOG,
                    fact.path_fingerprint,
                )

        entries: list[RepositorySnapshotEntry] = []
        for path_fingerprint, catalog_entry in sorted(
            catalog_by_fingerprint.items(), key=lambda item: item[1].path.value
        ):
            candidates = facts_by_path.get(path_fingerprint, [])
            if not candidates:
                add(
                    RepositorySnapshotDimension.SOURCE_TREE,
                    RepositorySnapshotDiagnosticCode.PATH_FACT_MISSING,
                    path_fingerprint,
                )
                continue
            primary = min(candidates, key=lambda item: repr(item.semantic_content()))
            if len(candidates) > 1:
                add(
                    RepositorySnapshotDimension.SOURCE_TREE,
                    RepositorySnapshotDiagnosticCode.PATH_FACT_DUPLICATE,
                    path_fingerprint,
                )
                if len({item.content_fingerprint for item in candidates}) > 1:
                    add(
                        RepositorySnapshotDimension.SOURCE_TREE,
                        RepositorySnapshotDiagnosticCode.CONTENT_FINGERPRINT_CONFLICT,
                        path_fingerprint,
                    )
            if (
                primary.fingerprint_algorithm,
                primary.fingerprint_version,
            ) not in policy.accepted_fingerprint_schemes:
                add(
                    RepositorySnapshotDimension.SOURCE_TREE,
                    RepositorySnapshotDiagnosticCode.FINGERPRINT_ALGORITHM_UNSUPPORTED,
                    path_fingerprint,
                )
            topology = catalog_entry.classification.topology
            content_required = (
                policy.require_regular_file_content
                and catalog_entry.resource_kind is RepositoryResourceKind.FILE
                and topology is RepositoryTopology.REGULAR
            )
            if content_required and primary.content_fingerprint is None:
                add(
                    RepositorySnapshotDimension.SOURCE_TREE,
                    RepositorySnapshotDiagnosticCode.CONTENT_FINGERPRINT_REQUIRED,
                    path_fingerprint,
                )
            complete = (
                primary.completeness is RepositoryObservationCompleteness.COMPLETE
                and (not content_required or primary.content_fingerprint is not None)
                and len(candidates) == 1
                and (
                    primary.fingerprint_algorithm,
                    primary.fingerprint_version,
                )
                in policy.accepted_fingerprint_schemes
            )
            entries.append(
                RepositorySnapshotEntry(
                    catalog_entry.path,
                    path_fingerprint,
                    catalog_entry.resource_kind,
                    topology,
                    catalog_entry.classification,
                    primary.content_fingerprint,
                    primary.metadata_fingerprint,
                    primary.content_length,
                    primary.fingerprint_algorithm,
                    primary.fingerprint_version,
                    RepositoryObservationCompleteness.COMPLETE
                    if complete
                    else RepositoryObservationCompleteness.PARTIAL,
                )
            )
        return tuple(entries)

    @staticmethod
    def _dimensions(request, catalog, entries, diagnostics):
        source_complete = len(entries) == len(catalog.entries) and all(
            entry.completeness is RepositoryObservationCompleteness.COMPLETE for entry in entries
        )
        source_has_error = any(
            item.dimension is RepositorySnapshotDimension.SOURCE_TREE for item in diagnostics
        )
        states = {
            RepositorySnapshotDimension.REPOSITORY_METADATA: RepositoryObservationCompleteness.COMPLETE,
            RepositorySnapshotDimension.HEAD: RepositoryObservationCompleteness.COMPLETE,
            RepositorySnapshotDimension.INDEX: RepositoryObservationCompleteness.COMPLETE,
            RepositorySnapshotDimension.SOURCE_TREE: RepositoryObservationCompleteness.COMPLETE
            if source_complete and not source_has_error
            else RepositoryObservationCompleteness.PARTIAL,
            RepositorySnapshotDimension.WORKSPACE: request.workspace.completeness,
            RepositorySnapshotDimension.PATH_CATALOG: catalog.completeness,
            RepositorySnapshotDimension.SPARSE_CHECKOUT: RepositoryObservationCompleteness.UNKNOWN
            if request.sparse_checkout is RepositorySparseCheckoutState.UNKNOWN
            else RepositoryObservationCompleteness.COMPLETE,
        }
        if any(item.code is RepositorySnapshotDiagnosticCode.PATH_COLLISION for item in diagnostics):
            states[RepositorySnapshotDimension.PATH_CATALOG] = RepositoryObservationCompleteness.PARTIAL
        return tuple(
            RepositorySnapshotDimensionState(dimension, states[dimension])
            for dimension in RepositorySnapshotDimension
        )
