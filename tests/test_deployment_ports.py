from dataclasses import FrozenInstanceError, replace

import pytest

from synapse.deployment import (
    AdapterBindingReference,
    ApplyReceiptReference,
    ArtifactAvailability,
    ArtifactFingerprintCorrespondence,
    ArtifactFingerprintReference,
    ArtifactMediaClass,
    ArtifactReference,
    AuthorizationReference,
    CapabilityReference,
    CorrelationReference,
    CustodyReference,
    DeploymentApplyOutcome,
    DeploymentApplyRequestV1,
    DeploymentApplyResultV1,
    DeploymentArtifactFactsRequestV1,
    DeploymentArtifactFactsResultV1,
    DeploymentArtifactRefV1,
    DeploymentAttemptId,
    DeploymentAttemptV1,
    DeploymentAuthorizationOutcome,
    DeploymentAuthorizationRequestV1,
    DeploymentAuthorizationResultV1,
    DeploymentEnvironmentV1,
    DeploymentFingerprint,
    DeploymentIdempotencyKey,
    DeploymentIntentId,
    DeploymentObservationOutcome,
    DeploymentObservationRequestV1,
    DeploymentObservationResultV1,
    DeploymentOperation,
    DeploymentPreparationOutcome,
    DeploymentPreparationRequestV1,
    DeploymentPreparationResultV1,
    DeploymentReleaseV1,
    DeploymentRollbackApplyRequestV1,
    DeploymentRollbackApplyResultV1,
    DeploymentRollbackAttemptV1,
    DeploymentRollbackObservationRequestV1,
    DeploymentRollbackObservationResultV1,
    DeploymentRollbackPreparationRequestV1,
    DeploymentRollbackPreparationResultV1,
    DeploymentRollbackVerificationRequestV1,
    DeploymentRollbackVerificationResultV1,
    DeploymentTargetClass,
    DeploymentTargetId,
    DeploymentTargetV1,
    DeploymentVerificationOutcome,
    DeploymentVerificationRequestV1,
    DeploymentVerificationResultV1,
    DesiredRevisionV1,
    EnvironmentClassification,
    EnvironmentId,
    EvidenceReference,
    FencingReference,
    InvalidDeploymentAttemptBinding,
    InvalidRollbackProgression,
    ObservationReference,
    ObservedRevisionV1,
    OccurrenceReference,
    PolicyReference,
    PreparationReference,
    ProvenanceAvailability,
    ProvenanceReference,
    ReleaseId,
    RequesterReference,
    RevisionId,
    RollbackApplyOutcome,
    RollbackAttemptId,
    RollbackObservationOutcome,
    RollbackPreparationOutcome,
    RollbackReceiptReference,
    RollbackVerificationOutcome,
    VerificationReference,
)


def _facts():
    environment = DeploymentEnvironmentV1(
        EnvironmentId("deployment-environment:ports"),
        "Ports",
        EnvironmentClassification.TEST,
        PolicyReference("policy:environment"),
    )
    target = DeploymentTargetV1(
        DeploymentTargetId("deployment-target:ports"),
        environment.environment_id,
        AdapterBindingReference("adapter-binding:ports"),
        DeploymentTargetClass.SERVICE,
    )
    artifact = DeploymentArtifactRefV1(
        ArtifactReference("artifact:ports"),
        ArtifactFingerprintReference("fingerprint:ports"),
        ProvenanceReference("provenance:ports"),
        ArtifactMediaClass.APPLICATION_BUNDLE,
        CustodyReference("custody:ports"),
    )
    revision = DesiredRevisionV1(
        RevisionId("deployment-revision:ports"), artifact.fingerprint
    )
    release = DeploymentReleaseV1(
        ReleaseId("deployment-release:ports"),
        DeploymentIntentId("deployment-intent:ports"),
        DeploymentFingerprint("sha256:" + "1" * 64),
        artifact,
        target.target_id,
        revision,
        PolicyReference("policy:deployment"),
    )
    attempt = DeploymentAttemptV1(
        DeploymentAttemptId("deployment-attempt:ports"),
        release.release_id,
        target.target_id,
        revision,
        artifact,
        1,
        release.policy_reference,
        DeploymentFingerprint("sha256:" + "2" * 64),
        OccurrenceReference("occurrence:ports"),
        CorrelationReference("correlation:ports"),
    )
    return environment, target, artifact, revision, release, attempt


