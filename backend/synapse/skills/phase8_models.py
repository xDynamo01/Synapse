from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from synapse.skills.phase2_models import (
    DataClassificationCeiling,
    EgressRequirement,
    ExternalProcessingRequirement,
    ExternalRuntimeRequirement,
    FilesystemRequirement,
    NetworkRequirement,
    ProviderModelRequirement,
    PublishedSkillVersionId,
    SkillDependencyDeclaration,
    SkillRequirementId,
    SkillSchemaVersionRequirement,
    SkillSemanticReference,
    SkillVersionConstraint,
)
from synapse.skills.phase2_serialization import canonical_json_bytes
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase3_values import SkillStoreQueryLimit, validate_store_timestamp
from synapse.skills.phase8_errors import (
    InvalidSkillCompatibilityObservation,
    InvalidSkillDependencyAnalysisProfile,
    InvalidSkillDependencyDeclaration,
    InvalidSkillDependencyGraphInput,
)

_SEMANTIC_ID = re.compile(r"^[0-9a-f]{64}$")
_MAX_GRAPH_NODES = 200
_MAX_GRAPH_EDGES = 1000


@dataclass(frozen=True, order=True)
class SkillDependencyId:
    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not self.value.startswith("dependency:")
            or not _SEMANTIC_ID.fullmatch(self.value.removeprefix("dependency:"))
        ):
            raise InvalidSkillDependencyGraphInput()

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value

    @classmethod
    def from_declaration(
        cls,
        owner: PublishedSkillVersionId,
        declaration: SkillDependencyDeclaration,
    ) -> SkillDependencyId:
        if declaration.version is not None:
            version_specification = (
                "exact",
                declaration.version.to_canonical_text(),
            )
        elif declaration.constraint is not None:
            version_specification = (
                "constraint",
                declaration.constraint.to_canonical_text(),
            )
        else:
            raise InvalidSkillDependencyDeclaration()
        projection = (
            owner.to_canonical_text(),
            declaration.skill_id.to_canonical_text(),
            version_specification,
            declaration.reason.value,
            declaration.optional,
        )
        digest = hashlib.sha256(canonical_json_bytes(projection)).hexdigest()
        return cls(f"dependency:{digest}")


@dataclass(frozen=True, order=True)
class SkillCompatibilityRequirementId:
    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not self.value.startswith("compatibility-requirement:")
            or not _SEMANTIC_ID.fullmatch(
                self.value.removeprefix("compatibility-requirement:")
            )
        ):
            raise InvalidSkillCompatibilityObservation()

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value


