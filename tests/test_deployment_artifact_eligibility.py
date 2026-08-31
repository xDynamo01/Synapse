from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from synapse.deployment import (
    AdapterBindingReference,
    ArtifactAvailability,
    ArtifactEligibilityOutcome,
    ArtifactEligibilityPolicyV1,
    ArtifactEligibilityReason,
    ArtifactEligibilityRequestV1,
    ArtifactEvalEvidenceV1,
    ArtifactFingerprintCorrespondence,
    ArtifactFingerprintReference,
    ArtifactMediaClass,
    ArtifactProvenanceEvidenceV1,
    ArtifactReference,
    CapabilityReference,
    CorrelationReference,
    CustodyReference,
    DeploymentArtifactFactsRequestV1,
    DeploymentArtifactFactsResultV1,
    DeploymentArtifactRefV1,
    DeploymentAttemptId,
    DeploymentAttemptV1,
    DeploymentEnvironmentV1,
    DeploymentFingerprint,
    DeploymentIntentId,
    DeploymentReleaseV1,
    DeploymentTargetClass,
    DeploymentTargetId,
    DeploymentTargetV1,
    DesiredRevisionV1,
    EnvironmentClassification,
    EnvironmentId,
    EvidenceReference,
    EvidenceValidity,
    InvalidDeploymentAttemptBinding,
    OccurrenceReference,
    PolicyReference,
    ProvenanceAvailability,
    ProvenanceReference,
    ReleaseId,
    RequesterReference,
    RevisionId,
    assess_artifact_eligibility,
    replay_artifact_eligibility,
)
from synapse.deployment_integrations import DeploymentCustodyFactsAdapter
from synapse.sandbox import (
    SandboxArtifactFingerprint,
    SandboxArtifactInspectionResult,
    SandboxMaterializationStepOutcome,
)


def _request() -> ArtifactEligibilityRequestV1:
    policy_ref = PolicyReference("policy:eligibility-v1")
    fingerprint = ArtifactFingerprintReference("sha256:" + "7" * 64)
    artifact = DeploymentArtifactRefV1(
        ArtifactReference("artifact:release-007"), fingerprint,
        ProvenanceReference("provenance:build-007"),
        ArtifactMediaClass.APPLICATION_BUNDLE, CustodyReference("custody:release-007"),
        "application/zip",
    )
    revision = DesiredRevisionV1(RevisionId("deployment-revision:007"), fingerprint)
    environment = DeploymentEnvironmentV1(
        EnvironmentId("deployment-environment:staging"), "Staging",
        EnvironmentClassification.STAGING, policy_ref,
    )
    target = DeploymentTargetV1(
        DeploymentTargetId("deployment-target:api"), environment.environment_id,
        AdapterBindingReference("adapter-binding:abstract"), DeploymentTargetClass.SERVICE,
    )
    release = DeploymentReleaseV1(
        ReleaseId("deployment-release:007"), DeploymentIntentId("deployment-intent:007"),
        DeploymentFingerprint("sha256:" + "1" * 64), artifact, target.target_id,
        revision, policy_ref,
    )
    attempt = DeploymentAttemptV1(
        DeploymentAttemptId("deployment-attempt:007"), release.release_id,
        target.target_id, revision, artifact, 1, policy_ref,
        DeploymentFingerprint("sha256:" + "2" * 64), OccurrenceReference("occurrence:attempt"),
        CorrelationReference("correlation:attempt"),
    )
    facts = DeploymentArtifactFactsResultV1(
        ArtifactAvailability.AVAILABLE, ArtifactFingerprintCorrespondence.MATCH,
        ProvenanceAvailability.AVAILABLE, fingerprint, CustodyReference("custody:release-007"),
    )
    provenance = ArtifactProvenanceEvidenceV1(
        EvidenceReference("evidence:provenance-007"), artifact.provenance,
        release.release_id.value, attempt.attempt_id.value, artifact.artifact.value,
        fingerprint, CapabilityReference("producer:builder"), policy_ref, "v1",
        EvidenceValidity.VALID,
    )
    return ArtifactEligibilityRequestV1(
        release, attempt, environment, target, artifact, revision,
        ArtifactEligibilityPolicyV1(policy_ref, "v1"), facts, provenance, None, (),
        attempt.semantic_fingerprint, CorrelationReference("correlation:eligibility"),
        OccurrenceReference("occurrence:eligibility"),
    )


def test_available_matching_valid_provenance_is_eligible_and_not_authorized() -> None:
    result = assess_artifact_eligibility(_request())
    assert result.outcome is ArtifactEligibilityOutcome.ELIGIBLE
    assert result.reasons == ()
    assert not result.authorized
    assert not hasattr(result, "authorization_reference")