def _rollback(target: DeploymentTargetV1) -> DeploymentRollbackAttemptV1:
    return DeploymentRollbackAttemptV1(
        RollbackAttemptId("deployment-rollback-attempt:ports"),
        ReleaseId("deployment-release:ports"),
        target.target_id,
        RevisionId("deployment-revision:failed"),
        RevisionId("deployment-revision:rollback"),
        AuthorizationReference("authorization:rollback"),
        OccurrenceReference("occurrence:rollback"),
    )


def test_artifact_facts_are_immutable_factual_and_not_eligibility() -> None:
    _, _, artifact, _, release, attempt = _facts()
    request = DeploymentArtifactFactsRequestV1(
        release,
        attempt,
        artifact,
        RequesterReference("subject:operator"),
        CorrelationReference("correlation:artifact-facts"),
    )
    result = DeploymentArtifactFactsResultV1(
        ArtifactAvailability.AVAILABLE,
        ArtifactFingerprintCorrespondence.MATCH,
        ProvenanceAvailability.AVAILABLE,
        artifact.fingerprint,
        artifact.custody,
        (CapabilityReference("limitation:local-only"),),
    )
    assert request.artifact == artifact
    assert not hasattr(result, "eligible")
    assert not hasattr(result, "deployable")
    with pytest.raises(FrozenInstanceError):
        setattr(result, "availability", ArtifactAvailability.UNAVAILABLE)


@pytest.mark.parametrize(
    "outcome",
    [
        DeploymentAuthorizationOutcome.DENIED,
        DeploymentAuthorizationOutcome.APPROVAL_REQUIRED,
        DeploymentAuthorizationOutcome.UNAVAILABLE,
        DeploymentAuthorizationOutcome.STALE,
        DeploymentAuthorizationOutcome.EXPIRED,
    ],
)
def test_authorization_outcomes_do_not_imply_grant(outcome) -> None:
    result = DeploymentAuthorizationResultV1(outcome)
    assert result.authorization_reference is None
    assert not hasattr(result, "authorized")


def test_authorization_allowed_requires_typed_reference_and_request_correspondence() -> None:
    environment, target, artifact, revision, release, attempt = _facts()
    request = DeploymentAuthorizationRequestV1(
        DeploymentOperation.APPLY,
        RequesterReference("subject:operator"),
        release,
        attempt,
        environment,
        target,
        artifact,
        revision,
        release.policy_reference,
        CorrelationReference("correlation:authorization"),
        None,
    )
    assert request.operation is DeploymentOperation.APPLY
    allowed = DeploymentAuthorizationResultV1(
        DeploymentAuthorizationOutcome.ALLOWED,
        AuthorizationReference("authorization:apply"),
        (EvidenceReference("evidence:approval"),),
    )
    assert isinstance(allowed.authorization_reference, AuthorizationReference)
    with pytest.raises(InvalidDeploymentAttemptBinding):
        DeploymentAuthorizationResultV1(DeploymentAuthorizationOutcome.ALLOWED)
    with pytest.raises(InvalidDeploymentAttemptBinding):
        replace(request, target=replace(target, target_id=DeploymentTargetId("deployment-target:other")))


def test_preparation_is_distinct_from_apply_and_prepared_requires_reference() -> None:
    _, target, artifact, revision, release, attempt = _facts()
    request = DeploymentPreparationRequestV1(
        release,
        attempt,
        target,
        artifact,
        revision,
        release.policy_reference,
        attempt.configuration_fingerprint,
    )
    prepared = DeploymentPreparationResultV1(
        DeploymentPreparationOutcome.PREPARED,
        PreparationReference("preparation:apply"),
    )
    assert not hasattr(prepared, "apply_receipt_reference")
    assert not hasattr(request, "authorization_reference")
    with pytest.raises(InvalidDeploymentAttemptBinding):
        DeploymentPreparationResultV1(DeploymentPreparationOutcome.PREPARED)


