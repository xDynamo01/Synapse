from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import StrEnum

from synapse.skills.phase2_errors import (
    ImmutableSkillIdentityMismatch,
    InvalidPublishedSkillManifest,
    InvalidSkillCompatibilityDeclaration,
    InvalidSkillContentReference,
    InvalidSkillDependencyDeclaration,
    InvalidSkillReference,
    InvalidSkillSecurityDeclaration,
    SkillPhase2DomainError,
)
from synapse.skills.phase2_serialization import canonical_json_bytes, canonical_sort_key
from synapse.skills.phase2_values import (
    SkillContentFingerprint,
    SkillId,
    SkillLogicalPath,
    SkillManifestFingerprint,
    SkillManifestFormatVersion,
    SkillPackageFingerprint,
    SkillRequirementId,
    SkillSchemaVersionRequirement,
    SkillSemanticReference,
    SkillVersion,
    SkillVersionConstraint,
)

_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")

__all__ = [
    "SkillContentFingerprint",
    "SkillId",
    "SkillLogicalPath",
    "SkillManifestFingerprint",
    "SkillManifestFormatVersion",
    "SkillPackageFingerprint",
    "SkillRequirementId",
    "SkillSchemaVersionRequirement",
    "SkillSemanticReference",
    "SkillVersion",
    "SkillVersionConstraint",
]


class SkillContentKind(StrEnum):
    INSTRUCTIONS = "instructions"
    DOCUMENTATION = "documentation"
    RESOURCE = "resource"
    ENTRYPOINT = "entrypoint"
    SCHEMA = "schema"


@dataclass(frozen=True, order=True)
class SkillContentRef:
    logical_path: SkillLogicalPath
    fingerprint: SkillContentFingerprint
    kind: SkillContentKind
    media_type: str
    size_bytes: int
    role: SkillSemanticReference | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.logical_path, SkillLogicalPath)
            or not isinstance(self.fingerprint, SkillContentFingerprint)
            or not isinstance(self.kind, SkillContentKind)
            or (self.role is not None and not isinstance(self.role, SkillSemanticReference))
        ):
            raise InvalidSkillContentReference("skill content kind is invalid")
        if not isinstance(self.media_type, str) or not _MEDIA_TYPE.fullmatch(self.media_type):
            raise InvalidSkillContentReference("skill content media type is invalid")
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise InvalidSkillContentReference("skill content size is invalid")


@dataclass(frozen=True, order=True)
class SkillProvenance:
    publisher_ref: SkillSemanticReference
    source_repository_ref: SkillSemanticReference | None = None
    publication_ref: SkillSemanticReference | None = None
    source_revision_ref: SkillSemanticReference | None = None
    build_ref: SkillSemanticReference | None = None
    signature_ref: SkillSemanticReference | None = None
    lineage_ref: SkillSemanticReference | None = None

    def __post_init__(self) -> None:
        values = (
            self.source_repository_ref,
            self.publication_ref,
            self.source_revision_ref,
            self.build_ref,
            self.signature_ref,
            self.lineage_ref,
        )
        if not isinstance(self.publisher_ref, SkillSemanticReference) or any(
            value is not None and not isinstance(value, SkillSemanticReference)
            for value in values
        ):
            raise InvalidSkillReference("skill provenance reference is invalid")


class SkillPublicationScope(StrEnum):
    SYSTEM = "system"
    USER = "user"
    WORKSPACE = "workspace"
    PROJECT = "project"
    AGENT = "agent"
    MISSION = "mission"
    TASK = "task"


class SkillDependencyReason(StrEnum):
    REQUIRED_WORKFLOW = "required_workflow"
    SHARED_SCHEMA = "shared_schema"
    OPTIONAL_ENHANCEMENT = "optional_enhancement"


