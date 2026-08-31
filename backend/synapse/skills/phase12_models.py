from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from synapse.skills.phase2_models import (
    CapabilityRequirement,
    PublishedSkillVersionId,
    SkillContentRef,
    SkillExecutionRuntime,
    SkillLogicalPath,
    SkillResourceRequirement,
    SkillSecurityDeclaration,
    ToolRequirement,
)
from synapse.skills.phase2_values import SkillSemanticReference
from synapse.skills.phase3_records import PublishedSkillVersionRecord, SkillActivationRecord
from synapse.skills.phase3_values import SkillStoreRecordId
from synapse.skills.phase6_models import SkillLifecycleProjection
from synapse.skills.phase7_models import SkillInstallationProjection
from synapse.skills.phase8_models import (
    SkillCompatibilityStatus,
    SkillDependencyLifecycleStatus,
)
from synapse.skills.phase9_models import (
    SkillDependencyResolutionConflictKind,
    SkillDependencyResolutionPlan,
    SkillDependencyResolutionStatus,
)
from synapse.skills.phase9_policy import SkillDependencyResolutionPolicyVersion
from synapse.skills.phase10_models import (
    SkillGovernanceBindingProjection,
    SkillIntelligenceBindingProjection,
)
from synapse.skills.phase10_refs import ExternalBindingOccurrenceRef
from synapse.skills.phase11_models import SkillPrivateEvalBindingProjection
from synapse.skills.phase11_refs import PrivateEvalBindingOccurrenceRef
from synapse.skills.phase12_errors import InvalidSkillExecutionHandoffRequest
from synapse.skills.phase12_policy import (
    SkillExecutionBindingCompletenessPolicy,
    SkillExecutionHandoffBuildPolicy,
)
from synapse.skills.phase12_refs import (
    SkillExecutionHandoffFormatVersion,
    SkillExecutionHandoffId,
    SkillExecutionProfileRef,
)


class SkillDependencyRegistrationStatus(StrEnum):
    REGISTERED = "registered"
    UNKNOWN = "unknown"
    TERMINATED = "terminated"
    CORRUPTED_REGISTRATION = "corrupted_registration"


class SkillExecutionBindingFamily(StrEnum):
    GOVERNANCE = "governance"
    INTELLIGENCE = "intelligence"
    PRIVATE_EVALS = "private_evals"


class SkillExecutionReadinessStatus(StrEnum):
    SATISFIED = "satisfied"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not_required"


class SkillExecutionHandoffDiagnosticCode(StrEnum):
    INSTALLATION_MISSING = "installation_missing"
    INSTALLATION_TERMINATED = "installation_terminated"
    INSTALLATION_REGISTRATION_CORRUPTED = "installation_registration_corrupted"
    INSTALLATION_HISTORY_INCOMPLETE = "installation_history_incomplete"
    ACTIVATION_MISSING = "activation_missing"
    LIFECYCLE_HISTORY_INCOMPLETE = "lifecycle_history_incomplete"
    LIFECYCLE_INACTIVE = "lifecycle_inactive"
    LIFECYCLE_REVOKED = "lifecycle_revoked"
    LIFECYCLE_DEPRECATED = "lifecycle_deprecated"
    LIFECYCLE_SUPERSEDED = "lifecycle_superseded"
    RESOLUTION_INCOMPLETE = "resolution_incomplete"
    UNRESOLVED_REQUIRED_DEPENDENCY = "unresolved_required_dependency"
    OPTIONAL_DEPENDENCY_OMITTED = "optional_dependency_omitted"
    DEGRADED_DEPENDENCY_SELECTION = "degraded_dependency_selection"
    RESOLUTION_CONFLICT = "resolution_conflict"
    DEPENDENCY_REGISTRATION_UNKNOWN = "dependency_registration_unknown"
    DEPENDENCY_REGISTRATION_INVALID = "dependency_registration_invalid"
    EXECUTION_PROFILE_MISSING = "execution_profile_missing"
    EXTERNAL_BINDING_ABSENT = "external_binding_absent"
    BINDING_HISTORY_INCOMPLETE = "binding_history_incomplete"
    GRAPH_CYCLE_CONFLICT = "graph_cycle_conflict"