@pytest.mark.parametrize(
    ("facts", "outcome", "reason"),
    [
        (
            DeploymentArtifactFactsResultV1(
                ArtifactAvailability.UNAVAILABLE,
                ArtifactFingerprintCorrespondence.UNKNOWN,
                ProvenanceAvailability.UNKNOWN,
            ),
            ArtifactEligibilityOutcome.UNAVAILABLE,
            ArtifactEligibilityReason.FACTS_UNAVAILABLE,
        ),
        (
            DeploymentArtifactFactsResultV1(
                ArtifactAvailability.UNKNOWN,
                ArtifactFingerprintCorrespondence.MATCH,
                ProvenanceAvailability.AVAILABLE,
                custody_reference=CustodyReference("custody:historical"),
            ),
            ArtifactEligibilityOutcome.INDETERMINATE,
            ArtifactEligibilityReason.CURRENT_AVAILABILITY_UNKNOWN,
        ),
        (
            DeploymentArtifactFactsResultV1(
                ArtifactAvailability.AVAILABLE,
                ArtifactFingerprintCorrespondence.MISMATCH,
                ProvenanceAvailability.AVAILABLE,
                ArtifactFingerprintReference("sha256:" + "8" * 64),
                CustodyReference("custody:release-007"),
            ),
            ArtifactEligibilityOutcome.STALE,
            ArtifactEligibilityReason.FINGERPRINT_MISMATCH,
        ),
        (
            DeploymentArtifactFactsResultV1(
                ArtifactAvailability.AVAILABLE,
                ArtifactFingerprintCorrespondence.MATCH,
                ProvenanceAvailability.AVAILABLE,
            ),
            ArtifactEligibilityOutcome.CUSTODY_UNAVAILABLE,
            ArtifactEligibilityReason.CUSTODY_REFERENCE_UNAVAILABLE,
        ),
    ],
)
def test_factual_availability_and_correspondence_outcomes(
    facts: DeploymentArtifactFactsResultV1,
    outcome: ArtifactEligibilityOutcome,
    reason: ArtifactEligibilityReason,
) -> None:
    result = assess_artifact_eligibility(replace(_request(), facts=facts))
    assert result.outcome is outcome
    assert result.reasons == (reason,)


def test_missing_invalid_stale_and_unknown_provenance_remain_distinct() -> None:
    request = _request()
    assert request.provenance is not None
    missing = assess_artifact_eligibility(replace(request, provenance=None))
    assert missing.outcome is ArtifactEligibilityOutcome.PROVENANCE_MISSING
    invalid = assess_artifact_eligibility(
        replace(request, provenance=replace(request.provenance, validity=EvidenceValidity.INVALID))
    )
    stale = assess_artifact_eligibility(
        replace(request, provenance=replace(request.provenance, validity=EvidenceValidity.STALE))
    )
    unknown = assess_artifact_eligibility(
        replace(request, provenance=replace(request.provenance, validity=EvidenceValidity.UNKNOWN))
    )
    assert invalid.outcome is ArtifactEligibilityOutcome.INELIGIBLE
    assert stale.outcome is ArtifactEligibilityOutcome.STALE
    assert unknown.outcome is ArtifactEligibilityOutcome.INDETERMINATE


def test_eval_pass_is_only_evidence_and_never_authorization_or_availability() -> None:
    request = _request()
    eval_evidence = ArtifactEvalEvidenceV1(
        EvidenceReference("evidence:eval-007"), request.artifact.artifact.value,
        request.artifact.fingerprint, request.policy.policy_reference,
        EvidenceValidity.VALID, True,
    )
    result = assess_artifact_eligibility(
        replace(
            request,
            policy=replace(request.policy, require_eval_evidence=True),
            eval_evidence=eval_evidence,
        )
    )
    assert result.outcome is ArtifactEligibilityOutcome.ELIGIBLE
    assert not result.authorized
    assert result.observed_fingerprint == request.facts.observed_fingerprint


def test_evaluator_unavailable_and_required_policy_evidence_are_indeterminate() -> None:
    request = _request()
    unavailable = ArtifactEvalEvidenceV1(
        EvidenceReference("evidence:eval-unavailable"), request.artifact.artifact.value,
        request.artifact.fingerprint, request.policy.policy_reference,
        EvidenceValidity.UNAVAILABLE, None,
    )
    result = assess_artifact_eligibility(
        replace(request, policy=replace(request.policy, require_eval_evidence=True), eval_evidence=unavailable)
    )
    assert result.reasons == (ArtifactEligibilityReason.EVALUATOR_UNAVAILABLE,)
    required = EvidenceReference("evidence:governance-required")
    missing = assess_artifact_eligibility(
        replace(request, policy=replace(request.policy, required_evidence=(required,)))
    )
    assert missing.reasons == (ArtifactEligibilityReason.REQUIRED_EVIDENCE_MISSING,)


