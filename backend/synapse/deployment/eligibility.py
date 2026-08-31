"""Pure provider-neutral artifact eligibility assessment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import content_fingerprint
from .errors import InvalidDeploymentAttemptBinding
from .identities import (
    ArtifactFingerprintReference,
    CapabilityReference,
    CorrelationReference,
    CustodyReference,
    DeploymentFingerprint,
    EvidenceReference,
    OccurrenceReference,
    PolicyReference,
    ProvenanceReference,
)
from .models import (
    DeploymentArtifactRefV1,
    DeploymentAttemptV1,
    DeploymentEnvironmentV1,
    DeploymentReleaseV1,
    DeploymentTargetV1,
    DesiredRevisionV1,
)
from .ports import (
    ArtifactAvailability,
    ArtifactFingerprintCorrespondence,
    DeploymentArtifactFactsResultV1,
    ProvenanceAvailability,
)


class ArtifactEligibilityOutcome(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    PROVENANCE_MISSING = "provenance-missing"
    CUSTODY_UNAVAILABLE = "custody-unavailable"
    INDETERMINATE = "indeterminate"


class ArtifactEligibilityReason(StrEnum):
    FACTS_UNAVAILABLE = "facts-unavailable"
    CURRENT_AVAILABILITY_UNKNOWN = "current-availability-unknown"
    FINGERPRINT_MISMATCH = "fingerprint-mismatch"
    FINGERPRINT_UNKNOWN = "fingerprint-unknown"
    PROVENANCE_UNAVAILABLE = "provenance-unavailable"
    PROVENANCE_INVALID = "provenance-invalid"
    PROVENANCE_STALE = "provenance-stale"
    CUSTODY_REFERENCE_UNAVAILABLE = "custody-reference-unavailable"
    EVALUATOR_UNAVAILABLE = "evaluator-unavailable"
    EVAL_EVIDENCE_MISSING = "eval-evidence-missing"
    POLICY_UNSUPPORTED = "policy-unsupported"
    REQUIRED_EVIDENCE_MISSING = "required-evidence-missing"


class EvidenceValidity(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ArtifactProvenanceEvidenceV1:
    evidence_reference: EvidenceReference
    provenance_reference: ProvenanceReference
    release_id: str
    attempt_id: str
    artifact_reference: str
    artifact_fingerprint: ArtifactFingerprintReference
    producer_reference: CapabilityReference
    policy_reference: PolicyReference
    policy_version: str
    validity: EvidenceValidity


@dataclass(frozen=True, slots=True)
class ArtifactEvalEvidenceV1:
    evidence_reference: EvidenceReference
    artifact_reference: str
    artifact_fingerprint: ArtifactFingerprintReference
    policy_reference: PolicyReference
    validity: EvidenceValidity
    passed: bool | None


@dataclass(frozen=True, slots=True)
class ArtifactEligibilityPolicyV1:
    policy_reference: PolicyReference
    policy_version: str
    require_current_availability: bool = True
    require_custody: bool = True
    require_valid_provenance: bool = True
    require_eval_evidence: bool = False
    supported: bool = True
    required_evidence: tuple[EvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        if not self.policy_version or len(set(self.required_evidence)) != len(
            self.required_evidence
        ):
            raise InvalidDeploymentAttemptBinding("eligibility policy binding is invalid")


@dataclass(frozen=True, slots=True)
class ArtifactEligibilityRequestV1:
    release: DeploymentReleaseV1
    attempt: DeploymentAttemptV1
    environment: DeploymentEnvironmentV1
    target: DeploymentTargetV1
    artifact: DeploymentArtifactRefV1
    desired_revision: DesiredRevisionV1
    policy: ArtifactEligibilityPolicyV1
    facts: DeploymentArtifactFactsResultV1
    provenance: ArtifactProvenanceEvidenceV1 | None
    eval_evidence: ArtifactEvalEvidenceV1 | None
    additional_evidence: tuple[EvidenceReference, ...]
    semantic_fingerprint: DeploymentFingerprint
    correlation: CorrelationReference
    occurrence: OccurrenceReference

    def __post_init__(self) -> None:
        if (
            self.release.release_id != self.attempt.release_id
            or self.release.target_id != self.target.target_id
            or self.attempt.target_id != self.target.target_id
            or self.target.environment_id != self.environment.environment_id
            or self.release.artifact != self.artifact
            or self.attempt.artifact != self.artifact
            or self.release.desired_revision != self.desired_revision
            or self.attempt.desired_revision != self.desired_revision
            or self.policy.policy_reference != self.release.policy_reference
            or self.policy.policy_reference != self.attempt.policy_reference
        ):
            raise InvalidDeploymentAttemptBinding("artifact eligibility subject mismatch")
        if len(set(self.additional_evidence)) != len(self.additional_evidence):
            raise InvalidDeploymentAttemptBinding("eligibility evidence must be unique")
        _validate_provenance_binding(self)
        _validate_eval_binding(self)


@dataclass(frozen=True, slots=True)
class ArtifactEligibilityResultV1:
    outcome: ArtifactEligibilityOutcome
    reasons: tuple[ArtifactEligibilityReason, ...]
    release_id: str
    attempt_id: str
    artifact_reference: str
    expected_fingerprint: ArtifactFingerprintReference
    observed_fingerprint: ArtifactFingerprintReference | None
    custody_reference: CustodyReference | None
    provenance_evidence_reference: EvidenceReference | None
    eval_evidence_reference: EvidenceReference | None
    policy_reference: PolicyReference
    semantic_fingerprint: DeploymentFingerprint
    assessment_fingerprint: DeploymentFingerprint

    @property
    def authorized(self) -> bool:
        return False


def assess_artifact_eligibility(
    request: ArtifactEligibilityRequestV1,
) -> ArtifactEligibilityResultV1:
    outcome, reasons = _decision(request)
    semantic = (
        outcome,
        reasons,
        request.release.release_id,
        request.attempt.attempt_id,
        request.target.target_id,
        request.environment.environment_id,
        request.artifact,
        request.desired_revision,
        request.policy,
        request.facts,
        request.provenance,
        request.eval_evidence,
        tuple(sorted(request.additional_evidence)),
        request.semantic_fingerprint,
    )
    return ArtifactEligibilityResultV1(
        outcome,
        reasons,
        request.release.release_id.value,
        request.attempt.attempt_id.value,
        request.artifact.artifact.value,
        request.artifact.fingerprint,
        request.facts.observed_fingerprint,
        request.facts.custody_reference,
        request.provenance.evidence_reference if request.provenance else None,
        request.eval_evidence.evidence_reference if request.eval_evidence else None,
        request.policy.policy_reference,
        request.semantic_fingerprint,
        DeploymentFingerprint(content_fingerprint(semantic)),
    )


def replay_artifact_eligibility(
    result: ArtifactEligibilityResultV1,
) -> ArtifactEligibilityResultV1:
    """Return the historical fact without consulting any authority."""
    return result


def _validate_provenance_binding(request: ArtifactEligibilityRequestV1) -> None:
    evidence = request.provenance
    if evidence is None:
        return
    if (
        evidence.provenance_reference != request.artifact.provenance
        or evidence.release_id != request.release.release_id.value
        or evidence.attempt_id != request.attempt.attempt_id.value
        or evidence.artifact_reference != request.artifact.artifact.value
        or evidence.artifact_fingerprint != request.artifact.fingerprint
        or evidence.policy_reference != request.policy.policy_reference
        or evidence.policy_version != request.policy.policy_version
    ):
        raise InvalidDeploymentAttemptBinding("provenance evidence correspondence mismatch")


def _validate_eval_binding(request: ArtifactEligibilityRequestV1) -> None:
    evidence = request.eval_evidence
    if evidence is not None and (
        evidence.artifact_reference != request.artifact.artifact.value
        or evidence.artifact_fingerprint != request.artifact.fingerprint
        or evidence.policy_reference != request.policy.policy_reference
    ):
        raise InvalidDeploymentAttemptBinding("eval evidence correspondence mismatch")


def _decision(
    request: ArtifactEligibilityRequestV1,
) -> tuple[ArtifactEligibilityOutcome, tuple[ArtifactEligibilityReason, ...]]:
    facts = request.facts
    policy = request.policy
    if not policy.supported:
        return ArtifactEligibilityOutcome.INDETERMINATE, (
            ArtifactEligibilityReason.POLICY_UNSUPPORTED,
        )
    if facts.availability is ArtifactAvailability.UNAVAILABLE:
        return ArtifactEligibilityOutcome.UNAVAILABLE, (
            ArtifactEligibilityReason.FACTS_UNAVAILABLE,
        )
    if policy.require_current_availability and facts.availability is ArtifactAvailability.UNKNOWN:
        return ArtifactEligibilityOutcome.INDETERMINATE, (
            ArtifactEligibilityReason.CURRENT_AVAILABILITY_UNKNOWN,
        )
    if facts.fingerprint_correspondence is ArtifactFingerprintCorrespondence.MISMATCH:
        return ArtifactEligibilityOutcome.STALE, (ArtifactEligibilityReason.FINGERPRINT_MISMATCH,)
    if facts.fingerprint_correspondence is ArtifactFingerprintCorrespondence.UNKNOWN:
        return ArtifactEligibilityOutcome.INDETERMINATE, (
            ArtifactEligibilityReason.FINGERPRINT_UNKNOWN,
        )
    if policy.require_custody and facts.custody_reference is None:
        return ArtifactEligibilityOutcome.CUSTODY_UNAVAILABLE, (
            ArtifactEligibilityReason.CUSTODY_REFERENCE_UNAVAILABLE,
        )
    if (
        facts.provenance_availability is not ProvenanceAvailability.AVAILABLE
        or request.provenance is None
    ):
        return ArtifactEligibilityOutcome.PROVENANCE_MISSING, (
            ArtifactEligibilityReason.PROVENANCE_UNAVAILABLE,
        )
    if policy.require_valid_provenance and request.provenance.validity is EvidenceValidity.STALE:
        return ArtifactEligibilityOutcome.STALE, (ArtifactEligibilityReason.PROVENANCE_STALE,)
    if policy.require_valid_provenance and request.provenance.validity is EvidenceValidity.INVALID:
        return ArtifactEligibilityOutcome.INELIGIBLE, (
            ArtifactEligibilityReason.PROVENANCE_INVALID,
        )
    if (
        policy.require_valid_provenance
        and request.provenance.validity is not EvidenceValidity.VALID
    ):
        return ArtifactEligibilityOutcome.INDETERMINATE, (
            ArtifactEligibilityReason.PROVENANCE_UNAVAILABLE,
        )
    if policy.require_eval_evidence:
        if request.eval_evidence is None:
            return ArtifactEligibilityOutcome.INDETERMINATE, (
                ArtifactEligibilityReason.EVAL_EVIDENCE_MISSING,
            )
        if request.eval_evidence.validity is not EvidenceValidity.VALID:
            return ArtifactEligibilityOutcome.INDETERMINATE, (
                ArtifactEligibilityReason.EVALUATOR_UNAVAILABLE,
            )
        if request.eval_evidence.passed is not True:
            return ArtifactEligibilityOutcome.INELIGIBLE, (
                ArtifactEligibilityReason.EVAL_EVIDENCE_MISSING,
            )
    available = set(request.additional_evidence)
    if not set(policy.required_evidence).issubset(available):
        return ArtifactEligibilityOutcome.INDETERMINATE, (
            ArtifactEligibilityReason.REQUIRED_EVIDENCE_MISSING,
        )
    return ArtifactEligibilityOutcome.ELIGIBLE, ()
