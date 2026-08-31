"""Pure process containment contracts without process creation or signaling."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .capability_grants import SandboxCapabilityGrantSet
from .errors import InvalidProcessBoundary
from .execution_plan import (
    SandboxExecutionPlan,
    SandboxLogicalEntrypoint,
    SandboxRuntimeDescriptor,
)
from .facts import FactCompleteness, SandboxCapabilityScopeKind
from .filesystem_boundary import (
    SandboxFilesystemOperation,
    SandboxFilesystemResource,
    SandboxFilesystemSpecification,
)
from .identities import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxIsolationProfileId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxPolicyVersion,
    SandboxProcessGrantSetId,
    SandboxProcessPolicyId,
    derive_identity,
)
from .network_boundary import SandboxNetworkSpecification

PROCESS_POLICY_FORMAT = "sandbox-process-policy-v1"
PROCESS_CAPABILITY_FORMAT = "sandbox-process-capabilities-v1"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/=@+,-]{0,255}$")
_ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SHELL_MARKERS = frozenset(";&|`$><\n\r\t")


class SandboxProcessOperation(StrEnum):
    START = "start"
    SPAWN_CHILD = "spawn_child"
    SIGNAL = "signal"
    TERMINATE = "terminate"
    INSPECT_STATUS = "inspect_status"


class SandboxProcessArgumentKind(StrEnum):
    TOKEN = "token"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    OPAQUE_REFERENCE = "opaque_reference"


class SandboxProcessStdioPolicy(StrEnum):
    CLOSED = "closed"
    DISCARD = "discard"
    CAPTURED = "captured"
    LOGICAL_INPUT = "logical_input"


class SandboxChildProcessPolicy(StrEnum):
    DENY = "deny"
    SAME_SUPERVISED_TREE = "same_supervised_tree"


class SandboxHandleInheritancePolicy(StrEnum):
    NONE = "none"
    EXPLICIT_ALLOWLIST = "explicit_allowlist"


@dataclass(frozen=True, slots=True)
class SandboxProcessStartupRequirements:
    validate_support_before_start: bool
    start_inside_boundary: bool


@dataclass(frozen=True, slots=True)
class SandboxProcessTerminationRequirements:
    terminate_complete_tree: bool
    force_after_grace_period: bool


@dataclass(frozen=True, slots=True)
class SandboxProcessCleanupRequirements:
    close_inherited_handles: bool
    verify_complete_tree_exit: bool


class SandboxProcessEnforcement(StrEnum):
    KILL_ON_BOUNDARY_CLOSE = "kill_on_boundary_close"
    DESCENDANT_TRACKING = "descendant_tracking"
    NO_DETACHED_PROCESS = "no_detached_process"
    NO_INHERITED_HOST_HANDLES = "no_inherited_host_handles"
    VERIFIED_TERMINATION = "verified_termination"
    RUNTIME_ALLOWLIST = "runtime_allowlist"
    EXECUTABLE_ARTIFACT_BINDING = "executable_artifact_binding"


class SandboxProcessDenialReason(StrEnum):
    RUNTIME_DENIED = "runtime_denied"
    RUNTIME_UNSUPPORTED = "runtime_unsupported"
    ENTRYPOINT_MISMATCH = "entrypoint_mismatch"
    CAPABILITY_ABSENT = "capability_absent"
    CHILD_PROCESS_DENIED = "child_process_denied"
    SHELL_SEMANTICS_DETECTED = "shell_semantics_detected"
    ENVIRONMENT_DENIED = "environment_denied"
    HANDLE_INHERITANCE_DENIED = "handle_inheritance_denied"
    DETACHED_PROCESS_DENIED = "detached_process_denied"
    ENFORCEMENT_UNSUPPORTED = "enforcement_unsupported"
    MISMATCH = "mismatch"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"
    LIMIT_EXCEEDED = "limit_exceeded"


@dataclass(frozen=True, slots=True)
class SandboxProcessArgument:
    kind: SandboxProcessArgumentKind
    token: str | None = None
    integer: int | None = None
    boolean: bool | None = None
    reference: OpaqueReference | None = None

    def __post_init__(self) -> None:
        populated = sum(
            value is not None for value in (self.token, self.integer, self.boolean, self.reference)
        )
        if populated != 1:
            raise InvalidProcessBoundary("argument.value_invalid")
        if self.kind is SandboxProcessArgumentKind.TOKEN:
            if (
                self.token is None
                or not _TOKEN.fullmatch(self.token)
                or any(marker in self.token for marker in _SHELL_MARKERS)
            ):
                raise InvalidProcessBoundary("argument.shell_semantics_detected")
        elif self.kind is SandboxProcessArgumentKind.INTEGER:
            if (
                not isinstance(self.integer, int)
                or isinstance(self.integer, bool)
                or self.token is not None
            ):
                raise InvalidProcessBoundary("argument.integer_invalid")
        elif self.kind is SandboxProcessArgumentKind.BOOLEAN:
            if not isinstance(self.boolean, bool):
                raise InvalidProcessBoundary("argument.boolean_invalid")
        elif self.reference is None:
            raise InvalidProcessBoundary("argument.reference_invalid")

    def encoded_size(self) -> int:
        if self.token is not None:
            return len(self.token.encode("utf-8"))
        if self.integer is not None:
            return len(str(self.integer))
        if self.boolean is not None:
            return 4 if self.boolean else 5
        assert self.reference is not None
        return len(self.reference.value.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class SandboxProcessEnvironmentEntry:
    name: str
    value_ref: OpaqueReference

    def __post_init__(self) -> None:
        if not _ENVIRONMENT_NAME.fullmatch(self.name):
            raise InvalidProcessBoundary("environment.name_invalid")


@dataclass(frozen=True, slots=True)
class SandboxProcessLimits:
    maximum_processes: int
    maximum_tree_depth: int
    maximum_inheritable_handles: int
    maximum_arguments: int
    maximum_argument_bytes: int
    maximum_environment_entries: int
    maximum_environment_bytes: int
    startup_timeout_seconds: int
    termination_grace_seconds: int

    def __post_init__(self) -> None:
        values = (
            self.maximum_processes,
            self.maximum_tree_depth,
            self.maximum_arguments,
            self.maximum_argument_bytes,
            self.maximum_environment_entries,
            self.maximum_environment_bytes,
            self.startup_timeout_seconds,
            self.termination_grace_seconds,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in values
        ):
            raise InvalidProcessBoundary("limits.must_be_positive")
        if (
            not isinstance(self.maximum_inheritable_handles, int)
            or isinstance(self.maximum_inheritable_handles, bool)
            or self.maximum_inheritable_handles < 0
        ):
            raise InvalidProcessBoundary("limits.handles_invalid")

    def within(self, other: SandboxProcessLimits) -> bool:
        return all(
            current <= maximum
            for current, maximum in zip(
                (
                    self.maximum_processes,
                    self.maximum_tree_depth,
                    self.maximum_inheritable_handles,
                    self.maximum_arguments,
                    self.maximum_argument_bytes,
                    self.maximum_environment_entries,
                    self.maximum_environment_bytes,
                    self.startup_timeout_seconds,
                    self.termination_grace_seconds,
                ),
                (
                    other.maximum_processes,
                    other.maximum_tree_depth,
                    other.maximum_inheritable_handles,
                    other.maximum_arguments,
                    other.maximum_argument_bytes,
                    other.maximum_environment_entries,
                    other.maximum_environment_bytes,
                    other.startup_timeout_seconds,
                    other.termination_grace_seconds,
                ),
                strict=True,
            )
        )


@dataclass(frozen=True, slots=True)
class SandboxProcessOperationCapability:
    operation: SandboxProcessOperation
    capability: str


@dataclass(frozen=True, slots=True)
class SandboxProcessRequest:
    runtime: SandboxRuntimeDescriptor
    entrypoint: SandboxLogicalEntrypoint
    artifact_fingerprint: SandboxArtifactFingerprint
    operations: tuple[SandboxProcessOperation, ...]
    arguments: tuple[SandboxProcessArgument, ...]
    working_root: SandboxFilesystemResource
    environment: tuple[SandboxProcessEnvironmentEntry, ...]
    stdin: SandboxProcessStdioPolicy
    stdout: SandboxProcessStdioPolicy
    stderr: SandboxProcessStdioPolicy
    child_policy: SandboxChildProcessPolicy
    handle_policy: SandboxHandleInheritancePolicy
    inheritable_handle_refs: tuple[OpaqueReference, ...]
    detached: bool
    startup_requirements: SandboxProcessStartupRequirements
    termination_requirements: SandboxProcessTerminationRequirements
    cleanup_requirements: SandboxProcessCleanupRequirements
    limits: SandboxProcessLimits

    def __post_init__(self) -> None:
        if not self.operations or len(set(self.operations)) != len(self.operations):
            raise InvalidProcessBoundary("request.operations_invalid")
        object.__setattr__(
            self,
            "operations",
            tuple(sorted(self.operations, key=lambda item: item.value)),
        )
        if len({item.name for item in self.environment}) != len(self.environment):
            raise InvalidProcessBoundary("request.environment_conflict")
        object.__setattr__(
            self,
            "environment",
            tuple(sorted(self.environment, key=lambda item: item.name)),
        )
        if len(set(self.inheritable_handle_refs)) != len(self.inheritable_handle_refs):
            raise InvalidProcessBoundary("request.handle_refs_conflict")
        object.__setattr__(
            self,
            "inheritable_handle_refs",
            tuple(sorted(self.inheritable_handle_refs, key=lambda item: item.value)),
        )
        if (
            self.handle_policy is SandboxHandleInheritancePolicy.NONE
            and self.inheritable_handle_refs
        ):
            raise InvalidProcessBoundary("request.handle_policy_conflict")
        if (
            SandboxProcessOperation.SPAWN_CHILD in self.operations
            and self.child_policy is SandboxChildProcessPolicy.DENY
        ):
            raise InvalidProcessBoundary("request.child_policy_conflict")
        if not (
            self.startup_requirements.validate_support_before_start
            and self.startup_requirements.start_inside_boundary
            and self.termination_requirements.terminate_complete_tree
            and self.termination_requirements.force_after_grace_period
            and self.cleanup_requirements.close_inherited_handles
            and self.cleanup_requirements.verify_complete_tree_exit
        ):
            raise InvalidProcessBoundary("request.lifecycle_requirements_incomplete")


@dataclass(frozen=True, slots=True)
class SandboxProcessPolicy:
    format_version: str
    policy_id: SandboxProcessPolicyId
    version: SandboxPolicyVersion
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    runtime: SandboxRuntimeDescriptor
    entrypoint: SandboxLogicalEntrypoint
    allowed_operations: tuple[SandboxProcessOperation, ...]
    capability_requirements: tuple[SandboxProcessOperationCapability, ...]
    allowed_argument_kinds: tuple[SandboxProcessArgumentKind, ...]
    allowed_working_roots: tuple[SandboxFilesystemResource, ...]
    allowed_environment_names: tuple[str, ...]
    allowed_stdio: tuple[SandboxProcessStdioPolicy, ...]
    child_policy: SandboxChildProcessPolicy
    handle_policy: SandboxHandleInheritancePolicy
    allowed_handle_refs: tuple[OpaqueReference, ...]
    startup_requirements: SandboxProcessStartupRequirements
    termination_requirements: SandboxProcessTerminationRequirements
    cleanup_requirements: SandboxProcessCleanupRequirements
    limits: SandboxProcessLimits
    required_enforcements: tuple[SandboxProcessEnforcement, ...]
    policy_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.format_version,
            self.version,
            self.plan_id,
            self.plan_fingerprint,
            self.runtime,
            self.entrypoint,
            self.allowed_operations,
            self.capability_requirements,
            self.allowed_argument_kinds,
            self.allowed_working_roots,
            self.allowed_environment_names,
            self.allowed_stdio,
            self.child_policy,
            self.handle_policy,
            self.allowed_handle_refs,
            self.startup_requirements,
            self.termination_requirements,
            self.cleanup_requirements,
            self.limits,
            self.required_enforcements,
        )

    @classmethod
    def create(
        cls,
        *,
        version: SandboxPolicyVersion,
        plan: SandboxExecutionPlan,
        allowed_operations: tuple[SandboxProcessOperation, ...],
        capability_requirements: tuple[SandboxProcessOperationCapability, ...],
        allowed_argument_kinds: tuple[SandboxProcessArgumentKind, ...],
        allowed_working_roots: tuple[SandboxFilesystemResource, ...],
        allowed_environment_names: tuple[str, ...],
        allowed_stdio: tuple[SandboxProcessStdioPolicy, ...],
        child_policy: SandboxChildProcessPolicy,
        handle_policy: SandboxHandleInheritancePolicy,
        allowed_handle_refs: tuple[OpaqueReference, ...],
        startup_requirements: SandboxProcessStartupRequirements,
        termination_requirements: SandboxProcessTerminationRequirements,
        cleanup_requirements: SandboxProcessCleanupRequirements,
        limits: SandboxProcessLimits,
        required_enforcements: tuple[SandboxProcessEnforcement, ...],
    ) -> SandboxProcessPolicy:
        operations = tuple(sorted(set(allowed_operations), key=lambda item: item.value))
        requirements = tuple(
            sorted(
                capability_requirements,
                key=lambda item: (item.operation.value, item.capability),
            )
        )
        argument_kinds = tuple(sorted(set(allowed_argument_kinds), key=lambda item: item.value))
        roots = tuple(sorted(set(allowed_working_roots), key=lambda item: item.value))
        environment_names = tuple(sorted(set(allowed_environment_names)))
        stdio = tuple(sorted(set(allowed_stdio), key=lambda item: item.value))
        handles = tuple(sorted(set(allowed_handle_refs), key=lambda item: item.value))
        enforcements = tuple(sorted(set(required_enforcements), key=lambda item: item.value))
        content = (
            PROCESS_POLICY_FORMAT,
            version,
            plan.plan_id,
            plan.plan_fingerprint,
            plan.runtime,
            plan.entrypoint,
            operations,
            requirements,
            argument_kinds,
            roots,
            environment_names,
            stdio,
            child_policy,
            handle_policy,
            handles,
            startup_requirements,
            termination_requirements,
            cleanup_requirements,
            limits,
            enforcements,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        identity = derive_identity(SandboxProcessPolicyId, fingerprint)
        return cls(
            PROCESS_POLICY_FORMAT,
            SandboxProcessPolicyId(identity.value),
            version,
            plan.plan_id,
            plan.plan_fingerprint,
            plan.runtime,
            plan.entrypoint,
            operations,
            requirements,
            argument_kinds,
            roots,
            environment_names,
            stdio,
            child_policy,
            handle_policy,
            handles,
            startup_requirements,
            termination_requirements,
            cleanup_requirements,
            limits,
            enforcements,
            fingerprint,
        )

    def __post_init__(self) -> None:
        if self.format_version != PROCESS_POLICY_FORMAT:
            raise InvalidProcessBoundary("policy.format_unsupported")
        if (
            self.allowed_operations
            != tuple(sorted(set(self.allowed_operations), key=lambda item: item.value))
            or self.capability_requirements
            != tuple(
                sorted(
                    set(self.capability_requirements),
                    key=lambda item: (item.operation.value, item.capability),
                )
            )
            or self.allowed_argument_kinds
            != tuple(sorted(set(self.allowed_argument_kinds), key=lambda item: item.value))
            or self.allowed_working_roots
            != tuple(sorted(set(self.allowed_working_roots), key=lambda item: item.value))
            or self.allowed_environment_names != tuple(sorted(set(self.allowed_environment_names)))
            or self.allowed_stdio
            != tuple(sorted(set(self.allowed_stdio), key=lambda item: item.value))
            or self.allowed_handle_refs
            != tuple(sorted(set(self.allowed_handle_refs), key=lambda item: item.value))
            or self.required_enforcements
            != tuple(sorted(set(self.required_enforcements), key=lambda item: item.value))
        ):
            raise InvalidProcessBoundary("policy.collections_not_canonical")
        mapping = tuple(item.operation for item in self.capability_requirements)
        if len(set(mapping)) != len(mapping) or set(mapping) != set(self.allowed_operations):
            raise InvalidProcessBoundary("policy.capability_mapping_incomplete")
        required = set(SandboxProcessEnforcement)
        if not required <= set(self.required_enforcements):
            raise InvalidProcessBoundary("policy.enforcements_incomplete")
        if not _lifecycle_complete(
            self.startup_requirements,
            self.termination_requirements,
            self.cleanup_requirements,
        ):
            raise InvalidProcessBoundary("policy.lifecycle_requirements_incomplete")
        if SandboxArtifactFingerprint.from_content(self.content()) != self.policy_fingerprint:
            raise InvalidProcessBoundary("policy.fingerprint_mismatch")
        if derive_identity(SandboxProcessPolicyId, self.policy_fingerprint) != self.policy_id:
            raise InvalidProcessBoundary("policy.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxProcessCapabilityFact:
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    runtime: SandboxRuntimeDescriptor
    entrypoint: SandboxLogicalEntrypoint
    artifact_fingerprint: SandboxArtifactFingerprint
    operations: tuple[SandboxProcessOperation, ...]
    scope_ref: OpaqueReference
    allowed_environment_names: tuple[str, ...]
    allowed_handle_refs: tuple[OpaqueReference, ...]
    child_policy: SandboxChildProcessPolicy
    handle_policy: SandboxHandleInheritancePolicy
    startup_requirements: SandboxProcessStartupRequirements
    termination_requirements: SandboxProcessTerminationRequirements
    cleanup_requirements: SandboxProcessCleanupRequirements
    limits: SandboxProcessLimits
    supported_enforcements: tuple[SandboxProcessEnforcement, ...]
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
            raise InvalidProcessBoundary("fact.validity_invalid")
        if not _lifecycle_complete(
            self.startup_requirements,
            self.termination_requirements,
            self.cleanup_requirements,
        ):
            raise InvalidProcessBoundary("fact.lifecycle_requirements_incomplete")
        if (
            SandboxProcessOperation.SPAWN_CHILD in self.operations
            and self.child_policy is SandboxChildProcessPolicy.DENY
        ):
            raise InvalidProcessBoundary("fact.child_policy_conflict")
        for name in (
            "operations",
            "allowed_environment_names",
            "allowed_handle_refs",
            "supported_enforcements",
            "isolation_profiles",
        ):
            values = getattr(self, name)
            key = (lambda item: item.value) if name not in {"allowed_environment_names"} else None
            object.__setattr__(self, name, tuple(sorted(set(values), key=key)))


@dataclass(frozen=True, slots=True)
class SandboxProcessCapabilitySnapshot:
    format_version: str
    observed_at: datetime
    completeness: FactCompleteness
    facts: tuple[SandboxProcessCapabilityFact, ...]
    capability_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (self.format_version, self.observed_at, self.completeness, self.facts)

    @classmethod
    def create(
        cls,
        *,
        observed_at: datetime,
        completeness: FactCompleteness,
        facts: tuple[SandboxProcessCapabilityFact, ...],
    ) -> SandboxProcessCapabilitySnapshot:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise InvalidProcessBoundary("snapshot.observed_at_invalid")
        ordered = tuple(sorted(facts, key=repr))
        content = (PROCESS_CAPABILITY_FORMAT, observed_at, completeness, ordered)
        return cls(
            PROCESS_CAPABILITY_FORMAT,
            observed_at,
            completeness,
            ordered,
            SandboxArtifactFingerprint.from_content(content),
        )

    def __post_init__(self) -> None:
        if self.format_version != PROCESS_CAPABILITY_FORMAT:
            raise InvalidProcessBoundary("snapshot.format_unsupported")
        if self.facts != tuple(sorted(self.facts, key=repr)):
            raise InvalidProcessBoundary("snapshot.facts_not_canonical")
        if SandboxArtifactFingerprint.from_content(self.content()) != self.capability_fingerprint:
            raise InvalidProcessBoundary("snapshot.fingerprint_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxProcessGrant:
    runtime: SandboxRuntimeDescriptor
    entrypoint: SandboxLogicalEntrypoint
    artifact_fingerprint: SandboxArtifactFingerprint
    operations: tuple[SandboxProcessOperation, ...]
    arguments: tuple[SandboxProcessArgument, ...]
    working_root: SandboxFilesystemResource
    environment: tuple[SandboxProcessEnvironmentEntry, ...]
    stdin: SandboxProcessStdioPolicy
    stdout: SandboxProcessStdioPolicy
    stderr: SandboxProcessStdioPolicy
    child_policy: SandboxChildProcessPolicy
    handle_policy: SandboxHandleInheritancePolicy
    inheritable_handle_refs: tuple[OpaqueReference, ...]
    startup_requirements: SandboxProcessStartupRequirements
    termination_requirements: SandboxProcessTerminationRequirements
    cleanup_requirements: SandboxProcessCleanupRequirements
    limits: SandboxProcessLimits
    scope_ref: OpaqueReference
    required_enforcements: tuple[SandboxProcessEnforcement, ...]
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.required_enforcements != tuple(
            sorted(set(self.required_enforcements), key=lambda item: item.value)
        ):
            raise InvalidProcessBoundary("grant.enforcements_not_canonical")
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidProcessBoundary("grant.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxProcessDenial:
    reason: SandboxProcessDenialReason
    operations: tuple[SandboxProcessOperation, ...]
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.operations != tuple(sorted(set(self.operations), key=lambda item: item.value)):
            raise InvalidProcessBoundary("denial.operations_not_canonical")
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidProcessBoundary("denial.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxProcessGrantSet:
    grant_set_id: SandboxProcessGrantSetId
    grant_set_fingerprint: SandboxArtifactFingerprint
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    request_fingerprint: SandboxArtifactFingerprint
    capability_grant_set_fingerprint: SandboxArtifactFingerprint
    filesystem_specification_fingerprint: SandboxArtifactFingerprint
    network_specification_fingerprint: SandboxArtifactFingerprint
    policy_id: SandboxProcessPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    capability_snapshot_fingerprint: SandboxArtifactFingerprint
    evaluated_at: datetime
    grants: tuple[SandboxProcessGrant, ...]
    denials: tuple[SandboxProcessDenial, ...]
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
            raise InvalidProcessBoundary("grant_set.timestamp_invalid")
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.grant_set_fingerprint:
            raise InvalidProcessBoundary("grant_set.fingerprint_mismatch")
        if derive_identity(SandboxProcessGrantSetId, expected) != self.grant_set_id:
            raise InvalidProcessBoundary("grant_set.identity_mismatch")
        if self.grants != tuple(sorted(self.grants, key=repr)):
            raise InvalidProcessBoundary("grant_set.grants_not_canonical")
        if self.denials != tuple(sorted(self.denials, key=repr)):
            raise InvalidProcessBoundary("grant_set.denials_not_canonical")
        if self.diagnostics != tuple(sorted(set(self.diagnostics))):
            raise InvalidProcessBoundary("grant_set.diagnostics_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxProcessSpecification:
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    grant_set_id: SandboxProcessGrantSetId
    grant_set_fingerprint: SandboxArtifactFingerprint
    filesystem_specification_fingerprint: SandboxArtifactFingerprint
    network_specification_fingerprint: SandboxArtifactFingerprint
    grants: tuple[SandboxProcessGrant, ...]
    required_enforcements: tuple[SandboxProcessEnforcement, ...]
    specification_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.plan_id,
            self.plan_fingerprint,
            self.grant_set_id,
            self.grant_set_fingerprint,
            self.filesystem_specification_fingerprint,
            self.network_specification_fingerprint,
            self.grants,
            self.required_enforcements,
        )

    def __post_init__(self) -> None:
        if self.required_enforcements != tuple(
            sorted(set(self.required_enforcements), key=lambda item: item.value)
        ):
            raise InvalidProcessBoundary("specification.enforcements_not_canonical")
        if (
            SandboxArtifactFingerprint.from_content(self.content())
            != self.specification_fingerprint
        ):
            raise InvalidProcessBoundary("specification.fingerprint_mismatch")


def _lifecycle_complete(
    startup: SandboxProcessStartupRequirements,
    termination: SandboxProcessTerminationRequirements,
    cleanup: SandboxProcessCleanupRequirements,
) -> bool:
    return (
        startup.validate_support_before_start
        and startup.start_inside_boundary
        and termination.terminate_complete_tree
        and termination.force_after_grace_period
        and cleanup.close_inherited_handles
        and cleanup.verify_complete_tree_exit
    )


class SandboxProcessGrantService:
    """Derive process descriptions without starting or controlling a process."""

    def evaluate(
        self,
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        filesystem: SandboxFilesystemSpecification,
        network: SandboxNetworkSpecification,
        facts: SandboxProcessCapabilitySnapshot,
        policy: SandboxProcessPolicy,
        requests: tuple[SandboxProcessRequest, ...],
        *,
        evaluated_at: datetime,
        occurred_at: datetime,
    ) -> SandboxProcessGrantSet:
        self._validate_bindings(plan, capabilities, filesystem, network, policy)
        if (
            evaluated_at.tzinfo is None
            or evaluated_at.utcoffset() is None
            or occurred_at.tzinfo is None
            or occurred_at.utcoffset() is None
        ):
            raise InvalidProcessBoundary("grant_set.timestamp_invalid")
        ordered_requests = tuple(sorted(requests, key=repr))
        request_fingerprint = SandboxArtifactFingerprint.from_content(
            (plan.plan_id, plan.plan_fingerprint, ordered_requests)
        )
        grants: list[SandboxProcessGrant] = []
        denials: list[SandboxProcessDenial] = []
        for request in ordered_requests:
            grant, denial = self._evaluate_request(
                plan,
                capabilities,
                filesystem,
                facts,
                policy,
                request,
                evaluated_at,
            )
            if grant is not None:
                grants.append(grant)
            if denial is not None:
                denials.append(denial)
        ordered_grants = tuple(sorted(grants, key=repr))
        ordered_denials = tuple(sorted(denials, key=repr))
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
            policy.policy_id,
            policy.policy_fingerprint,
            facts.capability_fingerprint,
            evaluated_at,
            ordered_grants,
            ordered_denials,
            diagnostics,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        identity = derive_identity(SandboxProcessGrantSetId, fingerprint)
        return SandboxProcessGrantSet(
            SandboxProcessGrantSetId(identity.value),
            fingerprint,
            plan.plan_id,
            plan.plan_fingerprint,
            request_fingerprint,
            capabilities.grant_set_fingerprint,
            filesystem.specification_fingerprint,
            network.specification_fingerprint,
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
        grant_set: SandboxProcessGrantSet,
    ) -> SandboxProcessSpecification:
        enforcements = tuple(
            sorted(
                {
                    enforcement
                    for grant in grant_set.grants
                    for enforcement in grant.required_enforcements
                },
                key=lambda item: item.value,
            )
        )
        content = (
            grant_set.plan_id,
            grant_set.plan_fingerprint,
            grant_set.grant_set_id,
            grant_set.grant_set_fingerprint,
            grant_set.filesystem_specification_fingerprint,
            grant_set.network_specification_fingerprint,
            grant_set.grants,
            enforcements,
        )
        return SandboxProcessSpecification(
            grant_set.plan_id,
            grant_set.plan_fingerprint,
            grant_set.grant_set_id,
            grant_set.grant_set_fingerprint,
            grant_set.filesystem_specification_fingerprint,
            grant_set.network_specification_fingerprint,
            grant_set.grants,
            enforcements,
            SandboxArtifactFingerprint.from_content(content),
        )

    @staticmethod
    def _validate_bindings(
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        filesystem: SandboxFilesystemSpecification,
        network: SandboxNetworkSpecification,
        policy: SandboxProcessPolicy,
    ) -> None:
        diagnostics = []
        for name, candidate_id, candidate_fingerprint in (
            ("capability", capabilities.plan_id, capabilities.plan_fingerprint),
            ("filesystem", filesystem.plan_id, filesystem.plan_fingerprint),
            ("network", network.plan_id, network.plan_fingerprint),
            ("policy", policy.plan_id, policy.plan_fingerprint),
        ):
            if candidate_id != plan.plan_id:
                diagnostics.append(f"binding.{name}_plan_identity_mismatch")
            if candidate_fingerprint != plan.plan_fingerprint:
                diagnostics.append(f"binding.{name}_plan_fingerprint_mismatch")
        if diagnostics:
            raise InvalidProcessBoundary(",".join(sorted(diagnostics)))

    @classmethod
    def _evaluate_request(
        cls,
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        filesystem: SandboxFilesystemSpecification,
        snapshot: SandboxProcessCapabilitySnapshot,
        policy: SandboxProcessPolicy,
        request: SandboxProcessRequest,
        evaluated_at: datetime,
    ) -> tuple[SandboxProcessGrant | None, SandboxProcessDenial | None]:
        if snapshot.completeness is FactCompleteness.INCOMPLETE:
            return None, cls._denial(
                request, SandboxProcessDenialReason.INCOMPLETE, "facts.incomplete"
            )
        if snapshot.completeness is not FactCompleteness.COMPLETE:
            return None, cls._denial(
                request, SandboxProcessDenialReason.UNAVAILABLE, "facts.unavailable"
            )
        if request.runtime != plan.runtime or request.runtime != policy.runtime:
            return None, cls._denial(
                request, SandboxProcessDenialReason.RUNTIME_DENIED, "runtime.mismatch"
            )
        if request.entrypoint != plan.entrypoint or request.entrypoint != policy.entrypoint:
            return None, cls._denial(
                request, SandboxProcessDenialReason.ENTRYPOINT_MISMATCH, "entrypoint.mismatch"
            )
        if request.artifact_fingerprint != plan.artifact_fingerprint:
            return None, cls._denial(
                request, SandboxProcessDenialReason.MISMATCH, "artifact.fingerprint_mismatch"
            )
        executable = any(
            grant.resource is SandboxFilesystemResource.ARTIFACT
            and grant.operation is SandboxFilesystemOperation.EXECUTE
            and grant.executable_content
            for grant in filesystem.grants
        )
        if not executable:
            return None, cls._denial(
                request, SandboxProcessDenialReason.MISMATCH, "artifact.execute_binding_absent"
            )
        working_root_bound = any(
            grant.resource is request.working_root for grant in filesystem.grants
        )
        if not working_root_bound:
            return None, cls._denial(
                request,
                SandboxProcessDenialReason.MISMATCH,
                "working_root.filesystem_binding_absent",
            )
        if not set(request.operations) <= set(policy.allowed_operations):
            reason = (
                SandboxProcessDenialReason.CHILD_PROCESS_DENIED
                if SandboxProcessOperation.SPAWN_CHILD in request.operations
                else SandboxProcessDenialReason.CAPABILITY_ABSENT
            )
            return None, cls._denial(request, reason, "policy.operation_denied")
        if request.detached:
            return None, cls._denial(
                request,
                SandboxProcessDenialReason.DETACHED_PROCESS_DENIED,
                "process.detached_denied",
            )
        if any(
            argument.kind not in policy.allowed_argument_kinds for argument in request.arguments
        ):
            return None, cls._denial(
                request,
                SandboxProcessDenialReason.SHELL_SEMANTICS_DETECTED,
                "arguments.kind_denied",
            )
        if request.working_root not in policy.allowed_working_roots:
            return None, cls._denial(
                request, SandboxProcessDenialReason.MISMATCH, "working_root.denied"
            )
        if not {item.name for item in request.environment} <= set(policy.allowed_environment_names):
            return None, cls._denial(
                request, SandboxProcessDenialReason.ENVIRONMENT_DENIED, "environment.name_denied"
            )
        if any(
            item not in policy.allowed_stdio
            for item in (request.stdin, request.stdout, request.stderr)
        ):
            return None, cls._denial(request, SandboxProcessDenialReason.MISMATCH, "stdio.denied")
        if (
            request.child_policy is SandboxChildProcessPolicy.SAME_SUPERVISED_TREE
            and policy.child_policy is SandboxChildProcessPolicy.DENY
        ):
            return None, cls._denial(
                request, SandboxProcessDenialReason.CHILD_PROCESS_DENIED, "child.policy_denied"
            )
        if request.handle_policy != policy.handle_policy or not set(
            request.inheritable_handle_refs
        ) <= set(policy.allowed_handle_refs):
            return None, cls._denial(
                request, SandboxProcessDenialReason.HANDLE_INHERITANCE_DENIED, "handles.denied"
            )
        if not request.limits.within(policy.limits) or cls._request_exceeds_internal_limits(
            request
        ):
            return None, cls._denial(
                request, SandboxProcessDenialReason.LIMIT_EXCEEDED, "limits.exceeded"
            )
        if len(snapshot.facts) != 1:
            return None, cls._denial(
                request, SandboxProcessDenialReason.MISMATCH, "facts.correspondence"
            )
        fact = snapshot.facts[0]
        if fact.runtime != request.runtime:
            return None, cls._denial(
                request,
                SandboxProcessDenialReason.RUNTIME_UNSUPPORTED,
                "fact.runtime_unsupported",
            )
        if fact.entrypoint != request.entrypoint:
            return None, cls._denial(
                request,
                SandboxProcessDenialReason.ENTRYPOINT_MISMATCH,
                "fact.entrypoint_mismatch",
            )
        if (
            fact.plan_id != plan.plan_id
            or fact.plan_fingerprint != plan.plan_fingerprint
            or fact.artifact_fingerprint != request.artifact_fingerprint
            or plan.isolation_profile_id not in fact.isolation_profiles
        ):
            return None, cls._denial(
                request, SandboxProcessDenialReason.MISMATCH, "fact.binding_mismatch"
            )
        if not fact.valid_from <= evaluated_at <= fact.valid_until:
            return None, cls._denial(request, SandboxProcessDenialReason.STALE, "fact.stale")
        if not set(request.operations) <= set(fact.operations):
            reason = (
                SandboxProcessDenialReason.CHILD_PROCESS_DENIED
                if SandboxProcessOperation.SPAWN_CHILD in request.operations
                else SandboxProcessDenialReason.RUNTIME_UNSUPPORTED
            )
            return None, cls._denial(request, reason, "fact.operation_unsupported")
        if not {item.name for item in request.environment} <= set(fact.allowed_environment_names):
            return None, cls._denial(
                request, SandboxProcessDenialReason.ENVIRONMENT_DENIED, "fact.environment_denied"
            )
        if request.child_policy != fact.child_policy:
            return None, cls._denial(
                request,
                SandboxProcessDenialReason.CHILD_PROCESS_DENIED,
                "fact.child_policy_mismatch",
            )
        if request.handle_policy != fact.handle_policy or not set(
            request.inheritable_handle_refs
        ) <= set(fact.allowed_handle_refs):
            return None, cls._denial(
                request, SandboxProcessDenialReason.HANDLE_INHERITANCE_DENIED, "fact.handles_denied"
            )
        lifecycle = (
            request.startup_requirements,
            request.termination_requirements,
            request.cleanup_requirements,
        )
        if lifecycle != (
            policy.startup_requirements,
            policy.termination_requirements,
            policy.cleanup_requirements,
        ) or lifecycle != (
            fact.startup_requirements,
            fact.termination_requirements,
            fact.cleanup_requirements,
        ):
            return None, cls._denial(
                request,
                SandboxProcessDenialReason.MISMATCH,
                "lifecycle.requirements_mismatch",
            )
        if not request.limits.within(fact.limits):
            return None, cls._denial(
                request, SandboxProcessDenialReason.LIMIT_EXCEEDED, "fact.limits_exceeded"
            )
        if not set(policy.required_enforcements) <= set(fact.supported_enforcements):
            return None, cls._denial(
                request,
                SandboxProcessDenialReason.ENFORCEMENT_UNSUPPORTED,
                "fact.enforcement_unsupported",
            )
        requirements = {item.operation: item.capability for item in policy.capability_requirements}
        for operation in request.operations:
            capability = next(
                (
                    grant
                    for grant in capabilities.grants
                    if grant.capability == requirements[operation]
                ),
                None,
            )
            if capability is None:
                return None, cls._denial(
                    request, SandboxProcessDenialReason.CAPABILITY_ABSENT, "capability.absent"
                )
            if not capability.valid_from <= evaluated_at <= capability.valid_until:
                return None, cls._denial(
                    request, SandboxProcessDenialReason.STALE, "capability.stale"
                )
            if not any(
                scope.kind is SandboxCapabilityScopeKind.WILDCARD
                or scope.reference == fact.scope_ref
                for scope in capability.scopes
            ):
                return None, cls._denial(
                    request, SandboxProcessDenialReason.CAPABILITY_ABSENT, "capability.scope_absent"
                )
        return (
            SandboxProcessGrant(
                request.runtime,
                request.entrypoint,
                request.artifact_fingerprint,
                request.operations,
                request.arguments,
                request.working_root,
                request.environment,
                request.stdin,
                request.stdout,
                request.stderr,
                request.child_policy,
                request.handle_policy,
                request.inheritable_handle_refs,
                request.startup_requirements,
                request.termination_requirements,
                request.cleanup_requirements,
                request.limits,
                fact.scope_ref,
                policy.required_enforcements,
                ("process.intersection_satisfied",),
            ),
            None,
        )

    @staticmethod
    def _request_exceeds_internal_limits(request: SandboxProcessRequest) -> bool:
        return (
            len(request.arguments) > request.limits.maximum_arguments
            or sum(item.encoded_size() for item in request.arguments)
            > request.limits.maximum_argument_bytes
            or len(request.environment) > request.limits.maximum_environment_entries
            or sum(
                len(item.name.encode("utf-8")) + len(item.value_ref.value.encode("utf-8"))
                for item in request.environment
            )
            > request.limits.maximum_environment_bytes
            or len(request.inheritable_handle_refs) > request.limits.maximum_inheritable_handles
        )

    @staticmethod
    def _denial(
        request: SandboxProcessRequest,
        reason: SandboxProcessDenialReason,
        code: str,
    ) -> SandboxProcessDenial:
        return SandboxProcessDenial(reason, request.operations, (code,))