@pytest.mark.parametrize("field", ["release", "attempt", "target", "environment", "artifact", "desired_revision"])
def test_wrong_subject_binding_is_rejected(field: str) -> None:
    request = _request()
    with pytest.raises(InvalidDeploymentAttemptBinding):
        if field == "release":
            replace(request, release=replace(request.release, release_id=ReleaseId("deployment-release:other")))
        elif field == "attempt":
            replace(request, attempt=replace(request.attempt, attempt_id=DeploymentAttemptId("deployment-attempt:other"), release_id=ReleaseId("deployment-release:other")))
        elif field == "target":
            replace(request, target=replace(request.target, target_id=DeploymentTargetId("deployment-target:other")))
        elif field == "environment":
            replace(request, environment=replace(request.environment, environment_id=EnvironmentId("deployment-environment:other")))
        elif field == "artifact":
            replace(request, artifact=replace(request.artifact, artifact=ArtifactReference("artifact:other")))
        else:
            replace(request, desired_revision=replace(request.desired_revision, revision_id=RevisionId("deployment-revision:other")))


def test_provenance_cross_attempt_and_policy_reuse_is_rejected() -> None:
    request = _request()
    assert request.provenance is not None
    with pytest.raises(InvalidDeploymentAttemptBinding):
        replace(request, provenance=replace(request.provenance, attempt_id="deployment-attempt:other"))
    with pytest.raises(InvalidDeploymentAttemptBinding):
        replace(request, provenance=replace(request.provenance, policy_version="v2"))


def test_assessment_is_deterministic_immutable_and_occurrence_independent() -> None:
    request = _request()
    first = assess_artifact_eligibility(request)
    changed_context = replace(
        request, correlation=CorrelationReference("correlation:other"),
        occurrence=OccurrenceReference("occurrence:other"),
    )
    assert assess_artifact_eligibility(changed_context).assessment_fingerprint == first.assessment_fingerprint
    with pytest.raises(FrozenInstanceError):
        setattr(first, "outcome", ArtifactEligibilityOutcome.INELIGIBLE)


def test_replay_returns_historical_fact_without_authority_access() -> None:
    result = assess_artifact_eligibility(_request())
    assert replay_artifact_eligibility(result) is result


class Custody:
    def __init__(self, result: SandboxArtifactInspectionResult) -> None:
        self.result = result
        self.calls = 0

    def inspect(self, request: object) -> SandboxArtifactInspectionResult:
        self.calls += 1
        return self.result


def test_custody_integration_maps_current_match_stale_and_unavailable_without_copy() -> None:
    request = _request()
    facts_request = DeploymentArtifactFactsRequestV1(
        request.release, request.attempt, request.artifact,
        RequesterReference("subject:operator"), CorrelationReference("correlation:facts"),
    )
    sandbox_fingerprint = SandboxArtifactFingerprint(request.artifact.fingerprint.value)
    matched = Custody(SandboxArtifactInspectionResult(SandboxMaterializationStepOutcome.SUCCEEDED, sandbox_fingerprint, False, ()))
    matching = DeploymentCustodyFactsAdapter(matched).artifact_facts(facts_request)
    assert matching.fingerprint_correspondence is ArtifactFingerprintCorrespondence.MATCH
    stale = Custody(SandboxArtifactInspectionResult(SandboxMaterializationStepOutcome.FAILED, SandboxArtifactFingerprint("sha256:" + "9" * 64), True, ("artifact_stale",)))
    stale_facts = DeploymentCustodyFactsAdapter(stale).artifact_facts(facts_request)
    assert stale_facts.fingerprint_correspondence is ArtifactFingerprintCorrespondence.MISMATCH
    unavailable = DeploymentCustodyFactsAdapter(None).artifact_facts(facts_request)
    assert unavailable.availability is ArtifactAvailability.UNAVAILABLE
    assert matched.calls == 1
    assert not hasattr(DeploymentCustodyFactsAdapter, "materialize")
    assert not hasattr(DeploymentCustodyFactsAdapter, "copy")


def test_artifact_change_after_assessment_makes_prior_result_historical_only() -> None:
    request = _request()
    prior = assess_artifact_eligibility(request)
    changed = replace(
        request,
        facts=replace(
            request.facts,
            fingerprint_correspondence=ArtifactFingerprintCorrespondence.MISMATCH,
            observed_fingerprint=ArtifactFingerprintReference("sha256:" + "0" * 64),
        ),
    )
    current = assess_artifact_eligibility(changed)
    assert prior.outcome is ArtifactEligibilityOutcome.ELIGIBLE
    assert current.outcome is ArtifactEligibilityOutcome.STALE
    assert prior.assessment_fingerprint != current.assessment_fingerprint