@pytest.mark.parametrize(
    "outcome",
    [
        DeploymentApplyOutcome.PARTIALLY_APPLIED,
        DeploymentApplyOutcome.FAILED,
        DeploymentApplyOutcome.OUTCOME_UNKNOWN,
    ],
)
def test_apply_partial_failed_and_unknown_are_distinct_without_fake_receipt(outcome) -> None:
    result = DeploymentApplyResultV1(outcome)
    assert result.apply_receipt_reference is None
    assert DeploymentApplyOutcome.OUTCOME_UNKNOWN is not DeploymentApplyOutcome.FAILED


def test_apply_request_requires_correspondence_idempotency_fingerprint_and_fencing_is_opaque() -> None:
    _, target, artifact, revision, release, attempt = _facts()
    request = DeploymentApplyRequestV1(
        release,
        attempt,
        target,
        artifact,
        revision,
        PreparationReference("preparation:apply"),
        AuthorizationReference("authorization:apply"),
        DeploymentIdempotencyKey("deployment-idempotency:apply"),
        attempt.semantic_fingerprint,
        FencingReference("fencing:generation-1"),
    )
    assert isinstance(request.idempotency_key, DeploymentIdempotencyKey)
    assert isinstance(request.fencing_reference, FencingReference)
    applied = DeploymentApplyResultV1(
        DeploymentApplyOutcome.APPLIED, ApplyReceiptReference("apply-receipt:ports")
    )
    assert not hasattr(applied, "verification_reference")
    with pytest.raises(InvalidDeploymentAttemptBinding):
        DeploymentApplyResultV1(DeploymentApplyOutcome.APPLIED)
    with pytest.raises(InvalidDeploymentAttemptBinding):
        replace(request, semantic_fingerprint=DeploymentFingerprint("sha256:" + "3" * 64))


def test_observation_is_factual_and_unavailable_is_not_verification_failure() -> None:
    _, target, _, revision, release, attempt = _facts()
    request = DeploymentObservationRequestV1(release, attempt, target, revision)
    observation_ref = ObservationReference("observation:ports")
    observed = DeploymentObservationResultV1(
        DeploymentObservationOutcome.OBSERVED,
        observation_ref,
        ObservedRevisionV1(revision.revision_id, observation_ref, revision.artifact_fingerprint),
    )
    unavailable = DeploymentObservationResultV1(DeploymentObservationOutcome.UNAVAILABLE)
    assert request.desired_revision == revision
    assert observed.observed_revision is not None
    assert not hasattr(observed, "verified")
    assert not hasattr(unavailable, "verification_outcome")


@pytest.mark.parametrize(
    "outcome",
    [
        DeploymentVerificationOutcome.FAILED,
        DeploymentVerificationOutcome.UNAVAILABLE,
        DeploymentVerificationOutcome.INDETERMINATE,
    ],
)
def test_verification_non_success_outcomes_are_distinct(outcome) -> None:
    result = DeploymentVerificationResultV1(outcome)
    assert result.verification_reference is None


def test_verification_consumes_observation_but_requires_its_own_reference() -> None:
    _, target, _, revision, release, attempt = _facts()
    observation_ref = ObservationReference("observation:verify")
    observation = DeploymentObservationResultV1(
        DeploymentObservationOutcome.OBSERVED,
        observation_ref,
        ObservedRevisionV1(revision.revision_id, observation_ref),
    )
    request = DeploymentVerificationRequestV1(
        release,
        attempt,
        target,
        revision,
        observation,
        PolicyReference("policy:verification"),
    )
    assert request.observation.observation_reference == observation_ref
    verified = DeploymentVerificationResultV1(
        DeploymentVerificationOutcome.VERIFIED,
        VerificationReference("verification:ports"),
    )
    assert isinstance(verified.verification_reference, VerificationReference)
    with pytest.raises(InvalidDeploymentAttemptBinding):
        DeploymentVerificationResultV1(DeploymentVerificationOutcome.VERIFIED)
    with pytest.raises(InvalidDeploymentAttemptBinding):
        DeploymentVerificationResultV1(
            DeploymentVerificationOutcome.VERIFIED,
            ObservationReference("observation:not-verification"),
        )
    with pytest.raises(InvalidDeploymentAttemptBinding):
        replace(request, observation=DeploymentObservationResultV1(DeploymentObservationOutcome.UNAVAILABLE))