@dataclass(frozen=True, order=True)
class SkillDependencyDeclaration:
    skill_id: SkillId
    reason: SkillDependencyReason
    version: SkillVersion | None = None
    constraint: SkillVersionConstraint | None = None
    optional: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.skill_id, SkillId)
            or not isinstance(self.reason, SkillDependencyReason)
            or (self.version is not None and not isinstance(self.version, SkillVersion))
            or (
                self.constraint is not None
                and not isinstance(self.constraint, SkillVersionConstraint)
            )
            or not isinstance(self.optional, bool)
        ):
            raise InvalidSkillDependencyDeclaration("skill dependency declaration is invalid")
        if (self.version is None) == (self.constraint is None):
            raise InvalidSkillDependencyDeclaration(
                "skill dependency requires exactly one version or constraint"
            )
        if self.optional and self.reason is not SkillDependencyReason.OPTIONAL_ENHANCEMENT:
            raise InvalidSkillDependencyDeclaration("optional skill dependency reason is invalid")
        if not self.optional and self.reason is SkillDependencyReason.OPTIONAL_ENHANCEMENT:
            raise InvalidSkillDependencyDeclaration("required skill dependency reason is invalid")


@dataclass(frozen=True, order=True)
class ToolRequirement:
    tool_id: SkillRequirementId
    version_constraint: SkillVersionConstraint | None = None

    def __post_init__(self) -> None:
        _validate_requirement(self.tool_id, self.version_constraint)


@dataclass(frozen=True, order=True)
class CapabilityRequirement:
    capability_id: SkillRequirementId
    version_constraint: SkillVersionConstraint | None = None

    def __post_init__(self) -> None:
        _validate_requirement(self.capability_id, self.version_constraint)


@dataclass(frozen=True, order=True)
class ProviderModelRequirement:
    provider_id: SkillRequirementId
    model_id: SkillRequirementId | None = None
    version_constraint: SkillVersionConstraint | None = None

    def __post_init__(self) -> None:
        _validate_requirement(self.provider_id, self.version_constraint)
        if self.model_id is not None and not isinstance(self.model_id, SkillRequirementId):
            raise InvalidSkillDependencyDeclaration("skill requirement declaration is invalid")


@dataclass(frozen=True, order=True)
class ExternalRuntimeRequirement:
    runtime_id: SkillRequirementId
    version_constraint: SkillVersionConstraint

    def __post_init__(self) -> None:
        _validate_requirement(self.runtime_id, self.version_constraint)


@dataclass(frozen=True, order=True)
class SkillConflictDeclaration:
    skill_id: SkillId
    version_constraint: SkillVersionConstraint | None
    reason: SkillSemanticReference

    def __post_init__(self) -> None:
        if (
            not isinstance(self.skill_id, SkillId)
            or (
                self.version_constraint is not None
                and not isinstance(self.version_constraint, SkillVersionConstraint)
            )
            or not isinstance(self.reason, SkillSemanticReference)
        ):
            raise InvalidSkillDependencyDeclaration("skill conflict declaration is invalid")


@dataclass(frozen=True)
class SkillCompatibilityDeclaration:
    operating_profiles: tuple[SkillRequirementId, ...] = ()
    platforms: tuple[SkillRequirementId, ...] = ()
    python_constraint: SkillVersionConstraint | None = None
    external_runtimes: tuple[ExternalRuntimeRequirement, ...] = ()
    providers: tuple[ProviderModelRequirement, ...] = ()
    schemas: tuple[SkillSchemaVersionRequirement, ...] = ()

    def __post_init__(self) -> None:
        if (
            not _tuple_of(self.operating_profiles, SkillRequirementId)
            or not _tuple_of(self.platforms, SkillRequirementId)
            or (
                self.python_constraint is not None
                and not isinstance(self.python_constraint, SkillVersionConstraint)
            )
            or not _tuple_of(self.external_runtimes, ExternalRuntimeRequirement)
            or not _tuple_of(self.providers, ProviderModelRequirement)
            or not _tuple_of(self.schemas, SkillSchemaVersionRequirement)
        ):
            raise InvalidSkillCompatibilityDeclaration(
                "skill compatibility declaration is invalid"
            )
        _canonicalize_unique(self, "operating_profiles")
        _canonicalize_unique(self, "platforms")
        _canonicalize_unique(self, "external_runtimes")
        _canonicalize_unique(self, "providers")
        _canonicalize_unique(self, "schemas")


