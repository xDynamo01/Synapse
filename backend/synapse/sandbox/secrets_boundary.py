"""Pure opaque-reference secret lease contracts without secret material or I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .capability_grants import SandboxCapabilityGrantSet
from .errors import InvalidSecretsBoundary
from .execution_plan import SandboxExecutionPlan
from .facts import FactCompleteness, SandboxCapabilityScopeKind
from .identities import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxAttemptId,
    SandboxIsolationProfileId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxPolicyVersion,
    SandboxSecretGrantSetId,
    SandboxSecretPolicyId,
    SandboxWorkloadId,
    derive_identity,
)
from .resource_limits import (
    SandboxResourceDimension,
    SandboxResourceSpecification,
)

SECRET_POLICY_FORMAT = "sandbox-secret-policy-v1"
SECRET_CAPABILITY_FORMAT = "sandbox-secret-capabilities-v1"
_NAME = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")


class SandboxSecretOperation(StrEnum):
    RESOLVE_REFERENCE = "resolve_reference"
    ACQUIRE_LEASE = "acquire_lease"
    RENEW_LEASE = "renew_lease"
    REVOKE_LEASE = "revoke_lease"
    USE_ONCE = "use_once"


class SandboxSecretFormat(StrEnum):
    OPAQUE = "opaque"
    UTF8_TEXT = "utf8_text"
    JSON = "json"


class SandboxSecretRenewalPolicy(StrEnum):
    DENY = "deny"
    EXPLICIT = "explicit"


class SandboxSecretDenialReason(StrEnum):
    CAPABILITY_ABSENT = "capability_absent"
    SECRET_UNAVAILABLE = "secret_unavailable"
    AUTHORIZATION_MISSING = "authorization_missing"
    SUBJECT_MISMATCH = "subject_mismatch"
    PURPOSE_MISMATCH = "purpose_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    PROVIDER_UNSUPPORTED = "provider_unsupported"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    EXPIRED = "expired"
    LEASE_UNSUPPORTED = "lease_unsupported"
    RENEWAL_DENIED = "renewal_denied"
    ISOLATION_INSUFFICIENT = "isolation_insufficient"


@dataclass(frozen=True, slots=True)
class SandboxSecretDeclaration:
    secret_ref: OpaqueReference
    provider: str
    purpose: str
    scope_ref: OpaqueReference
    expected_format: SandboxSecretFormat

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.provider):
            raise InvalidSecretsBoundary("declaration.provider_invalid")
        if not _NAME.fullmatch(self.purpose):
            raise InvalidSecretsBoundary("declaration.purpose_invalid")


@dataclass(frozen=True, slots=True)
class SandboxSecretLeaseRequest:
    not_before: datetime
    requested_expires_at: datetime
    maximum_duration_seconds: int
    maximum_usage_count: int
    renewal_policy: SandboxSecretRenewalPolicy
    revoke_on_termination: bool
    revoke_on_timeout: bool
    revoke_on_cancellation: bool

    def __post_init__(self) -> None:
        if (
            self.not_before.tzinfo is None
            or self.not_before.utcoffset() is None
            or self.requested_expires_at.tzinfo is None
            or self.requested_expires_at.utcoffset() is None
            or self.requested_expires_at <= self.not_before
        ):
            raise InvalidSecretsBoundary("lease.validity_invalid")
        if (
            not isinstance(self.maximum_duration_seconds, int)
            or isinstance(self.maximum_duration_seconds, bool)
            or self.maximum_duration_seconds <= 0
            or not isinstance(self.maximum_usage_count, int)
            or isinstance(self.maximum_usage_count, bool)
            or self.maximum_usage_count <= 0
        ):
            raise InvalidSecretsBoundary("lease.limits_invalid")
        requested_duration = (self.requested_expires_at - self.not_before).total_seconds()
        if requested_duration > self.maximum_duration_seconds:
            raise InvalidSecretsBoundary("lease.expiry_exceeds_duration")


@dataclass(frozen=True, slots=True)
class SandboxSecretRequest:
    declaration: SandboxSecretDeclaration
    subject: OpaqueReference
    workload_id: SandboxWorkloadId
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    attempt_id: SandboxAttemptId
    operations: tuple[SandboxSecretOperation, ...]
    lease: SandboxSecretLeaseRequest

    def __post_init__(self) -> None:
        if not self.operations or len(set(self.operations)) != len(self.operations):
            raise InvalidSecretsBoundary("request.operations_invalid")
        object.__setattr__(
            self,
            "operations",
            tuple(sorted(self.operations, key=lambda item: item.value)),
        )
        if SandboxSecretOperation.USE_ONCE in self.operations and (
            SandboxSecretOperation.RENEW_LEASE in self.operations
            or self.lease.renewal_policy is not SandboxSecretRenewalPolicy.DENY
            or self.lease.maximum_usage_count != 1
        ):
            raise InvalidSecretsBoundary("request.use_once_renewal_conflict")


@dataclass(frozen=True, slots=True)
class SandboxSecretPolicyRule:
    declaration: SandboxSecretDeclaration
    capability: str
    allowed_operations: tuple[SandboxSecretOperation, ...]
    maximum_duration_seconds: int
    maximum_usage_count: int
    renewal_policy: SandboxSecretRenewalPolicy
    require_revocation_on_termination: bool
    require_revocation_on_timeout: bool
    require_revocation_on_cancellation: bool

    def __post_init__(self) -> None:
        if not self.capability or not _NAME.fullmatch(self.capability):
            raise InvalidSecretsBoundary("policy.capability_invalid")
        canonical = tuple(sorted(set(self.allowed_operations), key=lambda item: item.value))
        if not canonical or canonical != self.allowed_operations:
            raise InvalidSecretsBoundary("policy.operations_not_canonical")
        if (
            not isinstance(self.maximum_duration_seconds, int)
            or isinstance(self.maximum_duration_seconds, bool)
            or self.maximum_duration_seconds <= 0
            or not isinstance(self.maximum_usage_count, int)
            or isinstance(self.maximum_usage_count, bool)
            or self.maximum_usage_count <= 0
        ):
            raise InvalidSecretsBoundary("policy.lease_limits_invalid")
        if SandboxSecretOperation.USE_ONCE in self.allowed_operations and (
            self.renewal_policy is not SandboxSecretRenewalPolicy.DENY
            or self.maximum_usage_count != 1
        ):
            raise InvalidSecretsBoundary("policy.use_once_renewal_conflict")


@dataclass(frozen=True, slots=True)
class SandboxSecretPolicy:
    format_version: str
    policy_id: SandboxSecretPolicyId
    version: SandboxPolicyVersion
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    workload_id: SandboxWorkloadId
    subject: OpaqueReference
    resource_specification_fingerprint: SandboxArtifactFingerprint
    rules: tuple[SandboxSecretPolicyRule, ...]
    policy_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.format_version,
            self.version,
            self.plan_id,
            self.plan_fingerprint,
            self.workload_id,
            self.subject,
            self.resource_specification_fingerprint,
            self.rules,
        )

    @classmethod
    def create(
        cls,
        *,
        version: SandboxPolicyVersion,
        plan: SandboxExecutionPlan,
        resources: SandboxResourceSpecification,
        rules: tuple[SandboxSecretPolicyRule, ...],
    ) -> SandboxSecretPolicy:
        ordered = tuple(sorted(rules, key=lambda item: repr(item.declaration)))
        if len({item.declaration.secret_ref for item in ordered}) != len(ordered):
            raise InvalidSecretsBoundary("policy.rules_conflict")
        content = (
            SECRET_POLICY_FORMAT,
            version,
            plan.plan_id,
            plan.plan_fingerprint,
            plan.workload_id,
            plan.subject,
            resources.specification_fingerprint,
            ordered,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        identity = derive_identity(SandboxSecretPolicyId, fingerprint)
        return cls(
            SECRET_POLICY_FORMAT,
            SandboxSecretPolicyId(identity.value),
            version,
            plan.plan_id,
            plan.plan_fingerprint,
            plan.workload_id,
            plan.subject,
            resources.specification_fingerprint,
            ordered,
            fingerprint,
        )

    def __post_init__(self) -> None:
        if self.format_version != SECRET_POLICY_FORMAT:
            raise InvalidSecretsBoundary("policy.format_unsupported")
        if self.rules != tuple(sorted(self.rules, key=lambda item: repr(item.declaration))):
            raise InvalidSecretsBoundary("policy.rules_not_canonical")
        if SandboxArtifactFingerprint.from_content(self.content()) != self.policy_fingerprint:
            raise InvalidSecretsBoundary("policy.fingerprint_mismatch")
        if derive_identity(SandboxSecretPolicyId, self.policy_fingerprint) != self.policy_id:
            raise InvalidSecretsBoundary("policy.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxSecretCapabilityFact:
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    workload_id: SandboxWorkloadId
    subject: OpaqueReference
    attempt_id: SandboxAttemptId
    declaration: SandboxSecretDeclaration
    available: bool
    authorization_ref: OpaqueReference | None
    authorized_operations: tuple[SandboxSecretOperation, ...]
    maximum_duration_seconds: int
    maximum_usage_count: int
    renewal_authorized: bool
    revocation_on_termination_supported: bool
    revocation_on_timeout_supported: bool
    revocation_on_cancellation_supported: bool
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
            raise InvalidSecretsBoundary("fact.validity_invalid")
        canonical = tuple(sorted(set(self.authorized_operations), key=lambda item: item.value))
        if canonical != self.authorized_operations:
            raise InvalidSecretsBoundary("fact.operations_not_canonical")
        if (
            not isinstance(self.maximum_duration_seconds, int)
            or isinstance(self.maximum_duration_seconds, bool)
            or self.maximum_duration_seconds <= 0
            or not isinstance(self.maximum_usage_count, int)
            or isinstance(self.maximum_usage_count, bool)
            or self.maximum_usage_count <= 0
        ):
            raise InvalidSecretsBoundary("fact.lease_limits_invalid")
        if SandboxSecretOperation.USE_ONCE in self.authorized_operations and (
            self.renewal_authorized or self.maximum_usage_count != 1
        ):
            raise InvalidSecretsBoundary("fact.use_once_renewal_conflict")
        object.__setattr__(
            self,
            "isolation_profiles",
            tuple(sorted(set(self.isolation_profiles), key=lambda item: item.value)),
        )


@dataclass(frozen=True, slots=True)
class SandboxSecretCapabilitySnapshot:
    format_version: str
    observed_at: datetime
    completeness: FactCompleteness
    facts: tuple[SandboxSecretCapabilityFact, ...]
    capability_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (self.format_version, self.observed_at, self.completeness, self.facts)

    @classmethod
    def create(
        cls,
        *,
        observed_at: datetime,
        completeness: FactCompleteness,
        facts: tuple[SandboxSecretCapabilityFact, ...],
    ) -> SandboxSecretCapabilitySnapshot:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise InvalidSecretsBoundary("snapshot.observed_at_invalid")
        ordered = tuple(sorted(facts, key=lambda item: repr(item.declaration)))
        content = (SECRET_CAPABILITY_FORMAT, observed_at, completeness, ordered)
        return cls(
            SECRET_CAPABILITY_FORMAT,
            observed_at,
            completeness,
            ordered,
            SandboxArtifactFingerprint.from_content(content),
        )

    def __post_init__(self) -> None:
        if self.format_version != SECRET_CAPABILITY_FORMAT:
            raise InvalidSecretsBoundary("snapshot.format_unsupported")
        if self.facts != tuple(sorted(self.facts, key=lambda item: repr(item.declaration))):
            raise InvalidSecretsBoundary("snapshot.facts_not_canonical")
        if SandboxArtifactFingerprint.from_content(self.content()) != self.capability_fingerprint:
            raise InvalidSecretsBoundary("snapshot.fingerprint_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxSecretGrant:
    declaration: SandboxSecretDeclaration
    subject: OpaqueReference
    workload_id: SandboxWorkloadId
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    attempt_id: SandboxAttemptId
    operations: tuple[SandboxSecretOperation, ...]
    authorization_ref: OpaqueReference
    not_before: datetime
    expires_at: datetime
    maximum_duration_seconds: int
    maximum_usage_count: int
    renewal_policy: SandboxSecretRenewalPolicy
    revoke_on_termination: bool
    revoke_on_timeout: bool
    revoke_on_cancellation: bool
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.operations != tuple(sorted(set(self.operations), key=lambda item: item.value)):
            raise InvalidSecretsBoundary("grant.operations_not_canonical")
        if (
            self.not_before.tzinfo is None
            or self.not_before.utcoffset() is None
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
            or self.expires_at <= self.not_before
            or int((self.expires_at - self.not_before).total_seconds())
            != self.maximum_duration_seconds
        ):
            raise InvalidSecretsBoundary("grant.validity_invalid")
        if SandboxSecretOperation.USE_ONCE in self.operations and (
            self.renewal_policy is not SandboxSecretRenewalPolicy.DENY
            or self.maximum_usage_count != 1
        ):
            raise InvalidSecretsBoundary("grant.use_once_renewal_conflict")
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidSecretsBoundary("grant.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxSecretDenial:
    secret_ref: OpaqueReference
    reason: SandboxSecretDenialReason
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidSecretsBoundary("denial.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxSecretGrantSet:
    grant_set_id: SandboxSecretGrantSetId
    grant_set_fingerprint: SandboxArtifactFingerprint
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    request_fingerprint: SandboxArtifactFingerprint
    capability_grant_set_fingerprint: SandboxArtifactFingerprint
    resource_specification_fingerprint: SandboxArtifactFingerprint
    policy_id: SandboxSecretPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    capability_snapshot_fingerprint: SandboxArtifactFingerprint
    evaluated_at: datetime
    grants: tuple[SandboxSecretGrant, ...]
    denials: tuple[SandboxSecretDenial, ...]
    diagnostics: tuple[str, ...]
    occurred_at: datetime

    def content(self) -> tuple[object, ...]:
        return (
            self.plan_id,
            self.plan_fingerprint,
            self.request_fingerprint,
            self.capability_grant_set_fingerprint,
            self.resource_specification_fingerprint,
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
            raise InvalidSecretsBoundary("grant_set.timestamp_invalid")
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.grant_set_fingerprint:
            raise InvalidSecretsBoundary("grant_set.fingerprint_mismatch")
        if derive_identity(SandboxSecretGrantSetId, expected) != self.grant_set_id:
            raise InvalidSecretsBoundary("grant_set.identity_mismatch")
        if self.grants != tuple(
            sorted(self.grants, key=lambda item: item.declaration.secret_ref.value)
        ):
            raise InvalidSecretsBoundary("grant_set.grants_not_canonical")
        if self.denials != tuple(sorted(self.denials, key=lambda item: item.secret_ref.value)):
            raise InvalidSecretsBoundary("grant_set.denials_not_canonical")
        if self.diagnostics != tuple(sorted(set(self.diagnostics))):
            raise InvalidSecretsBoundary("grant_set.diagnostics_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxSecretLeaseSpecification:
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    grant_set_id: SandboxSecretGrantSetId
    grant_set_fingerprint: SandboxArtifactFingerprint
    resource_specification_fingerprint: SandboxArtifactFingerprint
    leases: tuple[SandboxSecretGrant, ...]
    specification_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.plan_id,
            self.plan_fingerprint,
            self.grant_set_id,
            self.grant_set_fingerprint,
            self.resource_specification_fingerprint,
            self.leases,
        )

    def __post_init__(self) -> None:
        if self.leases != tuple(
            sorted(self.leases, key=lambda item: item.declaration.secret_ref.value)
        ):
            raise InvalidSecretsBoundary("specification.leases_not_canonical")
        if (
            SandboxArtifactFingerprint.from_content(self.content())
            != self.specification_fingerprint
        ):
            raise InvalidSecretsBoundary("specification.fingerprint_mismatch")


class SandboxSecretGrantService:
    """Derive opaque prospective lease grants without acquiring secret material."""

    def evaluate(
        self,
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        resources: SandboxResourceSpecification,
        facts: SandboxSecretCapabilitySnapshot,
        policy: SandboxSecretPolicy,
        requests: tuple[SandboxSecretRequest, ...],
        *,
        evaluated_at: datetime,
        occurred_at: datetime,
    ) -> SandboxSecretGrantSet:
        self._validate_bindings(plan, capabilities, resources, policy)
        if (
            evaluated_at.tzinfo is None
            or evaluated_at.utcoffset() is None
            or occurred_at.tzinfo is None
            or occurred_at.utcoffset() is None
        ):
            raise InvalidSecretsBoundary("grant_set.timestamp_invalid")
        ordered_requests = tuple(
            sorted(requests, key=lambda item: item.declaration.secret_ref.value)
        )
        request_fingerprint = SandboxArtifactFingerprint.from_content(
            (plan.plan_id, plan.plan_fingerprint, ordered_requests)
        )
        rules = {rule.declaration.secret_ref: rule for rule in policy.rules}
        facts_by_declaration: dict[OpaqueReference, list[SandboxSecretCapabilityFact]] = {}
        for fact in facts.facts:
            facts_by_declaration.setdefault(fact.declaration.secret_ref, []).append(fact)
        grants: list[SandboxSecretGrant] = []
        denials: list[SandboxSecretDenial] = []
        requests_by_ref: dict[OpaqueReference, list[SandboxSecretRequest]] = {}
        for request in ordered_requests:
            requests_by_ref.setdefault(request.declaration.secret_ref, []).append(request)
        for secret_ref in sorted(requests_by_ref, key=lambda item: item.value):
            matching_requests = requests_by_ref[secret_ref]
            request = matching_requests[0]
            if len(matching_requests) != 1:
                denials.append(
                    self._denial(
                        request,
                        SandboxSecretDenialReason.LEASE_UNSUPPORTED,
                        "request.correspondence",
                    )
                )
                continue
            grant, denial = self._evaluate_request(
                plan,
                capabilities,
                resources,
                facts.completeness,
                rules.get(request.declaration.secret_ref),
                facts_by_declaration.get(request.declaration.secret_ref, []),
                request,
                evaluated_at,
            )
            if grant is not None:
                grants.append(grant)
            if denial is not None:
                denials.append(denial)
        ordered_grants = tuple(sorted(grants, key=lambda item: item.declaration.secret_ref.value))
        ordered_denials = tuple(sorted(denials, key=lambda item: item.secret_ref.value))
        diagnostics = tuple(
            sorted({code for denial in ordered_denials for code in denial.rationale_codes})
        )
        content = (
            plan.plan_id,
            plan.plan_fingerprint,
            request_fingerprint,
            capabilities.grant_set_fingerprint,
            resources.specification_fingerprint,
            policy.policy_id,
            policy.policy_fingerprint,
            facts.capability_fingerprint,
            evaluated_at,
            ordered_grants,
            ordered_denials,
            diagnostics,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        identity = derive_identity(SandboxSecretGrantSetId, fingerprint)
        return SandboxSecretGrantSet(
            SandboxSecretGrantSetId(identity.value),
            fingerprint,
            plan.plan_id,
            plan.plan_fingerprint,
            request_fingerprint,
            capabilities.grant_set_fingerprint,
            resources.specification_fingerprint,
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
        grant_set: SandboxSecretGrantSet,
    ) -> SandboxSecretLeaseSpecification:
        content = (
            grant_set.plan_id,
            grant_set.plan_fingerprint,
            grant_set.grant_set_id,
            grant_set.grant_set_fingerprint,
            grant_set.resource_specification_fingerprint,
            grant_set.grants,
        )
        return SandboxSecretLeaseSpecification(
            grant_set.plan_id,
            grant_set.plan_fingerprint,
            grant_set.grant_set_id,
            grant_set.grant_set_fingerprint,
            grant_set.resource_specification_fingerprint,
            grant_set.grants,
            SandboxArtifactFingerprint.from_content(content),
        )

    @staticmethod
    def _validate_bindings(
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        resources: SandboxResourceSpecification,
        policy: SandboxSecretPolicy,
    ) -> None:
        diagnostics = []
        for name, candidate_id, candidate_fingerprint in (
            ("capability", capabilities.plan_id, capabilities.plan_fingerprint),
            ("resources", resources.plan_id, resources.plan_fingerprint),
            ("policy", policy.plan_id, policy.plan_fingerprint),
        ):
            if candidate_id != plan.plan_id:
                diagnostics.append(f"binding.{name}_plan_identity_mismatch")
            if candidate_fingerprint != plan.plan_fingerprint:
                diagnostics.append(f"binding.{name}_plan_fingerprint_mismatch")
        if policy.workload_id != plan.workload_id:
            diagnostics.append("binding.policy_workload_mismatch")
        if policy.subject != plan.subject:
            diagnostics.append("binding.policy_subject_mismatch")
        if policy.resource_specification_fingerprint != resources.specification_fingerprint:
            diagnostics.append("binding.policy_resources_mismatch")
        if diagnostics:
            raise InvalidSecretsBoundary(",".join(sorted(diagnostics)))

    @classmethod
    def _evaluate_request(
        cls,
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        resources: SandboxResourceSpecification,
        completeness: FactCompleteness,
        rule: SandboxSecretPolicyRule | None,
        facts: list[SandboxSecretCapabilityFact],
        request: SandboxSecretRequest,
        evaluated_at: datetime,
    ) -> tuple[SandboxSecretGrant | None, SandboxSecretDenial | None]:
        if completeness is FactCompleteness.INCOMPLETE:
            return None, cls._denial(
                request, SandboxSecretDenialReason.INCOMPLETE, "facts.incomplete"
            )
        if completeness is not FactCompleteness.COMPLETE:
            return None, cls._denial(
                request, SandboxSecretDenialReason.SECRET_UNAVAILABLE, "facts.unavailable"
            )
        if request.subject != plan.subject:
            return None, cls._denial(
                request, SandboxSecretDenialReason.SUBJECT_MISMATCH, "request.subject_mismatch"
            )
        if (
            request.workload_id != plan.workload_id
            or request.plan_id != plan.plan_id
            or request.plan_fingerprint != plan.plan_fingerprint
        ):
            return None, cls._denial(
                request, SandboxSecretDenialReason.SCOPE_MISMATCH, "request.plan_mismatch"
            )
        if rule is None:
            return None, cls._denial(
                request, SandboxSecretDenialReason.PROVIDER_UNSUPPORTED, "policy.declaration_absent"
            )
        if request.declaration.purpose != rule.declaration.purpose:
            return None, cls._denial(
                request, SandboxSecretDenialReason.PURPOSE_MISMATCH, "policy.purpose_mismatch"
            )
        if request.declaration.provider != rule.declaration.provider:
            return None, cls._denial(
                request,
                SandboxSecretDenialReason.PROVIDER_UNSUPPORTED,
                "policy.provider_unsupported",
            )
        if request.declaration.scope_ref != rule.declaration.scope_ref:
            return None, cls._denial(
                request, SandboxSecretDenialReason.SCOPE_MISMATCH, "policy.scope_mismatch"
            )
        if not set(request.operations) <= set(rule.allowed_operations):
            reason = (
                SandboxSecretDenialReason.RENEWAL_DENIED
                if SandboxSecretOperation.RENEW_LEASE in request.operations
                else SandboxSecretDenialReason.LEASE_UNSUPPORTED
            )
            return None, cls._denial(request, reason, "policy.operation_denied")
        if len(facts) != 1:
            return None, cls._denial(
                request, SandboxSecretDenialReason.SECRET_UNAVAILABLE, "fact.correspondence"
            )
        fact = facts[0]
        if not fact.available:
            return None, cls._denial(
                request, SandboxSecretDenialReason.SECRET_UNAVAILABLE, "fact.unavailable"
            )
        if fact.authorization_ref is None:
            return None, cls._denial(
                request,
                SandboxSecretDenialReason.AUTHORIZATION_MISSING,
                "fact.authorization_missing",
            )
        if fact.subject != request.subject or fact.workload_id != request.workload_id:
            return None, cls._denial(
                request, SandboxSecretDenialReason.SUBJECT_MISMATCH, "fact.subject_mismatch"
            )
        if fact.declaration.purpose != request.declaration.purpose:
            return None, cls._denial(
                request, SandboxSecretDenialReason.PURPOSE_MISMATCH, "fact.purpose_mismatch"
            )
        if (
            fact.plan_id != request.plan_id
            or fact.plan_fingerprint != request.plan_fingerprint
            or fact.attempt_id != request.attempt_id
            or fact.declaration.scope_ref != request.declaration.scope_ref
        ):
            return None, cls._denial(
                request, SandboxSecretDenialReason.SCOPE_MISMATCH, "fact.scope_mismatch"
            )
        if fact.declaration.provider != request.declaration.provider:
            return None, cls._denial(
                request, SandboxSecretDenialReason.PROVIDER_UNSUPPORTED, "fact.provider_unsupported"
            )
        if fact.declaration.expected_format is not request.declaration.expected_format:
            return None, cls._denial(
                request, SandboxSecretDenialReason.LEASE_UNSUPPORTED, "fact.format_mismatch"
            )
        if plan.isolation_profile_id not in fact.isolation_profiles:
            return None, cls._denial(
                request,
                SandboxSecretDenialReason.ISOLATION_INSUFFICIENT,
                "fact.isolation_insufficient",
            )
        if evaluated_at > fact.valid_until:
            return None, cls._denial(request, SandboxSecretDenialReason.EXPIRED, "fact.expired")
        if evaluated_at < fact.valid_from:
            return None, cls._denial(request, SandboxSecretDenialReason.STALE, "fact.not_yet_valid")
        if not set(request.operations) <= set(fact.authorized_operations):
            reason = (
                SandboxSecretDenialReason.RENEWAL_DENIED
                if SandboxSecretOperation.RENEW_LEASE in request.operations
                else SandboxSecretDenialReason.AUTHORIZATION_MISSING
            )
            return None, cls._denial(request, reason, "fact.operation_unauthorized")
        if (
            request.lease.renewal_policy is SandboxSecretRenewalPolicy.EXPLICIT
            or SandboxSecretOperation.RENEW_LEASE in request.operations
        ) and (
            rule.renewal_policy is not SandboxSecretRenewalPolicy.EXPLICIT
            or not fact.renewal_authorized
        ):
            return None, cls._denial(
                request, SandboxSecretDenialReason.RENEWAL_DENIED, "lease.renewal_denied"
            )
        if not cls._revocation_supported(rule, fact, request):
            return None, cls._denial(
                request, SandboxSecretDenialReason.LEASE_UNSUPPORTED, "lease.revocation_unsupported"
            )
        capability = next(
            (grant for grant in capabilities.grants if grant.capability == rule.capability),
            None,
        )
        if capability is None:
            return None, cls._denial(
                request, SandboxSecretDenialReason.CAPABILITY_ABSENT, "capability.absent"
            )
        if not capability.valid_from <= evaluated_at <= capability.valid_until:
            return None, cls._denial(request, SandboxSecretDenialReason.STALE, "capability.stale")
        if not any(
            scope.kind is SandboxCapabilityScopeKind.WILDCARD
            or scope.reference == request.declaration.scope_ref
            for scope in capability.scopes
        ):
            return None, cls._denial(
                request, SandboxSecretDenialReason.SCOPE_MISMATCH, "capability.scope_mismatch"
            )
        if request.lease.not_before < evaluated_at or request.lease.not_before < fact.valid_from:
            return None, cls._denial(
                request, SandboxSecretDenialReason.STALE, "lease.not_before_invalid"
            )
        duration = min(
            request.lease.maximum_duration_seconds,
            rule.maximum_duration_seconds,
            fact.maximum_duration_seconds,
        )
        resource_duration = cls._resource_duration_seconds(resources)
        if resource_duration is not None:
            duration = min(duration, resource_duration)
        expires_at = min(
            request.lease.requested_expires_at,
            request.lease.not_before + timedelta(seconds=duration),
            fact.valid_until,
        )
        if expires_at <= request.lease.not_before:
            return None, cls._denial(request, SandboxSecretDenialReason.EXPIRED, "lease.expired")
        usage_count = min(
            request.lease.maximum_usage_count,
            rule.maximum_usage_count,
            fact.maximum_usage_count,
        )
        renewal = (
            SandboxSecretRenewalPolicy.EXPLICIT
            if request.lease.renewal_policy is SandboxSecretRenewalPolicy.EXPLICIT
            else SandboxSecretRenewalPolicy.DENY
        )
        return (
            SandboxSecretGrant(
                request.declaration,
                request.subject,
                request.workload_id,
                request.plan_id,
                request.plan_fingerprint,
                request.attempt_id,
                request.operations,
                fact.authorization_ref,
                request.lease.not_before,
                expires_at,
                int((expires_at - request.lease.not_before).total_seconds()),
                usage_count,
                renewal,
                request.lease.revoke_on_termination,
                request.lease.revoke_on_timeout,
                request.lease.revoke_on_cancellation,
                ("secret.intersection_satisfied",),
            ),
            None,
        )

    @staticmethod
    def _revocation_supported(
        rule: SandboxSecretPolicyRule,
        fact: SandboxSecretCapabilityFact,
        request: SandboxSecretRequest,
    ) -> bool:
        return (
            (
                not rule.require_revocation_on_termination
                or (
                    request.lease.revoke_on_termination and fact.revocation_on_termination_supported
                )
            )
            and (
                not rule.require_revocation_on_timeout
                or (request.lease.revoke_on_timeout and fact.revocation_on_timeout_supported)
            )
            and (
                not rule.require_revocation_on_cancellation
                or (
                    request.lease.revoke_on_cancellation
                    and fact.revocation_on_cancellation_supported
                )
            )
        )

    @staticmethod
    def _resource_duration_seconds(
        resources: SandboxResourceSpecification,
    ) -> int | None:
        candidates = [
            limit.hard // 1000
            for limit in resources.effective_limits
            if limit.dimension
            in {
                SandboxResourceDimension.IDLE_DURATION,
                SandboxResourceDimension.WALL_CLOCK_DURATION,
            }
            and not limit.unlimited
            and limit.hard is not None
        ]
        return min(candidates) if candidates else None

    @staticmethod
    def _denial(
        request: SandboxSecretRequest,
        reason: SandboxSecretDenialReason,
        code: str,
    ) -> SandboxSecretDenial:
        return SandboxSecretDenial(
            request.declaration.secret_ref,
            reason,
            (code,),
        )
