"""Pure correspondence and contradiction assessment for neutral repository facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .errors import InvalidRepositoryObservationFacts
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .models import (
    RepositoryCheckout,
    RepositoryHeadState,
    RepositoryIndexState,
    RepositoryObservation,
    RepositoryPath,
    RepositoryPathClassification,
    RepositoryPathObservation,
    RepositoryPlatformProfile,
    RepositoryWorkspaceState,
    RepositoryWorktree,
)
from .states import (
    RepositoryCorrespondence,
    RepositoryEntryStatus,
    RepositoryHeadKind,
    RepositoryIndexPresence,
    RepositoryObservationCompleteness,
    RepositoryObservationDimension,
    RepositoryObservationOutcome,
    RepositoryPresence,
    RepositoryTopology,
    RepositoryWorkspaceStatus,
)

_SOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


class RepositoryObservationDiagnosticCode(StrEnum):
    REPOSITORY_ABSENT = "repository_absent"
    REPOSITORY_IDENTITY_MISMATCH = "repository_identity_mismatch"
    CHECKOUT_BINDING_MISMATCH = "checkout_binding_mismatch"
    WORKTREE_BINDING_MISMATCH = "worktree_binding_mismatch"
    PLATFORM_PROFILE_MISMATCH = "platform_profile_mismatch"
    PATH_BINDING_MISMATCH = "path_binding_mismatch"
    HEAD_BRANCH_CONTRADICTION = "head_branch_contradiction"
    HEAD_OBJECT_CONTRADICTION = "head_object_contradiction"
    CLEAN_WITH_CHANGES = "clean_with_changes"
    CLEAN_WITH_CONFLICTS = "clean_with_conflicts"
    INDEX_ABSENT_WITH_STAGING = "index_absent_with_staging"
    PATH_FACT_CONFLICT = "path_fact_conflict"
    SPARSE_EXCLUDED_OBSERVED = "sparse_excluded_observed"
    TOPOLOGY_IMPLICIT_TRAVERSAL = "topology_implicit_traversal"
    DIMENSION_PARTIAL = "dimension_partial"
    DIMENSION_UNAVAILABLE = "dimension_unavailable"
    DIMENSION_UNSUPPORTED = "dimension_unsupported"
    DIMENSION_UNKNOWN = "dimension_unknown"
    NOT_REQUIRED_INVALID = "not_required_invalid"
    CLEAN_WITH_INCOMPLETE_OBSERVATION = "clean_with_incomplete_observation"


@dataclass(frozen=True, slots=True)
class RepositoryObservationSource:
    source_id: str
    source_version: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not _SOURCE.fullmatch(self.source_id) or not _SOURCE.fullmatch(self.source_version):
            raise InvalidRepositoryObservationFacts("observation source is invalid")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise InvalidRepositoryObservationFacts("occurrence timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RepositoryDimensionCompleteness:
    dimension: RepositoryObservationDimension
    state: RepositoryObservationCompleteness


@dataclass(frozen=True, slots=True)
class RepositoryObservedEntry:
    path: RepositoryPath
    classification: RepositoryPathClassification
    status: RepositoryEntryStatus
    content_observed: bool
    descendants_observed: bool = False


@dataclass(frozen=True, slots=True)
class RepositoryObservationRequest:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryObservationFacts:
    source: RepositoryObservationSource
    repository_presence: RepositoryPresence
    repository_id: RepositoryIdentity | None
    checkout: RepositoryCheckout | None
    worktree: RepositoryWorktree | None
    platform_profile: RepositoryPlatformProfile | None
    head: RepositoryHeadState | None
    branch_reference: str | None
    object_reference: str | None
    index: RepositoryIndexState | None
    workspace_status: RepositoryWorkspaceStatus
    entries: tuple[RepositoryObservedEntry, ...]
    staged_paths: tuple[RepositoryPath, ...]
    completeness: tuple[RepositoryDimensionCompleteness, ...]

    def __post_init__(self) -> None:
        dimensions = [item.dimension for item in self.completeness]
        if len(set(dimensions)) != len(dimensions):
            raise InvalidRepositoryObservationFacts("dimension completeness must be unique")
        object.__setattr__(
            self,
            "completeness",
            tuple(sorted(self.completeness, key=lambda item: item.dimension.value)),
        )
        object.__setattr__(
            self,
            "entries",
            tuple(
                sorted(
                    self.entries,
                    key=lambda item: (
                        item.path.value,
                        item.classification.tracking.value,
                        item.classification.material_role.value,
                        item.classification.sensitivity.value,
                        item.classification.topology.value,
                        item.status.value,
                        item.content_observed,
                        item.descendants_observed,
                    ),
                )
            ),
        )
        object.__setattr__(
            self,
            "staged_paths",
            tuple(sorted(self.staged_paths, key=lambda item: item.value)),
        )


@dataclass(frozen=True, slots=True, order=True)
class RepositoryObservationDiagnostic:
    dimension: RepositoryObservationDimension
    code: RepositoryObservationDiagnosticCode


@dataclass(frozen=True, slots=True)
class RepositoryDimensionAssessment:
    dimension: RepositoryObservationDimension
    completeness: RepositoryObservationCompleteness
    correspondence: RepositoryCorrespondence


@dataclass(frozen=True, slots=True)
class RepositoryObservationAssessment:
    outcome: RepositoryObservationOutcome
    dimensions: tuple[RepositoryDimensionAssessment, ...]
    diagnostics: tuple[RepositoryObservationDiagnostic, ...]
    conflicts: tuple[RepositoryObservationDiagnosticCode, ...]
    unsupported: tuple[RepositoryObservationDimension, ...]

    def __post_init__(self) -> None:
        if len({item.dimension for item in self.dimensions}) != len(self.dimensions):
            raise InvalidRepositoryObservationFacts("assessment dimensions must be unique")
        object.__setattr__(
            self, "dimensions", tuple(sorted(self.dimensions, key=lambda item: item.dimension.value))
        )
        object.__setattr__(self, "diagnostics", tuple(sorted(set(self.diagnostics))))
        object.__setattr__(self, "conflicts", tuple(sorted(set(self.conflicts), key=str)))
        object.__setattr__(self, "unsupported", tuple(sorted(set(self.unsupported), key=str)))


@dataclass(frozen=True, slots=True)
class RepositoryObservationResult:
    request_fingerprint: RepositoryFingerprint
    source_id: str
    source_version: str
    occurred_at: datetime
    assessment: RepositoryObservationAssessment
    observation: RepositoryObservation | None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise InvalidRepositoryObservationFacts("result occurrence timestamp must be aware")
        if not _SOURCE.fullmatch(self.source_id) or not _SOURCE.fullmatch(self.source_version):
            raise InvalidRepositoryObservationFacts("result source is invalid")

    def semantic_content(self) -> object:
        """Return semantic content; occurrence time is intentionally excluded."""

        return (
            self.request_fingerprint,
            self.source_id,
            self.source_version,
            self.assessment,
            self.observation,
        )

    def canonical_value(self) -> object:
        return self.semantic_content()

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self.semantic_content())


class RepositoryObservationService:
    """Assess supplied facts only; never discover or mutate repository state."""

    _dimensions = tuple(RepositoryObservationDimension)

    def assess(
        self, request: RepositoryObservationRequest, facts: RepositoryObservationFacts
    ) -> RepositoryObservationResult:
        completeness = {item.dimension: item.state for item in facts.completeness}
        diagnostics: set[RepositoryObservationDiagnostic] = set()
        correspondence = self._correspondence(request, facts, diagnostics)
        self._validate_completeness(request, completeness, diagnostics)
        self._contradictions(facts, completeness, diagnostics)

        dimensions = tuple(
            RepositoryDimensionAssessment(
                dimension,
                completeness.get(dimension, RepositoryObservationCompleteness.UNKNOWN),
                correspondence.get(dimension, RepositoryCorrespondence.UNKNOWN),
            )
            for dimension in self._dimensions
        )
        ordered_diagnostics = tuple(sorted(diagnostics))
        conflicts = tuple(
            sorted(
                {
                    item.code
                    for item in ordered_diagnostics
                    if item.code
                    in {
                        RepositoryObservationDiagnosticCode.HEAD_BRANCH_CONTRADICTION,
                        RepositoryObservationDiagnosticCode.HEAD_OBJECT_CONTRADICTION,
                        RepositoryObservationDiagnosticCode.CLEAN_WITH_CHANGES,
                        RepositoryObservationDiagnosticCode.CLEAN_WITH_CONFLICTS,
                        RepositoryObservationDiagnosticCode.INDEX_ABSENT_WITH_STAGING,
                        RepositoryObservationDiagnosticCode.PATH_FACT_CONFLICT,
                        RepositoryObservationDiagnosticCode.SPARSE_EXCLUDED_OBSERVED,
                        RepositoryObservationDiagnosticCode.TOPOLOGY_IMPLICIT_TRAVERSAL,
                    }
                },
                key=str,
            )
        )
        unsupported = tuple(
            sorted(
                (
                    dimension
                    for dimension, state in completeness.items()
                    if state is RepositoryObservationCompleteness.UNSUPPORTED
                ),
                key=str,
            )
        )
        outcome = self._outcome(ordered_diagnostics, completeness)
        observation = self._observation(request, facts, outcome)
        assessment = RepositoryObservationAssessment(
            outcome, dimensions, ordered_diagnostics, conflicts, unsupported
        )
        return RepositoryObservationResult(
            request.fingerprint,
            facts.source.source_id,
            facts.source.source_version,
            facts.source.occurred_at,
            assessment,
            observation,
        )

    @classmethod
    def _correspondence(
        cls,
        request: RepositoryObservationRequest,
        facts: RepositoryObservationFacts,
        diagnostics: set[RepositoryObservationDiagnostic],
    ) -> dict[RepositoryObservationDimension, RepositoryCorrespondence]:
        result: dict[RepositoryObservationDimension, RepositoryCorrespondence] = {}

        def compare(
            dimension: RepositoryObservationDimension,
            matches: bool,
            code: RepositoryObservationDiagnosticCode,
        ) -> None:
            result[dimension] = (
                RepositoryCorrespondence.MATCH if matches else RepositoryCorrespondence.MISMATCH
            )
            if not matches:
                diagnostics.add(RepositoryObservationDiagnostic(dimension, code))

        compare(
            RepositoryObservationDimension.REPOSITORY,
            facts.repository_presence is RepositoryPresence.PRESENT
            and facts.repository_id == request.repository_id,
            RepositoryObservationDiagnosticCode.REPOSITORY_IDENTITY_MISMATCH,
        )
        if facts.repository_presence is RepositoryPresence.ABSENT:
            diagnostics.add(
                RepositoryObservationDiagnostic(
                    RepositoryObservationDimension.REPOSITORY,
                    RepositoryObservationDiagnosticCode.REPOSITORY_ABSENT,
                )
            )
        compare(
            RepositoryObservationDimension.CHECKOUT,
            facts.checkout is not None
            and facts.checkout.identity == request.checkout_id
            and facts.checkout.repository_id == request.repository_id,
            RepositoryObservationDiagnosticCode.CHECKOUT_BINDING_MISMATCH,
        )
        worktree_matches = (
            facts.worktree is None
            if request.worktree_id is None
            else facts.worktree is not None
            and facts.worktree.identity == request.worktree_id
            and facts.worktree.checkout_id == request.checkout_id
            and facts.worktree.repository_id == request.repository_id
        )
        compare(
            RepositoryObservationDimension.WORKTREE,
            worktree_matches,
            RepositoryObservationDiagnosticCode.WORKTREE_BINDING_MISMATCH,
        )
        compare(
            RepositoryObservationDimension.PLATFORM,
            facts.platform_profile == request.platform_profile,
            RepositoryObservationDiagnosticCode.PLATFORM_PROFILE_MISMATCH,
        )
        return result

    @classmethod
    def _validate_completeness(
        cls,
        request: RepositoryObservationRequest,
        completeness: dict[RepositoryObservationDimension, RepositoryObservationCompleteness],
        diagnostics: set[RepositoryObservationDiagnostic],
    ) -> None:
        for dimension in cls._dimensions:
            state = completeness.get(dimension, RepositoryObservationCompleteness.UNKNOWN)
            if state is RepositoryObservationCompleteness.COMPLETE:
                continue
            if state is RepositoryObservationCompleteness.NOT_REQUIRED:
                if dimension is RepositoryObservationDimension.WORKTREE and request.worktree_id is None:
                    continue
                diagnostics.add(
                    RepositoryObservationDiagnostic(
                        dimension, RepositoryObservationDiagnosticCode.NOT_REQUIRED_INVALID
                    )
                )
                continue
            code = {
                RepositoryObservationCompleteness.PARTIAL: RepositoryObservationDiagnosticCode.DIMENSION_PARTIAL,
                RepositoryObservationCompleteness.UNAVAILABLE: RepositoryObservationDiagnosticCode.DIMENSION_UNAVAILABLE,
                RepositoryObservationCompleteness.UNSUPPORTED: RepositoryObservationDiagnosticCode.DIMENSION_UNSUPPORTED,
                RepositoryObservationCompleteness.UNKNOWN: RepositoryObservationDiagnosticCode.DIMENSION_UNKNOWN,
            }[state]
            diagnostics.add(RepositoryObservationDiagnostic(dimension, code))

    @classmethod
    def _contradictions(
        cls,
        facts: RepositoryObservationFacts,
        completeness: dict[RepositoryObservationDimension, RepositoryObservationCompleteness],
        diagnostics: set[RepositoryObservationDiagnostic],
    ) -> None:
        def add(
            dimension: RepositoryObservationDimension,
            code: RepositoryObservationDiagnosticCode,
        ) -> None:
            diagnostics.add(RepositoryObservationDiagnostic(dimension, code))

        if facts.head is not None:
            if facts.head.kind is RepositoryHeadKind.DETACHED and facts.branch_reference is not None:
                add(
                    RepositoryObservationDimension.HEAD,
                    RepositoryObservationDiagnosticCode.HEAD_BRANCH_CONTRADICTION,
                )
            if facts.head.branch_name != facts.branch_reference:
                add(
                    RepositoryObservationDimension.HEAD,
                    RepositoryObservationDiagnosticCode.HEAD_BRANCH_CONTRADICTION,
                )
            if facts.head.commit_id != facts.object_reference:
                add(
                    RepositoryObservationDimension.HEAD,
                    RepositoryObservationDiagnosticCode.HEAD_OBJECT_CONTRADICTION,
                )
        if facts.index is not None and facts.index.presence is RepositoryIndexPresence.ABSENT:
            if facts.staged_paths:
                add(
                    RepositoryObservationDimension.INDEX,
                    RepositoryObservationDiagnosticCode.INDEX_ABSENT_WITH_STAGING,
                )
        changed = any(
            entry.status
            in {
                RepositoryEntryStatus.MODIFIED,
                RepositoryEntryStatus.ADDED,
                RepositoryEntryStatus.DELETED,
                RepositoryEntryStatus.CONFLICTED,
            }
            for entry in facts.entries
        )
        conflicted = any(
            entry.status is RepositoryEntryStatus.CONFLICTED for entry in facts.entries
        )
        if facts.workspace_status is RepositoryWorkspaceStatus.CLEAN and changed:
            add(
                RepositoryObservationDimension.WORKSPACE,
                RepositoryObservationDiagnosticCode.CLEAN_WITH_CHANGES,
            )
        if facts.workspace_status is RepositoryWorkspaceStatus.CLEAN and conflicted:
            add(
                RepositoryObservationDimension.WORKSPACE,
                RepositoryObservationDiagnosticCode.CLEAN_WITH_CONFLICTS,
            )
        if facts.workspace_status is RepositoryWorkspaceStatus.CLEAN and any(
            completeness.get(dimension, RepositoryObservationCompleteness.UNKNOWN)
            not in {
                RepositoryObservationCompleteness.COMPLETE,
                RepositoryObservationCompleteness.NOT_REQUIRED,
            }
            for dimension in cls._dimensions
        ):
            add(
                RepositoryObservationDimension.WORKSPACE,
                RepositoryObservationDiagnosticCode.CLEAN_WITH_INCOMPLETE_OBSERVATION,
            )
        by_path: dict[object, RepositoryObservedEntry] = {}
        for entry in facts.entries:
            key = entry.path.canonical_value().__repr__()
            previous = by_path.get(key)
            if previous is not None and previous != entry:
                add(
                    RepositoryObservationDimension.PATHS,
                    RepositoryObservationDiagnosticCode.PATH_FACT_CONFLICT,
                )
            by_path[key] = entry
            if (
                entry.path.checkout_id != facts.checkout.identity
                if facts.checkout is not None
                else True
            ) or (
                entry.path.worktree_id
                != (facts.worktree.identity if facts.worktree is not None else None)
            ) or entry.path.profile != facts.platform_profile:
                add(
                    RepositoryObservationDimension.PATHS,
                    RepositoryObservationDiagnosticCode.PATH_BINDING_MISMATCH,
                )
            topology = entry.classification.topology
            if topology is RepositoryTopology.SPARSE_EXCLUDED and entry.content_observed:
                add(
                    RepositoryObservationDimension.TOPOLOGY,
                    RepositoryObservationDiagnosticCode.SPARSE_EXCLUDED_OBSERVED,
                )
            if topology in {
                RepositoryTopology.SUBMODULE,
                RepositoryTopology.NESTED_REPOSITORY,
            } and entry.descendants_observed:
                add(
                    RepositoryObservationDimension.TOPOLOGY,
                    RepositoryObservationDiagnosticCode.TOPOLOGY_IMPLICIT_TRAVERSAL,
                )
        for path in facts.staged_paths:
            if (
                path.checkout_id != (facts.checkout.identity if facts.checkout is not None else None)
                or path.worktree_id
                != (facts.worktree.identity if facts.worktree is not None else None)
                or path.profile != facts.platform_profile
            ):
                add(
                    RepositoryObservationDimension.PATHS,
                    RepositoryObservationDiagnosticCode.PATH_BINDING_MISMATCH,
                )

    @staticmethod
    def _outcome(
        diagnostics: tuple[RepositoryObservationDiagnostic, ...],
        completeness: dict[RepositoryObservationDimension, RepositoryObservationCompleteness],
    ) -> RepositoryObservationOutcome:
        conflict_codes = {
            RepositoryObservationDiagnosticCode.HEAD_BRANCH_CONTRADICTION,
            RepositoryObservationDiagnosticCode.HEAD_OBJECT_CONTRADICTION,
            RepositoryObservationDiagnosticCode.CLEAN_WITH_CHANGES,
            RepositoryObservationDiagnosticCode.CLEAN_WITH_CONFLICTS,
            RepositoryObservationDiagnosticCode.INDEX_ABSENT_WITH_STAGING,
            RepositoryObservationDiagnosticCode.PATH_FACT_CONFLICT,
            RepositoryObservationDiagnosticCode.SPARSE_EXCLUDED_OBSERVED,
            RepositoryObservationDiagnosticCode.TOPOLOGY_IMPLICIT_TRAVERSAL,
        }
        if any(item.code in conflict_codes for item in diagnostics):
            return RepositoryObservationOutcome.CONTRADICTORY
        if any(
            assessment.code
            in {
                RepositoryObservationDiagnosticCode.REPOSITORY_IDENTITY_MISMATCH,
                RepositoryObservationDiagnosticCode.CHECKOUT_BINDING_MISMATCH,
                RepositoryObservationDiagnosticCode.WORKTREE_BINDING_MISMATCH,
                RepositoryObservationDiagnosticCode.PLATFORM_PROFILE_MISMATCH,
                RepositoryObservationDiagnosticCode.PATH_BINDING_MISMATCH,
                RepositoryObservationDiagnosticCode.NOT_REQUIRED_INVALID,
            }
            for assessment in diagnostics
        ):
            return RepositoryObservationOutcome.MISMATCH
        states = set(completeness.values())
        if RepositoryObservationCompleteness.UNAVAILABLE in states:
            return RepositoryObservationOutcome.UNAVAILABLE
        if RepositoryObservationCompleteness.UNSUPPORTED in states:
            return RepositoryObservationOutcome.UNSUPPORTED
        if states & {
            RepositoryObservationCompleteness.PARTIAL,
            RepositoryObservationCompleteness.UNKNOWN,
        }:
            return RepositoryObservationOutcome.INCOMPLETE
        return RepositoryObservationOutcome.SATISFIED

    @staticmethod
    def _observation(
        request: RepositoryObservationRequest,
        facts: RepositoryObservationFacts,
        outcome: RepositoryObservationOutcome,
    ) -> RepositoryObservation | None:
        if (
            outcome is not RepositoryObservationOutcome.SATISFIED
            or facts.head is None
            or facts.index is None
        ):
            return None
        unique_entries = {
            entry.path.canonical_value().__repr__(): RepositoryPathObservation(
                entry.path, entry.classification
            )
            for entry in facts.entries
        }
        return RepositoryObservation(
            request.repository_id,
            request.checkout_id,
            request.worktree_id,
            facts.head,
            facts.index,
            RepositoryWorkspaceState(
                facts.workspace_status, RepositoryObservationCompleteness.COMPLETE
            ),
            RepositoryObservationCompleteness.COMPLETE,
            tuple(unique_entries.values()),
        )