class DataClassificationCeiling(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class NetworkRequirement(StrEnum):
    NONE = "none"
    REQUIRED = "required"


class ExternalProcessingRequirement(StrEnum):
    FORBIDDEN = "forbidden"
    OPTIONAL = "optional"
    REQUIRED = "required"


class FilesystemRequirement(StrEnum):
    NONE = "none"
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class EgressRequirement(StrEnum):
    NONE = "none"
    DECLARED = "declared"


@dataclass(frozen=True)
class SkillSecurityDeclaration:
    classification_ceiling: DataClassificationCeiling = DataClassificationCeiling.INTERNAL
    network_requirement: NetworkRequirement = NetworkRequirement.NONE
    external_processing_requirement: ExternalProcessingRequirement = (
        ExternalProcessingRequirement.FORBIDDEN
    )
    filesystem_requirement: FilesystemRequirement = FilesystemRequirement.NONE
    egress_requirement: EgressRequirement = EgressRequirement.NONE
    sandbox_profile_requirement: SkillSemanticReference | None = None
    secret_reference_requirements: tuple[SkillSemanticReference, ...] = ()

    def __post_init__(self) -> None:
        enum_fields = (
            (self.classification_ceiling, DataClassificationCeiling),
            (self.network_requirement, NetworkRequirement),
            (self.external_processing_requirement, ExternalProcessingRequirement),
            (self.filesystem_requirement, FilesystemRequirement),
            (self.egress_requirement, EgressRequirement),
        )
        if any(not isinstance(value, expected) for value, expected in enum_fields):
            raise InvalidSkillSecurityDeclaration("skill security declaration is invalid")
        if (
            self.sandbox_profile_requirement is not None
            and not isinstance(self.sandbox_profile_requirement, SkillSemanticReference)
        ) or not _tuple_of(self.secret_reference_requirements, SkillSemanticReference):
            raise InvalidSkillSecurityDeclaration("skill security declaration is invalid")
        if (
            self.egress_requirement is EgressRequirement.DECLARED
            and self.network_requirement is NetworkRequirement.NONE
        ):
            raise InvalidSkillSecurityDeclaration("skill egress requirement needs network")
        _canonicalize_unique(self, "secret_reference_requirements")


class SkillExecutionRuntime(StrEnum):
    PYTHON = "python"
    WASM = "wasm"


@dataclass(frozen=True, order=True)
class SkillResourceRequirement:
    timeout_seconds: int
    memory_mebibytes: int
    cpu_millicores: int

    def __post_init__(self) -> None:
        values = (self.timeout_seconds, self.memory_mebibytes, self.cpu_millicores)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values):
            raise InvalidPublishedSkillManifest("skill resource requirement is invalid")


@dataclass(frozen=True)
class SkillExecutionDeclaration:
    entrypoint: SkillContentRef
    runtime: SkillExecutionRuntime
    sandbox_profile_ref: SkillSemanticReference
    resources: SkillResourceRequirement
    required_tools: tuple[ToolRequirement, ...] = ()
    required_capabilities: tuple[CapabilityRequirement, ...] = ()
    input_schema_ref: SkillContentRef | None = None
    output_schema_ref: SkillContentRef | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.entrypoint, SkillContentRef)
            or not isinstance(self.runtime, SkillExecutionRuntime)
            or not isinstance(self.sandbox_profile_ref, SkillSemanticReference)
            or not isinstance(self.resources, SkillResourceRequirement)
            or not _tuple_of(self.required_tools, ToolRequirement)
            or not _tuple_of(self.required_capabilities, CapabilityRequirement)
            or (
                self.input_schema_ref is not None
                and not isinstance(self.input_schema_ref, SkillContentRef)
            )
            or (
                self.output_schema_ref is not None
                and not isinstance(self.output_schema_ref, SkillContentRef)
            )
        ):
            raise InvalidPublishedSkillManifest("skill execution declaration is invalid")
        if self.entrypoint.kind is not SkillContentKind.ENTRYPOINT:
            raise InvalidPublishedSkillManifest("skill execution entrypoint kind is invalid")
        if not isinstance(self.runtime, SkillExecutionRuntime):
            raise InvalidPublishedSkillManifest("skill execution runtime is invalid")
        for schema in (self.input_schema_ref, self.output_schema_ref):
            if schema is not None and schema.kind is not SkillContentKind.SCHEMA:
                raise InvalidPublishedSkillManifest("skill execution schema kind is invalid")
        _canonicalize_unique(self, "required_tools")
        _canonicalize_unique(self, "required_capabilities")