class SkillDependencyCardinality(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"


class SkillDependencyConstraintStatus(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"


class SkillDependencyLifecycleStatus(StrEnum):
    ELIGIBLE = "eligible"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"
    UNAVAILABLE = "unavailable"
    INCOMPLETE = "incomplete"
    INCONSISTENT = "inconsistent"


class SkillDependencyRequirementStatus(StrEnum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    INCOMPLETE = "incomplete"


class SkillCompatibilityDimension(StrEnum):
    OPERATING_PROFILE = "operating_profile"
    PLATFORM = "platform"
    PYTHON_RUNTIME = "python_runtime"
    EXTERNAL_RUNTIME = "external_runtime"
    PROVIDER = "provider"
    SCHEMA = "schema"
    SECURITY_CLASSIFICATION = "security_classification"
    SECURITY_NETWORK = "security_network"
    SECURITY_EXTERNAL_PROCESSING = "security_external_processing"
    SECURITY_FILESYSTEM = "security_filesystem"
    SECURITY_EGRESS = "security_egress"
    SECURITY_SANDBOX_PROFILE = "security_sandbox_profile"
    SECURITY_SECRET_REFERENCE = "security_secret_reference"


class SkillCompatibilityObservationStatus(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"


class SkillCompatibilityStatus(StrEnum):
    DECLARED_COMPATIBLE = "declared_compatible"
    DECLARED_INCOMPATIBLE = "declared_incompatible"
    OBSERVED_COMPATIBLE = "observed_compatible"
    OBSERVED_INCOMPATIBLE = "observed_incompatible"
    UNKNOWN = "unknown"
    CONFLICTING_INFORMATION = "conflicting_information"


class SkillDependencyDiagnosticCode(StrEnum):
    CATALOG_TRUNCATED = "catalog_truncated"
    CATALOG_UNAVAILABLE = "catalog_unavailable"
    NO_PUBLISHED_VERSION = "no_published_version"
    NO_CONSTRAINT_MATCH = "no_constraint_match"
    NO_LIFECYCLE_ELIGIBLE = "no_lifecycle_eligible"
    LIFECYCLE_UNAVAILABLE = "lifecycle_unavailable"
    LIFECYCLE_INCOMPLETE = "lifecycle_incomplete"
    LIFECYCLE_INCONSISTENT = "lifecycle_inconsistent"
    COMPATIBILITY_MISMATCH = "compatibility_mismatch"
    COMPATIBILITY_UNKNOWN = "compatibility_unknown"
    CONFLICTING_COMPATIBILITY = "conflicting_compatibility"
    OPTIONAL_DEPENDENCY_UNAVAILABLE = "optional_dependency_unavailable"
    OPTIONAL_DEPENDENCY_UNMATCHED = "optional_dependency_unmatched"
    OPTIONAL_DEPENDENCY_INCOMPATIBLE = "optional_dependency_incompatible"


class SkillDependencyDiagnosticSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INCOMPLETE = "incomplete"


class SkillDependencyAnalysisStatus(StrEnum):
    SATISFIABLE = "satisfiable"
    UNSATISFIABLE = "unsatisfiable"
    INCOMPLETE = "incomplete"
    CONFLICTING_FACTS = "conflicting_facts"


class SkillDependencyIncompleteReason(StrEnum):
    CATALOG_TRUNCATED = "catalog_truncated"
    CATALOG_UNAVAILABLE = "catalog_unavailable"
    LIFECYCLE_UNAVAILABLE = "lifecycle_unavailable"
    LIFECYCLE_INCOMPLETE = "lifecycle_incomplete"
    LIFECYCLE_INCONSISTENT = "lifecycle_inconsistent"
    COMPATIBILITY_UNKNOWN = "compatibility_unknown"
    OBSERVATION_MISSING = "observation_missing"


class SkillDependencyCycleStatus(StrEnum):
    BLOCKING = "blocking"
    ADVISORY = "advisory"


CompatibilityRequirementValue = (
    SkillRequirementId
    | SkillVersionConstraint
    | SkillSchemaVersionRequirement
    | SkillSemanticReference
    | ExternalRuntimeRequirement
    | ProviderModelRequirement
    | DataClassificationCeiling
    | NetworkRequirement
    | ExternalProcessingRequirement
    | FilesystemRequirement
    | EgressRequirement
)


@dataclass(frozen=True)
class SkillCompatibilityRequirementFact:
    requirement_id: SkillCompatibilityRequirementId
    owner: PublishedSkillVersionId
    dimension: SkillCompatibilityDimension
    value: CompatibilityRequirementValue

    def __post_init__(self) -> None:
        if (
            not isinstance(
                self.requirement_id, SkillCompatibilityRequirementId
            )
            or not isinstance(self.owner, PublishedSkillVersionId)
            or not isinstance(self.dimension, SkillCompatibilityDimension)
            or not isinstance(
                self.value,
                (
                    SkillRequirementId,
                    SkillVersionConstraint,
                    SkillSchemaVersionRequirement,
                    SkillSemanticReference,
                    ExternalRuntimeRequirement,
                    ProviderModelRequirement,
                    DataClassificationCeiling,
                    NetworkRequirement,
                    ExternalProcessingRequirement,
                    FilesystemRequirement,
                    EgressRequirement,
                ),
            )
        ):
            raise InvalidSkillCompatibilityObservation()


@dataclass(frozen=True)
class SkillCompatibilityObservation:
    subject: PublishedSkillVersionId
    dependency: PublishedSkillVersionId
    analysis_profile_ref: SkillSemanticReference
    requirement_id: SkillCompatibilityRequirementId
    status: SkillCompatibilityObservationStatus
    observer_ref: SkillSemanticReference
    observed_at: datetime
    observation_ref: SkillSemanticReference
    evidence_ref: SkillSemanticReference | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.subject, PublishedSkillVersionId)
            or not isinstance(self.dependency, PublishedSkillVersionId)
            or not isinstance(self.analysis_profile_ref, SkillSemanticReference)
            or not self.analysis_profile_ref.value.startswith("analysis-profile:")
            or not isinstance(
                self.requirement_id, SkillCompatibilityRequirementId
            )
            or not isinstance(self.status, SkillCompatibilityObservationStatus)
            or not isinstance(self.observer_ref, SkillSemanticReference)
            or not isinstance(self.observation_ref, SkillSemanticReference)
            or not self.observation_ref.value.startswith(
                "compatibility-observation:"
            )
            or (
                self.evidence_ref is not None
                and not isinstance(self.evidence_ref, SkillSemanticReference)
            )
        ):
            raise InvalidSkillCompatibilityObservation()
        try:
            validate_store_timestamp(self.observed_at)
        except (TypeError, ValueError, RuntimeError) as exc:
            raise InvalidSkillCompatibilityObservation() from exc


@dataclass(frozen=True)
class SkillDependencyCandidateFact:
    dependency_id: SkillDependencyId
    candidate: PublishedSkillVersionId
    constraint_status: SkillDependencyConstraintStatus
    lifecycle_status: SkillDependencyLifecycleStatus | None
    compatibility_status: SkillCompatibilityStatus
    compatibility_requirement_ids: tuple[SkillCompatibilityRequirementId, ...]
    observation_refs: tuple[SkillSemanticReference, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.dependency_id, SkillDependencyId)
            or not isinstance(self.candidate, PublishedSkillVersionId)
            or not isinstance(
                self.constraint_status, SkillDependencyConstraintStatus
            )
            or (
                self.lifecycle_status is not None
                and not isinstance(
                    self.lifecycle_status, SkillDependencyLifecycleStatus
                )
            )
            or not isinstance(self.compatibility_status, SkillCompatibilityStatus)
            or not _tuple_of(
                self.compatibility_requirement_ids,
                SkillCompatibilityRequirementId,
            )
            or not _tuple_of(self.observation_refs, SkillSemanticReference)
        ):
            raise InvalidSkillDependencyDeclaration()
        if (
            self.constraint_status is SkillDependencyConstraintStatus.MISMATCH
            and (
                self.lifecycle_status is not None
                or self.compatibility_status is not SkillCompatibilityStatus.UNKNOWN
                or self.compatibility_requirement_ids
                or self.observation_refs
            )
        ):
            raise InvalidSkillDependencyDeclaration()


@dataclass(frozen=True)
class SkillDependencyRequirementFact:
    dependency_id: SkillDependencyId
    owner: PublishedSkillVersionId
    declaration: SkillDependencyDeclaration
    cardinality: SkillDependencyCardinality
    matching_candidates: tuple[PublishedSkillVersionId, ...]
    eligible_candidates: tuple[PublishedSkillVersionId, ...]
    status: SkillDependencyRequirementStatus

    def __post_init__(self) -> None:
        if (
            not isinstance(self.dependency_id, SkillDependencyId)
            or not isinstance(self.owner, PublishedSkillVersionId)
            or not isinstance(self.declaration, SkillDependencyDeclaration)
            or not isinstance(self.cardinality, SkillDependencyCardinality)
            or not _tuple_of(
                self.matching_candidates, PublishedSkillVersionId
            )
            or not _tuple_of(
                self.eligible_candidates, PublishedSkillVersionId
            )
            or not isinstance(self.status, SkillDependencyRequirementStatus)
            or not set(self.eligible_candidates).issubset(
                self.matching_candidates
            )
        ):
            raise InvalidSkillDependencyDeclaration()


@dataclass(frozen=True)
class SkillDependencyDiagnostic:
    subject: PublishedSkillVersionId
    code: SkillDependencyDiagnosticCode
    severity: SkillDependencyDiagnosticSeverity
    dependency_id: SkillDependencyId | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.subject, PublishedSkillVersionId)
            or not isinstance(self.code, SkillDependencyDiagnosticCode)
            or not isinstance(self.severity, SkillDependencyDiagnosticSeverity)
            or (
                self.dependency_id is not None
                and not isinstance(self.dependency_id, SkillDependencyId)
            )
        ):
            raise InvalidSkillDependencyDeclaration()