def test_rollback_preparation_and_apply_preserve_exact_bindings() -> None:
    _, target, artifact, _, _, _ = _facts()
    rollback = _rollback(target)
    preparation = DeploymentRollbackPreparationRequestV1(
        rollback,
        target,
        artifact,
        rollback.authorization_reference,
        PolicyReference("policy:rollback"),
    )
    prepared = DeploymentRollbackPreparationResultV1(
        RollbackPreparationOutcome.PREPARED,
        PreparationReference("preparation:rollback"),
    )
    apply_request = DeploymentRollbackApplyRequestV1(
        rollback,
        target,
        artifact,
        prepared.preparation_reference,
        rollback.authorization_reference,
        DeploymentIdempotencyKey("deployment-idempotency:rollback"),
        DeploymentFingerprint("sha256:" + "4" * 64),
        FencingReference("fencing:rollback-generation-1"),
    )
    assert preparation.rollback.intended_revision == rollback.intended_revision
    assert isinstance(apply_request.idempotency_key, DeploymentIdempotencyKey)
    with pytest.raises(InvalidRollbackProgression):
        replace(preparation, authorization_reference=AuthorizationReference("authorization:other"))


@pytest.mark.parametrize(
    "outcome",
    [
        RollbackApplyOutcome.PARTIALLY_ROLLED_BACK,
        RollbackApplyOutcome.FAILED,
        RollbackApplyOutcome.OUTCOME_UNKNOWN,
    ],
)
def test_rollback_apply_outcomes_do_not_infer_verification(outcome) -> None:
    result = DeploymentRollbackApplyResultV1(outcome)
    assert result.rollback_receipt_reference is None
    assert not hasattr(result, "verification_reference")


def test_rolled_back_requires_receipt_and_rollback_observe_verify_are_distinct() -> None:
    _, target, _, _, _, _ = _facts()
    rollback = _rollback(target)
    rolled_back = DeploymentRollbackApplyResultV1(
        RollbackApplyOutcome.ROLLED_BACK,
        RollbackReceiptReference("rollback-receipt:ports"),
    )
    assert rolled_back.rollback_receipt_reference is not None
    with pytest.raises(InvalidRollbackProgression):
        DeploymentRollbackApplyResultV1(RollbackApplyOutcome.ROLLED_BACK)
    observation_request = DeploymentRollbackObservationRequestV1(rollback, target)
    observation_ref = ObservationReference("observation:rollback-ports")
    observation = DeploymentRollbackObservationResultV1(
        RollbackObservationOutcome.OBSERVED,
        observation_ref,
        ObservedRevisionV1(rollback.intended_revision, observation_ref),
    )
    verification_request = DeploymentRollbackVerificationRequestV1(
        rollback,
        target,
        observation,
        PolicyReference("policy:rollback-verification"),
    )
    verified = DeploymentRollbackVerificationResultV1(
        RollbackVerificationOutcome.VERIFIED,
        VerificationReference("verification:rollback-ports"),
    )
    assert observation_request.rollback == rollback
    assert verification_request.observation == observation
    assert verified.verification_reference is not None


def test_rollback_wrong_target_or_observed_revision_is_rejected() -> None:
    _, target, _, _, _, _ = _facts()
    rollback = _rollback(target)
    other_target = replace(target, target_id=DeploymentTargetId("deployment-target:other"))
    with pytest.raises(InvalidRollbackProgression):
        DeploymentRollbackObservationRequestV1(rollback, other_target)
    observation_ref = ObservationReference("observation:wrong-revision")
    observation = DeploymentRollbackObservationResultV1(
        RollbackObservationOutcome.OBSERVED,
        observation_ref,
        ObservedRevisionV1(RevisionId("deployment-revision:wrong"), observation_ref),
    )
    with pytest.raises(InvalidRollbackProgression):
        DeploymentRollbackVerificationRequestV1(
            rollback, target, observation, PolicyReference("policy:rollback-verification")
        )