@dataclass(frozen=True, order=True)
class SkillExecutionDependencyFact:
    selected: PublishedSkillVersionId
    requirement_ids: tuple[str, ...]
    policy_version: SkillDependencyResolutionPolicyVersion
    lifecycle_status: SkillDependencyLifecycleStatus
    compatibility_status: SkillCompatibilityStatus
    degraded: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.selected, PublishedSkillVersionId)
            or not isinstance(self.requirement_ids, tuple)
            or not self.requirement_ids
            or not all(isinstance(item, str) and item for item in self.requirement_ids)
            or len(set(self.requirement_ids)) != len(self.requirement_ids)
            or not isinstance(self.policy_version, SkillDependencyResolutionPolicyVersion)
            or not isinstance(self.lifecycle_status, SkillDependencyLifecycleStatus)
            or not isinstance(self.compatibility_status, SkillCompatibilityStatus)
            or not isinstance(self.degraded, bool)
        ):
            raise InvalidSkillExecutionHandoffRequest()


@dataclass(frozen=True, order=True)
class SkillExecutionDependencyRegistrationFact:
    """Caller-supplied registral fact; never evidence of physical custody."""

    dependency: PublishedSkillVersionId
    status: SkillDependencyRegistrationStatus
    installation_id: SkillStoreRecordId | None
    history_complete: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.dependency, PublishedSkillVersionId)
            or not isinstance(self.status, SkillDependencyRegistrationStatus)
            or not isinstance(self.history_complete, bool)
            or (
                self.installation_id is not None
                and not isinstance(self.installation_id, SkillStoreRecordId)
            )
            or (
                (self.status is SkillDependencyRegistrationStatus.REGISTERED)
                != (self.installation_id is not None)
            )
        ):
            raise InvalidSkillExecutionHandoffRequest()


@dataclass(frozen=True)
class SkillExecutionResolutionFact:
    profile_ref: SkillSemanticReference
    policy_version: SkillDependencyResolutionPolicyVersion
    status: SkillDependencyResolutionStatus
    complete: bool
    required_resolved: bool
    has_optional_omissions: bool
    has_degraded_selections: bool
    conflict_kinds: tuple[SkillDependencyResolutionConflictKind, ...]
    has_graph_cycles: bool


@dataclass(frozen=True)
class SkillExecutionInstallationFact:
    selected_record_known: bool
    current_registration: bool
    history_complete: bool
    terminated_registration: bool
    corrupted_registration_observed: bool


@dataclass(frozen=True)
class SkillExecutionLifecycleFact:
    history_complete: bool
    active: bool
    revoked: bool
    deprecated: bool
    superseded: bool
    active_installation_id: SkillStoreRecordId | None


@dataclass(frozen=True, order=True)
class SkillExecutionBindingHistoryFact:
    family: SkillExecutionBindingFamily
    supplied: bool
    complete: bool


@dataclass(frozen=True)
class SkillExecutionHandoffRequirements:
    require_active_subject: bool
    require_complete_dependency_resolution: bool
    require_resolved_dependency_registrations: bool
    allow_optional_dependency_omissions: bool
    require_declared_execution_profile: bool
    bindings: SkillExecutionBindingCompletenessPolicy


@dataclass(frozen=True, order=True)
class SkillExecutionHandoffDiagnostic:
    code: SkillExecutionHandoffDiagnosticCode
    subject: PublishedSkillVersionId | None = None
    binding_family: SkillExecutionBindingFamily | None = None


@dataclass(frozen=True)
class SkillExecutionReadiness:
    publication_correspondent: SkillExecutionReadinessStatus
    installation_registration_correspondent: SkillExecutionReadinessStatus
    lifecycle_activation_satisfied: SkillExecutionReadinessStatus
    dependencies_resolved: SkillExecutionReadinessStatus
    dependency_registration_known: SkillExecutionReadinessStatus
    capability_declarations_complete: SkillExecutionReadinessStatus
    security_declaration_complete: SkillExecutionReadinessStatus
    execution_profile_present: SkillExecutionReadinessStatus
    external_bindings_complete: SkillExecutionReadinessStatus
    handoff_structurally_complete: SkillExecutionReadinessStatus