@dataclass(frozen=True, order=True)
class SkillDependencyGraphEdge:
    owner: PublishedSkillVersionId
    dependency: PublishedSkillVersionId
    dependency_id: SkillDependencyId
    declaration: SkillDependencyDeclaration

    def __post_init__(self) -> None:
        if (
            not isinstance(self.owner, PublishedSkillVersionId)
            or not isinstance(self.dependency, PublishedSkillVersionId)
            or not isinstance(self.dependency_id, SkillDependencyId)
            or not isinstance(self.declaration, SkillDependencyDeclaration)
        ):
            raise InvalidSkillDependencyGraphInput()


@dataclass(frozen=True)
class SkillDependencyGraphInput:
    nodes: tuple[PublishedSkillVersionRecord, ...]
    edges: tuple[SkillDependencyGraphEdge, ...]
    complete: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.nodes, tuple)
            or not all(
                isinstance(node, PublishedSkillVersionRecord) for node in self.nodes
            )
            or not isinstance(self.edges, tuple)
            or not all(isinstance(edge, SkillDependencyGraphEdge) for edge in self.edges)
            or not isinstance(self.complete, bool)
            or len(self.nodes) > _MAX_GRAPH_NODES
            or len(self.edges) > _MAX_GRAPH_EDGES
        ):
            raise InvalidSkillDependencyGraphInput()


