"""Deterministic Sandbox admission policy and decision artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .assessment import (
    AdmissionFactProperty,
    DimensionAssessment,
    FactCorrespondence,
    FactFreshness,
    SandboxAdmissionFactsAssessment,
)
from .errors import InvalidAdmissionDecision, InvalidAdmissionPolicy
from .facts import AdmissionFactDimension, FactCompleteness
from .identities import (
    SandboxAdmissionId,
    SandboxAdmissionPolicyId,
    SandboxArtifactFingerprint,
    SandboxIsolationProfileId,
    SandboxPolicyVersion,
    SandboxWorkloadId,
    derive_identity,
)
from .models import SandboxAdmissionRequest

ADMISSION_POLICY_FORMAT = "sandbox-admission-policy-v1"


class SandboxAdmissionDecisionOutcome(StrEnum):
    ADMITTED = "admitted"
    DENIED = "denied"
    INCOMPLETE = "incomplete"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


ADMISSION_OUTCOME_PRECEDENCE = (
    SandboxAdmissionDecisionOutcome.DENIED,
    SandboxAdmissionDecisionOutcome.STALE,
    SandboxAdmissionDecisionOutcome.UNAVAILABLE,
    SandboxAdmissionDecisionOutcome.INCOMPLETE,
)


@dataclass(frozen=True, slots=True)
class AdmissionPolicyTreatments:
    mismatch: SandboxAdmissionDecisionOutcome
    stale: SandboxAdmissionDecisionOutcome
    unavailable: SandboxAdmissionDecisionOutcome
    incomplete: SandboxAdmissionDecisionOutcome

    def __post_init__(self) -> None:
        expected = (
            SandboxAdmissionDecisionOutcome.DENIED,
            SandboxAdmissionDecisionOutcome.STALE,
            SandboxAdmissionDecisionOutcome.UNAVAILABLE,
            SandboxAdmissionDecisionOutcome.INCOMPLETE,
        )
        if (self.mismatch, self.stale, self.unavailable, self.incomplete) != expected:
            raise InvalidAdmissionPolicy("admission policy treatments violate outcome semantics")


@dataclass(frozen=True, slots=True)
class AdmissionDimensionRequirement:
    dimension: AdmissionFactDimension
    required: bool
    allowed_completeness: tuple[FactCompleteness, ...]
    allow_not_required: bool
    require_fresh: bool

    def __post_init__(self) -> None:
        if not self.allowed_completeness:
            raise InvalidAdmissionPolicy("dimension requirement needs explicit completeness")
        if len(set(self.allowed_completeness)) != len(self.allowed_completeness):
            raise InvalidAdmissionPolicy("allowed completeness values must be unique")
        if (
            FactCompleteness.NOT_REQUIRED in self.allowed_completeness
            and not self.allow_not_required
        ):
            raise InvalidAdmissionPolicy("NOT_REQUIRED needs explicit policy permission")


@dataclass(frozen=True, slots=True)
class SandboxAdmissionPolicy:
    format_version: str
    policy_id: SandboxAdmissionPolicyId
    version: SandboxPolicyVersion
    dimension_requirements: tuple[AdmissionDimensionRequirement, ...]
    treatments: AdmissionPolicyTreatments
    minimum_isolation_profiles: tuple[SandboxIsolationProfileId, ...]
    require_isolation_support: bool
    require_approval_fact: bool
    require_external_capability_grants: bool
    require_external_resource_grants: bool
    allowed_capabilities: tuple[str, ...]
    allow_capability_wildcards: bool
    outcome_precedence: tuple[SandboxAdmissionDecisionOutcome, ...]
    policy_fingerprint: SandboxArtifactFingerprint

    def semantic_content(self) -> tuple[object, ...]:
        return (
            self.format_version,
            self.version,
            self.dimension_requirements,
            self.treatments,
            self.minimum_isolation_profiles,
            self.require_isolation_support,
            self.require_approval_fact,
            self.require_external_capability_grants,
            self.require_external_resource_grants,
            self.allowed_capabilities,
            self.allow_capability_wildcards,
            self.outcome_precedence,
        )

    def __post_init__(self) -> None:
        if self.format_version != ADMISSION_POLICY_FORMAT:
            raise InvalidAdmissionPolicy("unsupported admission policy format")
        dimensions = [item.dimension for item in self.dimension_requirements]
        if len(dimensions) != len(set(dimensions)) or set(dimensions) != set(
            AdmissionFactDimension
        ):
            raise InvalidAdmissionPolicy("policy must define every dimension exactly once")
        if self.outcome_precedence != ADMISSION_OUTCOME_PRECEDENCE:
            raise InvalidAdmissionPolicy("policy outcome precedence violates closed semantics")
        expected_fingerprint = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if self.policy_fingerprint != expected_fingerprint:
            raise InvalidAdmissionPolicy("policy fingerprint does not match canonical content")
        expected_id = derive_identity(
            SandboxAdmissionPolicyId, self.version, self.policy_fingerprint
        )
        if self.policy_id != expected_id:
            raise InvalidAdmissionPolicy("policy identity does not match semantic content")

    @classmethod
    def create(
        cls,
        *,
        version: SandboxPolicyVersion,
        dimension_requirements: tuple[AdmissionDimensionRequirement, ...],
        treatments: AdmissionPolicyTreatments,
        minimum_isolation_profiles: tuple[SandboxIsolationProfileId, ...],
        require_isolation_support: bool,
        require_approval_fact: bool,
        require_external_capability_grants: bool,
        require_external_resource_grants: bool,
        allowed_capabilities: tuple[str, ...],
        allow_capability_wildcards: bool,
        outcome_precedence: tuple[SandboxAdmissionDecisionOutcome, ...],
    ) -> SandboxAdmissionPolicy:
        ordered_requirements = tuple(
            sorted(dimension_requirements, key=lambda item: item.dimension.value)
        )
        normalized_requirements = tuple(
            AdmissionDimensionRequirement(
                item.dimension,
                item.required,
                tuple(sorted(item.allowed_completeness, key=lambda value: value.value)),
                item.allow_not_required,
                item.require_fresh,
            )
            for item in ordered_requirements
        )
        ordered_profiles = tuple(
            sorted(set(minimum_isolation_profiles), key=lambda item: item.value)
        )
        ordered_capabilities = tuple(sorted(set(allowed_capabilities)))
        if len(ordered_capabilities) != len(allowed_capabilities):
            raise InvalidAdmissionPolicy("allowed capabilities must be unique")
        semantic_content: tuple[object, ...] = (
            ADMISSION_POLICY_FORMAT,
            version,
            normalized_requirements,
            treatments,
            ordered_profiles,
            require_isolation_support,
            require_approval_fact,
            require_external_capability_grants,
            require_external_resource_grants,
            ordered_capabilities,
            allow_capability_wildcards,
            outcome_precedence,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(semantic_content)
        policy_id = derive_identity(SandboxAdmissionPolicyId, version, fingerprint)
        return cls(
            format_version=ADMISSION_POLICY_FORMAT,
            policy_id=SandboxAdmissionPolicyId(policy_id.value),
            version=version,
            dimension_requirements=normalized_requirements,
            treatments=treatments,
            minimum_isolation_profiles=ordered_profiles,
            require_isolation_support=require_isolation_support,
            require_approval_fact=require_approval_fact,
            require_external_capability_grants=require_external_capability_grants,
            require_external_resource_grants=require_external_resource_grants,
            allowed_capabilities=ordered_capabilities,
            allow_capability_wildcards=allow_capability_wildcards,
            outcome_precedence=outcome_precedence,
            policy_fingerprint=fingerprint,
        )


@dataclass(frozen=True, slots=True)
class AdmissionDecisionDiagnostic:
    dimension: AdmissionFactDimension | None
    code: str


@dataclass(frozen=True, slots=True)
class SandboxAdmissionDecision:
    decision_id: SandboxAdmissionId
    workload_id: SandboxWorkloadId
    request_fingerprint: SandboxArtifactFingerprint
    assessment_fingerprint: SandboxArtifactFingerprint
    policy_id: SandboxAdmissionPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    outcome: SandboxAdmissionDecisionOutcome
    rationale_codes: tuple[str, ...]
    diagnostics: tuple[AdmissionDecisionDiagnostic, ...]
    decision_fingerprint: SandboxArtifactFingerprint
    occurred_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            self.workload_id,
            self.request_fingerprint,
            self.assessment_fingerprint,
            self.policy_id,
            self.policy_fingerprint,
            self.outcome,
            self.rationale_codes,
            self.diagnostics,
        )

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise InvalidAdmissionDecision("decision occurrence timestamp must be timezone-aware")
        expected_fingerprint = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if self.decision_fingerprint != expected_fingerprint:
            raise InvalidAdmissionDecision("decision fingerprint does not match semantic content")
        expected_id = derive_identity(SandboxAdmissionId, self.decision_fingerprint)
        if self.decision_id != expected_id:
            raise InvalidAdmissionDecision("decision identity does not match semantic content")


class SandboxAdmissionDecisionService:
    """Apply explicit admission policy without producing authorization or grants."""

    def decide(
        self,
        request: SandboxAdmissionRequest,
        assessment: SandboxAdmissionFactsAssessment,
        policy: SandboxAdmissionPolicy,
        *,
        occurred_at: datetime,
    ) -> SandboxAdmissionDecision:
        request_fingerprint = SandboxArtifactFingerprint.from_content(request)
        if assessment.request_fingerprint != request_fingerprint:
            raise InvalidAdmissionDecision("assessment does not bind to the supplied request")

        rationale: set[str] = set()
        diagnostics: set[AdmissionDecisionDiagnostic] = {
            AdmissionDecisionDiagnostic(item.dimension, item.code)
            for item in assessment.diagnostics
        }
        severity: set[SandboxAdmissionDecisionOutcome] = set()
        requirements = {item.dimension: item for item in policy.dimension_requirements}
        dimensions = {item.dimension: item for item in assessment.dimensions}

        for dimension in AdmissionFactDimension:
            self._evaluate_dimension(
                dimensions[dimension],
                requirements[dimension],
                policy,
                severity,
                rationale,
                diagnostics,
            )

        properties = {item.property: item.value for item in assessment.properties}
        self._evaluate_policy_properties(
            request, policy, dimensions, properties, severity, rationale, diagnostics
        )
        outcome = self._precedence(severity, policy.outcome_precedence)
        if outcome is SandboxAdmissionDecisionOutcome.ADMITTED:
            rationale.add("admission.criteria_satisfied")

        ordered_rationale = tuple(sorted(rationale))
        ordered_diagnostics = tuple(
            sorted(
                diagnostics,
                key=lambda item: (
                    "" if item.dimension is None else item.dimension.value,
                    item.code,
                ),
            )
        )
        semantic_content: tuple[object, ...] = (
            request.workload_id,
            request_fingerprint,
            assessment.assessment_fingerprint,
            policy.policy_id,
            policy.policy_fingerprint,
            outcome,
            ordered_rationale,
            ordered_diagnostics,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(semantic_content)
        decision_id = derive_identity(SandboxAdmissionId, fingerprint)
        return SandboxAdmissionDecision(
            decision_id=SandboxAdmissionId(decision_id.value),
            workload_id=request.workload_id,
            request_fingerprint=request_fingerprint,
            assessment_fingerprint=assessment.assessment_fingerprint,
            policy_id=policy.policy_id,
            policy_fingerprint=policy.policy_fingerprint,
            outcome=outcome,
            rationale_codes=ordered_rationale,
            diagnostics=ordered_diagnostics,
            decision_fingerprint=fingerprint,
            occurred_at=occurred_at,
        )

    @staticmethod
    def _evaluate_dimension(
        assessment: DimensionAssessment,
        requirement: AdmissionDimensionRequirement,
        policy: SandboxAdmissionPolicy,
        severity: set[SandboxAdmissionDecisionOutcome],
        rationale: set[str],
        diagnostics: set[AdmissionDecisionDiagnostic],
    ) -> None:
        dimension = assessment.dimension
        rationale_before = len(rationale)
        if assessment.correspondence is FactCorrespondence.MISMATCH:
            severity.add(policy.treatments.mismatch)
            rationale.add(f"{dimension.value}.mismatch")
        if assessment.freshness is FactFreshness.STALE:
            severity.add(policy.treatments.stale)
            rationale.add(f"{dimension.value}.stale")
        if assessment.completeness is FactCompleteness.INCOMPLETE:
            severity.add(policy.treatments.incomplete)
            rationale.add(f"{dimension.value}.incomplete")
        if assessment.completeness is not FactCompleteness.INCOMPLETE and (
            assessment.completeness in {FactCompleteness.ABSENT, FactCompleteness.UNKNOWN}
            or assessment.correspondence is FactCorrespondence.UNKNOWN
            or assessment.freshness is FactFreshness.UNKNOWN
        ):
            severity.add(policy.treatments.unavailable)
            rationale.add(f"{dimension.value}.unavailable")
        if assessment.completeness not in requirement.allowed_completeness:
            if assessment.completeness is FactCompleteness.NOT_REQUIRED:
                severity.add(policy.treatments.mismatch)
                rationale.add(f"{dimension.value}.not_required_disallowed")
            elif requirement.required and assessment.completeness in {
                FactCompleteness.ABSENT,
                FactCompleteness.UNKNOWN,
            }:
                severity.add(policy.treatments.unavailable)
                rationale.add(f"{dimension.value}.completeness_required")
        if (
            assessment.completeness is FactCompleteness.NOT_REQUIRED
            and not requirement.allow_not_required
        ):
            severity.add(policy.treatments.mismatch)
            rationale.add(f"{dimension.value}.not_required_disallowed")
        if requirement.require_fresh and assessment.freshness is FactFreshness.NOT_REQUIRED:
            severity.add(policy.treatments.unavailable)
            rationale.add(f"{dimension.value}.freshness_required")
        if len(rationale) > rationale_before:
            diagnostics.add(AdmissionDecisionDiagnostic(dimension, "policy.requirement_evaluated"))

    @classmethod
    def _evaluate_policy_properties(
        cls,
        request: SandboxAdmissionRequest,
        policy: SandboxAdmissionPolicy,
        dimensions: dict[AdmissionFactDimension, DimensionAssessment],
        properties: dict[AdmissionFactProperty, bool | None],
        severity: set[SandboxAdmissionDecisionOutcome],
        rationale: set[str],
        diagnostics: set[AdmissionDecisionDiagnostic],
    ) -> None:
        if (
            policy.minimum_isolation_profiles
            and request.isolation_profile_id not in policy.minimum_isolation_profiles
        ):
            severity.add(policy.treatments.mismatch)
            rationale.add("isolation.profile_disallowed")
        cls._require_property(
            policy.require_approval_fact,
            AdmissionFactProperty.APPROVAL_CORRESPONDS,
            AdmissionFactDimension.APPROVAL,
            "approval.fact_required",
            dimensions,
            properties,
            policy,
            severity,
            rationale,
        )
        cls._require_property(
            policy.require_external_capability_grants,
            AdmissionFactProperty.CAPABILITY_EXTERNAL_GRANTS_COMPLETE,
            AdmissionFactDimension.CAPABILITIES,
            "capabilities.external_grants_required",
            dimensions,
            properties,
            policy,
            severity,
            rationale,
        )
        cls._require_property(
            policy.require_external_resource_grants,
            AdmissionFactProperty.RESOURCE_EXTERNAL_GRANTS_COMPLETE,
            AdmissionFactDimension.RESOURCES,
            "resources.external_grants_required",
            dimensions,
            properties,
            policy,
            severity,
            rationale,
        )
        cls._require_property(
            policy.require_isolation_support,
            AdmissionFactProperty.ISOLATION_SUPPORTED,
            AdmissionFactDimension.ISOLATION,
            "isolation.support_required",
            dimensions,
            properties,
            policy,
            severity,
            rationale,
        )
        if rationale:
            diagnostics.add(AdmissionDecisionDiagnostic(None, "policy.criteria_evaluated"))

    @staticmethod
    def _require_property(
        required: bool,
        property_name: AdmissionFactProperty,
        dimension: AdmissionFactDimension,
        code: str,
        dimensions: dict[AdmissionFactDimension, DimensionAssessment],
        properties: dict[AdmissionFactProperty, bool | None],
        policy: SandboxAdmissionPolicy,
        severity: set[SandboxAdmissionDecisionOutcome],
        rationale: set[str],
    ) -> None:
        if not required or properties.get(property_name) is True:
            return
        factual = dimensions[dimension]
        if (
            factual.completeness in {FactCompleteness.ABSENT, FactCompleteness.UNKNOWN}
            or factual.correspondence is FactCorrespondence.UNKNOWN
        ):
            severity.add(policy.treatments.unavailable)
        elif factual.completeness is FactCompleteness.INCOMPLETE:
            severity.add(policy.treatments.incomplete)
        else:
            severity.add(policy.treatments.mismatch)
        rationale.add(code)

    @staticmethod
    def _precedence(
        severity: set[SandboxAdmissionDecisionOutcome],
        precedence: tuple[SandboxAdmissionDecisionOutcome, ...],
    ) -> SandboxAdmissionDecisionOutcome:
        return next(
            (outcome for outcome in precedence if outcome in severity),
            SandboxAdmissionDecisionOutcome.ADMITTED,
        )