@dataclass(frozen=True, order=True)
class SkillGovernanceRequirement:
    reference: SkillSemanticReference

    def __post_init__(self) -> None:
        if not isinstance(self.reference, SkillSemanticReference):
            raise InvalidPublishedSkillManifest("skill governance requirement is invalid")


@dataclass(frozen=True, order=True)
class SkillEvaluationRequirement:
    reference: SkillSemanticReference

    def __post_init__(self) -> None:
        if not isinstance(self.reference, SkillSemanticReference):
            raise InvalidPublishedSkillManifest("skill evaluation requirement is invalid")


@dataclass(frozen=True)
class PublishedSkillManifest:
    format_version: SkillManifestFormatVersion
    skill_id: SkillId
    version: SkillVersion
    display_name: str
    summary: str
    description: str
    provenance: SkillProvenance
    scopes: tuple[SkillPublicationScope, ...]
    content: tuple[SkillContentRef, ...]
    dependencies: tuple[SkillDependencyDeclaration, ...] = ()
    conflicts: tuple[SkillConflictDeclaration, ...] = ()
    tools: tuple[ToolRequirement, ...] = ()
    capabilities: tuple[CapabilityRequirement, ...] = ()
    providers: tuple[ProviderModelRequirement, ...] = ()
    compatibility: SkillCompatibilityDeclaration = field(
        default_factory=SkillCompatibilityDeclaration
    )
    security: SkillSecurityDeclaration = field(default_factory=SkillSecurityDeclaration)
    execution: tuple[SkillExecutionDeclaration, ...] = ()
    governance_requirements: tuple[SkillGovernanceRequirement, ...] = ()
    evaluation_requirements: tuple[SkillEvaluationRequirement, ...] = ()
    configuration_schema_ref: SkillContentRef | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.format_version, SkillManifestFormatVersion)
            or not isinstance(self.skill_id, SkillId)
            or not isinstance(self.version, SkillVersion)
            or not isinstance(self.provenance, SkillProvenance)
            or not _tuple_of(self.scopes, SkillPublicationScope)
            or not _tuple_of(self.content, SkillContentRef)
            or not _tuple_of(self.dependencies, SkillDependencyDeclaration)
            or not _tuple_of(self.conflicts, SkillConflictDeclaration)
            or not _tuple_of(self.tools, ToolRequirement)
            or not _tuple_of(self.capabilities, CapabilityRequirement)
            or not _tuple_of(self.providers, ProviderModelRequirement)
            or not isinstance(self.compatibility, SkillCompatibilityDeclaration)
            or not isinstance(self.security, SkillSecurityDeclaration)
            or not _tuple_of(self.execution, SkillExecutionDeclaration)
            or not _tuple_of(self.governance_requirements, SkillGovernanceRequirement)
            or not _tuple_of(self.evaluation_requirements, SkillEvaluationRequirement)
            or (
                self.configuration_schema_ref is not None
                and not isinstance(self.configuration_schema_ref, SkillContentRef)
            )
        ):
            raise InvalidPublishedSkillManifest("skill manifest declaration type is invalid")
        for value, label, maximum in (
            (self.display_name, "display name", 120),
            (self.summary, "summary", 280),
            (self.description, "description", 4000),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
                or len(value) > maximum
            ):
                raise InvalidPublishedSkillManifest(f"skill manifest {label} is invalid")
        if not self.scopes:
            raise InvalidPublishedSkillManifest("skill manifest requires a publication scope")
        if not self.content:
            raise InvalidPublishedSkillManifest("skill manifest requires content references")
        if self.configuration_schema_ref is not None:
            if self.configuration_schema_ref.kind is not SkillContentKind.SCHEMA:
                raise InvalidPublishedSkillManifest("skill configuration schema kind is invalid")
        for name in (
            "scopes",
            "content",
            "dependencies",
            "conflicts",
            "tools",
            "capabilities",
            "providers",
            "execution",
            "governance_requirements",
            "evaluation_requirements",
        ):
            _canonicalize_unique(self, name)
        paths = tuple(item.logical_path for item in self.content)
        if len(paths) != len(set(paths)):
            raise InvalidPublishedSkillManifest("skill manifest content paths must be unique")
        if any(item.skill_id == self.skill_id for item in self.dependencies):
            raise InvalidPublishedSkillManifest("skill manifest cannot depend on itself")
        declared = set(self.content)
        referenced = {
            item
            for execution in self.execution
            for item in (
                execution.entrypoint,
                execution.input_schema_ref,
                execution.output_schema_ref,
            )
            if item is not None
        }
        if self.configuration_schema_ref is not None:
            referenced.add(self.configuration_schema_ref)
        if not referenced.issubset(declared):
            raise InvalidPublishedSkillManifest(
                "skill manifest references undeclared content"
            )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self)

    def fingerprint(self) -> SkillManifestFingerprint:
        return SkillManifestFingerprint(hashlib.sha256(self.canonical_bytes()).hexdigest())


