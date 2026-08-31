"""Pure correspondence, completeness and freshness assessment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .errors import InvalidAdmissionFacts
from .facts import (
    AdmissionFactDimension,
    ArtifactAvailability,
    FactCompleteness,
    HandoffReadiness,
    SandboxAdmissionFactsSnapshot,
)
from .identities import SandboxArtifactFingerprint
from .models import SandboxAdmissionRequest


class FactCorrespondence(StrEnum):
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not_required"
    MATCH = "match"
    MISMATCH = "mismatch"


class FactFreshness(StrEnum):
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not_required"
    FRESH = "fresh"
    STALE = "stale"


class AdmissionFactsOutcome(StrEnum):
    SATISFIED = "satisfied"
    INCOMPLETE = "incomplete"
    MISMATCH = "mismatch"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class AdmissionFactProperty(StrEnum):
    APPROVAL_CORRESPONDS = "approval_corresponds"
    CAPABILITY_EXTERNAL_GRANTS_COMPLETE = "capability_external_grants_complete"
    RESOURCE_EXTERNAL_GRANTS_COMPLETE = "resource_external_grants_complete"
    ISOLATION_SUPPORTED = "isolation_supported"


@dataclass(frozen=True, slots=True)
class AdmissionFactPropertyValue:
    property: AdmissionFactProperty
    value: bool | None


@dataclass(frozen=True, slots=True)
class AdmissionFactDiagnostic:
    dimension: AdmissionFactDimension
    code: str


@dataclass(frozen=True, slots=True)
class DimensionAssessment:
    dimension: AdmissionFactDimension
    correspondence: FactCorrespondence
    completeness: FactCompleteness
    freshness: FactFreshness


@dataclass(frozen=True, slots=True)
class SandboxAdmissionFactsAssessment:
    request_fingerprint: SandboxArtifactFingerprint
    snapshot_fingerprint: SandboxArtifactFingerprint
    evaluated_at: datetime
    dimensions: tuple[DimensionAssessment, ...]
    properties: tuple[AdmissionFactPropertyValue, ...]
    diagnostics: tuple[AdmissionFactDiagnostic, ...]
    outcome: AdmissionFactsOutcome
    assessment_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.request_fingerprint,
            self.snapshot_fingerprint,
            self.evaluated_at,
            self.dimensions,
            self.properties,
            self.diagnostics,
            self.outcome,
        )

    def __post_init__(self) -> None:
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.assessment_fingerprint:
            raise InvalidAdmissionFacts("assessment fingerprint does not match canonical content")


class SandboxAdmissionFactsAssessmentService:
    """Assess supplied facts without deciding admission, authorization or grants."""

    def assess(
        self,
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        *,
        evaluated_at: datetime,
    ) -> SandboxAdmissionFactsAssessment:
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise InvalidAdmissionFacts("evaluated_at must be timezone-aware")
        completeness = {item.dimension: item.status for item in snapshot.completeness}
        correspondence = {item: FactCorrespondence.UNKNOWN for item in AdmissionFactDimension}
        freshness = {item: FactFreshness.NOT_REQUIRED for item in AdmissionFactDimension}
        diagnostics: list[AdmissionFactDiagnostic] = []

        self._handoff(request, snapshot, correspondence, diagnostics)
        self._artifact(request, snapshot, correspondence, diagnostics)
        self._policy(request, snapshot, evaluated_at, correspondence, freshness, diagnostics)
        self._approval(request, snapshot, evaluated_at, correspondence, freshness, diagnostics)
        self._capabilities(request, snapshot, correspondence, diagnostics)
        self._resources(request, snapshot, correspondence, diagnostics)
        self._isolation(request, snapshot, correspondence, diagnostics)
        self._evidence(request, snapshot, correspondence, diagnostics)

        for dimension in AdmissionFactDimension:
            status = completeness[dimension]
            if status is FactCompleteness.NOT_REQUIRED:
                if self._not_required_by_request(request, snapshot, dimension):
                    correspondence[dimension] = FactCorrespondence.NOT_REQUIRED
                    freshness[dimension] = FactFreshness.NOT_REQUIRED
                else:
                    correspondence[dimension] = FactCorrespondence.MISMATCH
                    diagnostics.append(
                        AdmissionFactDiagnostic(dimension, "not_required.contradiction")
                    )
            elif status in {FactCompleteness.ABSENT, FactCompleteness.UNKNOWN}:
                diagnostics.append(AdmissionFactDiagnostic(dimension, f"{status.value}.facts"))

        dimensions = tuple(
            DimensionAssessment(
                dimension,
                correspondence[dimension],
                completeness[dimension],
                freshness[dimension],
            )
            for dimension in AdmissionFactDimension
        )
        properties = self._properties(request, snapshot, dimensions)
        ordered_diagnostics = tuple(
            sorted(set(diagnostics), key=lambda item: (item.dimension, item.code))
        )
        outcome = self._outcome(dimensions)
        request_fingerprint = SandboxArtifactFingerprint.from_content(request)
        content: tuple[object, ...] = (
            request_fingerprint,
            snapshot.snapshot_fingerprint,
            evaluated_at,
            dimensions,
            properties,
            ordered_diagnostics,
            outcome,
        )
        return SandboxAdmissionFactsAssessment(
            request_fingerprint=request_fingerprint,
            snapshot_fingerprint=snapshot.snapshot_fingerprint,
            evaluated_at=evaluated_at,
            dimensions=dimensions,
            properties=properties,
            diagnostics=ordered_diagnostics,
            outcome=outcome,
            assessment_fingerprint=SandboxArtifactFingerprint.from_content(content),
        )

    @staticmethod
    def _properties(
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        dimensions: tuple[DimensionAssessment, ...],
    ) -> tuple[AdmissionFactPropertyValue, ...]:
        by_dimension = {item.dimension: item for item in dimensions}
        requested_capabilities = {item.name for item in request.requested_capabilities}
        externally_granted_capabilities = {
            fact.declaration.name
            for fact in snapshot.capability_facts
            if fact.external_grant_ref is not None
        }
        requested_resources = {item.resource for item in request.requested_resources}
        externally_granted_resources = {fact.limit.resource for fact in snapshot.resource_facts}
        values = (
            AdmissionFactPropertyValue(
                AdmissionFactProperty.APPROVAL_CORRESPONDS,
                by_dimension[AdmissionFactDimension.APPROVAL].correspondence
                in {FactCorrespondence.MATCH, FactCorrespondence.NOT_REQUIRED},
            ),
            AdmissionFactPropertyValue(
                AdmissionFactProperty.CAPABILITY_EXTERNAL_GRANTS_COMPLETE,
                requested_capabilities <= externally_granted_capabilities,
            ),
            AdmissionFactPropertyValue(
                AdmissionFactProperty.RESOURCE_EXTERNAL_GRANTS_COMPLETE,
                requested_resources <= externally_granted_resources,
            ),
            AdmissionFactPropertyValue(
                AdmissionFactProperty.ISOLATION_SUPPORTED,
                any(
                    fact.profile_id == request.isolation_profile_id
                    and fact.policy_version == request.isolation_policy_version
                    and fact.supported is True
                    for fact in snapshot.isolation_facts
                ),
            ),
        )
        return tuple(sorted(values, key=lambda item: item.property.value))

    @staticmethod
    def _not_required_by_request(
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        dimension: AdmissionFactDimension,
    ) -> bool:
        if dimension is AdmissionFactDimension.APPROVAL:
            return request.approval_ref is None and not snapshot.approval_facts
        if dimension is AdmissionFactDimension.CAPABILITIES:
            return not request.requested_capabilities and not snapshot.capability_facts
        if dimension is AdmissionFactDimension.RESOURCES:
            return not request.requested_resources and not snapshot.resource_facts
        if dimension is AdmissionFactDimension.EVIDENCE:
            return not snapshot.evidence_facts
        return False

    @staticmethod
    def _set_match(
        dimension: AdmissionFactDimension,
        matches: bool,
        correspondence: dict[AdmissionFactDimension, FactCorrespondence],
        diagnostics: list[AdmissionFactDiagnostic],
        code: str,
    ) -> None:
        correspondence[dimension] = (
            FactCorrespondence.MATCH if matches else FactCorrespondence.MISMATCH
        )
        if not matches:
            diagnostics.append(AdmissionFactDiagnostic(dimension, code))

    def _handoff(
        self,
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        correspondence: dict[AdmissionFactDimension, FactCorrespondence],
        diagnostics: list[AdmissionFactDiagnostic],
    ) -> None:
        facts = set(snapshot.handoff_facts)
        if not facts:
            return
        matches = len(facts) == 1
        fact = sorted(facts, key=repr)[0]
        matches = matches and (
            fact.subject == request.subject
            and fact.handoff_fingerprint == request.handoff_fingerprint
            and fact.actor_ref == request.actor_ref
            and fact.purpose == request.purpose
            and fact.plan_intent_ref == request.execution_profile
            and fact.readiness is HandoffReadiness.READY
        )
        self._set_match(
            AdmissionFactDimension.HANDOFF,
            matches,
            correspondence,
            diagnostics,
            "handoff.correspondence",
        )

    def _artifact(
        self,
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        correspondence: dict[AdmissionFactDimension, FactCorrespondence],
        diagnostics: list[AdmissionFactDiagnostic],
    ) -> None:
        facts = set(snapshot.artifact_facts)
        if not facts:
            return
        handoff_fingerprints = {fact.artifact_fingerprint for fact in snapshot.handoff_facts}
        matches = (
            len(facts) == 1
            and len(handoff_fingerprints) == 1
            and all(
                fact.subject == request.subject
                and fact.fingerprint in handoff_fingerprints
                and fact.availability is ArtifactAvailability.AVAILABLE
                for fact in facts
            )
        )
        self._set_match(
            AdmissionFactDimension.ARTIFACT,
            matches,
            correspondence,
            diagnostics,
            "artifact.correspondence",
        )

    def _policy(
        self,
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        evaluated_at: datetime,
        correspondence: dict[AdmissionFactDimension, FactCorrespondence],
        freshness: dict[AdmissionFactDimension, FactFreshness],
        diagnostics: list[AdmissionFactDiagnostic],
    ) -> None:
        facts = set(snapshot.policy_facts)
        if not facts:
            freshness[AdmissionFactDimension.POLICY] = FactFreshness.UNKNOWN
            return
        matches = (
            len(facts) == len(request.policy_refs)
            and {fact.policy_ref for fact in facts} == set(request.policy_refs)
            and all(
                fact.subject == request.subject and fact.version == request.isolation_policy_version
                for fact in facts
            )
        )
        self._set_match(
            AdmissionFactDimension.POLICY,
            matches,
            correspondence,
            diagnostics,
            "policy.correspondence",
        )
        is_fresh = all(fact.valid_from <= evaluated_at <= fact.valid_until for fact in facts)
        freshness[AdmissionFactDimension.POLICY] = (
            FactFreshness.FRESH if is_fresh else FactFreshness.STALE
        )
        if not is_fresh:
            diagnostics.append(
                AdmissionFactDiagnostic(AdmissionFactDimension.POLICY, "policy.stale")
            )

    def _approval(
        self,
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        evaluated_at: datetime,
        correspondence: dict[AdmissionFactDimension, FactCorrespondence],
        freshness: dict[AdmissionFactDimension, FactFreshness],
        diagnostics: list[AdmissionFactDiagnostic],
    ) -> None:
        facts = set(snapshot.approval_facts)
        if request.approval_ref is None:
            return
        if not facts:
            freshness[AdmissionFactDimension.APPROVAL] = FactFreshness.UNKNOWN
            return
        matches = len(facts) == 1 and all(
            fact.approval_ref == request.approval_ref
            and fact.subject == request.subject
            and fact.actor_ref == request.actor_ref
            and fact.purpose == request.purpose
            and fact.plan_intent_ref == request.execution_profile
            for fact in facts
        )
        self._set_match(
            AdmissionFactDimension.APPROVAL,
            matches,
            correspondence,
            diagnostics,
            "approval.correspondence",
        )
        is_fresh = all(fact.valid_from <= evaluated_at <= fact.valid_until for fact in facts)
        freshness[AdmissionFactDimension.APPROVAL] = (
            FactFreshness.FRESH if is_fresh else FactFreshness.STALE
        )
        if not is_fresh:
            diagnostics.append(
                AdmissionFactDiagnostic(AdmissionFactDimension.APPROVAL, "approval.stale")
            )

    def _capabilities(
        self,
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        correspondence: dict[AdmissionFactDimension, FactCorrespondence],
        diagnostics: list[AdmissionFactDiagnostic],
    ) -> None:
        facts = set(snapshot.capability_facts)
        if not facts:
            return
        fact_names = {fact.declaration.name for fact in facts}
        requested = {item.name for item in request.requested_capabilities}
        declared = {item.name for item in request.declared_capabilities}
        conflicting = len(fact_names) != len(facts)
        matches = (
            not conflicting
            and requested <= fact_names
            and fact_names <= declared
            and all(
                fact.subject == request.subject
                and fact.actor_ref == request.actor_ref
                and fact.purpose == request.purpose
                and fact.plan_intent_ref == request.execution_profile
                and fact.supported is True
                for fact in facts
            )
        )
        self._set_match(
            AdmissionFactDimension.CAPABILITIES,
            matches,
            correspondence,
            diagnostics,
            "capabilities.correspondence",
        )

    def _resources(
        self,
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        correspondence: dict[AdmissionFactDimension, FactCorrespondence],
        diagnostics: list[AdmissionFactDiagnostic],
    ) -> None:
        facts = set(snapshot.resource_facts)
        if not facts:
            return
        by_resource = {fact.limit.resource: fact for fact in facts}
        matches = len(by_resource) == len(facts) and all(
            requested.resource in by_resource
            and by_resource[requested.resource].subject == request.subject
            and by_resource[requested.resource].limit.unit == requested.unit
            and by_resource[requested.resource].limit.maximum >= requested.amount
            for requested in request.requested_resources
        )
        self._set_match(
            AdmissionFactDimension.RESOURCES,
            matches,
            correspondence,
            diagnostics,
            "resources.correspondence",
        )

    def _isolation(
        self,
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        correspondence: dict[AdmissionFactDimension, FactCorrespondence],
        diagnostics: list[AdmissionFactDiagnostic],
    ) -> None:
        facts = set(snapshot.isolation_facts)
        if not facts:
            return
        matches = len(facts) == 1 and all(
            fact.profile_id == request.isolation_profile_id
            and fact.policy_version == request.isolation_policy_version
            and fact.supported is True
            for fact in facts
        )
        self._set_match(
            AdmissionFactDimension.ISOLATION,
            matches,
            correspondence,
            diagnostics,
            "isolation.correspondence",
        )

    def _evidence(
        self,
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        correspondence: dict[AdmissionFactDimension, FactCorrespondence],
        diagnostics: list[AdmissionFactDiagnostic],
    ) -> None:
        facts = set(snapshot.evidence_facts)
        if not facts:
            return
        matches = all(
            fact.subject == request.subject and (not fact.required or fact.available is True)
            for fact in facts
        )
        self._set_match(
            AdmissionFactDimension.EVIDENCE,
            matches,
            correspondence,
            diagnostics,
            "evidence.correspondence",
        )

    @staticmethod
    def _outcome(dimensions: tuple[DimensionAssessment, ...]) -> AdmissionFactsOutcome:
        if any(item.correspondence is FactCorrespondence.MISMATCH for item in dimensions):
            return AdmissionFactsOutcome.MISMATCH
        if any(item.freshness is FactFreshness.STALE for item in dimensions):
            return AdmissionFactsOutcome.STALE
        if any(item.completeness is FactCompleteness.INCOMPLETE for item in dimensions):
            return AdmissionFactsOutcome.INCOMPLETE
        if any(
            item.completeness in {FactCompleteness.ABSENT, FactCompleteness.UNKNOWN}
            or item.correspondence is FactCorrespondence.UNKNOWN
            or item.freshness is FactFreshness.UNKNOWN
            for item in dimensions
        ):
            return AdmissionFactsOutcome.UNAVAILABLE
        return AdmissionFactsOutcome.SATISFIED
