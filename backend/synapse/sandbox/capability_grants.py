"""Pure derivation of plan-bound effective capability grants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .admission_policy import SandboxAdmissionDecision, SandboxAdmissionPolicy
from .errors import InvalidCapabilityGrantSet
from .execution_plan import SandboxExecutionPlan
from .facts import (
    FactCompleteness,
    SandboxCapabilityConstraint,
    SandboxCapabilityFact,
    SandboxCapabilityScope,
    SandboxCapabilityScopeKind,
)
from .identities import (
    OpaqueReference,
    SandboxAdmissionId,
    SandboxAdmissionPolicyId,
    SandboxArtifactFingerprint,
    SandboxCapabilityGrantSetId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    derive_identity,
)
from .models import SandboxAdmissionRequest

CAPABILITY_PERMISSION_FORMAT = "sandbox-capability-permissions-v1"


@dataclass(frozen=True, slots=True)
class SandboxPlanCapabilityPermission:
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    fact: SandboxCapabilityFact


@dataclass(frozen=True, slots=True)
class SandboxCapabilityPermissionSnapshot:
    format_version: str
    observed_at: datetime
    completeness: FactCompleteness
    facts: tuple[SandboxPlanCapabilityPermission, ...]
    permission_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.format_version,
            self.observed_at,
            self.completeness,
            self.facts,
        )

    def __post_init__(self) -> None:
        if self.format_version != CAPABILITY_PERMISSION_FORMAT:
            raise InvalidCapabilityGrantSet("permission_snapshot.format_unsupported")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise InvalidCapabilityGrantSet("permission_snapshot.observed_at_invalid")
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.permission_fingerprint:
            raise InvalidCapabilityGrantSet("permission_snapshot.fingerprint_mismatch")

    @classmethod
    def create(
        cls,
        *,
        observed_at: datetime,
        completeness: FactCompleteness,
        facts: tuple[SandboxPlanCapabilityPermission, ...],
    ) -> SandboxCapabilityPermissionSnapshot:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise InvalidCapabilityGrantSet("permission_snapshot.observed_at_invalid")
        ordered_facts = tuple(sorted(facts, key=repr))
        content: tuple[object, ...] = (
            CAPABILITY_PERMISSION_FORMAT,
            observed_at,
            completeness,
            ordered_facts,
        )
        return cls(
            format_version=CAPABILITY_PERMISSION_FORMAT,
            observed_at=observed_at,
            completeness=completeness,
            facts=ordered_facts,
            permission_fingerprint=SandboxArtifactFingerprint.from_content(content),
        )


class SandboxCapabilityDenialReason(StrEnum):
    ABSENT = "absent"
    MISMATCH = "mismatch"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    POLICY_DENIED = "policy_denied"


@dataclass(frozen=True, slots=True)
class SandboxCapabilityGrant:
    capability: str
    scopes: tuple[SandboxCapabilityScope, ...]
    constraints: tuple[SandboxCapabilityConstraint, ...]
    source_references: tuple[OpaqueReference, ...]
    valid_from: datetime
    valid_until: datetime
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.valid_from.tzinfo is None
            or self.valid_from.utcoffset() is None
            or self.valid_until.tzinfo is None
            or self.valid_until.utcoffset() is None
            or self.valid_until < self.valid_from
        ):
            raise InvalidCapabilityGrantSet("grant.validity_invalid")
        if not self.source_references or len(set(self.source_references)) != len(
            self.source_references
        ):
            raise InvalidCapabilityGrantSet("grant.source_references_invalid")
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidCapabilityGrantSet("grant.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxCapabilityDenial:
    capability: str
    reason: SandboxCapabilityDenialReason
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.rationale_codes or self.rationale_codes != tuple(
            sorted(set(self.rationale_codes))
        ):
            raise InvalidCapabilityGrantSet("denial.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxCapabilityGrantSet:
    grant_set_id: SandboxCapabilityGrantSetId
    grant_set_fingerprint: SandboxArtifactFingerprint
    request_fingerprint: SandboxArtifactFingerprint
    admission_snapshot_fingerprint: SandboxArtifactFingerprint
    permission_snapshot_fingerprint: SandboxArtifactFingerprint
    policy_id: SandboxAdmissionPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    decision_id: SandboxAdmissionId
    decision_fingerprint: SandboxArtifactFingerprint
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    evaluated_at: datetime
    grants: tuple[SandboxCapabilityGrant, ...]
    denials: tuple[SandboxCapabilityDenial, ...]
    rationale_codes: tuple[str, ...]
    occurred_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            self.request_fingerprint,
            self.admission_snapshot_fingerprint,
            self.permission_snapshot_fingerprint,
            self.policy_id,
            self.policy_fingerprint,
            self.decision_id,
            self.decision_fingerprint,
            self.plan_id,
            self.plan_fingerprint,
            self.evaluated_at,
            self.grants,
            self.denials,
            self.rationale_codes,
        )

    def __post_init__(self) -> None:
        for value, code in (
            (self.evaluated_at, "grant_set.evaluated_at_invalid"),
            (self.occurred_at, "grant_set.occurred_at_invalid"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise InvalidCapabilityGrantSet(code)
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.grant_set_fingerprint:
            raise InvalidCapabilityGrantSet("grant_set.fingerprint_mismatch")
        expected_id = derive_identity(SandboxCapabilityGrantSetId, self.grant_set_fingerprint)
        if expected_id != self.grant_set_id:
            raise InvalidCapabilityGrantSet("grant_set.identity_mismatch")
        if self.grants != tuple(sorted(self.grants, key=lambda item: item.capability)):
            raise InvalidCapabilityGrantSet("grant_set.grants_not_canonical")
        if self.denials != tuple(
            sorted(self.denials, key=lambda item: (item.capability, item.reason.value))
        ):
            raise InvalidCapabilityGrantSet("grant_set.denials_not_canonical")
        if {item.capability for item in self.grants} & {item.capability for item in self.denials}:
            raise InvalidCapabilityGrantSet("grant_set.conflicting_outcomes")
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidCapabilityGrantSet("grant_set.rationale_not_canonical")


class SandboxCapabilityGrantService:
    """Derive minimal effective grants without creating global authorization."""

    def evaluate(
        self,
        request: SandboxAdmissionRequest,
        permissions: SandboxCapabilityPermissionSnapshot,
        policy: SandboxAdmissionPolicy,
        decision: SandboxAdmissionDecision,
        plan: SandboxExecutionPlan,
        *,
        evaluated_at: datetime,
        occurred_at: datetime,
    ) -> SandboxCapabilityGrantSet:
        self._validate_bindings(request, policy, decision, plan)
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise InvalidCapabilityGrantSet("grant_set.evaluated_at_invalid")
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise InvalidCapabilityGrantSet("grant_set.occurred_at_invalid")

        declared = {item.name for item in request.declared_capabilities}
        requested = {item.name for item in request.requested_capabilities}
        permissions_by_capability: dict[str, list[SandboxPlanCapabilityPermission]] = {}
        for permission in permissions.facts:
            permissions_by_capability.setdefault(permission.fact.declaration.name, []).append(
                permission
            )

        grants: list[SandboxCapabilityGrant] = []
        denials: list[SandboxCapabilityDenial] = []
        for capability in sorted(requested):
            grant, denial = self._evaluate_capability(
                capability=capability,
                declared=declared,
                permissions=permissions_by_capability.get(capability, []),
                completeness=permissions.completeness,
                request=request,
                policy=policy,
                plan=plan,
                evaluated_at=evaluated_at,
            )
            if grant is not None:
                grants.append(grant)
            if denial is not None:
                denials.append(denial)

        ordered_grants = tuple(sorted(grants, key=lambda item: item.capability))
        ordered_denials = tuple(
            sorted(denials, key=lambda item: (item.capability, item.reason.value))
        )
        rationale = tuple(
            sorted(
                {code for item in ordered_grants for code in item.rationale_codes}
                | {code for item in ordered_denials for code in item.rationale_codes}
            )
        )
        request_fingerprint = SandboxArtifactFingerprint.from_content(request)
        content: tuple[object, ...] = (
            request_fingerprint,
            plan.snapshot_fingerprint,
            permissions.permission_fingerprint,
            policy.policy_id,
            policy.policy_fingerprint,
            decision.decision_id,
            decision.decision_fingerprint,
            plan.plan_id,
            plan.plan_fingerprint,
            evaluated_at,
            ordered_grants,
            ordered_denials,
            rationale,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        grant_set_id = derive_identity(SandboxCapabilityGrantSetId, fingerprint)
        return SandboxCapabilityGrantSet(
            grant_set_id=SandboxCapabilityGrantSetId(grant_set_id.value),
            grant_set_fingerprint=fingerprint,
            request_fingerprint=request_fingerprint,
            admission_snapshot_fingerprint=plan.snapshot_fingerprint,
            permission_snapshot_fingerprint=permissions.permission_fingerprint,
            policy_id=policy.policy_id,
            policy_fingerprint=policy.policy_fingerprint,
            decision_id=decision.decision_id,
            decision_fingerprint=decision.decision_fingerprint,
            plan_id=plan.plan_id,
            plan_fingerprint=plan.plan_fingerprint,
            evaluated_at=evaluated_at,
            grants=ordered_grants,
            denials=ordered_denials,
            rationale_codes=rationale,
            occurred_at=occurred_at,
        )

    @staticmethod
    def _validate_bindings(
        request: SandboxAdmissionRequest,
        policy: SandboxAdmissionPolicy,
        decision: SandboxAdmissionDecision,
        plan: SandboxExecutionPlan,
    ) -> None:
        request_fingerprint = SandboxArtifactFingerprint.from_content(request)
        mismatches = []
        if plan.request_fingerprint != request_fingerprint:
            mismatches.append("binding.request_mismatch")
        if plan.policy_id != policy.policy_id:
            mismatches.append("binding.policy_identity_mismatch")
        if plan.policy_fingerprint != policy.policy_fingerprint:
            mismatches.append("binding.policy_fingerprint_mismatch")
        if plan.decision_id != decision.decision_id:
            mismatches.append("binding.decision_identity_mismatch")
        if plan.decision_fingerprint != decision.decision_fingerprint:
            mismatches.append("binding.decision_fingerprint_mismatch")
        if tuple(sorted(item.name for item in plan.requested_capabilities)) != tuple(
            sorted(item.name for item in request.requested_capabilities)
        ):
            mismatches.append("binding.capability_requests_mismatch")
        if mismatches:
            raise InvalidCapabilityGrantSet(",".join(sorted(mismatches)))

    @classmethod
    def _evaluate_capability(
        cls,
        *,
        capability: str,
        declared: set[str],
        permissions: list[SandboxPlanCapabilityPermission],
        completeness: FactCompleteness,
        request: SandboxAdmissionRequest,
        policy: SandboxAdmissionPolicy,
        plan: SandboxExecutionPlan,
        evaluated_at: datetime,
    ) -> tuple[SandboxCapabilityGrant | None, SandboxCapabilityDenial | None]:
        if capability not in declared:
            return None, cls._denial(
                capability, SandboxCapabilityDenialReason.MISMATCH, "declaration.missing"
            )
        if capability not in policy.allowed_capabilities:
            return None, cls._denial(
                capability, SandboxCapabilityDenialReason.POLICY_DENIED, "policy.denied"
            )
        if completeness is FactCompleteness.INCOMPLETE:
            return None, cls._denial(
                capability, SandboxCapabilityDenialReason.INCOMPLETE, "facts.incomplete"
            )
        if completeness in {FactCompleteness.ABSENT, FactCompleteness.NOT_REQUIRED}:
            return None, cls._denial(
                capability, SandboxCapabilityDenialReason.ABSENT, "facts.absent"
            )
        if completeness is FactCompleteness.UNKNOWN:
            return None, cls._denial(
                capability, SandboxCapabilityDenialReason.UNAVAILABLE, "facts.unavailable"
            )
        if not permissions:
            return None, cls._denial(
                capability, SandboxCapabilityDenialReason.ABSENT, "permission.absent"
            )
        if len(set(permissions)) != 1:
            return None, cls._denial(
                capability, SandboxCapabilityDenialReason.MISMATCH, "permission.conflict"
            )
        permission = permissions[0]
        fact = permission.fact
        planned_references = {
            item.reference
            for item in plan.external_capability_refs
            if item.capability == capability
        }
        if (
            fact.subject != request.subject
            or fact.actor_ref != request.actor_ref
            or fact.purpose != request.purpose
            or fact.plan_intent_ref != plan.execution_profile
            or fact.declaration.name != capability
            or fact.external_grant_ref not in planned_references
            or permission.plan_id != plan.plan_id
            or permission.plan_fingerprint != plan.plan_fingerprint
        ):
            return None, cls._denial(
                capability,
                SandboxCapabilityDenialReason.MISMATCH,
                "permission.correspondence",
            )
        if not fact.valid_from <= evaluated_at <= fact.valid_until:
            return None, cls._denial(
                capability, SandboxCapabilityDenialReason.STALE, "permission.stale"
            )
        if fact.supported is not True or plan.isolation_profile_id not in fact.isolation_profiles:
            return None, cls._denial(
                capability,
                SandboxCapabilityDenialReason.UNSUPPORTED,
                "isolation.unsupported",
            )
        if fact.external_grant_ref is None:
            return None, cls._denial(
                capability,
                SandboxCapabilityDenialReason.UNAVAILABLE,
                "permission.reference_unavailable",
            )
        if (
            any(scope.kind is SandboxCapabilityScopeKind.WILDCARD for scope in fact.scopes)
            and not policy.allow_capability_wildcards
        ):
            return None, cls._denial(
                capability,
                SandboxCapabilityDenialReason.POLICY_DENIED,
                "policy.wildcard_denied",
            )
        scopes = tuple(sorted(fact.scopes, key=lambda item: (item.kind.value, repr(item))))
        constraints = tuple(sorted(fact.constraints, key=lambda item: item.name))
        return (
            SandboxCapabilityGrant(
                capability=capability,
                scopes=scopes,
                constraints=constraints,
                source_references=(fact.external_grant_ref,),
                valid_from=evaluated_at,
                valid_until=fact.valid_until,
                rationale_codes=("grant.external_permission_matched",),
            ),
            None,
        )

    @staticmethod
    def _denial(
        capability: str, reason: SandboxCapabilityDenialReason, code: str
    ) -> SandboxCapabilityDenial:
        return SandboxCapabilityDenial(
            capability=capability,
            reason=reason,
            rationale_codes=(code,),
        )