@dataclass(frozen=True, kw_only=True)
class BuildSkillExecutionHandoffRequest:
    """Typed facts supplied by a trusted composition boundary; no source authentication."""

    subject: PublishedSkillVersionId
    publication: PublishedSkillVersionRecord
    installation_id: SkillStoreRecordId
    installation: SkillInstallationProjection
    activation: SkillActivationRecord | None
    lifecycle: SkillLifecycleProjection
    lifecycle_history_complete: bool
    resolution: SkillDependencyResolutionPlan
    dependency_registrations: tuple[SkillExecutionDependencyRegistrationFact, ...]
    logical_entrypoint: SkillLogicalPath | None
    execution_profile: SkillExecutionProfileRef | None
    governance: SkillGovernanceBindingProjection | None
    intelligence: SkillIntelligenceBindingProjection | None
    private_evals: SkillPrivateEvalBindingProjection | None
    governance_occurrences: tuple[ExternalBindingOccurrenceRef, ...]
    intelligence_occurrences: tuple[ExternalBindingOccurrenceRef, ...]
    private_eval_occurrences: tuple[PrivateEvalBindingOccurrenceRef, ...]
    policy: SkillExecutionHandoffBuildPolicy
    format_version: SkillExecutionHandoffFormatVersion = SkillExecutionHandoffFormatVersion.V1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.subject, PublishedSkillVersionId)
            or not isinstance(self.publication, PublishedSkillVersionRecord)
            or not isinstance(self.installation_id, SkillStoreRecordId)
            or not isinstance(self.installation, SkillInstallationProjection)
            or (
                self.activation is not None
                and not isinstance(self.activation, SkillActivationRecord)
            )
            or not isinstance(self.lifecycle, SkillLifecycleProjection)
            or not isinstance(self.lifecycle_history_complete, bool)
            or not isinstance(self.resolution, SkillDependencyResolutionPlan)
            or (
                self.logical_entrypoint is not None
                and not isinstance(self.logical_entrypoint, SkillLogicalPath)
            )
            or (
                self.execution_profile is not None
                and not isinstance(self.execution_profile, SkillExecutionProfileRef)
            )
            or (
                self.governance is not None
                and not isinstance(self.governance, SkillGovernanceBindingProjection)
            )
            or (
                self.intelligence is not None
                and not isinstance(self.intelligence, SkillIntelligenceBindingProjection)
            )
            or (
                self.private_evals is not None
                and not isinstance(self.private_evals, SkillPrivateEvalBindingProjection)
            )
            or not isinstance(self.policy, SkillExecutionHandoffBuildPolicy)
            or not isinstance(self.format_version, SkillExecutionHandoffFormatVersion)
            or not _tuple_of(
                self.dependency_registrations,
                SkillExecutionDependencyRegistrationFact,
            )
            or not _tuple_of(
                self.governance_occurrences, ExternalBindingOccurrenceRef
            )
            or not _tuple_of(
                self.intelligence_occurrences, ExternalBindingOccurrenceRef
            )
            or not _tuple_of(
                self.private_eval_occurrences, PrivateEvalBindingOccurrenceRef
            )
        ):
            raise InvalidSkillExecutionHandoffRequest()


@dataclass(frozen=True)
class SkillExecutionHandoffDraft:
    format_version: SkillExecutionHandoffFormatVersion
    handoff_id: SkillExecutionHandoffId
    subject: PublishedSkillVersionId
    installation_id: SkillStoreRecordId
    activation_id: SkillStoreRecordId | None
    requirements: SkillExecutionHandoffRequirements
    installation: SkillExecutionInstallationFact
    lifecycle: SkillExecutionLifecycleFact
    resolution: SkillExecutionResolutionFact
    dependencies: tuple[SkillExecutionDependencyFact, ...]
    dependency_registrations: tuple[SkillExecutionDependencyRegistrationFact, ...]
    capabilities: tuple[CapabilityRequirement, ...]
    security_declaration: SkillSecurityDeclaration
    resources: tuple[SkillResourceRequirement, ...]
    required_tools: tuple[ToolRequirement, ...]
    execution_runtime: SkillExecutionRuntime | None
    execution_profile: SkillExecutionProfileRef | None
    logical_entrypoint: SkillContentRef | None
    governance_occurrences: tuple[ExternalBindingOccurrenceRef, ...]
    intelligence_occurrences: tuple[ExternalBindingOccurrenceRef, ...]
    private_eval_occurrences: tuple[PrivateEvalBindingOccurrenceRef, ...]
    binding_histories: tuple[SkillExecutionBindingHistoryFact, ...]
    readiness: SkillExecutionReadiness
    diagnostics: tuple[SkillExecutionHandoffDiagnostic, ...]


@dataclass(frozen=True)
class SkillExecutionHandoffBuildResult:
    draft: SkillExecutionHandoffDraft
    readiness: SkillExecutionReadiness


def _tuple_of(value: object, expected: type[object]) -> bool:
    return isinstance(value, tuple) and all(
        isinstance(item, expected) for item in value
    )