@dataclass(frozen=True)
class SkillDependencyCycleFact:
    nodes: tuple[PublishedSkillVersionId, ...]
    dependency_ids: tuple[SkillDependencyId, ...]
    status: SkillDependencyCycleStatus

    def __post_init__(self) -> None:
        if (
            not _tuple_of(self.nodes, PublishedSkillVersionId)
            or not self.nodes
            or not _tuple_of(self.dependency_ids, SkillDependencyId)
            or len(self.nodes) != len(self.dependency_ids)
            or not isinstance(self.status, SkillDependencyCycleStatus)
        ):
            raise InvalidSkillDependencyGraphInput()


@dataclass(frozen=True)
class SkillDependencyGraphSnapshot:
    nodes: tuple[PublishedSkillVersionId, ...]
    edges: tuple[SkillDependencyGraphEdge, ...]
    cycles: tuple[SkillDependencyCycleFact, ...]
    complete: bool

    def __post_init__(self) -> None:
        if (
            not _tuple_of(self.nodes, PublishedSkillVersionId)
            or not _tuple_of(self.edges, SkillDependencyGraphEdge)
            or not _tuple_of(self.cycles, SkillDependencyCycleFact)
            or not isinstance(self.complete, bool)
        ):
            raise InvalidSkillDependencyGraphInput()


@dataclass(frozen=True, kw_only=True)
class AnalyzeSkillDependenciesRequest:
    subject: PublishedSkillVersionId
    analysis_profile_ref: SkillSemanticReference
    observations: tuple[SkillCompatibilityObservation, ...] = ()
    candidate_limit: SkillStoreQueryLimit = SkillStoreQueryLimit()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.subject, PublishedSkillVersionId)
            or not isinstance(self.analysis_profile_ref, SkillSemanticReference)
            or not self.analysis_profile_ref.value.startswith("analysis-profile:")
            or not isinstance(self.observations, tuple)
            or not all(
                isinstance(observation, SkillCompatibilityObservation)
                for observation in self.observations
            )
            or not isinstance(self.candidate_limit, SkillStoreQueryLimit)
        ):
            raise InvalidSkillDependencyAnalysisProfile()


@dataclass(frozen=True)
class SkillDependencyAnalysis:
    subject: PublishedSkillVersionId
    requirements: tuple[SkillDependencyRequirementFact, ...]
    candidates: tuple[SkillDependencyCandidateFact, ...]
    compatibility_requirements: tuple[SkillCompatibilityRequirementFact, ...]
    observation_refs: tuple[SkillSemanticReference, ...]
    diagnostics: tuple[SkillDependencyDiagnostic, ...]
    incomplete_reasons: tuple[SkillDependencyIncompleteReason, ...]
    status: SkillDependencyAnalysisStatus
    complete: bool
    has_unsatisfied_required: bool
    has_conflicting_facts: bool
    analysis_profile_ref: SkillSemanticReference

    def __post_init__(self) -> None:
        if (
            not isinstance(self.subject, PublishedSkillVersionId)
            or not _tuple_of(
                self.requirements, SkillDependencyRequirementFact
            )
            or not _tuple_of(self.candidates, SkillDependencyCandidateFact)
            or not _tuple_of(
                self.compatibility_requirements,
                SkillCompatibilityRequirementFact,
            )
            or not _tuple_of(self.observation_refs, SkillSemanticReference)
            or not _tuple_of(self.diagnostics, SkillDependencyDiagnostic)
            or not _tuple_of(
                self.incomplete_reasons, SkillDependencyIncompleteReason
            )
            or not isinstance(self.status, SkillDependencyAnalysisStatus)
            or not isinstance(self.complete, bool)
            or self.complete != (not self.incomplete_reasons)
            or not isinstance(self.has_unsatisfied_required, bool)
            or not isinstance(self.has_conflicting_facts, bool)
            or not isinstance(self.analysis_profile_ref, SkillSemanticReference)
            or not self.analysis_profile_ref.value.startswith(
                "analysis-profile:"
            )
        ):
            raise InvalidSkillDependencyAnalysisProfile()


@dataclass(frozen=True)
class AnalyzeSkillDependencyGraphRequest:
    graph: SkillDependencyGraphInput

    def __post_init__(self) -> None:
        if not isinstance(self.graph, SkillDependencyGraphInput):
            raise InvalidSkillDependencyGraphInput()


def _tuple_of(value: object, expected: type[object]) -> bool:
    return isinstance(value, tuple) and all(
        isinstance(item, expected) for item in value
    )
