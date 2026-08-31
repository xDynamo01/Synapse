"""Deny-by-default logical filesystem grant evaluation with no filesystem I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .capability_grants import SandboxCapabilityGrantSet
from .errors import InvalidFilesystemBoundary
from .execution_plan import SandboxExecutionPlan
from .facts import FactCompleteness, SandboxCapabilityScopeKind
from .identities import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxFilesystemGrantSetId,
    SandboxFilesystemPolicyId,
    SandboxIsolationProfileId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxPolicyVersion,
    derive_identity,
)

FILESYSTEM_PATH_FORMAT = "sandbox-logical-path-v1"
FILESYSTEM_POLICY_FORMAT = "sandbox-filesystem-policy-v1"
FILESYSTEM_RESOURCE_FORMAT = "sandbox-filesystem-resources-v1"
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


class SandboxFilesystemOperation(StrEnum):
    READ = "read"
    CREATE = "create"
    WRITE = "write"
    APPEND = "append"
    DELETE = "delete"
    LIST = "list"
    METADATA = "metadata"
    EXECUTE = "execute"


class SandboxFilesystemResource(StrEnum):
    ARTIFACT = "artifact"
    WORKSPACE = "workspace"
    INPUT = "input"
    OUTPUT = "output"
    TEMPORARY = "temporary"
    STATE = "state"


class SandboxFilesystemLinkKind(StrEnum):
    NONE = "none"
    SYMLINK = "symlink"
    JUNCTION = "junction"
    REPARSE_POINT = "reparse_point"
    HARDLINK = "hardlink"


class SandboxFilesystemEnforcement(StrEnum):
    CASE_SENSITIVITY = "case_sensitivity"
    LINK_REJECTION = "link_rejection"
    HARDLINK_REJECTION = "hardlink_rejection"
    ATOMIC_REPLACE = "atomic_replace"
    EXECUTABLE_CONTENT = "executable_content"
    LIMITS = "limits"


class SandboxFilesystemDenialReason(StrEnum):
    CAPABILITY_ABSENT = "capability_absent"
    RESOURCE_SCOPE_ABSENT = "resource_scope_absent"
    OPERATION_DENIED = "operation_denied"
    PATH_INVALID = "path_invalid"
    TRAVERSAL = "traversal"
    LINK_POLICY = "link_policy"
    LIMIT_EXCEEDED = "limit_exceeded"
    UNSUPPORTED_ENFORCEMENT = "unsupported_enforcement"
    MISMATCH = "mismatch"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SandboxLogicalPath:
    format_version: str
    value: str
    case_sensitive: bool

    @classmethod
    def parse(cls, expression: str, *, case_sensitive: bool) -> SandboxLogicalPath:
        reason = _invalid_path_reason(expression)
        if reason is not None:
            raise InvalidFilesystemBoundary(reason.value)
        normalized = expression if case_sensitive else expression.lower()
        return cls(FILESYSTEM_PATH_FORMAT, normalized, case_sensitive)

    def __post_init__(self) -> None:
        if self.format_version != FILESYSTEM_PATH_FORMAT:
            raise InvalidFilesystemBoundary("path.format_unsupported")
        if _invalid_path_reason(self.value) is not None:
            raise InvalidFilesystemBoundary("path.invalid")

    @property
    def depth(self) -> int:
        return len(self.value.split("/"))


def _invalid_path_reason(expression: str) -> SandboxFilesystemDenialReason | None:
    if not isinstance(expression, str) or not expression or len(expression) > 512:
        return SandboxFilesystemDenialReason.PATH_INVALID
    if expression.startswith(("/", "\\", "~")) or "\\" in expression:
        return SandboxFilesystemDenialReason.PATH_INVALID
    segments = expression.split("/")
    if any(not segment for segment in segments):
        return SandboxFilesystemDenialReason.PATH_INVALID
    if any(segment == ".." for segment in segments):
        return SandboxFilesystemDenialReason.TRAVERSAL
    if any(segment == "." for segment in segments):
        return SandboxFilesystemDenialReason.PATH_INVALID
    for segment in segments:
        if not _SEGMENT.fullmatch(segment):
            return SandboxFilesystemDenialReason.PATH_INVALID
        stem = segment.split(".", 1)[0].casefold()
        if stem in _RESERVED or segment.endswith((".", " ")):
            return SandboxFilesystemDenialReason.PATH_INVALID
    return None


@dataclass(frozen=True, slots=True)
class SandboxFilesystemLimits:
    maximum_depth: int
    maximum_files: int
    maximum_bytes: int

    def __post_init__(self) -> None:
        values = (self.maximum_depth, self.maximum_files, self.maximum_bytes)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in values
        ):
            raise InvalidFilesystemBoundary("limits.must_be_positive")

    def within(self, other: SandboxFilesystemLimits) -> bool:
        return (
            self.maximum_depth <= other.maximum_depth
            and self.maximum_files <= other.maximum_files
            and self.maximum_bytes <= other.maximum_bytes
        )


@dataclass(frozen=True, slots=True)
class SandboxFilesystemRequest:
    resource: SandboxFilesystemResource
    path_expression: str
    operation: SandboxFilesystemOperation
    requested_limits: SandboxFilesystemLimits
    link_kind: SandboxFilesystemLinkKind
    overwrite: bool
    atomic_replace: bool
    executable_content: bool

    def __post_init__(self) -> None:
        if not isinstance(self.path_expression, str) or len(self.path_expression) > 512:
            raise InvalidFilesystemBoundary("request.path_expression_invalid")


@dataclass(frozen=True, slots=True)
class SandboxFilesystemCapabilityRequirement:
    operation: SandboxFilesystemOperation
    capability: str


@dataclass(frozen=True, slots=True)
class SandboxFilesystemResourceRule:
    resource: SandboxFilesystemResource
    allowed_operations: tuple[SandboxFilesystemOperation, ...]
    capability_requirements: tuple[SandboxFilesystemCapabilityRequirement, ...]
    case_sensitive: bool
    read_only: bool
    create_only: bool
    allow_overwrite: bool
    require_atomic_replace: bool
    allow_executable_content: bool
    allowed_links: tuple[SandboxFilesystemLinkKind, ...]
    limits: SandboxFilesystemLimits
    required_enforcements: tuple[SandboxFilesystemEnforcement, ...]

    def __post_init__(self) -> None:
        if len(set(self.allowed_operations)) != len(self.allowed_operations):
            raise InvalidFilesystemBoundary("policy.operations_conflict")
        mapping = [item.operation for item in self.capability_requirements]
        if len(mapping) != len(set(mapping)) or set(mapping) != set(self.allowed_operations):
            raise InvalidFilesystemBoundary("policy.capability_mapping_incomplete")
        if SandboxFilesystemLinkKind.NONE not in self.allowed_links:
            raise InvalidFilesystemBoundary("policy.link_none_required")
        if self.read_only and any(
            operation
            in {
                SandboxFilesystemOperation.CREATE,
                SandboxFilesystemOperation.WRITE,
                SandboxFilesystemOperation.APPEND,
                SandboxFilesystemOperation.DELETE,
                SandboxFilesystemOperation.EXECUTE,
            }
            for operation in self.allowed_operations
        ):
            raise InvalidFilesystemBoundary("policy.read_only_mutation")
        object.__setattr__(
            self,
            "allowed_operations",
            tuple(sorted(self.allowed_operations, key=lambda item: item.value)),
        )
        object.__setattr__(
            self,
            "capability_requirements",
            tuple(
                sorted(
                    self.capability_requirements,
                    key=lambda item: (item.operation.value, item.capability),
                )
            ),
        )
        object.__setattr__(
            self,
            "allowed_links",
            tuple(sorted(set(self.allowed_links), key=lambda item: item.value)),
        )
        object.__setattr__(
            self,
            "required_enforcements",
            tuple(sorted(set(self.required_enforcements), key=lambda item: item.value)),
        )


@dataclass(frozen=True, slots=True)
class SandboxFilesystemPolicy:
    format_version: str
    policy_id: SandboxFilesystemPolicyId
    version: SandboxPolicyVersion
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    rules: tuple[SandboxFilesystemResourceRule, ...]
    policy_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.format_version,
            self.version,
            self.plan_id,
            self.plan_fingerprint,
            self.rules,
        )

    def __post_init__(self) -> None:
        if self.format_version != FILESYSTEM_POLICY_FORMAT:
            raise InvalidFilesystemBoundary("policy.format_unsupported")
        if len({item.resource for item in self.rules}) != len(self.rules):
            raise InvalidFilesystemBoundary("policy.resource_rules_conflict")
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.policy_fingerprint:
            raise InvalidFilesystemBoundary("policy.fingerprint_mismatch")
        expected_id = derive_identity(SandboxFilesystemPolicyId, expected)
        if expected_id != self.policy_id:
            raise InvalidFilesystemBoundary("policy.identity_mismatch")

    @classmethod
    def create(
        cls,
        *,
        version: SandboxPolicyVersion,
        plan: SandboxExecutionPlan,
        rules: tuple[SandboxFilesystemResourceRule, ...],
    ) -> SandboxFilesystemPolicy:
        ordered = tuple(sorted(rules, key=lambda item: item.resource.value))
        content: tuple[object, ...] = (
            FILESYSTEM_POLICY_FORMAT,
            version,
            plan.plan_id,
            plan.plan_fingerprint,
            ordered,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        policy_id = derive_identity(SandboxFilesystemPolicyId, fingerprint)
        return cls(
            FILESYSTEM_POLICY_FORMAT,
            SandboxFilesystemPolicyId(policy_id.value),
            version,
            plan.plan_id,
            plan.plan_fingerprint,
            ordered,
            fingerprint,
        )


@dataclass(frozen=True, slots=True)
class SandboxFilesystemResourceFact:
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    resource: SandboxFilesystemResource
    scope_ref: OpaqueReference
    allowed_operations: tuple[SandboxFilesystemOperation, ...]
    read_only: bool
    writable: bool
    create_only: bool
    limits: SandboxFilesystemLimits
    supported_enforcements: tuple[SandboxFilesystemEnforcement, ...]
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
            raise InvalidFilesystemBoundary("resource_fact.validity_invalid")
        if len(set(self.allowed_operations)) != len(self.allowed_operations):
            raise InvalidFilesystemBoundary("resource_fact.operations_conflict")
        object.__setattr__(
            self,
            "allowed_operations",
            tuple(sorted(self.allowed_operations, key=lambda item: item.value)),
        )
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
class SandboxFilesystemResourceSnapshot:
    format_version: str
    observed_at: datetime
    completeness: FactCompleteness
    facts: tuple[SandboxFilesystemResourceFact, ...]
    resource_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (self.format_version, self.observed_at, self.completeness, self.facts)

    @classmethod
    def create(
        cls,
        *,
        observed_at: datetime,
        completeness: FactCompleteness,
        facts: tuple[SandboxFilesystemResourceFact, ...],
    ) -> SandboxFilesystemResourceSnapshot:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise InvalidFilesystemBoundary("resource_snapshot.observed_at_invalid")
        ordered = tuple(sorted(facts, key=repr))
        content = (FILESYSTEM_RESOURCE_FORMAT, observed_at, completeness, ordered)
        return cls(
            FILESYSTEM_RESOURCE_FORMAT,
            observed_at,
            completeness,
            ordered,
            SandboxArtifactFingerprint.from_content(content),
        )

    def __post_init__(self) -> None:
        if self.format_version != FILESYSTEM_RESOURCE_FORMAT:
            raise InvalidFilesystemBoundary("resource_snapshot.format_unsupported")
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.resource_fingerprint:
            raise InvalidFilesystemBoundary("resource_snapshot.fingerprint_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxFilesystemGrant:
    resource: SandboxFilesystemResource
    path: SandboxLogicalPath
    operation: SandboxFilesystemOperation
    limits: SandboxFilesystemLimits
    scope_ref: OpaqueReference
    overwrite: bool
    atomic_replace: bool
    executable_content: bool
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidFilesystemBoundary("grant.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxFilesystemDenial:
    resource: SandboxFilesystemResource
    operation: SandboxFilesystemOperation
    reason: SandboxFilesystemDenialReason
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidFilesystemBoundary("denial.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxFilesystemGrantSet:
    grant_set_id: SandboxFilesystemGrantSetId
    grant_set_fingerprint: SandboxArtifactFingerprint
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    request_fingerprint: SandboxArtifactFingerprint
    capability_grant_set_fingerprint: SandboxArtifactFingerprint
    policy_id: SandboxFilesystemPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    resource_snapshot_fingerprint: SandboxArtifactFingerprint
    evaluated_at: datetime
    grants: tuple[SandboxFilesystemGrant, ...]
    denials: tuple[SandboxFilesystemDenial, ...]
    diagnostics: tuple[str, ...]
    occurred_at: datetime

    def content(self) -> tuple[object, ...]:
        return (
            self.plan_id,
            self.plan_fingerprint,
            self.request_fingerprint,
            self.capability_grant_set_fingerprint,
            self.policy_id,
            self.policy_fingerprint,
            self.resource_snapshot_fingerprint,
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
            raise InvalidFilesystemBoundary("grant_set.timestamp_invalid")
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.grant_set_fingerprint:
            raise InvalidFilesystemBoundary("grant_set.fingerprint_mismatch")
        expected_id = derive_identity(SandboxFilesystemGrantSetId, expected)
        if expected_id != self.grant_set_id:
            raise InvalidFilesystemBoundary("grant_set.identity_mismatch")
        if self.diagnostics != tuple(sorted(set(self.diagnostics))):
            raise InvalidFilesystemBoundary("grant_set.diagnostics_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxFilesystemSpecification:
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    grant_set_id: SandboxFilesystemGrantSetId
    grant_set_fingerprint: SandboxArtifactFingerprint
    grants: tuple[SandboxFilesystemGrant, ...]
    specification_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.plan_id,
            self.plan_fingerprint,
            self.grant_set_id,
            self.grant_set_fingerprint,
            self.grants,
        )

    def __post_init__(self) -> None:
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.specification_fingerprint:
            raise InvalidFilesystemBoundary("specification.fingerprint_mismatch")


class SandboxFilesystemGrantService:
    """Evaluate logical requests; never inspect or mutate a real filesystem."""

    def evaluate(
        self,
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        resources: SandboxFilesystemResourceSnapshot,
        policy: SandboxFilesystemPolicy,
        requests: tuple[SandboxFilesystemRequest, ...],
        *,
        evaluated_at: datetime,
        occurred_at: datetime,
    ) -> SandboxFilesystemGrantSet:
        self._validate_bindings(plan, capabilities, policy)
        if (
            evaluated_at.tzinfo is None
            or evaluated_at.utcoffset() is None
            or occurred_at.tzinfo is None
            or occurred_at.utcoffset() is None
        ):
            raise InvalidFilesystemBoundary("grant_set.timestamp_invalid")
        ordered_requests = tuple(
            sorted(
                requests,
                key=lambda item: (
                    item.resource.value,
                    item.path_expression,
                    item.operation.value,
                ),
            )
        )
        request_fingerprint = SandboxArtifactFingerprint.from_content(
            (plan.plan_id, plan.plan_fingerprint, ordered_requests)
        )
        rules = {item.resource: item for item in policy.rules}
        facts: dict[SandboxFilesystemResource, list[SandboxFilesystemResourceFact]] = {}
        for fact in resources.facts:
            facts.setdefault(fact.resource, []).append(fact)
        grants: list[SandboxFilesystemGrant] = []
        denials: list[SandboxFilesystemDenial] = []
        for request in ordered_requests:
            grant, denial = self._evaluate_request(
                plan,
                capabilities,
                resources.completeness,
                rules.get(request.resource),
                facts.get(request.resource, []),
                request,
                evaluated_at,
            )
            if grant is not None:
                grants.append(grant)
            if denial is not None:
                denials.append(denial)
        ordered_grants = tuple(
            sorted(
                grants,
                key=lambda item: (
                    item.resource.value,
                    item.path.value,
                    item.operation.value,
                ),
            )
        )
        ordered_denials = tuple(
            sorted(
                denials,
                key=lambda item: (
                    item.resource.value,
                    item.operation.value,
                    item.reason.value,
                ),
            )
        )
        diagnostics = tuple(
            sorted({code for denial in ordered_denials for code in denial.rationale_codes})
        )
        content = (
            plan.plan_id,
            plan.plan_fingerprint,
            request_fingerprint,
            capabilities.grant_set_fingerprint,
            policy.policy_id,
            policy.policy_fingerprint,
            resources.resource_fingerprint,
            evaluated_at,
            ordered_grants,
            ordered_denials,
            diagnostics,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        identity = derive_identity(SandboxFilesystemGrantSetId, fingerprint)
        return SandboxFilesystemGrantSet(
            SandboxFilesystemGrantSetId(identity.value),
            fingerprint,
            plan.plan_id,
            plan.plan_fingerprint,
            request_fingerprint,
            capabilities.grant_set_fingerprint,
            policy.policy_id,
            policy.policy_fingerprint,
            resources.resource_fingerprint,
            evaluated_at,
            ordered_grants,
            ordered_denials,
            diagnostics,
            occurred_at,
        )

    @staticmethod
    def build_specification(
        grant_set: SandboxFilesystemGrantSet,
    ) -> SandboxFilesystemSpecification:
        content = (
            grant_set.plan_id,
            grant_set.plan_fingerprint,
            grant_set.grant_set_id,
            grant_set.grant_set_fingerprint,
            grant_set.grants,
        )
        return SandboxFilesystemSpecification(
            grant_set.plan_id,
            grant_set.plan_fingerprint,
            grant_set.grant_set_id,
            grant_set.grant_set_fingerprint,
            grant_set.grants,
            SandboxArtifactFingerprint.from_content(content),
        )

    @staticmethod
    def _validate_bindings(
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        policy: SandboxFilesystemPolicy,
    ) -> None:
        diagnostics = []
        if capabilities.plan_id != plan.plan_id:
            diagnostics.append("binding.capability_plan_identity_mismatch")
        if capabilities.plan_fingerprint != plan.plan_fingerprint:
            diagnostics.append("binding.capability_plan_fingerprint_mismatch")
        if policy.plan_id != plan.plan_id:
            diagnostics.append("binding.policy_plan_identity_mismatch")
        if policy.plan_fingerprint != plan.plan_fingerprint:
            diagnostics.append("binding.policy_plan_fingerprint_mismatch")
        if diagnostics:
            raise InvalidFilesystemBoundary(",".join(sorted(diagnostics)))

    @classmethod
    def _evaluate_request(
        cls,
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        completeness: FactCompleteness,
        rule: SandboxFilesystemResourceRule | None,
        facts: list[SandboxFilesystemResourceFact],
        request: SandboxFilesystemRequest,
        evaluated_at: datetime,
    ) -> tuple[SandboxFilesystemGrant | None, SandboxFilesystemDenial | None]:
        invalid_reason = _invalid_path_reason(request.path_expression)
        if invalid_reason is not None:
            return None, cls._denial(request, invalid_reason, f"path.{invalid_reason.value}")
        if completeness is FactCompleteness.INCOMPLETE:
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.INCOMPLETE, "resources.incomplete"
            )
        if completeness is not FactCompleteness.COMPLETE:
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.UNAVAILABLE, "resources.unavailable"
            )
        if rule is None:
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.OPERATION_DENIED, "policy.deny_default"
            )
        if request.operation not in rule.allowed_operations:
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.OPERATION_DENIED, "policy.operation_denied"
            )
        if len(set(facts)) != 1:
            reason = (
                SandboxFilesystemDenialReason.RESOURCE_SCOPE_ABSENT
                if not facts
                else SandboxFilesystemDenialReason.MISMATCH
            )
            return None, cls._denial(request, reason, "resource.correspondence")
        fact = facts[0]
        if (
            fact.plan_id != plan.plan_id
            or fact.plan_fingerprint != plan.plan_fingerprint
            or plan.isolation_profile_id not in fact.isolation_profiles
        ):
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.MISMATCH, "resource.binding_mismatch"
            )
        if not fact.valid_from <= evaluated_at <= fact.valid_until:
            return None, cls._denial(request, SandboxFilesystemDenialReason.STALE, "resource.stale")
        if request.operation not in fact.allowed_operations:
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.OPERATION_DENIED, "resource.operation_denied"
            )
        requirement = next(
            item for item in rule.capability_requirements if item.operation is request.operation
        )
        capability = next(
            (item for item in capabilities.grants if item.capability == requirement.capability),
            None,
        )
        if capability is None:
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.CAPABILITY_ABSENT, "capability.absent"
            )
        if not capability.valid_from <= evaluated_at <= capability.valid_until:
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.STALE, "capability.stale"
            )
        scope_matches = any(
            scope.kind is SandboxCapabilityScopeKind.WILDCARD or scope.reference == fact.scope_ref
            for scope in capability.scopes
        )
        if not scope_matches:
            return None, cls._denial(
                request,
                SandboxFilesystemDenialReason.RESOURCE_SCOPE_ABSENT,
                "capability.resource_scope_absent",
            )
        if request.link_kind not in rule.allowed_links:
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.LINK_POLICY, "policy.link_denied"
            )
        if not set(rule.required_enforcements) <= set(fact.supported_enforcements):
            return None, cls._denial(
                request,
                SandboxFilesystemDenialReason.UNSUPPORTED_ENFORCEMENT,
                "resource.enforcement_unsupported",
            )
        if not request.requested_limits.within(rule.limits) or not request.requested_limits.within(
            fact.limits
        ):
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.LIMIT_EXCEEDED, "limits.exceeded"
            )
        if request.requested_limits.maximum_depth < len(request.path_expression.split("/")):
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.LIMIT_EXCEEDED, "limits.depth_exceeded"
            )
        mutation = request.operation in {
            SandboxFilesystemOperation.CREATE,
            SandboxFilesystemOperation.WRITE,
            SandboxFilesystemOperation.APPEND,
            SandboxFilesystemOperation.DELETE,
        }
        if request.resource is SandboxFilesystemResource.ARTIFACT and mutation:
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.OPERATION_DENIED, "artifact.read_only"
            )
        if mutation and (rule.read_only or fact.read_only or not fact.writable):
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.OPERATION_DENIED, "resource.read_only"
            )
        if request.overwrite and (
            request.operation is SandboxFilesystemOperation.CREATE
            or rule.create_only
            or fact.create_only
            or not rule.allow_overwrite
        ):
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.OPERATION_DENIED, "overwrite.denied"
            )
        if rule.require_atomic_replace and mutation and not request.atomic_replace:
            return None, cls._denial(
                request,
                SandboxFilesystemDenialReason.UNSUPPORTED_ENFORCEMENT,
                "atomic_replace.required",
            )
        if request.executable_content and (
            request.operation is not SandboxFilesystemOperation.EXECUTE
            or not rule.allow_executable_content
        ):
            return None, cls._denial(
                request, SandboxFilesystemDenialReason.OPERATION_DENIED, "executable.denied"
            )
        path = SandboxLogicalPath.parse(request.path_expression, case_sensitive=rule.case_sensitive)
        return (
            SandboxFilesystemGrant(
                request.resource,
                path,
                request.operation,
                request.requested_limits,
                fact.scope_ref,
                request.overwrite,
                request.atomic_replace,
                request.executable_content,
                ("filesystem.intersection_satisfied",),
            ),
            None,
        )

    @staticmethod
    def _denial(
        request: SandboxFilesystemRequest,
        reason: SandboxFilesystemDenialReason,
        code: str,
    ) -> SandboxFilesystemDenial:
        return SandboxFilesystemDenial(request.resource, request.operation, reason, (code,))