@dataclass(frozen=True, order=True)
class PublishedSkillVersionId:
    skill_id: SkillId
    version: SkillVersion
    manifest_fingerprint: SkillManifestFingerprint
    content_fingerprint: SkillContentFingerprint

    def __post_init__(self) -> None:
        if (
            not isinstance(self.skill_id, SkillId)
            or not isinstance(self.version, SkillVersion)
            or not isinstance(self.manifest_fingerprint, SkillManifestFingerprint)
            or not isinstance(self.content_fingerprint, SkillContentFingerprint)
        ):
            raise ImmutableSkillIdentityMismatch("published skill identity is invalid")

    def to_canonical_text(self) -> str:
        return (
            f"{self.skill_id}@{self.version}"
            f"#manifest-sha256:{self.manifest_fingerprint}"
            f";content-sha256:{self.content_fingerprint}"
        )

    @classmethod
    def parse(cls, value: str) -> PublishedSkillVersionId:
        try:
            identity, fingerprints = value.split("#manifest-sha256:", 1)
            skill_id, version = identity.split("@", 1)
            manifest, content = fingerprints.split(";content-sha256:", 1)
            parsed = cls(
                SkillId.parse(skill_id),
                SkillVersion.parse(version),
                SkillManifestFingerprint(manifest),
                SkillContentFingerprint(content),
            )
        except (ValueError, SkillPhase2DomainError) as exc:
            raise ImmutableSkillIdentityMismatch("published skill identity is invalid") from exc
        if parsed.to_canonical_text() != value:
            raise ImmutableSkillIdentityMismatch("published skill identity is invalid")
        return parsed

    @classmethod
    def from_manifest(
        cls,
        manifest: PublishedSkillManifest,
        content_fingerprint: SkillContentFingerprint,
    ) -> PublishedSkillVersionId:
        return cls(
            manifest.skill_id,
            manifest.version,
            manifest.fingerprint(),
            content_fingerprint,
        )

    def assert_manifest(self, manifest: PublishedSkillManifest) -> None:
        if not isinstance(manifest, PublishedSkillManifest) or (
            manifest.skill_id != self.skill_id
            or manifest.version != self.version
            or manifest.fingerprint() != self.manifest_fingerprint
        ):
            raise ImmutableSkillIdentityMismatch("published skill identity does not match manifest")

    def __str__(self) -> str:
        return self.to_canonical_text()


def _validate_requirement(
    requirement_id: SkillRequirementId,
    version_constraint: SkillVersionConstraint | None,
) -> None:
    if not isinstance(requirement_id, SkillRequirementId) or (
        version_constraint is not None
        and not isinstance(version_constraint, SkillVersionConstraint)
    ):
        raise InvalidSkillDependencyDeclaration("skill requirement declaration is invalid")


def _tuple_of(value: object, expected: type[object]) -> bool:
    return isinstance(value, tuple) and all(isinstance(item, expected) for item in value)


def _canonicalize_unique(instance: object, name: str) -> None:
    value = getattr(instance, name)
    if not isinstance(value, tuple):
        raise InvalidPublishedSkillManifest("skill manifest collections must be immutable tuples")
    ordered = tuple(sorted(value, key=canonical_sort_key))
    if len(ordered) != len(set(ordered)):
        raise InvalidPublishedSkillManifest("skill manifest declarations must be unique")
    object.__setattr__(instance, name, ordered)
