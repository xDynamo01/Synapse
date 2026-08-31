"""Pure deterministic resource quota derivation without measurement or enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .capability_grants import SandboxCapabilityGrantSet
from .errors import InvalidResourceLimitBoundary
from .execution_plan import SandboxExecutionPlan
from .facts import FactCompleteness
from .filesystem_boundary import SandboxFilesystemSpecification
from .identities import (
    SandboxArtifactFingerprint,
    SandboxIsolationProfileId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxPolicyVersion,
    SandboxResourceGrantSetId,
    SandboxResourceLimitPolicyId,
    derive_identity,
)
from .network_boundary import SandboxNetworkSpecification
from .process_boundary import SandboxProcessSpecification

RESOURCE_LIMIT_POLICY_FORMAT = "sandbox-resource-limit-policy-v1"
RESOURCE_CAPABILITY_FORMAT = "sandbox-resource-capabilities-v1"


class SandboxResourceDimension(StrEnum):
    CPU_QUOTA = "cpu_quota"
    CPU_TIME = "cpu_time"
    MEMORY_WORKING_SET = "memory_working_set"
    MEMORY_COMMIT = "memory_commit"
    DISK_SPACE = "disk_space"
    FILE_COUNT = "file_count"
    FILE_SIZE = "file_size"
    STDOUT_BYTES = "stdout_bytes"
    STDERR_BYTES = "stderr_bytes"
    RESULT_BYTES = "result_bytes"
    PROCESS_COUNT = "process_count"
    PROCESS_TREE_DEPTH = "process_tree_depth"
    HANDLE_COUNT = "handle_count"
    FILESYSTEM_OPERATIONS = "filesystem_operations"
    NETWORK_CONNECTIONS = "network_connections"
    NETWORK_BYTES_SENT = "network_bytes_sent"
    NETWORK_BYTES_RECEIVED = "network_bytes_received"
    STARTUP_DURATION = "startup_duration"
    IDLE_DURATION = "idle_duration"
    WALL_CLOCK_DURATION = "wall_clock_duration"
    TERMINATION_GRACE = "termination_grace"
    EVIDENCE_BYTES = "evidence_bytes"
    ARTIFACT_OUTPUT_BYTES = "artifact_output_bytes"


class SandboxResourceUnit(StrEnum):
    MICROSECONDS_PER_SECOND = "microseconds_per_second"
    MILLISECONDS = "milliseconds"
    BYTES = "bytes"
    COUNT = "count"
    OPERATIONS = "operations"


class SandboxResourceScope(StrEnum):
    PER_PROCESS = "per_process"
    PROCESS_TREE = "process_tree"
    SANDBOX_TOTAL = "sandbox_total"
    FILESYSTEM_TOTAL = "filesystem_total"
    NETWORK_TOTAL = "network_total"
    OUTPUT_TOTAL = "output_total"


class SandboxResourceEnforcement(StrEnum):
    CPU_QUOTA = "cpu_quota"
    CPU_TIME = "cpu_time"
    MEMORY = "memory"
    DISK = "disk"
    FILESYSTEM = "filesystem"
    OUTPUT = "output"
    PROCESS_TREE = "process_tree"
    HANDLES = "handles"
    NETWORK = "network"
    TIME = "time"
    EVIDENCE = "evidence"
    ARTIFACT_OUTPUT = "artifact_output"


class SandboxResourceDenialReason(StrEnum):
    LIMIT_ABSENT = "limit_absent"
    POLICY_EXCEEDED = "policy_exceeded"
    UNSUPPORTED_ENFORCEMENT = "unsupported_enforcement"
    UNIT_MISMATCH = "unit_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"
    CONTRADICTORY_LIMITS = "contradictory_limits"


_DIMENSION_SHAPE: dict[
    SandboxResourceDimension, tuple[SandboxResourceUnit, SandboxResourceScope]
] = {
    SandboxResourceDimension.CPU_QUOTA: (
        SandboxResourceUnit.MICROSECONDS_PER_SECOND,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.CPU_TIME: (
        SandboxResourceUnit.MILLISECONDS,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.MEMORY_WORKING_SET: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.PER_PROCESS,
    ),
    SandboxResourceDimension.MEMORY_COMMIT: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.DISK_SPACE: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.FILESYSTEM_TOTAL,
    ),
    SandboxResourceDimension.FILE_COUNT: (
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.FILESYSTEM_TOTAL,
    ),
    SandboxResourceDimension.FILE_SIZE: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.FILESYSTEM_TOTAL,
    ),
    SandboxResourceDimension.STDOUT_BYTES: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.OUTPUT_TOTAL,
    ),
    SandboxResourceDimension.STDERR_BYTES: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.OUTPUT_TOTAL,
    ),
    SandboxResourceDimension.RESULT_BYTES: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.OUTPUT_TOTAL,
    ),
    SandboxResourceDimension.PROCESS_COUNT: (
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.PROCESS_TREE_DEPTH: (
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.HANDLE_COUNT: (
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.FILESYSTEM_OPERATIONS: (
        SandboxResourceUnit.OPERATIONS,
        SandboxResourceScope.FILESYSTEM_TOTAL,
    ),
    SandboxResourceDimension.NETWORK_CONNECTIONS: (
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.NETWORK_TOTAL,
    ),
    SandboxResourceDimension.NETWORK_BYTES_SENT: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.NETWORK_TOTAL,
    ),
    SandboxResourceDimension.NETWORK_BYTES_RECEIVED: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.NETWORK_TOTAL,
    ),
    SandboxResourceDimension.STARTUP_DURATION: (
        SandboxResourceUnit.MILLISECONDS,
        SandboxResourceScope.SANDBOX_TOTAL,
    ),
    SandboxResourceDimension.IDLE_DURATION: (
        SandboxResourceUnit.MILLISECONDS,
        SandboxResourceScope.SANDBOX_TOTAL,
    ),
    SandboxResourceDimension.WALL_CLOCK_DURATION: (
        SandboxResourceUnit.MILLISECONDS,
        SandboxResourceScope.SANDBOX_TOTAL,
    ),
    SandboxResourceDimension.TERMINATION_GRACE: (
        SandboxResourceUnit.MILLISECONDS,
        SandboxResourceScope.SANDBOX_TOTAL,
    ),
    SandboxResourceDimension.EVIDENCE_BYTES: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.OUTPUT_TOTAL,
    ),
    SandboxResourceDimension.ARTIFACT_OUTPUT_BYTES: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.OUTPUT_TOTAL,
    ),
}


@dataclass(frozen=True, slots=True)
class SandboxResourceLimit:
    dimension: SandboxResourceDimension
    unit: SandboxResourceUnit
    scope: SandboxResourceScope
    hard: int | None
    soft: int | None = None
    burst: int | None = None
    grace: int | None = None
    unlimited: bool = False

    def __post_init__(self) -> None:
        if self.unlimited:
            if any(value is not None for value in (self.hard, self.soft, self.burst, self.grace)):
                raise InvalidResourceLimitBoundary("limit.unlimited_conflict")
            return
        if not isinstance(self.hard, int) or isinstance(self.hard, bool) or self.hard <= 0:
            raise InvalidResourceLimitBoundary("limit.hard_required")
        for name, value in (
            ("soft", self.soft),
            ("burst", self.burst),
            ("grace", self.grace),
        ):
            if value is not None and (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value <= 0
                or value > self.hard
            ):
                raise InvalidResourceLimitBoundary(f"limit.{name}_invalid")


@dataclass(frozen=True, slots=True)
class SandboxResourceLimitRequest:
    limit: SandboxResourceLimit


@dataclass(frozen=True, slots=True)
class SandboxResourceLimitRequirement:
    maximum: SandboxResourceLimit
    required: bool
    allow_unlimited: bool
    required_enforcements: tuple[SandboxResourceEnforcement, ...]

    def __post_init__(self) -> None:
        expected_unit, expected_scope = _DIMENSION_SHAPE[self.maximum.dimension]
        if self.maximum.unit is not expected_unit or self.maximum.scope is not expected_scope:
            raise InvalidResourceLimitBoundary("requirement.maximum_shape_invalid")
        canonical = tuple(sorted(set(self.required_enforcements), key=lambda item: item.value))
        if not canonical or self.required_enforcements != canonical:
            raise InvalidResourceLimitBoundary("requirement.enforcements_invalid")
        if self.maximum.unlimited and not self.allow_unlimited:
            raise InvalidResourceLimitBoundary("requirement.unlimited_conflict")


@dataclass(frozen=True, slots=True)
class SandboxResourceLimitPolicy:
    format_version: str
    policy_id: SandboxResourceLimitPolicyId
    version: SandboxPolicyVersion
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    filesystem_specification_fingerprint: SandboxArtifactFingerprint
    network_specification_fingerprint: SandboxArtifactFingerprint
    process_specification_fingerprint: SandboxArtifactFingerprint
    requirements: tuple[SandboxResourceLimitRequirement, ...]
    policy_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.format_version,
            self.version,
            self.plan_id,
            self.plan_fingerprint,
            self.filesystem_specification_fingerprint,
            self.network_specification_fingerprint,
            self.process_specification_fingerprint,
            self.requirements,
        )

    @classmethod
    def create(
        cls,
        *,
        version: SandboxPolicyVersion,
        plan: SandboxExecutionPlan,
        filesystem: SandboxFilesystemSpecification,
        network: SandboxNetworkSpecification,
        process: SandboxProcessSpecification,
        requirements: tuple[SandboxResourceLimitRequirement, ...],
    ) -> SandboxResourceLimitPolicy:
        ordered = tuple(sorted(requirements, key=lambda item: item.maximum.dimension.value))
        if len({item.maximum.dimension for item in ordered}) != len(ordered):
            raise InvalidResourceLimitBoundary("policy.requirements_conflict")
        content = (
            RESOURCE_LIMIT_POLICY_FORMAT,
            version,
            plan.plan_id,
            plan.plan_fingerprint,
            filesystem.specification_fingerprint,
            network.specification_fingerprint,
            process.specification_fingerprint,
            ordered,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        identity = derive_identity(SandboxResourceLimitPolicyId, fingerprint)
        return cls(
            RESOURCE_LIMIT_POLICY_FORMAT,
            SandboxResourceLimitPolicyId(identity.value),
            version,
            plan.plan_id,
            plan.plan_fingerprint,
            filesystem.specification_fingerprint,
            network.specification_fingerprint,
            process.specification_fingerprint,
            ordered,
            fingerprint,
        )

    def __post_init__(self) -> None:
        if self.format_version != RESOURCE_LIMIT_POLICY_FORMAT:
            raise InvalidResourceLimitBoundary("policy.format_unsupported")
        if self.requirements != tuple(
            sorted(self.requirements, key=lambda item: item.maximum.dimension.value)
        ):
            raise InvalidResourceLimitBoundary("policy.requirements_not_canonical")
        if len({item.maximum.dimension for item in self.requirements}) != len(self.requirements):
            raise InvalidResourceLimitBoundary("policy.requirements_conflict")
        if SandboxArtifactFingerprint.from_content(self.content()) != self.policy_fingerprint:
            raise InvalidResourceLimitBoundary("policy.fingerprint_mismatch")
        if derive_identity(SandboxResourceLimitPolicyId, self.policy_fingerprint) != self.policy_id:
            raise InvalidResourceLimitBoundary("policy.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxResourceCapabilityFact:
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    supported_maximum: SandboxResourceLimit
    supported_enforcements: tuple[SandboxResourceEnforcement, ...]
    isolation_profiles: tuple[SandboxIsolationProfileId, ...]
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        if (
            self.valid_from.tzinfo is None
            or self.valid_from.utcoffset() is None
            or self.valid_until.tzinfo is None
            or self.valid_until.utcoffset() is None
            or self.valid_until < self.valid_from
        ):
            raise InvalidResourceLimitBoundary("fact.validity_invalid")
        object.__setattr__(
            self,
            "supported_enforcements",
            tuple(sorted(set(self.supported_enforcements), key=lambda item: item.value)),
        )
        object.__setattr__(
            self,
            "isolation_profiles",
            tuple(sorted(set(self.isolation_profiles), key=lambda item: item.value)),
        )


@dataclass(frozen=True, slots=True)
class SandboxResourceCapabilitySnapshot:
    format_version: str
    observed_at: datetime
    completeness: FactCompleteness
    facts: tuple[SandboxResourceCapabilityFact, ...]
    capability_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (self.format_version, self.observed_at, self.completeness, self.facts)

    @classmethod
    def create(
        cls,
        *,
        observed_at: datetime,
        completeness: FactCompleteness,
        facts: tuple[SandboxResourceCapabilityFact, ...],
    ) -> SandboxResourceCapabilitySnapshot:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise InvalidResourceLimitBoundary("snapshot.observed_at_invalid")
        ordered = tuple(sorted(facts, key=lambda item: item.supported_maximum.dimension.value))
        content = (RESOURCE_CAPABILITY_FORMAT, observed_at, completeness, ordered)
        return cls(
            RESOURCE_CAPABILITY_FORMAT,
            observed_at,
            completeness,
            ordered,
            SandboxArtifactFingerprint.from_content(content),
        )

    def __post_init__(self) -> None:
        if self.format_version != RESOURCE_CAPABILITY_FORMAT:
            raise InvalidResourceLimitBoundary("snapshot.format_unsupported")
        if self.facts != tuple(
            sorted(self.facts, key=lambda item: item.supported_maximum.dimension.value)
        ):
            raise InvalidResourceLimitBoundary("snapshot.facts_not_canonical")
        if SandboxArtifactFingerprint.from_content(self.content()) != self.capability_fingerprint:
            raise InvalidResourceLimitBoundary("snapshot.fingerprint_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxResourceGrant:
    requested: SandboxResourceLimit
    policy_maximum: SandboxResourceLimit
    supported_maximum: SandboxResourceLimit
    effective: SandboxResourceLimit
    required_enforcements: tuple[SandboxResourceEnforcement, ...]
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.required_enforcements != tuple(
            sorted(set(self.required_enforcements), key=lambda item: item.value)
        ):
            raise InvalidResourceLimitBoundary("grant.enforcements_not_canonical")
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidResourceLimitBoundary("grant.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxResourceDenial:
    dimension: SandboxResourceDimension
    reason: SandboxResourceDenialReason
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidResourceLimitBoundary("denial.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxResourceGrantSet:
    grant_set_id: SandboxResourceGrantSetId
    grant_set_fingerprint: SandboxArtifactFingerprint
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    request_fingerprint: SandboxArtifactFingerprint
    capability_grant_set_fingerprint: SandboxArtifactFingerprint
    filesystem_specification_fingerprint: SandboxArtifactFingerprint
    network_specification_fingerprint: SandboxArtifactFingerprint
    process_specification_fingerprint: SandboxArtifactFingerprint
    policy_id: SandboxResourceLimitPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    capability_snapshot_fingerprint: SandboxArtifactFingerprint
    evaluated_at: datetime
    grants: tuple[SandboxResourceGrant, ...]
    denials: tuple[SandboxResourceDenial, ...]
    diagnostics: tuple[str, ...]
    occurred_at: datetime

    def content(self) -> tuple[object, ...]:
        return (
            self.plan_id,
            self.plan_fingerprint,
            self.request_fingerprint,
            self.capability_grant_set_fingerprint,
            self.filesystem_specification_fingerprint,
            self.network_specification_fingerprint,
            self.process_specification_fingerprint,
            self.policy_id,
            self.policy_fingerprint,
            self.capability_snapshot_fingerprint,
            self.evaluated_at,
            self.grants,
            self.denials,
            self.diagnostics,
        )

    def __post_init__(self) -> None:
        if (
            self.evaluated_at.tzinfo is None
            or self.evaluated_at.utcoffset() is None
            or self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() is None
        ):
            raise InvalidResourceLimitBoundary("grant_set.timestamp_invalid")
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.grant_set_fingerprint:
            raise InvalidResourceLimitBoundary("grant_set.fingerprint_mismatch")
        if derive_identity(SandboxResourceGrantSetId, expected) != self.grant_set_id:
            raise InvalidResourceLimitBoundary("grant_set.identity_mismatch")
        if self.grants != tuple(
            sorted(self.grants, key=lambda item: item.effective.dimension.value)
        ):
            raise InvalidResourceLimitBoundary("grant_set.grants_not_canonical")
        if self.denials != tuple(sorted(self.denials, key=lambda item: item.dimension.value)):
            raise InvalidResourceLimitBoundary("grant_set.denials_not_canonical")
        if self.diagnostics != tuple(sorted(set(self.diagnostics))):
            raise InvalidResourceLimitBoundary("grant_set.diagnostics_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxResourceSpecification:
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    grant_set_id: SandboxResourceGrantSetId
    grant_set_fingerprint: SandboxArtifactFingerprint
    filesystem_specification_fingerprint: SandboxArtifactFingerprint
    network_specification_fingerprint: SandboxArtifactFingerprint
    process_specification_fingerprint: SandboxArtifactFingerprint
    effective_limits: tuple[SandboxResourceLimit, ...]
    specification_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.plan_id,
            self.plan_fingerprint,
            self.grant_set_id,
            self.grant_set_fingerprint,
            self.filesystem_specification_fingerprint,
            self.network_specification_fingerprint,
            self.process_specification_fingerprint,
            self.effective_limits,
        )

    def __post_init__(self) -> None:
        if self.effective_limits != tuple(
            sorted(self.effective_limits, key=lambda item: item.dimension.value)
        ):
            raise InvalidResourceLimitBoundary("specification.limits_not_canonical")
        if len({item.dimension for item in self.effective_limits}) != len(self.effective_limits):
            raise InvalidResourceLimitBoundary("specification.limits_conflict")
        if (
            SandboxArtifactFingerprint.from_content(self.content())
            != self.specification_fingerprint
        ):
            raise InvalidResourceLimitBoundary("specification.fingerprint_mismatch")


class SandboxResourceLimitService:
    """Derive enforceable quota descriptions without measuring resources."""

    def evaluate(
        self,
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        filesystem: SandboxFilesystemSpecification,
        network: SandboxNetworkSpecification,
        process: SandboxProcessSpecification,
        facts: SandboxResourceCapabilitySnapshot,
        policy: SandboxResourceLimitPolicy,
        requests: tuple[SandboxResourceLimitRequest, ...],
        *,
        evaluated_at: datetime,
        occurred_at: datetime,
    ) -> SandboxResourceGrantSet:
        self._validate_bindings(plan, capabilities, filesystem, network, process, policy)
        if (
            evaluated_at.tzinfo is None
            or evaluated_at.utcoffset() is None
            or occurred_at.tzinfo is None
            or occurred_at.utcoffset() is None
        ):
            raise InvalidResourceLimitBoundary("grant_set.timestamp_invalid")
        ordered_requests = tuple(sorted(requests, key=lambda item: item.limit.dimension.value))
        request_fingerprint = SandboxArtifactFingerprint.from_content(
            (plan.plan_id, plan.plan_fingerprint, ordered_requests)
        )
        requests_by_dimension: dict[SandboxResourceDimension, list[SandboxResourceLimit]] = {}
        for request in ordered_requests:
            requests_by_dimension.setdefault(request.limit.dimension, []).append(request.limit)
        facts_by_dimension: dict[SandboxResourceDimension, list[SandboxResourceCapabilityFact]] = {}
        for fact in facts.facts:
            facts_by_dimension.setdefault(fact.supported_maximum.dimension, []).append(fact)
        requirements = {
            requirement.maximum.dimension: requirement for requirement in policy.requirements
        }
        dimensions = sorted(
            set(requests_by_dimension)
            | {
                dimension for dimension, requirement in requirements.items() if requirement.required
            },
            key=lambda item: item.value,
        )
        grants: list[SandboxResourceGrant] = []
        denials: list[SandboxResourceDenial] = []
        for dimension in dimensions:
            grant, denial = self._evaluate_dimension(
                plan,
                filesystem,
                network,
                process,
                facts.completeness,
                requirements.get(dimension),
                requests_by_dimension.get(dimension, []),
                facts_by_dimension.get(dimension, []),
                evaluated_at,
            )
            if grant is not None:
                grants.append(grant)
            if denial is not None:
                denials.append(denial)
        ordered_grants = tuple(sorted(grants, key=lambda item: item.effective.dimension.value))
        ordered_denials = tuple(sorted(denials, key=lambda item: item.dimension.value))
        diagnostics = tuple(
            sorted({code for denial in ordered_denials for code in denial.rationale_codes})
        )
        content = (
            plan.plan_id,
            plan.plan_fingerprint,
            request_fingerprint,
            capabilities.grant_set_fingerprint,
            filesystem.specification_fingerprint,
            network.specification_fingerprint,
            process.specification_fingerprint,
            policy.policy_id,
            policy.policy_fingerprint,
            facts.capability_fingerprint,
            evaluated_at,
            ordered_grants,
            ordered_denials,
            diagnostics,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        identity = derive_identity(SandboxResourceGrantSetId, fingerprint)
        return SandboxResourceGrantSet(
            SandboxResourceGrantSetId(identity.value),
            fingerprint,
            plan.plan_id,
            plan.plan_fingerprint,
            request_fingerprint,
            capabilities.grant_set_fingerprint,
            filesystem.specification_fingerprint,
            network.specification_fingerprint,
            process.specification_fingerprint,
            policy.policy_id,
            policy.policy_fingerprint,
            facts.capability_fingerprint,
            evaluated_at,
            ordered_grants,
            ordered_denials,
            diagnostics,
            occurred_at,
        )

    @staticmethod
    def build_specification(
        grant_set: SandboxResourceGrantSet,
    ) -> SandboxResourceSpecification:
        limits = tuple(grant.effective for grant in grant_set.grants)
        content = (
            grant_set.plan_id,
            grant_set.plan_fingerprint,
            grant_set.grant_set_id,
            grant_set.grant_set_fingerprint,
            grant_set.filesystem_specification_fingerprint,
            grant_set.network_specification_fingerprint,
            grant_set.process_specification_fingerprint,
            limits,
        )
        return SandboxResourceSpecification(
            grant_set.plan_id,
            grant_set.plan_fingerprint,
            grant_set.grant_set_id,
            grant_set.grant_set_fingerprint,
            grant_set.filesystem_specification_fingerprint,
            grant_set.network_specification_fingerprint,
            grant_set.process_specification_fingerprint,
            limits,
            SandboxArtifactFingerprint.from_content(content),
        )

    @staticmethod
    def _validate_bindings(
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        filesystem: SandboxFilesystemSpecification,
        network: SandboxNetworkSpecification,
        process: SandboxProcessSpecification,
        policy: SandboxResourceLimitPolicy,
    ) -> None:
        diagnostics = []
        for name, candidate_id, candidate_fingerprint in (
            ("capability", capabilities.plan_id, capabilities.plan_fingerprint),
            ("filesystem", filesystem.plan_id, filesystem.plan_fingerprint),
            ("network", network.plan_id, network.plan_fingerprint),
            ("process", process.plan_id, process.plan_fingerprint),
            ("policy", policy.plan_id, policy.plan_fingerprint),
        ):
            if candidate_id != plan.plan_id:
                diagnostics.append(f"binding.{name}_plan_identity_mismatch")
            if candidate_fingerprint != plan.plan_fingerprint:
                diagnostics.append(f"binding.{name}_plan_fingerprint_mismatch")
        if policy.filesystem_specification_fingerprint != filesystem.specification_fingerprint:
            diagnostics.append("binding.policy_filesystem_mismatch")
        if policy.network_specification_fingerprint != network.specification_fingerprint:
            diagnostics.append("binding.policy_network_mismatch")
        if policy.process_specification_fingerprint != process.specification_fingerprint:
            diagnostics.append("binding.policy_process_mismatch")
        if process.filesystem_specification_fingerprint != filesystem.specification_fingerprint:
            diagnostics.append("binding.process_filesystem_mismatch")
        if process.network_specification_fingerprint != network.specification_fingerprint:
            diagnostics.append("binding.process_network_mismatch")
        if diagnostics:
            raise InvalidResourceLimitBoundary(",".join(sorted(diagnostics)))

    @classmethod
    def _evaluate_dimension(
        cls,
        plan: SandboxExecutionPlan,
        filesystem: SandboxFilesystemSpecification,
        network: SandboxNetworkSpecification,
        process: SandboxProcessSpecification,
        completeness: FactCompleteness,
        requirement: SandboxResourceLimitRequirement | None,
        requests: list[SandboxResourceLimit],
        facts: list[SandboxResourceCapabilityFact],
        evaluated_at: datetime,
    ) -> tuple[SandboxResourceGrant | None, SandboxResourceDenial | None]:
        dimension = (
            requirement.maximum.dimension if requirement is not None else requests[0].dimension
        )
        if len(requests) != 1:
            reason = (
                SandboxResourceDenialReason.LIMIT_ABSENT
                if not requests
                else SandboxResourceDenialReason.CONTRADICTORY_LIMITS
            )
            return None, cls._denial(dimension, reason, "request.correspondence")
        requested = requests[0]
        if requirement is None:
            return None, cls._denial(
                dimension,
                SandboxResourceDenialReason.POLICY_EXCEEDED,
                "policy.requirement_absent",
            )
        if completeness is FactCompleteness.INCOMPLETE:
            return None, cls._denial(
                dimension, SandboxResourceDenialReason.INCOMPLETE, "facts.incomplete"
            )
        if completeness is not FactCompleteness.COMPLETE:
            return None, cls._denial(
                dimension, SandboxResourceDenialReason.UNAVAILABLE, "facts.unavailable"
            )
        if len(facts) != 1:
            reason = (
                SandboxResourceDenialReason.LIMIT_ABSENT
                if not facts
                else SandboxResourceDenialReason.CONTRADICTORY_LIMITS
            )
            return None, cls._denial(dimension, reason, "fact.correspondence")
        fact = facts[0]
        maximum = requirement.maximum
        supported = fact.supported_maximum
        if requested.unit is not maximum.unit or requested.unit is not supported.unit:
            return None, cls._denial(
                dimension, SandboxResourceDenialReason.UNIT_MISMATCH, "limit.unit_mismatch"
            )
        if requested.scope is not maximum.scope or requested.scope is not supported.scope:
            return None, cls._denial(
                dimension, SandboxResourceDenialReason.SCOPE_MISMATCH, "limit.scope_mismatch"
            )
        if (
            fact.plan_id != plan.plan_id
            or fact.plan_fingerprint != plan.plan_fingerprint
            or plan.isolation_profile_id not in fact.isolation_profiles
        ):
            return None, cls._denial(
                dimension, SandboxResourceDenialReason.SCOPE_MISMATCH, "fact.binding_mismatch"
            )
        if not fact.valid_from <= evaluated_at <= fact.valid_until:
            return None, cls._denial(dimension, SandboxResourceDenialReason.STALE, "fact.stale")
        if not set(requirement.required_enforcements) <= set(fact.supported_enforcements):
            return None, cls._denial(
                dimension,
                SandboxResourceDenialReason.UNSUPPORTED_ENFORCEMENT,
                "fact.enforcement_unsupported",
            )
        effective, denial = cls._intersect(
            requested, maximum, supported, requirement.allow_unlimited
        )
        if denial is not None:
            return None, cls._denial(dimension, denial, f"limit.{denial.value}")
        assert effective is not None
        specification_maximum = cls._specification_maximum(dimension, filesystem, network, process)
        if (
            specification_maximum is not None
            and not effective.unlimited
            and effective.hard is not None
            and effective.hard > specification_maximum
        ):
            return None, cls._denial(
                dimension,
                SandboxResourceDenialReason.POLICY_EXCEEDED,
                "specification.maximum_exceeded",
            )
        return (
            SandboxResourceGrant(
                requested,
                maximum,
                supported,
                effective,
                requirement.required_enforcements,
                ("resource.intersection_satisfied",),
            ),
            None,
        )

    @staticmethod
    def _intersect(
        requested: SandboxResourceLimit,
        maximum: SandboxResourceLimit,
        supported: SandboxResourceLimit,
        allow_unlimited: bool,
    ) -> tuple[SandboxResourceLimit | None, SandboxResourceDenialReason | None]:
        values = (requested, maximum, supported)
        if any(value.dimension is not requested.dimension for value in values):
            return None, SandboxResourceDenialReason.CONTRADICTORY_LIMITS
        if requested.unlimited:
            if allow_unlimited and maximum.unlimited and supported.unlimited:
                return requested, None
            return None, SandboxResourceDenialReason.POLICY_EXCEEDED
        if maximum.unlimited:
            policy_hard = requested.hard
        else:
            policy_hard = maximum.hard
        if supported.unlimited:
            support_hard = requested.hard
        else:
            support_hard = supported.hard
        assert requested.hard is not None
        assert policy_hard is not None
        assert support_hard is not None
        hard = min(requested.hard, policy_hard, support_hard)
        soft = _minimum_optional(
            requested.soft,
            maximum.soft if not maximum.unlimited else None,
            supported.soft if not supported.unlimited else None,
            upper=hard,
        )
        burst = _minimum_optional(
            requested.burst,
            maximum.burst if not maximum.unlimited else None,
            supported.burst if not supported.unlimited else None,
            upper=hard,
        )
        grace = _minimum_optional(
            requested.grace,
            maximum.grace if not maximum.unlimited else None,
            supported.grace if not supported.unlimited else None,
            upper=hard,
        )
        return (
            SandboxResourceLimit(
                requested.dimension,
                requested.unit,
                requested.scope,
                hard,
                soft,
                burst,
                grace,
            ),
            None,
        )

    @staticmethod
    def _specification_maximum(
        dimension: SandboxResourceDimension,
        filesystem: SandboxFilesystemSpecification,
        network: SandboxNetworkSpecification,
        process: SandboxProcessSpecification,
    ) -> int | None:
        values: list[int] = []
        if dimension in {
            SandboxResourceDimension.DISK_SPACE,
            SandboxResourceDimension.FILE_SIZE,
        }:
            values = [grant.limits.maximum_bytes for grant in filesystem.grants]
        elif dimension is SandboxResourceDimension.FILE_COUNT:
            values = [grant.limits.maximum_files for grant in filesystem.grants]
        elif dimension is SandboxResourceDimension.NETWORK_CONNECTIONS:
            values = [grant.limits.maximum_connections for grant in network.grants]
        elif dimension is SandboxResourceDimension.NETWORK_BYTES_SENT:
            values = [grant.limits.maximum_bytes_sent for grant in network.grants]
        elif dimension is SandboxResourceDimension.NETWORK_BYTES_RECEIVED:
            values = [grant.limits.maximum_bytes_received for grant in network.grants]
        elif dimension is SandboxResourceDimension.PROCESS_COUNT:
            values = [grant.limits.maximum_processes for grant in process.grants]
        elif dimension is SandboxResourceDimension.PROCESS_TREE_DEPTH:
            values = [grant.limits.maximum_tree_depth for grant in process.grants]
        elif dimension is SandboxResourceDimension.HANDLE_COUNT:
            values = [grant.limits.maximum_inheritable_handles for grant in process.grants]
        elif dimension is SandboxResourceDimension.STARTUP_DURATION:
            values = [grant.limits.startup_timeout_seconds * 1000 for grant in process.grants]
        elif dimension is SandboxResourceDimension.TERMINATION_GRACE:
            values = [grant.limits.termination_grace_seconds * 1000 for grant in process.grants]
        return min(values) if values else None

    @staticmethod
    def _denial(
        dimension: SandboxResourceDimension,
        reason: SandboxResourceDenialReason,
        code: str,
    ) -> SandboxResourceDenial:
        return SandboxResourceDenial(dimension, reason, (code,))


def _minimum_optional(
    requested: int | None,
    maximum: int | None,
    supported: int | None,
    *,
    upper: int,
) -> int | None:
    if requested is None:
        return None
    candidates = [requested, upper]
    if maximum is not None:
        candidates.append(maximum)
    if supported is not None:
        candidates.append(supported)
    return min(candidates)
