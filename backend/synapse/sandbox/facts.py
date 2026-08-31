"""Neutral, immutable external facts used by Sandbox admission assessment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .errors import InvalidAdmissionFacts
from .identities import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxIsolationProfileId,
    SandboxPolicyVersion,
)
from .models import CapabilityDeclaration, ResourceLimit

SNAPSHOT_FORMAT_VERSION = "sandbox-admission-facts-v1"
_CAPABILITY_CONSTRAINT = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")


def _aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidAdmissionFacts(f"{field} must be timezone-aware")


def _window(valid_from: datetime, valid_until: datetime) -> None:
    _aware(valid_from, "valid_from")
    _aware(valid_until, "valid_until")
    if valid_until < valid_from:
        raise InvalidAdmissionFacts("validity window is inverted")


class AdmissionFactDimension(StrEnum):
    HANDOFF = "handoff"
    ARTIFACT = "artifact"
    POLICY = "policy"
    APPROVAL = "approval"
    CAPABILITIES = "capabilities"
    RESOURCES = "resources"
    ISOLATION = "isolation"
    EVIDENCE = "evidence"


class FactCompleteness(StrEnum):
    ABSENT = "absent"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not_required"
    COMPLETE = "complete"


class HandoffReadiness(StrEnum):
    UNKNOWN = "unknown"
    NOT_READY = "not_ready"
    READY = "ready"


class ArtifactAvailability(StrEnum):
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"


class SandboxCapabilityScopeKind(StrEnum):
    EXACT = "exact"
    WILDCARD = "wildcard"


@dataclass(frozen=True, slots=True)
class SandboxCapabilityScope:
    kind: SandboxCapabilityScopeKind
    reference: OpaqueReference | None

    def __post_init__(self) -> None:
        if self.kind is SandboxCapabilityScopeKind.EXACT and self.reference is None:
            raise InvalidAdmissionFacts("exact capability scope requires a reference")
        if self.kind is SandboxCapabilityScopeKind.WILDCARD and self.reference is not None:
            raise InvalidAdmissionFacts("wildcard capability scope cannot carry a reference")


@dataclass(frozen=True, slots=True)
class SandboxCapabilityConstraint:
    name: str
    maximum: int

    def __post_init__(self) -> None:
        if not _CAPABILITY_CONSTRAINT.fullmatch(self.name):
            raise InvalidAdmissionFacts("capability constraint name is invalid")
        if not isinstance(self.maximum, int) or isinstance(self.maximum, bool) or self.maximum <= 0:
            raise InvalidAdmissionFacts("capability constraint maximum must be positive")


@dataclass(frozen=True, slots=True)
class DimensionCompleteness:
    dimension: AdmissionFactDimension
    status: FactCompleteness


@dataclass(frozen=True, slots=True)
class SandboxHandoffFact:
    subject: OpaqueReference
    handoff_fingerprint: SandboxArtifactFingerprint
    artifact_fingerprint: SandboxArtifactFingerprint
    actor_ref: OpaqueReference
    purpose: str
    plan_intent_ref: OpaqueReference
    readiness: HandoffReadiness


@dataclass(frozen=True, slots=True)
class SandboxArtifactFact:
    subject: OpaqueReference
    artifact_ref: OpaqueReference
    fingerprint: SandboxArtifactFingerprint
    availability: ArtifactAvailability


@dataclass(frozen=True, slots=True)
class SandboxPolicyFact:
    policy_ref: OpaqueReference
    subject: OpaqueReference
    version: SandboxPolicyVersion
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        _window(self.valid_from, self.valid_until)


@dataclass(frozen=True, slots=True)
class SandboxApprovalFact:
    approval_ref: OpaqueReference
    subject: OpaqueReference
    actor_ref: OpaqueReference
    purpose: str
    plan_intent_ref: OpaqueReference
    scope: tuple[OpaqueReference, ...]
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        _window(self.valid_from, self.valid_until)


@dataclass(frozen=True, slots=True)
class SandboxCapabilityFact:
    subject: OpaqueReference
    actor_ref: OpaqueReference
    purpose: str
    plan_intent_ref: OpaqueReference
    declaration: CapabilityDeclaration
    external_grant_ref: OpaqueReference | None
    supported: bool | None
    scopes: tuple[SandboxCapabilityScope, ...]
    constraints: tuple[SandboxCapabilityConstraint, ...]
    isolation_profiles: tuple[SandboxIsolationProfileId, ...]
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        _window(self.valid_from, self.valid_until)
        if len(set(self.scopes)) != len(self.scopes):
            raise InvalidAdmissionFacts("capability scopes must be unique")
        if len({item.name for item in self.constraints}) != len(self.constraints):
            raise InvalidAdmissionFacts("capability constraints must be unique")
        if len(set(self.isolation_profiles)) != len(self.isolation_profiles):
            raise InvalidAdmissionFacts("capability isolation profiles must be unique")


@dataclass(frozen=True, slots=True)
class SandboxResourceGrantFact:
    subject: OpaqueReference
    external_grant_ref: OpaqueReference
    limit: ResourceLimit


@dataclass(frozen=True, slots=True)
class SandboxIsolationSupportFact:
    profile_id: SandboxIsolationProfileId
    policy_version: SandboxPolicyVersion
    support_ref: OpaqueReference
    supported: bool | None


@dataclass(frozen=True, slots=True)
class SandboxEvidenceRequirementFact:
    evidence_ref: OpaqueReference
    subject: OpaqueReference
    required: bool
    available: bool | None


@dataclass(frozen=True, slots=True)
class SandboxAdmissionFactsSnapshot:
    format_version: str
    observed_at: datetime
    handoff_facts: tuple[SandboxHandoffFact, ...]
    artifact_facts: tuple[SandboxArtifactFact, ...]
    policy_facts: tuple[SandboxPolicyFact, ...]
    approval_facts: tuple[SandboxApprovalFact, ...]
    capability_facts: tuple[SandboxCapabilityFact, ...]
    resource_facts: tuple[SandboxResourceGrantFact, ...]
    isolation_facts: tuple[SandboxIsolationSupportFact, ...]
    evidence_facts: tuple[SandboxEvidenceRequirementFact, ...]
    completeness: tuple[DimensionCompleteness, ...]
    snapshot_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.format_version,
            self.observed_at,
            self.handoff_facts,
            self.artifact_facts,
            self.policy_facts,
            self.approval_facts,
            self.capability_facts,
            self.resource_facts,
            self.isolation_facts,
            self.evidence_facts,
            self.completeness,
        )

    def __post_init__(self) -> None:
        if self.format_version != SNAPSHOT_FORMAT_VERSION:
            raise InvalidAdmissionFacts("unsupported admission facts snapshot format")
        _aware(self.observed_at, "observed_at")
        statuses = [item.dimension for item in self.completeness]
        if len(statuses) != len(set(statuses)) or set(statuses) != set(AdmissionFactDimension):
            raise InvalidAdmissionFacts("completeness must cover every dimension exactly once")
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.snapshot_fingerprint:
            raise InvalidAdmissionFacts("snapshot fingerprint does not match canonical content")

    @classmethod
    def create(
        cls,
        *,
        observed_at: datetime,
        handoff_facts: tuple[SandboxHandoffFact, ...] = (),
        artifact_facts: tuple[SandboxArtifactFact, ...] = (),
        policy_facts: tuple[SandboxPolicyFact, ...] = (),
        approval_facts: tuple[SandboxApprovalFact, ...] = (),
        capability_facts: tuple[SandboxCapabilityFact, ...] = (),
        resource_facts: tuple[SandboxResourceGrantFact, ...] = (),
        isolation_facts: tuple[SandboxIsolationSupportFact, ...] = (),
        evidence_facts: tuple[SandboxEvidenceRequirementFact, ...] = (),
        completeness: tuple[DimensionCompleteness, ...],
    ) -> SandboxAdmissionFactsSnapshot:
        _aware(observed_at, "observed_at")
        ordered_handoff = tuple(sorted(handoff_facts, key=repr))
        ordered_artifact = tuple(sorted(artifact_facts, key=repr))
        ordered_policy = tuple(sorted(policy_facts, key=repr))
        ordered_approval = tuple(sorted(approval_facts, key=repr))
        ordered_capability = tuple(sorted(capability_facts, key=repr))
        ordered_resource = tuple(sorted(resource_facts, key=repr))
        ordered_isolation = tuple(sorted(isolation_facts, key=repr))
        ordered_evidence = tuple(sorted(evidence_facts, key=repr))
        ordered_completeness = tuple(sorted(completeness, key=lambda item: item.dimension.value))
        content: tuple[object, ...] = (
            SNAPSHOT_FORMAT_VERSION,
            observed_at,
            ordered_handoff,
            ordered_artifact,
            ordered_policy,
            ordered_approval,
            ordered_capability,
            ordered_resource,
            ordered_isolation,
            ordered_evidence,
            ordered_completeness,
        )
        return cls(
            format_version=SNAPSHOT_FORMAT_VERSION,
            observed_at=observed_at,
            handoff_facts=ordered_handoff,
            artifact_facts=ordered_artifact,
            policy_facts=ordered_policy,
            approval_facts=ordered_approval,
            capability_facts=ordered_capability,
            resource_facts=ordered_resource,
            isolation_facts=ordered_isolation,
            evidence_facts=ordered_evidence,
            completeness=ordered_completeness,
            snapshot_fingerprint=SandboxArtifactFingerprint.from_content(content),
        )
